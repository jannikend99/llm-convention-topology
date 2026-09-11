#!/usr/bin/env python3
"""Rich terminal dashboard (WORKING.md §7.6, §9) -- read-only, 5 KPI widgets.

Thin CLI (§0 principle 6): imports `live/reader.py` for all data, builds a
`rich.layout.Layout` per refresh tick. No writes to `data/`/`logs/` (asserted
by `tests/test_monitor.py::test_monitor_session_leaves_data_mtimes_unchanged`).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

if __name__ == "__main__" and __package__ is None:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.layout import Layout
from rich.live import Live
from rich.table import Table

from live.cost import cost_summary
from live.reader import DashboardState, load_dashboard_state


def _runs_table(state: DashboardState) -> Table:
    table = Table(title="Runs by topology x model x status")
    table.add_column("topology")
    table.add_column("model")
    table.add_column("status")
    table.add_column("count", justify="right")
    if state.runs.empty:
        return table
    counts = (
        state.runs.groupby(["topology", "model_shorthand", "run_status"]).size().reset_index(name="count")
    )
    for _, row in counts.iterrows():
        table.add_row(str(row["topology"]), str(row["model_shorthand"]), str(row["run_status"]), str(row["count"]))
    return table


def _active_runs_table(state: DashboardState) -> Table:
    table = Table(title="Active runs (t, phase, rolling success)")
    table.add_column("run_id")
    table.add_column("t", justify="right")
    table.add_column("phase")
    if state.runs.empty or "run_id" not in state.runs.columns:
        return table
    in_progress = set(state.runs.loc[state.runs["run_status"] == "in_progress", "run_id"])
    if state.events.empty or "run_id" not in state.events.columns:
        return table
    for run_id in sorted(in_progress):
        run_events = state.events[state.events["run_id"] == run_id]
        progress = run_events[run_events["type"].isin(["phase1_progress", "phase2_progress"])]
        if progress.empty:
            continue
        last = progress.iloc[-1]
        phase = "phase1" if last["type"] == "phase1_progress" else "phase2"
        table.add_row(run_id, str(int(last["t"])), phase)
    return table


def _eligibility_table(state: DashboardState) -> Table:
    table = Table(title="Eligibility rate by topology (rolling)")
    table.add_column("topology")
    table.add_column("attempted", justify="right")
    table.add_column("eligible", justify="right")
    table.add_column("rate", justify="right")
    if state.runs.empty or "topology" not in state.runs.columns:
        return table
    finished = state.runs[state.runs["run_status"].isin(["completed", "censored"])]
    for topology, group in finished.groupby("topology"):
        attempted = len(group)
        eligible = int((group["eligibility"] == 1).sum())
        rate = eligible / attempted if attempted else 0.0
        table.add_row(str(topology), str(attempted), str(eligible), f"{rate:.2f}")
    return table


def _api_health_table(state: DashboardState) -> Table:
    table = Table(title="API health (errors/retries)")
    table.add_column("type")
    table.add_column("count", justify="right")
    if state.events.empty or "type" not in state.events.columns:
        return table
    retries = state.events[state.events["type"] == "retry"]
    table.add_row("retry", str(len(retries)))
    return table


def _cost_table(state: DashboardState) -> Table:
    table = Table(title="Cost (cumulative)")
    table.add_column("model_id")
    table.add_column("prompt_tokens", justify="right")
    table.add_column("completion_tokens", justify="right")
    table.add_column("$ estimate", justify="right")
    summary = cost_summary(state.events)
    for _, row in summary.iterrows():
        table.add_row(
            str(row["model_id"]), str(int(row["prompt_tokens"])), str(int(row["completion_tokens"])),
            f"${row['cost_usd']:.4f}",
        )
    return table


def build_layout(state: DashboardState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top"),
        Layout(name="middle"),
        Layout(name="bottom"),
    )
    layout["top"].split_row(Layout(_runs_table(state), name="runs"), Layout(_active_runs_table(state), name="active"))
    layout["middle"].split_row(
        Layout(_eligibility_table(state), name="eligibility"), Layout(_api_health_table(state), name="api_health")
    )
    layout["bottom"].update(_cost_table(state))
    return layout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rich terminal dashboard for live/logs and data sidecars.")
    parser.add_argument("--watch", default="logs/")
    parser.add_argument("--data", default="data")
    parser.add_argument("--refresh", type=float, default=5.0, help="Seconds between refreshes.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-refreshes", type=int, default=None, help="Stop after N refreshes (testing).")
    args = parser.parse_args(argv)

    logs_dir, data_dir = Path(args.watch), Path(args.data)
    refresh_per_second = 1.0 / args.refresh if args.refresh > 0 else 1.0

    count = 0
    with Live(build_layout(load_dashboard_state(logs_dir, data_dir, args.model)), refresh_per_second=refresh_per_second) as live:
        while args.max_refreshes is None or count < args.max_refreshes:
            state = load_dashboard_state(logs_dir, data_dir, args.model)
            live.update(build_layout(state))
            count += 1
            if args.max_refreshes is not None and count >= args.max_refreshes:
                break
            time.sleep(args.refresh)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
