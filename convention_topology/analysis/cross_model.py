"""Cross-model robustness comparison (WORKING.md §8) -- descriptive only.

Llama-3.1-70B is the primary confirmatory model; the other three are
descriptive robustness strata. This module never pools or runs inference
across models (Methods cross-model rule, locked).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from convention_topology.analysis.common import critical_mass


def cross_model_summary(per_model_run_tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for model, df in per_model_run_tables.items():
        eligible = df[df["eligibility"] == 1] if "eligibility" in df.columns else df.iloc[0:0]
        # H1/H2 pool *all attempted* Phase 1 trajectories, censored included
        # (03_Methods.tex:212,246) -- mean_dominant_share must match that
        # population, not just gate-passed runs, or heavy censoring in a
        # sparse topology silently inflates this descriptive stat relative
        # to the confirmatory H1/H2 construct it's meant to summarize.
        attempted = df[df["dominant_share"].notna()] if "dominant_share" in df.columns else df.iloc[0:0]
        summary[model] = {
            "n_eligible": len(eligible),
            "n_attempted": len(attempted),
            "mean_dominant_share": (
                float(attempted["dominant_share"].mean()) if not attempted.empty else None
            ),
            "flip_rate": (
                float(eligible["flip"].mean()) if not eligible.empty and "flip" in eligible.columns else None
            ),
            "critical_mass": critical_mass(df).to_dict("records") if not df.empty else [],
        }
    return summary
