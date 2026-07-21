from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from convention_topology.config import derive_seeds, load_config, resolve_model
from convention_topology.orchestration import (
    GridCell,
    cell_targets,
    cm_pilot_grid,
    emergence_pilot_grid,
    get_code_commit,
    pilot_grid,
    run_batch,
    run_cell_targeted,
)
from convention_topology.persistence import META_FIELDS, build_run_id, read_meta, run_paths, write_meta
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


def _small_config():
    config = load_config()
    config.params.N = 8  # must be >= max cm_k (6) for CM pilot cells
    config.params.total_interactions = 40  # short CM horizon in tests
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
        for _ in range(5):
            self.assertEqual(derive_seeds(1, "lattice", 3, 7), derive_seeds(1, "lattice", 3, 7))


class PilotGridTests(unittest.TestCase):
    def test_emergence_grid_36_rows_no_k(self):
        cells = emergence_pilot_grid(base_seed=20260713)
        self.assertEqual(len(cells), 36)
        self.assertTrue(all(c.program == PROGRAM_EMERGENCE and c.cm_k == 0 for c in cells))
        by_topology = {}
        for cell in cells:
            by_topology.setdefault(cell.topology, []).append(cell)
        self.assertEqual(set(by_topology), {"complete", "random_regular", "lattice"})
        for rows in by_topology.values():
            self.assertEqual(len(rows), 12)

    def test_cm_grid_k_cyclic(self):
        cells = cm_pilot_grid(base_seed=20260713)
        self.assertEqual(len(cells), 36)
        complete_ks = [c.cm_k for c in cells if c.topology == "complete"]
        self.assertEqual(complete_ks, [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6])
        self.assertTrue(all(c.program == PROGRAM_CM for c in cells))

    def test_pilot_grid_dispatch(self):
        self.assertEqual(pilot_grid(1, PROGRAM_EMERGENCE), emergence_pilot_grid(1))
        self.assertEqual(pilot_grid(1, PROGRAM_CM), cm_pilot_grid(1))

    def test_topology_filter_keeps_twelve_complete_rows(self):
        cells = pilot_grid(20260713, PROGRAM_EMERGENCE)
        filtered = [cell for cell in cells if cell.topology == "complete"]
        self.assertEqual(len(filtered), 12)
        self.assertTrue(all(cell.topology == "complete" for cell in filtered))


class ResumeAndRetryTests(unittest.TestCase):
    def test_completed_and_censored_runs_are_skipped_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cells = [
                GridCell(PROGRAM_EMERGENCE, "complete", 1, 0, *derive_seeds(1, "complete", 0, 1)),
                GridCell(PROGRAM_EMERGENCE, "complete", 2, 0, *derive_seeds(1, "complete", 0, 2)),
            ]
            first = run_batch(
                config,
                model_spec,
                cells,
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=False,
            )
            self.assertTrue(all(status in ("completed", "censored") for status in first.values()))
            second = run_batch(
                config,
                model_spec,
                cells,
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=False,
            )
            self.assertEqual(first, second)

    def test_failed_run_only_reattempted_with_retry_failed_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            cell = GridCell(PROGRAM_CM, "complete", 1, 1, *derive_seeds(1, "complete", 1, 1))
            run_id = build_run_id(
                model_spec.shorthand, cell.topology, cell.run_seed, program=PROGRAM_CM, cm_k=cell.cm_k
            )
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
            paths.events_path.parent.mkdir(parents=True, exist_ok=True)

            fake_meta = {field: None for field in META_FIELDS}
            fake_meta.update(
                run_id=run_id,
                run_status="failed",
                topology=cell.topology,
                cm_k=cell.cm_k,
                program=PROGRAM_CM,
            )
            write_meta(paths.meta_path, fake_meta)

            results = run_batch(
                config,
                model_spec,
                [cell],
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=False,
            )
            self.assertEqual(results[run_id], "failed")

            results = run_batch(
                config,
                model_spec,
                [cell],
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=True,
            )
            self.assertEqual(results[run_id], "completed")


