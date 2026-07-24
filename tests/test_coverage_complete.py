"""Targeted tests to close remaining coverage gaps across convention_topology/ and live/."""

from __future__ import annotations

import asyncio
import json
import os
import pickle
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
from openai import RateLimitError

from convention_topology.analysis import common as analysis_common
from convention_topology.analysis.common import critical_mass, eligibility_table
from convention_topology.analysis.dispatch import (
    run_all,
    run_cross_model,
    run_eligibility,
    run_h1,
    run_h2,
    run_h3a,
    run_h3b,
    run_h4,
)
from convention_topology.analysis.h1 import h1_analysis
from convention_topology.analysis.h2 import h2_analysis
from convention_topology.analysis.h3a import h3a_analysis
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.async_llm import (
    AsyncClientAdapter,
    ProviderPool,
    RateLimitedError,
    RateLimiter,
    _retry_after_seconds,
)
from convention_topology.async_run import execute_cm_run_async, execute_emergence_run_async
from convention_topology.config import ConfigError, ModelSpec, _parse_openrouter_provider, resolve_model, load_config
from convention_topology.dvs import flip_50
from convention_topology.llm import MockLLMClient, RetryPolicy, RunFailedError
from convention_topology.networks import get_interaction_network
from convention_topology.orchestration import (
    GridCell,
    ProgressHeartbeat,
    build_client,
    build_run_config,
    build_run_config_for_cell,
    cell_targets,
    get_code_commit,
    latest_run_progress,
    options_for_program,
    pilot_grid,
    retry_policy_for,
    run_batch,
    run_cell_targeted,
    run_main_study,
    run_pilot,
)
from convention_topology.persistence import (
    EventWriter,
    PersistenceError,
    build_run_id,
    load_run_pickle,
    read_meta,
    run_paths,
    save_run_pickle,
    write_meta,
    write_analysis_csv,
    write_analysis_json,
    META_FIELDS,
)
from convention_topology.prepared import PreparedInitError, committed_label, make_prepared_population, set_initial_state
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    RunConfig,
    _dominant_share,
    execute_cm_run,
    execute_emergence_run,
    execute_run,
)
from convention_topology.simulation import make_interaction_step, swap_committed
from convention_topology.tracker import modal_label_in_window, modal_lexicographic, update_dict
from live import monitor as monitor_module
from live import web as web_module
from live.cost import cost_summary
from live.monitor import build_layout, main as monitor_main
from live.reader import (
    DashboardState,
    events_dataframe,
    load_dashboard_state,
    read_events,
    runs_dataframe,
    scan_sidecars,
)
from live.web import (
    api_health_frame,
    cost_frame,
    dominant_share_frame,
    eligibility_frame,
    kpi_frame,
    trajectories_frame,
)

from tests.test_async_run_integration import (
    ASYNC_FAST_RETRY,
    CM_OPTIONS,
    EMERGENCE_OPTIONS,
    _cm_config,
    _emergence_config,
)
from tests.test_monitor import _run_small_mocked_batch
from tests.test_orchestration import _small_config


def _run_batch_for_analysis(data_dir: Path, logs_dir: Path, n_cells: int = 2) -> pd.DataFrame:
    config = _small_config()
    config.params.total_interactions = 80
    model_spec = resolve_model(config, "mock")
    from convention_topology.config import derive_seeds
    cells = [
        GridCell(
            PROGRAM_CM, "complete", i, ((i - 1) % 6) + 1,
            *derive_seeds(config.run.base_seed, "complete", ((i - 1) % 6) + 1, i),
        )
        for i in range(1, n_cells + 1)
    ]
    run_batch(
        config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
        mock_policy="imitate_modal", workers=1, retry_failed=False,
    )
    return analysis_common.load_run_table(data_dir, model_filter="mock")


def _meta_template(run_id: str, *, program: str, run_status: str, **overrides) -> dict:
    meta = {field: None for field in META_FIELDS}
    meta.update(
        run_id=run_id,
        program=program,
        init_mode="organic" if program == PROGRAM_EMERGENCE else "prepared",
        topology="complete",
        cm_k=0 if program == PROGRAM_EMERGENCE else 1,
        options=["A", "B"] if program == PROGRAM_CM else EMERGENCE_OPTIONS,
        incumbent_index=0,
        model_id="mock",
        model_shorthand="mock",
        endpoint_base_url="",
        graph_seed=1,
        run_seed=1,
        adjacency_hash="abc",
        t_gate=80 if program == PROGRAM_EMERGENCE else 0,
        t_phase1_end=None,
        eligibility=1,
        incumbent_label="A",
        committed_to="B" if program == PROGRAM_CM else None,
        phase2_horizon=72,
        config_hash="deadbeefdeadbeef",
        run_status=run_status,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:01:00+00:00" if run_status != "in_progress" else None,
        n_api_calls=1,
        n_retries=0,
        prompt_template_version="v1",
        code_commit="test",
    )
    meta.update(overrides)
    return meta


