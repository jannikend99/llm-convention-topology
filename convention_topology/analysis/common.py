"""Shared run-table loader + eligibility/critical-mass helpers (WORKING.md §8).

`load_run_table` is the single entry point every H1-H4 script consumes: one
row per run, sidecar metadata joined with pickle-derived DVs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from convention_topology.dvs import dominant_share, flip, flip_50, shannon_entropy, time_to_flip
from convention_topology.persistence import PersistenceError, load_run_pickle, read_meta

META_COLUMNS = [
    "run_id",
    "program",
    "init_mode",
    "topology",
    "cm_k",
    "model_shorthand",
    "model_id",
    "run_status",
    "eligibility",
    "t_gate",
    "incumbent_label",
    "committed_to",
]


def scan_meta_paths(data_dir: Path) -> list[Path]:
    runs_root = Path(data_dir) / "runs"
    if not runs_root.exists():
        return []
    return sorted(runs_root.glob("**/*.meta.json"))


def _emergence_tracker(tracker: dict[str, Any], t_gate: int | None) -> dict[str, Any]:
    """Emergence-only prefix for H1/H2 DVs.

    Completed emergence runs store only Phase 1 interactions; `t_gate` still
    slices to the gate index. Censored runs (`t_gate is None`) use the full
    tracker.
    """
    if t_gate is None:
        return tracker
    return {"answers": tracker["answers"][:t_gate]}


def _run_dvs(meta: dict[str, Any], meta_path: Path) -> dict[str, Any]:
    empty = {
        "dominant_share": None,
        "shannon_entropy": None,
        "flip": None,
        "flip_50": None,
        "time_to_flip": None,
    }
    if meta["run_status"] not in ("completed", "censored"):
        return empty

    pickle_path = Path(meta_path).with_suffix("").with_suffix(".pkl")
    try:
        payload = load_run_pickle(pickle_path)
    except PersistenceError:
        return empty

    tracker = payload["tracker"]
    result = dict(empty)
    program = meta.get("program")

    if program == "emergence":
        phase1_tracker = _emergence_tracker(tracker, meta.get("t_gate"))
        if len(phase1_tracker["answers"]) >= 72:
            result["dominant_share"] = dominant_share(phase1_tracker)
            result["shannon_entropy"] = shannon_entropy(phase1_tracker)

    if program == "cm" and meta["run_status"] == "completed" and meta.get("committed_to") is not None:
        t_start = meta.get("t_gate")
        if t_start is None:
            t_start = 0
        result["flip"] = flip(tracker, meta["committed_to"], t_start)
        result["time_to_flip"] = time_to_flip(tracker, meta["committed_to"], t_start)
        result["flip_50"] = flip_50(payload["simulation"], meta["committed_to"])

    return result


def load_run_table(data_dir: Path, model_filter: str | None = None) -> pd.DataFrame:
    """One row per run: sidecar metadata + pickle-derived DVs."""
    rows: list[dict[str, Any]] = []
    for meta_path in scan_meta_paths(data_dir):
        try:
            meta = read_meta(meta_path)
        except PersistenceError:
            continue
        if model_filter and meta.get("model_shorthand") != model_filter:
            continue
        row = dict(meta)
        row.update(_run_dvs(meta, meta_path))
        rows.append(row)

    extra = ["dominant_share", "shannon_entropy", "flip", "flip_50", "time_to_flip"]
    if not rows:
        return pd.DataFrame(columns=META_COLUMNS + extra)
    return pd.DataFrame(rows)


def eligibility_table(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Attempted/eligible/censored/failed counts by topology x model (emergence)."""
    columns = ["topology", "model_shorthand", "attempted", "eligible", "censored", "failed"]
    if runs_df.empty:
        return pd.DataFrame(columns=columns)

    emergence = runs_df[runs_df["program"] == "emergence"]
    if emergence.empty:
        return pd.DataFrame(columns=columns)

    def _agg(group: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "attempted": len(group),
                "eligible": int((group["eligibility"] == 1).sum()),
                "censored": int((group["run_status"] == "censored").sum()),
                "failed": int((group["run_status"] == "failed").sum()),
            }
        )

    grouped = emergence.groupby(["topology", "model_shorthand"]).apply(_agg, include_groups=False).reset_index()
    return grouped[columns]


def critical_mass(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Smallest cm_k with flip rate >= 0.5 among completed CM runs, per topology x model."""
    columns = ["topology", "model_shorthand", "critical_mass"]
    cm = runs_df[runs_df["program"] == "cm"]
    eligible = cm[(cm["eligibility"] == 1) & cm["flip"].notna()]
    if eligible.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for (topology, model), group in eligible.groupby(["topology", "model_shorthand"]):
        flip_rates = group.groupby("cm_k")["flip"].mean().sort_index()
        mass = next((k for k, rate in flip_rates.items() if rate >= 0.5), None)
        rows.append({"topology": topology, "model_shorthand": model, "critical_mass": mass})
    return pd.DataFrame(rows, columns=columns)
