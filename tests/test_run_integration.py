from __future__ import annotations

import ast
import random
import re
import tempfile
import time
import unittest
from pathlib import Path

from convention_topology.config import config_hash
from convention_topology.llm import MockLLMClient, RetryPolicy, RunFailedError
from convention_topology.persistence import (
    META_FIELDS,
    EventWriter,
    PersistenceError,
    build_run_id,
    delete_run_artifacts,
    load_run_pickle,
    read_meta,
    run_paths,
    save_run_pickle,
    write_analysis_csv,
    write_analysis_json,
    write_meta,
)
from convention_topology.networks import get_interaction_network
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE, RunConfig, execute_cm_run, execute_emergence_run
from convention_topology.simulation import make_interaction_step, swap_committed
from convention_topology.tracker import update_dict

FAST_RETRY = RetryPolicy(sleep=lambda _: None)

EMERGENCE_OPTIONS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
CM_OPTIONS = ["Q", "M"]


def _make_emergence_config(**overrides) -> RunConfig:
    base = dict(
        program=PROGRAM_EMERGENCE,
        model_shorthand="mock",
        model_id="mock",
        endpoint_base_url="",
        topology="complete",
        cm_k=0,
        graph_seed=0,
        run_seed=0,
        config_hash="deadbeefdeadbeef",
        prompt_template_version="v1-ashery-chat-split",
        code_commit="testcommit",
        options=EMERGENCE_OPTIONS,
        n=4,
    )
    base.update(overrides)
    return RunConfig(**base)


def _make_cm_config(**overrides) -> RunConfig:
    base = dict(
        program=PROGRAM_CM,
        model_shorthand="mock",
        model_id="mock",
        endpoint_base_url="",
        topology="complete",
        cm_k=1,
        graph_seed=0,
        run_seed=0,
        config_hash="deadbeefdeadbeef",
        prompt_template_version="v1-ashery-chat-split",
        code_commit="testcommit",
        options=CM_OPTIONS,
        incumbent_index=0,
        n=4,
        phase2_horizon=100,
    )
    base.update(overrides)
    return RunConfig(**base)


class UpdateDictTests(unittest.TestCase):
    def test_score_and_histories_accumulate_in_order(self):
        player = {"my_history": [], "partner_history": [], "score": 0, "score_history": [], "outcome": []}
        update_dict(player, "A", "B", -50)
        update_dict(player, "A", "A", 100)
        self.assertEqual(player["my_history"], ["A", "A"])
        self.assertEqual(player["partner_history"], ["B", "A"])
        self.assertEqual(player["score"], 50)
        self.assertEqual(player["score_history"], [-50, 50])
        self.assertEqual(player["outcome"], [-50, 100])


class _OptionOrderCapturingClient:
    """Fake LLM client that always answers the first option and records the
    exact option order embedded in each system prompt (M1 shuffle tests)."""

    def __init__(self, first_option: str):
        self.first_option = first_option
        self.systems: list[str] = []

    def complete(self, system: str, user: str):
        from convention_topology.llm import LLMResponse

        self.systems.append(system)
        return LLMResponse(
            text=f"{{'value': '{self.first_option}'; 'reason': 'x'}}",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            model_id="fake",
        )


def _option_order_in_system(system: str, options: list[str]) -> list[str]:
    """Recover the shuffled option order embedded by `prompting.get_rules`."""
    match = re.search(r"following values: (\[.*?\])", system)
    assert match is not None
    return ast.literal_eval(match.group(1))


