"""H2: topology contrasts on dominant share (WORKING.md §8, locked M04).

2 pre-planned one-tailed Welch t contrasts (lattice < mixing; random_regular
< mixing), alpha=.05 each, no correction; Mann-Whitney U robustness; Shannon
entropy reported descriptively alongside.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

ALPHA = 0.05


def _welch_one_tailed_less(sparse: np.ndarray, mixing: np.ndarray) -> tuple[float, float]:
    """One-tailed Welch t: is mean(sparse) < mean(mixing)?"""
    t_stat, p_two = stats.ttest_ind(sparse, mixing, equal_var=False)
    p_one = p_two / 2 if t_stat < 0 else 1 - p_two / 2
    return float(t_stat), float(p_one)


def _contrast(sparse_shares: Sequence[float], mixing_shares: Sequence[float]) -> dict[str, Any]:
    sparse = np.asarray(list(sparse_shares), dtype=float)
    mixing = np.asarray(list(mixing_shares), dtype=float)
    if len(sparse) == 0 or len(mixing) == 0:
        return {"n": len(sparse)}

    t_stat, p_one = _welch_one_tailed_less(sparse, mixing)
    u_stat, p_mw = stats.mannwhitneyu(sparse, mixing, alternative="less")
    return {
        "n": len(sparse),
        "mean": float(sparse.mean()),
        "welch_t": t_stat,
        "welch_p_one_tailed": p_one,
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p_one_tailed": float(p_mw),
        "alpha": ALPHA,
        "reject_h0": bool(p_one < ALPHA),
    }


def _entropy_descriptives(entropy: Sequence[float] | None) -> dict[str, Any] | None:
    if entropy is None:
        return None
    values = np.asarray(list(entropy), dtype=float)
    if len(values) == 0:
        return {"n": 0}
    return {"n": len(values), "mean": float(values.mean()), "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0}


def h2_analysis(
    mixing_shares: Sequence[float],
    lattice_shares: Sequence[float],
    random_shares: Sequence[float],
    mixing_entropy: Sequence[float] | None = None,
    lattice_entropy: Sequence[float] | None = None,
    random_entropy: Sequence[float] | None = None,
) -> dict[str, Any]:
    mixing = np.asarray(list(mixing_shares), dtype=float)
    return {
        "mixing": {"n": len(mixing), "mean": float(mixing.mean()) if len(mixing) else None},
        "lattice_vs_mixing": _contrast(lattice_shares, mixing_shares),
        "random_regular_vs_mixing": _contrast(random_shares, mixing_shares),
        "entropy_descriptive": {
            "mixing": _entropy_descriptives(mixing_entropy),
            "lattice": _entropy_descriptives(lattice_entropy),
            "random_regular": _entropy_descriptives(random_entropy),
        },
    }
