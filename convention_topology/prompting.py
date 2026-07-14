"""Prompt construction, ported from Ashery et al. `prompting.py`.

Deviation from upstream (documented, WORKING.md §2): Ashery's raw completion
prompt embeds Llama-3 header tokens (`<|begin_of_text|>`, `<|eot_id|>`, ...) to
simulate chat turns inside a single string. This port keeps the rule text,
H=5 memory windowing, local score computation, history-dict formatting, and
the `{'value': ...; 'reason': ...}` response format verbatim, but splits the
content into a system message and a user message for an OpenAI-compatible
chat API — the provider applies its own chat template instead.
"""

from __future__ import annotations

from typing import Mapping, Sequence

PROMPT_TEMPLATE_VERSION = "v1-ashery-chat-split"


def get_rules(rewards: Sequence[int], options: Sequence[str]) -> str:
    """Verbatim Ashery rule text (payoffs, 100-round framing), header tokens stripped."""
    incorrect, correct = rewards
    return (
        "\n  Context: Player 1 is playing a multi-round partnership game with Player 2 for 100 rounds.\n"
        f"  At each round, Player 1 and Player 2 simultaneously pick an action from the following values: {options}.\n"
        "  The payoff that both players get is determined by the following rule:\n"
        f"  1. If Players play the SAME action as each other, they will both be REWARDED with payoff +{correct} points.\n"
        f"  2. If Players play DIFFERENT actions to each other, they will both be PUNISHED with payoff {incorrect} points.\n"
        "  The objective of each Player is to maximize their own accumulated point tally, conditional on the behavior of the other player.\n"
        "  "
    )


_ANSWER_INSTRUCTION = (
    " Answer saying which value Player 1 should pick. Please think step by step before "
    "making a decision. Remember, examining history explicitly is important. Write your "
    "answer using the following format: {'value': <VALUE_OF_PLAYER_1>; 'reason': <YOUR_REASON>}."
)
_ANSWER_PROMPT = "Answer saying which action Player 1 should play."


def build_messages(
    player: Mapping[str, Sequence],
    memory_size: int,
    rewards: Sequence[int],
    options: Sequence[str],
) -> tuple[str, str]:
    """Port of Ashery `get_prompt`, split into (system, user) chat messages.

    Keeps H=5 windowing, local score tracking, history-dict lines, and the
    off-by-design round numbering (`idx+2`, matching upstream) verbatim.
    """
    rules = get_rules(rewards, options)
    length = len(player["my_history"])

    if length == 0:
        new_query = f"It is now round 1. The current score of Player 1 is 0.{_ANSWER_INSTRUCTION} {_ANSWER_PROMPT}"
        return rules, new_query

    current_score = 0
    histories: list[dict[str, object]] = []
    if length < memory_size:
        indices = list(range(length))
    else:
        indices = list(range(length))[-memory_size:]

    idx = 0
    for idx, r in enumerate(indices):
        my_answer = player["my_history"][r]
        partner_answer = player["partner_history"][r]
        outcome = player["outcome"][r]
        current_score += outcome
        histories.append(
            {"round": idx + 1, "Player 1": my_answer, "Player 2": partner_answer, "payoff": outcome}
        )

    history_intro = "This is the history of choices in past rounds:"
    history_lines = "\n ".join(f"{hist}" for hist in histories)
    new_query = (
        f"It is now round {idx + 2}. The current score of Player 1 is {current_score}."
        f"{_ANSWER_INSTRUCTION} {_ANSWER_PROMPT}"
    )
    user = "\n ".join([history_intro, history_lines, new_query])
    return rules, user
