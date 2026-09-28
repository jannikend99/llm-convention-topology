"""H3b: flip ~ cm_k x topology interaction (WORKING.md §8, locked M04).

Exploratory logistic regression (statsmodels), LR test vs the main-effects
model. The cell-n floor controls fit evaluability only; it never changes the
exploratory status.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd
import numpy as np
import statsmodels.api as sm
from numpy.linalg import LinAlgError
from scipy.stats import chi2
from statsmodels.tools.sm_exceptions import ConvergenceWarning, PerfectSeparationError, PerfectSeparationWarning
import warnings

MIN_CELL_N = 8
MIN_TOPOLOGIES = 2
DEFAULT_EXPECTED_CM_KS = (5, 10, 14)

_FIT_EXCEPTIONS = (LinAlgError, PerfectSeparationError, PerfectSeparationWarning, ConvergenceWarning, ValueError)


def _design_matrices(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["cm_k_centered"] = df["cm_k"] - df["cm_k"].mean()
    topology_dummies = pd.get_dummies(df["topology"], prefix="topology", drop_first=True).astype(float)
    main = pd.concat(
        [pd.Series(1.0, index=df.index, name="const"), df["cm_k_centered"], topology_dummies], axis=1
    )
    interaction = pd.DataFrame(
        {f"cm_k:{col}": df["cm_k_centered"] * topology_dummies[col] for col in topology_dummies.columns}
    )
    full = pd.concat([main, interaction], axis=1)
    return main, full


def _qualifying_topologies(df: pd.DataFrame, expected_cm_ks: Sequence[int]) -> list[str]:
    """>=2 topologies each with >=8 eligible runs in **every** expected cm_k cell.

    M3 fix: a cell entirely absent from `df` (zero eligible runs for a given
    `(topology, cm_k)`) has no row in `df.groupby(...)`'s result at all --
    `.groupby(...).size()` is blind to cells with zero observations, so
    checking `(cell_counts >= MIN_CELL_N).all()` over only the *observed*
    cells could previously let a topology with a structurally-empty cell
    (e.g. every seed at k=6 censored) still count as qualifying. Each
    topology must now explicitly clear the floor for every k in
    `expected_cm_ks`, via `.get(..., 0)` rather than an all-observed scan.
    """
    observed_counts = df.groupby(["topology", "cm_k"]).size().to_dict()
    qualifying_topologies = []
    for topology in df["topology"].unique():
        if all(observed_counts.get((topology, k), 0) >= MIN_CELL_N for k in expected_cm_ks):
            qualifying_topologies.append(topology)
    return qualifying_topologies


def h3b_analysis(
    runs_df: pd.DataFrame,
    expected_cm_ks: Sequence[int] = DEFAULT_EXPECTED_CM_KS,
) -> dict[str, Any]:
    df = runs_df.dropna(subset=["flip", "cm_k", "topology"])
    numeric_flip = pd.to_numeric(df["flip"], errors="coerce")
    numeric_k = pd.to_numeric(df["cm_k"], errors="coerce")
    valid_values = (numeric_flip.isin([0, 1]) & numeric_k.isin(expected_cm_ks) & np.isfinite(numeric_flip) & np.isfinite(numeric_k))
    if not valid_values.all():
        return {"n": int(len(df)), "label": "exploratory", "analysis_status": "exploratory", "cell_floor_met": False,
                "fit_evaluable": False, "reason": "cm_k must be in the tested grid and flip must be binary"}
    df = df.copy()
    df["flip"], df["cm_k"] = numeric_flip.astype(int), numeric_k.astype(float)
    n = len(df)
    label = "exploratory"
    qualifying_topologies = _qualifying_topologies(df, expected_cm_ks)
    cell_floor_met = len(qualifying_topologies) >= MIN_TOPOLOGIES

    y = df["flip"].astype(int).to_numpy()
    if n < MIN_CELL_N or df["topology"].nunique() < MIN_TOPOLOGIES or len(set(y.tolist())) < 2:
        return {"n": n, "label": label, "analysis_status": "exploratory", "cell_floor_met": cell_floor_met,
                "fit_evaluable": False, "reason": "insufficient data or outcome variation for interaction model fit"}

    if not cell_floor_met:
        return {"n": n, "label": label, "analysis_status": "exploratory", "cell_floor_met": False, "fit_evaluable": False,
                "reason": "expected cells do not meet the exploratory fit floor"}
    df = df[df["topology"].isin(qualifying_topologies)].copy()
    n = len(df)
    y = df["flip"].astype(int).to_numpy()
    if len(set(y.tolist())) < 2:
        return {"n": n, "label": label, "analysis_status": "exploratory", "cell_floor_met": True,
                "fit_evaluable": False, "qualifying_topologies": sorted(qualifying_topologies),
                "reason": "qualified topology subset has no flip outcome variation"}

    main, full = _design_matrices(df)
    if np.linalg.matrix_rank(main.to_numpy()) < main.shape[1] or np.linalg.matrix_rank(full.to_numpy()) < full.shape[1]:
        return {"n": n, "label": label, "analysis_status": "exploratory", "cell_floor_met": True,
                "fit_evaluable": False, "qualifying_topologies": sorted(qualifying_topologies),
                "reason": "interaction design matrix is rank deficient"}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            warnings.simplefilter("error", PerfectSeparationWarning)
            main_fit = sm.Logit(y, main.to_numpy()).fit(disp=0, method="newton", maxiter=200)
            full_fit = sm.Logit(y, full.to_numpy()).fit(disp=0, method="newton", maxiter=200)
        if not bool(main_fit.mle_retvals.get("converged", False)) or not bool(full_fit.mle_retvals.get("converged", False)):
            raise ValueError("interaction model did not converge")
        if (not np.isfinite(main_fit.llf) or not np.isfinite(full_fit.llf)
                or not np.isfinite(main_fit.params).all() or not np.isfinite(full_fit.params).all()):
            raise ValueError("interaction model has invalid estimates or possible separation")
        lr_stat = float(2 * (full_fit.llf - main_fit.llf))
        if not np.isfinite(lr_stat) or lr_stat < 0:
            raise ValueError("invalid interaction likelihood-ratio statistic")
        df_diff = full.shape[1] - main.shape[1]
        lr_p = float(chi2.sf(lr_stat, df=df_diff)) if df_diff > 0 else None
        reason = None
    except _FIT_EXCEPTIONS as exc:
        lr_stat, lr_p = None, None
        reason = f"interaction model fit failed: {exc}"

    result = {
        "n": n,
        "label": label,
        "analysis_status": "exploratory",
        "cell_floor_met": cell_floor_met,
        "fit_evaluable": reason is None,
        "n_topologies": int(df["topology"].nunique()),
        "qualifying_topologies": sorted(qualifying_topologies),
        "lr_stat_interaction_vs_main": lr_stat,
        "lr_p_interaction_vs_main": lr_p,
    }
    if reason is not None:
        result["reason"] = reason
    return result
