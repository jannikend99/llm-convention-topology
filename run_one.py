#!/usr/bin/env python3
"""CLI: run a single (topology, k, seed) Phase 1(->2) run for one model.

Thin dispatch only (§0 principle 6): argument parsing + one call into
`convention_topology.run.execute_run`, or a lightweight `--smoke` loop that
skips persistence and Phase 2 entirely (offline CLI check, C-04/C-05).
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from dotenv import load_dotenv

from convention_topology.config import load_config, resolve_model
from convention_topology.networks import get_interaction_network
from convention_topology.orchestration import (
    build_client,
    build_run_config,
    options as _options,
    retry_policy_for as _retry_policy_for,
    rewards as _rewards,
)
from convention_topology.run import execute_run
from convention_topology.simulation import make_interaction_step


def run_smoke(config, model_spec, client, *, topology, cm_k, graph_seed, run_seed, max_interactions) -> None:
    n = config.params.N
    memory_size = config.params.memory_size_set[0]
    simulation = get_interaction_network(topology, n=n, degree=config.network.degree, graph_seed=graph_seed)
    committed_to = None
    if cm_k:
        from convention_topology.simulation import swap_committed

        swap_committed(simulation, cm_k, random.Random(run_seed))
        # Smoke mode never runs Phase 1's gate, so there is no incumbent to
        # derive a committed label from (unlike `execute_run`) -- fix an
        # arbitrary option so committed agents still emit a valid label.
        committed_to = _options(config)[0]
    rng = random.Random(run_seed)
    step = make_interaction_step(
        simulation,
        client,
        memory_size,
        _rewards(config),
        _options(config),
        rng,
        committed_to=committed_to,
        retry_policy=_retry_policy_for(model_spec),
    )
    tracker: dict[str, list] = {"players": [], "answers": [], "outcome": []}
    print(f"model_id={model_spec.model_id} endpoint={model_spec.base_url or '(mock, no endpoint)'}")
    for _ in range(max_interactions):
        step(tracker)
        p1_answer, p2_answer = tracker["answers"][-1]
        print(f"t={len(tracker['outcome'])} labels=({p1_answer}, {p2_answer})")


def run_full(config, model_spec, client, *, topology, cm_k, graph_seed, run_seed):
    run_config = build_run_config(
        config, model_spec, topology=topology, cm_k=cm_k, graph_seed=graph_seed, run_seed=run_seed,
    )
    paths = execute_run(
        run_config,
        client,
        data_dir=Path(config.paths.data),
        logs_dir=Path(config.paths.logs),
        retry_policy=_retry_policy_for(model_spec),
    )
    print(f"run_id={paths.pickle_path.stem} meta={paths.meta_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one Phase 1(->2) convention-topology run.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--topology", required=True, choices=["complete", "random_regular", "lattice"])
    parser.add_argument("--k", type=int, required=True, dest="cm_k")
    parser.add_argument("--seed", type=int, required=True, dest="run_seed")
    parser.add_argument("--graph-seed", type=int, default=None)
    parser.add_argument("--max-interactions", type=int, default=20)
    parser.add_argument("--smoke", action="store_true", help="Cap interactions, skip Phase 2 and persistence.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)
    client = build_client(model_spec, args.mock_policy, args.run_seed, _options(config))
    graph_seed = args.graph_seed if args.graph_seed is not None else args.run_seed

    if args.smoke:
        run_smoke(
            config,
            model_spec,
            client,
            topology=args.topology,
            cm_k=args.cm_k,
            graph_seed=graph_seed,
            run_seed=args.run_seed,
            max_interactions=args.max_interactions,
        )
        return 0

    run_full(config, model_spec, client, topology=args.topology, cm_k=args.cm_k, graph_seed=graph_seed, run_seed=args.run_seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
