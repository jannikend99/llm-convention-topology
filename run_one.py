#!/usr/bin/env python3
"""CLI: run one counted cell. Always writes pickle, sidecar, and events."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from convention_topology.campaign import ensure_campaign_files
from convention_topology.config import (
    K_SET,
    TOPOLOGIES,
    ConfigError,
    apply_cli_protocol_env,
    check_campaign_name,
    load_config,
    resolve_model,
)
from convention_topology.git_guard import DirtyWorktreeError, current_commit, require_clean_worktree
from convention_topology.orchestration import build_client
from convention_topology.persistence import campaign_root, read_meta
from convention_topology.pool import options_for_program
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE, build_run_config, execute_run_async


REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one counted emergence or CM cell.")
    parser.add_argument("--program", required=True, choices=[PROGRAM_EMERGENCE, PROGRAM_CM])
    parser.add_argument("--model", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--k", type=int, default=None, dest="cm_k")
    parser.add_argument("--seed-index", type=int, required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--campaign", default=None)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--mock-policy", default="imitate_modal")
    args = parser.parse_args(argv)

    if not args.campaign:
        parser.error("--campaign is required")
    if args.topology not in TOPOLOGIES:
        parser.error(f"unknown topology {args.topology!r}; choose from {list(TOPOLOGIES)}")
    if args.seed_index < 0:
        parser.error("--seed-index must be non-negative")
    if args.seed_index >= 32:
        parser.error("--seed-index must be less than attempted_per_cell (32)")
    if args.program == PROGRAM_CM and args.cm_k not in K_SET:
        parser.error(f"--k is required for --program cm and must be one of {list(K_SET)}")
    if args.program == PROGRAM_EMERGENCE and args.cm_k is not None:
        parser.error("--k is only valid for --program cm")
    if args.program == PROGRAM_EMERGENCE:
        args.cm_k = None

    try:
        require_clean_worktree(REPO_ROOT)
    except DirtyWorktreeError as exc:
        print(str(exc), flush=True)
        return 2

    try:
        config = load_config(args.config)
        config["run"]["campaign"] = check_campaign_name(args.campaign)
        apply_cli_protocol_env(config)
        model_spec = resolve_model(config, args.model)
    except ConfigError as exc:
        parser.error(str(exc))
    campaign = str(config["run"]["campaign"])
    root = campaign_root(
        args.artifact_root if args.artifact_root is not None else config["run"]["artifact_root"],
        campaign,
        REPO_ROOT,
    )
    files = ensure_campaign_files(root, config)
    cfg = build_run_config(
        config,
        model_spec,
        program=args.program,
        topology=args.topology,
        seed_index=args.seed_index,
        cm_k=args.cm_k,
        pool_labels=files["pool"]["labels"],
        pool_sha256=files["pool"]["sha256"],
        code_commit=current_commit(REPO_ROOT),
        artifact_root=str(root),
    )
    options = options_for_program(files["pool"]["labels"], args.program)
    client = build_client(
        model_spec, args.mock_policy, cfg.model_seed, options, json_schema=cfg.json_schema
    )

    async def _run():
        return await execute_run_async(
            cfg, client, campaign_dir=root, limiter=asyncio.Semaphore(cfg.in_flight_limit)
        )

    paths = asyncio.run(_run())
    status = read_meta(paths.meta_path)["run_status"]
    print(f"[done] run_id={paths.pickle_path.stem} status={status}", flush=True)
    return 0 if status in {"completed", "censored"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
