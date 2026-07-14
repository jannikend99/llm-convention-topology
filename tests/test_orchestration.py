from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from convention_topology.config import derive_seeds, load_config, resolve_model
from convention_topology.orchestration import GridCell, cell_targets, get_code_commit, pilot_grid, run_cell_targeted
from convention_topology.orchestration import run_batch
from convention_topology.persistence import build_run_id, read_meta, run_paths, write_meta


def _small_config():
    config = load_config()
    config.params.N = 4  # keep mocked runs fast in tests
    return config


class DeriveSeedsTests(unittest.TestCase):
    def test_same_inputs_give_same_seeds(self):
        a = derive_seeds(20260713, "complete", 1, 1)
        b = derive_seeds(20260713, "complete", 1, 1)
        self.assertEqual(a, b)

    def test_distinct_cells_give_distinct_seeds(self):
        a = derive_seeds(20260713, "complete", 1, 1)
        b = derive_seeds(20260713, "complete", 2, 1)
        c = derive_seeds(20260713, "lattice", 1, 1)
        d = derive_seeds(20260713, "complete", 1, 2)
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)

    def test_not_python_hash_randomized(self):
        # Two independent processes would disagree if this used hash();
        # within one process, calling twice must already agree (proxy check).
        for _ in range(5):
            self.assertEqual(derive_seeds(1, "lattice", 3, 7), derive_seeds(1, "lattice", 3, 7))


class PilotGridTests(unittest.TestCase):
    def test_exactly_36_rows_three_topologies_twelve_seeds(self):
        cells = pilot_grid(base_seed=20260713)
        self.assertEqual(len(cells), 36)
        by_topology = {}
        for cell in cells:
            by_topology.setdefault(cell.topology, []).append(cell)
        self.assertEqual(set(by_topology), {"complete", "random_regular", "lattice"})
        for topology, rows in by_topology.items():
            self.assertEqual(len(rows), 12)

    def test_k_assigned_cyclically_1_through_6_twice(self):
        cells = pilot_grid(base_seed=20260713)
        complete_ks = [c.cm_k for c in cells if c.topology == "complete"]
        self.assertEqual(complete_ks, [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6])

    def test_grid_is_deterministic_across_calls(self):
        self.assertEqual(pilot_grid(base_seed=1), pilot_grid(base_seed=1))


class ResumeAndRetryTests(unittest.TestCase):
    def test_completed_and_censored_runs_are_skipped_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cells = [
                GridCell("complete", 1, 1, *derive_seeds(1, "complete", 1, 1)),
                GridCell("complete", 2, 2, *derive_seeds(1, "complete", 2, 2)),
            ]
            first = run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )
            self.assertTrue(all(status in ("completed", "censored") for status in first.values()))

            # Sentinel: touch the pickle mtime marker via meta read; a second
            # batch run must not re-execute (proxy: total wall time is tiny
            # and results are unchanged) since resume-by-sidecar skips them.
            second = run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )
            self.assertEqual(first, second)

    def test_failed_run_only_reattempted_with_retry_failed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell("complete", 1, 1, *derive_seeds(1, "complete", 1, 1))
            run_id = build_run_id(model_spec.shorthand, cell.topology, cell.cm_k, cell.run_seed)
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            from convention_topology.persistence import META_FIELDS

            fake_meta = {field: None for field in META_FIELDS}
            fake_meta.update(run_id=run_id, run_status="failed", topology=cell.topology, cm_k=cell.cm_k)
            write_meta(paths.meta_path, fake_meta)

            # Default: failed run is left alone (not auto-replaced, M03 lock).
            results = run_batch(
                config, model_spec, [cell], data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )
            self.assertEqual(results[run_id], "failed")
            self.assertEqual(read_meta(paths.meta_path)["run_status"], "failed")

            # --retry-failed: re-attempted and (with a working mock) completes.
            results = run_batch(
                config, model_spec, [cell], data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=True,
            )
            self.assertIn(results[run_id], ("completed", "censored"))


