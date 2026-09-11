"""Thesis LLM Naming Game — locked protocol, mock-green counted path."""

from convention_topology.config import load_config
from convention_topology.gate import GateResult, evaluate_phase1_gate, has_tracker_converged
from convention_topology.networks import adjacency_hash, get_interaction_network

__all__ = [
    "load_config",
    "GateResult",
    "has_tracker_converged",
    "evaluate_phase1_gate",
    "get_interaction_network",
    "adjacency_hash",
]
