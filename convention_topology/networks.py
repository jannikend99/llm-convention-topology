from __future__ import annotations

import hashlib
import random
from typing import Any

import networkx as nx


def _empty_player() -> dict[str, Any]:
    return {
        "my_history": [],
        "partner_history": [],
        "interactions": [],
        "score": 0,
        "score_history": [],
        "outcome": [],
        "committed_tag": False,
    }


def lattice_neighbours(node_id: int, n: int) -> list[int]:
    """1D ring lattice (Centola 2015): nearest + next-nearest, degree 4."""
    index = node_id - 1
    neighbours: set[int] = set()
    for offset in (1, 2):
        neighbours.add((index - offset) % n + 1)
        neighbours.add((index + offset) % n + 1)
    return sorted(neighbours)


def adjacency_hash(network: dict[int, dict[str, Any]]) -> str:
    edge_pairs: list[tuple[int, int]] = []
    for node_id, player in sorted(network.items()):
        for neighbour in sorted(player["neighbours"]):
            if node_id < neighbour:
                edge_pairs.append((node_id, neighbour))
    digest = hashlib.sha256(repr(edge_pairs).encode("utf-8")).hexdigest()
    return digest[:16]


def get_interaction_network(
    network_type: str,
    *,
    n: int = 24,
    degree: int = 4,
    graph_seed: int | None = None,
    minority_size: int = 0,
) -> dict[int, dict[str, Any]]:
    """
    Build the fixed interaction graph for one population run.

    Supported topologies: complete (mixing), random_regular, lattice.
    """
    if minority_size != 0:
        # N2 (code review, minimal-edit lock -- this module is not rewritten):
        # committed-minority assignment goes through simulation.py::swap_committed's
        # injected-rng path; this module-level-random.sample path is dead upstream code.
        raise NotImplementedError(
            "minority_size is unused in this codebase; committed-minority assignment "
            "goes through convention_topology.simulation.swap_committed instead"
        )
    network = {
        node_id + 1: _empty_player()
        for node_id in range(n + minority_size)
    }

    if network_type == "complete":
        for node_id in network:
            network[node_id]["neighbours"] = [
                other for other in network if other != node_id
            ]

    elif network_type == "random_regular":
        rng = random.Random(graph_seed)
        graph = nx.random_regular_graph(d=degree, n=len(network), seed=rng)
        for node_id in network:
            network[node_id]["neighbours"] = sorted(
                neighbour + 1 for neighbour in graph.neighbors(node_id - 1)
            )

    elif network_type == "lattice":
        for node_id in network:
            network[node_id]["neighbours"] = lattice_neighbours(node_id, n)

    else:
        raise ValueError(f"Unsupported network_type: {network_type}")

    if minority_size > 0:
        committed_ids = random.sample(list(network.keys()), k=minority_size)
        for node_id in committed_ids:
            network[node_id]["committed_tag"] = True

    return network