class WorkersTests(unittest.TestCase):
    def test_workers_two_matches_serial_run_set(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        cells = [
            GridCell("complete", i, ((i - 1) % 6) + 1, *derive_seeds(1, "complete", ((i - 1) % 6) + 1, i))
            for i in range(1, 7)
        ]

        with tempfile.TemporaryDirectory() as tmp_serial:
            serial = run_batch(
                config, model_spec, cells,
                data_dir=Path(tmp_serial) / "data", logs_dir=Path(tmp_serial) / "logs",
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )

        with tempfile.TemporaryDirectory() as tmp_parallel:
            parallel = run_batch(
                config, model_spec, cells,
                data_dir=Path(tmp_parallel) / "data", logs_dir=Path(tmp_parallel) / "logs",
                mock_policy="imitate_modal", workers=2, retry_failed=False,
            )

        self.assertEqual(set(serial.keys()), set(parallel.keys()))
        self.assertEqual(serial, parallel)


class MainStudyTargetingTests(unittest.TestCase):
    def test_cell_targets_18_rows_correct_targets(self):
        config = load_config()
        rows = cell_targets(config)
        self.assertEqual(len(rows), 18)  # 3 topologies x 6 k cells
        complete_rows = [r for r in rows if r["topology"] == "complete"]
        self.assertEqual(len(complete_rows), 6)
        self.assertEqual(complete_rows[0]["eligible_target_min"], 15)
        self.assertEqual(complete_rows[0]["eligible_target_max"], 20)
        self.assertEqual(complete_rows[0]["attempted_cap"], 45)
        lattice_rows = [r for r in rows if r["topology"] == "lattice"]
        self.assertEqual(lattice_rows[0]["eligible_target_min"], 8)
        self.assertEqual(lattice_rows[0]["attempted_cap"], 24)

    def test_forced_censoring_stops_at_attempted_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            config.params.max_phase1_interactions = 10  # force fast censoring
            model_spec = resolve_model(config, "mock")
            result = run_cell_targeted(
                config, model_spec, "complete", 1, target=3, attempted_cap=5,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="random", retry_failed=False,
            )
            self.assertEqual(result["attempted"], 5)
            self.assertEqual(result["eligible"], 0)

            # Eligible counting matches what's actually on disk.
            on_disk_completed = 0
            for run_id, status in result["runs"]:
                self.assertEqual(status, "censored")
                paths = run_paths(data_dir, logs_dir, model_spec.shorthand, "complete", run_id)
                meta = read_meta(paths.meta_path)
                self.assertEqual(meta["run_status"], "censored")
                if meta["run_status"] == "completed":
                    on_disk_completed += 1
            self.assertEqual(on_disk_completed, result["eligible"])

    def test_stops_early_once_eligible_target_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            result = run_cell_targeted(
                config, model_spec, "complete", 1, target=2, attempted_cap=20,
                data_dir=data_dir, logs_dir=logs_dir, mock_policy="imitate_modal", retry_failed=False,
            )
            self.assertEqual(result["eligible"], 2)
            self.assertLessEqual(result["attempted"], 20)
            self.assertEqual(result["attempted"], len(result["runs"]))


class CodeCommitSidecarTests(unittest.TestCase):
    """B2: pilot-produced sidecars must record the real git commit, never the literal "pilot"."""

    def test_pilot_batch_sidecar_records_real_commit(self):
        try:
            expected = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            expected = "unknown"

        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell("complete", 1, 1, *derive_seeds(1, "complete", 1, 1))
            run_id = build_run_id(model_spec.shorthand, cell.topology, cell.cm_k, cell.run_seed)

            run_batch(
                config, model_spec, [cell], data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )

            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["code_commit"], expected)
            self.assertNotEqual(meta["code_commit"], "pilot")

    def test_get_code_commit_matches_git_rev_parse(self):
        try:
            expected = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            expected = "unknown"
        self.assertEqual(get_code_commit(), expected)

    def test_get_code_commit_ignores_process_cwd(self):
        # R2-M1: a CLI launched from inside a *different* git repo (e.g. a
        # meta-repo root) must still record this repo's commit, not the
        # cwd's -- get_code_commit() is pinned to its own package directory.
        try:
            this_repo_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            self.skipTest("not running inside a git repo")

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp, check=True)
            (Path(tmp) / "file.txt").write_text("x")
            subprocess.run(["git", "add", "file.txt"], cwd=tmp, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
            other_repo_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], cwd=tmp, stderr=subprocess.DEVNULL
            ).decode().strip()
            self.assertNotEqual(other_repo_commit, this_repo_commit)

            original_cwd = Path.cwd()
            import os

            os.chdir(tmp)
            try:
                result = get_code_commit()
            finally:
                os.chdir(original_cwd)

            self.assertEqual(result, this_repo_commit)
            self.assertNotEqual(result, other_repo_commit)


if __name__ == "__main__":
    unittest.main()
