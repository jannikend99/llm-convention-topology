"""Reopen runs that stopped on a cap or horizon so the same run_id can continue.

Dry-run unless apply is set. A lower cap or horizon refuses the whole call.
Failed runs stay failed. Gated Study 1 runs stay finished unless explicitly
selected for post-gate observation to their existing cap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import fcntl

from convention_topology.persistence import PersistenceError, read_meta, write_meta

PROGRAM_EMERGENCE = "emergence"
PROGRAM_CM = "cm"


class ExtendBoundsError(Exception):
    """Extend refused or a sidecar could not be read."""


def _decreased(meta: dict[str, Any], *, cap_phase1: int, phase2_horizon: int) -> str | None:
    program = meta.get("program")
    if program == PROGRAM_EMERGENCE:
        stored = meta.get("cap_phase1")
        if isinstance(stored, int) and cap_phase1 < stored:
            return "cap_phase1"
    if program == PROGRAM_CM:
        stored = meta.get("phase2_horizon")
        if isinstance(stored, int) and phase2_horizon < stored:
            return "phase2_horizon"
    return None


def _extension(
    meta: dict[str, Any],
    *,
    cap_phase1: int,
    phase2_horizon: int,
) -> dict[str, Any] | None:
    program = meta.get("program")
    status = meta.get("run_status")
    reason = meta.get("stop_reason")
    n_interactions = int(meta.get("n_interactions") or 0)
    if program == PROGRAM_EMERGENCE and status == "censored" and reason == "cap" and cap_phase1 > n_interactions:
        return {
            "field": "cap_phase1",
            "previous": meta.get("cap_phase1"),
            "new": cap_phase1,
            "t": n_interactions,
        }
    if program == PROGRAM_CM and status == "completed" and reason == "horizon" and phase2_horizon > n_interactions:
        return {
            "field": "phase2_horizon",
            "previous": meta.get("phase2_horizon"),
            "new": phase2_horizon,
            "t": n_interactions,
        }
    return None


def extend_bounds(
    campaign_dir: Path,
    model_shorthand: str,
    *,
    cap_phase1: int,
    phase2_horizon: int,
    apply: bool = False,
    continue_gated: bool = False,
) -> list[dict[str, Any]]:
    """List runs a higher bound would continue. Write sidecars only when apply is set."""
    root = Path(campaign_dir)
    runs = root / "runs" / model_shorthand
    if not runs.is_dir():
        return []
    metas: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(runs.rglob("*.meta.json")):
        try:
            meta = read_meta(path)
        except PersistenceError as exc:
            raise ExtendBoundsError(f"unreadable sidecar {path}: {exc}") from exc
        if meta.get("model_shorthand") != model_shorthand:
            continue
        metas.append((path, meta))

    for _path, meta in metas:
        field = _decreased(meta, cap_phase1=cap_phase1, phase2_horizon=phase2_horizon)
        if field is not None:
            raise ExtendBoundsError(f"{field} decreased; refuse extend")

    changed: list[dict[str, Any]] = []
    for path, meta in metas:
        if continue_gated:
            if not (
                meta.get("program") == PROGRAM_EMERGENCE
                and meta.get("run_status") == "completed"
                and meta.get("stop_reason") == "gate"
                and meta.get("gate_passed") is True
                and isinstance(meta.get("t_gate"), int)
                and int(meta.get("n_interactions") or 0) < cap_phase1
            ):
                continue
            if meta.get("cap_phase1") != cap_phase1:
                raise ExtendBoundsError("post-gate observation requires the unchanged stored cap_phase1")
            extension = {
                "field": "post_gate_observation",
                "previous": meta["n_interactions"],
                "new": cap_phase1,
                "t": meta["n_interactions"],
                "original_meta": dict(meta),
            }
        else:
            extension = _extension(meta, cap_phase1=cap_phase1, phase2_horizon=phase2_horizon)
        if extension is None:
            continue
        pickle_path = path.with_name(path.name[: -len(".meta.json")] + ".pkl")
        row = {
            "path": str(path),
            "run_id": meta.get("run_id"),
            "topology": meta.get("topology"),
            "seed_index": meta.get("seed_index"),
            "program": meta.get("program"),
            "last_checkpoint_t": meta.get("last_checkpoint_t"),
            "field": extension["field"],
            "previous": extension["previous"],
            "new": extension["new"],
            "t": extension["t"],
            "skipped": None,
        }
        if not pickle_path.is_file():
            row["skipped"] = "missing_pickle"
            changed.append(row)
            continue
        if apply:
            lock_path = path.with_name(path.name[:-len(".meta.json")] + ".lock")
            with lock_path.open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise ExtendBoundsError(f"run is locked: {path}") from exc
                if read_meta(path) != meta:
                    raise ExtendBoundsError(f"sidecar changed during selection: {path}")
                history = list(meta.get("bound_extensions") or [])
                history.append(extension)
                meta["bound_extensions"] = history
                meta["run_status"] = "in_progress"
                meta["stop_reason"] = None
                meta["finished_at"] = None
                if extension["field"] == "cap_phase1":
                    meta["cap_phase1"] = cap_phase1
                elif extension["field"] == "phase2_horizon":
                    meta["phase2_horizon"] = phase2_horizon
                write_meta(path, meta)
        changed.append(row)
    return changed
