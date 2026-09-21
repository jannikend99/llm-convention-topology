from __future__ import annotations

import random
import unittest

from convention_topology.config import TOPOLOGIES, load_config
from convention_topology.gate import MIN_SUCCESSES, first_gate_time, has_tracker_converged, min_gate_successes
from convention_topology.networks import adjacency_hash, get_interaction_network
from convention_topology.orchestration import cell_grid
from convention_topology.pool import draw_pool, options_for_program
from convention_topology.seeds import ENVIRONMENT_TAGS, environment_seed, graph_seed, substream


class ProtocolIdentityTests(unittest.TestCase):
    def test_five_campaign_graphs_and_hashes(self):
        config = load_config()
        n = config["protocol"]["N"]
        hashes = {}
        for topology in TOPOLOGIES:
            seed = graph_seed(config["run"]["base_seed"], topology)
            net, attempts = get_interaction_network(topology, n=n, graph_seed=seed)
            self.assertEqual(len(net), 48)
            self.assertGreaterEqual(attempts, 1)
            hashes[topology] = adjacency_hash(net)
            again, _ = get_interaction_network(topology, n=n, graph_seed=seed)
            self.assertEqual(adjacency_hash(again), hashes[topology])
        self.assertEqual(len(set(hashes.values())), 5)
        self.assertIn("mixing", hashes)
        self.assertNotIn("complete", hashes)

    def test_pool_and_shared_option_order(self):
        config = load_config()
        pool = draw_pool(seed=config["pool"]["seed"])
        self.assertEqual(len(pool), 10)
        self.assertTrue(all(len(token) == 5 and token.islower() for token in pool))
        self.assertEqual(options_for_program(pool, "emergence"), pool)
        self.assertEqual(options_for_program(pool, "cm"), pool[:2])
        rng = random.Random(0)
        order = list(pool)
        rng.shuffle(order)
        self.assertEqual(sorted(order), sorted(pool))

    def test_environment_seeds_common_across_models(self):
        a = environment_seed(1, "emergence", "mixing", None, 0)
        b = environment_seed(1, "emergence", "mixing", None, 0)
        self.assertEqual(a, b)
        self.assertNotEqual(a, environment_seed(1, "emergence", "lattice", None, 0))
        tags = [substream(a, tag) for tag in ENVIRONMENT_TAGS]
        self.assertEqual(len(set(tags)), 4)

    def test_study1_cm_k_is_null(self):
        config = load_config()
        rows = cell_grid(config, program="emergence")
        self.assertTrue(all(row["cm_k"] is None for row in rows))
        self.assertEqual(len(rows), 5 * 32)

    def test_study2_grid(self):
        config = load_config()
        rows = cell_grid(config, program="cm")
        self.assertEqual(len(rows), 5 * 3 * 32)
        self.assertEqual({row["cm_k"] for row in rows}, {5, 10, 14})

    def test_integer_gate(self):
        outcomes = [1] * 136 + [0] * 8
        self.assertEqual(len(outcomes), 144)
        self.assertFalse(has_tracker_converged({"outcome": outcomes}))
        outcomes[0] = 1
        outcomes = [1] * 137 + [0] * 7
        self.assertTrue(has_tracker_converged({"outcome": outcomes}))
        self.assertEqual(MIN_SUCCESSES, 137)
        late = [0] * 10 + [1] * 137
        self.assertEqual(first_gate_time(late), 147)
        short = [1] * 69 + [0] * 3
        self.assertEqual(min_gate_successes(72), 69)
        self.assertTrue(has_tracker_converged({"outcome": short}, window=72))
        self.assertFalse(has_tracker_converged({"outcome": [1] * 68 + [0] * 4}, window=72))
