#!/usr/bin/env python3
"""CLI: main-study batch runner -- eligible-count targeting per cell (§5, M01 locks).

Thin dispatch (§0 principle 6): argument parsing + one call into
`convention_topology.orchestration.run_main_study`. Per (topology x cm_k)
cell, keeps launching seeds until the eligible (gate-passed) count reaches
the target or the attempted cap (default 3x target) is hit -- guards
runaway censoring cells. Same resume/`--retry-failed` semantics as
`run_pilot.py`; targeting counts **eligible** runs, not attempted.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from convention_topology.config import load_config, resolve_model
from convention_topology.orchestration import TOPOLOGIES, cell_targets, run_main_study


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Main-study batch: eligible-count targeting per (topology, k) cell.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--topology", choices=TOPOLOGIES, default=None, help="Restrict to one topology.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    model_spec = resolve_model(config, args.model)

    if args.dry_run:
        targets = cell_targets(config)
        if args.topology:
            targets = [row for row in targets if row["topology"] == args.topology]
        for row in targets:
            print(
                f"topology={row['topology']} k={row['cm_k']} "
                f"eligible_target=[{row['eligible_target_min']}-{row['eligible_target_max']}] "
                f"attempted_cap={row['attempted_cap']}"
            )
        print(f"total_cells={len(targets)}")
        return 0

    results = run_main_study(
        config,
        model_spec,
        data_dir=Path(config.paths.data),
        logs_dir=Path(config.paths.logs),
        mock_policy=args.mock_policy,
        retry_failed=args.retry_failed,
        topology_filter=args.topology,
    )
    for result in results:
        print(
            f"topology={result['topology']} k={result['cm_k']} "
            f"eligible={result['eligible']}/{result['target']} attempted={result['attempted']}/{result['attempted_cap']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
