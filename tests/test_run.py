from __future__ import annotations

import asyncio
import json
import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from convention_topology.campaign import ensure_campaign_files
from convention_topology.config import apply_diag_protocol, load_config, resolve_model
from convention_topology.json_output import ParseError
from convention_topology.llm import AsyncClientAdapter, MockLLMClient, RunFailedError
from convention_topology.persistence import SIDECAR_FIELDS, read_events, read_meta, run_paths
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    StopRequested,
    build_run_config,
    execute_run,
    execute_run_async,
    job_forensics,
)
from convention_topology.seeds import environment_seed, model_seed


def _cfg(program: str, tmp: Path, **overrides):
    config = load_config()
    files = ensure_campaign_files(tmp, config)
    spec = resolve_model(config, "mock")
    cfg = build_run_config(
        config,
        spec,
        program=program,
        topology="mixing",
        seed_index=0,
        cm_k=None if program == PROGRAM_EMERGENCE else 2,
        pool_labels=files["pool"]["labels"],
        pool_sha256=files["pool"]["sha256"],
        code_commit="test",
        artifact_root=str(tmp),
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg, files


class RecordingTests(unittest.TestCase):
    def test_mock_cm_writes_three_artifacts_and_campaign_root(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _files = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=2, memory_size=12)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            self.assertTrue(paths.pickle_path.exists())
            self.assertTrue(paths.meta_path.exists())
            self.assertTrue(paths.events_path.exists())
            self.assertTrue((root / "label_pool.json").exists())
            self.assertTrue((root / "graphs.json").exists())
            self.assertTrue((root / "config.snapshot.yaml").exists())
            meta = read_meta(paths.meta_path)
            for key in ("run_id", "campaign", "N", "H", "label_pool", "sampling_plan", "started_at"):
                self.assertIn(key, meta)
                self.assertIsNotNone(meta[key])
            self.assertEqual(meta["sampling_plan"], "fixed_attempted")
            self.assertIsNone(meta["gpu_ids"])
            self.assertIsNone(meta["gpu_type"])
            self.assertIsNone(meta["vllm_version"])
            self.assertEqual(set(SIDECAR_FIELDS), set(meta))
            self.assertNotIn("eligibility", meta)
            events = read_events(paths.events_path)
            types = {row["record_type"] for row in events}
            self.assertIn("run_segment_start", types)
            self.assertIn("prepared_state", types)
            self.assertIn("interaction", types)
            for row in events:
                if row["record_type"] == "interaction":
                    self.assertEqual(row["option_order_p1"], row["option_order_p2"])
            prepared = next(row for row in events if row["record_type"] == "prepared_state")
            first_ix = next(row for row in events if row["record_type"] == "interaction")
            self.assertLess(
                events.index(prepared),
                events.index(first_ix),
            )
            self.assertTrue(meta["prepared_state_valid"])
            self.assertEqual(meta["t_cm_start"], 0)

    def test_campaign_snapshot_ignores_ephemeral_serve_port(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = load_config()
            first["serve"]["base_url"] = "http://127.0.0.1:45167/v1"
            ensure_campaign_files(root, first)
            snap_path = root / "config.snapshot.yaml"
            snap = yaml.safe_load(snap_path.read_text(encoding="utf-8"))
            self.assertEqual(snap["serve"]["base_url"], "http://127.0.0.1:8000/v1")
            snap["serve"]["base_url"] = "http://127.0.0.1:45167/v1"
            snap_path.write_text(yaml.safe_dump(snap, sort_keys=True), encoding="utf-8")
            second = load_config()
            second["serve"]["base_url"] = "http://127.0.0.1:41222/v1"
            ensure_campaign_files(root, second)

    def test_cm_turns_do_not_http(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, cm_k=8, phase2_horizon=3, memory_size=12)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(client.call_count, 0)

    def test_decision_budget_exhausts_without_committing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, cm_k=2, phase2_horizon=1, retry_max_attempts=3)
            client = MockLLMClient(
                policy="scripted",
                rng=random.Random(0),
                options=list(cfg.options),
                scripted_responses=["not-json", "not-json", "not-json", "not-json"],
            )
            with self.assertRaises(RunFailedError) as ctx:
                execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(ctx.exception.error_class, "attempts_exhausted")
            events = read_events(next(root.joinpath("runs").rglob("*.events.jsonl")))
            attempts = [row for row in events if row["record_type"] == "llm_attempt"]
            self.assertGreaterEqual(len(attempts), 3)
            self.assertLessEqual(len(attempts), 6)
            self.assertFalse(any(row["record_type"] == "interaction" for row in events))
            meta = read_meta(next(root.joinpath("runs").rglob("*.meta.json")))
            self.assertGreaterEqual(meta["n_retries"], 3)
            self.assertLessEqual(meta["n_retries"], 6)
            for row in attempts:
                self.assertIsNotNone(row["prompt_sha256"])
                self.assertTrue(row["t_start"])
                self.assertTrue(row["t_end"])
                self.assertEqual(row["temperature"], cfg.temperature)
                self.assertEqual(row["max_tokens"], cfg.max_tokens)

    def test_serve_down_does_not_consume_decision_budget(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_CM,
                root,
                n=8,
                cm_k=2,
                phase2_horizon=1,
                provider="openai_compat",
                endpoint_base_url="http://127.0.0.1:9/v1",
                serve_wait_timeout=0.05,
            )
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            health_calls = {"n": 0}

            def health():
                health_calls["n"] += 1
                return False

            with self.assertRaises(RunFailedError) as ctx:
                execute_run(cfg, client, campaign_dir=root, health=health, sleep=_short_sleep)
            self.assertEqual(ctx.exception.error_class, "serve_startup")
            events = read_events(next(root.joinpath("runs").rglob("*.events.jsonl")))
            transport = [row for row in events if row.get("error_class") == "transport"]
            self.assertGreaterEqual(len(transport), 1)
            self.assertEqual(client.call_count, 0)
            meta = read_meta(next(root.joinpath("runs").rglob("*.meta.json")))
            self.assertGreater(meta["wait_on_model_ms"], 0)
            self.assertEqual(meta["n_retries"], 0)

    def test_attempt_clocks_stamp_around_complete(self):
        import time as time_mod

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=1)
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            marks = []

            class SlowClient:
                def complete(self, prompt, *, options):
                    marks.append("enter")
                    time_mod.sleep(0.01)
                    result = inner.complete(prompt, options=options)
                    marks.append("leave")
                    return result

            paths = execute_run(cfg, SlowClient(), campaign_dir=root)
            events = read_events(paths.events_path)
            attempts = [row for row in events if row["record_type"] == "llm_attempt"]
            self.assertGreaterEqual(len(attempts), 1)
            self.assertEqual(marks, ["enter", "leave"] * len(attempts))
            for row in attempts:
                self.assertIsNotNone(row["prompt_sha256"])
                self.assertEqual(len(row["prompt_sha256"]), 64)
                self.assertTrue(row["t_start"])
                self.assertTrue(row["t_end"])
                self.assertGreaterEqual(row["duration_ms"], 10)

    def test_emergence_gate_and_sidecar_window(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_EMERGENCE, root, n=48, gate_window=144)
            client = MockLLMClient(
                policy="imitate_modal",
                rng=random.Random(0),
                options=list(cfg.options),
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["gate_window"], 144)
            self.assertEqual(meta["N"], 48)
            self.assertIn(meta["run_status"], {"completed", "censored"})
            if meta["run_status"] == "completed":
                self.assertGreaterEqual(meta["t_gate"], 144)
                self.assertTrue(meta["gate_passed"])

    def test_diag_option_match_letter_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config()
            config["run"]["campaign"] = "diag-ashery-parse-mock"
            apply_diag_protocol(
                config,
                memory_h=5,
                pool_kind="letters",
                cap_phase1=400,
                population_n=24,
                decode="parse",
            )
            files = ensure_campaign_files(root, config)
            spec = resolve_model(config, "mock")
            cfg = build_run_config(
                config,
                spec,
                program=PROGRAM_EMERGENCE,
                topology="mixing",
                seed_index=0,
                cm_k=None,
                pool_labels=files["pool"]["labels"],
                pool_sha256=files["pool"]["sha256"],
                code_commit="test",
                artifact_root=str(root),
            )
            cfg.max_phase1_interactions = 1
            self.assertEqual(cfg.n, 24)
            self.assertEqual(cfg.gate_window, 72)
            self.assertFalse(cfg.json_schema)
            self.assertEqual(cfg.options[0], "Q")
            client = MockLLMClient(
                policy="scripted",
                rng=random.Random(0),
                options=list(cfg.options),
                scripted_responses=["I choose Q.", "Player uses Q."],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["N"], 24)
            self.assertEqual(meta["H"], 5)
            self.assertEqual(meta["response_format"], "option_match")
            self.assertFalse(meta["json_schema"])
            self.assertEqual(meta["n_interactions"], 1)
            events = read_events(paths.events_path)
            attempts = [row for row in events if row["record_type"] == "llm_attempt"]
            self.assertEqual(len(attempts), 2)
            self.assertTrue(all(row["parse_method"] == "option_match" for row in attempts))
            self.assertEqual({row["enum_label"] for row in attempts}, {"Q"})

    def test_counted_path_keeps_json_schema_and_rejects_free_text(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_EMERGENCE, root)
            self.assertTrue(cfg.json_schema)
            self.assertEqual(cfg.n, 48)
            self.assertEqual(cfg.gate_window, 144)
            cfg.max_phase1_interactions = 1
            client = MockLLMClient(
                policy="scripted",
                rng=random.Random(0),
                options=list(cfg.options),
                scripted_responses=[f"I choose {cfg.options[0]}."],
            )
            with self.assertRaises(RunFailedError):
                execute_run(cfg, client, campaign_dir=root)


