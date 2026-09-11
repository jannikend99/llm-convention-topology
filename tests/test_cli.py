from __future__ import annotations

import unittest
from unittest.mock import patch

from convention_topology.git_guard import DirtyWorktreeError, require_clean_worktree
import run_main
import run_one


class DirtyGitCliTests(unittest.TestCase):
    def test_require_clean_worktree_raises(self):
        with patch("convention_topology.git_guard.subprocess.check_output", side_effect=[" M foo.py\n", "abc123\n"]):
            with self.assertRaises(DirtyWorktreeError):
                require_clean_worktree()

    def test_run_main_slice_refuses_dirty_tree(self):
        with patch("run_main.require_clean_worktree", side_effect=DirtyWorktreeError("dirty")):
            self.assertEqual(run_main.main(["--model", "mock", "--program", "emergence", "--seed-from", "0", "--seed-to", "1"]), 2)

    def test_run_main_print_jobs_does_not_need_clean_tree(self):
        code = run_main.main(["--print-jobs"])
        self.assertEqual(code, 0)

    def test_counted_slice_installs_sigterm(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / "convention_topology" / "orchestration.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("install_sigterm=True", source)

    def test_slurm_passes_started_server_base_url(self):
        from pathlib import Path

        job = (Path(__file__).resolve().parent.parent / "jobs" / "thesis_vllm.slurm").read_text(encoding="utf-8")
        self.assertIn('--base-url "${BASE_URL}"', job)
        self.assertIn("export BASE_URL=", job)

    def test_run_main_cli_base_url_reaches_model_spec(self):
        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["url"] = model_spec.base_url
            return []

        with patch("run_main.require_clean_worktree"), patch("run_main.run_slice_async", side_effect=fake_slice):
            code = run_main.main(
                [
                    "--model",
                    "llama4_scout",
                    "--program",
                    "emergence",
                    "--seed-from",
                    "0",
                    "--seed-to",
                    "0",
                    "--base-url",
                    "http://127.0.0.1:12345/v1",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(captured["url"], "http://127.0.0.1:12345/v1")

    def test_run_one_refuses_dirty_tree(self):
        with patch("run_one.require_clean_worktree", side_effect=DirtyWorktreeError("dirty")):
            self.assertEqual(
                run_one.main(["--program", "emergence", "--model", "mock", "--topology", "mixing", "--seed-index", "0"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
