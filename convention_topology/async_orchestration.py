"""Async batch scheduler (③⑤⑥): run many independent runs concurrently under a
global rate-limit ceiling, with provider failover wired in.

Concurrency model — two independent knobs:
- `run_concurrency`: how many *runs* share the event loop at once
  (`asyncio.Semaphore`). Coarse bound; also the only bound for the offline mock.
- `api_concurrency`: total *in-flight API calls* across all runs, owned by the
  shared `RateLimiter` inside one `ProviderPool` (Step ①'s measured ceiling).

Each run stays a sequential coroutine (`async_run.execute_run_async`); the
Markov chain is untouched. All grid construction, seeding, resume/skip, targeting
and metadata come from the sync `orchestration.py` so both engines agree.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from convention_topology.async_llm import (
    AsyncClientAdapter,
    AsyncOpenAICompatClient,
    AsyncRetryPolicy,
    ProviderPool,
    RateLimiter,
    RateLimitedError,
)
from convention_topology.async_run import execute_run_async
from convention_topology.llm import OPENAI_RETRY_EXCEPTIONS, MockLLMClient, RunFailedError
from convention_topology.orchestration import (
    GridCell,
    ProgressHeartbeat,
    _counts_as_success,
    _log_progress,
    _run_id_for_cell,
    build_run_config_for_cell,
    existing_status,
    options_for_program,
    pilot_grid,
    cell_targets,
)
from convention_topology.config import derive_seeds
from convention_topology.persistence import delete_run_artifacts, read_meta, run_paths
import random


# Async retry catches the same failures as the sync path, plus the pool's
# endpoint-level 429 signal so failover/backoff runs through one code path.
_ASYNC_RETRY_EXCEPTIONS = OPENAI_RETRY_EXCEPTIONS + (RateLimitedError,)


def async_retry_policy_for(model_spec) -> AsyncRetryPolicy:
    if model_spec.shorthand == "mock":
        return AsyncRetryPolicy()
    return AsyncRetryPolicy(retry_on=_ASYNC_RETRY_EXCEPTIONS)


def build_provider_pool(model_spec, *, api_concurrency: int) -> ProviderPool:
    """Construct the shared endpoint pool for a real model (⑤ scaffold).

    Today: exactly one endpoint (the resolved model_spec). To add providers /
    keys later, resolve additional `AsyncOpenAICompatClient`s for the *same
    model weights* and pass them all here — no simulation change required.
    """
    endpoint = AsyncOpenAICompatClient(
        base_url=model_spec.base_url,
        model_id=model_spec.model_id,
        api_key_env=model_spec.api_key_env,
        temperature=model_spec.temperature,
        max_tokens=model_spec.max_tokens,
        openrouter_provider=model_spec.openrouter_provider,
    )
    limiter = RateLimiter(api_concurrency)
    return ProviderPool([endpoint], rate_limiter=limiter, names=[model_spec.provider])


def _build_run_client(model_spec, shared_pool, mock_policy: str, run_seed: int, options_list: list[str]):
    """Per-run client: shared pool for real models; fresh mock adapter otherwise.

    Mock clients must be per-run (own RNG seeded by `run_seed`) to match the sync
    engine; real runs share one pool so the rate limiter and endpoint cooldowns
    are global.
    """
    if model_spec.shorthand == "mock":
        return AsyncClientAdapter(
            MockLLMClient(policy=mock_policy, rng=random.Random(run_seed), options=options_list)
        )
    return shared_pool


async def _run_one_cell(
    config, model_spec, cell: GridCell, shared_pool, *, data_dir: Path, logs_dir: Path,
    mock_policy: str, console_progress: bool,
) -> str:
    opts = options_for_program(config, cell.program)
    client = _build_run_client(model_spec, shared_pool, mock_policy, cell.run_seed, opts)
    run_config = build_run_config_for_cell(config, model_spec, cell)
    paths = await execute_run_async(
        run_config, client, data_dir=data_dir, logs_dir=logs_dir,
        retry_policy=async_retry_policy_for(model_spec), console_progress=console_progress,
    )
    return read_meta(paths.meta_path)["run_status"]


async def run_batch_async(
    config, model_spec, cells: list[GridCell], *, data_dir: Path, logs_dir: Path,
    mock_policy: str, run_concurrency: int, api_concurrency: int, retry_failed: bool,
    progress: bool = False,
) -> dict[str, str]:
    """Async resume-by-sidecar batch (fixed grid). Returns {run_id: final_status}."""
    to_run: list[GridCell] = []
    results: dict[str, str] = {}

    for cell in cells:
        run_id = _run_id_for_cell(model_spec.shorthand, cell)
        status = existing_status(data_dir, logs_dir, model_spec, cell)
        if status in ("completed", "censored"):
            results[run_id] = status
            continue
        if status == "failed" and not retry_failed:
            results[run_id] = status
            continue
        if status == "failed" and retry_failed:
            delete_run_artifacts(run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id))
        to_run.append(cell)

    total = len(to_run)
    _log_progress(
        progress,
        f"[abatch] model={model_spec.shorthand} run_concurrency={run_concurrency} "
        f"api_concurrency={api_concurrency} to_run={total} skipped_resume={len(cells) - total}",
    )
    if total == 0:
        return results

    shared_pool = None if model_spec.shorthand == "mock" else build_provider_pool(
        model_spec, api_concurrency=api_concurrency
    )
    semaphore = asyncio.Semaphore(run_concurrency)

    async def _guarded(cell: GridCell, heartbeat: ProgressHeartbeat):
        run_id = _run_id_for_cell(model_spec.shorthand, cell)
        async with semaphore:
            heartbeat.mark_start(run_id)
            _log_progress(progress, f"[start] {run_id} program={cell.program} topology={cell.topology} k={cell.cm_k}")
            try:
                status = await _run_one_cell(
                    config, model_spec, cell, shared_pool,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy,
                    console_progress=progress,
                )
            except RunFailedError as exc:
                logging.warning("async orchestration: cell %s failed: %s", run_id, exc)
                status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
            except Exception:
                logging.exception("async orchestration: cell %s raised outside execute_run_async", run_id)
                status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
            done = heartbeat.mark_done(run_id)
            _log_progress(progress, f"[done]  {run_id}: {status}  ({done}/{total})")
            return run_id, status

    with ProgressHeartbeat(logs_dir=logs_dir, total=total, enabled=progress) as heartbeat:
        gathered = await asyncio.gather(*(_guarded(cell, heartbeat) for cell in to_run))
    for run_id, status in gathered:
        results[run_id] = status

    if progress:
        counts: dict[str, int] = {}
        for status in results.values():
            counts[status] = counts.get(status, 0) + 1
        _log_progress(True, "[abatch] finished — " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return results


def run_pilot_async(
    config, model_spec, *, program: str, data_dir: Path, logs_dir: Path, mock_policy: str,
    run_concurrency: int, api_concurrency: int, retry_failed: bool,
    topology_filter: str | None = None, progress: bool = False,
) -> dict[str, str]:
    cells = pilot_grid(config.run.base_seed, program)
    if topology_filter:
        cells = [cell for cell in cells if cell.topology == topology_filter]
    return asyncio.run(
        run_batch_async(
            config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy,
            run_concurrency=run_concurrency, api_concurrency=api_concurrency,
            retry_failed=retry_failed, progress=progress,
        )
    )


async def run_cell_targeted_async(
    config, model_spec, program: str, topology: str, cm_k: int, target: int, attempted_cap: int,
    shared_pool, semaphore: asyncio.Semaphore, *, data_dir: Path, logs_dir: Path, mock_policy: str,
    retry_failed: bool, progress: bool, heartbeat: ProgressHeartbeat | None,
) -> dict:
    """Run seeds in concurrent waves until `target` successes or `attempted_cap`.

    A wave launches up to `target - success` runs at once; results are folded in,
    then another wave starts if still short. Skips/resumes are honoured exactly as
    in the sync targeted path; only the launching is parallel.
    """
    success_count = 0
    attempted_count = 0
    seed_index = 0
    runs: list[tuple[str, str]] = []
    _log_progress(progress, f"[acell] start program={program} topology={topology} k={cm_k} target={target}")

    async def _attempt(cell: GridCell) -> tuple[str, str]:
        run_id = _run_id_for_cell(model_spec.shorthand, cell)
        async with semaphore:
            if heartbeat is not None:
                heartbeat.mark_start(run_id)
            try:
                status = await _run_one_cell(
                    config, model_spec, cell, shared_pool,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy, console_progress=progress,
                )
            except RunFailedError as exc:
                logging.warning("async orchestration: targeted cell %s failed: %s", run_id, exc)
                status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
            except Exception:
                logging.exception("async orchestration: targeted cell %s raised unexpectedly", run_id)
                status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
            finally:
                if heartbeat is not None:
                    heartbeat.mark_done(run_id)
            return run_id, status

    while success_count < target and attempted_count < attempted_cap:
        wave: list[GridCell] = []
        # Fill a wave, consuming already-finished seeds synchronously (no launch).
        while len(wave) < (target - success_count) and attempted_count + len(wave) < attempted_cap:
            seed_index += 1
            graph_seed, run_seed = derive_seeds(config.run.base_seed, topology, cm_k, seed_index)
            cell = GridCell(program, topology, seed_index, cm_k, graph_seed, run_seed)
            run_id = _run_id_for_cell(model_spec.shorthand, cell)
            status = existing_status(data_dir, logs_dir, model_spec, cell)
            if status in ("completed", "censored") or (status == "failed" and not retry_failed):
                attempted_count += 1
                if _counts_as_success(program, status):
                    success_count += 1
                runs.append((run_id, status))
                _log_progress(progress, f"[skip]  {run_id}: {status} (eligible={success_count}/{target})")
                continue
            if status == "failed" and retry_failed:
                delete_run_artifacts(run_paths(data_dir, logs_dir, model_spec.shorthand, topology, run_id))
            wave.append(cell)

        if not wave:
            # Wave was all skips/resumes (no launches); loop guard advances via
            # seed_index/attempted_count, so re-evaluate the while condition.
            continue
        results = await asyncio.gather(*(_attempt(cell) for cell in wave))
        for run_id, status in results:
            attempted_count += 1
            if _counts_as_success(program, status):
                success_count += 1
            runs.append((run_id, status))
            _log_progress(progress, f"[done]  {run_id}: {status} (eligible={success_count}/{target})")

    result = {
        "program": program, "topology": topology, "cm_k": cm_k, "target": target,
        "attempted_cap": attempted_cap, "attempted": attempted_count, "eligible": success_count, "runs": runs,
    }
    _log_progress(progress, f"[acell] done program={program} topology={topology} k={cm_k} eligible={success_count}/{target}")
    return result


async def run_main_study_async(
    config, model_spec, *, program: str, data_dir: Path, logs_dir: Path, mock_policy: str,
    retry_failed: bool, topology_filter: str | None = None,
    run_concurrency: int = 8, api_concurrency: int = 8, progress: bool = False,
) -> list[dict]:
    targets = cell_targets(config, program)
    if topology_filter:
        targets = [row for row in targets if row["topology"] == topology_filter]

    _log_progress(
        progress,
        f"[amain] model={model_spec.shorthand} program={program} run_concurrency={run_concurrency} "
        f"api_concurrency={api_concurrency} cells={len(targets)}",
    )

    shared_pool = None if model_spec.shorthand == "mock" else build_provider_pool(
        model_spec, api_concurrency=api_concurrency
    )
    semaphore = asyncio.Semaphore(run_concurrency)

    with ProgressHeartbeat(logs_dir=logs_dir, total=None, enabled=progress, label="alive") as heartbeat:
        results = await asyncio.gather(
            *(
                run_cell_targeted_async(
                    config, model_spec, program, row["topology"], row["cm_k"],
                    target=row["target_min"], attempted_cap=row["attempted_cap"],
                    shared_pool=shared_pool, semaphore=semaphore,
                    data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy,
                    retry_failed=retry_failed, progress=progress, heartbeat=heartbeat,
                )
                for row in targets
            )
        )
    results = sorted(results, key=lambda r: (r["topology"], r["cm_k"]))

    if progress:
        ok = sum(1 for r in results if r["eligible"] >= r["target"])
        _log_progress(True, f"[amain] finished — cells_ok={ok}/{len(results)}")
    return results
