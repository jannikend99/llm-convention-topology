from __future__ import annotations

import json
import tempfile
import unittest
import warnings
from pathlib import Path

import pandas as pd

import analyze
from convention_topology.analysis.common import critical_mass, eligibility_table, load_run_table
from convention_topology.analysis.cross_model import cross_model_summary
from convention_topology.analysis.dispatch import run_h3a
from convention_topology.analysis.h1 import TAU, h1_analysis
from convention_topology.analysis.h2 import h2_analysis
from convention_topology.analysis.h3a import h3a_analysis, sensitivity_50_agreement
from convention_topology.analysis.h3b import h3b_analysis
from convention_topology.analysis.h4 import h4_analysis
from convention_topology.persistence import META_FIELDS, save_run_pickle, write_meta


def _runs_df(rows):
    return pd.DataFrame(rows)


class EligibilityTableTests(unittest.TestCase):
    def test_counts_by_topology_and_model(self):
        runs = _runs_df(
            [
                {"topology": "complete", "model_shorthand": "mock", "eligibility": 1, "run_status": "completed"},
                {"topology": "complete", "model_shorthand": "mock", "eligibility": 0, "run_status": "censored"},
                {"topology": "complete", "model_shorthand": "mock", "eligibility": 0, "run_status": "failed"},
                {"topology": "lattice", "model_shorthand": "mock", "eligibility": 1, "run_status": "completed"},
            ]
        )
        table = eligibility_table(runs).set_index(["topology", "model_shorthand"])
        self.assertEqual(table.loc[("complete", "mock"), "attempted"], 3)
        self.assertEqual(table.loc[("complete", "mock"), "eligible"], 1)
        self.assertEqual(table.loc[("complete", "mock"), "censored"], 1)
        self.assertEqual(table.loc[("complete", "mock"), "failed"], 1)
        self.assertEqual(table.loc[("lattice", "mock"), "attempted"], 1)

    def test_empty_runs_returns_empty_table(self):
        self.assertTrue(eligibility_table(_runs_df([])).empty)


class CriticalMassTests(unittest.TestCase):
    def test_smallest_k_with_flip_rate_at_least_half(self):
        runs = _runs_df(
            [
                {"topology": "complete", "model_shorthand": "mock", "cm_k": 1, "eligibility": 1, "flip": 0},
                {"topology": "complete", "model_shorthand": "mock", "cm_k": 1, "eligibility": 1, "flip": 0},
                {"topology": "complete", "model_shorthand": "mock", "cm_k": 2, "eligibility": 1, "flip": 1},
                {"topology": "complete", "model_shorthand": "mock", "cm_k": 2, "eligibility": 1, "flip": 0},
            ]
        )
        result = critical_mass(runs).set_index(["topology", "model_shorthand"])
        self.assertEqual(result.loc[("complete", "mock"), "critical_mass"], 2)

    def test_no_critical_mass_reached_gives_none(self):
        runs = _runs_df(
            [
                {"topology": "lattice", "model_shorthand": "mock", "cm_k": 1, "eligibility": 1, "flip": 0},
                {"topology": "lattice", "model_shorthand": "mock", "cm_k": 2, "eligibility": 1, "flip": 0},
            ]
        )
        result = critical_mass(runs).set_index(["topology", "model_shorthand"])
        self.assertTrue(pd.isna(result.loc[("lattice", "mock"), "critical_mass"]))

    def test_ineligible_runs_excluded(self):
        runs = _runs_df(
            [
                {"topology": "complete", "model_shorthand": "mock", "cm_k": 1, "eligibility": 0, "flip": 1},
            ]
        )
        self.assertTrue(critical_mass(runs).empty)


