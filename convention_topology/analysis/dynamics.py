"""Time-series aggregates from the interaction stream for F1, F5, F7."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from convention_topology.dvs import DEFAULT_WINDOW
from convention_topology.persistence import read_events
from convention_topology.analysis.stream import interactions_from_events, tracker_from_interactions


def _mean_ci(values: np.ndarray) -> tuple[float, float, float]:
    n = len(values)
    mean = float(values.mean()) if n else float("nan")
    if n < 2:
        return mean, mean, mean
    se = float(values.std(ddof=1) / np.sqrt(n))
    tcrit = float(stats.t.ppf(0.975, n - 1))
    return mean, mean - tcrit * se, mean + tcrit * se


def success_by_round(runs_df: pd.DataFrame, *, mixing_only: bool = False) -> pd.DataFrame:
    columns = ["model_shorthand", "topology", "t", "round", "mean_success", "ci_low", "ci_high", "n"]
    if runs_df.empty:
        return pd.DataFrame(columns=columns)
    work = runs_df
    if mixing_only:
        work = work[work["topology"] == "mixing"]
    buckets: dict[tuple[Any, Any, int], list[int]] = {}
    for _, row in work.iterrows():
        path = row.get("events_path")
        if not path or not Path(path).exists():
            continue
        n_agents = int(row["N"]) if pd.notna(row.get("N")) else 48
        for ix in interactions_from_events(read_events(Path(path))):
            key = (row.get("model_shorthand"), row.get("topology"), int(ix["t"]))
            buckets.setdefault(key, []).append(int(ix["success"]))
    rows = []
    for (model, topology, t), successes in sorted(buckets.items(), key=lambda item: (str(item[0][0]), str(item[0][1]), item[0][2])):
        arr = np.asarray(successes, dtype=float)
        mean, low, high = _mean_ci(arr)
        n_agents = 48
        rows.append(
            {
                "model_shorthand": model,
                "topology": topology,
                "t": t,
                "round": t / n_agents,
                "mean_success": mean,
                "ci_low": low,
                "ci_high": high,
                "n": len(arr),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def phase_points(runs_df: pd.DataFrame, window: int = DEFAULT_WINDOW) -> pd.DataFrame:
    columns = ["run_id", "topology", "model_shorthand", "t", "window_success", "unique_labels"]
    if runs_df.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in runs_df.iterrows():
        path = row.get("events_path")
        if not path or not Path(path).exists():
            continue
        tracker = tracker_from_interactions(interactions_from_events(read_events(Path(path))))
        answers, outcomes = tracker["answers"], tracker["outcome"]
        if len(outcomes) < window:
            continue
        for end in range(window, len(outcomes) + 1):
            window_answers = answers[end - window : end]
            labels = {label for pair in window_answers for label in pair}
            rows.append(
                {
                    "run_id": row.get("run_id"),
                    "topology": row.get("topology"),
                    "model_shorthand": row.get("model_shorthand"),
                    "t": end,
                    "window_success": float(sum(outcomes[end - window : end]) / window),
                    "unique_labels": len(labels),
                }
            )
    return pd.DataFrame(rows, columns=columns)
