"""Shared run-dispatch orchestration (§0 principle 6: CLIs are thin).

Emergence (organic Phase 1, W=10) and CM (prepared, W=2) are separate
programs with separate grids, run IDs, and targeting rules.
"""

from __future__ import annotations

import logging
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from convention_topology.config import config_hash, derive_seeds
from convention_topology.llm import OPENAI_RETRY_EXCEPTIONS, MockLLMClient, OpenAICompatClient, RetryPolicy
from convention_topology.persistence import PersistenceError, build_run_id, delete_run_artifacts, read_meta, run_paths
from convention_topology.prompting import PROMPT_TEMPLATE_VERSION
from convention_topology.run import PROGRAM_CM, PROGRAM_EMERGENCE, RunConfig, execute_run

TOPOLOGIES = ("complete", "random_regular", "lattice")
SEEDS_PER_TOPOLOGY = 12
K_LEVELS = 6
MAIN_K_LEVELS = range(1, 7)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_code_commit() -> str:
    """Real short git HEAD hash of *this* repo, or `"unknown"` outside a repo."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


@dataclass(frozen=True)
class GridCell:
    program: str
    topology: str
    seed_index: int
    cm_k: int
    graph_seed: int
    run_seed: int


def rewards(config) -> tuple[int, int]:
    return tuple(config.params.rewards_set[0])


def options_for_program(config, program: str) -> list[str]:
    if program == PROGRAM_EMERGENCE:
        return list(config.params.options_emergence)
    if program == PROGRAM_CM:
        return list(config.params.options_cm)
    raise ValueError(f"Unknown program {program!r}")


def build_run_config(
    config,
    model_spec,
    *,
    program: str,
    topology: str,
    cm_k: int,
    graph_seed: int,
    run_seed: int,
) -> RunConfig:
    opts = options_for_program(config, program)
    incumbent_index = int(config.params.incumbent_index) if program == PROGRAM_CM else 0
    resolved = {
        "program": program,
        "model": model_spec.shorthand,
        "provider": model_spec.provider,
        "model_id": model_spec.model_id,
        "endpoint_base_url": model_spec.base_url,
        "topology": topology,
        "cm_k": cm_k,
        "run_seed": run_seed,
        "graph_seed": graph_seed,
        "params": {
            "rewards": rewards(config),
            "options": opts,
            "memory_size": config.params.memory_size_set[0],
            "n": config.params.N,
            "incumbent_index": incumbent_index,
            "convergence_threshold": config.params.convergence_threshold,
            "max_phase1_interactions": config.params.max_phase1_interactions,
            "phase2_horizon": config.params.total_interactions,
        },
    }
    if model_spec.openrouter_provider is not None:
        resolved["openrouter_provider"] = model_spec.openrouter_provider
    return RunConfig(
        program=program,
        model_shorthand=model_spec.shorthand,
        model_id=model_spec.model_id,
        endpoint_base_url=model_spec.base_url,
        topology=topology,
        cm_k=cm_k,
        graph_seed=graph_seed,
        run_seed=run_seed,
        config_hash=config_hash(resolved),
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        code_commit=get_code_commit(),
        rewards=rewards(config),
        options=opts,
        memory_size=config.params.memory_size_set[0],
        n=config.params.N,
        incumbent_index=incumbent_index,
        convergence_threshold=config.params.convergence_threshold,
        max_phase1_interactions=config.params.max_phase1_interactions,
        phase2_horizon=config.params.total_interactions,
        checkpoint_every=config.run.checkpoint_every,
        degree=config.network.degree,
    )


def build_run_config_for_cell(config, model_spec, cell: GridCell) -> RunConfig:
    return build_run_config(
        config,
        model_spec,
        program=cell.program,
        topology=cell.topology,
        cm_k=cell.cm_k,
        graph_seed=cell.graph_seed,
        run_seed=cell.run_seed,
    )


def build_client(model_spec, mock_policy: str, run_seed: int, options_list: list[str]):
    if model_spec.shorthand == "mock":
        return MockLLMClient(policy=mock_policy, rng=random.Random(run_seed), options=options_list)
    return OpenAICompatClient(
        base_url=model_spec.base_url,
        model_id=model_spec.model_id,
        api_key_env=model_spec.api_key_env,
        temperature=model_spec.temperature,
        max_tokens=model_spec.max_tokens,
        openrouter_provider=model_spec.openrouter_provider,
    )


def retry_policy_for(model_spec) -> RetryPolicy:
    if model_spec.shorthand == "mock":
        return RetryPolicy()
    return RetryPolicy(retry_on=OPENAI_RETRY_EXCEPTIONS)


def _run_id_for_cell(model_shorthand: str, cell: GridCell) -> str:
    return build_run_id(
        model_shorthand,
        cell.topology,
        cell.run_seed,
        program=cell.program,
        cm_k=cell.cm_k,
    )


def existing_status(data_dir: Path, logs_dir: Path, model_spec, cell: GridCell) -> str | None:
    run_id = _run_id_for_cell(model_spec.shorthand, cell)
    paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
    if not paths.meta_path.exists():
        return None
    try:
        return read_meta(paths.meta_path)["run_status"]
    except PersistenceError:
        return None


def emergence_pilot_grid(base_seed: int) -> list[GridCell]:
    """36 rows: 12 seeds/topology, program=emergence, cm_k=0."""
    cells = []
    for topology in TOPOLOGIES:
        for seed_index in range(1, SEEDS_PER_TOPOLOGY + 1):
            graph_seed, run_seed = derive_seeds(base_seed, topology, 0, seed_index)
            cells.append(GridCell(PROGRAM_EMERGENCE, topology, seed_index, 0, graph_seed, run_seed))
    return cells


def cm_pilot_grid(base_seed: int) -> list[GridCell]:
    """36 rows: 12 seeds/topology, k cyclic 1..6,1..6, program=cm."""
    cells = []
    for topology in TOPOLOGIES:
        for seed_index in range(1, SEEDS_PER_TOPOLOGY + 1):
            cm_k = ((seed_index - 1) % K_LEVELS) + 1
            graph_seed, run_seed = derive_seeds(base_seed, topology, cm_k, seed_index)
            cells.append(GridCell(PROGRAM_CM, topology, seed_index, cm_k, graph_seed, run_seed))
    return cells


def pilot_grid(base_seed: int, program: str) -> list[GridCell]:
    if program == PROGRAM_EMERGENCE:
        return emergence_pilot_grid(base_seed)
    if program == PROGRAM_CM:
        return cm_pilot_grid(base_seed)
    raise ValueError(f"Unknown program {program!r}")


def run_cell(config, model_spec, cell: GridCell, *, data_dir: Path, logs_dir: Path, mock_policy: str) -> str:
    opts = options_for_program(config, cell.program)
    client = build_client(model_spec, mock_policy, cell.run_seed, opts)
    run_config = build_run_config_for_cell(config, model_spec, cell)
    paths = execute_run(
        run_config,
        client,
        data_dir=data_dir,
        logs_dir=logs_dir,
        retry_policy=retry_policy_for(model_spec),
    )
    return read_meta(paths.meta_path)["run_status"]


def run_batch(
    config,
    model_spec,
    cells: list[GridCell],
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    workers: int,
    retry_failed: bool,
) -> dict[str, str]:
    """Resume-by-sidecar batch execution. Returns {run_id: final_status}."""
    to_run: list[GridCell] = []
    results: dict[str, str] = {}

    for cell in cells:
        run_id = _run_id_for_cell(model_spec.shorthand, cell)
        status = existing_status(data_dir, logs_dir, model_spec, cell)
        if status in ("completed", "censored"):
            results[run_id] = status
            continue
        if status == "failed" and not retry_failed:
            results[run_id] = status
            continue
        if status == "failed" and retry_failed:
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, cell.topology, run_id)
            delete_run_artifacts(paths)
        to_run.append(cell)

    def _worker(cell: GridCell) -> tuple[str, str]:
        run_id = _run_id_for_cell(model_spec.shorthand, cell)
        try:
            status = run_cell(config, model_spec, cell, data_dir=data_dir, logs_dir=logs_dir, mock_policy=mock_policy)
        except Exception:
            logging.exception("orchestration: cell %s raised outside execute_run's own failure handling", run_id)
            status = existing_status(data_dir, logs_dir, model_spec, cell) or "failed"
        return run_id, status

    if workers <= 1:
        for cell in to_run:
            run_id, status = _worker(cell)
            results[run_id] = status
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for run_id, status in pool.map(_worker, to_run):
                results[run_id] = status

    return results


def run_pilot(
    config,
    model_spec,
    *,
    program: str,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    workers: int,
    retry_failed: bool,
) -> dict[str, str]:
    cells = pilot_grid(config.run.base_seed, program)
    return run_batch(
        config,
        model_spec,
        cells,
        data_dir=data_dir,
        logs_dir=logs_dir,
        mock_policy=mock_policy,
        workers=workers,
        retry_failed=retry_failed,
    )


def cm_cell_targets(config) -> list[dict]:
    """Per-cell (topology, cm_k) completed-run targets for the CM program."""
    targets = config.run.main_eligible_targets
    cap_factor = config.run.attempted_cap_factor
    rows = []
    for topology in TOPOLOGIES:
        low, high = targets[topology]
        for cm_k in MAIN_K_LEVELS:
            rows.append(
                {
                    "program": PROGRAM_CM,
                    "topology": topology,
                    "cm_k": cm_k,
                    "target_min": low,
                    "target_max": high,
                    "attempted_cap": low * cap_factor,
                }
            )
    return rows


def emergence_cell_targets(config) -> list[dict]:
    """Per-topology gate-eligible targets for the emergence program."""
    targets = config.run.main_eligible_targets
    cap_factor = config.run.attempted_cap_factor
    rows = []
    for topology in TOPOLOGIES:
        low, high = targets[topology]
        rows.append(
            {
                "program": PROGRAM_EMERGENCE,
                "topology": topology,
                "cm_k": 0,
                "target_min": low,
                "target_max": high,
                "attempted_cap": low * cap_factor,
            }
        )
    return rows


def cell_targets(config, program: str) -> list[dict]:
    if program == PROGRAM_EMERGENCE:
        return emergence_cell_targets(config)
    if program == PROGRAM_CM:
        return cm_cell_targets(config)
    raise ValueError(f"Unknown program {program!r}")


def _counts_as_success(program: str, status: str) -> bool:
    """Emergence success = gate-passed (completed). CM success = completed."""
    return status == "completed"


def run_cell_targeted(
    config,
    model_spec,
    program: str,
    topology: str,
    cm_k: int,
    target: int,
    attempted_cap: int,
    *,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    retry_failed: bool,
) -> dict:
    success_count = 0
    attempted_count = 0
    seed_index = 0
    runs: list[tuple[str, str]] = []

    while success_count < target and attempted_count < attempted_cap:
        seed_index += 1
        graph_seed, run_seed = derive_seeds(config.run.base_seed, topology, cm_k, seed_index)
        cell = GridCell(program, topology, seed_index, cm_k, graph_seed, run_seed)
        run_id = _run_id_for_cell(model_spec.shorthand, cell)

        status = existing_status(data_dir, logs_dir, model_spec, cell)
        if status in ("completed", "censored"):
            attempted_count += 1
            if _counts_as_success(program, status):
                success_count += 1
            runs.append((run_id, status))
            continue
        if status == "failed" and not retry_failed:
            attempted_count += 1
            runs.append((run_id, status))
            continue
        if status == "failed" and retry_failed:
            paths = run_paths(data_dir, logs_dir, model_spec.shorthand, topology, run_id)
            delete_run_artifacts(paths)

        opts = options_for_program(config, program)
        client = build_client(model_spec, mock_policy, cell.run_seed, opts)
        run_config = build_run_config_for_cell(config, model_spec, cell)
        paths = execute_run(
            run_config, client, data_dir=data_dir, logs_dir=logs_dir, retry_policy=retry_policy_for(model_spec)
        )
        result_status = read_meta(paths.meta_path)["run_status"]
        attempted_count += 1
        if _counts_as_success(program, result_status):
            success_count += 1
        runs.append((run_id, result_status))

    return {
        "program": program,
        "topology": topology,
        "cm_k": cm_k,
        "target": target,
        "attempted_cap": attempted_cap,
        "attempted": attempted_count,
        "eligible": success_count,
        "runs": runs,
    }


def run_main_study(
    config,
    model_spec,
    *,
    program: str,
    data_dir: Path,
    logs_dir: Path,
    mock_policy: str,
    retry_failed: bool,
    topology_filter: str | None = None,
) -> list[dict]:
    targets = cell_targets(config, program)
    if topology_filter:
        targets = [row for row in targets if row["topology"] == topology_filter]

    results = []
    for row in targets:
        result = run_cell_targeted(
            config,
            model_spec,
            program,
            row["topology"],
            row["cm_k"],
            target=row["target_min"],
            attempted_cap=row["attempted_cap"],
            data_dir=data_dir,
            logs_dir=logs_dir,
            mock_policy=mock_policy,
            retry_failed=retry_failed,
        )
        results.append(result)
    return results