async def _instant(_delay):
    return None


async def _short_sleep(delay):
    import asyncio

    await asyncio.sleep(min(float(delay), 0.02))


class ResumeTests(unittest.TestCase):
    def test_completed_skips_and_failed_is_kept(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=2)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(1),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            first = read_meta(paths.meta_path)
            execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(read_meta(paths.meta_path)["n_interactions"], first["n_interactions"])

            fail_cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=1, seed_index=1)
            bad = MockLLMClient(
                policy="scripted",
                rng=random.Random(0),
                options=list(fail_cfg.options),
                scripted_responses=["bad", "bad", "bad"],
            )
            with self.assertRaises(RunFailedError):
                execute_run(fail_cfg, bad, campaign_dir=root)
            failed_meta = read_meta(next(root.joinpath("runs").rglob("*s01*.meta.json")))
            self.assertEqual(failed_meta["run_status"], "failed")
            execute_run(fail_cfg, client, campaign_dir=root)
            self.assertEqual(read_meta(next(root.joinpath("runs").rglob("*s01*.meta.json")))["run_status"], "failed")

    def test_censored_skips(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=2)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = dict(read_meta(paths.meta_path))
            meta["run_status"] = "censored"
            paths.meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "censored")

    def test_in_progress_continues(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=4)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            seen = {"n": 0}

            def hook(kind: str) -> None:
                if kind == "after_interaction":
                    seen["n"] += 1
                    if seen["n"] == 1:
                        raise StopRequested("killed")

            paths = execute_run(cfg, client, campaign_dir=root, on_stop=hook)
            meta = dict(read_meta(paths.meta_path))
            meta["run_status"] = "in_progress"
            meta["stop_reason"] = None
            paths.meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "completed")

    def test_resume_mismatches_fail_config(self):
        cases = (
            ("prompt_template_hash", "deadbeef"),
            ("pool_sha256", "deadbeef"),
            ("model_revision", "other-revision"),
            ("protocol_fingerprint", "deadbeef"),
        )
        for attr, value in cases:
            with self.subTest(attr=attr):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=1)
                    client = MockLLMClient(
                        policy="always",
                        rng=random.Random(0),
                        options=list(cfg.options),
                        always_label=cfg.options[0],
                    )
                    paths = execute_run(cfg, client, campaign_dir=root)
                    meta = dict(read_meta(paths.meta_path))
                    meta["run_status"] = "interrupted"
                    meta["finished_at"] = None
                    paths.meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
                    setattr(cfg, attr, value)
                    with self.assertRaises(RunFailedError) as ctx:
                        execute_run(cfg, client, campaign_dir=root)
                    self.assertEqual(ctx.exception.error_class, "config")
                    self.assertTrue(paths.pickle_path.exists())

    def test_graph_hash_mismatch_fails_config(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=1)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = dict(read_meta(paths.meta_path))
            meta["run_status"] = "interrupted"
            meta["finished_at"] = None
            meta["adjacency_hash"] = "deadbeefdeadbeef"
            paths.meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            with self.assertRaises(RunFailedError) as ctx:
                execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(ctx.exception.error_class, "config")

    def test_truncated_jsonl_last_line_dropped(self):
        from convention_topology.persistence import read_events

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"record_type":"interaction","t":1}\n{"record_type":"interaction","t":2')
            rows = read_events(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["t"], 1)

    def test_fingerprint_mismatch_fails_config(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=1)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = dict(read_meta(paths.meta_path))
            meta["run_status"] = "interrupted"
            meta["finished_at"] = None
            paths.meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            cfg.protocol_fingerprint = "deadbeef"
            with self.assertRaises(RunFailedError) as ctx:
                execute_run(cfg, client, campaign_dir=root)
            self.assertEqual(ctx.exception.error_class, "config")
            self.assertTrue(paths.pickle_path.exists())

    def test_interrupted_continues(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=4)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            seen = {"n": 0}

            def hook(kind: str) -> None:
                if kind == "after_interaction":
                    seen["n"] += 1
                    if seen["n"] == 1:
                        raise StopRequested("killed")

            paths = execute_run(cfg, client, campaign_dir=root, on_stop=hook)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "interrupted")
            self.assertEqual(meta["stop_reason"], "killed")
            execute_run(cfg, client, campaign_dir=root)
            done = read_meta(paths.meta_path)
            self.assertEqual(done["run_status"], "completed")
            events = read_events(paths.events_path)
            ts = [row["t"] for row in events if row["record_type"] == "interaction"]
            self.assertEqual(ts, list(range(1, len(ts) + 1)))

    def test_injected_stop_after_attempt_does_not_duplicate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, cm_k=2, phase2_horizon=3)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            flagged = {"stop": False}

            def hook(kind: str) -> None:
                if kind == "after_attempt" and not flagged["stop"]:
                    flagged["stop"] = True
                    raise StopRequested("killed")

            paths = execute_run(cfg, client, campaign_dir=root, on_stop=hook)
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "interrupted")
            execute_run(cfg, client, campaign_dir=root)
            events = read_events(paths.events_path)
            interactions = [row for row in events if row["record_type"] == "interaction"]
            ts = [row["t"] for row in interactions]
            self.assertEqual(ts, sorted(set(ts)))

    def test_injected_stop_after_remaining_boundaries(self):
        for kind in ("after_interaction", "after_pickle", "after_sidecar"):
            with self.subTest(kind=kind):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    cfg, _ = _cfg(PROGRAM_CM, root, n=8, cm_k=2, phase2_horizon=3)
                    client = MockLLMClient(
                        policy="always",
                        rng=random.Random(0),
                        options=list(cfg.options),
                        always_label=cfg.options[0],
                    )
                    seen = {"n": 0}

                    def hook(name: str) -> None:
                        if name != kind:
                            return
                        seen["n"] += 1
                        raise StopRequested("killed")

                    paths = execute_run(cfg, client, campaign_dir=root, on_stop=hook)
                    self.assertEqual(read_meta(paths.meta_path)["run_status"], "interrupted")
                    execute_run(cfg, client, campaign_dir=root)
                    events = read_events(paths.events_path)
                    ts = [row["t"] for row in events if row["record_type"] == "interaction"]
                    self.assertEqual(ts, sorted(set(ts)))
                    self.assertEqual(ts, list(range(1, len(ts) + 1)))

    def test_sigterm_handler_is_process_wide(self):
        import signal

        from convention_topology import run as run_mod

        prev_term = signal.getsignal(signal.SIGTERM)
        prev_int = signal.getsignal(signal.SIGINT)
        try:
            run_mod._PROCESS_STOP["reason"] = None
            run_mod._SIGTERM_INSTALLED = False
            run_mod.install_process_sigterm()
            first = signal.getsignal(signal.SIGTERM)
            run_mod.install_process_sigterm()
            self.assertIs(signal.getsignal(signal.SIGTERM), first)
            first(signal.SIGTERM, None)
            self.assertEqual(run_mod.process_stop_reason(), "killed")
        finally:
            signal.signal(signal.SIGTERM, prev_term)
            signal.signal(signal.SIGINT, prev_int)
            run_mod._PROCESS_STOP["reason"] = None
            run_mod._SIGTERM_INSTALLED = False

    def test_jsonl_ahead_replay_advances_rng(self):
        from convention_topology.run import _init_state, _pair, _replay_interactions
        from convention_topology.tracker import update_dict, update_tracker

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=3)
            control = _init_state(cfg)
            behind = _init_state(cfg)
            records = []
            for t in range(1, 4):
                p1, p2 = _pair(control.simulation, control.rng_pairing)
                order = list(cfg.options)
                control.rng_option.shuffle(order)
                a1 = a2 = cfg.options[0]
                payoff = 100
                control.simulation[p1]["interactions"].append(p2)
                control.simulation[p2]["interactions"].append(p1)
                update_dict(control.simulation[p1], a1, a2, payoff)
                update_dict(control.simulation[p2], a2, a1, payoff)
                update_tracker(control.tracker, p1, p2, a1, a2, payoff)
                records.append(
                    {
                        "record_type": "interaction",
                        "t": t,
                        "p1": p1,
                        "p2": p2,
                        "label_p1": a1,
                        "label_p2": a2,
                        "payoff_p1": payoff,
                        "option_order_p1": list(order),
                    }
                )
                if t == 1:
                    p1b, p2b = _pair(behind.simulation, behind.rng_pairing)
                    order_b = list(cfg.options)
                    behind.rng_option.shuffle(order_b)
                    behind.simulation[p1b]["interactions"].append(p2b)
                    behind.simulation[p2b]["interactions"].append(p1b)
                    update_dict(behind.simulation[p1b], a1, a2, payoff)
                    update_dict(behind.simulation[p2b], a2, a1, payoff)
                    update_tracker(behind.tracker, p1b, p2b, a1, a2, payoff)
            self.assertEqual(len(behind.tracker["outcome"]), 1)
            _replay_interactions(behind, records, cfg.options)
            self.assertEqual(behind.rng_pairing.getstate(), control.rng_pairing.getstate())
            self.assertEqual(behind.rng_option.getstate(), control.rng_option.getstate())
            self.assertEqual(_pair(behind.simulation, behind.rng_pairing), _pair(control.simulation, control.rng_pairing))


