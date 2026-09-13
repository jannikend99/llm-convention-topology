#!/usr/bin/env python3
"""Counted campaign CLI: planner and one async slice."""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import replace
from pathlib import Path

from convention_topology.config import (
    ConfigError,
    apply_diag_protocol,
    apply_diag_tech_interactions,
    apply_pilot_bounds,
    check_campaign_name,
    is_localhost_url,
    load_config,
    resolve_model,
)
from convention_topology.git_guard import DirtyWorktreeError, require_clean_worktree
from convention_topology.orchestration import format_job_line, print_jobs, run_slice_async
from convention_topology.persistence import campaign_root
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE


REPO_ROOT = Path(__file__).resolve().parent

DIAG_FULL_KNOB_PREFIXES = ("diag-ashery", "diag-h12-", "diag-n48-", "diag-strings-")


def _campaign_requires_full_diag_knobs(campaign: str) -> bool:
    name = str(campaign)
    return name.startswith(DIAG_FULL_KNOB_PREFIXES)


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
    parser.add_argument("--campaign", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.campaign:
        config["run"]["campaign"] = check_campaign_name(args.campaign)
    campaign_name = str(config["run"]["campaign"])
    if _campaign_requires_full_diag_knobs(campaign_name):
        missing = [
            key
            for key in ("DIAG_N", "DIAG_H", "DIAG_POOL", "DIAG_DECODE", "DIAG_CAP")
            if not os.environ.get(key)
        ]
        if missing:
            parser.error(
                "this diag campaign requires DIAG_N, DIAG_H, DIAG_POOL, DIAG_DECODE, and DIAG_CAP; "
                f"missing {', '.join(missing)}"
            )
    diag_h = os.environ.get("DIAG_H")
    diag_pool = os.environ.get("DIAG_POOL")
    diag_cap = os.environ.get("DIAG_CAP")
    diag_n = os.environ.get("DIAG_N")
    diag_decode = os.environ.get("DIAG_DECODE")
    if diag_h or diag_pool or diag_cap or diag_n or diag_decode:
        if not diag_h or not diag_pool:
            parser.error("DIAG_H and DIAG_POOL must be set together")
        apply_diag_protocol(
            config,
            memory_h=int(diag_h),
            pool_kind=str(diag_pool),
            cap_phase1=int(diag_cap) if diag_cap else 1200,
            population_n=int(diag_n) if diag_n else None,
            decode=str(diag_decode) if diag_decode else None,
        )
    tech_n = os.environ.get("DIAG_TECH_INTERACTIONS")
    if tech_n:
        apply_diag_tech_interactions(config, int(tech_n))
    pilot_cap = os.environ.get("PILOT_CAP_PHASE1")
    pilot_horizon = os.environ.get("PILOT_PHASE2_HORIZON")
    if pilot_cap or pilot_horizon:
        apply_pilot_bounds(
            config,
            cap_phase1=int(pilot_cap) if pilot_cap else None,
            phase2_horizon=int(pilot_horizon) if pilot_horizon else None,
        )
        print(
            "[pilot] cap_phase1="
            f"{config['protocol']['cap_phase1']} phase2_horizon={config['protocol']['phase2_horizon']}",
            flush=True,
        )
    if args.print_jobs:
        for job in print_jobs(config, program=args.program):
            print(format_job_line(job))
        return 0

    if not args.model:
        parser.error("--model is required when running a slice")

    override = args.base_url or os.environ.get("SERVE_BASE_URL") or os.environ.get("BASE_URL")

    try:
        require_clean_worktree(REPO_ROOT)
    except DirtyWorktreeError as exc:
        print(str(exc), flush=True)
        return 2

    model_spec = resolve_model(config, args.model)
    if override:
        if config["serve"]["provider"] != "mock" and not is_localhost_url(override):
            raise ConfigError("non-localhost serve.base_url fails unless provider is mock")
        model_spec = replace(model_spec, base_url=override)
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
