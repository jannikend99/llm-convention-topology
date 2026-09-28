"""H2: directed lattice and random-regular contrasts against mixing.

The 2026-09-28 amendment makes these two one-sided Welch tests the H2
primary family (Bonferroni alpha .025). Watts-Strogatz and Barabasi-Albert
comparisons remain two-sided exploratory analyses and never determine H2
support.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

ALPHA = 0.025
PRIMARY_TOPOLOGIES = ("lattice", "random_regular")
EXPLORATORY_TOPOLOGIES = ("watts_strogatz", "barabasi_albert")
CONTRAST_TOPOLOGIES = PRIMARY_TOPOLOGIES + EXPLORATORY_TOPOLOGIES


def _metadata() -> dict[str, Any]:
    return {"analysis_status": "amended-primary", "confirmatory_status": "not-established", "amendment_date": "2026-09-28", "prior_result_inspection": True, "preregistration_status": "unknown"}


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
    return 0.0 if pooled == 0 else float((sparse.mean() - mixing.mean()) / pooled)


def _unevaluable(sparse: np.ndarray, mixing: np.ndarray, *, exploratory: bool) -> dict[str, Any]:
    return {"n": len(sparse), "n_mixing": len(mixing), "mean": float(sparse.mean()) if len(sparse) else None,
            "welch_t": None, "welch_p_one_tailed": None, "welch_p_two_tailed": None,
            "mannwhitney_u": None, "mannwhitney_p_one_tailed": None, "mannwhitney_p_two_tailed": None, "cohens_d": None,
            "mean_difference_vs_mixing": None, "welch_ci_95_low": None, "welch_ci_95_high": None,
            "alpha": None if exploratory else ALPHA, "evaluable": False, "decision": "unevaluable", "reject_h0": None}


def _contrast(sparse_shares: Sequence[float], mixing_shares: Sequence[float], *, exploratory: bool) -> dict[str, Any]:
    sparse, mixing = np.asarray(list(sparse_shares), dtype=float), np.asarray(list(mixing_shares), dtype=float)
    if (len(sparse) < 2 or len(mixing) < 2 or not np.isfinite(sparse).all() or not np.isfinite(mixing).all()
            or not ((0 <= sparse).all() and (sparse <= 1).all() and (0 <= mixing).all() and (mixing <= 1).all())):
        return _unevaluable(sparse, mixing, exploratory=exploratory)
    se2 = float(sparse.var(ddof=1) / len(sparse) + mixing.var(ddof=1) / len(mixing))
    if se2 <= 0 or not np.isfinite(se2):
        return _unevaluable(sparse, mixing, exploratory=exploratory)
    t_stat, p_one = _welch_one_tailed_less(sparse, mixing)
    _, p_two = stats.ttest_ind(sparse, mixing, equal_var=False)
    u_stat, p_mw = stats.mannwhitneyu(sparse, mixing, alternative="two-sided" if exploratory else "less")
    difference = float(sparse.mean() - mixing.mean())
    se = float(np.sqrt(se2))
    df = se2**2 / ((sparse.var(ddof=1) / len(sparse))**2 / (len(sparse) - 1) + (mixing.var(ddof=1) / len(mixing))**2 / (len(mixing) - 1))
    margin = float(stats.t.ppf(0.975, df) * se)
    return {"n": len(sparse), "n_mixing": len(mixing), "mean": float(sparse.mean()), "welch_t": t_stat,
            "welch_p_one_tailed": None if exploratory else p_one, "welch_p_two_tailed": float(p_two), "mannwhitney_u": float(u_stat),
            "mannwhitney_p_one_tailed": None if exploratory else float(p_mw), "mannwhitney_p_two_tailed": float(p_mw) if exploratory else None, "cohens_d": cohens_d_unequal_n(sparse, mixing),
            "mean_difference_vs_mixing": difference, "welch_ci_95_low": difference - margin, "welch_ci_95_high": difference + margin,
            "alpha": None if exploratory else ALPHA, "evaluable": True,
            "decision": "exploratory" if exploratory else ("rejected_h0" if p_one < ALPHA else "not_rejected"),
            "reject_h0": None if exploratory else bool(p_one < ALPHA)}


def _entropy_descriptives(entropy: Sequence[float] | None) -> dict[str, Any] | None:
    if entropy is None:
        return None
    values = np.asarray(list(entropy), dtype=float)
    return {"n": 0} if len(values) == 0 else {"n": len(values), "mean": float(values.mean()), "sd": float(values.std(ddof=1)) if len(values) > 1 else 0.0}


def _support_label(primary: list[dict[str, Any]]) -> str:
    if not all(row["evaluable"] for row in primary):
        return "unevaluable"
    return {2: "full", 1: "partial", 0: "none"}[sum(bool(row["reject_h0"]) for row in primary)]


def h2_analysis(shares_by_topology: Mapping[str, Sequence[float]], entropy_by_topology: Mapping[str, Sequence[float]] | None = None) -> dict[str, Any]:
    mixing_shares = list(shares_by_topology.get("mixing") or [])
    mixing = np.asarray(mixing_shares, dtype=float)
    contrasts: dict[str, Any] = {}
    primary = []
    for topology in PRIMARY_TOPOLOGIES:
        row = _contrast(list(shares_by_topology.get(topology) or []), mixing_shares, exploratory=False)
        contrasts[f"{topology}_vs_mixing"] = row
        primary.append(row)
    for topology in EXPLORATORY_TOPOLOGIES:
        contrasts[f"{topology}_vs_mixing"] = _contrast(list(shares_by_topology.get(topology) or []), mixing_shares, exploratory=True)
    entropy_src = entropy_by_topology or {}
    return {**_metadata(), "alpha": ALPHA, "n_contrasts": len(PRIMARY_TOPOLOGIES),
            "n_significant_welch": sum(bool(row["reject_h0"]) for row in primary if row["evaluable"]),
            "support": _support_label(primary), "mixing": {"n": len(mixing), "mean": float(mixing.mean()) if len(mixing) else None},
            **contrasts,
            "entropy_descriptive": {name: _entropy_descriptives(entropy_src.get(name)) for name in ("mixing",) + CONTRAST_TOPOLOGIES}}
