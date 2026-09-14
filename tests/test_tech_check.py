from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from convention_topology.prompting import CANONICAL_TEMPLATE
from convention_topology.tech_check import DEFAULT_TECH_CHECK_N, evaluate_pass
import run_main


class TechCheckCliTests(unittest.TestCase):
    def test_tech_check_plus_task_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(
                [
                    "--tech-check",
                    "--model",
                    "mock",
                    "--task",
                    "emergence:mixing:0-1",
                ]
            )
        self.assertNotEqual(raised.exception.code, 0)

    def test_print_queue_plus_tech_check_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(
                [
                    "--print-queue",
                    "--tech-check",
                    "--task",
                    "emergence:mixing:0-1",
                ]
            )
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_n_without_tech_check_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(
                [
                    "--tech-check-n",
                    "3",
                    "--model",
                    "mock",
                    "--campaign",
                    "technical-smoke",
                    "--task",
                    "emergence:mixing:0-1",
                ]
            )
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_n_zero_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--tech-check", "--tech-check-n", "0"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_n_negative_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--tech-check", "--tech-check-n", "-1"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_n_not_integer_is_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--tech-check", "--tech-check-n", "nope"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_requires_model(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--tech-check"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_queue_campaign_and_model_without_task_still_errors(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--campaign", "technical-smoke"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_tech_check_refuses_experiment_before_http(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client"
            ) as client_factory:
                with self.assertRaises(SystemExit) as raised:
                    run_main.main(
                        [
                            "--model",
                            "mock",
                            "--tech-check",
                            "--campaign",
                            "experiment",
                            "--artifact-root",
                            str(root),
                        ]
                    )
            self.assertNotEqual(raised.exception.code, 0)
            client_factory.assert_not_called()
            self.assertFalse(list(root.iterdir()))

    def test_tech_check_defaults_campaign_without_config_yaml(self):
        captured = {}

        def fake_probe(config, model_spec, **kwargs):
            captured["campaign"] = config["run"]["campaign"]
            captured["n"] = kwargs["n"]
            captured["campaign_dir"] = kwargs["campaign_dir"]
            return 0

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "run_main.run_tech_check", side_effect=fake_probe
            ), patch("run_main.flatten_tasks") as flatten, patch(
                "run_main.run_slice_async"
            ) as slice_run, patch(
                "convention_topology.orchestration.execute_run_async"
            ) as execute_run, patch(
                "convention_topology.campaign.ensure_campaign_files"
            ) as ensure_files:
                code = run_main.main(
                    ["--model", "mock", "--tech-check", "--artifact-root", str(root)]
                )
        from convention_topology.config import load_config

        self.assertEqual(load_config()["run"]["campaign"], "experiment")
        self.assertEqual(code, 0)
        self.assertEqual(captured["campaign"], "tech-check")
        self.assertEqual(captured["n"], DEFAULT_TECH_CHECK_N)
        self.assertEqual(DEFAULT_TECH_CHECK_N, 100)
        self.assertEqual(Path(captured["campaign_dir"]), root)
        flatten.assert_not_called()
        slice_run.assert_not_called()
        execute_run.assert_not_called()
        ensure_files.assert_not_called()

    def test_tech_check_base_url_override(self):
        captured = {}

        def fake_probe(config, model_spec, **kwargs):
            captured["base_url"] = model_spec.base_url
            return 0

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "run_main.run_tech_check", side_effect=fake_probe
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--base-url",
                        "http://127.0.0.1:9/v1",
                        "--artifact-root",
                        str(root),
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured["base_url"], "http://127.0.0.1:9/v1")

    def test_tech_check_dirty_tree_exits_2(self):
        from convention_topology.git_guard import DirtyWorktreeError

        with patch("run_main.require_clean_worktree", side_effect=DirtyWorktreeError("dirty")):
            self.assertEqual(run_main.main(["--model", "mock", "--tech-check"]), 2)