class OrchestrationUtilityTests(unittest.TestCase):
    def test_latest_run_progress_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            self.assertEqual(latest_run_progress(logs, "missing"), "t=?")
            events = logs / "run.events.jsonl"
            events.write_text('{"type":"phase1_progress","t":3,"phase":"phase1"}\n{bad json\n')
            self.assertIn("phase1 t=3", latest_run_progress(logs, "run"))
            empty = logs / "empty.events.jsonl"
            empty.write_text("\n")
            self.assertEqual(latest_run_progress(logs, "empty"), "t=0 (starting)")

    def test_latest_run_progress_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            events = logs / "run.events.jsonl"
            events.write_text('{"type":"phase1_progress","t":1}\n')
            with patch.object(Path, "open", side_effect=OSError("denied")):
                self.assertEqual(latest_run_progress(logs, "run"), "t=?")

    def test_progress_heartbeat_loop_without_active_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            with ProgressHeartbeat(logs_dir=logs, total=None, enabled=True, interval_s=0.05) as hb:
                time.sleep(0.12)

    @patch("convention_topology.orchestration.subprocess.check_output", side_effect=FileNotFoundError)
    def test_get_code_commit_unknown_on_error(self, _mock):
        self.assertEqual(get_code_commit(), "unknown")

    def test_progress_heartbeat_loop_with_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            events = logs / "rid.events.jsonl"
            events.write_text('{"type":"phase1_progress","t":1,"phase":"phase1"}\n')
            with ProgressHeartbeat(logs_dir=logs, total=3, enabled=True, interval_s=0.05) as hb:
                hb.mark_start("rid")
                time.sleep(0.12)
                hb.mark_done("rid")

    def test_progress_heartbeat_loop_prints_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            events = logs / "rid.events.jsonl"
            events.write_text('{"type":"phase1_progress","t":1,"phase":"phase1"}\n')
            with ProgressHeartbeat(logs_dir=logs, total=None, enabled=True, interval_s=0.05) as hb:
                hb.mark_start("rid")
                time.sleep(0.12)
                hb.mark_done("rid")

    def test_options_and_pilot_grid_invalid_program(self):
        config = load_config()
        with self.assertRaises(ValueError):
            options_for_program(config, "nope")
        with self.assertRaises(ValueError):
            pilot_grid(1, "nope")
        with self.assertRaises(ValueError):
            cell_targets(config, "nope")

    def test_build_run_config_with_openrouter_provider(self):
        config = load_config()
        model_spec = resolve_model(config, "llama31")
        cfg = build_run_config(
            config, model_spec, program=PROGRAM_EMERGENCE, topology="complete",
            cm_k=0, graph_seed=1, run_seed=2,
        )
        self.assertEqual(cfg.model_id, model_spec.model_id)

    @patch("convention_topology.orchestration.OpenAICompatClient")
    def test_build_client_and_retry_policy_for_real_model(self, mock_client):
        config = load_config()
        model_spec = resolve_model(config, "llama31")
        mock_client.return_value = MagicMock()
        client = build_client(model_spec, "imitate_modal", 1, ["A"])
        self.assertIs(client, mock_client.return_value)
        policy = retry_policy_for(model_spec)
        self.assertTrue(len(policy.retry_on) > 1)

    def test_existing_status_corrupt_meta_returns_none(self):
        from convention_topology.config import derive_seeds
        from convention_topology.orchestration import existing_status

        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell(PROGRAM_CM, "complete", 1, 1, *derive_seeds(config.run.base_seed, "complete", 1, 1))
            run_id = build_run_id(model_spec.shorthand, "complete", cell.run_seed, program=PROGRAM_CM, cm_k=1)
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id)
            paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
            paths.meta_path.write_text("{not json")
            self.assertIsNone(existing_status(data_dir, logs_dir, model_spec, cell))


