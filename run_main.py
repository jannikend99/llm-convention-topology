#!/usr/bin/env python3
"""Counted campaign CLI: task queue and one async slice."""

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
from convention_topology.orchestration import (
    TaskSpecError,
    flatten_tasks,
    format_queue_summary,
    parse_task,
    run_slice_async,
)
from convention_topology.health import run_health_cli
from convention_topology.persistence import campaign_root
from convention_topology.tech_check import DEFAULT_TECH_CHECK_N, run_tech_check


REPO_ROOT = Path(__file__).resolve().parent

DIAG_FULL_KNOB_PREFIXES = ("diag-ashery", "diag-h12-", "diag-n48-", "diag-strings-")


def _campaign_requires_full_diag_knobs(campaign: str) -> bool:
    name = str(campaign)
    return name.startswith(DIAG_FULL_KNOB_PREFIXES)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parse_task_list(parser: argparse.ArgumentParser, specs: list[str]) -> list[dict]:
    try:
        tasks = [parse_task(spec) for spec in specs]
        return flatten_tasks(tasks)
    except TaskSpecError as exc:
        parser.error(str(exc))
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Counted naming-game campaign queue.")
    parser.add_argument("--print-jobs", action="store_true")
    parser.add_argument("--print-queue", action="store_true")
    parser.add_argument("--tech-check", action="store_true")
    parser.add_argument("--tech-check-n", type=_positive_int, default=None)
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--task", action="append", default=[], dest="tasks")
    parser.add_argument("--model", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--campaign", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    if args.print_jobs:
        parser.error("--print-jobs is removed; use --print-queue")
    if args.tech_check and args.print_queue:
        parser.error("--tech-check cannot be combined with --print-queue")
    if args.tech_check and args.tasks:
        parser.error("--tech-check cannot be combined with --task")
    if args.health and args.watch:
        parser.error("--health cannot be combined with --watch")
    if args.health and args.tasks:
        parser.error("--health cannot be combined with --task")
    if args.watch and args.tasks:
        parser.error("--watch cannot be combined with --task")
    if args.health and args.tech_check:
        parser.error("--health cannot be combined with --tech-check")
    if args.watch and args.tech_check:
        parser.error("--watch cannot be combined with --tech-check")
    if args.health and args.print_queue:
        parser.error("--health cannot be combined with --print-queue")
    if args.watch and args.print_queue:
        parser.error("--watch cannot be combined with --print-queue")
    if args.tech_check_n is not None and not args.tech_check:
        parser.error("--tech-check-n requires --tech-check")

    if args.tech_check:
        if not args.model:
            parser.error("--model is required")
        campaign_name = args.campaign if args.campaign else "tech-check"
        if campaign_name == "experiment":
            parser.error("--tech-check refuses campaign experiment")
        n = args.tech_check_n if args.tech_check_n is not None else DEFAULT_TECH_CHECK_N
        try:
            require_clean_worktree(REPO_ROOT)
        except DirtyWorktreeError as exc:
            print(str(exc), flush=True)
            return 2
        config = load_config(args.config)
        config["run"]["campaign"] = check_campaign_name(campaign_name)
        override = args.base_url or os.environ.get("SERVE_BASE_URL") or os.environ.get("BASE_URL")
        model_spec = resolve_model(config, args.model)
        if override:
            if config["serve"]["provider"] != "mock" and not is_localhost_url(override):
                raise ConfigError("non-localhost serve.base_url fails unless provider is mock")
            model_spec = replace(model_spec, base_url=override)
        root = campaign_root(
            args.artifact_root if args.artifact_root is not None else config["run"]["artifact_root"],
            campaign_name,
            REPO_ROOT,
        )
        return run_tech_check(
            config,
            model_spec,
            campaign_dir=root,
            n=n,
            mock_policy=args.mock_policy,
        )

    if args.health or args.watch:
        if not args.campaign:
            parser.error("--campaign is required")
        if not args.model:
            parser.error("--model is required")
        root = campaign_root(args.artifact_root, args.campaign, REPO_ROOT)
        return run_health_cli(
            campaign_dir=root,
            model_shorthand=args.model,
            watch=bool(args.watch),
        )

    if not args.tasks:
        parser.error("at least one --task is required")

    cells = _parse_task_list(parser, args.tasks)
    if args.print_queue:
        print(format_queue_summary(cells))
        return 0

    if not args.campaign:
        parser.error("--campaign is required")
    if not args.model:
        parser.error("--model is required")

    config = load_config(args.config)
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
    if campaign_name != "experiment":
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
    root = campaign_root(
        args.artifact_root if args.artifact_root is not None else config["run"]["artifact_root"],
        campaign,
        REPO_ROOT,
    )
    asyncio.run(
        run_slice_async(
            config,
            model_spec,
            cells=cells,
            campaign_dir=root,
            mock_policy=args.mock_policy,
            require_clean=False,
            task_argv=args.tasks,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
