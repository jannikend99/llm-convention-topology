"""Streamlit localhost dashboard (WORKING.md §7.8, §9) -- six live panels.

Shares `live/reader.py` + `live/cost.py` with `monitor.py` (no duplicate
jsonl parsing, §0 single-data-layer rule). Frame builders are pure functions
of a `DashboardState` and are unit-tested in `tests/test_monitor.py`; the
`st.*` rendering in `main()` is manual-smoke-only (excluded from CI, §7.8).

Launch: `streamlit run live/web.py --server.headless true --server.port 8501`
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__" and __package__ is None:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from live.cost import cost_summary
from live.reader import DashboardState, load_dashboard_state


def kpi_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 1: run status KPIs -- counts by topology x model x run_status."""
    if state.runs.empty:
        return pd.DataFrame(columns=["topology", "model_shorthand", "run_status", "count"])
    return (
        state.runs.groupby(["topology", "model_shorthand", "run_status"])
        .size()
        .reset_index(name="count")
    )


def eligibility_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 2: cumulative eligible/attempted per topology."""
    if state.runs.empty:
        return pd.DataFrame(columns=["topology", "attempted", "eligible", "rate"])
    finished = state.runs[state.runs["run_status"].isin(["completed", "censored"])]
    if finished.empty:
        return pd.DataFrame(columns=["topology", "attempted", "eligible", "rate"])
    grouped = finished.groupby("topology").agg(
        attempted=("run_id", "count"), eligible=("eligibility", "sum")
    ).reset_index()
    grouped["rate"] = grouped["eligible"] / grouped["attempted"]
    return grouped


def trajectories_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 3: rolling 3N success vs t for active + recent runs."""
    if state.events.empty or "type" not in state.events.columns:
        return pd.DataFrame(columns=["run_id", "t", "rolling_success"])
    progress = state.events[state.events["type"].isin(["phase1_progress", "phase2_progress"])]
    if progress.empty or "rolling_success" not in progress.columns:
        return pd.DataFrame(columns=["run_id", "t", "rolling_success"])
    return progress[["run_id", "t", "rolling_success"]].dropna()


def dominant_share_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 4: latest dominant-share snapshot per topology."""
    if state.events.empty or "type" not in state.events.columns:
        return pd.DataFrame(columns=["run_id", "topology", "dominant_share"])
    progress = state.events[state.events["type"].isin(["phase1_progress", "phase2_progress"])]
    if progress.empty or "dominant_share" not in progress.columns:
        return pd.DataFrame(columns=["run_id", "topology", "dominant_share"])
    latest = progress.dropna(subset=["dominant_share"]).groupby("run_id").tail(1)
    if state.runs.empty:
        latest["topology"] = None
        return latest[["run_id", "topology", "dominant_share"]]
    merged = latest.merge(state.runs[["run_id", "topology"]], on="run_id", how="left")
    return merged[["run_id", "topology", "dominant_share"]]


def api_health_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 5: retry/error counts by class."""
    if state.events.empty or "type" not in state.events.columns:
        return pd.DataFrame(columns=["error", "count"])
    retries = state.events[state.events["type"] == "retry"]
    if retries.empty:
        return pd.DataFrame(columns=["error", "count"])
    if "error" not in retries.columns:
        retries = retries.assign(error="unknown")
    return retries.groupby("error").size().reset_index(name="count")


def cost_frame(state: DashboardState) -> pd.DataFrame:
    """Panel 6: cumulative token usage + $ estimate."""
    return cost_summary(state.events)


def main() -> None:  # pragma: no cover -- manual localhost smoke only (§7.8)
    import streamlit as st

    st.set_page_config(page_title="Naming Game Pilot", layout="wide")
    logs_dir = Path(st.sidebar.text_input("logs dir", "logs"))
    data_dir = Path(st.sidebar.text_input("data dir", "data"))
    model_filter = st.sidebar.text_input("model filter (blank = all)", "") or None
    refresh_s = st.sidebar.slider("Refresh (s)", 2, 30, 5)
    st.sidebar.caption("Read-only · logs/*.jsonl + sidecars")

    def panels() -> None:
        state = load_dashboard_state(logs_dir, data_dir, model_filter)

        st.subheader("1. Run status KPIs")
        kpi = kpi_frame(state)
        cols = st.columns(max(len(kpi), 1))
        for col, (_, row) in zip(cols, kpi.iterrows()):
            col.metric(f"{row['topology']}/{row['model_shorthand']}/{row['run_status']}", int(row["count"]))

        st.subheader("2. Eligibility rate")
        st.line_chart(eligibility_frame(state).set_index("topology")["rate"] if not eligibility_frame(state).empty else None)

        st.subheader("3. Coordination trajectories")
        traj = trajectories_frame(state)
        if not traj.empty:
            st.line_chart(traj.pivot_table(index="t", columns="run_id", values="rolling_success"))

        st.subheader("4. Dominant share")
        st.bar_chart(dominant_share_frame(state).set_index("run_id")["dominant_share"] if not dominant_share_frame(state).empty else None)

        st.subheader("5. API health")
        st.bar_chart(api_health_frame(state).set_index("error")["count"] if not api_health_frame(state).empty else None)

        st.subheader("6. Cost")
        st.dataframe(cost_frame(state))

    try:
        fragment = st.fragment(run_every=f"{refresh_s}s")
        fragment(panels)()
    except (AttributeError, TypeError):
        panels()
        st.button("Refresh")


if __name__ == "__main__":  # pragma: no cover
    main()
