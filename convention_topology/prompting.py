"""Canonical Ashery observer prompt with JSON enum instruction."""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

PROMPT_TEMPLATE_VERSION = "v2-ashery-json-enum"

CANONICAL_TEMPLATE = """Context: Player 1 is playing a multi-round partnership game with Player 2.
At each round, Player 1 and Player 2 simultaneously pick an action from these values: {options}.
If both players pick the SAME action, both receive +{match_reward} points.
If they pick DIFFERENT actions, both receive {mismatch_reward} points.
Player 1 should maximize their accumulated point tally conditional on Player 2's behavior.

{history_or_empty}
It is now round {player_round}. The current score of Player 1 over the displayed history is {displayed_score}.
Please think step by step before making a decision. Examining the history explicitly is important.
Return exactly one JSON object: {{"value":"<one offered value>","reason":"<brief reason>"}}.
Do not write text outside the JSON object.
"""


def prompt_template_hash(template: str = CANONICAL_TEMPLATE) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def format_history(player: Mapping[str, Sequence], memory_size: int) -> tuple[str, int, int]:
    length = len(player["my_history"])
    if length == 0:
        return "", 1, 0
    indices = list(range(length))[-memory_size:]
    lines = ["This is the history of choices in past rounds:"]
    displayed_score = 0
    for idx in indices:
        my_answer = player["my_history"][idx]
        partner_answer = player["partner_history"][idx]
        payoff = player["outcome"][idx]
        displayed_score += int(payoff)
        player_round_at_row = idx + 1
        lines.append(
            f"Round {player_round_at_row}: Player 1={my_answer}, Player 2={partner_answer}, payoff={payoff}."
        )
    player_round = length + 1
    return "\n".join(lines) + "\n", player_round, displayed_score


def build_user_prompt(
    player: Mapping[str, Sequence],
    memory_size: int,
    rewards: Sequence[int],
    options: Sequence[str],
) -> str:
    history_or_empty, player_round, displayed_score = format_history(player, memory_size)
    mismatch_reward, match_reward = rewards
    return CANONICAL_TEMPLATE.format(
        options=list(options),
        match_reward=match_reward,
        mismatch_reward=mismatch_reward,
        history_or_empty=history_or_empty,
        player_round=player_round,
        displayed_score=displayed_score,
    )


def rendered_prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
