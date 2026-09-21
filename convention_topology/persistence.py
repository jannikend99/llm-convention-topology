"""Campaign artifacts: pickle, sidecar, events under one campaign root."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    import pandas as pd


class PersistenceError(Exception):
    """Raised on missing or corrupt run artifacts."""


SCHEMA_VERSION = 1

SIDECAR_FIELDS = (
    "run_id",
    "campaign",
    "run_key",
    "program",
    "init_mode",
    "topology",
    "cell_key",
    "seed_index",
    "sampling_plan",
    "attempted_per_cell",
    "replaced",
    "adaptive_targeting",
    "N",
    "H",
    "W",
    "string_length",
    "edge_count",
    "realized_mean_degree",
    "nominal_degree",
    "ws_k",
    "ws_p",
    "ba_m",
    "graph_draw_attempts",
    "graph_connected",
    "lattice_kind",
    "cm_k",
    "cm_mode",
    "pairing_rule",
    "rewards_match",
    "rewards_mismatch",
    "success_rule",
    "gate_threshold",
    "gate_window",
    "cap_phase1",
    "phase2_horizon",
    "bound_extensions",
    "retry_max_attempts",
    "temperature",
    "max_tokens",
    "top_p",
    "top_k",
    "json_schema",
    "response_format",
    "label_pool",
    "pool_seed",
    "pool_sha256",
    "options",
    "incumbent_index",
    "incumbent_label",
    "committed_to",
    "committed_ids",
    "model_id",
    "model_revision",
    "model_shorthand",
    "served_model_name",
    "thinking",
    "reasoning_effort",
    "thinking_always_on",
    "fallback_applied",
    "fallback_from",
    "provider",
    "endpoint_base_url",
    "cloud_credential_used",
    "vllm_version",
    "torch_version",
    "python_version",
    "dtype",
    "quantization",
    "tensor_parallel",
    "gpu_ids",
    "gpu_type",
    "max_concurrent_runs",
    "in_flight_limit",
    "max_num_seqs",
    "homogeneous",
    "graph_seed",
    "environment_seed",
    "model_seed",
    "base_seed",
    "seed_scheme_version",
    "environment_substream_tags",
    "adjacency_hash",
    "prompt_template_version",
    "prompt_template_hash",
    "schema_version",
    "config_hash",
    "code_commit",
    "protocol_fingerprint",
    "chat_template_hash",
    "slurm_job_id",
    "hostname",
    "run_segments",
    "checkpoint_every",
    "last_checkpoint_t",
    "artifact_root",
    "run_status",
    "stop_reason",
    "error_class",
    "gate_passed",
    "prepared_state_valid",
    "t_gate",
    "t_phase1_end",
    "t_cm_start",
    "started_at",
    "finished_at",
    "n_interactions",
    "n_api_calls",
    "n_retries",
    "n_skipped_cm_turns",
    "wait_on_model_ms",
    "n_models_in_run",
)


def encode_run_key(
    *,
    campaign: str,
    program: str,
    model_id: str,
    topology: str,
    cm_k: int | None,
    seed_index: int,
) -> dict[str, Any]:
    return {
        "campaign": campaign,
        "cell_key": {
            "program": program,
            "model_id": model_id,
            "topology": topology,
            "cm_k": cm_k,
        },
        "seed_index": seed_index,
    }


def build_run_id(run_key: Mapping[str, Any]) -> str:
    cell = run_key["cell_key"]
    cm = "na" if cell["cm_k"] is None else f"k{cell['cm_k']}"
    canonical = json.dumps(run_key, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    model_token = str(cell["model_id"]).split("/")[-1][:24]
    return (
        f"{run_key['campaign']}_{cell['program']}_{model_token}_"
        f"{cell['topology']}_{cm}_s{run_key['seed_index']:02d}_{digest}"
    )


@dataclass(frozen=True)
class RunPaths:
    pickle_path: Path
    meta_path: Path
    events_path: Path
    lock_path: Path


def campaign_root(artifact_root: str | Path | None, campaign: str, repo_root: Path) -> Path:
    if artifact_root:
        return Path(artifact_root)
    return repo_root / "data" / "runs" / campaign


def run_paths(root: Path, model_shorthand: str, topology: str, run_id: str) -> RunPaths:
    run_dir = Path(root) / "runs" / model_shorthand / topology
    return RunPaths(
        pickle_path=run_dir / f"{run_id}.pkl",
        meta_path=run_dir / f"{run_id}.meta.json",
        events_path=run_dir / f"{run_id}.events.jsonl",
        lock_path=run_dir / f"{run_id}.lock",
    )


def ensure_run_dirs(paths: RunPaths) -> None:
    paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)


def save_run_pickle(
    path: Path,
    simulation: Mapping[int, Mapping[str, Any]],
    tracker: Mapping[str, Any],
    convergence: Mapping[str, Any],
    rng_states: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        "simulation": dict(simulation),
        "tracker": dict(tracker),
        "convergence": dict(convergence),
        "rng_states": dict(rng_states or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        pickle.dump(payload, handle)
        handle.flush()
    tmp_path.replace(path)


def load_run_pickle(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PersistenceError(f"No run pickle at {path}")
    with path.open("rb") as handle:
        try:
            payload = pickle.load(handle)
        except (pickle.UnpicklingError, EOFError) as exc:
            raise PersistenceError(f"Corrupt run pickle at {path}") from exc
    for key in ("simulation", "tracker", "convergence"):
        if key not in payload:
            raise PersistenceError(f"Run pickle at {path} missing key {key!r}")
    return payload


def empty_sidecar() -> dict[str, Any]:
    return {field: None for field in SIDECAR_FIELDS}


def write_meta(path: Path, metadata: Mapping[str, Any]) -> None:
    missing = [field for field in SIDECAR_FIELDS if field not in metadata]
    if missing:
        raise PersistenceError(f"Metadata missing required fields: {missing}")
    banned = [key for key in metadata if key not in SIDECAR_FIELDS]
    if banned:
        raise PersistenceError(f"unknown sidecar keys present: {banned}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(metadata), handle, indent=2, sort_keys=True)
        handle.flush()
    tmp_path.replace(path)


def read_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PersistenceError(f"No metadata sidecar at {path}")
    with path.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle)
        except json.JSONDecodeError as exc:
            raise PersistenceError(f"Corrupt metadata sidecar at {path}") from exc


def write_analysis_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True, default=str)


def write_analysis_csv(path: Path, table: "pd.DataFrame") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    if not lines:
        return []
    complete, last = lines[:-1], lines[-1]
    for line in complete:
        if not line.strip():
            continue
        records.append(json.loads(line))
    if last.strip():
        try:
            records.append(json.loads(last))
        except json.JSONDecodeError:
            pass
    return records


class EventWriter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", buffering=1, encoding="utf-8")

    def emit(self, event: Mapping[str, Any]) -> None:
        payload = dict(event)
        self._handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        self._handle.flush()

    def sync(self) -> None:
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "EventWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
