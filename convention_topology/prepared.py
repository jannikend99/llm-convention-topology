"""Prepared Study 2 init: H incumbent matches, then swap k, t_cm_start=0."""

from __future__ import annotations

from typing import Sequence

from convention_topology.networks import get_interaction_network
from convention_topology.tracker import empty_tracker, update_dict


class PreparedInitError(Exception):
    """Raised when prepared-population invariants fail."""


def set_initial_state(
    simulation: dict[int, dict],
    rewards: Sequence[int],
    options: Sequence[str],
    memory_size: int,
    incumbent_index: int,
) -> None:
    if not 0 <= incumbent_index < len(options):
        raise PreparedInitError(
            f"incumbent_index={incumbent_index} out of range for options={list(options)!r}"
        )
    incumbent = options[incumbent_index]
    match_payoff = rewards[1]
    for _ in range(memory_size):
        for player in simulation.values():
            if player.get("committed_tag"):
                continue
            update_dict(player, incumbent, incumbent, match_payoff)


def assert_prepared(
    simulation: dict[int, dict],
    options: Sequence[str],
    memory_size: int,
    incumbent_index: int,
    *,
    cm_k: int,
    committed_ids: Sequence[int],
    rewards_match: int,
) -> None:
    incumbent = options[incumbent_index]
    if len(committed_ids) != cm_k:
        raise PreparedInitError("committed_ids length must equal cm_k")
    for node_id, player in simulation.items():
        if player.get("committed_tag"):
            continue
        history = player["my_history"][:memory_size]
        if len(history) < memory_size or history.count(incumbent) != memory_size:
            raise PreparedInitError(
                f"player {node_id} prepared init failed: expected {memory_size} x incumbent"
            )
        if player["score"] != memory_size * rewards_match:
            raise PreparedInitError(f"player {node_id} prepared score is not H * match")
    tagged = [nid for nid, player in simulation.items() if player.get("committed_tag")]
    if sorted(tagged) != sorted(committed_ids):
        raise PreparedInitError("committed tags do not match committed_ids")


def committed_label(options: Sequence[str], incumbent_index: int) -> str:
    if len(options) != 2:
        raise PreparedInitError(f"prepared CM requires exactly 2 options; got {list(options)!r}")
    incumbent = options[incumbent_index]
    alternatives = [option for option in options if option != incumbent]
    return alternatives[0]


def make_prepared_population(
    topology: str,
    *,
    n: int,
    graph_seed: int | None,
    rewards: Sequence[int],
    options: Sequence[str],
    memory_size: int,
    incumbent_index: int = 0,
    degree: int = 4,
    ws_k: int = 4,
    ws_p: float = 0.1,
    ba_m: int = 2,
) -> tuple[dict[int, dict], dict[str, list], dict, int]:
    simulation, draw_attempts = get_interaction_network(
        topology,
        n=n,
        degree=degree,
        graph_seed=graph_seed,
        ws_k=ws_k,
        ws_p=ws_p,
        ba_m=ba_m,
    )
    set_initial_state(simulation, rewards, options, memory_size, incumbent_index)
    incumbent = options[incumbent_index]
    committed_to = committed_label(options, incumbent_index)
    tracker = empty_tracker()
    convergence = {
        "converged_index": 0,
        "incumbent_label": incumbent,
        "committed_to": committed_to,
    }
    return simulation, tracker, convergence, draw_attempts
