"""Rebuild interaction trackers from the JSONL stream and refuse pickle mismatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from convention_topology.persistence import PersistenceError, load_run_pickle, read_events
from convention_topology.tracker import empty_tracker, unique_modal

TERMINAL_STATUSES = frozenset({"completed", "censored"})


class AnalysisMismatchError(ValueError):
    """Pickle and interaction stream disagree, or a terminal run is missing an artifact."""


def artifact_paths(meta_path: Path) -> tuple[Path, Path]:
    name = meta_path.name
    if not name.endswith(".meta.json"):
        raise AnalysisMismatchError(f"sidecar path is not *.meta.json: {meta_path}")
    stem = name[: -len(".meta.json")]
    return meta_path.with_name(stem + ".pkl"), meta_path.with_name(stem + ".events.jsonl")


def interactions_from_events(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in records if row.get("record_type") == "interaction"]


def tracker_from_interactions(interactions: Sequence[Mapping[str, Any]]) -> dict[str, list[Any]]:
    tracker = empty_tracker()
    for row in interactions:
        tracker["players"].append([row.get("p1"), row.get("p2")])
        tracker["answers"].append([row["label_p1"], row["label_p2"]])
        tracker["outcome"].append(int(row["success"]))
    return tracker


def prepared_state_from_events(records: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for row in records:
        if row.get("record_type") == "prepared_state":
            return dict(row)
    return None


def window_winner(tracker: Mapping[str, Sequence], window: int) -> str | None:
    answers = tracker["answers"]
    if len(answers) < window:
        return None
    labels = [label for pair in answers[-window:] for label in pair]
    return unique_modal(labels)


def _series_equal(pickle_pairs: Sequence[Any], stream_pairs: Sequence[Any]) -> bool:
    if len(pickle_pairs) != len(stream_pairs):
        return False
    return list(pickle_pairs) == list(stream_pairs)


def refuse_pickle_jsonl_mismatch(
    *,
    meta: Mapping[str, Any],
    meta_path: Path,
    pickle_path: Path,
    events_path: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, list[Any]]]:
    """Return (pickle payload or None, interaction rows, stream tracker).

    Pickle may be None for non-terminal runs that have a stream only.
    """
    status = meta.get("run_status")
    pickle_exists = pickle_path.exists()
    events_exist = events_path.exists()
    if status in TERMINAL_STATUSES:
        if not pickle_exists or not events_exist:
            raise AnalysisMismatchError(
                f"terminal run {meta.get('run_id')} missing pickle or JSONL at {meta_path}"
            )

    records = read_events(events_path) if events_exist else []
    interactions = interactions_from_events(records)
    stream_tracker = tracker_from_interactions(interactions)

    payload: dict[str, Any] | None = None
    if pickle_exists:
        try:
            payload = load_run_pickle(pickle_path)
        except PersistenceError as exc:
            if status in TERMINAL_STATUSES:
                raise AnalysisMismatchError(str(exc)) from exc
            payload = None

    if payload is not None:
        tracker = payload["tracker"]
        pickle_n = len(tracker.get("outcome") or [])
        stream_n = len(interactions)
        if pickle_n != stream_n:
            raise AnalysisMismatchError(
                f"pickle interaction count {pickle_n} != JSONL interaction count {stream_n} "
                f"for {meta.get('run_id')}"
            )
        if not _series_equal(tracker.get("answers") or [], stream_tracker["answers"]):
            raise AnalysisMismatchError(f"pickle answers disagree with stream for {meta.get('run_id')}")
        if not _series_equal(tracker.get("outcome") or [], stream_tracker["outcome"]):
            raise AnalysisMismatchError(f"pickle outcome disagrees with stream for {meta.get('run_id')}")

    return payload, interactions, stream_tracker
