"""Thesis LLM Naming Game — Centola-3 topologies and stability gate."""

from convention_topology.config import load_config
from convention_topology.gate import GateResult, has_tracker_converged, evaluate_phase1_gate
from convention_topology.networks import get_interaction_network, adjacency_hash

__all__ = [
    "load_config",
    "GateResult",
    "has_tracker_converged",
    "evaluate_phase1_gate",
    "get_interaction_network",
    "adjacency_hash",
]
