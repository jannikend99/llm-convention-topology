"""Analysis dispatch: named spine IDs on the locked grid."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from convention_topology.analysis.common import (
    critical_mass,
    d1_funnel,
    d5_prepared,
    load_run_table,
    prepared_valid_cm,
)
from convention_topology.analysis.cross_model import cross_model_summary
from convention_topology.analysis.dynamics import phase_points, success_by_round
from convention_topology.analysis.figures import (
    HUMAN_F13_CM_MIXING,
    HUMAN_F4,
    HUMAN_SOURCE,
    plot_d1,
    plot_f1,
    plot_f3,
    plot_f4,
    plot_f5,
    plot_f7,
    plot_f13,
    plot_f14,
    plot_f18,
    plot_f24,
    plot_th1,
)
from convention_topology.analysis.h1 import h1_analysis, h1_per_model
from convention_topology.analysis.h2 import CONTRAST_TOPOLOGIES, h2_analysis
from convention_topology.analysis.h3a import empirical_flip_rates, h3a_analysis, sensitivity_50_agreement
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.analysis.h4 import h4_analysis
from convention_topology.persistence import write_analysis_csv, write_analysis_json

STUBBED_MEMORY = "memory-decision analysis is stubbed and cannot run from this CLI"


def _write_id(outputs_dir: Path, stem: str, payload: dict[str, Any], table: pd.DataFrame | None = None) -> None:
    write_analysis_json(outputs_dir / f"{stem}.json", payload)
    if table is not None:
        write_analysis_csv(outputs_dir / f"{stem}.csv", table)


def _load_pool(data_dir: Path) -> list[str]:
    path = Path(data_dir) / "label_pool.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("labels") or [])


def run_d1(runs_df, outputs_dir: Path) -> pd.DataFrame:
    table = d1_funnel(runs_df)
    _write_id(outputs_dir, "D1", {"id": "D1", "rows": table.to_dict("records")}, table)
    plot_d1(table, outputs_dir)
    return table


def run_d5(runs_df, outputs_dir: Path) -> pd.DataFrame:
    table = d5_prepared(runs_df)
    _write_id(outputs_dir, "D5", {"id": "D5", "rows": table.to_dict("records")}, table)
    return table


def run_h1(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"] if not runs_df.empty else runs_df
    mixing = emergence[(emergence["topology"] == "mixing") & emergence["dominant_share"].notna()]
    per_model = h1_per_model(mixing)
    pooled = h1_analysis(mixing["dominant_share"].tolist()) if not mixing.empty else {"n": 0}
    f3_payload = {"id": "F3", "tau": 0.90, "n": int(len(mixing)), "per_model": per_model.to_dict("records")}
    th1_payload = {"id": "T-H1", "rows": per_model.to_dict("records")}
    f24_payload = {"id": "F24", "rows": per_model.to_dict("records"), "note": "per-model H1; no ranked confirmatory model"}
    _write_id(outputs_dir, "F3", f3_payload, mixing.drop(columns=["events_path"], errors="ignore"))
    _write_id(outputs_dir, "T-H1", th1_payload, per_model)
    _write_id(outputs_dir, "F24", f24_payload, per_model)
    plot_f3(mixing, outputs_dir)
    plot_th1(per_model, outputs_dir)
    plot_f24(per_model, outputs_dir)
    series = success_by_round(mixing if not mixing.empty else emergence, mixing_only=True)
    _write_id(outputs_dir, "F1", {"id": "F1", "n_points": int(len(series))}, series)
    plot_f1(series, outputs_dir)
    return {"h1": pooled, "T-H1": per_model.to_dict("records")}


def run_h2(runs_df, outputs_dir: Path) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"] if not runs_df.empty else runs_df
    scored = emergence[emergence["dominant_share"].notna()] if not emergence.empty else emergence

    def _shares(topology: str) -> list[float]:
        if scored.empty:
            return []
        return scored.loc[scored["topology"] == topology, "dominant_share"].tolist()

    def _entropy(topology: str) -> list[float]:
        if scored.empty or "shannon_entropy" not in scored.columns:
            return []
        return scored.loc[scored["topology"] == topology, "shannon_entropy"].dropna().tolist()

    shares = {name: _shares(name) for name in ("mixing",) + CONTRAST_TOPOLOGIES}
    entropy = {name: _entropy(name) for name in ("mixing",) + CONTRAST_TOPOLOGIES}
    result = h2_analysis(shares, entropy)
    contrast_rows = []
    for topology in CONTRAST_TOPOLOGIES:
        row = {"topology": topology, **result[f"{topology}_vs_mixing"]}
        contrast_rows.append(row)
    table = pd.DataFrame(contrast_rows)
    table["support"] = result["support"]
    hum = pd.DataFrame(
        [
            {"id": "F-HUM", "quantity": "dominant_share", "topology": topo, "human_value": value, "source": HUMAN_SOURCE["dominant_share"]}
            for topo, value in HUMAN_F4.items()
        ]
        + [
            {
                "id": "F-HUM",
                "quantity": "cm_mixing_share",
                "topology": "mixing",
                "human_value": HUMAN_F13_CM_MIXING,
                "source": HUMAN_SOURCE["cm_mixing"],
            }
        ]
    )
    _write_id(outputs_dir, "T-H2", {"id": "T-H2", **result}, table)
    _write_id(outputs_dir, "F4", {"id": "F4", "n": int(len(scored))}, scored.drop(columns=["events_path"], errors="ignore"))
    _write_id(outputs_dir, "F-HUM", {"id": "F-HUM", "rows": hum.to_dict("records")}, hum)
    plot_f4(scored, outputs_dir)
    f5 = success_by_round(emergence)
    _write_id(outputs_dir, "F5", {"id": "F5", "n_points": int(len(f5))}, f5)
    plot_f5(f5, outputs_dir)
    f7 = phase_points(emergence)
    _write_id(outputs_dir, "F7", {"id": "F7", "n_points": int(len(f7))}, f7)
    plot_f7(f7, outputs_dir)
    return result


def run_h3a(runs_df, outputs_dir: Path, sensitivity_50: bool) -> dict[str, Any]:
    valid = prepared_valid_cm(runs_df)
    valid = valid[valid["flip"].notna()] if not valid.empty else valid
    mixing = valid[valid["topology"] == "mixing"] if not valid.empty else valid
    result = h3a_analysis(mixing["cm_k"].tolist(), mixing["flip"].tolist()) if not mixing.empty else {"n": 0}
    empirical = empirical_flip_rates(valid)
    _write_id(
        outputs_dir,
        "F13",
        {"id": "F13", "h3a": result, "human_cm_mixing": HUMAN_F13_CM_MIXING, "k_grid": [2, 4, 6, 8, 10, 12]},
        empirical,
    )
    plot_f13(empirical, result.get("flip_curve"), outputs_dir)
    if sensitivity_50 and not mixing.empty:
        with_50 = mixing[mixing["flip_50"].notna()]
        agreement = sensitivity_50_agreement(with_50["flip"].tolist(), with_50["flip_50"].tolist())
        write_analysis_csv(outputs_dir / "T-50.csv", pd.DataFrame([agreement]))
    return result


def run_h3b(runs_df, outputs_dir: Path) -> dict[str, Any]:
    valid = prepared_valid_cm(runs_df)
    valid = valid[valid["flip"].notna()] if not valid.empty else valid
    result = h3b_analysis(valid) if not valid.empty else {"n": 0, "label": "exploratory"}
    heat = empirical_flip_rates(valid)
    _write_id(outputs_dir, "F14", {"id": "F14", "h3b": result}, heat)
    plot_f14(heat, outputs_dir)
    rows = []
    if not valid.empty:
        for (topology, model), group in valid.groupby(["topology", "model_shorthand"]):
            rates = group.groupby("cm_k")["flip"].mean().sort_index()
            n_cell = group.groupby("cm_k").size().to_dict()
            mass = next((k for k, rate in rates.items() if rate >= 0.5), None)
            gam = h3a_analysis(group["cm_k"].tolist(), group["flip"].tolist())
            interaction_p = result.get("lr_p_interaction_vs_main") if result.get("label") == "confirmatory" else None
            rows.append(
                {
                    "topology": topology,
                    "model_shorthand": model,
                    "n": int(len(group)),
                    "cell_n": n_cell,
                    "flip_rates": rates.to_dict(),
                    "smallest_k_flip_ge_0.5": mass,
                    "critical_mass": mass,
                    "lr_stat_gam_vs_linear": gam.get("lr_stat_gam_vs_linear"),
                    "lr_p_gam_vs_linear": gam.get("lr_p_gam_vs_linear"),
                    "lr_p_interaction_vs_main": interaction_p,
                    "h3b_label": result.get("label"),
                }
            )
    th3 = pd.DataFrame(rows)
    cm_table = critical_mass(valid) if not valid.empty else pd.DataFrame()
    _write_id(outputs_dir, "T-H3", {"id": "T-H3", "h3b": result, "critical_mass": cm_table.to_dict("records")}, th3)
    return result


def run_h4(runs_df, outputs_dir: Path, data_dir: Path | None = None) -> dict[str, Any]:
    emergence = runs_df[runs_df["program"] == "emergence"] if not runs_df.empty else runs_df
    mixing = emergence[emergence["topology"] == "mixing"] if not emergence.empty else emergence
    winners = mixing["stream_winner"].dropna().tolist() if not mixing.empty and "stream_winner" in mixing.columns else []
    pool = _load_pool(data_dir) if data_dir is not None else []
    if not pool and not mixing.empty and "label_pool" in mixing.columns:
        first = mixing["label_pool"].dropna()
        if len(first):
            value = first.iloc[0]
            pool = list(value) if isinstance(value, (list, tuple)) else []
    result = h4_analysis(winners, pool)
    freq_rows = pd.DataFrame(
        [{"label": label, "frequency": result["frequencies"].get(label, 0.0), "count": result["counts"].get(label, 0)} for label in (pool or result["frequencies"])]
    )
    _write_id(outputs_dir, "F18", {"id": "F18", **result, "source": "stream unique modal, final 3N"}, freq_rows)
    plot_f18(result.get("frequencies") or {}, outputs_dir, pool or list(result.get("frequencies") or {}))
    return result


def run_gate_table(runs_df, outputs_dir: Path) -> None:
    run_d1(runs_df, outputs_dir)


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
    if memory_decision or memory_decision_compare:
        raise SystemExit(STUBBED_MEMORY)

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
        run_d5(runs_df, model_outputs_dir)
    if all_ or h3b:
        run_h3b(runs_df, model_outputs_dir)
    if all_ or h4:
        run_h4(runs_df, model_outputs_dir, data_dir=data_dir)
    if all_ or gate_summary:
        run_d1(runs_df, model_outputs_dir)
