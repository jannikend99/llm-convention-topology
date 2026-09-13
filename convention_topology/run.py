"""Counted run executor: one async engine, checkpoint-every-1, retry D split."""

from __future__ import annotations

import asyncio
import fcntl
import importlib.metadata
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import httpx

from convention_topology.config import ModelSpec, config_hash, protocol_fingerprint
from convention_topology.gate import evaluate_phase1_gate, has_tracker_converged
from convention_topology.json_output import ParseError, match_option_in_text, parse_decision
from convention_topology.llm import (
    AsyncClientAdapter,
    AsyncLLMClient,
    RunFailedError,
    classify_error,
    error_raw,
)
from convention_topology.networks import adjacency_hash, get_interaction_network, graph_stats
from convention_topology.persistence import (
    SCHEMA_VERSION,
    EventWriter,
    PersistenceError,
    RunPaths,
    build_run_id,
    empty_sidecar,
    encode_run_key,
    ensure_run_dirs,
    load_run_pickle,
    read_events,
    read_meta,
    run_paths,
    save_run_pickle,
    write_meta,
)
from convention_topology.pool import options_for_program
from convention_topology.prepared import (
    PreparedInitError,
    assert_prepared,
    make_prepared_population,
)
from convention_topology.prompting import (
    PROMPT_TEMPLATE_VERSION,
    build_user_prompt,
    prompt_template_hash,
    rendered_prompt_hash,
)
from convention_topology.seeds import (
    ENVIRONMENT_TAGS,
    SEED_SCHEME_VERSION,
    attempt_seed,
    environment_seed,
    graph_seed,
    model_seed,
    substream,
)
from convention_topology.simulation import swap_committed
from convention_topology.tracker import empty_tracker, get_outcome, update_dict, update_tracker

PROGRAM_EMERGENCE = "emergence"
PROGRAM_CM = "cm"

StopHook = Callable[[str], None]

_PROCESS_STOP: dict[str, str | None] = {"reason": None}
_SIGTERM_INSTALLED = False


def process_stop_reason() -> str | None:
    return _PROCESS_STOP["reason"]


def install_process_sigterm() -> None:
    """Install one process-wide SIGTERM/SIGINT handler shared by concurrent runs."""
    global _SIGTERM_INSTALLED
    if _SIGTERM_INSTALLED:
        return

    def _handler(signum, frame):
        _PROCESS_STOP["reason"] = "killed"

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    _SIGTERM_INSTALLED = True


class StopRequested(BaseException):
    """Injected or SIGTERM persistence-boundary stop."""


@dataclass
class RunConfig:
    program: str
    model_shorthand: str
    model_id: str
    model_revision: str
    endpoint_base_url: str
    provider: str
    topology: str
    campaign: str
    seed_index: int
    graph_seed: int
    environment_seed: int
    model_seed: int
    base_seed: int
    config_hash: str
    protocol_fingerprint: str
    prompt_template_version: str
    prompt_template_hash: str
    code_commit: str
    options: Sequence[str]
    label_pool: Sequence[str]
    pool_seed: int
    pool_sha256: str
    rewards: Sequence[int] = (-50, 100)
    memory_size: int = 12
    n: int = 48
    string_length: int = 5
    json_schema: bool = True
    cm_k: int | None = None
    incumbent_index: int = 0
    gate_window: int = 144
    max_phase1_interactions: int = 5000
    phase2_horizon: int = 1000
    checkpoint_every: int = 1
    degree: int = 4
    ws_k: int = 4
    ws_p: float = 0.1
    ba_m: int = 2
    retry_max_attempts: int = 3
    temperature: float = 0.5
    max_tokens: int = 512
    serve_wait_timeout: float = 600.0
    thinking: bool = False
    thinking_always_on: bool = False
    reasoning_effort: str | None = None
    sampling_plan: str = "fixed_attempted"
    attempted_per_cell: int = 32
    dtype: str | None = None
    quantization: str | None = None
    tensor_parallel: int = 1
    max_concurrent_runs: int = 1
    in_flight_limit: int = 1
    max_num_seqs: int = 1
    fallback_from: str | None = None
    schema_version: int = SCHEMA_VERSION
    artifact_root: str = ""
    slurm_job_id: str | None = None
    hostname: str | None = None


def default_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _gpu_ids_from_env(env: Mapping[str, str]) -> list[str] | None:
    for key in ("CUDA_VISIBLE_DEVICES", "SLURM_JOB_GPUS", "SLURM_STEP_GPUS", "SLURM_GPUS_ON_NODE"):
        raw = env.get(key)
        if raw is None:
            continue
        parts = [part.strip() for part in str(raw).replace(";", ",").split(",") if part.strip()]
        if parts:
            return parts
    return None


