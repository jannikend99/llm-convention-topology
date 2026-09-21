from __future__ import annotations

import unittest
from pathlib import Path

from convention_topology.dvs import DEFAULT_WINDOW
from convention_topology.analysis.h3a import K_GRID


class AnalysisIdentityTests(unittest.TestCase):
    def test_window_and_k_grid(self):
        self.assertEqual(DEFAULT_WINDOW, 144)
        self.assertEqual(K_GRID, [5, 10, 14])

    def test_job_file_exists(self):
        path = Path(__file__).resolve().parent.parent / "jobs" / "thesis_vllm.slurm"
        text = path.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertIn("/v1/models", text)
        self.assertIn("USR1", text)
        self.assertIn("run_main.py", text)
        self.assertIn("artifact-root", text)
        self.assertRegex(text, r'\$\{PYTHON\}"\s+-\s+<<')
        self.assertIn('"${VLLM_BIN[@]}" serve', text)