class H1AnalysisTests(unittest.TestCase):
    def test_shares_well_above_tau_reject_h0(self):
        shares = [0.95, 0.96, 0.97, 0.94, 0.98, 0.99, 0.93, 0.96]
        result = h1_analysis(shares)
        self.assertGreater(result["t_stat"], 0)
        self.assertLess(result["p_one_tailed"], 0.05)
        self.assertTrue(result["reject_h0"])
        self.assertEqual(result["regime_proportion_gt_tau"], 1.0)
        self.assertGreater(result["ci_95"][0], TAU)

    def test_shares_at_tau_do_not_reject_h0(self):
        shares = [0.90, 0.89, 0.91, 0.90, 0.88, 0.92, 0.90, 0.91]
        result = h1_analysis(shares)
        self.assertGreaterEqual(result["p_one_tailed"], 0.05)
        self.assertFalse(result["reject_h0"])

    def test_empty_input_returns_n_zero(self):
        self.assertEqual(h1_analysis([])["n"], 0)


class H2AnalysisTests(unittest.TestCase):
    def test_sparse_topologies_significantly_below_mixing(self):
        mixing = [0.95] * 10
        lattice = [0.55, 0.5, 0.6, 0.52, 0.58, 0.5, 0.6, 0.55, 0.5, 0.53]
        random_ = [0.6, 0.62, 0.58, 0.61, 0.59, 0.6, 0.57, 0.63, 0.6, 0.58]
        result = h2_analysis(mixing, lattice, random_)
        self.assertTrue(result["lattice_vs_mixing"]["reject_h0"])
        self.assertTrue(result["random_regular_vs_mixing"]["reject_h0"])
        self.assertLess(result["lattice_vs_mixing"]["welch_p_one_tailed"], 0.05)

    def test_no_difference_does_not_reject_h0(self):
        mixing = [0.90, 0.91, 0.89, 0.92, 0.88, 0.91, 0.90, 0.89]
        lattice = [0.91, 0.90, 0.92, 0.88, 0.90, 0.89, 0.91, 0.90]
        result = h2_analysis(mixing, lattice, [0.90] * 8)
        self.assertFalse(result["lattice_vs_mixing"]["reject_h0"])

    def test_entropy_reported_descriptively(self):
        result = h2_analysis([0.9] * 5, [0.5] * 5, [0.6] * 5, mixing_entropy=[0.1, 0.2], lattice_entropy=[0.5, 0.6])
        self.assertEqual(result["entropy_descriptive"]["mixing"]["n"], 2)
        self.assertAlmostEqual(result["entropy_descriptive"]["mixing"]["mean"], 0.15)
        self.assertIsNone(result["entropy_descriptive"]["random_regular"])


