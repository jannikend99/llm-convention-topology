"""Shared read-only data layer for live analytics (monitor, web, notebook).

Reads **only** `logs/*.events.jsonl` (append-only, tolerant of a torn last
line) and `data/**/*.meta.json` sidecars -- never a pickle of an active run
(WORKING.md §9). `monitor.py`, `web.py`, and the notebook all import this
module instead of duplicating tail/parse logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


def read_events(events_path: Path) -> list[dict[str, Any]]:
    """Parse a `.jsonl` events file line by line, skipping a torn last line."""
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with events_path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a partial last line from an in-progress writer
    return events


def scan_sidecars(data_dir: Path) -> list[dict[str, Any]]:
    """Read every `*.meta.json` sidecar under `data_dir/runs/`."""
    runs_root = Path(data_dir) / "runs"
    if not runs_root.exists():
        return []
    sidecars: list[dict[str, Any]] = []
    for meta_path in sorted(runs_root.glob("**/*.meta.json")):
        try:
            with meta_path.open("r", encoding="utf-8") as handle:
                sidecars.append(json.load(handle))
        except (json.JSONDecodeError, OSError):
            continue  # tolerate a sidecar mid-write
    return sidecars


def runs_dataframe(data_dir: Path) -> pd.DataFrame:
    """One row per run sidecar (empty DataFrame with expected columns if none exist)."""
    sidecars = scan_sidecars(data_dir)
    columns = [
        "run_id", "topology", "cm_k", "model_shorthand", "model_id",
        "run_status", "eligibility", "t_gate", "n_api_calls", "n_retries",
        "started_at", "finished_at",
    ]
    if not sidecars:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(sidecars)


def events_dataframe(logs_dir: Path, run_id: str | None = None) -> pd.DataFrame:
    """All events across `logs_dir/*.events.jsonl`, optionally filtered to one run_id."""
    logs_dir = Path(logs_dir)
    columns = ["run_id", "type", "t"]
    if not logs_dir.exists():
        return pd.DataFrame(columns=columns)

    paths = [logs_dir / f"{run_id}.events.jsonl"] if run_id else sorted(logs_dir.glob("*.events.jsonl"))
    rows: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        this_run_id = path.stem.removesuffix(".events")
        for event in read_events(path):
            row = dict(event)
            row.setdefault("run_id", this_run_id)
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


@dataclass
class DashboardState:
    runs: pd.DataFrame
    events: pd.DataFrame
    model_filter: str | None = field(default=None)


def load_dashboard_state(logs_dir: Path, data_dir: Path, model_filter: str | None = None) -> DashboardState:
    """Single entry point monitor/web/notebook call each refresh tick."""
    runs = runs_dataframe(data_dir)
    events = events_dataframe(logs_dir)
    if model_filter and not runs.empty and "model_shorthand" in runs.columns:
        runs = runs[runs["model_shorthand"] == model_filter]
        if not events.empty and "run_id" in events.columns:
            events = events[events["run_id"].isin(set(runs["run_id"]))]
    return DashboardState(runs=runs, events=events, model_filter=model_filter)
