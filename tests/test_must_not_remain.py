from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

from convention_topology.analysis.common import load_run_table
from convention_topology.config import TOPOLOGIES, load_config, validate_config
from convention_topology.persistence import SIDECAR_FIELDS


REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", "archive", "graphify-out", ".pytest_cache"}
BANNED_SUBSTRINGS = (
    "parse_label",
    "ProviderPool",
    "main_eligible_targets",
    "attempted_cap_factor",
    "run_cell_targeted",
    "ThreadPoolExecutor",
    "TBD-doug",
    "delete_run_artifacts",
    "load_dotenv",
    "run_pilot",
    "options_emergence",
    "openrouter_provider",
    "DEFAULT_WINDOW = 72",
    "K_GRID = range(1, 7)",
    "K_GRID = list(range(1, 7))",
)


def _iter_live_files():
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part == "pre-rebuild" or part == "tests" for part in path.parts):
            continue
        if path.suffix not in {".py", ".yaml", ".yml", ".md", ".ipynb", ".slurm", ".txt"}:
            continue
        if path.name in {"test_must_not_remain.py", "config.py"}:
            continue
        yield path


class MustNotRemainTests(unittest.TestCase):
    def test_banned_substrings_absent(self):
        hits = []
        for path in _iter_live_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in BANNED_SUBSTRINGS:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}:{token}")
        self.assertEqual(hits, [])

    def test_topology_and_sidecar_identity(self):
        self.assertNotIn("complete", TOPOLOGIES)
        self.assertEqual(TOPOLOGIES[0], "mixing")
        self.assertNotIn("eligibility", SIDECAR_FIELDS)
        self.assertNotIn("main_eligible_targets", SIDECAR_FIELDS)
        self.assertIn("gate_passed", SIDECAR_FIELDS)
        self.assertIn("prepared_state_valid", SIDECAR_FIELDS)

    def test_no_threadpool_in_live_python(self):
        for path in REPO.rglob("*.py"):
            if any(part in SKIP_DIRS or part == "pre-rebuild" or part == "tests" for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotEqual(node.id, "ThreadPoolExecutor")
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "ThreadPoolExecutor")

    def test_cloud_env_absent(self):
        env_path = REPO / ".env"
        if not env_path.exists():
            return
        text = env_path.read_text(encoding="utf-8", errors="replace")
        markers = ("API_KEY", "OPENROUTER", "TOGETHER", "ANTHROPIC", "OPENAI")
        if any(marker in text for marker in markers):
            self.fail("cloud-key .env remains in the experiment checkout")

    def test_live_analysis_does_not_key_eligibility_column(self):
        hits = []
        for path in (REPO / "convention_topology").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if '["eligibility"]' in text or "['eligibility']" in text:
                hits.append(str(path.relative_to(REPO)))
        self.assertEqual(hits, [])

    def test_analysis_refuses_old_topology_id(self):
        import pandas as pd
        from convention_topology.analysis.common import load_run_table
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from convention_topology.persistence import empty_sidecar, write_meta

        with TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "runs" / "mock" / "mixing" / "x.meta.json"
            payload = empty_sidecar()
            payload.update(topology="complete", model_shorthand="mock", program="emergence", run_status="completed")
            write_meta(meta_path, payload)
            with self.assertRaises(ValueError):
                load_run_table(Path(tmp))


if __name__ == "__main__":
    unittest.main()
