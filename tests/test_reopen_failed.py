from __future__ import annotations

from pathlib import Path

import pytest

import run_main
from convention_topology.persistence import empty_sidecar, write_meta
from convention_topology.reopen_failed import ReopenFailedError, reopen_failed


def _meta(root: Path, *, status: str, error: str | None, run_id: str = "r1", pickle: bool = True) -> Path:
    folder = root / "runs" / "gemma4_31b" / "mixing"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{run_id}.meta.json"
    row = empty_sidecar()
    row.update(
        {
            "run_id": run_id,
            "campaign": "pilot-run-n48-cap1500",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 3,
            "run_status": status,
            "error_class": error,
            "last_checkpoint_t": 40,
            "stop_reason": "failed",
        }
    )
    write_meta(path, row)
    if pickle:
        (folder / f"{run_id}.pkl").write_bytes(b"pickle")
    return path


def test_reopen_dry_run_leaves_failed(tmp_path: Path):
    path = _meta(tmp_path, status="failed", error="attempts_exhausted")
    rows = reopen_failed(
        tmp_path, "gemma4_31b", campaign="pilot-run-n48-cap1500", apply=False
    )
    assert len(rows) == 1
    assert rows[0]["skipped"] is None
    from convention_topology.persistence import read_meta

    assert read_meta(path)["run_status"] == "failed"


def test_reopen_apply_sets_interrupted(tmp_path: Path):
    path = _meta(tmp_path, status="failed", error="attempts_exhausted")
    rows = reopen_failed(
        tmp_path, "gemma4_31b", campaign="pilot-run-n48-cap1500", apply=True
    )
    from convention_topology.persistence import read_meta

    meta = read_meta(path)
    assert len(rows) == 1
    assert meta["run_status"] == "interrupted"
    assert meta["error_class"] is None
    assert meta["stop_reason"] == "killed"


def test_reopen_skips_other_errors_and_experiment():
    with pytest.raises(ReopenFailedError):
        reopen_failed(Path("/tmp"), "gemma4_31b", campaign="experiment", apply=True)


def test_reopen_skips_missing_pickle(tmp_path: Path):
    _meta(tmp_path, status="failed", error="attempts_exhausted", pickle=False)
    rows = reopen_failed(
        tmp_path, "gemma4_31b", campaign="pilot-run-n48-cap1500", apply=True
    )
    assert rows[0]["skipped"] == "missing_pickle"


def test_cli_reopen_refuses_experiment(tmp_path: Path):
    code = run_main.main(
        [
            "--reopen-failed",
            "--apply",
            "--campaign",
            "experiment",
            "--model",
            "gemma4_31b",
            "--artifact-root",
            str(tmp_path),
        ]
    )
    assert code == 2


def test_cli_reopen_exclusive_with_task():
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--reopen-failed",
                "--campaign",
                "pilot-run-n48-cap1500",
                "--model",
                "gemma4_31b",
                "--task",
                "emergence:mixing:0-1",
            ]
        )
    assert raised.value.code not in (0, None)
