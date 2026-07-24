"""Async run executors (③): emergence + CM as coroutines.

Each run is still a *sequential* Markov chain — interactions are awaited one at a
time (`await step(tracker)`), so the trajectory is unchanged. Concurrency comes
from (a) many runs sharing one event loop and (b) the two per-interaction player
calls overlapping (④). All persistence, gating, resume, checkpoint and metadata
logic is reused verbatim from the sync `run.py` so the two engines cannot drift.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from convention_topology.async_llm import AsyncLLMClient, AsyncRetryPolicy
from convention_topology.async_simulation import make_async_interaction_step
from convention_topology.gate import evaluate_phase1_gate
from convention_topology.llm import LLMResponse, RunFailedError
from convention_topology.persistence import (
    EventWriter,
    RunPaths,
    ensure_run_dirs,
    load_run_pickle,
    read_meta,
    run_paths,
    save_run_pickle,
    write_meta,
)
from convention_topology.prepared import make_prepared_population
from convention_topology.networks import get_interaction_network
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    RunConfig,
    _base_meta,
    _emit_progress,
    default_now,
)
from convention_topology.simulation import swap_committed
from convention_topology.tracker import empty_tracker, modal_label_in_window

import random


class _AsyncCountingClient:
    """Async twin of `run._CountingClient`: counts calls, fires `on_response`."""

    def __init__(self, client: AsyncLLMClient, on_response: Callable[[LLMResponse], None] | None = None):
        self._client = client
        self.calls = 0
        self._on_response = on_response

    async def complete(self, system: str, user: str) -> LLMResponse:
        self.calls += 1
        response = await self._client.complete(system, user)
        if self._on_response is not None:
            self._on_response(response)
        return response


async def execute_emergence_run_async(
    config: RunConfig,
    client: AsyncLLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: AsyncRetryPolicy | None = None,
    now: Callable[[], str] = default_now,
    console_progress: bool = True,
) -> RunPaths:
    """Async organic empty-start Phase 1 until gate or cap. No CM."""
    if config.program != PROGRAM_EMERGENCE:
        raise ValueError(f"execute_emergence_run_async requires program={PROGRAM_EMERGENCE!r}")

    from convention_topology.persistence import build_run_id

    run_id = build_run_id(
        config.model_shorthand, config.topology, config.run_seed, program=PROGRAM_EMERGENCE
    )
    paths = run_paths(data_dir, logs_dir, config.model_shorthand, config.topology, run_id)
    ensure_run_dirs(paths)
    convergence_time = 3 * config.n

    def on_response(response: LLMResponse) -> None:
        if response.usage:
            events.emit({"type": "token_usage", "model_id": response.model_id, **response.usage})

    counting_client = _AsyncCountingClient(client, on_response=on_response)

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
        phase1_step = make_async_interaction_step(
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
            await phase1_step(tracker)
            _emit_progress(
                events, tracker, "phase1", convergence_time, run_id=run_id, console=console_progress
            )
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


async def execute_cm_run_async(
    config: RunConfig,
    client: AsyncLLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: AsyncRetryPolicy | None = None,
    now: Callable[[], str] = default_now,
    console_progress: bool = True,
) -> RunPaths:
    """Async prepared population → swap CM → fixed Phase 2 horizon."""
    if config.program != PROGRAM_CM:
        raise ValueError(f"execute_cm_run_async requires program={PROGRAM_CM!r}")
    if config.cm_k < 1:
        raise ValueError(f"CM run requires cm_k >= 1; got {config.cm_k}")

    from convention_topology.persistence import build_run_id

    run_id = build_run_id(
        config.model_shorthand, config.topology, config.run_seed, program=PROGRAM_CM, cm_k=config.cm_k
    )
    paths = run_paths(data_dir, logs_dir, config.model_shorthand, config.topology, run_id)
    ensure_run_dirs(paths)
    convergence_time = 3 * config.n

    def on_response(response: LLMResponse) -> None:
        if response.usage:
            events.emit({"type": "token_usage", "model_id": response.model_id, **response.usage})

    counting_client = _AsyncCountingClient(client, on_response=on_response)

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
        phase2_step = make_async_interaction_step(
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
        already = len(tracker["outcome"])
        remaining = config.phase2_horizon - already

        # Sequential Phase 2 horizon (async twin of run_phase2's while-loop).
        while len(tracker["outcome"]) - already < remaining:
            await phase2_step(tracker)
            _emit_progress(
                events, tracker, "phase2", convergence_time, run_id=run_id, console=console_progress
            )
            interactions_since_checkpoint += 1
            if interactions_since_checkpoint >= config.checkpoint_every:
                checkpoint("in_progress")
                interactions_since_checkpoint = 0

        checkpoint("completed")
        return paths

    except RunFailedError:
        checkpoint("failed")
        raise
    finally:
        events.close()


async def execute_run_async(
    config: RunConfig,
    client: AsyncLLMClient,
    *,
    data_dir: Path,
    logs_dir: Path,
    retry_policy: AsyncRetryPolicy | None = None,
    now: Callable[[], str] = default_now,
    console_progress: bool = True,
) -> RunPaths:
    """Dispatch to the program-specific async executor."""
    if config.program == PROGRAM_EMERGENCE:
        return await execute_emergence_run_async(
            config, client, data_dir=data_dir, logs_dir=logs_dir,
            retry_policy=retry_policy, now=now, console_progress=console_progress,
        )
    if config.program == PROGRAM_CM:
        return await execute_cm_run_async(
            config, client, data_dir=data_dir, logs_dir=logs_dir,
            retry_policy=retry_policy, now=now, console_progress=console_progress,
        )
    raise ValueError(
        f"Unknown program {config.program!r}; expected {PROGRAM_EMERGENCE!r} or {PROGRAM_CM!r}"
    )
