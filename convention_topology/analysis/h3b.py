"""H3b: flip ~ cm_k x topology interaction (WORKING.md §8, locked M04).

Logistic regression (statsmodels), LR test vs the main-effects model.
Auto-labels `confirmatory` when the cell-n floor is met (>=2 topologies
x >=8 prepared-valid rows/cell), else `exploratory`/`informative-null`.
"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd
import statsmodels.api as sm
from numpy.linalg import LinAlgError
from scipy.stats import chi2
from statsmodels.tools.sm_exceptions import PerfectSeparationError

MIN_CELL_N = 8
MIN_TOPOLOGIES = 2
DEFAULT_EXPECTED_CM_KS = (2, 4, 6, 8, 10, 12)

_FIT_EXCEPTIONS = (LinAlgError, PerfectSeparationError, ValueError)


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


def _is_confirmatory(df: pd.DataFrame, expected_cm_ks: Sequence[int]) -> bool:
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
    qualifying_topologies = 0
    for topology in df["topology"].unique():
        if all(observed_counts.get((topology, k), 0) >= MIN_CELL_N for k in expected_cm_ks):
            qualifying_topologies += 1
    return qualifying_topologies >= MIN_TOPOLOGIES


def h3b_analysis(
    runs_df: pd.DataFrame,
    expected_cm_ks: Sequence[int] = DEFAULT_EXPECTED_CM_KS,
) -> dict[str, Any]:
    df = runs_df.dropna(subset=["flip", "cm_k", "topology"])
    n = len(df)
    label = "confirmatory" if _is_confirmatory(df, expected_cm_ks) else "exploratory"

    y = df["flip"].astype(int).to_numpy()
    if n < MIN_CELL_N or df["topology"].nunique() < MIN_TOPOLOGIES or len(set(y.tolist())) < 2:
        return {"n": n, "label": label, "reason": "insufficient data for interaction model fit"}

    main, full = _design_matrices(df)
    try:
        main_fit = sm.Logit(y, main.to_numpy()).fit(disp=0, method="lbfgs", maxiter=200)
        full_fit = sm.Logit(y, full.to_numpy()).fit(disp=0, method="lbfgs", maxiter=200)
        lr_stat = float(2 * (full_fit.llf - main_fit.llf))
        df_diff = full.shape[1] - main.shape[1]
        lr_p = float(chi2.sf(lr_stat, df=df_diff)) if df_diff > 0 else None
        reason = None
    except _FIT_EXCEPTIONS as exc:
        lr_stat, lr_p = None, None
        reason = f"interaction model fit failed: {exc}"

    result = {
        "n": n,
        "label": label,
        "n_topologies": int(df["topology"].nunique()),
        "lr_stat_interaction_vs_main": lr_stat,
        "lr_p_interaction_vs_main": lr_p,
    }
    if reason is not None:
        result["reason"] = reason
    return result