class JobForensicsTests(unittest.TestCase):
    def test_laptop_env_stays_null(self):
        fields = job_forensics({"CUDA_VISIBLE_DEVICES": "0", "VLLM_VERSION": "0.8.0"})
        self.assertIsNone(fields["gpu_ids"])
        self.assertIsNone(fields["gpu_type"])
        self.assertIsNone(fields["vllm_version"])
        self.assertIsNone(fields["torch_version"])

    def test_slurm_env_fills_sidecar_fields(self):
        fields = job_forensics(
            {
                "SLURM_JOB_ID": "12345",
                "CUDA_VISIBLE_DEVICES": "0,1",
                "GPU_TYPE": "measured-after-fit",
                "VLLM_VERSION": "0.8.5",
                "TORCH_VERSION": "2.6.0",
            }
        )
        self.assertEqual(fields["gpu_ids"], ["0", "1"])
        self.assertEqual(fields["gpu_type"], "measured-after-fit")
        self.assertEqual(fields["vllm_version"], "0.8.5")
        self.assertEqual(fields["torch_version"], "2.6.0")

    def test_slurm_job_gpus_fallback(self):
        fields = job_forensics({"SLURM_JOB_ID": "99", "SLURM_JOB_GPUS": "3", "SLURM_GPU_TYPE": "from-slurm"})
        self.assertEqual(fields["gpu_ids"], ["3"])
        self.assertEqual(fields["gpu_type"], "from-slurm")

    def test_execute_run_writes_forensics_when_slurm_env_set(self):
        import os
        from unittest.mock import patch

        env = {
            **os.environ,
            "SLURM_JOB_ID": "555",
            "CUDA_VISIBLE_DEVICES": "2",
            "GPU_TYPE": "from-env",
            "VLLM_VERSION": "9.9.9",
            "TORCH_VERSION": "1.2.3",
        }
        with patch.dict(os.environ, env, clear=True), TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _files = _cfg(PROGRAM_CM, root, n=8, phase2_horizon=2, memory_size=12)
            client = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, client, campaign_dir=root)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["gpu_ids"], ["2"])
            self.assertEqual(meta["gpu_type"], "from-env")
            self.assertEqual(meta["vllm_version"], "9.9.9")
            self.assertEqual(meta["torch_version"], "1.2.3")