class SyncOrchestrationBatchTests(unittest.TestCase):
    def test_run_batch_workers_two_progress_and_empty_resume(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        cells = [
            GridCell(PROGRAM_CM, "complete", i, 1, *(__import__("convention_topology.config", fromlist=["derive_seeds"]).derive_seeds(1, "complete", 1, i)))
            for i in range(1, 3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            results = run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=2, retry_failed=False, progress=True,
            )
            self.assertEqual(len(results), 2)
            again = run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=2, retry_failed=False, progress=True,
            )
            self.assertEqual(again, results)

    @patch("convention_topology.orchestration.execute_run")
    def test_run_batch_captures_run_failed_and_generic_errors(self, mock_execute):
        mock_execute.side_effect = [RunFailedError("x"), RuntimeError("boom")]
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        from convention_topology.config import derive_seeds
        cells = [
            GridCell(PROGRAM_EMERGENCE, "complete", 1, 0, *derive_seeds(1, "complete", 0, 1)),
            GridCell(PROGRAM_EMERGENCE, "complete", 2, 0, *derive_seeds(1, "complete", 0, 2)),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            results = run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False, progress=True,
            )
            self.assertEqual(set(results.values()), {"failed"})

    def test_run_pilot_topology_filter(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            run_pilot(
                config, model_spec, program=PROGRAM_EMERGENCE, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
                topology_filter="complete", progress=False,
            )


class SyncTargetedAndMainTests(unittest.TestCase):
    def test_run_cell_targeted_sync_skip_and_retry_paths(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        from convention_topology.config import derive_seeds
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            graph_seed, run_seed = derive_seeds(config.run.base_seed, "complete", 1, 1)
            run_id = build_run_id(model_spec.shorthand, "complete", run_seed, program=PROGRAM_CM, cm_k=1)
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id)
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            fake = {f: None for f in META_FIELDS}
            fake.update(run_id=run_id, run_status="failed", topology="complete", cm_k=1, program=PROGRAM_CM)
            write_meta(paths.meta_path, fake)
            hb = ProgressHeartbeat(logs_dir=logs_dir, total=None, enabled=False)
            result = run_cell_targeted(
                config, model_spec, PROGRAM_CM, "complete", 1, target=1, attempted_cap=3,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                retry_failed=True, progress=True, heartbeat=hb,
            )
            self.assertEqual(result["eligible"], 1)

    @patch("convention_topology.orchestration.execute_run")
    def test_run_cell_targeted_sync_exception_paths(self, mock_execute):
        mock_execute.side_effect = RunFailedError("fail")
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            run_cell_targeted(
                config, model_spec, PROGRAM_CM, "complete", 1, target=1, attempted_cap=1,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                retry_failed=False, progress=True, heartbeat=None,
            )
        mock_execute.side_effect = ValueError("unexpected")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            run_cell_targeted(
                config, model_spec, PROGRAM_CM, "complete", 1, target=1, attempted_cap=1,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                retry_failed=False, progress=False, heartbeat=None,
            )

    def test_run_main_study_workers_one_with_progress(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            results = run_main_study(
                config, model_spec, program=PROGRAM_CM, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", retry_failed=False, topology_filter="complete",
                workers=1, progress=True,
            )
            self.assertTrue(len(results) >= 1)

    def test_run_cell_targeted_skips_completed_and_failed_without_retry(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        from convention_topology.config import derive_seeds

        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            graph_seed, run_seed = derive_seeds(config.run.base_seed, "complete", 1, 1)
            run_id = build_run_id(model_spec.shorthand, "complete", run_seed, program=PROGRAM_CM, cm_k=1)
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id)
            paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
            write_meta(paths.meta_path, _meta_template(run_id, program=PROGRAM_CM, run_status="completed"))
            done = run_cell_targeted(
                config, model_spec, PROGRAM_CM, "complete", 1, target=1, attempted_cap=1,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                retry_failed=False, progress=True, heartbeat=None,
            )
            self.assertEqual(done["eligible"], 1)

            run_id2 = build_run_id(model_spec.shorthand, "complete", run_seed, program=PROGRAM_CM, cm_k=1)
            paths2 = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id2)
            write_meta(paths2.meta_path, _meta_template(run_id2, program=PROGRAM_CM, run_status="failed", eligibility=0))
            skipped = run_cell_targeted(
                config, model_spec, PROGRAM_CM, "complete", 1, target=1, attempted_cap=1,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal",
                retry_failed=False, progress=False, heartbeat=None,
            )
            self.assertEqual(skipped["attempted"], 1)
            self.assertEqual(skipped["eligible"], 0)

    def test_run_main_study_workers_two_parallel(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            results = run_main_study(
                config, model_spec, program=PROGRAM_CM, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", retry_failed=False, topology_filter="complete",
                workers=2, progress=True,
            )
            self.assertTrue(len(results) >= 1)


class AnalysisCoverageTests(unittest.TestCase):
    def test_h1_wilcoxon_value_error_branch(self):
        with patch("convention_topology.analysis.h1.stats.wilcoxon", side_effect=ValueError("all zero")):
            out = h1_analysis([0.90, 0.91, 0.92])
        self.assertIsNone(out["wilcoxon_stat"])

    def test_h2_empty_and_entropy_branches(self):
        out = h2_analysis([0.5], [], [0.4], mixing_entropy=[], lattice_entropy=[1.0])
        self.assertEqual(out["lattice_vs_mixing"]["n"], 0)
        self.assertEqual(out["entropy_descriptive"]["mixing"]["n"], 0)

    def test_h3a_insufficient_and_linear_fail(self):
        self.assertIn("reason", h3a_analysis([1], [0]))
        out = h3a_analysis([1, 1, 1, 1], [0, 0, 0, 0])
        self.assertEqual(out["label"], "exploratory")

    def test_h3a_confirmatory_with_variance(self):
        cm_k = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        flip = [0, 1, 0, 1, 0, 1, 1, 0, 1, 1]
        out = h3a_analysis(cm_k, flip)
        self.assertIn(out["label"], ("confirmatory", "exploratory"))

    def test_h3b_fit_failure_and_confirmatory_label(self):
        df = pd.DataFrame({"flip": [0, 0], "cm_k": [1, 2], "topology": ["complete", "complete"]})
        out = h3b_analysis(df)
        self.assertIn("reason", out)

    def test_h3a_gam_edof_undefined_and_fit_failure(self):
        cm_k = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
        flip = [0, 1, 0, 1, 0, 1, 1, 0, 1, 1]
        with patch("pygam.LogisticGAM") as mock_gam_cls:
            mock_gam = mock_gam_cls.return_value
            mock_gam.fit.return_value = mock_gam
            mock_gam.loglikelihood.return_value = 1.0
            mock_gam.statistics_ = {"edof": 2.0}
            mock_gam.predict_proba.return_value = [0.5] * 6
            out = h3a_analysis(cm_k, flip)
            self.assertEqual(out["reason"], "GAM effective df did not exceed the linear model's df; LR test undefined")
        with patch("pygam.LogisticGAM", side_effect=ValueError("gam fail")):
            out2 = h3a_analysis(cm_k, flip)
            self.assertIn("GAM fit failed", out2["reason"])

    def test_h3b_fit_failure_with_confirmatory_data(self):
        rows = []
        for topology in ("complete", "lattice"):
            for k in range(1, 7):
                for i in range(8):
                    rows.append({"topology": topology, "cm_k": k, "flip": i % 2})
        df = pd.DataFrame(rows)
        with patch("convention_topology.analysis.h3b.sm.Logit") as mock_logit:
            mock_logit.return_value.fit.side_effect = ValueError("singular")
            out = h3b_analysis(df)
            self.assertIn("interaction model fit failed", out["reason"])

    def test_analysis_common_helpers_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(analysis_common.scan_meta_paths(root), [])
            tracker = {"answers": [["A", "B"], ["A", "C"]]}
            sliced = analysis_common._emergence_tracker(tracker, t_gate=1)
            self.assertEqual(len(sliced["answers"]), 1)
            sliced2 = analysis_common._emergence_tracker(tracker, t_gate=None)
            self.assertEqual(sliced2, tracker)

            in_progress = _meta_template("r1", program=PROGRAM_EMERGENCE, run_status="in_progress")
            self.assertIsNone(analysis_common._run_dvs(in_progress, root / "r1.meta.json")["dominant_share"])

            data_dir = root / "data"
            logs_dir = root / "logs"
            runs_df = _run_batch_for_analysis(data_dir, logs_dir, n_cells=2)
            self.assertGreaterEqual(len(runs_df), 2)
            self.assertFalse(critical_mass(runs_df).empty)
            self.assertTrue(eligibility_table(runs_df).empty)

            corrupt_dir = data_dir / "runs" / "mock" / "complete"
            corrupt_meta = corrupt_dir / "bad.meta.json"
            corrupt_meta.write_text("{")
            bad_pkl_meta = _meta_template("badcm", program=PROGRAM_CM, run_status="completed")
            write_meta(corrupt_dir / "badcm.meta.json", bad_pkl_meta)
            (corrupt_dir / "badcm.pkl").write_bytes(b"not-pickle")
            no_gate_meta = _meta_template("nogate", program=PROGRAM_CM, run_status="completed", t_gate=None)
            write_meta(corrupt_dir / "nogate.meta.json", no_gate_meta)
            from convention_topology.tracker import empty_tracker
            from convention_topology.networks import get_interaction_network
            sim = get_interaction_network("complete", n=8, graph_seed=1)
            tracker = empty_tracker()
            for _ in range(80):
                tracker["answers"].append(["Q", "M"])
                tracker["outcome"].append(1)
            save_run_pickle(
                corrupt_dir / "nogate.pkl", sim, tracker,
                {"converged_index": 0, "incumbent_label": "Q", "committed_to": "M"},
            )
            analysis_common.load_run_table(data_dir, model_filter="mock")
            filtered = analysis_common.load_run_table(data_dir, model_filter="other")
            self.assertTrue(filtered.empty)

    def test_analysis_dispatch_all_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir, logs_dir, out_dir = root / "data", root / "logs", root / "out"
            runs_df = _run_batch_for_analysis(data_dir, logs_dir, n_cells=3)
            run_eligibility(runs_df, out_dir)
            run_cross_model(data_dir, out_dir)
            run_h1(runs_df, out_dir / "mock")
            run_h2(runs_df, out_dir / "mock")
            run_h3a(runs_df, out_dir / "mock", sensitivity_50=True)
            run_h3b(runs_df, out_dir / "mock")
            run_h4(runs_df, out_dir / "mock")
            run_all(
                data_dir, out_dir, model="mock", h1=False, h2=False, h3a=False, h3b=False, h4=False,
                eligibility=False, cross_model=True, sensitivity_50=False, all_=False,
            )
            run_all(
                data_dir, out_dir, model=None, h1=False, h2=False, h3a=False, h3b=False, h4=False,
                eligibility=False, cross_model=False, sensitivity_50=False, all_=False,
            )
            run_all(
                data_dir, out_dir, model="mock", h1=True, h2=True, h3a=True, h3b=True, h4=True,
                eligibility=True, cross_model=True, sensitivity_50=True, all_=True,
            )
            run_cross_model(root / "empty-data", out_dir / "cross-empty")


class PersistenceAndConfigTests(unittest.TestCase):
    def test_persistence_error_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.pkl"
            with self.assertRaises(PersistenceError):
                load_run_pickle(p)
            p.write_bytes(b"not a pickle")
            with self.assertRaises(PersistenceError):
                load_run_pickle(p)
            meta = Path(tmp) / "m.meta.json"
            with self.assertRaises(PersistenceError):
                read_meta(meta)
            meta.write_text("{")
            with self.assertRaises(PersistenceError):
                read_meta(meta)
            with self.assertRaises(PersistenceError):
                write_meta(Path(tmp) / "bad.meta.json", {"run_id": "only"})
            with self.assertRaises(ValueError):
                build_run_id("m", "complete", 1, program="nope")
            out = Path(tmp) / "sub/out.json"
            write_analysis_json(out, {"ok": True})
            write_analysis_csv(Path(tmp) / "sub/out.csv", pd.DataFrame({"a": [1]}))
            with EventWriter(Path(tmp) / "e.jsonl") as ew:
                ew.emit({"type": "x"})
                self.assertIs(ew.__enter__(), ew)
            bad_pickle = Path(tmp) / "bad.pkl"
            with bad_pickle.open("wb") as handle:
                pickle.dump({"tracker": {}, "convergence": {}}, handle)
            with self.assertRaises(PersistenceError):
                load_run_pickle(bad_pickle)

    def test_config_resolve_edge_cases(self):
        cfg = {"models": {"x": {"model_id": "TBD-doug", "base_url": "http://x", "api_key_env": "K",
                                 "temperature": 0.5, "max_tokens": 1}}}
        with self.assertRaises(ConfigError):
            resolve_model(cfg, "x")
        with self.assertRaises(ConfigError):
            resolve_model(cfg, "missing")
        cfg2 = {"models": {"m": {"model_id": "id", "base_url": "http://custom", "api_key_env": "K",
                                 "temperature": 0.5, "max_tokens": 1}}}
        spec = resolve_model(cfg2, "m")
        self.assertEqual(spec.provider, "unknown")
        cfg3 = {"models": {"or": {"model_id": "id", "base_url": "https://openrouter.ai/api/v1",
                                  "api_key_env": "K", "temperature": 0.5, "max_tokens": 1}}}
        or_spec = resolve_model(cfg3, "or")
        self.assertEqual(or_spec.provider, "openrouter")
        self.assertIsNone(or_spec.openrouter_provider)
        self.assertIsNone(_parse_openrouter_provider({}))
        cfg4 = {"models": {"mock": {"model_id": "mock", "base_url": "", "api_key_env": "",
                                    "temperature": 0.5, "max_tokens": 1}}}
        mock_spec = resolve_model(cfg4, "mock")
        self.assertEqual(mock_spec.provider, "mock")


class DvsLlmSimulationTests(unittest.TestCase):
    def test_flip_50_empty_history_branch(self):
        sim = {0: {"committed_tag": False, "my_history": []}}
        self.assertEqual(flip_50(sim, "A", window=1), 0)

    def test_mock_scripted_policy_requires_responses(self):
        mock = MockLLMClient(policy="scripted", rng=__import__("random").Random(0), options=["A"])
        with self.assertRaises(RuntimeError):
            mock.complete("s", "u")

    def test_modal_and_simulation_committed_branch(self):
        self.assertIsNone(modal_lexicographic([]))
        self.assertIsNone(modal_label_in_window({"answers": [["A"]]}, window_size=3))
        import random
        sim = get_interaction_network("complete", n=4, graph_seed=1)
        rng = random.Random(0)
        swap_committed(sim, 4, rng)
        mock = MockLLMClient(policy="always", rng=random.Random(1), options=["A", "B"], always_label="A")
        step = make_interaction_step(sim, mock, 5, (-50, 100), ["A", "B"], rng, committed_to="A")
        tracker = {"players": [], "answers": [], "outcome": []}
        step(tracker)
        self.assertEqual(mock.call_count, 0)

    def test_networks_invalid_topology(self):
        with self.assertRaises(ValueError):
            get_interaction_network("not_a_topology", n=4, graph_seed=0)


SYNC_FAST_RETRY = RetryPolicy(sleep=lambda _: None)


class SyncRunCoverageTests(unittest.TestCase):
    def test_dominant_share_empty_labels(self):
        tracker = {"answers": [[] for _ in range(80)]}
        self.assertIsNone(_dominant_share(tracker, 72))

    def test_execute_run_unknown_program(self):
        cfg = _emergence_config(program="nope")
        client = MockLLMClient(policy="always", rng=__import__("random").Random(0), options=["A"], always_label="A")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                execute_run(cfg, client, data_dir=Path(tmp) / "data", logs_dir=Path(tmp) / "logs")

    def test_emergence_wrong_program_and_early_return(self):
        cfg = _cm_config()
        client = MockLLMClient(policy="always", rng=__import__("random").Random(0), options=CM_OPTIONS, always_label="Q")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            with self.assertRaises(ValueError):
                execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir)
            emerg_cfg = _emergence_config(run_seed=5)
            emerg_client = MockLLMClient(
                policy="imitate_modal", rng=__import__("random").Random(99), options=list(emerg_cfg.options)
            )
            paths = execute_emergence_run(
                emerg_cfg, emerg_client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY
            )
            first_calls = read_meta(paths.meta_path)["n_api_calls"]
            again = execute_emergence_run(
                emerg_cfg, emerg_client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY
            )
            self.assertEqual(read_meta(again.meta_path)["n_api_calls"], first_calls)

    def test_cm_wrong_program_early_return_and_incumbent_checkpoint(self):
        cfg = _cm_config()
        client = MockLLMClient(policy="always", rng=__import__("random").Random(0), options=CM_OPTIONS, always_label="Q")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            with self.assertRaises(ValueError):
                execute_cm_run(_emergence_config(), client, data_dir=data_dir, logs_dir=logs_dir)
            paths = execute_cm_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY)
            first_calls = read_meta(paths.meta_path)["n_api_calls"]
            again = execute_cm_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY)
            self.assertEqual(read_meta(again.meta_path)["n_api_calls"], first_calls)

    def test_emergence_censored_checkpoint_sets_incumbent_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config(run_seed=77, max_phase1_interactions=72, n=4, checkpoint_every=1000)
            client = MockLLMClient(
                policy="imitate_modal", rng=__import__("random").Random(99), options=list(cfg.options)
            )
            paths = run_paths(
                data_dir, logs_dir, cfg.model_shorthand, cfg.topology,
                build_run_id(cfg.model_shorthand, cfg.topology, cfg.run_seed, program=PROGRAM_EMERGENCE),
            )
            paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            sim = get_interaction_network("complete", n=cfg.n, graph_seed=cfg.graph_seed)
            tracker = {"players": [], "answers": [["A", "B"]] * 72, "outcome": [0] * 72}
            convergence = {"converged_index": 72, "incumbent_label": None, "committed_to": None}
            save_run_pickle(paths.pickle_path, sim, tracker, convergence)
            write_meta(
                paths.meta_path,
                _meta_template(
                    paths.pickle_path.stem, program=PROGRAM_EMERGENCE, run_status="in_progress",
                    t_gate=None, finished_at=None, graph_seed=cfg.graph_seed, run_seed=cfg.run_seed,
                    eligibility=0,
                ),
            )
            execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "censored")
            self.assertIsNotNone(meta["incumbent_label"])

    def test_cm_invalid_k_and_run_failed(self):
        cfg = _cm_config(cm_k=0)
        client = MockLLMClient(policy="always", rng=__import__("random").Random(0), options=CM_OPTIONS, always_label="Q")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                execute_cm_run(cfg, client, data_dir=Path(tmp) / "data", logs_dir=Path(tmp) / "logs")
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            bad_cfg = _cm_config(run_seed=8, phase2_horizon=20)
            bad_client = MockLLMClient(
                policy="always", rng=__import__("random").Random(0), options=list(bad_cfg.options), always_label="Z"
            )
            with self.assertRaises(RunFailedError):
                execute_cm_run(bad_cfg, bad_client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=SYNC_FAST_RETRY)
            paths = run_paths(
                data_dir, logs_dir, bad_cfg.model_shorthand, bad_cfg.topology,
                build_run_id(bad_cfg.model_shorthand, bad_cfg.topology, bad_cfg.run_seed, program=PROGRAM_CM, cm_k=bad_cfg.cm_k),
            )
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "failed")

    def test_prepared_invalid_incumbent_and_committed_label(self):
        with self.assertRaises(PreparedInitError):
            make_prepared_population(
                "complete", n=4, graph_seed=0, rewards=(-50, 100), options=["A", "B"],
                memory_size=5, incumbent_index=5, degree=4,
            )
        with self.assertRaises(PreparedInitError):
            committed_label(["A", "B", "C"], 0)
        sim = get_interaction_network("complete", n=4, graph_seed=0)
        sim[1]["committed_tag"] = True
        set_initial_state(sim, (-50, 100), ["A", "B"], memory_size=2, incumbent_index=0)
        sim[2]["my_history"] = ["B", "B"]
        from convention_topology.prepared import assert_prepared
        with self.assertRaises(PreparedInitError):
            assert_prepared(sim, ["A", "B"], memory_size=2, incumbent_index=0)


