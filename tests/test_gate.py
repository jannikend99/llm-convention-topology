from __future__ import annotations

import unittest

from convention_topology.config import load_config
from convention_topology.gate import evaluate_phase1_gate, has_tracker_converged
from convention_topology.networks import adjacency_hash, get_interaction_network, lattice_neighbours
from convention_topology.simulation import run_phase1
from convention_topology.tracker import coordination_success, modal_label_in_window


class GateTests(unittest.TestCase):
  def test_config_uses_thesis_threshold(self) -> None:
    config = load_config()
    self.assertEqual(config.params.convergence_threshold, 0.95)
    self.assertEqual(config.params.max_phase1_interactions, 5000)
    self.assertEqual(config.params.convergence_time, 72)

  def test_gate_passes_at_95_percent_not_100_percent(self) -> None:
    window = 72
    # 69 successes = 95.83% — passes 0.95 gate, fails 1.0 gate
    outcomes = [0] * 3 + [1] * 69
    tracker = {"outcome": outcomes}
    self.assertTrue(
      has_tracker_converged(tracker, convergence_time=window, threshold=0.95)
    )
    self.assertFalse(
      has_tracker_converged(tracker, convergence_time=window, threshold=1.0)
    )

  def test_gate_fails_below_threshold(self) -> None:
    window = 72
    outcomes = [1] * 68 + [0] * 4
    tracker = {"outcome": outcomes}
    self.assertFalse(
      has_tracker_converged(tracker, convergence_time=window, threshold=0.95)
    )

  def test_phase1_censored_at_cap(self) -> None:
    def always_fail(_tracker: dict[str, list]) -> None:
      _tracker["outcome"].append(0)

    tracker, gate = run_phase1(
      always_fail,
      convergence_time=72,
      convergence_threshold=0.95,
      max_phase1_interactions=5000,
    )
    self.assertEqual(len(tracker["outcome"]), 5000)
    self.assertEqual(gate.eligibility, 0)
    self.assertEqual(gate.run_status, "censored")
    self.assertIsNone(gate.t_gate)

  def test_phase1_eligible_when_gate_met(self) -> None:
    def always_succeed(tracker: dict[str, list]) -> None:
      tracker["outcome"].append(1)

    tracker, gate = run_phase1(
      always_succeed,
      convergence_time=72,
      convergence_threshold=0.95,
      max_phase1_interactions=5000,
    )
    self.assertEqual(gate.eligibility, 1)
    self.assertEqual(gate.t_gate, 72)
    self.assertEqual(gate.run_status, "completed")

  def test_evaluate_gate_on_partial_window(self) -> None:
    tracker = {"outcome": [1] * 40}
    gate = evaluate_phase1_gate(
      tracker,
      convergence_time=72,
      threshold=0.95,
      max_phase1_interactions=5000,
    )
    self.assertEqual(gate.eligibility, 0)
    self.assertEqual(gate.run_status, "incomplete")


class NetworkTests(unittest.TestCase):
  def test_lattice_degree_four(self) -> None:
    neighbours = lattice_neighbours(1, 24)
    self.assertEqual(len(neighbours), 4)
    self.assertEqual(neighbours, [2, 3, 23, 24])

  def test_lattice_network_is_regular_degree_four(self) -> None:
    network = get_interaction_network("lattice", n=24)
    for node_id, player in network.items():
      self.assertEqual(len(player["neighbours"]), 4)

  def test_complete_network_has_n_minus_one_neighbours(self) -> None:
    network = get_interaction_network("complete", n=24)
    for player in network.values():
      self.assertEqual(len(player["neighbours"]), 23)

  def test_adjacency_hash_is_stable(self) -> None:
    network = get_interaction_network("lattice", n=24)
    self.assertEqual(
      adjacency_hash(network),
      adjacency_hash(get_interaction_network("lattice", n=24)),
    )

  def test_minority_size_nonzero_raises_not_implemented(self) -> None:
    # N2: minority_size is dead upstream code -- CM assignment goes through
    # simulation.py::swap_committed's injected-rng path instead.
    with self.assertRaises(NotImplementedError):
      get_interaction_network("complete", n=24, minority_size=1)

  def test_minority_size_zero_is_unaffected(self) -> None:
    # execute_run's path (always minority_size=0) must still work.
    network = get_interaction_network("complete", n=24, minority_size=0)
    self.assertEqual(len(network), 24)


class TrackerTests(unittest.TestCase):
  def test_coordination_success_threshold(self) -> None:
    self.assertTrue(coordination_success(100))
    self.assertFalse(coordination_success(-50))

  def test_modal_label_in_window(self) -> None:
    # Q strictly more frequent than M (4 vs 2) -- not a tie.
    tracker = {
      "answers": [["Q", "Q"], ["Q", "Q"], ["M", "M"]],
      "outcome": [1, 1, 0],
    }
    self.assertEqual(modal_label_in_window(tracker, window_size=3), "Q")

  def test_modal_label_in_window_exact_tie_breaks_lexicographically(self) -> None:
    # M2: the production incumbent/committed_to path must use the same
    # deterministic lexicographic tie-break as dvs.incumbent_label, not
    # Counter.most_common()'s insertion-order tie-break (which would pick
    # "Q" here, since it appears first). Lexicographic order picks "M"
    # ("M" < "Q"), regardless of insertion order.
    tracker = {
      "answers": [["Q", "Q"], ["M", "M"]],
      "outcome": [1, 1],
    }
    self.assertEqual(modal_label_in_window(tracker, window_size=2), "M")


if __name__ == "__main__":
  unittest.main()