def job_forensics(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """GPU/vLLM sidecar fields from the job environment. Laptop/mock: all None."""
    env = os.environ if environ is None else environ
    empty = {"gpu_ids": None, "gpu_type": None, "vllm_version": None, "torch_version": None}
    if not env.get("SLURM_JOB_ID"):
        return empty
    gpu_type = env.get("GPU_TYPE") or env.get("SLURM_GPU_TYPE") or None
    if gpu_type == "":
        gpu_type = None
    vllm_version = env.get("VLLM_VERSION") or _package_version("vllm")
    torch_version = env.get("TORCH_VERSION") or _package_version("torch")
    if not vllm_version:
        vllm_version = None
    if not torch_version:
        torch_version = None
    return {
        "gpu_ids": _gpu_ids_from_env(env),
        "gpu_type": gpu_type,
        "vllm_version": vllm_version,
        "torch_version": torch_version,
    }


def build_run_config(
    config: Mapping[str, Any],
    model_spec: ModelSpec,
    *,
    program: str,
    topology: str,
    seed_index: int,
    cm_k: int | None,
    pool_labels: Sequence[str],
    pool_sha256: str,
    code_commit: str,
    artifact_root: str = "",
) -> RunConfig:
    protocol = config["protocol"]
    network = config["network"]
    run = config["run"]
    if program == PROGRAM_EMERGENCE:
        cm_k = None
    options = options_for_program(pool_labels, program)
    return RunConfig(
        program=program,
        model_shorthand=model_spec.shorthand,
        model_id=model_spec.model_id,
        model_revision=model_spec.revision,
        endpoint_base_url=model_spec.base_url,
        provider=model_spec.provider,
        topology=topology,
        campaign=str(run["campaign"]),
        seed_index=seed_index,
        graph_seed=graph_seed(int(run["base_seed"]), topology),
        environment_seed=environment_seed(int(run["base_seed"]), program, topology, cm_k, seed_index),
        model_seed=model_seed(int(run["base_seed"]), model_spec.model_id, program, topology, cm_k, seed_index),
        base_seed=int(run["base_seed"]),
        config_hash=config_hash(config),
        protocol_fingerprint=protocol_fingerprint(config),
        prompt_template_version=str(run["prompt_template_version"]),
        prompt_template_hash=prompt_template_hash(),
        code_commit=code_commit,
        options=options,
        label_pool=list(pool_labels),
        pool_seed=int(config["pool"]["seed"]),
        pool_sha256=pool_sha256,
        rewards=(int(protocol["rewards_mismatch"]), int(protocol["rewards_match"])),
        memory_size=int(protocol["H"]),
        n=int(protocol["N"]),
        string_length=int(protocol["string_length"]),
        json_schema=str(protocol.get("diag_decode") or "json_schema") == "json_schema",
        cm_k=cm_k,
        incumbent_index=0,
        gate_window=3 * int(protocol["N"]),
        max_phase1_interactions=int(protocol["cap_phase1"]),
        phase2_horizon=int(protocol["phase2_horizon"]),
        checkpoint_every=int(run["checkpoint_every"]),
        degree=int(network["degree"]),
        ws_k=int(network["ws_k"]),
        ws_p=float(network["ws_p"]),
        ba_m=int(network["ba_m"]),
        retry_max_attempts=int(protocol["retry_max_attempts"]),
        temperature=float(protocol["temperature"]),
        max_tokens=int(model_spec.max_tokens),
        serve_wait_timeout=float(config["serve"]["serve_wait_timeout"]),
        thinking=model_spec.thinking,
        thinking_always_on=model_spec.thinking_always_on,
        reasoning_effort=model_spec.reasoning_effort,
        sampling_plan=str(run["sampling_plan"]),
        attempted_per_cell=int(run["attempted_per_cell"]),
        dtype=model_spec.dtype,
        quantization=model_spec.quantization,
        tensor_parallel=model_spec.tp,
        max_concurrent_runs=model_spec.max_concurrent_runs,
        in_flight_limit=model_spec.in_flight_limit,
        max_num_seqs=model_spec.max_num_seqs,
        fallback_from=model_spec.fallback_from,
        schema_version=int(run["schema_version"]),
        artifact_root=artifact_root,
        slurm_job_id=os.environ.get("SLURM_JOB_ID"),
        hostname=os.environ.get("HOSTNAME") or os.uname().nodename,
    )


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PersistenceError(f"another live writer owns {self.path}") from exc

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def models_health_ok(base_url: str, timeout: float = 2.0) -> bool:
    if not base_url:
        return True
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        url = root + "/models"
    else:
        url = root + "/v1/models"
    try:
        response = httpx.get(url, timeout=timeout)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


@dataclass
class RunState:
    simulation: dict[int, dict]
    tracker: dict[str, list]
    convergence: dict[str, Any]
    rng_pairing: random.Random
    rng_option: random.Random
    committed_ids: list[int]
    n_api_calls: int = 0
    n_retries: int = 0
    n_skipped_cm_turns: int = 0
    wait_on_model_ms: int = 0
    graph_draw_attempts: int = 1
    prepared_state_valid: bool | None = None
    started_at: str = field(default_factory=default_now)
    run_segments: list[dict[str, Any]] = field(default_factory=list)
    last_checkpoint_t: int = 0


def _pair(simulation: dict[int, dict], rng: random.Random) -> tuple[int, int]:
    p1 = rng.choice(list(simulation.keys()))
    p2 = rng.choice(simulation[p1]["neighbours"])
    return p1, p2


def _sidecar(cfg: RunConfig, run_id: str, run_key: dict, state: RunState, *, status: str, stop_reason: str | None, error_class: str | None, extra: dict[str, Any]) -> dict[str, Any]:
    stats = graph_stats(state.simulation)
    meta = empty_sidecar()
    W = len(cfg.options)
    topology = cfg.topology
    meta.update(
        {
            "run_id": run_id,
            "campaign": cfg.campaign,
            "run_key": run_key,
            "program": cfg.program,
            "init_mode": "organic" if cfg.program == PROGRAM_EMERGENCE else "prepared",
            "topology": cfg.topology,
            "cell_key": run_key["cell_key"],
            "seed_index": cfg.seed_index,
            "sampling_plan": cfg.sampling_plan,
            "attempted_per_cell": cfg.attempted_per_cell,
            "replaced": False,
            "adaptive_targeting": False,
            "N": cfg.n,
            "H": cfg.memory_size,
            "W": W,
            "string_length": cfg.string_length,
            "edge_count": stats["edge_count"],
            "realized_mean_degree": stats["realized_mean_degree"],
            "nominal_degree": cfg.n - 1 if topology == "mixing" else 4,
            "ws_k": cfg.ws_k if topology == "watts_strogatz" else None,
            "ws_p": cfg.ws_p if topology == "watts_strogatz" else None,
            "ba_m": cfg.ba_m if topology == "barabasi_albert" else None,
            "graph_draw_attempts": state.graph_draw_attempts,
            "graph_connected": stats["graph_connected"],
            "lattice_kind": "ring_degree4" if topology == "lattice" else None,
            "cm_k": cfg.cm_k,
            "cm_mode": "swap",
            "pairing_rule": "random_agent_then_neighbor",
            "rewards_match": cfg.rewards[1],
            "rewards_mismatch": cfg.rewards[0],
            "success_rule": "payoff_gt_5",
            "gate_threshold": 0.95,
            "gate_window": cfg.gate_window,
            "cap_phase1": cfg.max_phase1_interactions if cfg.program == PROGRAM_EMERGENCE else None,
            "phase2_horizon": cfg.phase2_horizon if cfg.program == PROGRAM_CM else None,
            "retry_max_attempts": cfg.retry_max_attempts,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            "top_p": None,
            "top_k": None,
            "json_schema": cfg.json_schema,
            "response_format": "json_schema" if cfg.json_schema else "option_match",
            "label_pool": list(cfg.label_pool),
            "pool_seed": cfg.pool_seed,
            "pool_sha256": cfg.pool_sha256,
            "options": list(cfg.options),
            "incumbent_index": cfg.incumbent_index if cfg.program == PROGRAM_CM else None,
            "incumbent_label": state.convergence.get("incumbent_label"),
            "committed_to": state.convergence.get("committed_to"),
            "committed_ids": list(state.committed_ids),
            "model_id": cfg.model_id,
            "model_revision": cfg.model_revision,
            "model_shorthand": cfg.model_shorthand,
            "served_model_name": cfg.model_id,
            "thinking": cfg.thinking,
            "reasoning_effort": cfg.reasoning_effort,
            "thinking_always_on": cfg.thinking_always_on,
            "fallback_applied": bool(cfg.fallback_from),
            "fallback_from": cfg.fallback_from,
            "provider": cfg.provider if cfg.provider != "mock" else "openai_compat",
            "endpoint_base_url": cfg.endpoint_base_url or "http://127.0.0.1:0/v1",
            "cloud_credential_used": False,
            **job_forensics(),
            "python_version": sys.version.split()[0],
            "dtype": cfg.dtype,
            "quantization": cfg.quantization,
            "tensor_parallel": cfg.tensor_parallel,
            "max_concurrent_runs": cfg.max_concurrent_runs,
            "in_flight_limit": cfg.in_flight_limit,
            "max_num_seqs": cfg.max_num_seqs,
            "homogeneous": True,
            "graph_seed": cfg.graph_seed,
            "environment_seed": cfg.environment_seed,
            "model_seed": cfg.model_seed,
            "base_seed": cfg.base_seed,
            "seed_scheme_version": SEED_SCHEME_VERSION,
            "environment_substream_tags": list(ENVIRONMENT_TAGS),
            "adjacency_hash": adjacency_hash(state.simulation),
            "prompt_template_version": cfg.prompt_template_version or PROMPT_TEMPLATE_VERSION,
            "prompt_template_hash": cfg.prompt_template_hash,
            "schema_version": cfg.schema_version,
            "config_hash": cfg.config_hash,
            "code_commit": cfg.code_commit,
            "protocol_fingerprint": cfg.protocol_fingerprint,
            "chat_template_hash": None,
            "slurm_job_id": cfg.slurm_job_id,
            "hostname": cfg.hostname,
            "run_segments": list(state.run_segments),
            "checkpoint_every": cfg.checkpoint_every,
            "last_checkpoint_t": state.last_checkpoint_t,
            "artifact_root": cfg.artifact_root,
            "run_status": status,
            "stop_reason": stop_reason,
            "error_class": error_class,
            "gate_passed": extra.get("gate_passed"),
            "prepared_state_valid": state.prepared_state_valid,
            "t_gate": extra.get("t_gate"),
            "t_phase1_end": extra.get("t_phase1_end"),
            "t_cm_start": 0 if cfg.program == PROGRAM_CM else None,
            "started_at": state.started_at,
            "finished_at": extra.get("finished_at"),
            "n_interactions": len(state.tracker["outcome"]),
            "n_api_calls": state.n_api_calls,
            "n_retries": state.n_retries,
            "n_skipped_cm_turns": state.n_skipped_cm_turns,
            "wait_on_model_ms": state.wait_on_model_ms,
            "n_models_in_run": 1,
        }
    )
    if cfg.provider == "mock":
        meta["provider"] = "openai_compat"
    return meta


def _checkpoint(paths: RunPaths, cfg: RunConfig, run_id: str, run_key: dict, state: RunState, **kwargs) -> None:
    t = len(state.tracker["outcome"])
    state.last_checkpoint_t = t
    save_run_pickle(
        paths.pickle_path,
        state.simulation,
        state.tracker,
        state.convergence,
        rng_states={
            "pairing": state.rng_pairing.getstate(),
            "option": state.rng_option.getstate(),
        },
    )
    write_meta(paths.meta_path, _sidecar(cfg, run_id, run_key, state, **kwargs))


def _resume_gates(cfg: RunConfig, meta: Mapping[str, Any], state: RunState) -> None:
    checks = {
        "protocol_fingerprint": cfg.protocol_fingerprint,
        "prompt_template_hash": cfg.prompt_template_hash,
        "pool_sha256": cfg.pool_sha256,
        "adjacency_hash": adjacency_hash(state.simulation),
        "seed_scheme_version": SEED_SCHEME_VERSION,
        "model_revision": cfg.model_revision,
        "schema_version": cfg.schema_version,
    }
    for key, expected in checks.items():
        if meta.get(key) != expected:
            raise RunFailedError(f"resume blocked: {key} mismatch", error_class="config")


def _in_flight_at_send(limiter: asyncio.Semaphore | None, *, limit: int) -> int | None:
    if limiter is None:
        return None
    remaining = int(getattr(limiter, "_value"))
    return max(0, int(limit) - remaining)


async def _decision(
    *,
    cfg: RunConfig,
    state: RunState,
    client: AsyncLLMClient,
    prompt: str,
    options: Sequence[str],
    run_id: str,
    t: int,
    agent_id: int,
    partner_id: int,
    option_order: Sequence[str],
    events: EventWriter,
    health: Callable[[], bool],
    sleep: Callable[[float], Any],
    on_stop: StopHook | None,
    limiter: asyncio.Semaphore | None,
) -> tuple[str, str]:
    decision_id = f"{t}:{agent_id}"
    consuming = 0
    attempt_index = 0
    serve_wait_start = time.monotonic()
    prompt_sha256 = rendered_prompt_hash(prompt)
    while True:
        if on_stop:
            on_stop("before_attempt")
        attempt_index += 1
        if cfg.provider != "mock" and not health():
            t_start = default_now()
            wait_t0 = time.monotonic()
            elapsed = time.monotonic() - serve_wait_start
            sleep_for = 0.0 if elapsed >= cfg.serve_wait_timeout else min(1.0, cfg.serve_wait_timeout - elapsed)
            if sleep_for > 0:
                await sleep(sleep_for)
            duration_ms = int((time.monotonic() - wait_t0) * 1000)
            state.wait_on_model_ms += duration_ms
            row = _attempt_row(
                cfg, run_id, decision_id, t, agent_id, partner_id, attempt_index, option_order,
                schema_valid=False, error_class="transport", raw="", enum_label=None, reason=None,
                duration_ms=duration_ms, http_status=None, finish_reason=None, usage={},
                prompt_sha256=prompt_sha256, t_start=t_start, t_end=default_now(),
                in_flight_at_send=_in_flight_at_send(limiter, limit=cfg.in_flight_limit),
            )
            events.emit(row)
            if on_stop:
                on_stop("after_attempt")
            if elapsed >= cfg.serve_wait_timeout:
                raise RunFailedError("serve wait timeout", error_class="serve_startup")
            continue
        t_start = default_now()
        t0 = time.monotonic()
        occupancy = _in_flight_at_send(limiter, limit=cfg.in_flight_limit)
        try:
            if limiter is not None:
                async with limiter:
                    occupancy = _in_flight_at_send(limiter, limit=cfg.in_flight_limit)
                    response = await client.complete(prompt, options=options)
            else:
                occupancy = None
                response = await client.complete(prompt, options=options)
            duration_ms = int((time.monotonic() - t0) * 1000)
            t_end = default_now()
            state.n_api_calls += 1
            state.wait_on_model_ms += duration_ms
            value, reason = (
                parse_decision(response.text, options)
                if cfg.json_schema
                else match_option_in_text(response.text, options)
            )
            row = _attempt_row(
                cfg, run_id, decision_id, t, agent_id, partner_id, attempt_index, option_order,
                schema_valid=True, error_class=None, raw=response.text, enum_label=value, reason=reason,
                duration_ms=duration_ms, http_status=response.http_status, finish_reason=response.finish_reason,
                usage=response.usage, reasoning=response.reasoning,
                prompt_sha256=prompt_sha256, t_start=t_start, t_end=t_end,
                in_flight_at_send=occupancy,
            )
            events.emit(row)
            if on_stop:
                on_stop("after_attempt")
            return value, row["attempt_id"]
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            t_end = default_now()
            state.n_api_calls += 1
            state.wait_on_model_ms += duration_ms
            error_class = classify_error(exc)
            consuming += 1
            state.n_retries += 1
            raw = error_raw(exc)
            row = _attempt_row(
                cfg, run_id, decision_id, t, agent_id, partner_id, attempt_index, option_order,
                schema_valid=False, error_class=error_class, raw=raw, enum_label=None, reason=None,
                duration_ms=duration_ms, http_status=getattr(exc, "status_code", None), finish_reason=None,
                usage={}, prompt_sha256=prompt_sha256, t_start=t_start, t_end=t_end,
                in_flight_at_send=occupancy if limiter is not None else None,
            )
            events.emit(row)
            if on_stop:
                on_stop("after_attempt")
            if consuming >= cfg.retry_max_attempts:
                raise RunFailedError("decision attempts exhausted", error_class="attempts_exhausted") from exc
            continue


def _attempt_row(
    cfg: RunConfig,
    run_id: str,
    decision_id: str,
    t: int,
    agent_id: int,
    partner_id: int,
    attempt_index: int,
    option_order: Sequence[str],
    **kwargs,
) -> dict[str, Any]:
    attempt_id = f"{decision_id}:{attempt_index}"
    now = default_now()
    return {
        "schema_version": cfg.schema_version,
        "record_type": "llm_attempt",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "decision_id": decision_id,
        "t": t,
        "agent_id": agent_id,
        "partner_id": partner_id,
        "attempt_index": attempt_index,
        "attempt_seed": attempt_seed(cfg.model_seed, decision_id, attempt_index),
        "schema_valid": kwargs["schema_valid"],
        "t_start": kwargs.get("t_start") or now,
        "t_end": kwargs.get("t_end") or now,
        "duration_ms": kwargs["duration_ms"],
        "prompt_tokens": (kwargs.get("usage") or {}).get("prompt_tokens"),
        "completion_tokens": (kwargs.get("usage") or {}).get("completion_tokens"),
        "reasoning_tokens": (kwargs.get("usage") or {}).get("reasoning_tokens"),
        "finish_reason": kwargs.get("finish_reason"),
        "http_status": kwargs.get("http_status"),
        "error_class": kwargs.get("error_class"),
        "enum_label": kwargs.get("enum_label"),
        "reason": kwargs.get("reason"),
        "raw_response_text": kwargs.get("raw"),
        "reasoning": kwargs.get("reasoning"),
        "option_order": list(option_order),
        "parse_method": (
            "json_schema" if kwargs["schema_valid"] and cfg.json_schema else "option_match" if kwargs["schema_valid"] else "fail"
        ),
        "prompt_sha256": kwargs.get("prompt_sha256"),
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "queue_wait_ms": None,
        "inference_ms": None,
        "in_flight_at_send": kwargs.get("in_flight_at_send"),
    }


async def _one_interaction(
    cfg: RunConfig,
    state: RunState,
    client: AsyncLLMClient,
    events: EventWriter,
    run_id: str,
    *,
    health: Callable[[], bool],
    sleep,
    on_stop: StopHook | None,
    limiter: asyncio.Semaphore | None,
) -> None:
    t = len(state.tracker["outcome"]) + 1
    p1, p2 = _pair(state.simulation, state.rng_pairing)
    option_order = list(cfg.options)
    state.rng_option.shuffle(option_order)
    answers: list[str | None] = [None, None]
    used_ids: list[str | None] = [None, None]
    llm_calls = [False, False]
    pending: list[tuple[int, Any]] = []
    for slot, (agent, partner) in enumerate(((p1, p2), (p2, p1))):
        player = state.simulation[agent]
        if player.get("committed_tag"):
            answers[slot] = state.convergence["committed_to"]
            used_ids[slot] = None
            llm_calls[slot] = False
            state.n_skipped_cm_turns += 1
            continue
        prompt = build_user_prompt(player, cfg.memory_size, cfg.rewards, option_order)
        pending.append(
            (
                slot,
                _decision(
                    cfg=cfg,
                    state=state,
                    client=client,
                    prompt=prompt,
                    options=option_order,
                    run_id=run_id,
                    t=t,
                    agent_id=agent,
                    partner_id=partner,
                    option_order=option_order,
                    events=events,
                    health=health,
                    sleep=sleep,
                    on_stop=on_stop,
                    limiter=limiter,
                ),
            )
        )
    if pending:
        results = await asyncio.gather(*(coro for _slot, coro in pending))
        for (slot, _coro), (label, attempt_id) in zip(pending, results):
            answers[slot] = label
            used_ids[slot] = attempt_id
            llm_calls[slot] = True
    a1, a2 = answers
    payoff = get_outcome(a1, a2, cfg.rewards)
    state.simulation[p1]["interactions"].append(p2)
    state.simulation[p2]["interactions"].append(p1)
    update_dict(state.simulation[p1], a1, a2, payoff)
    update_dict(state.simulation[p2], a2, a1, payoff)
    update_tracker(state.tracker, p1, p2, a1, a2, payoff)
    success = 1 if payoff > 5 else 0
    events.emit(
        {
            "schema_version": cfg.schema_version,
            "record_type": "interaction",
            "run_id": run_id,
            "t": t,
            "p1": p1,
            "p2": p2,
            "label_p1": a1,
            "label_p2": a2,
            "success": success,
            "payoff_p1": payoff,
            "payoff_p2": payoff,
            "option_order_p1": list(option_order),
            "option_order_p2": list(option_order),
            "llm_call_p1": llm_calls[0],
            "llm_call_p2": llm_calls[1],
            "used_attempt_id_p1": used_ids[0],
            "used_attempt_id_p2": used_ids[1],
        }
    )
    events.sync()
    if on_stop:
        on_stop("after_interaction")


def _init_state(cfg: RunConfig) -> RunState:
    rng_pairing = random.Random(substream(cfg.environment_seed, "pairing"))
    rng_option = random.Random(substream(cfg.environment_seed, "option"))
    rng_committed = random.Random(substream(cfg.environment_seed, "committed"))
    if cfg.program == PROGRAM_CM:
        if cfg.cm_k is None or cfg.cm_k < 1:
            raise ValueError("cm program requires cm_k")
        simulation, tracker, convergence, attempts = make_prepared_population(
            cfg.topology,
            n=cfg.n,
            graph_seed=cfg.graph_seed,
            rewards=cfg.rewards,
            options=cfg.options,
            memory_size=cfg.memory_size,
            incumbent_index=cfg.incumbent_index,
            degree=cfg.degree,
            ws_k=cfg.ws_k,
            ws_p=cfg.ws_p,
            ba_m=cfg.ba_m,
        )
        committed_ids = swap_committed(simulation, cfg.cm_k, rng_committed)
        try:
            assert_prepared(
                simulation,
                cfg.options,
                cfg.memory_size,
                cfg.incumbent_index,
                cm_k=cfg.cm_k,
                committed_ids=committed_ids,
                rewards_match=cfg.rewards[1],
            )
            prepared_ok = True
        except PreparedInitError:
            prepared_ok = False
        return RunState(
            simulation=simulation,
            tracker=tracker,
            convergence=convergence,
            rng_pairing=rng_pairing,
            rng_option=rng_option,
            committed_ids=committed_ids,
            graph_draw_attempts=attempts,
            prepared_state_valid=prepared_ok,
        )
    simulation, attempts = get_interaction_network(
        cfg.topology,
        n=cfg.n,
        degree=cfg.degree,
        graph_seed=cfg.graph_seed,
        ws_k=cfg.ws_k,
        ws_p=cfg.ws_p,
        ba_m=cfg.ba_m,
    )
    return RunState(
        simulation=simulation,
        tracker=empty_tracker(),
        convergence={"converged_index": None, "incumbent_label": None, "committed_to": None},
        rng_pairing=rng_pairing,
        rng_option=rng_option,
        committed_ids=[],
        graph_draw_attempts=attempts,
        prepared_state_valid=None,
    )


def _replay_interactions(state: RunState, records: list[dict[str, Any]], options: Sequence[str]) -> None:
    interactions = [row for row in records if row.get("record_type") == "interaction"]
    expected_t = 1
    for row in interactions:
        t = row["t"]
        if t != expected_t:
            raise RunFailedError(f"discontinuous interaction t={t}", error_class="config")
        if t <= len(state.tracker["outcome"]):
            existing_p = state.tracker["players"][t - 1]
            if existing_p != [row["p1"], row["p2"]]:
                raise RunFailedError("pickle ahead of events mismatch", error_class="config")
            expected_t += 1
            continue
        p1, p2 = _pair(state.simulation, state.rng_pairing)
        if (p1, p2) != (row["p1"], row["p2"]):
            raise RunFailedError("replay pairing RNG mismatch", error_class="config")
        option_order = list(options)
        state.rng_option.shuffle(option_order)
        recorded_order = row.get("option_order_p1")
        if recorded_order is not None and list(recorded_order) != option_order:
            raise RunFailedError("replay option RNG mismatch", error_class="config")
        a1, a2 = row["label_p1"], row["label_p2"]
        payoff = row["payoff_p1"]
        state.simulation[p1]["interactions"].append(p2)
        state.simulation[p2]["interactions"].append(p1)
        update_dict(state.simulation[p1], a1, a2, payoff)
        update_dict(state.simulation[p2], a2, a1, payoff)
        update_tracker(state.tracker, p1, p2, a1, a2, payoff)
        expected_t += 1


async def execute_run_async(
    cfg: RunConfig,
    client: AsyncLLMClient,
    *,
    campaign_dir: Path,
    health: Callable[[], bool] | None = None,
    sleep=asyncio.sleep,
    on_stop: StopHook | None = None,
    limiter: asyncio.Semaphore | None = None,
    install_sigterm: bool = False,
) -> RunPaths:
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
    ensure_run_dirs(paths)
    lock = FileLock(paths.lock_path)
    lock.acquire()
    if install_sigterm:
        install_process_sigterm()

    def boundary(kind: str) -> None:
        reason = process_stop_reason()
        if reason:
            raise StopRequested(reason)
        if on_stop:
            on_stop(kind)

    health_fn = health or (lambda: models_health_ok(cfg.endpoint_base_url) if cfg.provider != "mock" else True)
    events = EventWriter(paths.events_path)
    segment = {
        "segment_id": len(read_events(paths.events_path)) + 1,
        "slurm_job_id": cfg.slurm_job_id,
        "hostname": cfg.hostname,
        "started_at": default_now(),
        "start_t": 0,
        "slice_id": f"{cfg.seed_index}",
    }
    try:
        if paths.meta_path.exists():
            meta = read_meta(paths.meta_path)
            status = meta.get("run_status")
            if status in {"completed", "censored"}:
                events.close()
                lock.release()
                return paths
            if status == "failed":
                events.close()
                lock.release()
                return paths
            pickle_payload = load_run_pickle(paths.pickle_path)
            state = RunState(
                simulation=pickle_payload["simulation"],
                tracker=pickle_payload["tracker"],
                convergence=pickle_payload["convergence"],
                rng_pairing=random.Random(substream(cfg.environment_seed, "pairing")),
                rng_option=random.Random(substream(cfg.environment_seed, "option")),
                committed_ids=list(meta.get("committed_ids") or []),
                n_api_calls=int(meta.get("n_api_calls") or 0),
                n_retries=int(meta.get("n_retries") or 0),
                n_skipped_cm_turns=int(meta.get("n_skipped_cm_turns") or 0),
                wait_on_model_ms=int(meta.get("wait_on_model_ms") or 0),
                graph_draw_attempts=int(meta.get("graph_draw_attempts") or 1),
                prepared_state_valid=meta.get("prepared_state_valid"),
                started_at=meta.get("started_at") or default_now(),
                run_segments=list(meta.get("run_segments") or []),
                last_checkpoint_t=int(meta.get("last_checkpoint_t") or 0),
            )
            rng_states = pickle_payload.get("rng_states") or {}
            if "pairing" in rng_states:
                state.rng_pairing.setstate(rng_states["pairing"])
            if "option" in rng_states:
                state.rng_option.setstate(rng_states["option"])
            _resume_gates(cfg, meta, state)
            records = read_events(paths.events_path)
            pickle_t = len(state.tracker["outcome"])
            event_t = len([r for r in records if r.get("record_type") == "interaction"])
            if pickle_t > event_t:
                raise RunFailedError("pickle ahead of interaction journal", error_class="config")
            if pickle_t < event_t:
                _replay_interactions(state, records, cfg.options)
                _checkpoint(
                    paths, cfg, run_id, run_key, state,
                    status="in_progress", stop_reason=None, error_class=None, extra={"gate_passed": meta.get("gate_passed")},
                )
            boundary("after_sidecar")
        else:
            state = _init_state(cfg)
            if cfg.program == PROGRAM_CM and not state.prepared_state_valid:
                raise RunFailedError("prepared_state_valid is false", error_class="config")
        segment["start_t"] = len(state.tracker["outcome"])
        events.emit(
            {
                "schema_version": cfg.schema_version,
                "record_type": "run_segment_start",
                "run_id": run_id,
                **segment,
            }
        )
        if cfg.program == PROGRAM_CM and not any(
            row.get("record_type") == "prepared_state" for row in read_events(paths.events_path)
        ):
            memory_vector = [state.simulation[i]["my_history"][-1] if state.simulation[i]["my_history"] else None for i in sorted(state.simulation)]
            events.emit(
                {
                    "schema_version": cfg.schema_version,
                    "record_type": "prepared_state",
                    "run_id": run_id,
                    "t": 0,
                    "memory_labels": memory_vector,
                    "committed_ids": list(state.committed_ids),
                    "prepared_score": cfg.memory_size * cfg.rewards[1],
                    "memory_incumbent_share": 1.0,
                    "committed_policy_share": (cfg.cm_k or 0) / cfg.n,
                    "success": None,
                    "prepared_state_valid": state.prepared_state_valid,
                }
            )
            if on_stop:
                on_stop("after_prepared")
        _checkpoint(
            paths, cfg, run_id, run_key, state,
            status="in_progress", stop_reason=None, error_class=None,
            extra={"gate_passed": None if cfg.program == PROGRAM_CM else False},
        )
        boundary("after_sidecar")

        horizon = cfg.max_phase1_interactions if cfg.program == PROGRAM_EMERGENCE else cfg.phase2_horizon
        while True:
            if cfg.program == PROGRAM_EMERGENCE and has_tracker_converged(state.tracker, window=cfg.gate_window):
                break
            if len(state.tracker["outcome"]) >= horizon:
                break
            await _one_interaction(
                cfg, state, client, events, run_id,
                health=health_fn, sleep=sleep, on_stop=boundary, limiter=limiter,
            )
            _checkpoint(
                paths, cfg, run_id, run_key, state,
                status="in_progress", stop_reason=None, error_class=None,
                extra={"gate_passed": False if cfg.program == PROGRAM_EMERGENCE else None},
            )
            boundary("after_pickle")
            boundary("after_sidecar")

        extra: dict[str, Any] = {"finished_at": default_now()}
        if cfg.program == PROGRAM_EMERGENCE:
            gate = evaluate_phase1_gate(
                state.tracker, window=cfg.gate_window, max_phase1_interactions=cfg.max_phase1_interactions
            )
            extra.update(
                gate_passed=gate.gate_passed,
                t_gate=gate.t_gate,
                t_phase1_end=len(state.tracker["outcome"]),
            )
            status, stop_reason = gate.run_status, gate.stop_reason
            state.convergence["converged_index"] = gate.t_gate
        else:
            extra.update(gate_passed=None, t_gate=None, t_phase1_end=None)
            status, stop_reason = "completed", "horizon"
        _checkpoint(paths, cfg, run_id, run_key, state, status=status, stop_reason=stop_reason, error_class=None, extra=extra)
        events.emit(
            {
                "schema_version": cfg.schema_version,
                "record_type": "run_segment_end",
                "run_id": run_id,
                "ended_at": default_now(),
                "end_t": len(state.tracker["outcome"]),
                "termination_reason": stop_reason,
            }
        )
        return paths
    except StopRequested:
        if "state" not in locals():
            state = _init_state(cfg)
        _checkpoint(
            paths, cfg, run_id, run_key, state,
            status="interrupted", stop_reason="killed", error_class=None,
            extra={"finished_at": None, "gate_passed": False if cfg.program == PROGRAM_EMERGENCE else None},
        )
        events.emit(
            {
                "schema_version": cfg.schema_version,
                "record_type": "run_segment_end",
                "run_id": run_id,
                "ended_at": default_now(),
                "end_t": len(state.tracker["outcome"]),
                "termination_reason": "killed",
            }
        )
        return paths
    except RunFailedError as exc:
        if "state" not in locals():
            state = _init_state(cfg)
        _checkpoint(
            paths, cfg, run_id, run_key, state,
            status="failed", stop_reason="failed", error_class=exc.error_class,
            extra={"finished_at": default_now(), "gate_passed": False if cfg.program == PROGRAM_EMERGENCE else None},
        )
        events.emit(
            {
                "schema_version": cfg.schema_version,
                "record_type": "run_segment_end",
                "run_id": run_id,
                "ended_at": default_now(),
                "end_t": len(state.tracker["outcome"]),
                "termination_reason": "failed",
                "error_class": exc.error_class,
            }
        )
        raise
    finally:
        events.close()
        lock.release()


def execute_run(cfg: RunConfig, client, *, campaign_dir: Path, **kwargs) -> RunPaths:
    async_client = client if hasattr(client, "complete") and asyncio.iscoroutinefunction(getattr(client, "complete", None)) else AsyncClientAdapter(client)
    return asyncio.run(execute_run_async(cfg, async_client, campaign_dir=campaign_dir, **kwargs))