class AsyncRunCoverageTests(unittest.TestCase):
    def test_emergence_in_progress_resume_and_run_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config(run_seed=42, checkpoint_every=1, max_phase1_interactions=500, n=4)
            client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=__import__("random").Random(99), options=list(cfg.options))
            )
            paths = asyncio.run(
                execute_emergence_run_async(
                    cfg, client, data_dir=data_dir, logs_dir=logs_dir,
                    retry_policy=ASYNC_FAST_RETRY, console_progress=True,
                )
            )
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "completed")
            partial_meta = dict(meta)
            partial_meta["run_status"] = "in_progress"
            partial_meta["finished_at"] = None
            write_meta(paths.meta_path, partial_meta)
            resumed = asyncio.run(
                execute_emergence_run_async(
                    cfg, client, data_dir=data_dir, logs_dir=logs_dir,
                    retry_policy=ASYNC_FAST_RETRY, console_progress=False,
                )
            )
            self.assertEqual(read_meta(resumed.meta_path)["run_status"], "completed")

        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config(run_seed=1, checkpoint_every=1)
            failing = AsyncClientAdapter(
                MockLLMClient(
                    policy="always", rng=__import__("random").Random(0), options=list(cfg.options), always_label="Z"
                )
            )
            with self.assertRaises(RunFailedError):
                asyncio.run(
                    execute_emergence_run_async(
                        cfg, failing, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY,
                    )
                )
            paths = run_paths(
                data_dir, logs_dir, cfg.model_shorthand, cfg.topology,
                build_run_id(cfg.model_shorthand, cfg.topology, cfg.run_seed, program=PROGRAM_EMERGENCE),
            )
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "failed")

    def test_emergence_censored_resume_sets_incumbent_label_async(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _emergence_config(run_seed=88, max_phase1_interactions=72, n=4, checkpoint_every=1000)
            client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=__import__("random").Random(99), options=list(cfg.options))
            )
            paths = run_paths(
                data_dir, logs_dir, cfg.model_shorthand, cfg.topology,
                build_run_id(cfg.model_shorthand, cfg.topology, cfg.run_seed, program=PROGRAM_EMERGENCE),
            )
            paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            sim = get_interaction_network("complete", n=cfg.n, graph_seed=cfg.graph_seed)
            tracker = {"players": [], "answers": [["A", "B"]] * 72, "outcome": [0] * 72}
            convergence = {"converged_index": 72, "incumbent_label": None, "committed_to": None}
            save_run_pickle(paths.pickle_path, sim, tracker, convergence)
            write_meta(
                paths.meta_path,
                _meta_template(
                    paths.pickle_path.stem, program=PROGRAM_EMERGENCE, run_status="in_progress",
                    t_gate=None, finished_at=None, graph_seed=cfg.graph_seed, run_seed=cfg.run_seed,
                    eligibility=0,
                ),
            )
            asyncio.run(
                execute_emergence_run_async(
                    cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY,
                )
            )
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "censored")
            self.assertIsNotNone(meta["incumbent_label"])

    def test_cm_wrong_program_resume_and_run_failed(self):
        with self.assertRaises(ValueError):
            asyncio.run(
                execute_cm_run_async(
                    _emergence_config(), AsyncClientAdapter(MockLLMClient(policy="always", rng=__import__("random").Random(0), options=CM_OPTIONS)),
                    data_dir=Path("/tmp/d"), logs_dir=Path("/tmp/l"), retry_policy=ASYNC_FAST_RETRY,
                )
            )
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _cm_config(run_seed=2, phase2_horizon=80, checkpoint_every=1)
            client = AsyncClientAdapter(
                MockLLMClient(policy="imitate_modal", rng=__import__("random").Random(2), options=list(cfg.options))
            )
            paths = asyncio.run(
                execute_cm_run_async(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY)
            )
            first_calls = read_meta(paths.meta_path)["n_api_calls"]
            asyncio.run(
                execute_cm_run_async(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY)
            )
            self.assertEqual(read_meta(paths.meta_path)["n_api_calls"], first_calls)
            partial_meta = dict(read_meta(paths.meta_path))
            partial_meta["run_status"] = "in_progress"
            partial_meta["finished_at"] = None
            write_meta(paths.meta_path, partial_meta)
            resumed = asyncio.run(
                execute_cm_run_async(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY)
            )
            self.assertEqual(read_meta(resumed.meta_path)["run_status"], "completed")
            failing = AsyncClientAdapter(
                MockLLMClient(
                    policy="always", rng=__import__("random").Random(0), options=list(cfg.options), always_label="Z"
                )
            )
            cfg2 = _cm_config(run_seed=99, phase2_horizon=80)
            with self.assertRaises(RunFailedError):
                asyncio.run(
                    execute_cm_run_async(cfg2, failing, data_dir=data_dir, logs_dir=logs_dir, retry_policy=ASYNC_FAST_RETRY)
                )


