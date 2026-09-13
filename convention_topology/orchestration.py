"""Planner and async counted batch engine. No counted workers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from convention_topology.campaign import ensure_campaign_files
from convention_topology.config import (
    K_SET,
    TOPOLOGIES,
    ModelSpec,
    resolve_model,
)
from convention_topology.git_guard import current_commit, require_clean_worktree
from convention_topology.llm import (
    AsyncClientAdapter,
    AsyncOpenAICompatClient,
    MockLLMClient,
    request_timeout,
)
from convention_topology.persistence import build_run_id, encode_run_key, read_meta, run_paths
from convention_topology.pool import options_for_program
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    build_run_config,
    execute_run_async,
    install_process_sigterm,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class JobSlice:
    model: str
    model_id: str
    program: str
    seed_from: int
    seed_to: int
    gpus: int


def planned_models(config: Mapping[str, Any]) -> list[str]:
    return list(config["jobs"]["models"])


def planned_programs(config: Mapping[str, Any], program: str | None = None) -> list[str]:
    if program:
        return [program]
    return list(config["jobs"].get("programs") or [PROGRAM_EMERGENCE, PROGRAM_CM])


def seed_slices(attempted: int, slice_size: int) -> list[tuple[int, int]]:
    if slice_size <= 0:
        raise ValueError("seed_indices_per_slice must be positive")
    ranges = []
    start = 0
    while start < attempted:
        end = min(start + slice_size, attempted)
        ranges.append((start, end))
        start = end
    covered: set[int] = set()
    for a, b in ranges:
        chunk = set(range(a, b))
        if covered & chunk:
            raise ValueError("planner slices intersect")
        covered |= chunk
    if covered != set(range(attempted)):
        raise ValueError("planner slices do not tile [0, attempted_per_cell)")
    return ranges


def print_jobs(config: Mapping[str, Any], *, program: str | None = None) -> list[JobSlice]:
    attempted = int(config["run"]["attempted_per_cell"])
    jobs: list[JobSlice] = []
    for model in planned_models(config):
        spec = resolve_model(config, model)
        for prog in planned_programs(config, program):
            size = spec.seed_indices_per_slice[prog]
            for seed_from, seed_to in seed_slices(attempted, size):
                jobs.append(
                    JobSlice(
                        model=model,
                        model_id=spec.model_id,
                        program=prog,
                        seed_from=seed_from,
                        seed_to=seed_to,
                        gpus=spec.gpus,
                    )
                )
    return jobs


def format_job_line(job: JobSlice) -> str:
    return (
        f"python run_main.py --model {job.model} --program {job.program} "
        f"--seed-from {job.seed_from} --seed-to {job.seed_to} "
        f"# model_id={job.model_id} gpus={job.gpus}"
    )


def cell_grid(
    config: Mapping[str, Any],
    *,
    program: str,
    topology: str | None = None,
    k: int | None = None,
    seed_from: int = 0,
    seed_to: int | None = None,
) -> list[dict[str, Any]]:
    attempted = int(config["run"]["attempted_per_cell"])
    end = attempted if seed_to is None else seed_to
    topologies = [topology] if topology else list(TOPOLOGIES)
    rows = []
    if program == PROGRAM_EMERGENCE:
        for topo in topologies:
            for seed_index in range(seed_from, end):
                rows.append({"program": program, "topology": topo, "cm_k": None, "seed_index": seed_index})
        return rows
    ks = [k] if k is not None else list(K_SET)
    for topo in topologies:
        for cm_k in ks:
            for seed_index in range(seed_from, end):
                rows.append({"program": program, "topology": topo, "cm_k": cm_k, "seed_index": seed_index})
    return rows


def build_client(model_spec: ModelSpec, mock_policy: str, seed: int, options: Sequence[str], *, json_schema: bool = True):
    if model_spec.provider == "mock" or model_spec.shorthand == "mock":
        import random

        return AsyncClientAdapter(
            MockLLMClient(policy=mock_policy, rng=random.Random(seed), options=list(options))
        )
    return AsyncOpenAICompatClient(
        base_url=model_spec.base_url,
        model_id=model_spec.model_id,
        api_key=model_spec.api_key,
        temperature=model_spec.temperature,
        max_tokens=model_spec.max_tokens,
        timeout=request_timeout(thinking=model_spec.thinking),
        provider=model_spec.provider,
        reasoning_effort=model_spec.reasoning_effort,
        thinking=model_spec.thinking,
        json_schema=json_schema,
        send_chat_template_kwargs=model_spec.send_chat_template_kwargs,
        thinking_token_budget=model_spec.thinking_token_budget,
    )


async def run_slice_async(
    config: Mapping[str, Any],
    model_spec: ModelSpec,
    *,
    program: str,
    campaign_dir: Path,
    topology: str | None = None,
    k: int | None = None,
    seed_from: int = 0,
    seed_to: int | None = None,
    mock_policy: str = "imitate_modal",
    require_clean: bool = False,
) -> list[str]:
    if require_clean:
        require_clean_worktree(REPO_ROOT)
    files = ensure_campaign_files(campaign_dir, config)
    cells = cell_grid(
        config, program=program, topology=topology, k=k, seed_from=seed_from, seed_to=seed_to
    )
    install_process_sigterm()
    limiter = asyncio.Semaphore(model_spec.in_flight_limit)
    run_slots = asyncio.Semaphore(model_spec.max_concurrent_runs)
    commit = current_commit(REPO_ROOT)
    statuses: list[str] = []
    print(
        "[slice] max_concurrent_runs="
        f"{model_spec.max_concurrent_runs} in_flight_limit={model_spec.in_flight_limit} "
        f"max_num_seqs={model_spec.max_num_seqs}",
        flush=True,
    )

    async def _one(cell: dict[str, Any]) -> str:
        cfg = build_run_config(
            config,
            model_spec,
            program=cell["program"],
            topology=cell["topology"],
            seed_index=cell["seed_index"],
            cm_k=cell["cm_k"],
            pool_labels=files["pool"]["labels"],
            pool_sha256=files["pool"]["sha256"],
            code_commit=commit,
            artifact_root=str(campaign_dir),
        )
        run_key = encode_run_key(
            campaign=cfg.campaign,
            program=cfg.program,
            model_id=cfg.model_id,
            topology=cfg.topology,
            cm_k=cfg.cm_k,
            seed_index=cfg.seed_index,
        )
        run_id = build_run_id(run_key)
        paths = run_paths(campaign_dir, cfg.model_shorthand, cfg.topology, run_id)
        if paths.meta_path.exists():
            meta = read_meta(paths.meta_path)
            if meta.get("run_status") in {"completed", "censored", "failed"}:
                return meta["run_status"]
        async with run_slots:
            options = options_for_program(files["pool"]["labels"], program)
            decode = str(config["protocol"].get("diag_decode") or "json_schema")
            client = build_client(
                model_spec,
                mock_policy,
                cfg.model_seed,
                options,
                json_schema=decode == "json_schema",
            )
            try:
                await execute_run_async(cfg, client, campaign_dir=campaign_dir, limiter=limiter)
                return read_meta(paths.meta_path)["run_status"]
            except Exception:
                if paths.meta_path.exists():
                    return read_meta(paths.meta_path).get("run_status", "failed")
                return "failed"

    for coro in asyncio.as_completed([_one(cell) for cell in cells]):
        statuses.append(await coro)
    return statuses
