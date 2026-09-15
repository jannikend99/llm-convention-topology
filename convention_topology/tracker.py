from __future__ import annotations

from collections import Counter
from typing import Any, Sequence


def get_outcome(my_answer: str, partner_answer: str, rewards: Sequence[int]) -> int:
    if my_answer == partner_answer:
        return rewards[1]
    return rewards[0]


def coordination_success(outcome: int) -> bool:
    return outcome > 5


def update_dict(
    player: dict[str, Any],
    my_answer: str,
    partner_answer: str,
    outcome: int,
) -> dict[str, Any]:
    player["score"] += outcome
    player["my_history"].append(my_answer)
    player["partner_history"].append(partner_answer)
    player["score_history"].append(player["score"])
    player["outcome"].append(outcome)
    return player


def update_tracker(
    tracker: dict[str, list[Any]],
    p1: int,
    p2: int,
    p1_answer: str,
    p2_answer: str,
    outcome: int,
) -> None:
    tracker["players"].append([p1, p2])
    tracker["answers"].append([p1_answer, p2_answer])
    tracker["outcome"].append(1 if coordination_success(outcome) else 0)


def empty_tracker() -> dict[str, list[Any]]:
    return {"players": [], "answers": [], "outcome": []}


def unique_modal(labels: Sequence[str]) -> str | None:
    if not labels:
        return None
    counts = Counter(labels)
    max_count = max(counts.values())
    winners = [label for label, count in counts.items() if count == max_count]
    if len(winners) != 1:
        return None
    return winners[0]
