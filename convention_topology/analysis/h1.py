"""H1: dominant-share coordination test vs tau=0.90 (WORKING.md §8, locked M04).

One-sample t on dominant share (mixing, all attempted Phase 1 runs);
Wilcoxon signed-rank as robustness; 95% CI; descriptive regime proportion
(share of runs with dominant share > tau, no test).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy import stats

TAU = 0.90


def h1_analysis(dominant_shares: Sequence[float]) -> dict[str, Any]:
    values = np.asarray(list(dominant_shares), dtype=float)
    n = len(values)
    if n == 0:
        return {"n": 0}

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
        # All differences are zero, or n too small -- scipy raises.
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
