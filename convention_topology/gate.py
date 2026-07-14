from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class GateResult:
    """Phase 1 stability gate outcome for one population run."""

    eligibility: int
    t_gate: int | None
    run_status: str
    trailing_success_rate: float | None


def trailing_success_rate(
    outcomes: Sequence[int],
    window_size: int,
) -> float | None:
    if len(outcomes) < window_size:
        return None
    recent = outcomes[-window_size:]
    return sum(recent) / window_size


def has_tracker_converged(
    tracker: Mapping[str, Sequence[int]],
    *,
    convergence_time: int,
    threshold: float,
) -> bool:
    """
    Return True when the trailing window meets the stability gate.

    Thesis lock: threshold = 0.95 over convergence_time = 3N = 72 interactions.
    Ashery public code defaults to threshold = 1.0 (100%).
    """
    outcomes = tracker["outcome"]
    if len(outcomes) < convergence_time:
        return False
    recent = outcomes[-convergence_time:]
    return sum(recent) >= threshold * convergence_time


def evaluate_phase1_gate(
    tracker: Mapping[str, Sequence[int]],
    *,
    convergence_time: int,
    threshold: float,
    max_phase1_interactions: int,
) -> GateResult:
    """
    Evaluate Phase 1 gate state after the interaction loop stops.

    Eligible runs pass the >=95%/3N criterion before the hard cap.
    Censored runs hit max_phase1_interactions without gate passage.
    """
    outcomes = tracker["outcome"]
    interaction_count = len(outcomes)

    if has_tracker_converged(
        tracker,
        convergence_time=convergence_time,
        threshold=threshold,
    ):
        return GateResult(
            eligibility=1,
            t_gate=interaction_count,
            run_status="completed",
            trailing_success_rate=trailing_success_rate(outcomes, convergence_time),
        )

    if interaction_count >= max_phase1_interactions:
        return GateResult(
            eligibility=0,
            t_gate=None,
            run_status="censored",
            trailing_success_rate=trailing_success_rate(outcomes, convergence_time),
        )

    return GateResult(
        eligibility=0,
        t_gate=None,
        run_status="incomplete",
        trailing_success_rate=trailing_success_rate(outcomes, convergence_time),
    )
