"""H1: dominant-share coordination test vs tau=0.90, per model."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy import stats

TAU = 0.90


def h1_analysis(dominant_shares: Sequence[float]) -> dict[str, Any]:
    values = np.asarray(list(dominant_shares), dtype=float)
    n = len(values)
    if n == 0:
        return {"n": 0, "tau": TAU}
    if n < 2:
        mean = float(values.mean())
        return {
            "n": n,
            "tau": TAU,
            "mean_dominant_share": mean,
            "t_stat": None,
            "p_one_tailed": None,
            "p_two_tailed": None,
            "ci_95": [None, None],
            "wilcoxon_stat": None,
            "wilcoxon_p_one_tailed": None,
            "regime_proportion_gt_tau": float(np.mean(values > TAU)),
            "decision_alpha": 0.05,
            "reject_h0": False,
        }

    t_result = stats.ttest_1samp(values, popmean=TAU)
    t_stat = float(t_result.statistic)
    p_two = float(t_result.pvalue)
    p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
    ci = t_result.confidence_interval(0.95)

    wilcoxon_stat: float | None
    wilcoxon_p: float | None
    try:
        w_stat, p_w = stats.wilcoxon(values - TAU, alternative="greater")
        wilcoxon_stat, wilcoxon_p = float(w_stat), float(p_w)
    except ValueError:
        wilcoxon_stat, wilcoxon_p = None, None

    return {
        "n": n,
        "tau": TAU,
        "mean_dominant_share": float(values.mean()),
        "t_stat": t_stat,
        "p_one_tailed": p_one,
        "p_two_tailed": p_two,
        "ci_95": [float(ci.low), float(ci.high)],
        "wilcoxon_stat": wilcoxon_stat,
        "wilcoxon_p_one_tailed": wilcoxon_p,
        "regime_proportion_gt_tau": float(np.mean(values > TAU)),
        "decision_alpha": 0.05,
        "reject_h0": bool(p_one < 0.05),
    }


def h1_per_model(mixing: pd.DataFrame) -> pd.DataFrame:
    """T-H1 rows: mixing, one row per model, not pooled."""
    columns = [
        "model_shorthand",
        "n",
        "mean_dominant_share",
        "ci_95_low",
        "ci_95_high",
        "p_one_tailed",
        "reject_h0",
        "gate_rate",
        "median_t_gate",
        "tau",
    ]
    if mixing.empty or "dominant_share" not in mixing.columns:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for model, group in mixing.groupby("model_shorthand", dropna=False):
        shares = group["dominant_share"].dropna()
        stats_row = h1_analysis(shares.tolist())
        gated = group["gate_passed"] == True  # noqa: E712
        t_gate = group["t_gate"].dropna()
        ci = stats_row.get("ci_95") or [None, None]
        rows.append(
            {
                "model_shorthand": model,
                "n": int(stats_row.get("n") or 0),
                "mean_dominant_share": stats_row.get("mean_dominant_share"),
                "ci_95_low": ci[0] if ci else None,
                "ci_95_high": ci[1] if ci else None,
                "p_one_tailed": stats_row.get("p_one_tailed"),
                "reject_h0": stats_row.get("reject_h0"),
                "gate_rate": float(gated.mean()) if len(group) else None,
                "median_t_gate": float(t_gate.median()) if len(t_gate) else None,
                "tau": TAU,
            }
        )
    return pd.DataFrame(rows, columns=columns)
