#!/usr/bin/env python3
"""CLI: run one emergence or CM experiment run.

Thin dispatch (§0 principle 6): argument parsing + one call into
`convention_topology.run.execute_run`, or a lightweight `--smoke` loop.
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
    options_for_program,
    retry_policy_for,
    rewards as _rewards,
)
from convention_topology.prepared import make_prepared_population
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE, execute_run
from convention_topology.simulation import make_interaction_step, swap_committed


def run_smoke(config, model_spec, client, *, program, topology, cm_k, graph_seed, run_seed, max_interactions) -> None:
    n = config.params.N
    memory_size = config.params.memory_size_set[0]
    opts = options_for_program(config, program)
    rng = random.Random(run_seed)
    rewards = _rewards(config)

    if program == PROGRAM_CM:
        simulation, tracker, convergence = make_prepared_population(
            topology,
            n=n,
            graph_seed=graph_seed,
            rewards=rewards,
            options=opts,
            memory_size=memory_size,
            incumbent_index=int(config.params.incumbent_index),
            degree=config.network.degree,
        )
        swap_committed(simulation, cm_k, rng)
        committed_to = convergence["committed_to"]
        shared_shuffle = True
    else:
        simulation = get_interaction_network(
            topology, n=n, degree=config.network.degree, graph_seed=graph_seed
        )
        tracker = {"players": [], "answers": [], "outcome": []}
        committed_to = None
        shared_shuffle = False

    step = make_interaction_step(
        simulation,
        client,
        memory_size,
        rewards,
        opts,
        rng,
        committed_to=committed_to,
        retry_policy=retry_policy_for(model_spec),
        shared_shuffle=shared_shuffle,
    )
    print(f"program={program} model_id={model_spec.model_id} endpoint={model_spec.base_url or '(mock, no endpoint)'}")
    for _ in range(max_interactions):
        step(tracker)
        p1_answer, p2_answer = tracker["answers"][-1]
        print(f"t={len(tracker['outcome'])} labels=({p1_answer}, {p2_answer})")


def run_full(config, model_spec, client, *, program, topology, cm_k, graph_seed, run_seed):
    run_config = build_run_config(
        config,
        model_spec,
        program=program,
        topology=topology,
        cm_k=cm_k,
        graph_seed=graph_seed,
        run_seed=run_seed,
    )
    paths = execute_run(
        run_config,
        client,
        data_dir=Path(config.paths.data),
        logs_dir=Path(config.paths.logs),
        retry_policy=retry_policy_for(model_spec),
    )
    print(f"run_id={paths.pickle_path.stem} meta={paths.meta_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one emergence or CM convention-topology run.")
    parser.add_argument("--program", required=True, choices=[PROGRAM_EMERGENCE, PROGRAM_CM])
    parser.add_argument("--model", required=True)
    parser.add_argument("--topology", required=True, choices=["complete", "random_regular", "lattice"])
    parser.add_argument("--k", type=int, default=0, dest="cm_k", help="CM size (required for --program cm).")
    parser.add_argument("--seed", type=int, required=True, dest="run_seed")
    parser.add_argument("--graph-seed", type=int, default=None)
    parser.add_argument("--max-interactions", type=int, default=20)
    parser.add_argument("--smoke", action="store_true", help="Cap interactions; skip persistence.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    if args.program == PROGRAM_CM and args.cm_k < 1:
        parser.error("--k >= 1 is required for --program cm")
    if args.program == PROGRAM_EMERGENCE:
        args.cm_k = 0

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)
    opts = options_for_program(config, args.program)
    client = build_client(model_spec, args.mock_policy, args.run_seed, opts)
    graph_seed = args.graph_seed if args.graph_seed is not None else args.run_seed

    if args.smoke:
        run_smoke(
            config,
            model_spec,
            client,
            program=args.program,
            topology=args.topology,
            cm_k=args.cm_k,
            graph_seed=graph_seed,
            run_seed=args.run_seed,
            max_interactions=args.max_interactions,
        )
        return 0

    run_full(
        config,
        model_spec,
        client,
        program=args.program,
        topology=args.topology,
        cm_k=args.cm_k,
        graph_seed=graph_seed,
        run_seed=args.run_seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
