"""H3a: flip curve over committed-minority size cm_k (WORKING.md §8, locked M04).

Primary inferential contrast: logistic GAM `flip ~ s(cm_k)` vs. linear
logistic `flip ~ cm_k`, compared via a likelihood-ratio test
(`03_Methods.tex:228-229`; `WORKING.md:385`). The GAM is also the source of
the flip-curve figure data. Linear-vs-intercept is retained only as a
secondary/descriptive contrast -- it is never the primary H3a claim.
`--sensitivity-50` exports 95%-vs-50%-flip-indicator agreement (Appendix
`tab:appendix-flip-agreement`).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import statsmodels.api as sm
from numpy.linalg import LinAlgError
from scipy.stats import chi2
from statsmodels.tools.sm_exceptions import PerfectSeparationError

MIN_N_FOR_INFERENCE = 8
K_GRID = list(range(1, 7))

_FIT_EXCEPTIONS = (LinAlgError, PerfectSeparationError, ValueError)


def h3a_analysis(cm_k: Sequence[int], flip: Sequence[int]) -> dict[str, Any]:
    x = np.asarray(list(cm_k), dtype=float)
    y = np.asarray(list(flip), dtype=int)
    n = len(y)

    if n < MIN_N_FOR_INFERENCE or len(set(y.tolist())) < 2:
        return {"n": n, "label": "exploratory", "reason": "insufficient n or no variance in flip outcome"}

    # `has_constant="add"` forces the intercept column even if `x` itself
    # happens to be constant (degenerate cm_k input) -- default `"skip"`
    # would silently drop to a 1-column design and desync `full_fit.params`
    # indexing below.
    design = sm.add_constant(x.reshape(-1, 1), has_constant="add")
    linear_coef: float | None
    linear_p: float | None
    linear_ll: float | None = None
    lr_stat_linear_vs_intercept: float | None
    lr_p_linear_vs_intercept: float | None
    try:
        full_fit = sm.Logit(y, design).fit(disp=0)
        null_fit = sm.Logit(y, np.ones((n, 1))).fit(disp=0)
        linear_ll = float(full_fit.llf)
        lr_stat_linear_vs_intercept = float(2 * (full_fit.llf - null_fit.llf))
        lr_p_linear_vs_intercept = float(chi2.sf(lr_stat_linear_vs_intercept, df=1))
        linear_coef = float(full_fit.params[1])
        linear_p = float(full_fit.pvalues[1])
    except _FIT_EXCEPTIONS as exc:
        linear_coef = linear_p = lr_stat_linear_vs_intercept = lr_p_linear_vs_intercept = None
        return {
            "n": n,
            "label": "exploratory",
            "reason": f"linear logit fit failed: {exc}",
            "linear_logit_coef": None,
            "linear_logit_p": None,
            "lr_stat_linear_vs_intercept": None,
            "lr_p_linear_vs_intercept": None,
            "lr_stat_gam_vs_linear": None,
            "lr_p_gam_vs_linear": None,
            "gam": {},
            "flip_curve": None,
        }

    gam_summary: dict[str, Any] = {}
    lr_stat_gam_vs_linear: float | None = None
    lr_p_gam_vs_linear: float | None = None
    lr_df_gam_vs_linear: float | None = None
    flip_curve: list[dict[str, float]] | None = None
    label = "exploratory"
    reason: str | None = None
    try:
        from pygam import LogisticGAM, s

        n_splines = max(3, min(6, n - 2))
        X = x.reshape(-1, 1)
        gam = LogisticGAM(s(0, n_splines=n_splines)).fit(X, y)
        gam_ll = float(gam.loglikelihood(X, y))
        edof = float(gam.statistics_["edof"])
        lr_df_gam_vs_linear = edof - 2.0  # GAM smooth term's effective df vs. linear's 1 slope + 1 intercept
        if lr_df_gam_vs_linear > 0 and linear_ll is not None:
            lr_stat_gam_vs_linear = float(2 * (gam_ll - linear_ll))
            lr_stat_gam_vs_linear = max(lr_stat_gam_vs_linear, 0.0)
            lr_p_gam_vs_linear = float(chi2.sf(lr_stat_gam_vs_linear, df=lr_df_gam_vs_linear))
            label = "confirmatory"
        else:
            reason = "GAM effective df did not exceed the linear model's df; LR test undefined"

        grid = np.asarray(K_GRID, dtype=float).reshape(-1, 1)
        predicted = gam.predict_proba(grid)
        flip_curve = [{"cm_k": k, "predicted_flip_prob": float(p)} for k, p in zip(K_GRID, predicted)]
        gam_summary = {"n_splines": n_splines, "edof": edof}
    except _FIT_EXCEPTIONS as exc:  # tiny-n GAM fit failures are expected, not fatal
        gam_summary = {"error": str(exc)}
        label = "exploratory"
        reason = f"GAM fit failed: {exc}"

    result = {
        "n": n,
        "label": label,
        "linear_logit_coef": linear_coef,
        "linear_logit_p": linear_p,
        "lr_stat_linear_vs_intercept": lr_stat_linear_vs_intercept,
        "lr_p_linear_vs_intercept": lr_p_linear_vs_intercept,
        "lr_stat_gam_vs_linear": lr_stat_gam_vs_linear,
        "lr_p_gam_vs_linear": lr_p_gam_vs_linear,
        "lr_df_gam_vs_linear": lr_df_gam_vs_linear,
        "gam": gam_summary,
        "flip_curve": flip_curve,
    }
    if reason is not None:
        result["reason"] = reason
    return result


def sensitivity_50_agreement(flip_95: Sequence[int], flip_50: Sequence[int]) -> dict[str, Any]:
    """95% vs 50% flip-indicator agreement (mixing, eligible runs)."""
    a = np.asarray(list(flip_95), dtype=int)
    b = np.asarray(list(flip_50), dtype=int)
    n = len(a)
    if n == 0:
        return {"n": 0, "agreement_rate": None}
    return {"n": n, "agreement_rate": float((a == b).mean())}