class H3aAnalysisTests(unittest.TestCase):
    def test_increasing_flip_probability_with_cm_k_is_confirmatory_positive_coef(self):
        cm_k = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6]
        flip = [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]
        result = h3a_analysis(cm_k, flip)
        self.assertEqual(result["label"], "confirmatory")
        self.assertGreater(result["linear_logit_coef"], 0)

    def test_tiny_n_labeled_exploratory(self):
        result = h3a_analysis([1, 2], [0, 1])
        self.assertEqual(result["label"], "exploratory")

    def test_no_variance_in_flip_labeled_exploratory(self):
        result = h3a_analysis([1, 2, 3, 4, 5, 6, 1, 2, 3, 4], [0] * 10)
        self.assertEqual(result["label"], "exploratory")

    def test_primary_contrast_is_gam_vs_linear_not_linear_vs_intercept(self):
        """B1: the locked primary test is GAM-vs-linear (03_Methods.tex:228-229 / WORKING.md:385)."""
        cm_k = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6]
        flip = [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]
        result = h3a_analysis(cm_k, flip)
        self.assertIn("lr_stat_gam_vs_linear", result)
        self.assertIn("lr_p_gam_vs_linear", result)
        self.assertIn("lr_df_gam_vs_linear", result)
        self.assertIsNotNone(result["lr_stat_gam_vs_linear"])
        self.assertIsNotNone(result["lr_p_gam_vs_linear"])
        self.assertGreaterEqual(result["lr_stat_gam_vs_linear"], 0.0)
        self.assertTrue(0.0 <= result["lr_p_gam_vs_linear"] <= 1.0)

    def test_linear_vs_intercept_is_renamed_and_secondary(self):
        cm_k = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6]
        flip = [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]
        result = h3a_analysis(cm_k, flip)
        self.assertIn("lr_stat_linear_vs_intercept", result)
        self.assertIn("lr_p_linear_vs_intercept", result)
        # Old unqualified names must not resurface as the primary claim.
        self.assertNotIn("lr_stat_vs_intercept", result)
        self.assertNotIn("lr_p_vs_intercept", result)

    def test_sensitivity_50_exports_csv_not_json(self):
        # R2-m2: flip_agreement is locked to .csv (WORKING.md §8), not .json.
        rows = [
            {"topology": "complete", "cm_k": k, "flip": f, "flip_50": f}
            for k, f in zip([1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4], [0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1])
        ]
        runs_df = _runs_df(rows)
        with tempfile.TemporaryDirectory() as tmp:
            outputs_dir = Path(tmp)
            run_h3a(runs_df, outputs_dir, sensitivity_50=True)
            self.assertTrue((outputs_dir / "flip_agreement.csv").exists())
            self.assertFalse((outputs_dir / "flip_agreement.json").exists())

    def test_flip_curve_present_on_confirmatory_fit(self):
        cm_k = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 6]
        flip = [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1]
        result = h3a_analysis(cm_k, flip)
        self.assertIsNotNone(result["flip_curve"])
        self.assertEqual([row["cm_k"] for row in result["flip_curve"]], [1, 2, 3, 4, 5, 6])
        for row in result["flip_curve"]:
            self.assertTrue(0.0 <= row["predicted_flip_prob"] <= 1.0)

    def test_degenerate_n_returns_exploratory_dict_not_crash(self):
        result = h3a_analysis([1, 1, 1, 1, 1, 1, 1, 1], [0, 1, 0, 1, 0, 1, 0, 1])
        self.assertIn(result["label"], ("exploratory",))
        self.assertIn("reason", result)

    def test_unexpected_exception_type_is_not_swallowed(self):
        # N7: only the narrow fit-failure tuple is caught; anything else
        # (e.g. a bad call from a future refactor) must still propagate.
        import unittest.mock as mock

        cm_k = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]
        flip = [0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1]
        with mock.patch("convention_topology.analysis.h3a.sm.Logit", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                h3a_analysis(cm_k, flip)


class Sensitivity50Tests(unittest.TestCase):
    def test_known_agreement_rate(self):
        result = sensitivity_50_agreement([1, 0, 1, 1], [1, 0, 0, 1])
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["agreement_rate"], 0.75)

    def test_empty_returns_none(self):
        result = sensitivity_50_agreement([], [])
        self.assertIsNone(result["agreement_rate"])


