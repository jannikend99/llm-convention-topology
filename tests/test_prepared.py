"""Tests for Ashery prepared-population init (CM program)."""

from __future__ import annotations

import unittest

from convention_topology.prepared import (
    PreparedInitError,
    assert_prepared,
    committed_label,
    make_prepared_population,
    set_initial_state,
)
from convention_topology.networks import get_interaction_network


class PreparedPopulationTests(unittest.TestCase):
    def test_histories_filled_with_incumbent(self):
        simulation, tracker, convergence = make_prepared_population(
            "complete",
            n=8,
            graph_seed=1,
            rewards=(-50, 100),
            options=["Q", "M"],
            memory_size=5,
            incumbent_index=0,
        )
        self.assertEqual(len(tracker["outcome"]), 0)
        self.assertEqual(convergence["converged_index"], 0)
        self.assertEqual(convergence["incumbent_label"], "Q")
        self.assertEqual(convergence["committed_to"], "M")
        for player in simulation.values():
            self.assertEqual(player["my_history"], ["Q"] * 5)
            self.assertEqual(player["partner_history"], ["Q"] * 5)
            self.assertFalse(player["committed_tag"])

    def test_incumbent_index_one_swaps_labels(self):
        _, _, convergence = make_prepared_population(
            "lattice",
            n=8,
            graph_seed=2,
            rewards=(-50, 100),
            options=["Q", "M"],
            memory_size=3,
            incumbent_index=1,
        )
        self.assertEqual(convergence["incumbent_label"], "M")
        self.assertEqual(convergence["committed_to"], "Q")

    def test_assert_prepared_rejects_corrupt_history(self):
        simulation = get_interaction_network("complete", n=4, graph_seed=0)
        set_initial_state(simulation, (-50, 100), ["Q", "M"], 5, 0)
        simulation[1]["my_history"][0] = "M"
        with self.assertRaises(PreparedInitError):
            assert_prepared(simulation, ["Q", "M"], 5, 0)

    def test_committed_label_requires_binary_options(self):
        with self.assertRaises(PreparedInitError):
            committed_label(["A", "B", "C"], 0)


if __name__ == "__main__":
    unittest.main()
