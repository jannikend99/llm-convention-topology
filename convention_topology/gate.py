"""Study 1 integer gate: first t>=window with at least ceil(0.95*window) trailing successes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


GATE_WINDOW = 144
GATE_THRESHOLD = 0.95
MIN_SUCCESSES = 137  # ceil(0.95 * 144); locked counted window
CAP_PHASE1 = 1500


def min_gate_successes(window: int) -> int:
    return int(math.ceil(GATE_THRESHOLD * int(window)))


@dataclass(frozen=True)
class GateResult:
    gate_passed: bool
    t_gate: int | None
    run_status: str
    stop_reason: str | None
    trailing_successes: int | None


def trailing_successes(outcomes: Sequence[int], window_size: int) -> int | None:
    if len(outcomes) < window_size:
        return None
    return int(sum(outcomes[-window_size:]))


def has_tracker_converged(tracker: Mapping[str, Sequence[int]], *, window: int = GATE_WINDOW) -> bool:
    outcomes = tracker["outcome"]
    if len(outcomes) < window:
        return False
    return int(sum(outcomes[-window:])) >= min_gate_successes(window)


def first_gate_time(outcomes: Sequence[int], *, window: int = GATE_WINDOW) -> int | None:
    if len(outcomes) < window:
        return None
    need = min_gate_successes(window)
    for t in range(window, len(outcomes) + 1):
        if int(sum(outcomes[t - window : t])) >= need:
            return t
    return None


def evaluate_phase1_gate(
    tracker: Mapping[str, Sequence[int]],
    *,
    window: int = GATE_WINDOW,
    max_phase1_interactions: int = CAP_PHASE1,
) -> GateResult:
    outcomes = tracker["outcome"]
    t = len(outcomes)
    t_gate = first_gate_time(outcomes, window=window)
    successes = trailing_successes(outcomes, window)
    if t_gate is not None:
        return GateResult(
            gate_passed=True,
            t_gate=t_gate,
            run_status="completed",
            stop_reason="gate",
            trailing_successes=successes,
        )
    if t >= max_phase1_interactions:
        return GateResult(
            gate_passed=False,
            t_gate=None,
            run_status="censored",
            stop_reason="cap",
            trailing_successes=successes,
        )
    return GateResult(
        gate_passed=False,
        t_gate=None,
        run_status="in_progress",
        stop_reason=None,
        trailing_successes=successes,
    )
