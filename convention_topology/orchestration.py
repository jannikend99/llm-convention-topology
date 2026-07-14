"""Shared run-dispatch orchestration (§0 principle 6: CLIs are thin).

Single home for everything `run_one.py` / `run_pilot.py` / `run_main.py`
need to build a `RunConfig`, a client, and a retry policy, plus the pilot
grid/batch dispatch and main-study eligible-count targeting loop. CLIs
import from here and reduce to argument parsing + one call.
"""

from __future__ import annotations

import logging
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from convention_topology.config import config_hash, derive_seeds
from convention_topology.llm import OPENAI_RETRY_EXCEPTIONS, MockLLMClient, OpenAICompatClient, RetryPolicy
from convention_topology.persistence import PersistenceError, build_run_id, delete_run_artifacts, read_meta, run_paths
from convention_topology.prompting import PROMPT_TEMPLATE_VERSION
from convention_topology.run import RunConfig, execute_run

TOPOLOGIES = ("complete", "random_regular", "lattice")
SEEDS_PER_TOPOLOGY = 12
K_LEVELS = 6
MAIN_K_LEVELS = range(1, 7)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_code_commit() -> str:
    """Real short git HEAD hash of *this* repo, or `"unknown"` outside a repo.

    R2-M1: pinned to `_REPO_ROOT`, not the process cwd -- a bare `git
    rev-parse` run from a CLI launched out of a different git repo (e.g.
    the meta-repo root) would otherwise silently record that repo's
    commit instead of this one's.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


@dataclass(frozen=True)
class GridCell:
    topology: str
    seed_index: int
    cm_k: int
    graph_seed: int
    run_seed: int


def rewards(config) -> tuple[int, int]:
    return tuple(config.params.rewards_set[0])


def options(config) -> list[str]:
    return list(config.params.options_set[0])


def build_run_config(
    config,
    model_spec,
    *,
    topology: str,
    cm_k: int,
    graph_seed: int,
    run_seed: int,
) -> RunConfig:
    resolved = {
        "model": model_spec.shorthand,
        "provider": model_spec.provider,
        "model_id": model_spec.model_id,
        "endpoint_base_url": model_spec.base_url,
        "topology": topology,
        "cm_k": cm_k,
        "run_seed": run_seed,
        "graph_seed": graph_seed,
        "params": {
            "rewards": rewards(config),
            "options": options(config),
            "memory_size": config.params.memory_size_set[0],
            "n": config.params.N,
            "convergence_threshold": config.params.convergence_threshold,
            "max_phase1_interactions": config.params.max_phase1_interactions,
            "phase2_horizon": config.params.total_interactions,
        },
    }
    if model_spec.openrouter_provider is not None:
        resolved["openrouter_provider"] = model_spec.openrouter_provider
    return RunConfig(
        model_shorthand=model_spec.shorthand,
        model_id=model_spec.model_id,
        endpoint_base_url=model_spec.base_url,
        topology=topology,
        cm_k=cm_k,
        graph_seed=graph_seed,
        run_seed=run_seed,
        config_hash=config_hash(resolved),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        code_commit=get_code_commit(),
        rewards=rewards(config),
        options=options(config),
        memory_size=config.params.memory_size_set[0],
        n=config.params.N,
        convergence_threshold=config.params.convergence_threshold,
        max_phase1_interactions=config.params.max_phase1_interactions,
        phase2_horizon=config.params.total_interactions,
        checkpoint_every=config.run.checkpoint_every,
    )


def build_run_config_for_cell(config, model_spec, cell: GridCell) -> RunConfig:
    return build_run_config(
        config, model_spec,
        topology=cell.topology, cm_k=cell.cm_k, graph_seed=cell.graph_seed, run_seed=cell.run_seed,
    )


def build_client(model_spec, mock_policy: str, run_seed: int, options_list: list[str]):
    if model_spec.shorthand == "mock":
        return MockLLMClient(policy=mock_policy, rng=random.Random(run_seed), options=options_list)
    return OpenAICompatClient(
        base_url=model_spec.base_url,
        model_id=model_spec.model_id,
        api_key_env=model_spec.api_key_env,
        temperature=model_spec.temperature,
        max_tokens=model_spec.max_tokens,
        openrouter_provider=model_spec.openrouter_provider,
    )


def retry_policy_for(model_spec) -> RetryPolicy:
    if model_spec.shorthand == "mock":
        return RetryPolicy()
    return RetryPolicy(retry_on=OPENAI_RETRY_EXCEPTIONS)


def existing_status(data_dir: Path, logs_dir: Path, model_spec, cell: GridCell) -> str | None:
    run_id = build_run_id(model_spec.shorthand, cell.topology, cell.cm_k, cell.run_seed)
    paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
    if not paths.meta_path.exists():
        return None
    try:
        return read_meta(paths.meta_path)["run_status"]
    except PersistenceError:
        return None


# ---------------------------------------------------------------------------
# Pilot batch (§5): 12 attempted Phase 1 runs/topology, k cyclic 1..6,1..6
# ---------------------------------------------------------------------------


def pilot_grid(base_seed: int) -> list[GridCell]:
    """36 rows: 12 seeds/topology, k assigned cyclically 1..6,1..6."""
    cells = []
    for topology in TOPOLOGIES:
        for seed_index in range(1, SEEDS_PER_TOPOLOGY + 1):
            cm_k = ((seed_index - 1) % K_LEVELS) + 1
            graph_seed, run_seed = derive_seeds(base_seed, topology, cm_k, seed_index)
            cells.append(GridCell(topology, seed_index, cm_k, graph_seed, run_seed))
    return cells


def run_cell(config, model_spec, cell: GridCell, *, data_dir: Path, logs_dir: Path, mock_policy: str) -> str:
    client = build_client(model_spec, mock_policy, cell.run_seed, options(config))
    run_config = build_run_config_for_cell(config, model_spec, cell)
    paths = execute_run(
        run_config,
        client,
        data_dir=data_dir,
        logs_dir=logs_dir,
        retry_policy=retry_policy_for(model_spec),
    )
    return read_meta(paths.meta_path)["run_status"]


def run_batch(
    config,
    model_spec,
    cells: list[GridCell],
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    workers: int,
    retry_failed: bool,
) -> dict[str, str]:
    """Resume-by-sidecar batch execution. Returns {run_id: final_status}."""
    to_run: list[GridCell] = []
    results: dict[str, str] = {}

    for cell in cells:
        run_id = build_run_id(model_spec.shorthand, cell.topology, cell.cm_k, cell.run_seed)
        status = existing_status(data_dir, logs_dir, model_spec, cell)
        if status in ("completed", "censored"):
            results[run_id] = status
            continue
        if status == "failed" and not retry_failed:
            results[run_id] = status
            continue
        if status == "failed" and retry_failed:
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            delete_run_artifacts(paths)
        to_run.append(cell)

    def _worker(cell: GridCell) -> tuple[str, str]:
        run_id = build_run_id(model_spec.shorthand, cell.topology, cell.cm_k, cell.run_seed)
        try:
            status = run_cell(config, model_spec, cell, data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy)
        except Exception:
            logging.exception("orchestration: cell %s raised outside execute_run's own failure handling", run_id)
            # execute_run only checkpoints run_status="failed" for RunFailedError;
            # any other exception may leave the sidecar unwritten or stale
            # ("in_progress"/missing) -- report what's actually on disk rather
            # than asserting "failed" when no sidecar was ever produced.
            status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
        return run_id, status

    if workers <= 1:
        for cell in to_run:
            run_id, status = _worker(cell)
            results[run_id] = status
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for run_id, status in pool.map(_worker, to_run):
                results[run_id] = status

    return results


def run_pilot(
    config,
    model_spec,
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    workers: int,
    retry_failed: bool,
) -> dict[str, str]:
    """Full pilot dispatch: grid -> batch. The one call `run_pilot.py` makes."""
    cells = pilot_grid(config.run.base_seed)
    return run_batch(
        config, model_spec, cells,
        data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy,
        workers=workers, retry_failed=retry_failed,
    )


# ---------------------------------------------------------------------------
# Main-study eligible-count targeting (§5, M01 locks)
# ---------------------------------------------------------------------------


def cell_targets(config) -> list[dict]:
    """Per-cell (topology, cm_k) eligible target (lower bound of the range) + attempted cap."""
    targets = config.run.main_eligible_targets
    cap_factor = config.run.attempted_cap_factor
    rows = []
    for topology in TOPOLOGIES:
        low, high = targets[topology]
        for cm_k in MAIN_K_LEVELS:
            rows.append(
                {
                    "topology": topology,
                    "cm_k": cm_k,
                    "eligible_target_min": low,
                    "eligible_target_max": high,
                    "attempted_cap": low * cap_factor,
                }
            )
    return rows


def run_cell_targeted(
    config,
    model_spec,
    topology: str,
    cm_k: int,
    target: int,
    attempted_cap: int,
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    retry_failed: bool,
) -> dict:
    eligible_count = 0
    attempted_count = 0
    seed_index = 0
    runs: list[tuple[str, str]] = []

    while eligible_count < target and attempted_count < attempted_cap:
        seed_index += 1
        graph_seed, run_seed = derive_seeds(config.run.base_seed, topology, cm_k, seed_index)
        cell = GridCell(topology, seed_index, cm_k, graph_seed, run_seed)
        run_id = build_run_id(model_spec.shorthand, topology, cm_k, run_seed)

        status = existing_status(data_dir, logs_dir, model_spec, cell)
        if status in ("completed", "censored"):
            attempted_count += 1
            if status == "completed":
                eligible_count += 1
            runs.append((run_id, status))
            continue
        if status == "failed" and not retry_failed:
            attempted_count += 1
            runs.append((run_id, status))
            continue
        if status == "failed" and retry_failed:
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, topology, run_id)
            delete_run_artifacts(paths)

        client = build_client(model_spec, mock_policy, cell.run_seed, options(config))
        run_config = build_run_config_for_cell(config, model_spec, cell)
        paths = execute_run(
            run_config, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=retry_policy_for(model_spec)
        )
        result_status = read_meta(paths.meta_path)["run_status"]
        attempted_count += 1
        if result_status == "completed":
            eligible_count += 1
        runs.append((run_id, result_status))

    return {
        "topology": topology,
        "cm_k": cm_k,
        "target": target,
        "attempted_cap": attempted_cap,
        "attempted": attempted_count,
        "eligible": eligible_count,
        "runs": runs,
    }


def run_main_study(
    config,
    model_spec,
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    retry_failed: bool,
    topology_filter: str | None = None,
) -> list[dict]:
    """Full main-study dispatch: targets -> per-cell targeted runs. The one call `run_main.py` makes."""
    targets = cell_targets(config)
    if topology_filter:
        targets = [row for row in targets if row["topology"] == topology_filter]

    results = []
    for row in targets:
        result = run_cell_targeted(
            config,
            model_spec,
            row["topology"],
            row["cm_k"],
            target=row["eligible_target_min"],
            attempted_cap=row["attempted_cap"],
            data_dir=data_dir,
            logs_dir=logs_dir,
            mock_policy=mock_policy,
            retry_failed=retry_failed,
        )
        results.append(result)
    return results
