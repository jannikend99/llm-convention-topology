"""Single-writer persistence layer: run_id/path scheme, pickle I/O, metadata
sidecars, and the append-only events stream.

Ashery `utils.py::load_mainframe`/`get_empty_population`/`get_player` port
(WORKING.md §2): replaces the bare-`except` pickle resume with explicit
run_id-addressed I/O and typed errors (§0 architecture principle 5). This is
the *only* module in the package that writes files (§0 principle 3);
`live/` reads the same files but never writes them.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    import pandas as pd


class PersistenceError(Exception):
    """Raised on missing/corrupt run artifacts or malformed metadata."""


def build_run_id(model_shorthand: str, topology: str, cm_k: int, run_seed: int) -> str:
    return f"{model_shorthand}_{topology}_k{cm_k}_s{run_seed:04d}"


@dataclass(frozen=True)
class RunPaths:
    pickle_path: Path
    meta_path: Path
    events_path: Path


def run_paths(data_dir: Path, logs_dir: Path, model_shorthand: str, topology: str, run_id: str) -> RunPaths:
    run_dir = Path(data_dir) / "runs" / model_shorthand / topology
    return RunPaths(
        pickle_path=run_dir / f"{run_id}.pkl",
        meta_path=run_dir / f"{run_id}.meta.json",
        events_path=Path(logs_dir) / f"{run_id}.events.jsonl",
    )


def ensure_run_dirs(paths: RunPaths) -> None:
    paths.pickle_path.parent.mkdir(parents=True, exist_ok=True)
    paths.events_path.parent.mkdir(parents=True, exist_ok=True)


def save_run_pickle(
    path: Path,
    simulation: Mapping[int, Mapping[str, Any]],
    tracker: Mapping[str, Any],
    convergence: Mapping[str, Any],
) -> None:
    payload = {"simulation": dict(simulation), "tracker": dict(tracker), "convergence": dict(convergence)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        pickle.dump(payload, handle)
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


META_FIELDS = (
    "run_id",
    "topology",
    "cm_k",
    "model_id",
    "model_shorthand",
    "endpoint_base_url",
    "graph_seed",
    "run_seed",
    "adjacency_hash",
    "t_gate",
    "t_phase1_end",
    "eligibility",
    "incumbent_label",
    "committed_to",
    "phase2_horizon",
    "config_hash",
    "run_status",
    "started_at",
    "finished_at",
    "n_api_calls",
    "n_retries",
    "prompt_template_version",
    "code_commit",
)


def write_meta(path: Path, metadata: Mapping[str, Any]) -> None:
    missing = [field for field in META_FIELDS if field not in metadata]
    if missing:
        raise PersistenceError(f"Metadata missing required fields: {missing}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(metadata), handle, indent=2, sort_keys=True)
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
    """Analysis-output JSON writer (N1: single-writer principle covers `outputs/` too)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(payload), handle, indent=2, sort_keys=True, default=str)


def write_analysis_csv(path: Path, table: "pd.DataFrame") -> None:
    """Analysis-output CSV writer (N1: single-writer principle covers `outputs/` too)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)


def delete_run_artifacts(paths: RunPaths) -> None:
    """Delete a failed run's sidecar + pickle before a `--retry-failed` re-attempt.

    N1: centralizes the direct `unlink(missing_ok=True)` calls previously
    inlined in `run_pilot.py`/`run_main.py`'s retry-cleanup paths -- no
    change to what gets deleted or when, just the single writer that does it.
    """
    paths.meta_path.unlink(missing_ok=True)
    paths.pickle_path.unlink(missing_ok=True)


class EventWriter:
    """Append-only, line-buffered `.jsonl` event stream.

    The only writer for `logs/*.events.jsonl`; `live/reader.py` tails these
    files and must never open a pickle of an active run (§0 principle 3).
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", buffering=1, encoding="utf-8")

    def emit(self, event: Mapping[str, Any]) -> None:
        self._handle.write(json.dumps(dict(event), sort_keys=True) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "EventWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
