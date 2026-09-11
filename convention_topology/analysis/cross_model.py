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
        emergence = df[df["program"] == "emergence"] if "program" in df.columns else df.iloc[0:0]
        cm = df[df["program"] == "cm"] if "program" in df.columns else df.iloc[0:0]
        eligible_cm = (
            cm[(cm["prepared_state_valid"] == True) & cm["flip"].notna()]  # noqa: E712
            if not cm.empty
            else cm
        )
        attempted_emergence = (
            emergence[emergence["gate_passed"] == True]  # noqa: E712
            if not emergence.empty and "gate_passed" in emergence.columns
            else emergence
        )
        summary[model] = {
            "n_eligible": len(eligible_cm),
            "n_attempted": len(attempted_emergence),
            "mean_dominant_share": (
                float(attempted_emergence["dominant_share"].mean())
                if not attempted_emergence.empty
                else None
            ),
            "flip_rate": (
                float(eligible_cm["flip"].mean())
                if not eligible_cm.empty and "flip" in eligible_cm.columns
                else None
            ),
            "critical_mass": critical_mass(df).to_dict("records") if not df.empty else [],
        }
    return summary