class TechCheckProbeTests(unittest.TestCase):
    def test_mock_n_calls_log_and_exit_0(self):
        from convention_topology import tech_check as tech_mod

        real_build = tech_mod.build_client
        calls = {"n": 0}

        def wrap_client(*args, **kwargs):
            client = real_build(*args, **kwargs)
            inner = client.complete

            async def tracked(prompt, *, options=None):
                calls["n"] += 1
                return await inner(prompt, options=options)

            client.complete = tracked
            return client

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", side_effect=wrap_client
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "3",
                        "--campaign",
                        "probe-camp",
                        "--artifact-root",
                        str(root),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(calls["n"], 3)
            log_path = root / "tech-check.json"
            self.assertTrue(log_path.is_file())
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["n"], 3)
            self.assertEqual(payload["n_completed"], 3)
            self.assertEqual(payload["n_schema_valid"], 3)
            self.assertEqual(payload["share"], 1.0)
            self.assertFalse(payload["serve_startup"])
            self.assertEqual(payload["model"], "mock")
            self.assertTrue(payload["passed"])
            self.assertFalse(list(root.rglob("*.pkl")))
            self.assertFalse(list(root.rglob("*.meta.json")))
            self.assertFalse(list(root.rglob("*.events.jsonl")))
            self.assertFalse(list(root.rglob("*.live.json")))
            self.assertFalse((root / "label_pool.json").exists())
            self.assertFalse((root / "graphs.json").exists())
            self.assertFalse((root / "config.snapshot.yaml").exists())

    def test_mock_client_json_schema_fixture_prompt_reused_options(self):
        from convention_topology import tech_check as tech_mod
        from convention_topology.config import load_config
        from convention_topology.llm import AsyncClientAdapter, MockLLMClient
        from convention_topology.persistence import campaign_root
        from convention_topology.pool import draw_pool, options_for_program

        real_build = tech_mod.build_client
        seen = {"options": [], "json_schema": None, "inner": None, "prompt": None}

        def wrap_client(*args, **kwargs):
            seen["json_schema"] = kwargs.get("json_schema")
            client = real_build(*args, **kwargs)
            seen["inner"] = client.inner
            inner = client.complete

            async def tracked(prompt, *, options=None):
                if seen["prompt"] is None:
                    seen["prompt"] = prompt
                seen["options"].append(list(options or []))
                return await inner(prompt, options=options)

            client.complete = tracked
            self.assertIsInstance(client, AsyncClientAdapter)
            return client

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", side_effect=wrap_client
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "3",
                        "--artifact-root",
                        str(root),
                    ]
                )
        self.assertEqual(code, 0)
        self.assertTrue(seen["json_schema"])
        self.assertIsInstance(seen["inner"], MockLLMClient)
        self.assertEqual(len(seen["options"]), 3)
        self.assertEqual(seen["options"][0], seen["options"][1])
        self.assertEqual(seen["options"][1], seen["options"][2])
        config = load_config()
        expected = options_for_program(
            draw_pool(
                seed=int(config["pool"]["seed"]),
                string_length=int(config["protocol"]["string_length"]),
            ),
            "emergence",
        )
        self.assertEqual(set(seen["options"][0]), set(expected))
        prompt = seen["prompt"]
        self.assertNotIn("This is the history of choices", prompt)
        self.assertIn("It is now round 1.", prompt)
        self.assertIn("+100 points", prompt)
        self.assertIn("-50 points", prompt)
        self.assertEqual(
            campaign_root(None, "tech-check", Path("/repo")),
            Path("/repo") / "data" / "runs" / "tech-check",
        )

    def test_prompt_is_naming_game_json_enum(self):
        seen = {}

        real_build = None

        def wrap_client(*args, **kwargs):
            client = real_build(*args, **kwargs)
            inner_complete = client.complete

            async def tracked(prompt, *, options=None):
                seen["prompt"] = prompt
                seen["options"] = list(options or [])
                return await inner_complete(prompt, options=options)

            client.complete = tracked
            return client

        from convention_topology import tech_check as tech_mod

        real_build = tech_mod.build_client
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", side_effect=wrap_client
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "1",
                        "--artifact-root",
                        str(root),
                    ]
                )
        self.assertEqual(code, 0)
        self.assertIn("Return exactly one JSON object", seen["prompt"])
        self.assertNotIn("hello", seen["prompt"].lower())
        self.assertIn("{options}", CANONICAL_TEMPLATE)

    def test_share_below_bar_is_nonzero(self):
        from convention_topology.llm import LLMResponse

        class BadClient:
            async def complete(self, prompt, *, options=None):
                return LLMResponse(
                    text="not-json",
                    usage={},
                    model_id="mock",
                )

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", return_value=BadClient()
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "3",
                        "--artifact-root",
                        str(root),
                    ]
                )
            self.assertNotEqual(code, 0)
            payload = json.loads((root / "tech-check.json").read_text(encoding="utf-8"))
            self.assertLess(payload["share"], 0.95)
            self.assertFalse(payload["passed"])

    def test_serve_startup_is_nonzero(self):
        class DeadClient:
            async def complete(self, prompt, *, options=None):
                raise ConnectionError("unreachable base-url")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", return_value=DeadClient()
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "3",
                        "--artifact-root",
                        str(root),
                    ]
                )
            self.assertNotEqual(code, 0)
            payload = json.loads((root / "tech-check.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["serve_startup"])
            self.assertFalse(payload["passed"])

    def test_zero_completed_is_nonzero(self):
        class EmptyClient:
            async def complete(self, prompt, *, options=None):
                raise RuntimeError("no completion")

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch(
                "convention_topology.tech_check.build_client", return_value=EmptyClient()
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--tech-check",
                        "--tech-check-n",
                        "3",
                        "--artifact-root",
                        str(root),
                    ]
                )
            self.assertNotEqual(code, 0)
            payload = json.loads((root / "tech-check.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["n_completed"], 0)
            self.assertEqual(payload["share"], 0)
            self.assertFalse(payload["passed"])

    def test_evaluate_pass_bar(self):
        share, passed = evaluate_pass(n_completed=100, n_schema_valid=95, serve_startup=False)
        self.assertEqual(share, 0.95)
        self.assertTrue(passed)
        share, passed = evaluate_pass(n_completed=100, n_schema_valid=94, serve_startup=False)
        self.assertFalse(passed)
        share, passed = evaluate_pass(n_completed=0, n_schema_valid=0, serve_startup=False)
        self.assertEqual(share, 0.0)
        self.assertFalse(passed)
        _, passed = evaluate_pass(n_completed=10, n_schema_valid=10, serve_startup=True)
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
