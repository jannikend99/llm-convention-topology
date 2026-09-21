"""Shared run-table loader and gate/critical-mass helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from convention_topology.analysis.stream import (
    AnalysisMismatchError,
    artifact_paths,
    prepared_state_from_events,
    refuse_pickle_jsonl_mismatch,
    window_winner,
)
from convention_topology.dvs import DEFAULT_WINDOW, dominant_share, flip, flip_50, shannon_entropy, time_to_flip
from convention_topology.gate import first_gate_time
from convention_topology.persistence import PersistenceError, read_events, read_meta

META_COLUMNS = [
    "run_id",
    "program",
    "init_mode",
    "topology",
    "cm_k",
    "model_shorthand",
    "model_id",
    "run_status",
    "gate_passed",
    "prepared_state_valid",
    "t_gate",
    "incumbent_label",
    "committed_to",
]

ALLOWED_TOPOLOGIES = frozenset(
    {"mixing", "random_regular", "lattice", "watts_strogatz", "barabasi_albert"}
)
# Run-level API/decision failures for D1. Exclude infrastructure (`config`, `serve_startup`,
# `persistence`). Include exhausted decision budget and parse/HTTP classes if stored on the sidecar.
API_FAILED_ERROR_CLASSES = frozenset(
    {"attempts_exhausted", "schema", "http", "invalid_json", "truncated", "timeout"}
)
def scan_meta_paths(data_dir: Path) -> list[Path]:
    runs_root = Path(data_dir) / "runs"
    if not runs_root.exists():
        return []
    return sorted(runs_root.glob("**/*.meta.json"))


def _window(meta: dict[str, Any]) -> int:
    return int(meta.get("gate_window") or DEFAULT_WINDOW)


def _committed_id_set(
    simulation: Mapping[Any, Mapping[str, Any]] | None,
    prepared_event: Mapping[str, Any] | None,
    committed_ids: Sequence[Any] | None,
) -> list[Any]:
    if committed_ids:
        return list(committed_ids)
    if prepared_event is not None and prepared_event.get("committed_ids"):
        return list(prepared_event["committed_ids"])
    if simulation:
        return [nid for nid, player in simulation.items() if player.get("committed_tag")]
    return []


def prepared_memory_policy_shares(
    *,
    simulation: Mapping[Any, Mapping[str, Any]] | None,
    prepared_event: Mapping[str, Any] | None,
    incumbent_label: str | None,
    committed_ids: Sequence[Any] | None,
    memory_size: int | None,
    n: int | None,
) -> tuple[float, float]:
    """Rebuild t=0 memory incumbent share and committed-policy share from inventories.

    Uses pickle `my_history` prefixes (append-only t=0 inventories) when present.
    Falls back to stream `prepared_state.memory_labels` + `committed_ids` if those
    arrays already exist. Does not copy hardcoded prepared_state scalars.
    """
    if n is None or int(n) <= 0:
        raise ValueError("D5 cannot reconstruct shares: N is missing")
    if not incumbent_label:
        raise ValueError("D5 cannot reconstruct shares: incumbent_label is missing")
    committed = _committed_id_set(simulation, prepared_event, committed_ids)
    if not committed:
        raise ValueError("D5 cannot reconstruct shares: committed_ids are missing")

    memory_slots: list[Any] = []
    h = int(memory_size) if memory_size is not None else None
    if simulation:
        for nid, player in simulation.items():
            if player.get("committed_tag") or nid in committed:
                continue
            history = list(player.get("my_history") or [])
            if h is None or len(history) < h:
                memory_slots = []
                break
            memory_slots.extend(history[:h])

    if not memory_slots and prepared_event is not None:
        labels = prepared_event.get("memory_labels")
        if isinstance(labels, list) and labels:
            committed_set = set(committed)
            memory_slots = [
                lab
                for idx, lab in enumerate(labels)
                if idx not in committed_set and lab is not None
            ]

    if not memory_slots:
        raise ValueError(
            "D5 cannot reconstruct shares: pickle lacks t=0 inventories and "
            "prepared_state has no memory_labels array"
        )
    memory_share = float(sum(1 for lab in memory_slots if lab == incumbent_label) / len(memory_slots))
    policy_share = float(len(committed) / int(n))
    return memory_share, policy_share


def _run_dvs(meta: dict[str, Any], meta_path: Path) -> dict[str, Any]:
    empty = {
        "dominant_share": None,
        "shannon_entropy": None,
        "flip": None,
        "flip_50": None,
        "time_to_flip": None,
        "events_path": None,
        "memory_incumbent_share": None,
        "committed_policy_share": None,
        "stream_winner": None,
        "t_gate_sidecar": meta.get("t_gate"),
    }
    pickle_path, events_path = artifact_paths(meta_path)
    empty["events_path"] = str(events_path)
    payload, _interactions, stream_tracker = refuse_pickle_jsonl_mismatch(
        meta=meta,
        meta_path=meta_path,
        pickle_path=pickle_path,
        events_path=events_path,
    )
    records = read_events(events_path) if events_path.exists() else []
    prepared = prepared_state_from_events(records)
    if meta.get("program") == "cm":
        try:
            mem_share, pol_share = prepared_memory_policy_shares(
                simulation=(payload or {}).get("simulation") if payload else None,
                prepared_event=prepared,
                incumbent_label=meta.get("incumbent_label"),
                committed_ids=meta.get("committed_ids"),
                memory_size=int(meta["H"]) if meta.get("H") is not None else None,
                n=int(meta["N"]) if meta.get("N") is not None else None,
            )
            empty["memory_incumbent_share"] = mem_share
            empty["committed_policy_share"] = pol_share
        except ValueError:
            empty["memory_incumbent_share"] = None
            empty["committed_policy_share"] = None

    if meta["run_status"] not in ("completed", "censored"):
        return empty

    result = dict(empty)
    program = meta.get("program")
    window = _window(meta)

    if program == "emergence":
        outcomes = stream_tracker["outcome"]
        rebuilt_t_gate = first_gate_time(outcomes, window=window)
        rebuilt_passed = rebuilt_t_gate is not None
        sidecar_t = meta.get("t_gate")
        sidecar_passed = meta.get("gate_passed")
        if sidecar_t is not None and sidecar_t != rebuilt_t_gate:
            raise AnalysisMismatchError(
                f"sidecar t_gate {sidecar_t} != stream t_gate {rebuilt_t_gate} for {meta.get('run_id')}"
            )
        if sidecar_passed is not None and bool(sidecar_passed) != rebuilt_passed:
            raise AnalysisMismatchError(
                f"sidecar gate_passed {sidecar_passed} != stream gate {rebuilt_passed} for {meta.get('run_id')}"
            )
        result["t_gate"] = rebuilt_t_gate
        result["gate_passed"] = rebuilt_passed
        phase_answers = stream_tracker["answers"][:rebuilt_t_gate] if rebuilt_t_gate is not None else stream_tracker["answers"]
        phase_tracker = {"answers": phase_answers, "outcome": stream_tracker["outcome"][: len(phase_answers)]}
        if len(phase_tracker["answers"]) >= window:
            result["dominant_share"] = dominant_share(phase_tracker, window=window)
            result["shannon_entropy"] = shannon_entropy(phase_tracker, window=window)
            result["stream_winner"] = window_winner(phase_tracker, window)

    if program == "cm" and meta["run_status"] in ("completed", "censored"):
        n_interactions = len(stream_tracker["outcome"])
        if n_interactions < window:
            raise AnalysisMismatchError(
                f"Study 2 terminal run {meta.get('run_id')} has {n_interactions} interactions, "
                f"need >= {window} to evaluate flip"
            )
        if meta.get("committed_to") is not None:
            t_start = meta.get("t_cm_start")
            if t_start is None:
                t_start = 0
            try:
                result["flip"] = flip(stream_tracker, meta["committed_to"], t_start, window=window)
                horizon = meta.get("phase2_horizon")
                censor = int(horizon) if isinstance(horizon, int) and horizon > 0 else None
                if censor is None:
                    result["time_to_flip"] = time_to_flip(
                        stream_tracker, meta["committed_to"], t_start, window=window
                    )
                else:
                    result["time_to_flip"] = time_to_flip(
                        stream_tracker,
                        meta["committed_to"],
                        t_start,
                        window=window,
                        censor_value=censor,
                    )
            except ValueError as exc:
                raise AnalysisMismatchError(
                    f"Study 2 terminal run {meta.get('run_id')} cannot rebuild flip: {exc}"
                ) from exc
            if payload is not None:
                try:
                    result["flip_50"] = flip_50(payload["simulation"], meta["committed_to"], window=window)
                except (KeyError, TypeError, ZeroDivisionError, ValueError):
                    result["flip_50"] = None

    return result


def load_run_table(data_dir: Path, model_filter: str | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for meta_path in scan_meta_paths(data_dir):
        try:
            meta = read_meta(meta_path)
        except PersistenceError:
            continue
        topology = meta.get("topology")
        if topology is not None and topology not in ALLOWED_TOPOLOGIES:
            raise ValueError(f"analysis refuses unknown topology ids: {sorted({topology})}")
        if model_filter and meta.get("model_shorthand") != model_filter:
            continue
        row = dict(meta)
        row.update(_run_dvs(meta, meta_path))
        rows.append(row)

    extra = [
        "dominant_share",
        "shannon_entropy",
        "flip",
        "flip_50",
        "time_to_flip",
        "events_path",
        "memory_incumbent_share",
        "committed_policy_share",
        "stream_winner",
        "t_gate_sidecar",
    ]
    if not rows:
        return pd.DataFrame(columns=META_COLUMNS + extra)
    table = pd.DataFrame(rows)
    if "topology" in table.columns:
        unknown = set(table["topology"].dropna().unique()) - ALLOWED_TOPOLOGIES
        if unknown:
            raise ValueError(f"analysis refuses unknown topology ids: {sorted(unknown)}")
    if "gate_window" in table.columns:
        windows = {int(x) for x in table["gate_window"].dropna().unique()}
        if len(windows) > 1:
            raise ValueError(f"analysis refuses mixed gate_window values: {sorted(windows)}")
    return table


def d1_funnel(runs_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "topology",
        "model_shorthand",
        "attempted",
        "api_failed",
        "completed",
        "study1_gate_passed",
        "study2_prepared_state_valid",
    ]
    if runs_df.empty:
        return pd.DataFrame(columns=columns)

    def _agg(group: pd.DataFrame) -> pd.Series:
        if "error_class" in group.columns:
            api_failed = group["error_class"].isin(API_FAILED_ERROR_CLASSES)
        else:
            api_failed = pd.Series(False, index=group.index)
        emergence = group["program"] == "emergence"
        cm = group["program"] == "cm"
        return pd.Series(
            {
                "attempted": len(group),
                "api_failed": int(api_failed.sum()),
                "completed": int((group["run_status"] == "completed").sum()),
                "study1_gate_passed": int(((emergence) & (group["gate_passed"] == True)).sum()),  # noqa: E712
                "study2_prepared_state_valid": int(
                    ((cm) & (group["prepared_state_valid"] == True)).sum()  # noqa: E712
                ),
            }
        )

    grouped = runs_df.groupby(["topology", "model_shorthand"], dropna=False).apply(
        _agg, include_groups=False
    ).reset_index()
    return grouped[columns]


def d5_prepared(runs_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "run_id",
        "topology",
        "model_shorthand",
        "cm_k",
        "N",
        "memory_incumbent_share",
        "committed_policy_share",
        "prepared_state_valid",
    ]
    cm = runs_df[runs_df["program"] == "cm"] if not runs_df.empty else runs_df
    if cm.empty:
        return pd.DataFrame(columns=columns)
    missing = cm[
        cm["memory_incumbent_share"].isna() | cm["committed_policy_share"].isna()
    ] if {"memory_incumbent_share", "committed_policy_share"} <= set(cm.columns) else cm
    if not missing.empty:
        run_ids = missing["run_id"].tolist() if "run_id" in missing.columns else ["<unknown>"]
        raise ValueError(
            "D5 cannot plot prepared consensus: pickle lacks t=0 inventories "
            f"(and stream prepared_state has no memory/committed arrays) for runs {run_ids}"
        )
    keep = [c for c in columns if c in cm.columns]
    out = cm[keep].copy()
    for col in columns:
        if col not in out.columns:
            out[col] = None
    return out[columns]


def critical_mass(runs_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["topology", "model_shorthand", "critical_mass"]
    cm = runs_df[runs_df["program"] == "cm"]
    valid = cm[(cm["prepared_state_valid"] == True) & cm["flip"].notna()]  # noqa: E712
    if valid.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for (topology, model), group in valid.groupby(["topology", "model_shorthand"]):
        flip_rates = group.groupby("cm_k")["flip"].mean().sort_index()
        mass = next((k for k, rate in flip_rates.items() if rate >= 0.5), None)
        rows.append({"topology": topology, "model_shorthand": model, "critical_mass": mass})
    return pd.DataFrame(rows, columns=columns)


def prepared_valid_cm(runs_df: pd.DataFrame) -> pd.DataFrame:
    cm = runs_df[runs_df["program"] == "cm"] if not runs_df.empty and "program" in runs_df.columns else runs_df.iloc[0:0]
    if cm.empty:
        return cm
    return cm[cm["prepared_state_valid"] == True]  # noqa: E712
