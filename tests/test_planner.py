from __future__ import annotations

import unittest

from convention_topology.config import load_config
from convention_topology.orchestration import format_job_line, print_jobs, seed_slices


class PlannerTests(unittest.TestCase):
    def test_slices_disjoint_and_tile(self):
        ranges = seed_slices(32, 8)
        covered = []
        for start, end in ranges:
            chunk = list(range(start, end))
            self.assertTrue(set(covered).isdisjoint(chunk))
            covered.extend(chunk)
        self.assertEqual(covered, list(range(32)))

    def test_print_jobs_compose_grid(self):
        config = load_config()
        jobs = print_jobs(config)
        self.assertTrue(jobs)
        by_group: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for job in jobs:
            by_group.setdefault((job.model, job.program), []).append((job.seed_from, job.seed_to))
            line = format_job_line(job)
            self.assertIn("--seed-from", line)
            self.assertIn(f"--model {job.model}", line)
            self.assertIn(f"model_id={job.model_id}", line)
            self.assertIn("/", job.model_id)
        for (_model, _program), ranges in by_group.items():
            covered = []
            for start, end in ranges:
                self.assertTrue(set(covered).isdisjoint(range(start, end)))
                covered.extend(range(start, end))
            self.assertEqual(sorted(covered), list(range(32)))
        models = {job.model for job in jobs}
        self.assertEqual(models, {"nemotron35_lightning", "gemma4_31b", "qwen38_27b", "mistral_small4"})

    def test_bad_slice_size_raises(self):
        with self.assertRaises(ValueError):
            seed_slices(32, 0)