class H3bAnalysisTests(unittest.TestCase):
    def test_confirmatory_label_when_eligibility_floor_met(self):
        rows = []
        for topology in ("complete", "lattice"):
            for k in range(1, 7):
                for i in range(8):
                    p = min(0.9, 0.05 + 0.15 * k) if topology == "complete" else 0.1
                    rows.append({"topology": topology, "cm_k": k, "flip": 1 if (i + k) % 3 == 0 and p > 0.3 else 0})
        df = pd.DataFrame(rows)
        result = h3b_analysis(df)
        self.assertEqual(result["label"], "confirmatory")
        self.assertEqual(result["n_topologies"], 2)

    def test_exploratory_label_below_eligibility_floor(self):
        df = pd.DataFrame(
            [{"topology": "complete", "cm_k": k, "flip": k % 2} for k in range(1, 6)]
        )
        result = h3b_analysis(df)
        self.assertEqual(result["label"], "exploratory")

    def test_zero_count_cell_does_not_slip_through_as_confirmatory(self):
        """M3: a (topology, cm_k) cell with zero rows must not be invisible to the confirmatory check."""
        rows = []
        for topology in ("complete", "lattice"):
            for k in range(1, 7):
                if topology == "lattice" and k == 6:
                    continue  # entire cell censored/failed -- zero eligible rows
                for i in range(8):
                    rows.append({"topology": topology, "cm_k": k, "flip": (i + k) % 2})
        df = pd.DataFrame(rows)
        result = h3b_analysis(df)
        # Only "complete" has full k-coverage at the floor; "lattice" is missing
        # k=6 entirely, so only 1 topology qualifies -- must not be confirmatory.
        self.assertNotEqual(result["label"], "confirmatory")

    def test_full_grid_at_floor_is_confirmatory(self):
        rows = []
        for topology in ("complete", "lattice"):
            for k in range(1, 7):
                for i in range(8):
                    rows.append({"topology": topology, "cm_k": k, "flip": (i + k) % 2})
        df = pd.DataFrame(rows)
        result = h3b_analysis(df)
        self.assertEqual(result["label"], "confirmatory")

    def test_unexpected_exception_type_is_not_swallowed(self):
        # N7: only the narrow fit-failure tuple is caught in h3b too.
        import unittest.mock as mock

        rows = []
        for topology in ("complete", "lattice"):
            for k in range(1, 7):
                for i in range(8):
                    rows.append({"topology": topology, "cm_k": k, "flip": (i + k) % 2})
        df = pd.DataFrame(rows)
        with mock.patch("convention_topology.analysis.h3b.sm.Logit", side_effect=TypeError("boom")):
            with self.assertRaises(TypeError):
                h3b_analysis(df)


class H4AnalysisTests(unittest.TestCase):
    def test_known_frequencies_and_chi_square(self):
        result = h4_analysis(["A", "A", "A", "B"])
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["frequencies"]["A"], 0.75)
        self.assertAlmostEqual(result["frequencies"]["B"], 0.25)
        self.assertIn("chi2_p", result)

    def test_uniform_distribution_high_p_value(self):
        result = h4_analysis(["A", "B"])
        self.assertAlmostEqual(result["chi2_p"], 1.0)

    def test_empty_input(self):
        self.assertEqual(h4_analysis([])["n"], 0)


class CrossModelTests(unittest.TestCase):
    def test_descriptive_summary_per_model_no_pooling(self):
        df_a = pd.DataFrame(
            [
                {"topology": "complete", "model_shorthand": "llama31", "cm_k": 1, "eligibility": 1,
                 "flip": 0, "dominant_share": 0.9},
                {"topology": "complete", "model_shorthand": "llama31", "cm_k": 2, "eligibility": 1,
                 "flip": 1, "dominant_share": 0.95},
            ]
        )
        df_b = pd.DataFrame(
            [
                {"topology": "complete", "model_shorthand": "qwen25", "cm_k": 1, "eligibility": 1,
                 "flip": 1, "dominant_share": 0.8},
            ]
        )
        summary = cross_model_summary({"llama31": df_a, "qwen25": df_b})
        self.assertEqual(summary["llama31"]["n_eligible"], 2)
        self.assertAlmostEqual(summary["llama31"]["mean_dominant_share"], 0.925)
        self.assertEqual(summary["qwen25"]["n_eligible"], 1)
        # Each model's summary is computed independently -- no cross-model pooling.
        self.assertNotEqual(summary["llama31"]["mean_dominant_share"], summary["qwen25"]["mean_dominant_share"])

    def test_mean_dominant_share_includes_censored_runs(self):
        # H1/H2 pool all attempted Phase 1 trajectories, censored included
        # (03_Methods.tex:212,246) -- a gate-censored run still has a
        # dominant_share (post R2-B1) and must count toward this descriptive
        # mean, even though it's excluded from n_eligible/flip_rate.
        df = pd.DataFrame(
            [
                {"topology": "lattice", "model_shorthand": "llama31", "cm_k": 1, "eligibility": 1,
                 "flip": 1, "dominant_share": 0.95},
                {"topology": "lattice", "model_shorthand": "llama31", "cm_k": None, "eligibility": 0,
                 "flip": None, "dominant_share": 0.30},  # censored: low share, no flip
            ]
        )
        summary = cross_model_summary({"llama31": df})
        self.assertEqual(summary["llama31"]["n_eligible"], 1)
        self.assertEqual(summary["llama31"]["n_attempted"], 2)
        self.assertAlmostEqual(summary["llama31"]["mean_dominant_share"], (0.95 + 0.30) / 2)
        # A summary that only looked at eligible rows would report 0.95 --
        # overstating coordination relative to the Methods-locked H1/H2 pool.
        self.assertNotAlmostEqual(summary["llama31"]["mean_dominant_share"], 0.95)
        self.assertAlmostEqual(summary["llama31"]["flip_rate"], 1.0)


