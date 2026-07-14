#!/usr/bin/env python3
"""CLI: pilot batch runner -- 12 attempted Phase 1 runs/topology per model (§5).

Thin dispatch (§0 principle 6): argument parsing + one call into
`convention_topology.orchestration.run_pilot`. All grid construction,
resume/retry filtering, and dispatch logic lives in `orchestration.py`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from convention_topology.config import load_config, resolve_model
from convention_topology.orchestration import pilot_grid, run_pilot as _run_pilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot batch: 12 attempted Phase 1 runs/topology (36/model).")
    parser.add_argument("--model", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Across-run parallelism; each worker owns its run_id files. Recommended <=4 per provider.",
    )
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)

    if args.dry_run:
        cells = pilot_grid(config.run.base_seed)
        for cell in cells:
            print(
                f"topology={cell.topology} seed_index={cell.seed_index:2d} k={cell.cm_k} "
                f"graph_seed={cell.graph_seed} run_seed={cell.run_seed}"
            )
        print(f"total_rows={len(cells)}")
        return 0

    results = _run_pilot(
        config,
        model_spec,
        data_dir=Path(config.paths.data),
        logs_dir=Path(config.paths.logs),
        mock_policy=args.mock_policy,
        workers=args.workers,
        retry_failed=args.retry_failed,
    )
    for run_id, status in sorted(results.items()):
        print(f"{run_id}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
