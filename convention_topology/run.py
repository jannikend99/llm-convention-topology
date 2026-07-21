"""Run executors: emergence (organic Phase 1) and CM (prepared + Phase 2).

Ashery split: `bias_runner`-style emergence vs `committed_runner`-style CM on
prepared populations. No sequential Phase 1→2 on the same trajectory.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from convention_topology.gate import evaluate_phase1_gate, trailing_success_rate
from convention_topology.llm import LLMClient, LLMResponse, RetryPolicy, RunFailedError
from convention_topology.networks import adjacency_hash, get_interaction_network
from convention_topology.persistence import (
    EventWriter,
    RunPaths,
    build_run_id,
    ensure_run_dirs,
    load_run_pickle,
    read_meta,
    run_paths,
    save_run_pickle,
    write_meta,
)
from convention_topology.prepared import make_prepared_population
from convention_topology.simulation import make_interaction_step, run_phase2, swap_committed
from convention_topology.tracker import empty_tracker, modal_label_in_window

PROGRAM_EMERGENCE = "emergence"
PROGRAM_CM = "cm"


def _emit_progress(events: EventWriter, tracker: dict, phase: str, window: int) -> None:
    t = len(tracker["outcome"])
    if t % 10 != 0:
        return
    events.emit(
        {
            "type": f"{phase}_progress",
            "t": t,
            "phase": phase,
            "rolling_success": trailing_success_rate(tracker["outcome"], window),
            "dominant_share": _dominant_share(tracker, window),
        }
    )


def _dominant_share(tracker: dict, window: int) -> float | None:
    answers = tracker["answers"]
    if len(answers) < window:
        return None
    labels = [label for pair in answers[-window:] for label in pair]
    if not labels:
        return None
    dominant = modal_label_in_window(tracker, window)
    return labels.count(dominant) / len(labels)


def default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunConfig:
    program: str
    model_shorthand: str
    model_id: str
    endpoint_base_url: str
    topology: str
    graph_seed: int
    run_seed: int
    config_hash: str
    prompt_template_version: str
    code_commit: str
    options: Sequence[str]
    rewards: Sequence[int] = (-50, 100)
    memory_size: int = 5
    n: int = 24
    cm_k: int = 0
    incumbent_index: int = 0
    convergence_threshold: float = 0.95
    max_phase1_interactions: int = 5000
    phase2_horizon: int = 1000
    checkpoint_every: int = 50
    degree: int = 4


class _CountingClient:
    def __init__(self, client: LLMClient, on_response: Callable[[LLMResponse], None] | None = None):
        self._client = client
        self.calls = 0
        self._on_response = on_response

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls += 1
        response = self._client.complete(system, user)
        if self._on_response is not None:
            self._on_response(response)
        return response


def _base_meta(
    *,
    run_id: str,
    config: RunConfig,
    simulation: dict,
    convergence: dict,
    run_status: str,
    started_at: str,
    finished_at: str | None,
    n_api_calls: int,
    n_retries: int,
) -> dict:
    eligibility = 1 if convergence.get("converged_index") is not None else 0
    if config.program == PROGRAM_CM and run_status == "completed":
        eligibility = 1
    return {
        "run_id": run_id,
        "program": config.program,
        "init_mode": "organic" if config.program == PROGRAM_EMERGENCE else "prepared",
        "topology": config.topology,
        "cm_k": config.cm_k,
        "options": list(config.options),
        "incumbent_index": config.incumbent_index if config.program == PROGRAM_CM else None,
        "model_id": config.model_id,
        "model_shorthand": config.model_shorthand,
        "endpoint_base_url": config.endpoint_base_url,
        "graph_seed": config.graph_seed,
        "run_seed": config.run_seed,
        "adjacency_hash": adjacency_hash(simulation),
        "t_gate": convergence.get("converged_index"),
        "t_phase1_end": convergence.get("converged_index"),
        "eligibility": eligibility,
        "incumbent_label": convergence.get("incumbent_label"),
        "committed_to": convergence.get("committed_to"),
        "phase2_horizon": config.phase2_horizon if config.program == PROGRAM_CM else None,
        "config_hash": config.config_hash,
        "run_status": run_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "n_api_calls": n_api_calls,
        "n_retries": n_retries,
        "prompt_template_version": config.prompt_template_version,
        "code_commit": config.code_commit,
    }


def execute_emergence_run(
    config: RunConfig,
    client: LLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: RetryPolicy | None = None,
    now: Callable[[], str] = default_now,
) -> RunPaths:
    """Organic empty-start Phase 1 until gate or cap. No CM."""
    if config.program != PROGRAM_EMERGENCE:
        raise ValueError(f"execute_emergence_run requires program={PROGRAM_EMERGENCE!r}")

    run_id = build_run_id(
        config.model_shorthand, config.topology, config.run_seed, program=PROGRAM_EMERGENCE
    )
    paths = run_paths(data_dir, logs_dir, config.model_shorthand, config.topology, run_id)
    ensure_run_dirs(paths)
    convergence_time = 3 * config.n

    def on_response(response: LLMResponse) -> None:
        if response.usage:
            events.emit({"type": "token_usage", "model_id": response.model_id, **response.usage})

    counting_client = _CountingClient(client, on_response=on_response)

    existing_meta = read_meta(paths.meta_path) if paths.meta_path.exists() else None
    if existing_meta is not None and existing_meta["run_status"] in ("completed", "censored", "failed"):
        return paths

    started_at = existing_meta["started_at"] if existing_meta else now()
    n_retries = existing_meta["n_retries"] if existing_meta else 0

    if existing_meta is not None and existing_meta["run_status"] == "in_progress":
        payload = load_run_pickle(paths.pickle_path)
        simulation = payload["simulation"]
        tracker = payload["tracker"]
        convergence = payload["convergence"]
    else:
        simulation = get_interaction_network(
            config.topology, n=config.n, degree=config.degree, graph_seed=config.graph_seed
        )
        tracker = empty_tracker()
        convergence = {"converged_index": None, "incumbent_label": None, "committed_to": None}

    rng = random.Random(config.run_seed)
    events = EventWriter(paths.events_path)
    retries = {"n": n_retries}

    def on_attempt(attempt: int, exc: Exception | None) -> None:
        if exc is not None:
            retries["n"] += 1
            events.emit({"type": "retry", "attempt": attempt, "error": str(exc)})

    def checkpoint(run_status: str) -> None:
        if run_status in ("completed", "censored") and convergence.get("converged_index") is not None:
            if convergence.get("incumbent_label") is None:
                convergence["incumbent_label"] = modal_label_in_window(tracker, convergence_time)
        save_run_pickle(paths.pickle_path, simulation, tracker, convergence)
        write_meta(
            paths.meta_path,
            _base_meta(
                run_id=run_id,
                config=config,
                simulation=simulation,
                convergence=convergence,
                run_status=run_status,
                started_at=started_at,
                finished_at=now() if run_status in ("completed", "censored", "failed") else None,
                n_api_calls=counting_client.calls,
                n_retries=retries["n"],
            ),
        )

    try:
        phase1_step = make_interaction_step(
            simulation,
            counting_client,
            config.memory_size,
            config.rewards,
            config.options,
            rng,
            retry_policy=retry_policy,
            on_attempt=on_attempt,
        )
        interactions_since_checkpoint = 0
        while True:
            gate = evaluate_phase1_gate(
                tracker,
                convergence_time=convergence_time,
                threshold=config.convergence_threshold,
                max_phase1_interactions=config.max_phase1_interactions,
            )
            if gate.run_status != "incomplete":
                break
            phase1_step(tracker)
            _emit_progress(events, tracker, "phase1", convergence_time)
            interactions_since_checkpoint += 1
            if interactions_since_checkpoint >= config.checkpoint_every:
                checkpoint("in_progress")
                interactions_since_checkpoint = 0

        if gate.run_status == "censored":
            checkpoint("censored")
            return paths

        convergence["converged_index"] = gate.t_gate
        convergence["incumbent_label"] = modal_label_in_window(tracker, convergence_time)
        convergence["committed_to"] = None
        events.emit({"type": "gate_passed", "t_gate": gate.t_gate})
        checkpoint("completed")
        return paths

    except RunFailedError:
        checkpoint("failed")
        raise
    finally:
        events.close()


def execute_cm_run(
    config: RunConfig,
    client: LLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: RetryPolicy | None = None,
    now: Callable[[], str] = default_now,
) -> RunPaths:
    """Prepared population → swap CM → fixed Phase 2 horizon."""
    if config.program != PROGRAM_CM:
        raise ValueError(f"execute_cm_run requires program={PROGRAM_CM!r}")
    if config.cm_k < 1:
        raise ValueError(f"CM run requires cm_k >= 1; got {config.cm_k}")

    run_id = build_run_id(
        config.model_shorthand, config.topology, config.run_seed, program=PROGRAM_CM, cm_k=config.cm_k
    )
    paths = run_paths(data_dir, logs_dir, config.model_shorthand, config.topology, run_id)
    ensure_run_dirs(paths)
    convergence_time = 3 * config.n

    def on_response(response: LLMResponse) -> None:
        if response.usage:
            events.emit({"type": "token_usage", "model_id": response.model_id, **response.usage})

    counting_client = _CountingClient(client, on_response=on_response)

    existing_meta = read_meta(paths.meta_path) if paths.meta_path.exists() else None
    if existing_meta is not None and existing_meta["run_status"] in ("completed", "failed"):
        return paths

    started_at = existing_meta["started_at"] if existing_meta else now()
    n_retries = existing_meta["n_retries"] if existing_meta else 0

    if existing_meta is not None and existing_meta["run_status"] == "in_progress":
        payload = load_run_pickle(paths.pickle_path)
        simulation = payload["simulation"]
        tracker = payload["tracker"]
        convergence = payload["convergence"]
    else:
        simulation, tracker, convergence = make_prepared_population(
            config.topology,
            n=config.n,
            graph_seed=config.graph_seed,
            rewards=config.rewards,
            options=config.options,
            memory_size=config.memory_size,
            incumbent_index=config.incumbent_index,
            degree=config.degree,
        )

    rng = random.Random(config.run_seed)
    events = EventWriter(paths.events_path)
    retries = {"n": n_retries}

    def on_attempt(attempt: int, exc: Exception | None) -> None:
        if exc is not None:
            retries["n"] += 1
            events.emit({"type": "retry", "attempt": attempt, "error": str(exc)})

    def checkpoint(run_status: str) -> None:
        save_run_pickle(paths.pickle_path, simulation, tracker, convergence)
        write_meta(
            paths.meta_path,
            _base_meta(
                run_id=run_id,
                config=config,
                simulation=simulation,
                convergence=convergence,
                run_status=run_status,
                started_at=started_at,
                finished_at=now() if run_status in ("completed", "failed") else None,
                n_api_calls=counting_client.calls,
                n_retries=retries["n"],
            ),
        )

    try:
        committed_count = sum(1 for p in simulation.values() if p.get("committed_tag"))
        if committed_count == 0:
            events.emit(
                {
                    "type": "phase_transition",
                    "phase": "cm_start",
                    "committed_to": convergence["committed_to"],
                }
            )
            swap_committed(simulation, config.cm_k, rng)

        committed_to = convergence["committed_to"]
        phase2_step = make_interaction_step(
            simulation,
            counting_client,
            config.memory_size,
            config.rewards,
            config.options,
            rng,
            committed_to=committed_to,
            retry_policy=retry_policy,
            shared_shuffle=True,
            on_attempt=on_attempt,
        )

        interactions_since_checkpoint = 0

        def _phase2_step(t: dict) -> None:
            phase2_step(t)
            nonlocal interactions_since_checkpoint
            _emit_progress(events, tracker, "phase2", convergence_time)
            interactions_since_checkpoint += 1
            if interactions_since_checkpoint >= config.checkpoint_every:
                checkpoint("in_progress")
                interactions_since_checkpoint = 0

        # Resume: only run remaining horizon interactions.
        already = len(tracker["outcome"])
        remaining = config.phase2_horizon - already
        if remaining > 0:
            run_phase2({"tracker": tracker}, _phase2_step, phase2_horizon=remaining)

        checkpoint("completed")
        return paths

    except RunFailedError:
        checkpoint("failed")
        raise
    finally:
        events.close()


def execute_run(
    config: RunConfig,
    client: LLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: RetryPolicy | None = None,
    now: Callable[[], str] = default_now,
) -> RunPaths:
    """Dispatch to the program-specific executor."""
    if config.program == PROGRAM_EMERGENCE:
        return execute_emergence_run(
            config, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=retry_policy, now=now
        )
    if config.program == PROGRAM_CM:
        return execute_cm_run(
            config, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=retry_policy, now=now
        )
    raise ValueError(f"Unknown program {config.program!r}; expected {PROGRAM_EMERGENCE!r} or {PROGRAM_CM!r}")
