"""Ashery prepared-population init for CM runs (`utils.get_prepared_population`).

CM experiments start from a synthetic consensus: every agent's memory is
filled with the incumbent label for `memory_size` steps, then a committed
minority is swapped in. Tracker starts empty; `converged_index = 0`.
"""

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
    """Fill each non-committed agent's history with `H` incumbent matches."""
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
) -> None:
    """Every agent must have exactly `H` own-answers equal to the incumbent."""
    incumbent = options[incumbent_index]
    for node_id, player in simulation.items():
        history = player["my_history"][:memory_size]
        if len(history) < memory_size or history.count(incumbent) != memory_size:
            raise PreparedInitError(
                f"player {node_id} prepared init failed: "
                f"expected {memory_size}×{incumbent!r}, got {history!r}"
            )


def committed_label(options: Sequence[str], incumbent_index: int) -> str:
    """CM advocates the non-incumbent label (W=2 lock)."""
    if len(options) != 2:
        raise PreparedInitError(
            f"prepared CM requires exactly 2 options; got {list(options)!r}"
        )
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
    incumbent_index: int,
    degree: int = 4,
) -> tuple[dict[int, dict], dict[str, list], dict]:
    """Build graph + prepared histories + convergence block for a CM run."""
    simulation = get_interaction_network(topology, n=n, degree=degree, graph_seed=graph_seed)
    set_initial_state(simulation, rewards, options, memory_size, incumbent_index)
    assert_prepared(simulation, options, memory_size, incumbent_index)

    incumbent = options[incumbent_index]
    committed_to = committed_label(options, incumbent_index)
    tracker = empty_tracker()
    convergence = {
        "converged_index": 0,
        "incumbent_label": incumbent,
        "committed_to": committed_to,
    }
    return simulation, tracker, convergence
