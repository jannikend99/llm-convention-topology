#!/usr/bin/env python3
"""CLI: pilot batch runner — 12 attempted runs/topology per program.

`--program emergence` → organic Phase 1 (W=10), 36 runs (or 12 with `--topology`).
`--program cm` → prepared CM (W=2), 36 runs with cyclic k (or 12 with `--topology`).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from convention_topology.config import load_config, resolve_model
from convention_topology.orchestration import TOPOLOGIES, pilot_grid, run_pilot as _run_pilot
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot batch: 12 attempted runs/topology for one program.")
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
        help="[sync engine] Across-run thread parallelism; each worker owns its run_id files.",
    )
    parser.add_argument(
        "--engine",
        choices=["async", "sync"],
        default="async",
        help="async (default): asyncio scheduler + provider pool. sync: legacy ThreadPool path.",
    )
    parser.add_argument(
        "--run-concurrency",
        type=int,
        default=12,
        help="[async] Max runs in flight at once.",
    )
    parser.add_argument(
        "--api-concurrency",
        type=int,
        default=8,
        help="[async] Global ceiling on in-flight API calls (set to the measured provider limit, Step ①).",
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="Disable live [start]/[done]/[alive] progress.")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)

    if args.dry_run:
        cells = pilot_grid(config.run.base_seed, args.program)
        if args.topology:
            cells = [cell for cell in cells if cell.topology == args.topology]
        for cell in cells:
            print(
                f"program={cell.program} topology={cell.topology} seed_index={cell.seed_index:2d} "
                f"k={cell.cm_k} graph_seed={cell.graph_seed} run_seed={cell.run_seed}"
            )
        print(f"total_rows={len(cells)}")
        return 0

    if args.engine == "async":
        from convention_topology.async_orchestration import run_pilot_async

        results = run_pilot_async(
            config,
            model_spec,
            program=args.program,
            data_dir=Path(config.paths.data),
            logs_dir=Path(config.paths.logs),
            mock_policy=args.mock_policy,
            run_concurrency=args.run_concurrency,
            api_concurrency=args.api_concurrency,
            retry_failed=args.retry_failed,
            topology_filter=args.topology,
            progress=not args.quiet,
        )
    else:
        results = _run_pilot(
            config,
            model_spec,
            program=args.program,
            data_dir=Path(config.paths.data),
            logs_dir=Path(config.paths.logs),
            mock_policy=args.mock_policy,
            workers=args.workers,
            retry_failed=args.retry_failed,
            topology_filter=args.topology,
            progress=not args.quiet,
        )
    for run_id, status in sorted(results.items()):
        print(f"{run_id}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
