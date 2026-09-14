"""Planner and async counted batch engine. No counted workers."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
HEARTBEAT_INTERVAL_S = 2.0


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def allocation_job_id() -> str:
    slurm = os.environ.get("SLURM_JOB_ID")
    if slurm:
        return str(slurm)
    return f"local-{os.getpid()}"


def heartbeat_path(campaign_dir: Path, job_id: str) -> Path:
    return Path(campaign_dir) / "jobs" / f"{job_id}.live.json"


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.flush()
    tmp_path.replace(path)


@dataclass
class _QueueFill:
    live_run_ids: list[str] = field(default_factory=list)
    queued_run_ids: list[str] = field(default_factory=list)
    in_flight_http: int = 0


class _HttpLimiter:
    def __init__(self, bound: int, fill: _QueueFill):
        self._sem = asyncio.Semaphore(bound)
        self._fill = fill

    async def __aenter__(self) -> "_HttpLimiter":
        await self._sem.acquire()
        self._fill.in_flight_http += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._fill.in_flight_http -= 1
        self._sem.release()

    @property
    def _value(self) -> int:
        return int(self._sem._value)


_SEED_SPAN = re.compile(r"^(\d+)-(\d+)$")
_ALLOWED_TOPOLOGIES = frozenset(TOPOLOGIES)
_ALLOWED_K = frozenset(K_SET)


class TaskSpecError(ValueError):
    """Invalid --task grammar or duplicate cells."""


@dataclass(frozen=True)
class JobSlice:
    model: str
    model_id: str
    program: str
    seed_from: int
    seed_to: int
    gpus: int


@dataclass(frozen=True)
class TaskSpec:
    program: str
    topologies: tuple[str, ...]
    seed_from: int
    seed_to: int
    k_values: tuple[int, ...] | None


def parse_task(spec: str) -> TaskSpec:
    raw = str(spec).strip()
    if not raw:
        raise TaskSpecError("empty --task")
    parts = raw.split(":")
    k_values: tuple[int, ...] | None = None
    if parts[-1].startswith("k="):
        k_token = parts.pop()
        body = k_token[2:]
        if not body:
            raise TaskSpecError("cm k= list is empty")
        try:
            parsed_k = tuple(int(item) for item in body.split(","))
        except ValueError as exc:
            raise TaskSpecError("k= values must be integers") from exc
        unknown = [k for k in parsed_k if k not in _ALLOWED_K]
        if unknown:
            raise TaskSpecError(f"unknown k values: {unknown}")
        k_values = parsed_k
    if len(parts) != 3:
        raise TaskSpecError(
            "task must be PROGRAM:TOPOLOGIES:FROM-TO or PROGRAM:TOPOLOGIES:FROM-TO:k=KLIST"
        )
    program, topologies_s, span_s = parts
    if program not in {PROGRAM_EMERGENCE, PROGRAM_CM}:
        raise TaskSpecError(f"unknown program {program!r}")
    if program == PROGRAM_EMERGENCE and k_values is not None:
        raise TaskSpecError("emergence must not include k=")
    if program == PROGRAM_CM and k_values is None:
        raise TaskSpecError("cm requires k=")
    if not topologies_s or topologies_s == "all":
        raise TaskSpecError("topologies must be named; implicit all is not allowed")
    topologies = tuple(item.strip() for item in topologies_s.split(",") if item.strip())
    if not topologies:
        raise TaskSpecError("topologies must be named; implicit all is not allowed")
    unknown_topo = [name for name in topologies if name not in _ALLOWED_TOPOLOGIES]
    if unknown_topo:
        raise TaskSpecError(f"unknown topologies: {unknown_topo}")
    match = _SEED_SPAN.fullmatch(span_s)
    if not match:
        raise TaskSpecError("seed span must be FROM-TO with integers")
    seed_from = int(match.group(1))
    seed_to = int(match.group(2))
    if seed_to <= seed_from:
        raise TaskSpecError("seed span FROM-TO must be a non-empty half-open interval")
    return TaskSpec(
        program=program,
        topologies=topologies,
        seed_from=seed_from,
        seed_to=seed_to,
        k_values=k_values,
    )


def flatten_tasks(tasks: Sequence[TaskSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None, int]] = set()
    for task in tasks:
        ks: Sequence[int | None]
        if task.program == PROGRAM_EMERGENCE:
            ks = (None,)
        else:
            ks = task.k_values or ()
        for topology in task.topologies:
            for cm_k in ks:
                for seed_index in range(task.seed_from, task.seed_to):
                    key = (task.program, topology, cm_k, seed_index)
                    if key in seen:
                        raise TaskSpecError(
                            "duplicate cell in --task list: "
                            f"{task.program} {topology} k={cm_k} seed={seed_index}"
                        )
                    seen.add(key)
                    rows.append(
                        {
                            "program": task.program,
                            "topology": topology,
                            "cm_k": cm_k,
                            "seed_index": seed_index,
                        }
                    )
    return rows


def format_queue_summary(cells: Sequence[Mapping[str, Any]]) -> str:
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for cell in cells:
        k_label = "na" if cell["cm_k"] is None else str(cell["cm_k"])
        groups[(str(cell["program"]), str(cell["topology"]), k_label)].append(int(cell["seed_index"]))
    lines: list[str] = []
    for (program, topology, k_label), seeds in groups.items():
        seeds = sorted(seeds)
        lines.append(
            f"{program} {topology} k={k_label} seeds={seeds[0]}-{seeds[-1] + 1} n={len(seeds)}"
        )
    lines.append(f"total_cells={len(cells)}")
    return "\n".join(lines)


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
    cells: Sequence[Mapping[str, Any]],
    campaign_dir: Path,
    mock_policy: str = "imitate_modal",
    require_clean: bool = False,
    task_argv: Sequence[str] | None = None,
) -> list[str]:
    if require_clean:
        require_clean_worktree(REPO_ROOT)
    files = ensure_campaign_files(campaign_dir, config)
    install_process_sigterm()
    fill = _QueueFill()
    limiter = _HttpLimiter(model_spec.in_flight_limit, fill)
    run_slots = asyncio.Semaphore(model_spec.max_concurrent_runs)
    commit = current_commit(REPO_ROOT)
    statuses: list[str] = []
    started_at = _utc_stamp()
    job_id = allocation_job_id()
    live_path = heartbeat_path(campaign_dir, job_id)
    tasks = list(task_argv or [])
    print(
        "[slice] max_concurrent_runs="
        f"{model_spec.max_concurrent_runs} in_flight_limit={model_spec.in_flight_limit} "
        f"max_num_seqs={model_spec.max_num_seqs}",
        flush=True,
    )

    def _heartbeat_payload() -> dict[str, Any]:
        payload: dict[str, Any] = {
            "heartbeat_at": _utc_stamp(),
            "in_flight_http": fill.in_flight_http,
            "live_run_ids": list(fill.live_run_ids),
            "live_runs": len(fill.live_run_ids),
            "max_concurrent_runs": model_spec.max_concurrent_runs,
            "model_shorthand": model_spec.shorthand,
            "queued_run_ids": list(fill.queued_run_ids),
            "started_at": started_at,
            "tasks": tasks,
        }
        slurm_timelimit = os.environ.get("SLURM_TIMELIMIT")
        if slurm_timelimit:
            payload["slurm_timelimit"] = slurm_timelimit
        return payload

    def _write_heartbeat() -> None:
        write_json_atomic(live_path, _heartbeat_payload())

    async def _heartbeat_loop(stop: asyncio.Event) -> None:
        _write_heartbeat()
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_S)
            except asyncio.TimeoutError:
                _write_heartbeat()
        _write_heartbeat()

    async def _one(cell: Mapping[str, Any]) -> str:
        program = str(cell["program"])
        cfg = build_run_config(
            config,
            model_spec,
            program=program,
            topology=str(cell["topology"]),
            seed_index=int(cell["seed_index"]),
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
        fill.queued_run_ids.append(run_id)
        async with run_slots:
            if run_id in fill.queued_run_ids:
                fill.queued_run_ids.remove(run_id)
            fill.live_run_ids.append(run_id)
            try:
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
            finally:
                if run_id in fill.live_run_ids:
                    fill.live_run_ids.remove(run_id)

    work = [dict(cell) for cell in cells]
    stop_hb = asyncio.Event()
    hb_task = asyncio.create_task(_heartbeat_loop(stop_hb))
    try:
        for coro in asyncio.as_completed([_one(cell) for cell in work]):
            statuses.append(await coro)
    finally:
        stop_hb.set()
        await hb_task
    return statuses
