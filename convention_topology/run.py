"""Run orchestration: init -> Phase 1 -> gate -> swap -> Phase 2 -> finalize.

Composes pure core (`simulation.py`, `gate.py`, `networks.py`, `tracker.py`)
with boundaries (`llm.py`, `persistence.py`). Ashery `simulation_module.py`
`population`/`committed` port (WORKING.md §2): sequential Phase 1->2 per
(topology, k, seed) -- no prepared-population shortcut (M03 run-unit lock).
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
from convention_topology.simulation import make_interaction_step, run_phase2, swap_committed
from convention_topology.tracker import empty_tracker, modal_label_in_window


def _emit_progress(events: EventWriter, tracker: dict, phase: str, window: int) -> None:
    """Every 10 interactions (Ashery cadence, §6): t, phase, rolling 3N success, dominant share."""
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
    model_shorthand: str
    model_id: str
    endpoint_base_url: str
    topology: str
    cm_k: int
    graph_seed: int
    run_seed: int
    config_hash: str
    prompt_template_version: str
    code_commit: str
    rewards: Sequence[int] = (-50, 100)
    options: Sequence[str] = ("A", "B")
    memory_size: int = 5
    n: int = 24
    convergence_threshold: float = 0.95
    max_phase1_interactions: int = 5000
    phase2_horizon: int = 1000
    checkpoint_every: int = 50


class _CountingClient:
    """Wraps a client to count API calls without mutating the caller's instance."""

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


def execute_run(
    config: RunConfig,
    client: LLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: RetryPolicy | None = None,
    now: Callable[[], str] = default_now,
) -> RunPaths:
    """Execute (or resume) one Phase 1 -> Phase 2 run and return its artifact paths."""
    run_id = build_run_id(config.model_shorthand, config.topology, config.cm_k, config.run_seed)
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
        simulation = get_interaction_network(config.topology, n=config.n, graph_seed=config.graph_seed)
        tracker = empty_tracker()
        convergence = {"converged_index": None, "committed_to": None}

    rng = random.Random(config.run_seed)
    events = EventWriter(paths.events_path)
    retries = {"n": n_retries}

    def on_attempt(attempt: int, exc: Exception | None) -> None:
        if exc is not None:
            retries["n"] += 1
            events.emit({"type": "retry", "attempt": attempt, "error": str(exc)})

    def checkpoint(run_status: str) -> None:
        save_run_pickle(paths.pickle_path, simulation, tracker, convergence)
        eligibility = 1 if convergence.get("converged_index") is not None else 0
        write_meta(
            paths.meta_path,
            {
                "run_id": run_id,
                "topology": config.topology,
                "cm_k": config.cm_k,
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
                "phase2_horizon": config.phase2_horizon,
                "config_hash": config.config_hash,
                "run_status": run_status,
                "started_at": started_at,
                "finished_at": now() if run_status in ("completed", "censored", "failed") else None,
                "n_api_calls": counting_client.calls,
                "n_retries": retries["n"],
                "prompt_template_version": config.prompt_template_version,
                "code_commit": config.code_commit,
            },
        )

    try:
        # --- Phase 1 ---
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

        # --- Gate passed: incumbent + committed minority + Phase 2 ---
        # Resume guard: if this run already picked an incumbent/committed_to
        # and tagged committed agents in an earlier (interrupted) invocation,
        # re-deriving them here would recompute the incumbent off a tracker
        # that may already include Phase 2 interactions, and re-running
        # `swap_committed` would tag additional agents on top of the
        # already-committed ones -- corrupting the k-sized committed
        # minority on every resume. Only do this once per run.
        if convergence.get("committed_to") is None:
            incumbent_label = modal_label_in_window(tracker, convergence_time)
            committed_to = _pick_committed_label(config.options, incumbent_label)
            convergence["converged_index"] = gate.t_gate
            convergence["incumbent_label"] = incumbent_label
            convergence["committed_to"] = committed_to
            events.emit({"type": "phase_transition", "phase": "phase2_start", "t_gate": gate.t_gate})
            swap_committed(simulation, config.cm_k, rng)
        else:
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

        def _phase2_step(t: dict) -> None:
            phase2_step(t)
            nonlocal interactions_since_checkpoint
            _emit_progress(events, tracker, "phase2", convergence_time)
            interactions_since_checkpoint += 1
            if interactions_since_checkpoint >= config.checkpoint_every:
                checkpoint("in_progress")
                interactions_since_checkpoint = 0

        run_phase2(
            {"tracker": tracker},
            _phase2_step,
            phase2_horizon=config.phase2_horizon,
        )

        checkpoint("completed")
        return paths

    except RunFailedError:
        checkpoint("failed")
        raise
    finally:
        events.close()


def _pick_committed_label(options: Sequence[str], incumbent_label: str | None) -> str | None:
    """Committed minority advocates the non-incumbent label (binary-option lock)."""
    if incumbent_label is None:
        return None
    alternatives = [option for option in options if option != incumbent_label]
    if len(alternatives) != 1:
        raise NotImplementedError(
            "committed_to selection is defined for exactly 2 options (thesis lock); "
            f"got options={list(options)!r}"
        )
    return alternatives[0]