class AsyncLlmCoverageTests(unittest.TestCase):
    def test_rate_limiter_waits_for_cooldown(self):
        limiter = RateLimiter(1)

        async def go():
            async with limiter:
                await limiter.pause(0.05)
            async with limiter:
                return "ok"

        self.assertEqual(asyncio.run(go()), "ok")

    def test_provider_pool_empty_raises(self):
        with self.assertRaises(ValueError):
            ProviderPool([], rate_limiter=RateLimiter(1))

    def test_provider_pool_all_endpoints_cooling(self):
        class Stub:
            model_id = "m"
            async def complete(self, system, user):
                return MagicMock(text="{'value': 'A'}")

        pool = ProviderPool([Stub()], rate_limiter=RateLimiter(0))
        pool._endpoints[0].cooldown_until = time.monotonic() + 100
        asyncio.run(pool.complete("s", "u"))

    def test_retry_after_invalid_hints(self):
        self.assertEqual(_retry_after_seconds(RateLimitedError("x", retry_after="bad")), 5.0)
        response = httpx.Response(429, headers={"retry-after": "bad"}, request=httpx.Request("POST", "http://x"))
        self.assertEqual(_retry_after_seconds(RateLimitError("429", response=response, body=None)), 5.0)

    def test_async_client_adapter_call_count(self):
        mock = MockLLMClient(policy="always", rng=__import__("random").Random(0), options=["A"], always_label="A")
        adapter = AsyncClientAdapter(mock)
        asyncio.run(adapter.complete("s", "u"))
        self.assertEqual(adapter.call_count, 1)


