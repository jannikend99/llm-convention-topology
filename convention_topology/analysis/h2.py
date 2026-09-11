"""H2: four one-sided Welch contrasts vs mixing, Bonferroni alpha=0.0125."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

ALPHA = 0.0125
CONTRAST_TOPOLOGIES = ("lattice", "random_regular", "watts_strogatz", "barabasi_albert")


def _welch_one_tailed_less(sparse: np.ndarray, mixing: np.ndarray) -> tuple[float, float]:
    t_stat, p_two = stats.ttest_ind(sparse, mixing, equal_var=False)
    p_one = p_two / 2 if t_stat < 0 else 1 - p_two / 2
    return float(t_stat), float(p_one)


def cohens_d_unequal_n(sparse: np.ndarray, mixing: np.ndarray) -> float | None:
    if len(sparse) < 2 or len(mixing) < 2:
        return None
    n1, n2 = len(sparse), len(mixing)
    v1, v2 = float(sparse.var(ddof=1)), float(mixing.var(ddof=1))
    denom = n1 + n2 - 2
    if denom <= 0:
        return None
    pooled = np.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / denom)
    if pooled == 0:
        return 0.0
    return float((sparse.mean() - mixing.mean()) / pooled)


def _contrast(sparse_shares: Sequence[float], mixing_shares: Sequence[float]) -> dict[str, Any]:
    sparse = np.asarray(list(sparse_shares), dtype=float)
    mixing = np.asarray(list(mixing_shares), dtype=float)
    if len(sparse) == 0 or len(mixing) == 0:
        return {
            "n": len(sparse),
            "n_mixing": len(mixing),
            "mean": None,
            "welch_t": None,
            "welch_p_one_tailed": None,
            "mannwhitney_u": None,
            "mannwhitney_p_one_tailed": None,
            "cohens_d": None,
            "alpha": ALPHA,
            "reject_h0": False,
        }

    if len(sparse) < 2 or len(mixing) < 2:
        return {
            "n": len(sparse),
            "n_mixing": len(mixing),
            "mean": float(sparse.mean()) if len(sparse) else None,
            "welch_t": None,
            "welch_p_one_tailed": None,
            "mannwhitney_u": None,
            "mannwhitney_p_one_tailed": None,
            "cohens_d": None,
            "alpha": ALPHA,
            "reject_h0": False,
        }
    t_stat, p_one = _welch_one_tailed_less(sparse, mixing)
    u_stat, p_mw = stats.mannwhitneyu(sparse, mixing, alternative="less")
    return {
        "n": len(sparse),
        "n_mixing": len(mixing),
        "mean": float(sparse.mean()),
        "welch_t": t_stat,
        "welch_p_one_tailed": p_one,
        "mannwhitney_u": float(u_stat),
        "mannwhitney_p_one_tailed": float(p_mw),
        "cohens_d": cohens_d_unequal_n(sparse, mixing),
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


def _support_label(n_significant: int) -> str:
    if n_significant == 4:
        return "full"
    if 1 <= n_significant <= 3:
        return "partial"
    return "not-supported"


def h2_analysis(
    shares_by_topology: Mapping[str, Sequence[float]],
    entropy_by_topology: Mapping[str, Sequence[float]] | None = None,
) -> dict[str, Any]:
    mixing_shares = list(shares_by_topology.get("mixing") or [])
    mixing = np.asarray(mixing_shares, dtype=float)
    contrasts: dict[str, Any] = {}
    n_sig = 0
    for topology in CONTRAST_TOPOLOGIES:
        key = f"{topology}_vs_mixing"
        contrasts[key] = _contrast(list(shares_by_topology.get(topology) or []), mixing_shares)
        if contrasts[key].get("reject_h0"):
            n_sig += 1

    entropy_src = entropy_by_topology or {}
    return {
        "alpha": ALPHA,
        "n_contrasts": 4,
        "n_significant_welch": n_sig,
        "support": _support_label(n_sig),
        "mixing": {"n": len(mixing), "mean": float(mixing.mean()) if len(mixing) else None},
        **contrasts,
        "entropy_descriptive": {
            name: _entropy_descriptives(entropy_src.get(name))
            for name in ("mixing",) + CONTRAST_TOPOLOGIES
        },
    }
