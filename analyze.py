#!/usr/bin/env python3
"""CLI: analysis dispatch for H1-H4 on the locked cell identity."""

from __future__ import annotations

import argparse
from pathlib import Path

from convention_topology.analysis.dispatch import STUBBED_MEMORY, run_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-model H1-H4 + cross-model analysis dispatch.")
    parser.add_argument("--model", default=None, help="Required unless --cross-model.")
    parser.add_argument("--data", default="data/runs/slate-a")
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--h1", action="store_true")
    parser.add_argument("--h2", action="store_true")
    parser.add_argument("--h3a", action="store_true")
    parser.add_argument("--h3b", action="store_true")
    parser.add_argument("--h4", action="store_true")
    parser.add_argument("--gate-summary", action="store_true", dest="gate_summary")
    parser.add_argument("--cross-model", action="store_true", dest="cross_model")
    parser.add_argument("--memory-decision", action="store_true", dest="memory_decision")
    parser.add_argument(
        "--memory-decision-compare",
        action="store_true",
        dest="memory_decision_compare",
    )
    parser.add_argument("--sensitivity-50", action="store_true", dest="sensitivity_50")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    if args.memory_decision or args.memory_decision_compare:
        parser.error(STUBBED_MEMORY)

    if not args.model and not args.cross_model:
        parser.error("--model is required unless --cross-model")

    run_all(
        Path(args.data),
        Path(args.outputs),
        model=args.model,
        h1=args.h1,
        h2=args.h2,
        h3a=args.h3a,
        h3b=args.h3b,
        h4=args.h4,
        gate_summary=args.gate_summary,
        cross_model=args.cross_model,
        memory_decision=False,
        memory_decision_compare=False,
        sensitivity_50=args.sensitivity_50,
        all_=args.all,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