class LoadRunTableN3Tests(unittest.TestCase):
    """N3: DVs must be derived from the exact meta path scan_meta_paths found, not a reconstructed path."""

    def test_sidecar_in_nonstandard_location_still_yields_pickle_dvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            # Deliberately not persistence.run_paths's model/topology layout --
            # a recovered file or a future layout change.
            nested_dir = data_dir / "runs" / "recovered" / "nested" / "elsewhere"
            nested_dir.mkdir(parents=True)
            meta_path = nested_dir / "weird_run_id.meta.json"
            pickle_path = nested_dir / "weird_run_id.pkl"

            meta = {field: None for field in META_FIELDS}
            meta.update(
                run_id="weird_run_id",
                topology="complete",
                cm_k=1,
                model_shorthand="mock",
                model_id="mock",
                run_status="completed",
                eligibility=1,
                t_gate=72,
                incumbent_label="A",
                committed_to="B",
            )
            write_meta(meta_path, meta)
            # t_gate=72 + a full trailing window (72) of Phase 2 -- flip()/
            # time_to_flip() need >= t_gate + window interactions (N5 guard).
            answers = [("B", "B")] * 144
            tracker = {"players": [[1, 2]] * 144, "answers": answers, "outcome": [1] * 144}
            simulation = {1: {"committed_tag": False, "my_history": ["B"] * 144}}
            save_run_pickle(pickle_path, simulation, tracker, {"converged_index": 72, "committed_to": "B"})

            runs_df = load_run_table(data_dir, model_filter="mock")

        self.assertEqual(len(runs_df), 1)
        row = runs_df.iloc[0]
        self.assertIsNotNone(row["dominant_share"])
        self.assertIsNotNone(row["flip"])


