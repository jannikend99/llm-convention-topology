"""Campaign-root pool, graphs, and immutable config snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from convention_topology.config import TOPOLOGIES, config_hash
from convention_topology.networks import adjacency_hash, adjacency_pairs, get_interaction_network, graph_stats
from convention_topology.pool import draw_pool, pool_sha256
from convention_topology.seeds import graph_seed as derive_graph_seed


class CampaignError(Exception):
    """Campaign identity mismatch or create failure."""


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.flush()
    tmp.replace(path)


def _atomic_write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(payload), handle, sort_keys=True)
        handle.flush()
    tmp.replace(path)


def build_graphs_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    n = int(config["protocol"]["N"])
    network = config["network"]
    base_seed = int(config["run"]["base_seed"])
    graphs: dict[str, Any] = {}
    for topology in TOPOLOGIES:
        seed = derive_graph_seed(base_seed, topology)
        sim, attempts = get_interaction_network(
            topology,
            n=n,
            degree=int(network["degree"]),
            graph_seed=seed,
            ws_k=int(network["ws_k"]),
            ws_p=float(network["ws_p"]),
            ba_m=int(network["ba_m"]),
        )
        stats = graph_stats(sim)
        graphs[topology] = {
            "topology": topology,
            "graph_seed": seed,
            "adjacency": adjacency_pairs(sim),
            "adjacency_hash": adjacency_hash(sim),
            "graph_draw_attempts": attempts,
            **stats,
            "ws_k": network["ws_k"] if topology == "watts_strogatz" else None,
            "ws_p": network["ws_p"] if topology == "watts_strogatz" else None,
            "ba_m": network["ba_m"] if topology == "barabasi_albert" else None,
            "lattice_kind": "ring_degree4" if topology == "lattice" else None,
        }
    return {"N": n, "graphs": graphs}


def ensure_campaign_files(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    protocol = config["protocol"]
    pool_labels = draw_pool(seed=int(config["pool"]["seed"]), string_length=int(protocol["string_length"]))
    pool_payload = {
        "seed": int(config["pool"]["seed"]),
        "string_length": int(protocol["string_length"]),
        "labels": pool_labels,
        "sha256": pool_sha256(pool_labels),
    }
    graphs_payload = build_graphs_payload(config)
    snapshot = dict(config)
    snapshot_hash = config_hash(config)

    pool_path = root / "label_pool.json"
    graphs_path = root / "graphs.json"
    snapshot_path = root / "config.snapshot.yaml"

    if pool_path.exists():
        existing = json.loads(pool_path.read_text(encoding="utf-8"))
        if existing.get("sha256") != pool_payload["sha256"]:
            raise CampaignError("label_pool.json hash mismatch")
    else:
        _atomic_write_json(pool_path, pool_payload)

    if graphs_path.exists():
        existing = json.loads(graphs_path.read_text(encoding="utf-8"))
        for topology, graph in graphs_payload["graphs"].items():
            if existing["graphs"][topology]["adjacency_hash"] != graph["adjacency_hash"]:
                raise CampaignError(f"graphs.json hash mismatch for {topology}")
    else:
        _atomic_write_json(graphs_path, graphs_payload)

    if snapshot_path.exists():
        existing = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
        if config_hash(existing) != snapshot_hash:
            raise CampaignError("config.snapshot.yaml hash mismatch")
    else:
        _atomic_write_yaml(snapshot_path, snapshot)

    return {"pool": pool_payload, "graphs": graphs_payload, "config_hash": snapshot_hash}
