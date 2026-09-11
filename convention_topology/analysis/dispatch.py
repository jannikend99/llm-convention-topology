"""Analysis dispatch: per-hypothesis runners. Cell keys are the locked grid."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from convention_topology.analysis.common import gate_table, load_run_table
from convention_topology.analysis.cross_model import cross_model_summary
from convention_topology.analysis.h1 import h1_analysis
from convention_topology.analysis.h2 import h2_analysis
from convention_topology.analysis.h3a import h3a_analysis, sensitivity_50_agreement
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.analysis.h4 import h4_analysis
from convention_topology.analysis.memory_decision import compare_memory_decision, run_memory_decision
from convention_topology.persistence import write_analysis_csv, write_analysis_json


def run_h1(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]
    mixing = emergence[(emergence["topology"] == "mixing") & emergence["dominant_share"].notna()]
    result = h1_analysis(mixing["dominant_share"].tolist())
    write_analysis_json(outputs_dir / "h1.json", result)
    write_analysis_csv(outputs_dir / "h1.csv", mixing)
    return result


def run_h2(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]

    def _subset(topology: str) -> pd.DataFrame:
        return emergence[(emergence["topology"] == topology) & emergence["dominant_share"].notna()]

    mixing = _subset("mixing")
    lattice = _subset("lattice")
    random_regular = _subset("random_regular")
    result = h2_analysis(
        mixing["dominant_share"].tolist(),
        lattice["dominant_share"].tolist(),
        random_regular["dominant_share"].tolist(),
        mixing["shannon_entropy"].tolist(),
        lattice["shannon_entropy"].tolist(),
        random_regular["shannon_entropy"].tolist(),
    )
    frames = [mixing, lattice, random_regular, _subset("watts_strogatz"), _subset("barabasi_albert")]
    write_analysis_json(outputs_dir / "h2.json", result)
    write_analysis_csv(outputs_dir / "h2.csv", pd.concat(frames, ignore_index=True))
    return result


def run_h3a(runs_df, outputs_dir: Path, sensitivity_50: bool) -> dict[str, Any]:
    cm = runs_df[runs_df["program"] == "cm"]
    mixing = cm[(cm["topology"] == "mixing") & cm["flip"].notna()]
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
    flipped = cm[cm["flip"].notna()]
    result = h3b_analysis(flipped)
    write_analysis_json(outputs_dir / "h3b.json", result)
    write_analysis_csv(outputs_dir / "h3b.csv", flipped)
    return result


def run_h4(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"]
    mixing = emergence[(emergence["topology"] == "mixing") & emergence["incumbent_label"].notna()]
    result = h4_analysis(mixing["incumbent_label"].tolist())
    write_analysis_json(outputs_dir / "h4.json", result)
    write_analysis_csv(outputs_dir / "h4.csv", mixing)
    return result


def run_gate_table(runs_df, outputs_dir: Path) -> None:
    write_analysis_csv(outputs_dir / "gate_table.csv", gate_table(runs_df))


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
    gate_summary: bool,
    cross_model: bool,
    memory_decision: bool = False,
    memory_decision_compare: bool = False,
    sensitivity_50: bool,
    all_: bool,
) -> None:
    if memory_decision_compare:
        compare_memory_decision(data_dir, outputs_dir, models=["llama4_scout", "mistral_small4"])
        if not (memory_decision or all_ or h1 or h2 or h3a or h3b or h4 or gate_summary or cross_model):
            return

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
    if all_ or gate_summary:
        run_gate_table(runs_df, model_outputs_dir)
    if memory_decision:
        run_memory_decision(data_dir, outputs_dir, model=model)
