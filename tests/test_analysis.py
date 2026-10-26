from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from convention_topology.analysis.common import (
    d1_funnel,
    d5_prepared,
    load_run_table,
    prepared_memory_policy_shares,
    prepared_valid_cm,
)
from convention_topology.analysis.dispatch import run_h1, run_h2, run_h3a, run_h3b, run_h4
from convention_topology.analysis.h2 import ALPHA, CONTRAST_TOPOLOGIES, h2_analysis
from convention_topology.analysis.h3a import K_GRID, h3a_analysis
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.analysis.stream import AnalysisMismatchError
from convention_topology.dvs import DEFAULT_WINDOW
from convention_topology.persistence import empty_sidecar, save_run_pickle, write_meta
from convention_topology.tracker import empty_tracker

POOL = ["aaaaa", "bbbbb", "ccccc", "ddddd", "eeeee", "fffff", "ggggg", "hhhhh", "iiiii", "jjjjj"]
REPO = Path(__file__).resolve().parent.parent
LIVE_ANALYSIS = REPO / "convention_topology" / "analysis"


def _meta(**overrides):
    payload = empty_sidecar()
    payload.update(
        {
            "run_id": "run-1",
            "campaign": "results-smoke",
            "program": "emergence",
            "init_mode": "organic",
            "topology": "mixing",
            "model_shorthand": "mock",
            "model_id": "mock",
            "run_status": "completed",
            "gate_passed": True,
            "prepared_state_valid": None,
            "t_gate": 144,
            "gate_window": 144,
            "N": 48,
            "H": 12,
            "cm_k": None,
            "committed_to": None,
            "t_cm_start": None,
            "error_class": None,
            "label_pool": list(POOL),
        }
    )
    payload.update(overrides)
    return payload