class Phase1WindowDVTests(unittest.TestCase):
    """R2-B1: H1/H2's dominant_share/shannon_entropy must reflect the Phase-1-end
    window (trailing 3N at the gate), not the raw tracker's tail -- which, for a
    completed run, is the *end of Phase 2* after committed-minority injection."""

    def _write_run(self, tmp: Path, *, run_status: str, t_gate: int | None, answers, outcome, committed_to=None):
        data_dir = Path(tmp) / "data"
        run_dir = data_dir / "runs" / "mock" / "complete"
        run_dir.mkdir(parents=True)
        meta_path = run_dir / "run.meta.json"
        pickle_path = run_dir / "run.pkl"

        meta = {field: None for field in META_FIELDS}
        meta.update(
            run_id="run", topology="complete", cm_k=1, model_shorthand="mock", model_id="mock",
            run_status=run_status, eligibility=1 if run_status == "completed" else 0,
            t_gate=t_gate, incumbent_label="A", committed_to=committed_to,
        )
        write_meta(meta_path, meta)
        tracker = {"players": [[1, 2]] * len(answers), "answers": answers, "outcome": outcome}
        simulation = {1: {"committed_tag": False, "my_history": [a[0] for a in answers]}}
        save_run_pickle(pickle_path, simulation, tracker, {"converged_index": t_gate, "committed_to": committed_to})
        return data_dir

    def test_dominant_share_uses_phase1_window_not_tracker_tail(self):
        # Phase 1 (72 interactions): 50 "A" pairs + 22 "B" pairs -> share_A = 100/144.
        phase1 = [("A", "A")] * 50 + [("B", "B")] * 22
        # Phase 2 (72 interactions): 10 "A" pairs + 62 "B" pairs -> share_B = 124/144.
        phase2 = [("A", "A")] * 10 + [("B", "B")] * 62
        answers = phase1 + phase2
        outcome = [1] * len(answers)  # 100% success -- trivially clears the 0.95 flip threshold

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = self._write_run(
                tmp, run_status="completed", t_gate=72, answers=answers, outcome=outcome, committed_to="B",
            )
            runs_df = load_run_table(data_dir, model_filter="mock")

        row = runs_df.iloc[0]
        self.assertAlmostEqual(row["dominant_share"], 100 / 144, places=6)
        # The bug computed this from the tracker's raw tail (Phase 2) instead.
        self.assertNotAlmostEqual(row["dominant_share"], 124 / 144, places=2)

    def test_censored_run_contributes_dominant_share_to_h1(self):
        answers = [("A", "A")] * 50 + [("B", "B")] * 22  # 72 interactions, never gated
        outcome = [0] * len(answers)  # never reached the 0.95 gate -- that's why it censored

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = self._write_run(tmp, run_status="censored", t_gate=None, answers=answers, outcome=outcome)
            runs_df = load_run_table(data_dir, model_filter="mock")

        row = runs_df.iloc[0]
        self.assertIsNotNone(row["dominant_share"])
        self.assertAlmostEqual(row["dominant_share"], 100 / 144, places=6)
        self.assertIsNone(row["flip"])  # Phase 2 concept -- censored runs never enter Phase 2

        mixing = runs_df[(runs_df["topology"] == "complete") & runs_df["dominant_share"].notna()]
        self.assertEqual(len(mixing), 1)  # censored run must reach run_h1's input, not be dropped


class AnalyzeCliTests(unittest.TestCase):
    def test_all_on_mocked_pilot_batch_emits_h1_through_h4_without_error(self):
        from convention_topology.config import derive_seeds, load_config, resolve_model
        from convention_topology.orchestration import GridCell, run_batch

        with tempfile.TemporaryDirectory() as tmp:
            data_dir, logs_dir, outputs_dir = Path(tmp) / "data", Path(tmp) / "logs", Path(tmp) / "outputs"
            config = load_config()
            # Keep the thesis-locked N=24 (default): dvs.py's DEFAULT_WINDOW=72
            # is a fixed Methods constant (3N at N=24), not derived from
            # config.n -- a smaller N here would make Phase 1 gate before 72
            # interactions exist, so H1/H2's Phase-1-window DV (R2-B1) would
            # legitimately be None for every row. Mocked runs at N=24 are
            # still fast (~0.1s/run).
            model_spec = resolve_model(config, "mock")
            cells = [
                GridCell(topology, i, ((i - 1) % 6) + 1, *derive_seeds(1, topology, ((i - 1) % 6) + 1, i))
                for topology in ("complete", "lattice", "random_regular")
                for i in range(1, 3)
            ]
            run_batch(
                config, model_spec, cells, data_dir=data_dir, logs_dir=logs_dir,
                mock_policy="imitate_modal", workers=1, retry_failed=False,
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # small-n perfect-separation warnings expected on mocked data
                exit_code = analyze.main(
                    ["--all", "--model", "mock", "--data", str(data_dir), "--outputs", str(outputs_dir)]
                )
            self.assertEqual(exit_code, 0)

            for name in (
                "h1.json", "h1.csv", "h2.json", "h2.csv", "h3a.json", "h3a.csv",
                "h3b.json", "h3b.csv", "h4.json", "h4.csv", "eligibility.csv",
            ):
                path = outputs_dir / "mock" / name
                self.assertTrue(path.exists(), f"missing {path}")

            with (outputs_dir / "mock" / "h1.json").open() as handle:
                h1 = json.load(handle)
            self.assertGreater(h1["n"], 0)


if __name__ == "__main__":
    unittest.main()