class LiveModuleCoverageTests(unittest.TestCase):
    def test_reader_scan_and_events_edge_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(scan_sidecars(root), [])
            bad_meta_dir = root / "runs" / "mock" / "complete"
            bad_meta_dir.mkdir(parents=True)
            (bad_meta_dir / "bad.meta.json").write_text("{")
            self.assertEqual(scan_sidecars(root), [])
            logs_sub = root / "logs-sub"
            logs_sub.mkdir(parents=True)
            df = events_dataframe(logs_sub, run_id="nope")
            self.assertTrue(df.empty)
            blank = logs_sub / "blank.events.jsonl"
            blank.write_text("\n\n")
            self.assertTrue(events_dataframe(logs_sub).empty)
            ev = root / "logs" / "rid.events.jsonl"
            ev.parent.mkdir(parents=True)
            ev.write_text(
                '\n{"type":"phase1_progress","t":1,"rolling_success":0.5,"dominant_share":0.6}\n'
            )
            self.assertEqual(len(read_events(ev)), 1)

    def test_cost_summary_missing_token_columns(self):
        events = pd.DataFrame([{"type": "token_usage", "model_id": "mock"}])
        summary = cost_summary(events)
        self.assertEqual(int(summary.iloc[0]["prompt_tokens"]), 0)

    def test_cost_summary_empty_usage_events(self):
        events = pd.DataFrame([{"type": "retry", "model_id": "mock"}])
        self.assertTrue(cost_summary(events).empty)

    def test_monitor_tables_and_main(self):
        empty = DashboardState(runs=pd.DataFrame(), events=pd.DataFrame())
        layout = build_layout(empty)
        self.assertIsNotNone(layout["runs"])
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            _run_small_mocked_batch(2, data_dir, logs_dir)
            state = load_dashboard_state(logs_dir, data_dir)
            runs = state.runs.copy()
            runs.loc[0, "run_status"] = "in_progress"
            state = DashboardState(runs=runs, events=state.events)
            build_layout(state)
            runs_progress = runs.copy()
            runs_progress.loc[0, "run_status"] = "in_progress"
            progress_events = state.events[state.events["run_id"] == runs.iloc[0]["run_id"]]
            build_layout(DashboardState(runs=runs_progress, events=progress_events))
            retry_only = pd.DataFrame([{"run_id": runs.iloc[0]["run_id"], "type": "retry"}])
            build_layout(DashboardState(runs=runs_progress, events=pd.DataFrame()))
            build_layout(DashboardState(runs=runs_progress, events=retry_only))
            monitor_main([
                "--watch", str(logs_dir), "--data", str(data_dir),
                "--max-refreshes", "2", "--refresh", "0.01",
            ])

    def test_web_frame_edge_cases(self):
        empty = DashboardState(runs=pd.DataFrame(), events=pd.DataFrame())
        self.assertTrue(eligibility_frame(empty).empty)
        self.assertTrue(trajectories_frame(empty).empty)
        self.assertTrue(dominant_share_frame(empty).empty)
        self.assertTrue(api_health_frame(empty).empty)
        runs_only = pd.DataFrame([
            {"run_id": "r1", "topology": "complete", "model_shorthand": "mock",
             "run_status": "in_progress", "eligibility": 0},
        ])
        self.assertTrue(eligibility_frame(DashboardState(runs=runs_only, events=pd.DataFrame())).empty)
        events = pd.DataFrame([
            {"run_id": "r1", "type": "retry"},
            {"run_id": "r1", "type": "phase1_progress", "t": 1, "rolling_success": 0.5, "dominant_share": 0.6},
        ])
        runs = pd.DataFrame([
            {"run_id": "r1", "topology": "complete", "model_shorthand": "mock",
             "run_status": "completed", "eligibility": 1},
        ])
        state = DashboardState(runs=runs, events=events)
        self.assertFalse(kpi_frame(state).empty)
        self.assertFalse(eligibility_frame(state).empty)
        self.assertFalse(trajectories_frame(state).empty)
        self.assertFalse(dominant_share_frame(state).empty)
        retries_no_error = pd.DataFrame([{"run_id": "r1", "type": "retry"}])
        self.assertFalse(api_health_frame(DashboardState(runs=runs, events=retries_no_error)).empty)
        dominant_no_runs = DashboardState(
            runs=pd.DataFrame(), events=events[events["type"] == "phase1_progress"]
        )
        self.assertFalse(dominant_share_frame(dominant_no_runs).empty)
        bad_events = pd.DataFrame([{"run_id": "r1", "type": "phase1_progress", "t": 1}])
        self.assertTrue(trajectories_frame(DashboardState(runs=runs, events=bad_events)).empty)
        no_dom = pd.DataFrame([{"run_id": "r1", "type": "phase1_progress", "t": 1, "rolling_success": 0.5}])
        self.assertTrue(dominant_share_frame(DashboardState(runs=runs, events=no_dom)).empty)
        self.assertTrue(cost_frame(empty).empty)

    def test_simulation_swap_committed_zero(self):
        sim = get_interaction_network("complete", n=4, graph_seed=0)
        self.assertEqual(swap_committed(sim, 0, __import__("random").Random(0)), [])


if __name__ == "__main__":
    unittest.main()
