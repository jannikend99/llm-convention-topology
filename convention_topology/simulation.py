from __future__ import annotations

import random
from typing import Callable, Mapping, Sequence

from convention_topology.gate import GateResult, evaluate_phase1_gate, has_tracker_converged
from convention_topology.llm import LLMClient, RetryPolicy, parse_label
from convention_topology.prompting import build_messages
from convention_topology.tracker import empty_tracker, get_outcome, update_dict, update_tracker


InteractionStep = Callable[[dict[str, list]], None]


def run_phase1(
    interaction_step: InteractionStep,
    *,
    convergence_time: int,
    convergence_threshold: float,
    max_phase1_interactions: int,
    tracker: dict[str, list] | None = None,
) -> tuple[dict[str, list], GateResult]:
    """
    Execute Phase 1 until the stability gate passes or the hard cap is reached.

    Thesis locks:
    - convergence_threshold = 0.95 (not Ashery repo default 1.0)
    - max_phase1_interactions = 5000
    """
    tracker = empty_tracker() if tracker is None else tracker

    while not has_tracker_converged(
        tracker,
        convergence_time=convergence_time,
        threshold=convergence_threshold,
    ):
        if len(tracker["outcome"]) >= max_phase1_interactions:
            break
        interaction_step(tracker)

    gate = evaluate_phase1_gate(
        tracker,
        convergence_time=convergence_time,
        threshold=convergence_threshold,
        max_phase1_interactions=max_phase1_interactions,
    )
    return tracker, gate


def run_phase2(
    dataframe: Mapping[str, object],
    interaction_step: InteractionStep,
    *,
    phase2_horizon: int,
) -> dict[str, list]:
    """Run the fixed post-gate interaction horizon on an eligible population."""
    tracker = dataframe["tracker"]
    init_len = len(tracker["outcome"])

    while len(tracker["outcome"]) - init_len < phase2_horizon:
        interaction_step(tracker)

    return tracker


def swap_committed(simulation: dict[int, dict], minority_size: int, rng: random.Random) -> list[int]:
    """Tag k randomly selected agents as committed minorities (Ashery swap mode).

    `rng` is injected (§0 architecture principle 2) — no module-level `random.*`.
    """
    if minority_size <= 0:
        return []
    committed_ids = rng.sample(list(simulation.keys()), k=minority_size)
    for node_id in committed_ids:
        simulation[node_id]["committed_tag"] = True
    return committed_ids


def make_interaction_step(
    simulation: dict[int, dict],
    client: LLMClient,
    memory_size: int,
    rewards: Sequence[int],
    options: Sequence[str],
    rng: random.Random,
    committed_to: str | None = None,
    retry_policy: RetryPolicy | None = None,
    on_attempt: Callable[[int, Exception | None], None] | None = None,
    shared_shuffle: bool = False,
) -> InteractionStep:
    """Build one Phase 1/2 interaction step (Ashery `population`/`committed` port).

    Random agent -> random neighbour, prompt -> client -> `parse_label` ->
    payoff -> `update_dict` x2 + `update_tracker`. Committed agents
    (`committed_tag`) short-circuit straight to `committed_to` -- no client
    call, no retries (§0 CM zero-API lock).

    `shared_shuffle` controls the option-shuffle granularity (M1, WORKING §2):
    - `False` (default, Phase 1): each agent independently shuffles its own
      option order -- matches Ashery `population()`.
    - `True` (Phase 2): options are shuffled **once per interaction**,
      shared by both players, before either builds their prompt -- matches
      Ashery `committed()`, which shuffles before `p1`/`p2` are even chosen.
    """
    policy = retry_policy if retry_policy is not None else RetryPolicy()

    def step(tracker: dict[str, list]) -> None:
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

        answers: list[str] = []
        for player in (p1_dict, p2_dict):
            if player.get("committed_tag"):
                answers.append(committed_to)
                continue

            if shared_options is not None:
                shuffled_options = shared_options
            else:
                shuffled_options = list(options)
                rng.shuffle(shuffled_options)
            system, user = build_messages(player, memory_size, rewards, shuffled_options)

            def call_and_parse(system=system, user=user) -> str:
                response = client.complete(system, user)
                return parse_label(response.text, options)

            answers.append(policy.run(call_and_parse, on_attempt=on_attempt))

        my_answer, partner_answer = answers
        outcome = get_outcome(my_answer, partner_answer, rewards)
        update_dict(p1_dict, my_answer, partner_answer, outcome)
        update_dict(p2_dict, partner_answer, my_answer, outcome)
        update_tracker(tracker, p1, p2, my_answer, partner_answer, outcome)

    return step
