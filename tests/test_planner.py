from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO

from convention_topology.config import K_SET, TOPOLOGIES, load_config
from convention_topology.orchestration import (
    TaskSpecError,
    flatten_tasks,
    parse_task,
    seed_slices,
)
import run_main


class TaskGrammarTests(unittest.TestCase):
    def test_parse_emergence_half_open(self):
        spec = parse_task("emergence:mixing:0-2")
        self.assertEqual(spec.program, "emergence")
        self.assertEqual(spec.topologies, ("mixing",))
        self.assertEqual(spec.seed_from, 0)
        self.assertEqual(spec.seed_to, 2)
        self.assertIsNone(spec.k_values)
        cells = flatten_tasks([spec])
        self.assertEqual(
            [(c["topology"], c["cm_k"], c["seed_index"]) for c in cells],
            [("mixing", None, 0), ("mixing", None, 1)],
        )

    def test_parse_cm_k_list(self):
        spec = parse_task("cm:mixing,lattice:0-1:k=5,10")
        self.assertEqual(spec.program, "cm")
        self.assertEqual(spec.topologies, ("mixing", "lattice"))
        self.assertEqual(spec.k_values, (5, 10))
        cells = flatten_tasks([spec])
        keys = {(c["topology"], c["cm_k"], c["seed_index"]) for c in cells}
        self.assertEqual(keys, {("mixing", 5, 0), ("mixing", 10, 0), ("lattice", 5, 0), ("lattice", 10, 0)})

    def test_emergence_with_k_fails(self):
        with self.assertRaises(TaskSpecError):
            parse_task("emergence:mixing:0-2:k=2")

    def test_cm_without_k_fails(self):
        with self.assertRaises(TaskSpecError):
            parse_task("cm:mixing:0-2")

    def test_unknown_program_topology_k_fail(self):
        with self.assertRaises(TaskSpecError):
            parse_task("study1:mixing:0-1")
        with self.assertRaises(TaskSpecError):
            parse_task("emergence:complete:0-1")
        with self.assertRaises(TaskSpecError):
            parse_task("cm:mixing:0-1:k=3")

    def test_omitted_topology_does_not_expand_all(self):
        with self.assertRaises(TaskSpecError):
            parse_task("emergence::0-1")
        with self.assertRaises(TaskSpecError):
            parse_task("emergence:all:0-1")
        spec = parse_task("emergence:mixing:0-1")
        self.assertNotEqual(set(spec.topologies), set(TOPOLOGIES))

    def test_omitted_k_on_cm_does_not_expand_all(self):
        with self.assertRaises(TaskSpecError):
            parse_task("cm:mixing:0-1:k=")
        self.assertEqual(K_SET, (5, 10, 14))

    def test_duplicate_cells_fail(self):
        a = parse_task("emergence:mixing:0-2")
        b = parse_task("emergence:mixing:1-3")
        with self.assertRaises(TaskSpecError):
            flatten_tasks([a, b])


class PrintQueueCliTests(unittest.TestCase):
    def test_print_jobs_is_deprecation_error(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--print-jobs"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_print_queue_expands_tasks_only(self):
        buf = StringIO()
        with redirect_stdout(buf):
            code = run_main.main(
                [
                    "--print-queue",
                    "--task",
                    "emergence:mixing:0-32",
                    "--task",
                    "cm:lattice:0-2:k=5",
                ]
            )
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("emergence", text)
        self.assertIn("mixing", text)
        self.assertIn("total_cells=34", text)
        self.assertNotIn("--seed-from", text)
        self.assertNotIn("gpus=", text)

    def test_print_queue_ignores_seed_indices_per_slice(self):
        config = load_config()
        slice_size = config["models"]["mock"]["seed_indices_per_slice"]["emergence"]
        self.assertGreater(slice_size, 1)
        spec = parse_task("emergence:mixing:0-32")
        cells = flatten_tasks([spec])
        self.assertEqual(len(cells), 32)
        tiled = seed_slices(32, slice_size)
        self.assertGreater(len(tiled), 1)

    def test_queue_path_does_not_call_seed_slices_or_print_jobs(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parent.parent / "run_main.py").read_text(encoding="utf-8")
        self.assertNotIn("seed_slices(", source)
        self.assertNotIn("print_jobs(", source)
        self.assertIn("flatten_tasks(", source)

    def test_task_omitted_fails(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--campaign", "technical-smoke"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_campaign_omitted_fails_despite_config_default(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--model", "mock", "--task", "emergence:mixing:0-1"])
        self.assertNotEqual(raised.exception.code, 0)
        self.assertEqual(load_config()["run"]["campaign"], "experiment")

    def test_model_omitted_on_run_fails(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(["--campaign", "technical-smoke", "--task", "emergence:mixing:0-1"])
        self.assertNotEqual(raised.exception.code, 0)

    def test_print_queue_without_campaign_ok(self):
        buf = StringIO()
        with redirect_stdout(buf):
            code = run_main.main(["--print-queue", "--task", "emergence:mixing:0-1"])
        self.assertEqual(code, 0)
        self.assertIn("total_cells=1", buf.getvalue())

    def test_duplicate_tasks_fail_before_model_resolve(self):
        with self.assertRaises(SystemExit) as raised:
            run_main.main(
                [
                    "--print-queue",
                    "--task",
                    "emergence:mixing:0-2",
                    "--task",
                    "emergence:mixing:1-3",
                ]
            )
        self.assertNotEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
