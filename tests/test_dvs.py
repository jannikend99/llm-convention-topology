from __future__ import annotations

import math
import unittest

from convention_topology.dvs import (
    dominant_share,
    flip,
    flip_50,
    incumbent_label,
    label_shares,
    rounds_to_gate,
    shannon_entropy,
    time_to_flip,
)


def _tracker(answers, outcomes):
    return {"answers": answers, "outcome": outcomes}


class LabelSharesTests(unittest.TestCase):
    def test_known_100_of_144_split(self):
        # 50 (A, A) pairs = 100 A emissions, 22 (B, B) pairs = 44 B emissions -> 72 interactions, 144 emissions.
        answers = [("A", "A")] * 50 + [("B", "B")] * 22
        outcomes = [1] * 72
        tracker = _tracker(answers, outcomes)
        shares = label_shares(tracker, window=72)
        self.assertAlmostEqual(shares["A"], 100 / 144)
        self.assertAlmostEqual(shares["B"], 44 / 144)
        self.assertEqual(round(shares["A"] * 144), 100)
        self.assertEqual(dominant_share(tracker, window=72), 100 / 144)

    def test_denominator_is_144_for_default_window(self):
        answers = [("A", "B")] * 72
        tracker = _tracker(answers, [1] * 72)
        shares = label_shares(tracker, window=72)
        total_emissions = sum(round(share * 144) for share in shares.values())
        self.assertEqual(total_emissions, 144)

    def test_too_few_interactions_raises(self):
        tracker = _tracker([("A", "A")] * 5, [1] * 5)
        with self.assertRaises(ValueError):
            label_shares(tracker, window=72)


class ShannonEntropyTests(unittest.TestCase):
    def test_uniform_distribution_gives_ln2(self):
        tracker = _tracker([("A", "B"), ("A", "B")], [1, 1])
        self.assertAlmostEqual(shannon_entropy(tracker, window=2), math.log(2))

    def test_degenerate_distribution_gives_zero(self):
        tracker = _tracker([("A", "A"), ("A", "A")], [1, 1])
        self.assertAlmostEqual(shannon_entropy(tracker, window=2), 0.0)


class RoundsToGateTests(unittest.TestCase):
    def test_eligible_run_returns_t_gate(self):
        self.assertEqual(rounds_to_gate({"t_gate": 180}), 180)

    def test_censored_run_returns_cap(self):
        self.assertEqual(rounds_to_gate({"t_gate": None}), 5000)


class IncumbentLabelTests(unittest.TestCase):
    def test_modal_label_at_gate(self):
        answers = [("A", "A")] * 5 + [("B", "B")] * 2
        tracker = _tracker(answers, [1] * 7)
        self.assertEqual(incumbent_label(tracker, t_gate=7, window=7), "A")

    def test_tie_break_is_lexicographic(self):
        # Equal counts of A and B; insertion order favors B (appears first),
        # but the lock requires deterministic lexicographic tie-break -> "A".
        answers = [("B", "B"), ("A", "A")]
        tracker = _tracker(answers, [1, 1])
        self.assertEqual(incumbent_label(tracker, t_gate=2, window=2), "A")


class FlipTests(unittest.TestCase):
    def test_flip_when_window_converges_on_committed_label(self):
        answers = [("B", "B")] * 6  # committed_to = "B"
        outcomes = [1] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(flip(tracker, committed_to="B", t_start=0, window=6), 1)

    def test_non_flip_when_success_never_reaches_threshold(self):
        answers = [("A", "B")] * 6  # every pair mismatched -> 0 success
        outcomes = [0] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(flip(tracker, committed_to="B", t_start=0, window=6), 0)

    def test_re_convergence_on_incumbent_is_not_a_flip(self):
        # High success, but the modal label is the pre-existing incumbent "A",
        # not committed_to "B" -- single non-flip category (no flip_resisted).
        answers = [("A", "A")] * 6
        outcomes = [1] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(flip(tracker, committed_to="B", t_start=0, window=6), 0)

    def test_time_to_flip_known_flip_fixture(self):
        # First 6 interactions mismatched (no flip), next 6 converge on "B".
        answers = [("A", "B")] * 6 + [("B", "B")] * 6
        outcomes = [0] * 6 + [1] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(time_to_flip(tracker, committed_to="B", t_start=0, window=6, censor_value=100), 12)

    def test_time_to_flip_censored_at_horizon(self):
        answers = [("A", "B")] * 20
        outcomes = [0] * 20
        tracker = _tracker(answers, outcomes)
        self.assertEqual(time_to_flip(tracker, committed_to="B", t_start=0, window=6, censor_value=20), 20)

    def test_flip_raises_on_tracker_shorter_than_t_start_plus_window(self):
        # N5: a misconfigured/short Phase 2 must fail loudly, not silently score 0.
        answers = [("A", "B")] * 4
        outcomes = [0] * 4
        tracker = _tracker(answers, outcomes)
        with self.assertRaises(ValueError):
            flip(tracker, committed_to="B", t_start=0, window=6)

    def test_flip_boundary_exact_length_does_not_raise(self):
        answers = [("B", "B")] * 6
        outcomes = [1] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(flip(tracker, committed_to="B", t_start=0, window=6), 1)

    def test_time_to_flip_raises_on_tracker_shorter_than_t_start_plus_window(self):
        answers = [("A", "B")] * 4
        outcomes = [0] * 4
        tracker = _tracker(answers, outcomes)
        with self.assertRaises(ValueError):
            time_to_flip(tracker, committed_to="B", t_start=0, window=6, censor_value=100)

    def test_time_to_flip_boundary_exact_length_does_not_raise(self):
        answers = [("A", "B")] * 6
        outcomes = [0] * 6
        tracker = _tracker(answers, outcomes)
        self.assertEqual(
            time_to_flip(tracker, committed_to="B", t_start=0, window=6, censor_value=100), 100
        )


class Flip50Tests(unittest.TestCase):
    def test_exactly_50_percent_is_not_a_flip(self):
        simulation = {
            1: {"committed_tag": False, "my_history": ["B"] * 6},
            2: {"committed_tag": False, "my_history": ["B"] * 6},
            3: {"committed_tag": False, "my_history": ["A"] * 6},
            4: {"committed_tag": False, "my_history": ["A"] * 6},
            5: {"committed_tag": True, "my_history": ["B"] * 6},
        }
        self.assertEqual(flip_50(simulation, committed_to="B", window=6), 0)

    def test_majority_over_50_percent_is_a_flip(self):
        simulation = {
            1: {"committed_tag": False, "my_history": ["B"] * 6},
            2: {"committed_tag": False, "my_history": ["B"] * 6},
            3: {"committed_tag": False, "my_history": ["B"] * 6},
            4: {"committed_tag": False, "my_history": ["A"] * 6},
        }
        self.assertEqual(flip_50(simulation, committed_to="B", window=6), 1)

    def test_no_noncommitted_agents_returns_zero(self):
        simulation = {1: {"committed_tag": True, "my_history": ["B"] * 6}}
        self.assertEqual(flip_50(simulation, committed_to="B", window=6), 0)


if __name__ == "__main__":
    unittest.main()
