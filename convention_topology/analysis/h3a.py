"""H3a: mixing-only flip differences at the tested committed-minority sizes."""

from __future__ import annotations

import warnings
from typing import Any, Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm
from numpy.linalg import LinAlgError
from scipy.stats import chi2
from statsmodels.tools.sm_exceptions import ConvergenceWarning, PerfectSeparationError, PerfectSeparationWarning

MIN_N_FOR_INFERENCE = 8
K_GRID = [5, 10, 14]
_FIT_EXCEPTIONS = (LinAlgError, PerfectSeparationError, PerfectSeparationWarning, ConvergenceWarning, ValueError)


def _metadata() -> dict[str, Any]:
    return {"analysis_status": "amended-primary", "confirmatory_status": "not-established", "amendment_date": "2026-09-28", "prior_result_inspection": True, "preregistration_status": "unknown"}


def _empirical(x: np.ndarray, y: np.ndarray) -> list[dict[str, float | int | None]]:
    rows = []
    for k in K_GRID:
        values = y[x == k]
        rows.append({"cm_k": k, "n": int(len(values)), "flip_rate": float(values.mean()) if len(values) else None})
    return rows


def _fit_logit(y: np.ndarray, design: np.ndarray):
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        warnings.simplefilter("error", PerfectSeparationWarning)
        fit = sm.Logit(y, design).fit(disp=0, method="newton", maxiter=200)
    if not bool(fit.mle_retvals.get("converged", False)):
        raise ValueError("logit did not converge")
    return fit


def h3a_analysis(cm_k: Sequence[int], flip: Sequence[int]) -> dict[str, Any]:
    raw_x, raw_y = list(cm_k), list(flip)
    if len(raw_x) != len(raw_y):
        return {**_metadata(), "n": 0, "label": "unevaluable", "reason": "cm_k and flip lengths differ"}
    try:
        x, y_numeric = np.asarray(raw_x, dtype=float), np.asarray(raw_y, dtype=float)
    except (TypeError, ValueError):
        return {**_metadata(), "n": 0, "label": "unevaluable", "reason": "cm_k and flip must be numeric"}
    if (not np.isfinite(x).all() or not np.isfinite(y_numeric).all() or not np.isin(x, K_GRID).all()
            or not np.isin(y_numeric, [0.0, 1.0]).all()):
        return {**_metadata(), "n": 0, "label": "unevaluable", "reason": "cm_k must be in the tested grid and flip must be binary"}
    y = y_numeric.astype(int)
    counts = {k: int((x == k).sum()) for k in K_GRID}
    result: dict[str, Any] = {**_metadata(), "n": int(len(y)), "k_grid": list(K_GRID), "cell_n": counts,
                              "empirical_probabilities": _empirical(x, y), "omnibus_lr_df": 2,
                              "omnibus_lr_stat": None, "omnibus_lr_p": None,
                              "linear_logit_coef": None, "linear_logit_p": None,
                              "linear_lr_stat_vs_intercept": None, "linear_lr_p_vs_intercept": None}
    if any(count < MIN_N_FOR_INFERENCE for count in counts.values()):
        result.update(label="unevaluable", reason="each expected k cell requires at least 8 eligible runs")
        return result
    if len(set(y.tolist())) < 2:
        result.update(label="unevaluable", reason="flip outcome has no variance")
        return result
    categorical = pd.get_dummies(pd.Categorical(x, categories=K_GRID), drop_first=True).astype(float).to_numpy()
    full_design = sm.add_constant(categorical, has_constant="add")
    null_design = np.ones((len(y), 1))
    try:
        full_fit, null_fit = _fit_logit(y, full_design), _fit_logit(y, null_design)
        stat = float(2 * (full_fit.llf - null_fit.llf))
        if not np.isfinite(stat) or stat < 0:
            raise ValueError("invalid categorical likelihood-ratio statistic")
        result.update(label="evaluable", omnibus_lr_stat=stat, omnibus_lr_p=float(chi2.sf(stat, df=2)))
    except _FIT_EXCEPTIONS as exc:
        result.update(label="unevaluable", reason=f"categorical logit fit failed: {exc}")
        return result
    try:
        linear_fit = _fit_logit(y, sm.add_constant(x, has_constant="add"))
        stat = float(2 * (linear_fit.llf - null_fit.llf))
        if not np.isfinite(stat) or stat < 0:
            raise ValueError("invalid secondary linear likelihood-ratio statistic")
        result.update(linear_logit_coef=float(linear_fit.params[1]), linear_logit_p=float(linear_fit.pvalues[1]), linear_lr_stat_vs_intercept=stat, linear_lr_p_vs_intercept=float(chi2.sf(stat, df=1)))
    except _FIT_EXCEPTIONS as exc:
        result["linear_reason"] = f"secondary linear logit fit failed: {exc}"
    return result


def sensitivity_50_agreement(flip_95: Sequence[int], flip_50: Sequence[int]) -> dict[str, Any]:
    a, b = np.asarray(list(flip_95), dtype=int), np.asarray(list(flip_50), dtype=int)
    return {"n": len(a), "agreement_rate": None if len(a) == 0 else float((a == b).mean())}


def empirical_flip_rates(runs_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["topology", "cm_k", "flip_rate", "n"]
    if runs_df.empty:
        return pd.DataFrame(columns=columns)
    return runs_df.groupby(["topology", "cm_k"], as_index=False).agg(flip_rate=("flip", "mean"), n=("flip", "size"))[columns]
