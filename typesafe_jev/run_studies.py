#!/usr/bin/env python3
"""Run Study 1 and Study 2 on hosted Jev, outside the counted vLLM path.

Study 1 is emergence. Study 2 is the prepared committed-minority program.
Both reuse ``convention_topology`` for networks, prompts, the gate, and artifacts.
Requests are paced at the published TypeSafe limit of 1200 per minute.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from convention_topology.campaign import ensure_campaign_files
from convention_topology.config import (
    K_SET,
    TOPOLOGIES,
    ConfigError,
    ModelSpec,
    check_campaign_name,
    load_config,
)
from convention_topology.git_guard import current_commit
from convention_topology.orchestration import cell_grid, format_queue_summary, parse_task
from convention_topology.persistence import build_run_id, campaign_root, encode_run_key, read_meta, run_paths
from convention_topology.run import (
    PROGRAM_CM,
    PROGRAM_EMERGENCE,
    build_run_config,
    execute_run_async,
    install_process_sigterm,
)
from typesafe_jev.client import DEFAULT_MODEL, REQUESTS_PER_MINUTE, RpmLimiter, TypeSafeNamingClient


CAMPAIGN = "jev-system-one"
API_ROOT = "https://api.typesafe.ai"


def jev_model_spec(*, model_id: str, temperature: float, max_concurrent_runs: int, in_flight_limit: int) -> ModelSpec:
    return ModelSpec(
        shorthand="jev",
        provider="typesafe",
        model_id=model_id,
        revision=model_id,
        base_url=API_ROOT,
        api_key="ENV",
        temperature=temperature,
        max_tokens=64,
        thinking=False,
        thinking_always_on=False,
        reasoning_effort=None,
        dtype=None,
        quantization=None,
        gpus=0,
        tp=1,
        max_model_len=64000,
        max_concurrent_runs=max_concurrent_runs,
        in_flight_limit=in_flight_limit,
        max_num_seqs=in_flight_limit,
        seed_indices_per_slice={PROGRAM_EMERGENCE: 32, PROGRAM_CM: 32},
        send_chat_template_kwargs=False,
    )


def study_cells(config: dict, studies: set[int], *, seed_from: int, seed_to: int | None) -> list[dict]:
    rows: list[dict] = []
    if 1 in studies:
        rows.extend(
            cell_grid(
                config,
                program=PROGRAM_EMERGENCE,
                seed_from=seed_from,
                seed_to=seed_to,
            )
        )
    if 2 in studies:
        rows.extend(
            cell_grid(
                config,
                program=PROGRAM_CM,
                seed_from=seed_from,
                seed_to=seed_to,
            )
        )
    return rows


def parse_studies(raw: str) -> set[int]:
    studies: set[int] = set()
    for part in raw.split(","):
        token = part.strip()
        if token not in {"1", "2"}:
            raise argparse.ArgumentTypeError("studies must be 1, 2, or 1,2")
        studies.add(int(token))
    if not studies:
        raise argparse.ArgumentTypeError("studies must be 1, 2, or 1,2")
    return studies


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Naming Game Study 1 and Study 2 on TypeSafe Jev.")
    parser.add_argument("--studies", type=parse_studies, default={1, 2}, help="1, 2, or 1,2 (default both)")
    parser.add_argument("--task", action="append", default=None, help="Optional counted task spec. Repeatable. Overrides --studies.")
    parser.add_argument("--campaign", default=CAMPAIGN)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rpm", type=int, default=REQUESTS_PER_MINUTE)
    parser.add_argument("--max-concurrent-runs", type=int, default=48)
    parser.add_argument("--in-flight-limit", type=int, default=64)
    parser.add_argument("--seed-from", type=int, default=0)
    parser.add_argument("--seed-to", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print the cell grid and exit. No API key required.")
    args = parser.parse_args(argv)

    if args.rpm < 1:
        parser.error("--rpm must be positive")
    if args.seed_from < 0:
        parser.error("--seed-from must be >= 0")
    if args.seed_to is not None and args.seed_to <= args.seed_from:
        parser.error("--seed-to must be greater than --seed-from")

    try:
        campaign = check_campaign_name(args.campaign)
    except ConfigError as exc:
        parser.error(str(exc))
    if campaign == "experiment":
        parser.error("refusing campaign 'experiment'; this runner is not the counted path")

    config = load_config(args.config)
    config["run"]["campaign"] = campaign
    if args.task:
        cells: list[dict] = []
        for spec in args.task:
            task = parse_task(spec)
            for seed_index in range(task.seed_from, task.seed_to):
                ks = (None,) if task.program == PROGRAM_EMERGENCE else task.k_values
                for topology in task.topologies:
                    for cm_k in ks:
                        cells.append(
                            {
                                "program": task.program,
                                "topology": topology,
                                "cm_k": cm_k,
                                "seed_index": seed_index,
                            }
                        )
    else:
        cells = study_cells(config, set(args.studies), seed_from=args.seed_from, seed_to=args.seed_to)

    print(
        f"[jev] model={args.model} rpm={args.rpm} campaign={campaign} "
        f"topologies={','.join(TOPOLOGIES)} k={','.join(str(k) for k in K_SET)}",
        flush=True,
    )
    print(format_queue_summary(cells), flush=True)
    if args.dry_run:
        print("[jev] dry-run", flush=True)
        return 0

    root = campaign_root(
        args.artifact_root if args.artifact_root is not None else config["run"]["artifact_root"],
        campaign,
        REPO_ROOT,
    )
    print(f"[jev] artifact_root={root}", flush=True)
    return asyncio.run(
        _run(
            config,
            cells,
            campaign_dir=root,
            model_id=args.model,
            rpm=args.rpm,
            max_concurrent_runs=args.max_concurrent_runs,
            in_flight_limit=args.in_flight_limit,
        )
    )


async def _run(
    config: dict,
    cells: list[dict],
    *,
    campaign_dir: Path,
    model_id: str,
    rpm: int,
    max_concurrent_runs: int,
    in_flight_limit: int,
) -> int:
    from typesafe_sdk import AsyncTypeSafeClient

    files = ensure_campaign_files(campaign_dir, config)
    install_process_sigterm()
    spec = jev_model_spec(
        model_id=model_id,
        temperature=float(config["protocol"]["temperature"]),
        max_concurrent_runs=max_concurrent_runs,
        in_flight_limit=in_flight_limit,
    )
    limiter = asyncio.Semaphore(in_flight_limit)
    rpm_limiter = RpmLimiter(rpm)
    run_slots = asyncio.Semaphore(max_concurrent_runs)
    commit = current_commit(REPO_ROOT)
    statuses: list[str] = []

    async with AsyncTypeSafeClient(model=model_id) as sdk:
        async def _one(cell: dict) -> str:
            program = str(cell["program"])
            cfg = build_run_config(
                config,
                spec,
                program=program,
                topology=str(cell["topology"]),
                seed_index=int(cell["seed_index"]),
                cm_k=cell["cm_k"],
                pool_labels=files["pool"]["labels"],
                pool_sha256=files["pool"]["sha256"],
                code_commit=commit,
                artifact_root=str(campaign_dir),
            )
            run_key = encode_run_key(
                campaign=cfg.campaign,
                program=cfg.program,
                model_id=cfg.model_id,
                topology=cfg.topology,
                cm_k=cfg.cm_k,
                seed_index=cfg.seed_index,
            )
            run_id = build_run_id(run_key)
            paths = run_paths(campaign_dir, cfg.model_shorthand, cfg.topology, run_id)
            if paths.meta_path.exists():
                meta = read_meta(paths.meta_path)
                if meta.get("run_status") in {"completed", "censored", "failed"}:
                    print(f"[skip] {run_id} status={meta['run_status']}", flush=True)
                    return str(meta["run_status"])
            async with run_slots:
                client = TypeSafeNamingClient(
                    sdk,
                    model_id=model_id,
                    temperature=cfg.temperature,
                    model_seed=cfg.model_seed,
                    limiter=rpm_limiter,
                )
                await execute_run_async(
                    cfg,
                    client,
                    campaign_dir=campaign_dir,
                    health=lambda: True,
                    limiter=limiter,
                    install_sigterm=False,
                )
                status = read_meta(paths.meta_path)["run_status"]
                print(f"[done] {run_id} status={status}", flush=True)
                return status

        for coro in asyncio.as_completed([_one(cell) for cell in cells]):
            statuses.append(await coro)

    failed = sum(1 for status in statuses if status == "failed")
    print(f"[jev] cells={len(statuses)} failed={failed}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
