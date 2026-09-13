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
        self.assertEqual(source.count("install_process_sigterm()"), 1)
        self.assertNotIn("install_sigterm=True", source)
        skip_at = source.find('{"completed", "censored", "failed"}')
        slot_at = source.find("async with run_slots")
        self.assertGreater(skip_at, 0)
        self.assertGreater(slot_at, skip_at)

    def test_terminal_sidecar_does_not_call_execute_run(self):
        import asyncio
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock, patch

        from convention_topology.campaign import ensure_campaign_files
        from convention_topology.config import load_config, resolve_model
        from convention_topology.orchestration import run_slice_async
        from convention_topology.persistence import build_run_id, encode_run_key, run_paths
        from convention_topology.run import build_run_config

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_config()
            files = ensure_campaign_files(root, config)
            spec = resolve_model(config, "mock")
            cfg = build_run_config(
                config,
                spec,
                program="emergence",
                topology="mixing",
                seed_index=0,
                cm_k=None,
                pool_labels=files["pool"]["labels"],
                pool_sha256=files["pool"]["sha256"],
                code_commit="test",
                artifact_root=str(root),
            )
            run_key = encode_run_key(
                campaign=cfg.campaign,
                program=cfg.program,
                model_id=cfg.model_id,
                topology=cfg.topology,
                cm_k=cfg.cm_k,
                seed_index=cfg.seed_index,
            )
            paths = run_paths(root, cfg.model_shorthand, cfg.topology, build_run_id(run_key))
            paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
            paths.meta_path.write_text(json.dumps({"run_status": "completed"}), encoding="utf-8")
            with patch(
                "convention_topology.orchestration.execute_run_async", new_callable=AsyncMock
            ) as mocked:
                statuses = asyncio.run(
                    run_slice_async(
                        config,
                        spec,
                        program="emergence",
                        campaign_dir=root,
                        topology="mixing",
                        seed_from=0,
                        seed_to=1,
                    )
                )
            mocked.assert_not_called()
            self.assertEqual(statuses, ["completed"])

    def test_censored_and_failed_sidecars_skip_execute_run(self):
        import asyncio
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import AsyncMock, patch

        from convention_topology.campaign import ensure_campaign_files
        from convention_topology.config import load_config, resolve_model
        from convention_topology.orchestration import run_slice_async
        from convention_topology.persistence import build_run_id, encode_run_key, run_paths
        from convention_topology.run import build_run_config

        for terminal in ("censored", "failed"):
            with self.subTest(status=terminal):
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    config = load_config()
                    files = ensure_campaign_files(root, config)
                    spec = resolve_model(config, "mock")
                    cfg = build_run_config(
                        config,
                        spec,
                        program="emergence",
                        topology="mixing",
                        seed_index=0,
                        cm_k=None,
                        pool_labels=files["pool"]["labels"],
                        pool_sha256=files["pool"]["sha256"],
                        code_commit="test",
                        artifact_root=str(root),
                    )
                    run_key = encode_run_key(
                        campaign=cfg.campaign,
                        program=cfg.program,
                        model_id=cfg.model_id,
                        topology=cfg.topology,
                        cm_k=cfg.cm_k,
                        seed_index=cfg.seed_index,
                    )
                    paths = run_paths(root, cfg.model_shorthand, cfg.topology, build_run_id(run_key))
                    paths.meta_path.parent.mkdir(parents=True, exist_ok=True)
                    paths.meta_path.write_text(json.dumps({"run_status": terminal}), encoding="utf-8")
                    with patch(
                        "convention_topology.orchestration.execute_run_async", new_callable=AsyncMock
                    ) as mocked:
                        statuses = asyncio.run(
                            run_slice_async(
                                config,
                                spec,
                                program="emergence",
                                campaign_dir=root,
                                topology="mixing",
                                seed_from=0,
                                seed_to=1,
                            )
                        )
                    mocked.assert_not_called()
                    self.assertEqual(statuses, [terminal])

    def test_max_concurrent_runs_caps_and_two_cells_overlap(self):
        import asyncio
        from dataclasses import replace
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from convention_topology.config import load_config, resolve_model
        from convention_topology.orchestration import run_slice_async

        async def _peak_for(limit: int) -> int:
            tracker = {"current": 0, "peak": 0}

            async def delayed_execute(*_args, **_kwargs):
                tracker["current"] += 1
                tracker["peak"] = max(tracker["peak"], tracker["current"])
                try:
                    await asyncio.sleep(0.05)
                finally:
                    tracker["current"] -= 1

            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                config = load_config()
                spec = replace(resolve_model(config, "mock"), max_concurrent_runs=limit)
                with patch("convention_topology.orchestration.execute_run_async", side_effect=delayed_execute):
                    statuses = await run_slice_async(
                        config,
                        spec,
                        program="emergence",
                        campaign_dir=root,
                        topology="mixing",
                        seed_from=0,
                        seed_to=2,
                    )
            self.assertEqual(statuses, ["failed", "failed"])
            return tracker["peak"]

        self.assertEqual(asyncio.run(_peak_for(1)), 1)
        self.assertEqual(asyncio.run(_peak_for(2)), 2)

    def test_slice_logs_effective_serve_triple(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / "convention_topology" / "orchestration.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("max_concurrent_runs=", source)
        self.assertIn("in_flight_limit=", source)
        self.assertIn("max_num_seqs=", source)

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
        self.assertIn("VLLM_PIN", job)
        self.assertIn("v0.28.0", job)
        self.assertIn("VLLM_MODULE", job)
        self.assertIn("VLLM_SIF", job)
        self.assertIn("VLLM_LAUNCH", job)
        self.assertIn("--bind", job)
        self.assertNotIn("--cleanenv", job)
        self.assertNotIn("--home", job)
        self.assertNotIn('--env "HOME=', job)
        self.assertIn('--env "NCCL_P2P_DISABLE=', job)
        self.assertIn('export NCCL_P2P_DISABLE=', job)
        self.assertIn("SERVE_HANG_SECONDS", job)
        self.assertIn("shm_broadcast", job)
        self.assertIn("vllm_wrap.sh", job)
        self.assertIn("/scratch/shared/%u/vllm/thesis_vllm_%j.out", job)
        self.assertIn("/yen/scratch/shared", job)
        self.assertIn('GPU_MODEL:A40', job)
        self.assertNotIn("GPU_MODEL:H200", job)
        self.assertNotIn("HF_MODEL", job)
        self.assertIn("python/3.11.3", job)
        self.assertIn("python3 -m venv", job)
        self.assertNotIn("/usr/bin/python3 -m venv", job)
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
        self.assertIn("VLLM_EXTRA", job)
        self.assertIn("--enable-log-requests", job)
        self.assertIn('if [[ " ${VLLM_EXTRA[*]} " != *" --enable-prefix-caching "* ]]; then', job)
        self.assertIn("VLLM_EXTRA+=(--enable-prefix-caching)", job)
        self.assertIn("#SBATCH -G 1", job)
        self.assertNotIn("#SBATCH -G 2", job)
        self.assertIn("gemma4_31b", job)
        self.assertIn("olmo31_32b", job)
        self.assertIn("qwen38_27b", job)
        self.assertIn("glm4_32b", job)
        self.assertIn("--disable-custom-all-reduce", job)
        self.assertIn("Keep model YAML extras", job)
        self.assertIn('if key == "MAX_NUM_SEQS" or not os.environ.get(key):', job)
        self.assertIn("diag-ashery-*", job)
        self.assertIn("DIAG_DECODE", job)
        self.assertIn("DIAG_LADDER", job)
        self.assertIn("diag-ashery-parse-", job)
        self.assertIn("diag-ashery-schema-", job)
        self.assertIn("diag-h12-", job)
        self.assertIn("diag-n48-", job)
        self.assertIn("diag-strings-", job)
        self.assertIn("cannot be combined with CAMPAIGN", job)
        self.assertIn("cannot be combined with DIAG_TECH_INTERACTIONS", job)
        self.assertIn("run_counted_slice", job)
        self.assertIn("thesis_${SLURM_JOB_ID}.log", job)
        self.assertIn("http://127.0.0.1:{port}/metrics", job)
        self.assertIn("start_metrics_scrape", job)
        self.assertIn("interval = 20", job)
        self.assertIn("METRICS_RUNNER_PID", job)

    def test_run_main_cli_base_url_reaches_model_spec(self):
        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["url"] = model_spec.base_url
            captured["config_url"] = config["serve"]["base_url"]
            return []

        with patch("run_main.require_clean_worktree"), patch("run_main.run_slice_async", side_effect=fake_slice):
            code = run_main.main(
                [
                    "--model",
                    "nemotron35_lightning",
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
        self.assertEqual(captured["config_url"], "http://127.0.0.1:8000/v1")

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

    def test_run_main_ashery_without_diag_env_fails(self):
        cleared = {
            "DIAG_N": "",
            "DIAG_H": "",
            "DIAG_POOL": "",
            "DIAG_DECODE": "",
            "DIAG_CAP": "",
        }
        with patch.dict("os.environ", cleared, clear=False):
            with patch("run_main.require_clean_worktree"):
                with self.assertRaises(SystemExit) as raised:
                    run_main.main(
                        [
                            "--model",
                            "mock",
                            "--program",
                            "emergence",
                            "--seed-from",
                            "0",
                            "--seed-to",
                            "1",
                            "--campaign",
                            "diag-ashery-parse-mock",
                        ]
                    )
        self.assertNotEqual(raised.exception.code, 0)

    def test_run_main_one_factor_campaign_without_diag_env_fails(self):
        cleared = {
            "DIAG_N": "",
            "DIAG_H": "",
            "DIAG_POOL": "",
            "DIAG_DECODE": "",
            "DIAG_CAP": "",
        }
        with patch.dict("os.environ", cleared, clear=False):
            with patch("run_main.require_clean_worktree"):
                with self.assertRaises(SystemExit) as raised:
                    run_main.main(
                        [
                            "--model",
                            "mock",
                            "--program",
                            "emergence",
                            "--seed-from",
                            "0",
                            "--seed-to",
                            "1",
                            "--campaign",
                            "diag-h12-parse-mock",
                        ]
                    )
        self.assertNotEqual(raised.exception.code, 0)

    def test_run_main_ashery_diag_env_reaches_protocol(self):
        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["protocol"] = dict(config["protocol"])
            captured["pool"] = dict(config["pool"])
            return []

        env = {
            "DIAG_N": "24",
            "DIAG_H": "5",
            "DIAG_POOL": "letters",
            "DIAG_DECODE": "parse",
            "DIAG_CAP": "400",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("run_main.require_clean_worktree"), patch(
                "run_main.run_slice_async", side_effect=fake_slice
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--program",
                        "emergence",
                        "--seed-from",
                        "0",
                        "--seed-to",
                        "1",
                        "--campaign",
                        "diag-ashery-parse-mock",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured["protocol"]["N"], 24)
        self.assertEqual(captured["protocol"]["H"], 5)
        self.assertEqual(captured["protocol"]["gate_window"], 72)
        self.assertEqual(captured["protocol"]["diag_decode"], "parse")
        self.assertEqual(captured["protocol"]["cap_phase1"], 400)
        self.assertEqual(captured["pool"]["labels"][0], "Q")

    def test_run_main_h12_diag_env_reaches_protocol(self):
        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["protocol"] = dict(config["protocol"])
            return []

        env = {
            "DIAG_N": "24",
            "DIAG_H": "12",
            "DIAG_POOL": "letters",
            "DIAG_DECODE": "parse",
            "DIAG_CAP": "400",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("run_main.require_clean_worktree"), patch(
                "run_main.run_slice_async", side_effect=fake_slice
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--program",
                        "emergence",
                        "--seed-from",
                        "0",
                        "--seed-to",
                        "1",
                        "--campaign",
                        "diag-h12-parse-mock",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured["protocol"]["N"], 24)
        self.assertEqual(captured["protocol"]["H"], 12)
        self.assertEqual(captured["protocol"]["gate_window"], 72)
        self.assertEqual(captured["protocol"]["diag_decode"], "parse")

    def test_run_main_diag_tech_does_not_require_full_knobs(self):
        captured = {}

        async def fake_slice(config, model_spec, **kwargs):
            captured["N"] = config["protocol"]["N"]
            captured["campaign"] = config["run"]["campaign"]
            return []

        cleared = {
            "DIAG_N": "",
            "DIAG_H": "",
            "DIAG_POOL": "",
            "DIAG_DECODE": "",
            "DIAG_CAP": "",
        }
        with patch.dict("os.environ", cleared, clear=False):
            with patch("run_main.require_clean_worktree"), patch(
                "run_main.run_slice_async", side_effect=fake_slice
            ):
                code = run_main.main(
                    [
                        "--model",
                        "mock",
                        "--program",
                        "emergence",
                        "--seed-from",
                        "0",
                        "--seed-to",
                        "1",
                        "--campaign",
                        "diag-tech-mock",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(captured["campaign"], "diag-tech-mock")
        self.assertEqual(captured["N"], 48)

    def test_run_one_passes_json_schema_to_client(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / "run_one.py").read_text(encoding="utf-8")
        self.assertIn("json_schema=cfg.json_schema", source)
        self.assertIn("limiter=asyncio.Semaphore(cfg.in_flight_limit)", source)

    def test_run_main_print_jobs_emits_hf_id_and_shorthand(self):
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            code = run_main.main(["--print-jobs"])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("nemotron35_lightning", text)
        self.assertIn("nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16", text)
        self.assertIn("model_id=", text)

    def test_run_one_refuses_dirty_tree(self):
        with patch("run_one.require_clean_worktree", side_effect=DirtyWorktreeError("dirty")):
            self.assertEqual(
                run_one.main(["--program", "emergence", "--model", "mock", "--topology", "mixing", "--seed-index", "0"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()