class DyadGatherTests(unittest.TestCase):
    def _overlap_client(self, inner, delay: float = 0.04):
        tracker = {"current": 0, "peak": 0}

        class DelayedClient:
            async def complete(self, prompt, *, options):
                tracker["current"] += 1
                tracker["peak"] = max(tracker["peak"], tracker["current"])
                try:
                    await asyncio.sleep(delay)
                    return inner.complete(prompt, options=options)
                finally:
                    tracker["current"] -= 1

        return DelayedClient(), tracker

    def test_both_attempts_precede_interaction_and_t_is_serial(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_EMERGENCE,
                root,
                n=8,
                max_phase1_interactions=2,
                gate_window=144,
            )
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            client, _tracker = self._overlap_client(inner)

            async def _run():
                return await execute_run_async(
                    cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(2)
                )

            paths = asyncio.run(_run())
            events = read_events(paths.events_path)
            interactions = [row for row in events if row["record_type"] == "interaction"]
            self.assertEqual([row["t"] for row in interactions], [1, 2])
            for ix in interactions:
                t = ix["t"]
                ix_pos = events.index(ix)
                attempts = [
                    row
                    for row in events[:ix_pos]
                    if row["record_type"] == "llm_attempt" and row["t"] == t
                ]
                self.assertEqual({row["agent_id"] for row in attempts}, {ix["p1"], ix["p2"]})
                later_attempts = [
                    row
                    for row in events[ix_pos + 1 :]
                    if row["record_type"] == "llm_attempt" and row["t"] == t
                ]
                self.assertEqual(later_attempts, [])

    def test_delayed_complete_overlaps_when_in_flight_limit_at_least_two(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_EMERGENCE,
                root,
                n=8,
                max_phase1_interactions=1,
                gate_window=144,
            )
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            client, tracker = self._overlap_client(inner)

            async def _run():
                return await execute_run_async(
                    cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(2)
                )

            asyncio.run(_run())
            self.assertGreaterEqual(tracker["peak"], 2)

    def test_in_flight_limit_one_serializes_dyad_calls(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_EMERGENCE,
                root,
                n=8,
                max_phase1_interactions=1,
                gate_window=144,
            )
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            client, tracker = self._overlap_client(inner)

            async def _run():
                return await execute_run_async(
                    cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(1)
                )

            asyncio.run(_run())
            self.assertEqual(tracker["peak"], 1)

    def test_mixed_cm_skips_http_for_committed_agent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(PROGRAM_CM, root, n=8, cm_k=4, phase2_horizon=4, memory_size=12)
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            client, tracker = self._overlap_client(inner)

            async def _run():
                return await execute_run_async(
                    cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(2)
                )

            paths = asyncio.run(_run())
            events = read_events(paths.events_path)
            mixed = [
                row
                for row in events
                if row["record_type"] == "interaction" and row["llm_call_p1"] != row["llm_call_p2"]
            ]
            self.assertTrue(mixed)
            attempts = [row for row in events if row["record_type"] == "llm_attempt"]
            self.assertEqual(inner.call_count, len(attempts))
            self.assertGreater(inner.call_count, 0)

    def test_in_flight_at_send_null_only_without_limiter(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_EMERGENCE,
                root,
                n=8,
                max_phase1_interactions=1,
                gate_window=144,
            )
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            paths = execute_run(cfg, inner, campaign_dir=root)
            attempts = [row for row in read_events(paths.events_path) if row["record_type"] == "llm_attempt"]
            self.assertTrue(attempts)
            for row in attempts:
                self.assertIsNone(row["in_flight_at_send"])

    def test_in_flight_at_send_is_int_with_limiter(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_EMERGENCE,
                root,
                n=8,
                max_phase1_interactions=1,
                gate_window=144,
            )
            cfg.in_flight_limit = 2
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )
            client, _tracker = self._overlap_client(inner)

            async def _run():
                return await execute_run_async(
                    cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(2)
                )

            paths = asyncio.run(_run())
            attempts = [row for row in read_events(paths.events_path) if row["record_type"] == "llm_attempt"]
            self.assertTrue(attempts)
            for row in attempts:
                self.assertIsInstance(row["in_flight_at_send"], int)
                self.assertGreaterEqual(row["in_flight_at_send"], 1)

    def test_transport_row_snapshots_occupancy_when_limiter_present(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg, _ = _cfg(
                PROGRAM_CM,
                root,
                n=8,
                cm_k=2,
                phase2_horizon=1,
                provider="openai_compat",
                endpoint_base_url="http://127.0.0.1:9/v1",
                serve_wait_timeout=0.05,
            )
            cfg.in_flight_limit = 4
            inner = MockLLMClient(
                policy="always",
                rng=random.Random(0),
                options=list(cfg.options),
                always_label=cfg.options[0],
            )

            async def _run():
                return await execute_run_async(
                    cfg,
                    AsyncClientAdapter(inner),
                    campaign_dir=root,
                    limiter=asyncio.Semaphore(4),
                    health=lambda: False,
                    sleep=_short_sleep,
                )

            with self.assertRaises(RunFailedError):
                asyncio.run(_run())
            events = read_events(next(root.joinpath("runs").rglob("*.events.jsonl")))
            transport = [row for row in events if row.get("error_class") == "transport"]
            self.assertTrue(transport)
            for row in transport:
                self.assertIsInstance(row["in_flight_at_send"], int)


if __name__ == "__main__":
    unittest.main()
