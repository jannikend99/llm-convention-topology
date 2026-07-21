from __future__ import annotations

import inspect
import json
import random
import tempfile
import time
import unittest
from pathlib import Path

from convention_topology.config import derive_seeds, load_config, resolve_model
from live import reader as reader_module
from live.cost import cost_summary, estimate_cost_usd
from live.monitor import build_layout
from live.reader import events_dataframe, load_dashboard_state, read_events, runs_dataframe
from live.web import (
    api_health_frame,
    cost_frame,
    dominant_share_frame,
    eligibility_frame,
    kpi_frame,
    trajectories_frame,
)
from convention_topology.orchestration import GridCell, run_batch


def _small_config():
    config = load_config()
    config.params.N = 8  # >= max cm_k (6) so swap_committed never exceeds population size
    return config


def _run_small_mocked_batch(n_cells: int, data_dir: Path, logs_dir: Path):
    config = _small_config()
    config.params.total_interactions = 40
    model_spec = resolve_model(config, "mock")
    cells = [
        GridCell(
            "cm",
            "complete",
            i,
            ((i - 1) % 6) + 1,
            *derive_seeds(1, "complete", ((i - 1) % 6) + 1, i),
        )
        for i in range(1, n_cells + 1)
    ]
    run_batch(
        config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
        mock_policy="imitate_modal", workers=1, retry_failed=False,
    )
    return config, model_spec, cells


class EventsTailerTests(unittest.TestCase):
    def test_read_events_tolerates_torn_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.events.jsonl"
            path.write_text('{"type": "phase1_progress", "t": 1}\n{"type": "retry", "attemp')
            events = read_events(path)
            self.assertEqual(events, [{"type": "phase1_progress", "t": 1}])

    def test_read_events_on_missing_file_returns_empty(self):
        events = read_events(Path("/nonexistent/path.jsonl"))
        self.assertEqual(events, [])

    def test_reader_module_never_opens_files_for_writing(self):
        source = inspect.getsource(reader_module)
        self.assertNotIn('"w"', source)
        self.assertNotIn("'w'", source)
        self.assertNotIn("import pickle", source)
        self.assertNotIn("pickle.", source)


class SidecarScannerTests(unittest.TestCase):
    def test_runs_dataframe_on_fixture_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)
            df = runs_dataframe(data_dir)
            self.assertEqual(len(df), 6)
            self.assertTrue(set(df["run_status"]).issubset({"completed", "censored"}))

    def test_events_dataframe_on_fixture_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)
            df = events_dataframe(logs_dir)
            self.assertGreater(len(df), 0)
            self.assertIn("token_usage", set(df["type"]))

    def test_load_dashboard_state_model_filter_restricts_events(self):
        # Regression: load_dashboard_state checked `"run_id" in runs.columns`
        # instead of `events.columns` when filtering events by model, so the
        # events-side filter never actually applied.
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)
            state = load_dashboard_state(logs_dir, data_dir, model_filter="mock")
            run_ids_in_runs = set(state.runs["run_id"])
            self.assertTrue(set(state.events["run_id"]).issubset(run_ids_in_runs))

            state_missing_model = load_dashboard_state(logs_dir, data_dir, model_filter="nonexistent-model")
            self.assertTrue(state_missing_model.runs.empty)
            self.assertTrue(state_missing_model.events.empty)


class CostSummaryTests(unittest.TestCase):
    def test_known_token_totals_give_known_cost(self):
        import pandas as pd

        events = pd.DataFrame(
            [
                {"type": "token_usage", "model_id": "meta-llama/llama-3.1-70b-instruct",
                 "prompt_tokens": 1_000_000, "completion_tokens": 0},
                {"type": "token_usage", "model_id": "meta-llama/llama-3.1-70b-instruct",
                 "prompt_tokens": 0, "completion_tokens": 1_000_000},
            ]
        )
        summary = cost_summary(events)
        row = summary.iloc[0]
        self.assertEqual(row["prompt_tokens"], 1_000_000)
        self.assertEqual(row["completion_tokens"], 1_000_000)
        self.assertAlmostEqual(row["cost_usd"], estimate_cost_usd(row["model_id"], 1_000_000, 1_000_000))
        self.assertAlmostEqual(row["cost_usd"], 0.40 + 0.40)

    def test_empty_events_returns_empty_summary(self):
        import pandas as pd

        summary = cost_summary(pd.DataFrame(columns=["type"]))
        self.assertTrue(summary.empty)

    def test_unknown_model_id_falls_back_to_zero_rate(self):
        self.assertEqual(estimate_cost_usd("some-unlisted-model", 1_000_000, 1_000_000), 0.0)


class MonitorLayoutTests(unittest.TestCase):
    def test_build_layout_populates_widgets_on_mocked_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)
            state = load_dashboard_state(logs_dir, data_dir)
            layout = build_layout(state)
            # All five named panels render without raising.
            for name in ("runs", "active", "eligibility", "api_health", "bottom"):
                self.assertIsNotNone(layout[name])


class WebFrameBuilderTests(unittest.TestCase):
    def test_all_six_panels_non_empty_on_mocked_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)
            state = load_dashboard_state(logs_dir, data_dir)

            self.assertFalse(kpi_frame(state).empty)
            self.assertFalse(eligibility_frame(state).empty)
            self.assertFalse(trajectories_frame(state).empty)
            self.assertFalse(dominant_share_frame(state).empty)
            # api_health_frame legitimately empty when no retries occurred.
            api_health_frame(state)
            self.assertFalse(cost_frame(state).empty)

    def test_frame_builders_handle_empty_state_without_raising(self):
        empty_state = load_dashboard_state(Path("/nonexistent/logs"), Path("/nonexistent/data"))
        self.assertTrue(kpi_frame(empty_state).empty)
        self.assertTrue(eligibility_frame(empty_state).empty)
        self.assertTrue(trajectories_frame(empty_state).empty)
        self.assertTrue(dominant_share_frame(empty_state).empty)
        self.assertTrue(api_health_frame(empty_state).empty)
        self.assertTrue(cost_frame(empty_state).empty)


class ReadOnlyVerificationTests(unittest.TestCase):
    def test_monitor_session_leaves_data_mtimes_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(6, data_dir, logs_dir)

            tracked_files = list(data_dir.glob("**/*")) + list(logs_dir.glob("**/*"))
            tracked_files = [p for p in tracked_files if p.is_file()]
            mtimes_before = {p: p.stat().st_mtime_ns for p in tracked_files}

            for _ in range(5):
                state = load_dashboard_state(logs_dir, data_dir)
                build_layout(state)
                runs_dataframe(data_dir)
                events_dataframe(logs_dir)

            mtimes_after = {p: p.stat().st_mtime_ns for p in tracked_files}
            self.assertEqual(mtimes_before, mtimes_after)


if __name__ == "__main__":
    unittest.main()
