"""Async interaction step (④): the two players in one interaction call the LLM
concurrently, everything else matches `simulation.make_interaction_step`.

Determinism lock: all RNG draws (agent/neighbour choice, option shuffles) happen
*synchronously, in the same order as the sync step*, before either LLM call is
awaited. The two calls are independent (each player builds its prompt from its
own memory; neither sees the other's current answer before the shared state
update), so gathering them is statistically neutral — both answers are fixed
before any `update_dict`/`update_tracker`. With the sync mock via
`AsyncClientAdapter`, outcomes are byte-identical to the sync engine.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Sequence

from convention_topology.async_llm import AsyncLLMClient, AsyncRetryPolicy
from convention_topology.prompting import build_messages
from convention_topology.tracker import get_outcome, update_dict, update_tracker


def make_async_interaction_step(
    simulation: dict[int, dict],
    client: AsyncLLMClient,
    memory_size: int,
    rewards: Sequence[int],
    options: Sequence[str],
    rng,
    committed_to: str | None = None,
    retry_policy: AsyncRetryPolicy | None = None,
    on_attempt: Callable[[int, Exception | None], None] | None = None,
    shared_shuffle: bool = False,
):
    """Async twin of `simulation.make_interaction_step`.

    Returns an `async def step(tracker)`. Committed agents short-circuit to
    `committed_to` with no client call (CM zero-API lock). Non-committed player
    prompts are assembled first (draining the RNG in the exact sync order), then
    both completions are awaited via `asyncio.gather`.
    """
    policy = retry_policy if retry_policy is not None else AsyncRetryPolicy()

    async def step(tracker: dict[str, list]) -> None:
        # --- synchronous RNG section: identical draw order to the sync step ---
        shared_options: list[str] | None = None
        if shared_shuffle:
            shared_options = list(options)
            rng.shuffle(shared_options)

        p1 = rng.choice(list(simulation.keys()))
        p2 = rng.choice(simulation[p1]["neighbours"])

        simulation[p1]["interactions"].append(p2)
        simulation[p2]["interactions"].append(p1)
        p1_dict = simulation[p1]
        p2_dict = simulation[p2]

        # Build each non-committed player's prompt now, shuffling in p1→p2 order.
        pending: list[tuple[int, Callable | None, str]] = []  # (slot, awaitable-factory, committed_label)
        call_factories: list[Callable] = []
        for player in (p1_dict, p2_dict):
            if player.get("committed_tag"):
                pending.append(("committed", None, committed_to))
                continue

            if shared_options is not None:
                shuffled_options = shared_options
            else:
                shuffled_options = list(options)
                rng.shuffle(shuffled_options)
            system, user = build_messages(player, memory_size, rewards, shuffled_options)

            async def call_and_parse(system=system, user=user) -> str:
                from convention_topology.llm import parse_label

                response = await client.complete(system, user)
                return parse_label(response.text, options)

            slot_index = len(call_factories)
            call_factories.append(lambda cp=call_and_parse: policy.run(cp, on_attempt=on_attempt))
            pending.append(("call", slot_index, None))

        # --- concurrent section: both live LLM calls overlap here ---
        call_results: list[str] = []
        if call_factories:
            call_results = list(await asyncio.gather(*(factory() for factory in call_factories)))

        answers: list[str] = []
        for kind, ref, committed_label in pending:
            if kind == "committed":
                answers.append(committed_label)
            else:
                answers.append(call_results[ref])

        my_answer, partner_answer = answers
        outcome = get_outcome(my_answer, partner_answer, rewards)
        update_dict(p1_dict, my_answer, partner_answer, outcome)
        update_dict(p2_dict, partner_answer, my_answer, outcome)
        update_tracker(tracker, p1, p2, my_answer, partner_answer, outcome)

    return step
