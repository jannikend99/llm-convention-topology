"""Shared run-table loader + eligibility/critical-mass helpers (WORKING.md §8).

`load_run_table` is the single entry point every H1-H4 script consumes: one
row per run, sidecar metadata joined with pickle-derived DVs (dominant
share, entropy, flip, flip_50, time_to_flip). Post-hoc only -- reads
completed runs' pickles, unlike the read-only-of-active-runs `live/reader.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from convention_topology.dvs import dominant_share, flip, flip_50, shannon_entropy, time_to_flip
from convention_topology.persistence import PersistenceError, load_run_pickle, read_meta

META_COLUMNS = [
    "run_id", "topology", "cm_k", "model_shorthand", "model_id",
    "run_status", "eligibility", "t_gate", "incumbent_label", "committed_to",
]


def scan_meta_paths(data_dir: Path) -> list[Path]:
    runs_root = Path(data_dir) / "runs"
    if not runs_root.exists():
        return []
    return sorted(runs_root.glob("**/*.meta.json"))


def _phase1_end_tracker(tracker: dict[str, Any], t_gate: int | None) -> dict[str, Any]:
    """The Phase-1-only prefix of `tracker` (R2-B1).

    For a completed run, `tracker["answers"]` spans Phase 1 *and* Phase 2 --
    H1/H2's dominant share / entropy are locked to the trailing 3N window
    "at Phase 1 end" (`03_Methods.tex:199`), not the tracker's raw tail
    (which, for a completed run, is the *end of Phase 2*, after committed-
    minority injection). `t_gate` slices the tracker back to Phase 1 only.
    A censored run never reached the gate (`t_gate is None`) and its
    tracker *is* entirely Phase 1, so no slicing is needed.
    """
    if t_gate is None:
        return tracker
    return {"answers": tracker["answers"][:t_gate]}


def _run_dvs(meta: dict[str, Any], meta_path: Path) -> dict[str, Any]:
    """DVs that need the pickle (tracker/simulation), best-effort per run_status.

    `meta_path` is the exact path `scan_meta_paths`'s glob found (N3) --
    the pickle path is derived from *that*, not reconstructed from
    `model_shorthand`/`topology`/`run_id` string components. A sidecar
    living anywhere `persistence.py::run_paths` wouldn't have put it (a
    recovered file, a future layout change) still yields its pickle DVs
    instead of silently vanishing.
    """
    empty = {"dominant_share": None, "shannon_entropy": None, "flip": None, "flip_50": None, "time_to_flip": None}
    if meta["run_status"] not in ("completed", "censored"):
        return empty

    pickle_path = Path(meta_path).with_suffix("").with_suffix(".pkl")
    try:
        payload = load_run_pickle(pickle_path)
    except PersistenceError:
        return empty

    tracker = payload["tracker"]
    result = dict(empty)
    # H1/H2 pool *all attempted* Phase 1 trajectories, censored included
    # (`03_Methods.tex:212,246`) -- both run_status values reach here.
    phase1_tracker = _phase1_end_tracker(tracker, meta.get("t_gate"))
    if len(phase1_tracker["answers"]) >= 72:
        result["dominant_share"] = dominant_share(phase1_tracker)
        result["shannon_entropy"] = shannon_entropy(phase1_tracker)
    if meta["run_status"] == "completed" and meta.get("committed_to") and meta.get("t_gate") is not None:
        result["flip"] = flip(tracker, meta["committed_to"], meta["t_gate"])
        result["time_to_flip"] = time_to_flip(tracker, meta["committed_to"], meta["t_gate"])
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

    if not rows:
        return pd.DataFrame(columns=META_COLUMNS + ["dominant_share", "shannon_entropy", "flip", "flip_50", "time_to_flip"])
    return pd.DataFrame(rows)


def eligibility_table(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Attempted/eligible/censored/failed counts by topology x model (Results table)."""
    columns = ["topology", "model_shorthand", "attempted", "eligible", "censored", "failed"]
    if runs_df.empty:
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

    grouped = runs_df.groupby(["topology", "model_shorthand"]).apply(_agg, include_groups=False).reset_index()
    return grouped[columns]


def critical_mass(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Smallest cm_k with flip rate >= 0.5 among eligible runs, per topology x model. None if never reached."""
    columns = ["topology", "model_shorthand", "critical_mass"]
    eligible = runs_df[(runs_df["eligibility"] == 1) & runs_df["flip"].notna()]
    if eligible.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for (topology, model), group in eligible.groupby(["topology", "model_shorthand"]):
        flip_rates = group.groupby("cm_k")["flip"].mean().sort_index()
        cm = next((k for k, rate in flip_rates.items() if rate >= 0.5), None)
        rows.append({"topology": topology, "model_shorthand": model, "critical_mass": cm})
    return pd.DataFrame(rows, columns=columns)