class InteractionStepTests(unittest.TestCase):
    def test_all_committed_phase2_makes_zero_client_calls(self):
        n = 24
        simulation = get_interaction_network("complete", n=n, graph_seed=1)
        rng = random.Random(0)
        swap_committed(simulation, n, rng)  # every agent committed
        client = MockLLMClient(policy="always", rng=random.Random(1), options=["A", "B"], always_label="A")
        step = make_interaction_step(
            simulation, client, 5, (-50, 100), ["A", "B"], rng, committed_to="A", retry_policy=FAST_RETRY
        )
        tracker = {"players": [], "answers": [], "outcome": []}
        for _ in range(20):
            step(tracker)
        self.assertEqual(client.call_count, 0)
        self.assertEqual(len(tracker["outcome"]), 20)

    def test_shared_shuffle_true_gives_both_players_the_same_option_order(self):
        # M1: Phase 2 (shared_shuffle=True) must reproduce Ashery committed()'s
        # semantics -- options shuffled once per interaction, shared by both players.
        options = ["A", "B", "C"]
        simulation = get_interaction_network("complete", n=8, graph_seed=1)
        rng = random.Random(0)
        client = _OptionOrderCapturingClient(first_option="A")
        step = make_interaction_step(
            simulation, client, 5, (-50, 100), options, rng,
            retry_policy=FAST_RETRY, shared_shuffle=True,
        )
        tracker = {"players": [], "answers": [], "outcome": []}
        for _ in range(15):
            step(tracker)

        # Every interaction contributes exactly two system prompts (both
        # players non-committed); each pair must show the identical order.
        self.assertEqual(len(client.systems), 30)
        for i in range(0, len(client.systems), 2):
            order_p1 = _option_order_in_system(client.systems[i], options)
            order_p2 = _option_order_in_system(client.systems[i + 1], options)
            self.assertEqual(order_p1, order_p2)

    def test_shared_shuffle_false_gives_players_independent_option_orders(self):
        # M1: Phase 1 (default shared_shuffle=False) must keep the per-agent
        # independent shuffle -- matches Ashery population().
        options = ["A", "B", "C"]
        simulation = get_interaction_network("complete", n=8, graph_seed=1)
        rng = random.Random(0)
        client = _OptionOrderCapturingClient(first_option="A")
        step = make_interaction_step(
            simulation, client, 5, (-50, 100), options, rng, retry_policy=FAST_RETRY,
        )
        tracker = {"players": [], "answers": [], "outcome": []}
        for _ in range(15):
            step(tracker)

        self.assertEqual(len(client.systems), 30)
        pairs = [
            (
                _option_order_in_system(client.systems[i], options),
                _option_order_in_system(client.systems[i + 1], options),
            )
            for i in range(0, len(client.systems), 2)
        ]
        # Independent per-agent draws: over 15 interactions with 3! = 6
        # possible orders, at least one pair almost surely differs.
        self.assertTrue(any(a != b for a, b in pairs))


class RunIdAndPathTests(unittest.TestCase):
    def test_build_run_id_emergence_format(self):
        self.assertEqual(
            build_run_id("llama31", "lattice", 42, program="emergence"),
            "llama31_lattice_emerg_s0042",
        )

    def test_build_run_id_cm_format(self):
        self.assertEqual(
            build_run_id("llama31", "lattice", 42, program="cm", cm_k=3),
            "llama31_lattice_k3_s0042",
        )

    def test_run_paths_auto_create_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            logs_dir = Path(tmp) / "logs"
            paths = run_paths(data_dir, logs_dir, "mock", "complete", "mock_complete_emerg_s0000")
            self.assertFalse(paths.pickle_path.parent.exists())
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(paths.pickle_path.parent.exists())
            self.assertTrue(paths.events_path.parent.exists())


class PickleRoundTripTests(unittest.TestCase):
    def test_round_trip_preserves_schema_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.pkl"
            simulation = {1: {"my_history": ["A"], "neighbours": [2]}}
            tracker = {"players": [[1, 2]], "answers": [["A", "A"]], "outcome": [1]}
            convergence = {"converged_index": 10, "committed_to": "B"}
            save_run_pickle(path, simulation, tracker, convergence)
            payload = load_run_pickle(path)
            self.assertEqual(payload["simulation"], simulation)
            self.assertEqual(payload["tracker"], tracker)
            self.assertEqual(payload["convergence"], convergence)

    def test_missing_pickle_raises_persistence_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PersistenceError):
                load_run_pickle(Path(tmp) / "missing.pkl")


class MetaSidecarTests(unittest.TestCase):
    def test_write_meta_requires_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.meta.json"
            with self.assertRaises(PersistenceError):
                write_meta(path, {"run_id": "x"})

    def test_write_then_read_meta_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.meta.json"
            metadata = {field: f"value-{field}" for field in META_FIELDS}
            write_meta(path, metadata)
            loaded = read_meta(path)
            self.assertEqual(loaded, metadata)


