from __future__ import annotations

from pathlib import Path

import pytest

from convention_topology.extend_bounds import ExtendBoundsError, extend_bounds
from convention_topology.persistence import empty_sidecar, read_meta, write_meta


def _meta(
    root: Path,
    *,
    program: str,
    status: str,
    stop_reason: str,
    n_interactions: int,
    cap: int | None = None,
    horizon: int | None = None,
    run_id: str = "r1",
    pickle: bool = True,
) -> Path:
    folder = root / "runs" / "gemma4_31b" / "mixing"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{run_id}.meta.json"
    row = empty_sidecar()
    row.update(
        {
            "run_id": run_id,
            "campaign": "experiment",
            "model_shorthand": "gemma4_31b",
            "program": program,
            "topology": "mixing",
            "seed_index": 1,
            "run_status": status,
            "stop_reason": stop_reason,
            "n_interactions": n_interactions,
            "cap_phase1": cap,
            "phase2_horizon": horizon,
        }
    )
    write_meta(path, row)
    if pickle:
        (folder / f"{run_id}.pkl").write_bytes(b"pickle")
    return path


def test_gated_study1_is_not_reopened(tmp_path: Path):
    _meta(tmp_path, program="emergence", status="completed", stop_reason="gate", n_interactions=200, cap=1500)
    rows = extend_bounds(tmp_path, "gemma4_31b", cap_phase1=3000, phase2_horizon=1500, apply=True)
    assert rows == []


def test_study2_horizon_reopens(tmp_path: Path):
    path = _meta(tmp_path, program="cm", status="completed", stop_reason="horizon", n_interactions=1500, horizon=1500)
    rows = extend_bounds(tmp_path, "gemma4_31b", cap_phase1=1500, phase2_horizon=1800, apply=True)
    assert len(rows) == 1
    meta = read_meta(path)
    assert meta["run_status"] == "in_progress"
    assert meta["stop_reason"] is None
    assert meta["phase2_horizon"] == 1800
    assert meta["bound_extensions"][0]["t"] == 1500


def test_lower_bound_refuses_apply(tmp_path: Path):
    path = _meta(tmp_path, program="cm", status="completed", stop_reason="horizon", n_interactions=1500, horizon=1500)
    with pytest.raises(ExtendBoundsError):
        extend_bounds(tmp_path, "gemma4_31b", cap_phase1=1500, phase2_horizon=1000, apply=True)
    assert read_meta(path)["run_status"] == "completed"
