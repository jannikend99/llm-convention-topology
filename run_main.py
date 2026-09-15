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
    apply_cli_protocol_env,
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
from convention_topology.reopen_failed import ReopenFailedError, reopen_failed
from convention_topology.tech_check import DEFAULT_TECH_CHECK_N, run_tech_check


REPO_ROOT = Path(__file__).resolve().parent


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
    parser.add_argument("--reopen-failed", action="store_true")
    parser.add_argument("--apply", action="store_true")
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
    if args.apply and not args.reopen_failed:
        parser.error("--apply requires --reopen-failed")
    reopen_blockers = (
        ("--task", bool(args.tasks)),
        ("--health", args.health),
        ("--watch", args.watch),
        ("--tech-check", args.tech_check),
        ("--print-queue", args.print_queue),
    )
    if args.reopen_failed:
        for flag, on in reopen_blockers:
            if on:
                parser.error(f"--reopen-failed cannot be combined with {flag}")

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

    if args.reopen_failed:
        if not args.campaign:
            parser.error("--campaign is required")
        if not args.model:
            parser.error("--model is required")
        root = campaign_root(args.artifact_root, args.campaign, REPO_ROOT)
        try:
            rows = reopen_failed(
                root,
                args.model,
                campaign=args.campaign,
                apply=bool(args.apply),
            )
        except ReopenFailedError as exc:
            print(str(exc), flush=True)
            return 2
        mode = "applied" if args.apply else "dry-run"
        eligible = [row for row in rows if not row.get("skipped")]
        skipped = [row for row in rows if row.get("skipped")]
        print(f"reopen-failed {mode} model={args.model} campaign={args.campaign}", flush=True)
        print(f"eligible {len(eligible)} skipped {len(skipped)}", flush=True)
        for row in eligible:
            print(
                f"  {row.get('program')} {row.get('topology')} seed={row.get('seed_index')} "
                f"t={row.get('last_checkpoint_t')} {row.get('run_id')}",
                flush=True,
            )
        for row in skipped:
            print(
                f"  skip {row.get('skipped')} {row.get('run_id')} {row.get('path')}",
                flush=True,
            )
        if not args.apply and eligible:
            print("pass --apply to set those sidecars to interrupted", flush=True)
        return 0

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
    try:
        apply_cli_protocol_env(config)
    except ConfigError as exc:
        parser.error(str(exc))
    if os.environ.get("PILOT_CAP_PHASE1") or os.environ.get("PILOT_PHASE2_HORIZON"):
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
