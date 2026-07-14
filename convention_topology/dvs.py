"""Dependent variables (WORKING.md §7) -- pure functions over a run's tracker.

No I/O, no module-level state (§0 principle 1). `label_shares` is the single
shared helper every share/entropy DV routes through: windows are counted in
**label emissions**, so the trailing 3N = 72 interactions contribute 2 labels
each, denominator **2 x 3N = 144** (locked). Ties (label frequency ties in a
window) break **lexicographically** -- deterministic, documented here rather
than relying on dict/Counter insertion order.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Mapping, Sequence

from convention_topology.tracker import modal_lexicographic as _modal_lexicographic

DEFAULT_WINDOW = 72  # 3N, N=24 (thesis default population size)


def label_shares(tracker: Mapping[str, Sequence], window: int = DEFAULT_WINDOW) -> dict[str, float]:
    """Label shares over the trailing `window` interactions' emissions (denominator 2*window)."""
    answers = tracker["answers"]
    if len(answers) < window:
        raise ValueError(f"tracker has {len(answers)} interactions, need >= window={window}")
    trailing = answers[-window:]
    labels = [label for pair in trailing for label in pair]
    denominator = 2 * window
    counts = Counter(labels)
    return {label: count / denominator for label, count in counts.items()}


def dominant_share(tracker: Mapping[str, Sequence], window: int = DEFAULT_WINDOW) -> float:
    shares = label_shares(tracker, window)
    return max(shares.values())


def shannon_entropy(tracker: Mapping[str, Sequence], window: int = DEFAULT_WINDOW) -> float:
    shares = label_shares(tracker, window)
    return -sum(p * math.log(p) for p in shares.values() if p > 0)


def rounds_to_gate(meta: Mapping, censor_value: int = 5000) -> int:
    """`t_gate` if the run reached the gate, else the censoring cap."""
    t_gate = meta.get("t_gate")
    return t_gate if t_gate is not None else censor_value


def incumbent_label(tracker: Mapping[str, Sequence], t_gate: int, window: int = DEFAULT_WINDOW) -> str | None:
    """Modal emission in the trailing `window` interactions at the gate (lexicographic tie-break)."""
    answers = tracker["answers"][:t_gate]
    trailing = answers[-window:] if len(answers) >= window else answers
    labels = [label for pair in trailing for label in pair]
    return _modal_lexicographic(labels)


def _flip_windows(
    tracker: Mapping[str, Sequence],
    t_start: int,
    window: int,
    threshold: float,
    end_limit: int,
):
    """Yield (end_index, modal_label) for every trailing window in [t_start+window, end_limit]
    whose success rate meets `threshold`."""
    outcomes = tracker["outcome"]
    answers = tracker["answers"]
    for end in range(t_start + window, end_limit + 1):
        window_outcomes = outcomes[end - window : end]
        if sum(window_outcomes) >= threshold * window:
            window_answers = answers[end - window : end]
            labels = [label for pair in window_answers for label in pair]
            yield end, _modal_lexicographic(labels)


def flip(
    tracker: Mapping[str, Sequence],
    committed_to: str,
    t_start: int,
    window: int = DEFAULT_WINDOW,
    threshold: float = 0.95,
) -> int:
    """1 iff a trailing-3N window in Phase 2 has success >= threshold AND modal emission = committed_to.

    Single non-flip/censored category -- no `flip_resisted` (R2 lock). A
    re-convergence on the pre-existing incumbent (success high, modal label
    != committed_to) scores 0, not a separate category.

    Raises `ValueError` if the tracker has fewer than `t_start + window`
    interactions (N5): with the thesis-locked `phase2_horizon=1000 >> window=72`
    this is unreachable in normal operation, but a misconfigured/short Phase 2
    must fail loudly rather than silently returning 0 -- indistinguishable
    from a genuine non-flip.
    """
    n = len(tracker["outcome"])
    if n < t_start + window:
        raise ValueError(
            f"tracker has {n} interactions, need >= t_start + window = {t_start + window} "
            "to evaluate a full trailing window from t_start"
        )
    for _end, modal in _flip_windows(tracker, t_start, window, threshold, n):
        if modal == committed_to:
            return 1
    return 0


def flip_50(
    simulation: Mapping[int, Mapping[str, Sequence]],
    committed_to: str,
    window: int = DEFAULT_WINDOW,
) -> int:
    """1 iff >50% of noncommitted agents' modal own-emission (final window) equals committed_to.

    Centola 50% sensitivity check; secondary only. Exactly 50% -> 0 (strict >).
    """
    noncommitted = [player for player in simulation.values() if not player.get("committed_tag")]
    if not noncommitted:
        return 0
    matches = 0
    for player in noncommitted:
        my_history = player["my_history"]
        trailing = my_history[-window:] if len(my_history) >= window else my_history
        if not trailing:
            continue
        if _modal_lexicographic(trailing) == committed_to:
            matches += 1
    return 1 if (matches / len(noncommitted)) > 0.5 else 0


def time_to_flip(
    tracker: Mapping[str, Sequence],
    committed_to: str,
    t_start: int,
    window: int = DEFAULT_WINDOW,
    threshold: float = 0.95,
    censor_value: int = 1000,
) -> int:
    """Interactions from CM injection (t_gate) to the end of the first qualifying flip window.

    Censored at `censor_value` (Phase 2 horizon) if no flip occurs.

    Raises `ValueError` if the tracker has fewer than `t_start + window`
    interactions (N5) -- see `flip`'s docstring for rationale.
    """
    n = len(tracker["outcome"])
    if n < t_start + window:
        raise ValueError(
            f"tracker has {n} interactions, need >= t_start + window = {t_start + window} "
            "to evaluate a full trailing window from t_start"
        )
    end_limit = min(n, t_start + censor_value)
    for end, modal in _flip_windows(tracker, t_start, window, threshold, end_limit):
        if modal == committed_to:
            return end - t_start
    return censor_value