class AnalysisWriteHelpersTests(unittest.TestCase):
    """N1: analysis-output writes and run-artifact deletes route through persistence.py."""

    def test_write_analysis_json_round_trips(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outputs" / "h1.json"
            write_analysis_json(path, {"n": 3, "label": "confirmatory"})
            self.assertTrue(path.exists())
            with path.open() as handle:
                self.assertEqual(json.load(handle), {"n": 3, "label": "confirmatory"})

    def test_write_analysis_csv_round_trips(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outputs" / "eligibility.csv"
            table = pd.DataFrame([{"topology": "complete", "attempted": 12}])
            write_analysis_csv(path, table)
            self.assertTrue(path.exists())
            loaded = pd.read_csv(path)
            self.assertEqual(loaded.iloc[0]["topology"], "complete")
            self.assertEqual(loaded.iloc[0]["attempted"], 12)

    def test_delete_run_artifacts_removes_meta_and_pickle(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            paths = run_paths(data_dir, logs_dir, "mock", "complete", "mock_complete_emerg_s0000")
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.pickle_path.write_bytes(b"x")
            write_meta(paths.meta_path, {field: "x" for field in META_FIELDS})

            delete_run_artifacts(paths)

            self.assertFalse(paths.meta_path.exists())
            self.assertFalse(paths.pickle_path.exists())

    def test_delete_run_artifacts_is_missing_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            paths = run_paths(data_dir, logs_dir, "mock", "complete", "does_not_exist")
            delete_run_artifacts(paths)  # must not raise


class EventWriterTests(unittest.TestCase):
    def test_events_append_as_jsonl_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.events.jsonl"
            writer = EventWriter(path)
            writer.emit({"type": "phase1_progress", "t": 10})
            writer.emit({"type": "retry", "attempt": 2})
            writer.close()
            lines = path.read_text().strip().splitlines()
            self.assertEqual(len(lines), 2)
            import json

            self.assertEqual(json.loads(lines[0])["type"], "phase1_progress")
            self.assertEqual(json.loads(lines[1])["type"], "retry")


class ConfigHashTests(unittest.TestCase):
    def test_same_config_same_hash(self):
        cfg = {"topology": "complete", "cm_k": 1, "api_key_env": "SECRET_VAR"}
        self.assertEqual(config_hash(cfg), config_hash(dict(cfg)))

    def test_changed_param_changes_hash(self):
        cfg_a = {"topology": "complete", "cm_k": 1}
        cfg_b = {"topology": "complete", "cm_k": 2}
        self.assertNotEqual(config_hash(cfg_a), config_hash(cfg_b))

    def test_api_key_env_value_irrelevant_to_hash(self):
        cfg_a = {"topology": "complete", "api_key_env": "OPENROUTER_API_KEY"}
        cfg_b = {"topology": "complete", "api_key_env": "OPENAI_API_KEY"}
        self.assertEqual(config_hash(cfg_a), config_hash(cfg_b))


class EmergenceRunTests(unittest.TestCase):
    def test_mixing_emergence_completes_under_ten_seconds_with_full_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_emergence_config()
            client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            start = time.time()
            paths = execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            elapsed = time.time() - start

            self.assertLess(elapsed, 10.0)
            meta = read_meta(paths.meta_path)
            for field in META_FIELDS:
                self.assertIn(field, meta)
            self.assertEqual(meta["program"], "emergence")
            self.assertEqual(meta["init_mode"], "organic")
            self.assertEqual(meta["run_status"], "completed")
            self.assertEqual(meta["cm_k"], 0)
            self.assertIsNone(meta["committed_to"])
            self.assertIsNotNone(meta["t_gate"])
            self.assertIsNotNone(meta["incumbent_label"])
            self.assertTrue(paths.pickle_path.exists())
            self.assertTrue(paths.events_path.exists())

    def test_censored_path_with_random_policy_and_reduced_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_emergence_config(max_phase1_interactions=30, checkpoint_every=10)
            client = MockLLMClient(policy="random", rng=random.Random(7), options=list(cfg.options))
            paths = execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "censored")
            self.assertEqual(meta["eligibility"], 0)
            self.assertIsNone(meta["t_gate"])

    def test_failed_path_after_three_retries_on_malformed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_emergence_config()
            client = MockLLMClient(policy="always", rng=random.Random(0), options=list(cfg.options), always_label="Z")
            with self.assertRaises(RunFailedError):
                execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            paths = run_paths(
                data_dir,
                logs_dir,
                cfg.model_shorthand,
                cfg.topology,
                build_run_id(cfg.model_shorthand, cfg.topology, cfg.run_seed, program="emergence"),
            )
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["run_status"], "failed")
            self.assertIsNotNone(meta["finished_at"])

    def test_resume_from_checkpoint_does_not_replay_completed_phase1(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_emergence_config()
            client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            paths = execute_emergence_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            completed_payload = load_run_pickle(paths.pickle_path)
            completed_meta = read_meta(paths.meta_path)
            original_total = len(completed_payload["tracker"]["outcome"])
            original_calls = completed_meta["n_api_calls"]

            save_run_pickle(
                paths.pickle_path,
                completed_payload["simulation"],
                completed_payload["tracker"],
                completed_payload["convergence"],
            )
            resume_meta = dict(completed_meta)
            resume_meta["run_status"] = "in_progress"
            resume_meta["finished_at"] = None
            write_meta(paths.meta_path, resume_meta)

            resume_client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            resumed_paths = execute_emergence_run(
                cfg, resume_client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY
            )
            resumed_meta = read_meta(resumed_paths.meta_path)
            resumed_payload = load_run_pickle(resumed_paths.pickle_path)

            self.assertEqual(resumed_meta["run_status"], "completed")
            self.assertEqual(len(resumed_payload["tracker"]["outcome"]), original_total)
            self.assertLessEqual(resumed_meta["n_api_calls"], original_calls + 5)

    def test_one_emergence_run_per_topology(self):
        for topology in ("complete", "random_regular", "lattice"):
            with self.subTest(topology=topology):
                with tempfile.TemporaryDirectory() as tmp:
                    data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
                    cfg = _make_emergence_config(topology=topology, n=8)
                    client = MockLLMClient(policy="imitate_modal", rng=random.Random(3), options=list(cfg.options))
                    paths = execute_emergence_run(
                        cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY
                    )
                    meta = read_meta(paths.meta_path)
                    self.assertIn(meta["run_status"], ("completed", "censored"))
                    self.assertEqual(meta["topology"], topology)
                    self.assertEqual(meta["program"], "emergence")


class CMRunTests(unittest.TestCase):
    def test_prepared_cm_completes_with_fixed_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_cm_config(phase2_horizon=80)
            client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            paths = execute_cm_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            meta = read_meta(paths.meta_path)
            payload = load_run_pickle(paths.pickle_path)

            self.assertEqual(meta["program"], "cm")
            self.assertEqual(meta["init_mode"], "prepared")
            self.assertEqual(meta["run_status"], "completed")
            self.assertEqual(meta["t_gate"], 0)
            self.assertEqual(meta["incumbent_label"], "Q")
            self.assertEqual(meta["committed_to"], "M")
            self.assertEqual(meta["eligibility"], 1)
            self.assertEqual(len(payload["tracker"]["outcome"]), 80)
            committed = sum(1 for p in payload["simulation"].values() if p.get("committed_tag"))
            self.assertEqual(committed, 1)

    def test_resume_after_cm_start_does_not_re_swap_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_cm_config(cm_k=2, n=8, phase2_horizon=60)
            client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            paths = execute_cm_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            payload = load_run_pickle(paths.pickle_path)
            committed_before = sum(1 for p in payload["simulation"].values() if p.get("committed_tag"))
            self.assertEqual(committed_before, 2)

            meta = read_meta(paths.meta_path)
            meta["run_status"] = "in_progress"
            meta["finished_at"] = None
            write_meta(paths.meta_path, meta)
            # Truncate tracker to mid-horizon to force remaining Phase 2 work.
            mid = {k: v[:30] for k, v in payload["tracker"].items()}
            save_run_pickle(paths.pickle_path, payload["simulation"], mid, payload["convergence"])

            resume_client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            resumed_paths = execute_cm_run(
                cfg, resume_client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY
            )
            resumed_payload = load_run_pickle(resumed_paths.pickle_path)
            committed_after = sum(1 for p in resumed_payload["simulation"].values() if p.get("committed_tag"))
            self.assertEqual(committed_after, 2)
            self.assertEqual(len(resumed_payload["tracker"]["outcome"]), 60)

    def test_sidecar_incumbent_matches_prepared_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            cfg = _make_cm_config(phase2_horizon=40)
            client = MockLLMClient(policy="imitate_modal", rng=random.Random(99), options=list(cfg.options))
            paths = execute_cm_run(cfg, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=FAST_RETRY)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["incumbent_label"], "Q")
            self.assertEqual(meta["committed_to"], "M")
            self.assertEqual(meta["options"], ["Q", "M"])
            self.assertEqual(meta["incumbent_index"], 0)


if __name__ == "__main__":
    unittest.main()
