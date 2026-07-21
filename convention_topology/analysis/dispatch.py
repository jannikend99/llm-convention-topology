"""Analysis dispatch: per-hypothesis runners + output writers (§0 principle 6).

Single home for everything `analyze.py` needs: H1-H4 + eligibility +
cross-model runners, using `persistence.write_analysis_json`/
`write_analysis_csv` (N1: analysis-output writes are not exempt from the
single-writer principle) as the sole writers. `analyze.py` reduces to
argument parsing + one call into `run_all`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from convention_topology.analysis.common import critical_mass, eligibility_table, load_run_table
from convention_topology.analysis.cross_model import cross_model_summary
from convention_topology.analysis.h1 import h1_analysis
from convention_topology.analysis.h2 import h2_analysis
from convention_topology.analysis.h3a import h3a_analysis, sensitivity_50_agreement
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.analysis.h4 import h4_analysis
from convention_topology.persistence import write_analysis_csv, write_analysis_json


def run_h1(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]
    mixing = emergence[(emergence["topology"] == "complete") & emergence["dominant_share"].notna()]
    result = h1_analysis(mixing["dominant_share"].tolist())
    write_analysis_json(outputs_dir / "h1.json", result)
    write_analysis_csv(outputs_dir / "h1.csv", mixing)
    return result


def run_h2(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]

    def _subset(topology: str) -> pd.DataFrame:
        return emergence[(emergence["topology"] == topology) & emergence["dominant_share"].notna()]

    mixing, lattice, random_regular = _subset("complete"), _subset("lattice"), _subset("random_regular")
    result = h2_analysis(
        mixing["dominant_share"].tolist(), lattice["dominant_share"].tolist(), random_regular["dominant_share"].tolist(),
        mixing["shannon_entropy"].tolist(), lattice["shannon_entropy"].tolist(), random_regular["shannon_entropy"].tolist(),
    )
    write_analysis_json(outputs_dir / "h2.json", result)
    write_analysis_csv(outputs_dir / "h2.csv", pd.concat([mixing, lattice, random_regular], ignore_index=True))
    return result


def run_h3a(runs_df, outputs_dir: Path, sensitivity_50: bool) -> dict[str, Any]:
    cm = runs_df[runs_df["program"] == "cm"]
    mixing = cm[(cm["topology"] == "complete") & cm["flip"].notna()]
    result = h3a_analysis(mixing["cm_k"].tolist(), mixing["flip"].tolist())
    write_analysis_json(outputs_dir / "h3a.json", result)
    write_analysis_csv(outputs_dir / "h3a.csv", mixing)
    if sensitivity_50:
        with_50 = mixing[mixing["flip_50"].notna()]
        agreement = sensitivity_50_agreement(with_50["flip"].tolist(), with_50["flip_50"].tolist())
        write_analysis_csv(outputs_dir / "flip_agreement.csv", pd.DataFrame([agreement]))
    return result


def run_h3b(runs_df, outputs_dir: Path) -> dict[str, Any]:
    cm = runs_df[runs_df["program"] == "cm"]
    eligible = cm[cm["flip"].notna()]
    result = h3b_analysis(eligible)
    write_analysis_json(outputs_dir / "h3b.json", result)
    write_analysis_csv(outputs_dir / "h3b.csv", eligible)
    return result


def run_h4(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]
    mixing = emergence[(emergence["topology"] == "complete") & emergence["incumbent_label"].notna()]
    result = h4_analysis(mixing["incumbent_label"].tolist())
    write_analysis_json(outputs_dir / "h4.json", result)
    write_analysis_csv(outputs_dir / "h4.csv", mixing)
    return result


def run_eligibility(runs_df, outputs_dir: Path) -> None:
    table = eligibility_table(runs_df)
    write_analysis_csv(outputs_dir / "eligibility.csv", table)


def run_cross_model(data_dir: Path, outputs_dir: Path) -> dict[str, Any]:
    runs_root = data_dir / "runs"
    models = [p.name for p in runs_root.iterdir() if p.is_dir()] if runs_root.exists() else []
    per_model = {model: load_run_table(data_dir, model_filter=model) for model in models}
    result = cross_model_summary(per_model)
    write_analysis_json(outputs_dir / "cross_model.json", result)
    return result


def run_all(
    data_dir: Path,
    outputs_dir: Path,
    *,
    model: str | None,
    h1: bool,
    h2: bool,
    h3a: bool,
    h3b: bool,
    h4: bool,
    eligibility: bool,
    cross_model: bool,
    sensitivity_50: bool,
    all_: bool,
) -> None:
    """The one call `analyze.py` makes: dispatch every requested per-model script + cross-model."""
    if cross_model:
        run_cross_model(data_dir, outputs_dir)
        if not all_:
            return

    if not model:
        return

    model_outputs_dir = outputs_dir / model
    runs_df = load_run_table(data_dir, model_filter=model)

    if all_ or h1:
        run_h1(runs_df, model_outputs_dir)
    if all_ or h2:
        run_h2(runs_df, model_outputs_dir)
    if all_ or h3a:
        run_h3a(runs_df, model_outputs_dir, sensitivity_50=sensitivity_50)
    if all_ or h3b:
        run_h3b(runs_df, model_outputs_dir)
    if all_ or h4:
        run_h4(runs_df, model_outputs_dir)
    if all_ or eligibility:
        run_eligibility(runs_df, model_outputs_dir)
