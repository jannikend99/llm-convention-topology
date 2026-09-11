"""Campaign-fixed undirected graphs. Topology id is mixing."""

from __future__ import annotations

import hashlib
import random
from typing import Any

import networkx as nx

from convention_topology.config import TOPOLOGIES


def _empty_player() -> dict[str, Any]:
    return {
        "my_history": [],
        "partner_history": [],
        "interactions": [],
        "score": 0,
        "score_history": [],
        "outcome": [],
        "committed_tag": False,
        "neighbours": [],
    }


def lattice_neighbours(node_id: int, n: int) -> list[int]:
    index = node_id - 1
    neighbours: set[int] = set()
    for offset in (1, 2):
        neighbours.add((index - offset) % n + 1)
        neighbours.add((index + offset) % n + 1)
    return sorted(neighbours)


def adjacency_pairs(network: dict[int, dict[str, Any]]) -> list[tuple[int, int]]:
    edge_pairs: list[tuple[int, int]] = []
    for node_id, player in sorted(network.items()):
        for neighbour in sorted(player["neighbours"]):
            if node_id < neighbour:
                edge_pairs.append((node_id, neighbour))
    return edge_pairs


def adjacency_hash(network: dict[int, dict[str, Any]]) -> str:
    digest = hashlib.sha256(repr(adjacency_pairs(network)).encode("utf-8")).hexdigest()
    return digest[:16]


def graph_stats(network: dict[int, dict[str, Any]]) -> dict[str, float | int | bool]:
    n = len(network)
    edges = adjacency_pairs(network)
    edge_count = len(edges)
    mean_degree = (2 * edge_count / n) if n else 0.0
    nx_graph = nx.Graph()
    nx_graph.add_nodes_from(network)
    nx_graph.add_edges_from(edges)
    return {
        "edge_count": edge_count,
        "realized_mean_degree": mean_degree,
        "graph_connected": bool(n == 0 or nx.is_connected(nx_graph)),
    }


def _from_nx(graph: nx.Graph, n: int) -> dict[int, dict[str, Any]]:
    network = {node_id + 1: _empty_player() for node_id in range(n)}
    for node_id in network:
        network[node_id]["neighbours"] = sorted(
            neighbour + 1 for neighbour in graph.neighbors(node_id - 1)
        )
    return network


def _connected_draw(builder, rng: random.Random, n: int, max_draws: int = 10_000) -> tuple[dict[int, dict[str, Any]], int]:
    attempts = 0
    while attempts < max_draws:
        attempts += 1
        seed = rng.randrange(0, 2**32)
        graph = builder(seed)
        if nx.is_connected(graph):
            return _from_nx(graph, n), attempts
    raise RuntimeError("failed to draw a connected graph")


def get_interaction_network(
    topology: str,
    *,
    n: int,
    degree: int = 4,
    graph_seed: int | None = None,
    ws_k: int = 4,
    ws_p: float = 0.1,
    ba_m: int = 2,
) -> tuple[dict[int, dict[str, Any]], int]:
    if topology not in TOPOLOGIES:
        raise ValueError(f"Unsupported topology {topology!r}")
    rng = random.Random(graph_seed)
    if topology == "mixing":
        graph = nx.complete_graph(n)
        return _from_nx(graph, n), 1
    if topology == "lattice":
        network = {node_id + 1: _empty_player() for node_id in range(n)}
        for node_id in network:
            network[node_id]["neighbours"] = lattice_neighbours(node_id, n)
        return network, 1
    if topology == "random_regular":
        return _connected_draw(
            lambda seed: nx.random_regular_graph(d=degree, n=n, seed=seed),
            rng,
            n,
        )
    if topology == "watts_strogatz":
        return _connected_draw(
            lambda seed: nx.watts_strogatz_graph(n=n, k=ws_k, p=ws_p, seed=seed),
            rng,
            n,
        )
    return _from_nx(nx.barabasi_albert_graph(n=n, m=ba_m, seed=rng.randrange(0, 2**32)), n), 1