def _write_events(path: Path, interactions: list[dict], extra: list[dict] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(extra or []) + interactions
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _interactions(n: int, label: str, run_id: str, success: int = 1) -> list[dict]:
    return [
        {
            "schema_version": 1,
            "record_type": "interaction",
            "run_id": run_id,
            "t": t,
            "p1": 0,
            "p2": 1,
            "label_p1": label,
            "label_p2": label,
            "success": success,
        }
        for t in range(1, n + 1)
    ]


def _tracker_from(interactions: list[dict]):
    tracker = empty_tracker()
    for row in interactions:
        tracker["players"].append([row["p1"], row["p2"]])
        tracker["answers"].append([row["label_p1"], row["label_p2"]])
        tracker["outcome"].append(row["success"])
    return tracker


def _write_run(root: Path, *, model: str, topology: str, run_id: str, meta: dict, interactions: list[dict], extra_events: list[dict] | None = None, simulation: dict | None = None):
    run_dir = root / "runs" / model / topology
    run_dir.mkdir(parents=True, exist_ok=True)
    write_meta(run_dir / f"{run_id}.meta.json", meta)
    _write_events(run_dir / f"{run_id}.events.jsonl", interactions, extra_events)
    save_run_pickle(
        run_dir / f"{run_id}.pkl",
        simulation if simulation is not None else {},
        _tracker_from(interactions),
        {},
    )


class StreamLoadTests(unittest.TestCase):
    def test_window_and_k_grid(self):
        self.assertEqual(DEFAULT_WINDOW, 144)
        self.assertEqual(K_GRID, [5, 10, 14])
        self.assertNotEqual(K_GRID, list(range(1, 7)))

    def test_matching_artifacts_load(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "ok-run"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            table = load_run_table(root, model_filter="mock")
            self.assertEqual(len(table), 1)
            self.assertAlmostEqual(float(table.iloc[0]["dominant_share"]), 1.0)
            self.assertTrue(bool(table.iloc[0]["gate_passed"]))
            self.assertEqual(int(table.iloc[0]["t_gate"]), 144)
            self.assertEqual(table.iloc[0]["stream_winner"], POOL[0])

    def test_missing_pickle_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "no-pkl"
            run_dir = root / "runs" / "mock" / "mixing"
            meta = _meta(run_id=run_id)
            write_meta(run_dir / f"{run_id}.meta.json", meta)
            _write_events(run_dir / f"{run_id}.events.jsonl", _interactions(144, POOL[0], run_id))
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_count_mismatch_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "bad-count"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            pickle_path = root / "runs" / "mock" / "mixing" / f"{run_id}.pkl"
            tracker = _tracker_from(ix + _interactions(1, POOL[0], run_id))
            tracker["outcome"] = tracker["outcome"]  # extra row already included
            save_run_pickle(pickle_path, {}, tracker, {})
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_answers_mismatch_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "bad-ans"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            tracker = _tracker_from(ix)
            tracker["answers"][0] = [POOL[1], POOL[1]]
            save_run_pickle(root / "runs" / "mock" / "mixing" / f"{run_id}.pkl", {}, tracker, {})
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_outcome_mismatch_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "bad-out"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            tracker = _tracker_from(ix)
            tracker["outcome"][0] = 0
            save_run_pickle(root / "runs" / "mock" / "mixing" / f"{run_id}.pkl", {}, tracker, {})
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_missing_jsonl_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "no-jsonl"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            (root / "runs" / "mock" / "mixing" / f"{run_id}.events.jsonl").unlink()
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_sidecar_t_gate_mismatch_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "bad-tgate"
            ix = _interactions(144, POOL[0], run_id)
            meta = _meta(run_id=run_id, t_gate=200)
            _write_run(root, model="mock", topology="mixing", run_id=run_id, meta=meta, interactions=ix)
            with self.assertRaises(AnalysisMismatchError):
                load_run_table(root)

    def test_short_completed_cm_refuses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "short-cm"
            committed = POOL[1]
            ix = _interactions(10, committed, run_id)
            _write_run(
                root,
                model="mock",
                topology="mixing",
                run_id=run_id,
                meta=_meta(
                    run_id=run_id,
                    program="cm",
                    init_mode="prepared",
                    gate_passed=None,
                    t_gate=None,
                    prepared_state_valid=True,
                    cm_k=2,
                    committed_to=committed,
                    t_cm_start=0,
                    incumbent_label=POOL[0],
                    committed_ids=[0, 1],
                ),
                interactions=ix,
            )
            with self.assertRaises(AnalysisMismatchError) as ctx:
                load_run_table(root)
            self.assertIn("10 interactions", str(ctx.exception))

    def test_incomplete_short_cm_loads_without_flip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "fail-cm"
            committed = POOL[1]
            ix = _interactions(10, committed, run_id)
            _write_run(
                root,
                model="mock",
                topology="mixing",
                run_id=run_id,
                meta=_meta(
                    run_id=run_id,
                    program="cm",
                    init_mode="prepared",
                    run_status="failed",
                    gate_passed=None,
                    t_gate=None,
                    prepared_state_valid=True,
                    cm_k=2,
                    committed_to=committed,
                    t_cm_start=0,
                    error_class="config",
                    incumbent_label=POOL[0],
                    committed_ids=[0, 1],
                ),
                interactions=ix,
            )
            table = load_run_table(root)
            self.assertEqual(len(table), 1)
            self.assertTrue(pd.isna(table.iloc[0]["flip"]))


class H2SpineTests(unittest.TestCase):
    def test_primary_h2_is_independent_of_exploratory_topologies(self):
        mixing = [0.95, 0.96, 0.97, 0.94]
        low = [0.2, 0.21, 0.19, 0.22]
        result = h2_analysis(
            {
                "mixing": mixing,
                "lattice": low,
                "random_regular": low,
                "watts_strogatz": low,
                "barabasi_albert": low,
            }
        )
        for topology in CONTRAST_TOPOLOGIES:
            self.assertIn(f"{topology}_vs_mixing", result)
        self.assertEqual(ALPHA, 0.025)
        self.assertEqual(result["n_contrasts"], 2)
        self.assertEqual(result["watts_strogatz_vs_mixing"]["alpha"], None)
        self.assertEqual(result["analysis_status"], "amended-primary")
        self.assertEqual(result["confirmatory_status"], "not-established")
        self.assertEqual(result["support"], "full")

        none = h2_analysis(
            {
                "mixing": mixing,
                "lattice": mixing,
                "random_regular": mixing,
                "watts_strogatz": mixing,
                "barabasi_albert": mixing,
            }
        )
        self.assertEqual(none["support"], "none")

        partial = h2_analysis(
            {
                "mixing": mixing,
                "lattice": low,
                "random_regular": mixing,
                "watts_strogatz": mixing,
                "barabasi_albert": mixing,
            }
        )
        self.assertEqual(partial["support"], "partial")

        exploratory_only = h2_analysis({"mixing": mixing, "lattice": mixing, "random_regular": mixing,
                                        "watts_strogatz": low, "barabasi_albert": low})
        self.assertEqual(exploratory_only["support"], "none")

    def test_h2_missing_primary_data_is_unevaluable(self):
        result = h2_analysis({"mixing": [0.9, 0.95], "lattice": [0.2, 0.3]})
        self.assertEqual(result["support"], "unevaluable")
        self.assertEqual(result["random_regular_vs_mixing"]["decision"], "unevaluable")

    def test_h2_invalid_or_zero_total_variance_primary_data_is_unevaluable(self):
        invalid = h2_analysis({"mixing": [0.9, 1.1], "lattice": [0.2, 0.3], "random_regular": [0.2, 0.3]})
        self.assertEqual(invalid["support"], "unevaluable")
        constant = h2_analysis({"mixing": [0.9, 0.9], "lattice": [0.2, 0.3], "random_regular": [0.2, 0.3]})
        self.assertEqual(constant["support"], "full")
        both_constant = h2_analysis({"mixing": [0.9, 0.9], "lattice": [0.2, 0.2], "random_regular": [0.2, 0.2]})
        self.assertEqual(both_constant["support"], "unevaluable")

    def test_run_h1_h2_write_named_ids(self):
        table = pd.DataFrame(
            [
                {
                    "program": "emergence",
                    "topology": topo,
                    "model_shorthand": "mock",
                    "dominant_share": share,
                    "shannon_entropy": 0.1,
                    "gate_passed": True,
                    "t_gate": 144,
                    "events_path": None,
                    "N": 48,
                }
                for topo, share in [
                    ("mixing", 0.96),
                    ("mixing", 0.95),
                    ("lattice", 0.2),
                    ("lattice", 0.21),
                    ("random_regular", 0.22),
                    ("random_regular", 0.23),
                    ("watts_strogatz", 0.24),
                    ("watts_strogatz", 0.25),
                    ("barabasi_albert", 0.26),
                    ("barabasi_albert", 0.27),
                ]
            ]
        )
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_h1(table, out)
            run_h2(table, out)
            for stem in ("F3", "T-H1", "F24", "T-H2", "F4", "F-HUM"):
                self.assertTrue((out / f"{stem}.json").exists(), stem)
                self.assertTrue((out / f"{stem}.csv").exists(), stem)
            payload = json.loads((out / "T-H2.json").read_text())
            self.assertEqual(payload["alpha"], 0.025)
            self.assertIn("watts_strogatz_vs_mixing", payload)
            self.assertIn("barabasi_albert_vs_mixing", payload)
            self.assertEqual(payload["exclusion_counts"]["mixing"]["attempted"], 2)
            self.assertEqual(payload["exclusion_counts"]["mixing"]["available"], 2)
            self.assertEqual(payload["exclusion_counts"]["mixing"]["run_status_counts"], {"unknown": 2})


class H3H4Tests(unittest.TestCase):
    def test_h3a_uses_all_eligible_no_flip_runs_and_categorical_omnibus(self):
        cm_k = [5] * 8 + [10] * 8 + [14] * 8
        flip = [0, 0, 0, 0, 1, 1, 1, 1] * 3
        result = h3a_analysis(cm_k, flip)
        self.assertEqual(result["label"], "evaluable")
        self.assertEqual(result["n"], 24)
        self.assertEqual(result["cell_n"], {5: 8, 10: 8, 14: 8})
        self.assertEqual(result["omnibus_lr_df"], 2)
        self.assertNotIn("gam", result)
        self.assertNotIn("flip_curve", result)

    def test_h3a_missing_or_constant_cells_are_unevaluable(self):
        missing = h3a_analysis([5] * 8 + [10] * 8, [0, 1] * 8)
        self.assertEqual(missing["label"], "unevaluable")
        constant = h3a_analysis([5] * 8 + [10] * 8 + [14] * 8, [1] * 24)
        self.assertEqual(constant["label"], "unevaluable")
        separated = h3a_analysis([5] * 8 + [10] * 8 + [14] * 8, [0] * 8 + [1] * 8 + [1] * 8)
        self.assertEqual(separated["label"], "unevaluable")

    def test_h3a_nonconverged_fit_is_unevaluable(self):
        cm_k = [5] * 8 + [10] * 8 + [14] * 8
        with patch("convention_topology.analysis.h3a._fit_logit", side_effect=ValueError("logit did not converge")):
            result = h3a_analysis(cm_k, [0, 1] * 12)
        self.assertEqual(result["label"], "unevaluable")
        self.assertIn("did not converge", result["reason"])

    def test_h3a_rejects_malformed_input(self):
        self.assertEqual(h3a_analysis([5], [0, 1])["label"], "unevaluable")
        self.assertEqual(h3a_analysis([5], [0.5])["label"], "unevaluable")
        self.assertEqual(h3a_analysis([6], [0])["label"], "unevaluable")

    def test_h3b_remains_exploratory_when_cells_meet_floor(self):
        rows = []
        for topology in ("mixing", "lattice"):
            for k in (5, 10, 14):
                rows.extend({"topology": topology, "cm_k": k, "flip": i % 2} for i in range(8))
        result = h3b_analysis(pd.DataFrame(rows))
        self.assertEqual(result["label"], "exploratory")
        self.assertTrue(result["cell_floor_met"])

    def test_h3b_rechecks_outcome_variation_after_subsetting(self):
        rows = []
        for topology in ("mixing", "lattice"):
            for k in (5, 10, 14):
                rows.extend({"topology": topology, "cm_k": k, "flip": 0} for _ in range(8))
        rows.append({"topology": "watts_strogatz", "cm_k": 5, "flip": 1})
        result = h3b_analysis(pd.DataFrame(rows))
        self.assertFalse(result["fit_evaluable"])
        self.assertIn("qualified topology subset", result["reason"])

    def test_h3b_nonconverged_fit_is_unevaluable(self):
        rows = []
        for topology in ("mixing", "lattice"):
            for k in (5, 10, 14):
                rows.extend({"topology": topology, "cm_k": k, "flip": i % 2} for i in range(8))
        with patch("convention_topology.analysis.h3b.sm.Logit.fit", side_effect=ValueError("logit did not converge")):
            result = h3b_analysis(pd.DataFrame(rows))
        self.assertFalse(result["fit_evaluable"])
        self.assertIn("did not converge", result["reason"])

    def test_h3b_separated_data_is_unevaluable(self):
        rows = []
        for topology in ("mixing", "lattice"):
            for k, flip in ((5, 0), (10, 1), (14, 1)):
                rows.extend({"topology": topology, "cm_k": k, "flip": flip} for _ in range(8))
        result = h3b_analysis(pd.DataFrame(rows))
        self.assertFalse(result["fit_evaluable"])

    def test_t_h3_uses_descriptive_tested_grid_terms(self):
        df = pd.DataFrame(
            [{"program": "cm", "prepared_state_valid": True, "topology": "mixing", "model_shorthand": "mock", "cm_k": k, "flip": i % 2}
             for k in (5, 10, 14) for i in range(8)]
        )
        with TemporaryDirectory() as tmp:
            run_h3b(df, Path(tmp))
            payload = json.loads((Path(tmp) / "T-H3.json").read_text())
            self.assertIn("tested_grid_summary", payload)
            self.assertNotIn("critical_mass", payload)
            table = pd.read_csv(Path(tmp) / "T-H3.csv")
            self.assertIn("smallest_tested_k_flip_ge_0_5", table.columns)
            self.assertIn("grid_summary_status", table.columns)
    def test_h3_drops_invalid_prepared_state(self):
        df = pd.DataFrame(
            [
                {
                    "program": "cm",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "prepared_state_valid": False,
                    "flip": 1,
                    "cm_k": 2,
                    "flip_50": 1,
                },
                {
                    "program": "cm",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "prepared_state_valid": True,
                    "flip": 0,
                    "cm_k": 4,
                    "flip_50": 0,
                },
            ]
        )
        kept = prepared_valid_cm(df)
        self.assertEqual(len(kept), 1)
        self.assertTrue(bool(kept.iloc[0]["prepared_state_valid"]))
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_h3a(df, out, sensitivity_50=False)
            empirical = pd.read_csv(out / "F13.csv")
            self.assertTrue((empirical["cm_k"] == 4).all())
            self.assertFalse((empirical["cm_k"] == 2).any())

    def test_f18_uses_stream_labels_not_sidecar(self):
        df = pd.DataFrame(
            [
                {
                    "program": "emergence",
                    "topology": "mixing",
                    "stream_winner": POOL[3],
                    "incumbent_label": POOL[0],
                    "label_pool": [list(POOL)],
                }
            ]
        )
        # label_pool column as list per row
        df["label_pool"] = [list(POOL)]
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = run_h4(df, out, data_dir=Path(tmp))
            self.assertIn(POOL[3], result["frequencies"])
            self.assertEqual(result["counts"].get(POOL[3]), 1)
            self.assertNotIn(POOL[0], [k for k, v in result["counts"].items() if v])

    def test_gam_grid_not_one_to_six(self):
        self.assertEqual(K_GRID[0], 5)
        self.assertNotIn(2, K_GRID)
        self.assertNotIn(1, K_GRID)


class FunnelAndSmokeTests(unittest.TestCase):
    def test_d1_not_emergence_only(self):
        df = pd.DataFrame(
            [
                {
                    "program": "emergence",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "run_status": "completed",
                    "gate_passed": True,
                    "prepared_state_valid": None,
                    "error_class": None,
                },
                {
                    "program": "cm",
                    "topology": "lattice",
                    "model_shorthand": "mock",
                    "run_status": "failed",
                    "gate_passed": None,
                    "prepared_state_valid": True,
                    "error_class": "attempts_exhausted",
                },
            ]
        )
        table = d1_funnel(df)
        self.assertIn("api_failed", table.columns)
        self.assertIn("study2_prepared_state_valid", table.columns)
        lattice = table[table["topology"] == "lattice"].iloc[0]
        self.assertEqual(int(lattice["api_failed"]), 1)
        self.assertEqual(int(lattice["study2_prepared_state_valid"]), 1)
        extra = pd.DataFrame(
            [
                {
                    "program": "emergence",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "run_status": "failed",
                    "gate_passed": False,
                    "prepared_state_valid": None,
                    "error_class": "config",
                },
                {
                    "program": "emergence",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "run_status": "failed",
                    "gate_passed": False,
                    "prepared_state_valid": None,
                    "error_class": "serve_startup",
                },
                {
                    "program": "emergence",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "run_status": "failed",
                    "gate_passed": False,
                    "prepared_state_valid": None,
                    "error_class": "schema",
                },
            ]
        )
        mixed = pd.concat([df, extra], ignore_index=True)
        mixing = d1_funnel(mixed)
        mixing = mixing[mixing["topology"] == "mixing"].iloc[0]
        self.assertEqual(int(mixing["api_failed"]), 1)
        self.assertEqual(int(mixing["attempted"]), 4)

    def test_d5_reconstructs_from_pickle_not_scalar(self):
        sim = {
            0: {"committed_tag": True, "my_history": [POOL[0]] * 12},
            1: {"committed_tag": False, "my_history": [POOL[0]] * 6 + [POOL[1]] * 6},
            2: {"committed_tag": False, "my_history": [POOL[0]] * 12},
        }
        prepared = {
            "memory_incumbent_share": 1.0,
            "committed_policy_share": 1.0,
            "committed_ids": [0],
        }
        mem, pol = prepared_memory_policy_shares(
            simulation=sim,
            prepared_event=prepared,
            incumbent_label=POOL[0],
            committed_ids=[0],
            memory_size=12,
            n=48,
        )
        self.assertAlmostEqual(mem, 18 / 24)
        self.assertAlmostEqual(pol, 1 / 48)

    def test_d5_fails_without_inventories(self):
        with self.assertRaises(ValueError) as ctx:
            prepared_memory_policy_shares(
                simulation={},
                prepared_event={"memory_incumbent_share": 1.0, "committed_policy_share": 2 / 48},
                incumbent_label=POOL[0],
                committed_ids=[0, 1],
                memory_size=12,
                n=48,
            )
        self.assertIn("inventories", str(ctx.exception))
        df = pd.DataFrame(
            [
                {
                    "program": "cm",
                    "run_id": "no-inv",
                    "topology": "mixing",
                    "model_shorthand": "mock",
                    "cm_k": 2,
                    "N": 48,
                    "memory_incumbent_share": None,
                    "committed_policy_share": None,
                    "prepared_state_valid": True,
                }
            ]
        )
        with self.assertRaises(ValueError):
            d5_prepared(df)

    def test_d5_uses_stream_memory_labels_if_pickle_empty(self):
        mem, pol = prepared_memory_policy_shares(
            simulation={},
            prepared_event={"memory_labels": [POOL[0]] * 8, "committed_ids": [0, 1]},
            incumbent_label=POOL[0],
            committed_ids=[0, 1],
            memory_size=12,
            n=48,
        )
        self.assertAlmostEqual(mem, 1.0)
        self.assertAlmostEqual(pol, 2 / 48)

    def test_mock_smoke_named_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "label_pool.json").write_text(json.dumps({"labels": POOL}), encoding="utf-8")
            # Study 1 mixing
            e_id = "smoke-e"
            e_ix = _interactions(144, POOL[2], e_id)
            _write_run(
                root,
                model="mock",
                topology="mixing",
                run_id=e_id,
                meta=_meta(run_id=e_id, campaign="results-smoke"),
                interactions=e_ix,
            )
            failed_meta = _meta(run_id="smoke-fail", run_status="failed", gate_passed=False, t_gate=None)
            write_meta(root / "runs" / "mock" / "mixing" / "smoke-fail.meta.json", failed_meta)
            # Study 2 mixing k=2
            c_id = "smoke-c"
            committed = POOL[1]
            incumbent = POOL[0]
            c_ix = _interactions(144, committed, c_id)
            prepared = {
                "schema_version": 1,
                "record_type": "prepared_state",
                "run_id": c_id,
                "t": 0,
                "memory_incumbent_share": 1.0,
                "committed_policy_share": 1.0,
                "success": None,
                "committed_ids": [0, 1],
                "memory_labels": [incumbent] * 8,
                "prepared_state_valid": True,
            }
            sim = {}
            for agent in range(8):
                history = [incumbent] * 12 + [committed] * 132
                sim[agent] = {"committed_tag": agent < 2, "my_history": history}
            _write_run(
                root,
                model="mock",
                topology="mixing",
                run_id=c_id,
                meta=_meta(
                    run_id=c_id,
                    program="cm",
                    init_mode="prepared",
                    gate_passed=None,
                    t_gate=None,
                    prepared_state_valid=True,
                    cm_k=2,
                    committed_to=committed,
                    t_cm_start=0,
                    campaign="results-smoke",
                    incumbent_label=incumbent,
                    committed_ids=[0, 1],
                    H=12,
                    N=48,
                ),
                interactions=c_ix,
                extra_events=[prepared],
                simulation=sim,
            )
            out = Path(tmp) / "outputs"
            import analyze

            self.assertEqual(
                analyze.main(["--all", "--model", "mock", "--data", str(root), "--outputs", str(out)]),
                0,
            )
            model_out = out / "mock"
            spine = (
                "D1",
                "D5",
                "F1",
                "F3",
                "F4",
                "F5",
                "F7",
                "F13",
                "F14",
                "F18",
                "F24",
                "F-HUM",
                "T-H1",
                "T-H2",
                "T-H3",
            )
            smoke_plots = ("D1", "F3", "T-H1", "F13", "F18")
            for stem in spine:
                for suffix in (".json", ".csv"):
                    path = model_out / f"{stem}{suffix}"
                    self.assertTrue(path.exists(), path)
            for stem in smoke_plots:
                for suffix in (".png", ".pdf"):
                    path = model_out / f"{stem}{suffix}"
                    self.assertTrue(path.exists(), path)
            d5 = pd.read_csv(model_out / "D5.csv")
            self.assertAlmostEqual(float(d5.iloc[0]["memory_incumbent_share"]), 1.0)
            self.assertAlmostEqual(float(d5.iloc[0]["committed_policy_share"]), 2 / 48)
            self.assertNotEqual(json.loads((root / "runs" / "mock" / "mixing" / f"{e_id}.meta.json").read_text())["campaign"], "experiment")


class ScopedAbsenceTests(unittest.TestCase):
    def test_live_analysis_avoids_banned_dispatch(self):
        hits = []
        # pilot.py is a bounded descriptive analysis and intentionally uses
        # the current endpoint_eligible/eligibility_reason fields. The legacy guard applies to
        # counted thesis-analysis modules only.
        for path in LIVE_ANALYSIS.glob("*.py"):
            if path.name == "pilot.py":
                continue
            text = path.read_text(encoding="utf-8")
            for token in ('"complete"', "eligibility", "letter pool", "archive/pre-rebuild", "DEFAULT_WINDOW = 72"):
                if token in text:
                    hits.append(f"{path.name}:{token}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
