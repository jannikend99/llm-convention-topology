"""Committed-minority swap. Pairing lives in the counted run engine."""

from __future__ import annotations

import random


def swap_committed(simulation: dict[int, dict], minority_size: int, rng: random.Random) -> list[int]:
    if minority_size <= 0:
        return []
    committed_ids = rng.sample(list(simulation.keys()), k=minority_size)
    for node_id in committed_ids:
        simulation[node_id]["committed_tag"] = True
    return committed_ids