class WorkersTests(unittest.TestCase):
    def test_workers_two_matches_serial_run_set(self):
        config = _small_config()
        model_spec = resolve_model(config, "mock")
        cells = [
            GridCell(PROGRAM_CM, "complete", i, ((i - 1) % 6) + 1, *derive_seeds(1, "complete", ((i - 1) % 6) + 1, i))
            for i in range(1, 7)
        ]

        with tempfile.TemporaryDirectory() as tmp_serial:
            serial = run_batch(
                config,
                model_spec,
                cells,
                data_dir=Path(tmp_serial) / "data",
                logs_dir=Path(tmp_serial) / "logs",
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=False,
            )

        with tempfile.TemporaryDirectory() as tmp_parallel:
            parallel = run_batch(
                config,
                model_spec,
                cells,
                data_dir=Path(tmp_parallel) / "data",
                logs_dir=Path(tmp_parallel) / "logs",
                mock_policy="imitate_modal",
                workers=2,
                retry_failed=False,
            )

        self.assertEqual(set(serial.keys()), set(parallel.keys()))
        self.assertEqual(serial, parallel)


class MainStudyTargetingTests(unittest.TestCase):
    def test_cm_cell_targets_18_rows(self):
        config = load_config()
        rows = cell_targets(config, PROGRAM_CM)
        self.assertEqual(len(rows), 18)
        complete_rows = [r for r in rows if r["topology"] == "complete"]
        self.assertEqual(len(complete_rows), 6)
        self.assertEqual(complete_rows[0]["target_min"], 15)
        self.assertEqual(complete_rows[0]["attempted_cap"], 45)

    def test_emergence_cell_targets_3_rows(self):
        config = load_config()
        rows = cell_targets(config, PROGRAM_EMERGENCE)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["cm_k"] == 0 for r in rows))

    def test_forced_censoring_stops_at_attempted_cap_emergence(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            config.params.max_phase1_interactions = 10
            model_spec = resolve_model(config, "mock")
            result = run_cell_targeted(
                config,
                model_spec,
                PROGRAM_EMERGENCE,
                "complete",
                0,
                target=3,
                attempted_cap=5,
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="random",
                retry_failed=False,
            )
            self.assertEqual(result["attempted"], 5)
            self.assertEqual(result["eligible"], 0)

    def test_cm_stops_early_once_completed_target_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir = Path(tmp) / "data", Path(tmp) / "logs"
            config = _small_config()
            model_spec = resolve_model(config, "mock")
            result = run_cell_targeted(
                config,
                model_spec,
                PROGRAM_CM,
                "complete",
                1,
                target=2,
                attempted_cap=20,
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                retry_failed=False,
            )
            self.assertEqual(result["eligible"], 2)
            self.assertEqual(result["attempted"], 2)


class CodeCommitSidecarTests(unittest.TestCase):
    def test_batch_sidecar_records_real_commit(self):
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
            cell = GridCell(PROGRAM_EMERGENCE, "complete", 1, 0, *derive_seeds(1, "complete", 0, 1))
            run_id = build_run_id(
                model_spec.shorthand, cell.topology, cell.run_seed, program=PROGRAM_EMERGENCE
            )

            run_batch(
                config,
                model_spec,
                [cell],
                data_dir=data_dir,
                logs_dir=logs_dir,
                mock_policy="imitate_modal",
                workers=1,
                retry_failed=False,
            )

            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            meta = read_meta(paths.meta_path)
            self.assertEqual(meta["code_commit"], expected)

    def test_get_code_commit_matches_git_rev_parse(self):
        try:
            expected = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            expected = "unknown"
        self.assertEqual(get_code_commit(), expected)

    def test_get_code_commit_ignores_process_cwd(self):
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


if __name__ == "__main__":
    unittest.main()
