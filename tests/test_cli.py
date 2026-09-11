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

    def test_slurm_job_recipe_shape(self):
        from pathlib import Path

        job = (Path(__file__).resolve().parent.parent / "jobs" / "thesis_vllm.slurm").read_text(encoding="utf-8")
        self.assertIn('SCRATCH="/scratch/shared/${USER}"', job)
        self.assertIn('VENV="${SCRATCH}/venvs/thesis"', job)
        self.assertIn("${VENV}/bin/python", job)
        self.assertIn("run_main.py", job)
        self.assertNotIn("python3 run_main.py", job)
        self.assertIn("--dtype", job)
        self.assertIn("--max-model-len", job)
        self.assertIn("--max-num-seqs", job)
        self.assertIn("--tensor-parallel-size", job)
        self.assertIn('CAMPAIGN="${CAMPAIGN:-technical-smoke}"', job)
        self.assertIn('ARTIFACT_ROOT="${SCRATCH}/runs/${CAMPAIGN}"', job)
        self.assertIn('--campaign "${CAMPAIGN}"', job)
        self.assertIn("vLLM launch unset", job)
        self.assertIn("VLLM_MODULE", job)
        self.assertIn("VLLM_SIF", job)
        self.assertIn("VLLM_LAUNCH", job)
        self.assertIn("# #SBATCH -C", job)
        self.assertNotIn("GPU_MODEL:H200", job)
        self.assertNotIn("GPU_MODEL:A40", job)
        self.assertNotIn("HF_MODEL", job)
        self.assertIn("/usr/bin/python3 -m venv", job)
        self.assertIn("requirements.txt", job)
        self.assertIn("trap stop_vllm EXIT", job)
        self.assertIn("trap on_pretimeout USR1 TERM INT", job)
        self.assertIn("exit 0", job)
        self.assertIn("export VLLM_VERSION", job)
        self.assertIn('export GPU_TYPE="${GPU_TYPE:-${SLURM_GPU_TYPE:-}}"', job)
        self.assertIn("SLURM_GPU_TYPE", job)
        self.assertNotIn("nvidia-smi", job)
        self.assertNotIn("nvidia_smi", job)
        self.assertIn('SEED_TO:?', job)
        self.assertIn('TOPOLOGY:?', job)
        self.assertIn("# Wait until /v1/models answers", job)
        self.assertIn('url = os.environ["BASE_URL"] + "/models"', job)

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

    def test_run_main_campaign_reaches_campaign_root(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["campaign"] = config["run"]["campaign"]
            captured["campaign_dir"] = kwargs["campaign_dir"]
            return []

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("run_main.require_clean_worktree"), patch("run_main.run_slice_async", side_effect=fake_slice):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--program",
                        "emergence",
                        "--seed-from",
                        "0",
                        "--seed-to",
                        "0",
                        "--campaign",
                        "pilot-run",
                        "--artifact-root",
                        str(root),
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured["campaign"], "pilot-run")
        self.assertEqual(Path(captured["campaign_dir"]), root)

    def test_run_main_print_jobs_emits_hf_id_and_shorthand(self):
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            code = run_main.main(["--print-jobs"])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("llama4_scout", text)
        self.assertIn("meta-llama/Llama-4-Scout-17B-16E-Instruct", text)
        self.assertIn("model_id=", text)

    def test_run_one_refuses_dirty_tree(self):
        with patch("run_one.require_clean_worktree", side_effect=DirtyWorktreeError("dirty")):
            self.assertEqual(
                run_one.main(["--program", "emergence", "--model", "mock", "--topology", "mixing", "--seed-index", "0"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
