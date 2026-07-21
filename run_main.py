#!/usr/bin/env python3
"""CLI: main-study batch runner — target counts per program cell.

`--program emergence`: gate-eligible targets per topology.
`--program cm`: completed-run targets per (topology × k).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from convention_topology.config import load_config, resolve_model
from convention_topology.orchestration import TOPOLOGIES, cell_targets, run_main_study
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Main-study batch: target-count targeting per program cell.")
    parser.add_argument("--program", required=True, choices=[PROGRAM_EMERGENCE, PROGRAM_CM])
    parser.add_argument("--model", required=True)
    parser.add_argument("--topology", choices=TOPOLOGIES, default=None, help="Restrict to one topology.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Across-cell parallelism (topology×k cells). Default 1; 2–4 ok for OpenRouter.",
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Disable live [start]/[done]/[alive] progress.")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)

    if args.dry_run:
        targets = cell_targets(config, args.program)
        if args.topology:
            targets = [row for row in targets if row["topology"] == args.topology]
        for row in targets:
            print(
                f"program={row['program']} topology={row['topology']} k={row['cm_k']} "
                f"target=[{row['target_min']}-{row['target_max']}] "
                f"attempted_cap={row['attempted_cap']}"
            )
        print(f"total_cells={len(targets)}")
        return 0

    results = run_main_study(
        config,
        model_spec,
        program=args.program,
        data_dir=Path(config.paths.data),
        logs_dir=Path(config.paths.logs),
        mock_policy=args.mock_policy,
        retry_failed=args.retry_failed,
        topology_filter=args.topology,
        workers=args.workers,
        progress=not args.quiet,
    )
    for result in results:
        print(
            f"program={result['program']} topology={result['topology']} k={result['cm_k']} "
            f"eligible={result['eligible']}/{result['target']} "
            f"attempted={result['attempted']}/{result['attempted_cap']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
