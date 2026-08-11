"""Unit tests for memory decision-function helpers (TODO #4b)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from convention_topology.analysis.memory_decision import (
    decision_rows_for_agent,
    modal_label,
    run_memory_decision,
    summarize_by_program,
    summarize_decisions,
)
from convention_topology.persistence import META_FIELDS, save_run_pickle, write_meta


class ModalLabelTests(unittest.TestCase):
    def test_clear_mode(self):
        mode, tie = modal_label(["A", "A", "B", "A", "B"])
        self.assertEqual(mode, "A")
        self.assertFalse(tie)

    def test_tie(self):
        mode, tie = modal_label(["A", "B", "A", "B"])
        self.assertIsNone(mode)
        self.assertTrue(tie)

    def test_empty(self):
        mode, tie = modal_label([])
        self.assertIsNone(mode)
        self.assertTrue(tie)

    def test_single(self):
        mode, tie = modal_label(["Q"])
        self.assertEqual(mode, "Q")
        self.assertFalse(tie)


class DecisionRowsTests(unittest.TestCase):
    def test_partner_hit_and_tie(self):
        # t=1: partner window [A] → mode A, choice A → hit
        # t=2: partner window [A,B] for M=2 → tie
        # t=3: partner window [A,B,A] for M=3 → mode A, choice B → miss
        rows = decision_rows_for_agent(
            run_id="r1",
            program="emergence",
            topology="complete",
            model_shorthand="mock",
            agent_id=0,
            my_history=["X", "A", "B", "B"],
            partner_history=["A", "B", "A", "A"],
            memory_sizes=(1, 2, 3),
        )
        by_tm = {(r["t"], r["M"]): r for r in rows}

        self.assertEqual(by_tm[(1, 1)]["hit_partner"], 1)
        self.assertFalse(by_tm[(1, 1)]["tie_partner"])

        self.assertTrue(by_tm[(2, 2)]["tie_partner"])
        self.assertIsNone(by_tm[(2, 2)]["hit_partner"])

        self.assertEqual(by_tm[(3, 3)]["mode_partner"], "A")
        self.assertEqual(by_tm[(3, 3)]["hit_partner"], 0)

    def test_skips_empty_histories(self):
        rows = decision_rows_for_agent(
            run_id="r1",
            program="cm",
            topology="lattice",
            model_shorthand="mock",
            agent_id=1,
            my_history=[],
            partner_history=[],
            memory_sizes=(5,),
        )
        self.assertEqual(rows, [])


class SummarizeTests(unittest.TestCase):
    def test_summarize_hit_rate(self):
        decisions = pd.DataFrame(
            [
                {"program": "emergence", "topology": "complete", "M": 1, "hit_partner": 1, "hit_pooled": 1, "tie_partner": False, "tie_pooled": False},
                {"program": "emergence", "topology": "complete", "M": 1, "hit_partner": 0, "hit_pooled": 1, "tie_partner": False, "tie_pooled": False},
                {"program": "emergence", "topology": "complete", "M": 1, "hit_partner": None, "hit_pooled": None, "tie_partner": True, "tie_pooled": True},
            ]
        )
        summary = summarize_decisions(decisions)
        row = summary.iloc[0]
        self.assertEqual(row["n_valid_partner"], 2)
        self.assertEqual(row["n_ties_partner"], 1)
        self.assertAlmostEqual(row["p_partner"], 0.5)

        by_prog = summarize_by_program(decisions)
        self.assertAlmostEqual(by_prog.iloc[0]["p_partner"], 0.5)


class EndToEndMemoryDecisionTests(unittest.TestCase):
    def test_run_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            outputs_dir = root / "outputs"
            run_dir = data_dir / "runs" / "mock" / "complete"
            run_dir.mkdir(parents=True)

            sim = {
                0: {
                    "committed_tag": False,
                    "my_history": ["A", "A", "B"],
                    "partner_history": ["A", "A", "A"],
                    "outcome": [100, 100, -50],
                    "interactions": 3,
                    "score": 150,
                    "score_history": [],
                    "neighbours": [1],
                },
                1: {
                    "committed_tag": True,
                    "my_history": ["B", "B", "B"],
                    "partner_history": ["A", "A", "A"],
                    "outcome": [-50, -50, -50],
                    "interactions": 3,
                    "score": -150,
                    "score_history": [],
                    "neighbours": [0],
                },
            }
            pkl = run_dir / "mock_complete_emerg_s0001.pkl"
            save_run_pickle(pkl, sim, {"answers": [], "outcome": [], "players": []}, {})
            meta = {field: None for field in META_FIELDS}
            meta.update(
                {
                    "run_id": "mock_complete_emerg_s0001",
                    "program": "emergence",
                    "topology": "complete",
                    "model_shorthand": "mock",
                    "model_id": "mock",
                    "run_status": "completed",
                    "cm_k": 0,
                    "eligibility": 1,
                }
            )
            write_meta(run_dir / "mock_complete_emerg_s0001.meta.json", meta)

            payload = run_memory_decision(data_dir, outputs_dir, model="mock", memory_sizes=(1, 2))
            out = outputs_dir / "mock" / "memory_decision"
            self.assertTrue((out / "decisions.csv").exists())
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "p_M_by_program.png").exists())
            self.assertTrue((out / "FINDINGS.md").exists())
            self.assertGreater(payload["n_decision_rows"], 0)
            # committed agent excluded
            decisions = pd.read_csv(out / "decisions.csv")
            self.assertTrue((decisions["agent_id"] == 0).all())


if __name__ == "__main__":
    unittest.main()
