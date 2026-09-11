#!/usr/bin/env python3
"""Counted campaign CLI: planner and one async slice."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from convention_topology.config import apply_serve_base_url, load_config, resolve_model
from convention_topology.git_guard import DirtyWorktreeError, require_clean_worktree
from convention_topology.orchestration import format_job_line, print_jobs, run_slice_async
from convention_topology.persistence import campaign_root
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Counted naming-game campaign slice or planner.")
    parser.add_argument("--print-jobs", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--program", choices=[PROGRAM_EMERGENCE, PROGRAM_CM], default=None)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument("--seed-from", type=int, default=0)
    parser.add_argument("--seed-to", type=int, default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.print_jobs:
        for job in print_jobs(config, program=args.program):
            print(format_job_line(job))
        return 0

    if not args.model:
        parser.error("--model is required when running a slice")

    override = args.base_url or os.environ.get("SERVE_BASE_URL") or os.environ.get("BASE_URL")
    if override:
        apply_serve_base_url(config, override)

    try:
        require_clean_worktree(REPO_ROOT)
    except DirtyWorktreeError as exc:
        print(str(exc), flush=True)
        return 2

    model_spec = resolve_model(config, args.model)
    campaign = str(config["run"]["campaign"])
    root = campaign_root(args.artifact_root if args.artifact_root is not None else config["run"]["artifact_root"], campaign, REPO_ROOT)
    programs = [args.program] if args.program else list(config["jobs"]["programs"])
    for program in programs:
        asyncio.run(
            run_slice_async(
                config,
                model_spec,
                program=program,
                campaign_dir=root,
                topology=args.topology,
                k=args.k,
                seed_from=args.seed_from,
                seed_to=args.seed_to,
                mock_policy=args.mock_policy,
                require_clean=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
