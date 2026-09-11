"""Cross-model robustness comparison — Slate A models are confirmatory, not ranked."""

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
        gated_emergence = (
            emergence[emergence["gate_passed"] == True]  # noqa: E712
            if not emergence.empty and "gate_passed" in emergence.columns
            else emergence
        )
        summary[model] = {
            "n_eligible": len(eligible_cm),
            "n_attempted": len(gated_emergence),
            "mean_dominant_share": (
                float(gated_emergence["dominant_share"].mean())
                if not gated_emergence.empty and "dominant_share" in gated_emergence.columns
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
