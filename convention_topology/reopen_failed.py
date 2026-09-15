"""Reopen terminal failed cells so the same run_id can resume.

Counted campaign `experiment` is refused. Only `attempts_exhausted` is
reopened, as a technical retry of the same seed (not a replacement seed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from convention_topology.persistence import PersistenceError, read_meta, write_meta

ALLOWED_ERROR = "attempts_exhausted"


class ReopenFailedError(Exception):
    """Operator reopen refused or sidecar unreadable."""


def _campaign_allows_reopen(campaign: str) -> None:
    name = str(campaign or "").strip()
    if not name:
        raise ReopenFailedError("campaign is required")
    if name == "experiment":
        raise ReopenFailedError("--reopen-failed refuses campaign experiment")


def reopen_failed(
    campaign_dir: Path,
    model_shorthand: str,
    *,
    campaign: str,
    error_class: str = ALLOWED_ERROR,
    apply: bool = False,
) -> list[dict[str, Any]]:
    """Set matching failed sidecars to interrupted so the queue will resume them."""
    _campaign_allows_reopen(campaign)
    if error_class != ALLOWED_ERROR:
        raise ReopenFailedError(f"only error_class={ALLOWED_ERROR} can be reopened")
    root = Path(campaign_dir)
    runs = root / "runs" / model_shorthand
    if not runs.is_dir():
        return []
    changed: list[dict[str, Any]] = []
    for path in sorted(runs.rglob("*.meta.json")):
        try:
            meta = read_meta(path)
        except PersistenceError as exc:
            raise ReopenFailedError(f"unreadable sidecar {path}: {exc}") from exc
        if meta.get("model_shorthand") != model_shorthand:
            continue
        if meta.get("run_status") != "failed":
            continue
        if meta.get("error_class") != ALLOWED_ERROR:
            continue
        pickle_path = path.with_name(path.name[: -len(".meta.json")] + ".pkl")
        if not pickle_path.is_file():
            changed.append(
                {
                    "path": str(path),
                    "run_id": meta.get("run_id"),
                    "topology": meta.get("topology"),
                    "seed_index": meta.get("seed_index"),
                    "skipped": "missing_pickle",
                }
            )
            continue
        row = {
            "path": str(path),
            "run_id": meta.get("run_id"),
            "topology": meta.get("topology"),
            "seed_index": meta.get("seed_index"),
            "program": meta.get("program"),
            "last_checkpoint_t": meta.get("last_checkpoint_t"),
            "skipped": None,
        }
        if apply:
            meta["run_status"] = "interrupted"
            meta["stop_reason"] = "killed"
            meta["error_class"] = None
            write_meta(path, meta)
        changed.append(row)
    return changed
