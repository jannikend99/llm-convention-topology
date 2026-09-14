from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import run_main
from convention_topology.health import (
    HEARTBEAT_STALE_S,
    format_health_text,
    read_health_snapshot,
    render_watch_layout,
    run_health_cli,
    verdict_exit_code,
)
from convention_topology.persistence import campaign_root


NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
FRESH = "2026-09-14T11:59:30Z"
FRESH_NEAR = "2026-09-14T11:59:00Z"
STALE = "2026-09-14T11:57:00Z"
OLD_HB = "2026-09-14T11:50:00Z"
REPO = Path(__file__).resolve().parent.parent


def _meta(root: Path, model: str, topology: str, run_id: str, payload: dict) -> Path:
    path = root / "runs" / model / topology / f"{run_id}.meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _heartbeat(root: Path, job_id: str, payload: dict) -> Path:
    path = root / "jobs" / f"{job_id}.live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _hb(
    *,
    model: str = "gemma4_31b",
    heartbeat_at: str = FRESH,
    tasks: list[str] | None = None,
    live_run_ids: list[str] | None = None,
    queued_run_ids: list[str] | None = None,
    live_runs: int | None = None,
    max_concurrent_runs: int = 16,
    in_flight_http: int = 0,
    started_at: str = "2026-09-14T11:00:00Z",
    slurm_timelimit: str | None = "1-00:00:00",
) -> dict:
    ids = list(live_run_ids or [])
    payload = {
        "model_shorthand": model,
        "heartbeat_at": heartbeat_at,
        "tasks": list(tasks if tasks is not None else ["emergence:mixing:0-10"]),
        "live_run_ids": ids,
        "queued_run_ids": list(queued_run_ids or []),
        "live_runs": live_runs if live_runs is not None else len(ids),
        "max_concurrent_runs": max_concurrent_runs,
        "in_flight_http": in_flight_http,
        "started_at": started_at,
    }
    if slurm_timelimit is not None:
        payload["slurm_timelimit"] = slurm_timelimit
    return payload


@pytest.fixture(autouse=True)
def freeze_health_now():
    with patch("convention_topology.health._wall_now", return_value=NOW):
        yield


@pytest.fixture
def campaign(tmp_path: Path) -> Path:
    return tmp_path


def test_counts_match_fixture_sidecars_and_heartbeat(campaign: Path):
    _heartbeat(campaign, "1001", _hb(live_run_ids=["live-a"], live_runs=1))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done-1",
        {
            "run_id": "done-1",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "cm_k": None,
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
            "t_gate": 40,
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done-2",
        {
            "run_id": "done-2",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "cm_k": None,
            "seed_index": 1,
            "run_status": "censored",
            "gate_passed": False,
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "live-a",
        {
            "run_id": "live-a",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "cm_k": None,
            "seed_index": 2,
            "run_status": "in_progress",
            "n_interactions": 12,
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "fail-old",
        {
            "run_id": "fail-old",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "cm_k": None,
            "seed_index": 9,
            "run_status": "failed",
            "error_class": "schema",
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.completed == 1
    assert snap.censored == 1
    assert snap.failed == 1
    assert snap.in_progress == 1
    assert snap.pending == 6
    assert snap.total == 10
    assert snap.live_runs == 1
    assert snap.max_concurrent_runs == 16
    assert snap.unreadable == 0
    assert snap.job_id == "1001"


def test_unknown_pending_and_total_without_heartbeat(campaign: Path):
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done-1",
        {
            "run_id": "done-1",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.heartbeat is None
    assert snap.pending is None
    assert snap.total is None
    text = format_health_text(snap)
    assert "pending unknown" in text
    assert "total unknown" in text
    assert "pending 0" not in text
    assert "total 0" not in text


def test_unreadable_sidecar_increments_unreadable_not_completed(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-2"], live_run_ids=[]))
    bad = campaign / "runs" / "gemma4_31b" / "mixing" / "broken.meta.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not-json", encoding="utf-8")
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "ok",
        {
            "run_id": "ok",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.unreadable == 1
    assert snap.completed == 1
    assert snap.gate_passed == 1


def test_model_shorthand_filter_excludes_other_model(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-1"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "keep",
        {
            "run_id": "keep",
            "model_shorthand": "gemma4_31b",
            "model_id": "google/gemma",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
        },
    )
    _meta(
        campaign,
        "olmo31_32b",
        "mixing",
        "drop",
        {
            "run_id": "drop",
            "model_shorthand": "olmo31_32b",
            "model_id": "google/gemma",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "wrong-field",
        {
            "run_id": "wrong-field",
            "model_shorthand": "olmo31_32b",
            "model_id": "google/gemma",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 1,
            "run_status": "failed",
        },
    )
    _heartbeat(campaign, "other", _hb(model="olmo31_32b", live_run_ids=["drop"]))
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.completed == 1
    assert snap.failed == 0
    assert snap.job_id == "1001"
    assert snap.overlapping_heartbeats is False
    assert {row["run_id"] for row in snap.sidecars} == {"keep"}


def test_overlap_within_120s_sets_flag_freshest_when_apart(campaign: Path):
    _heartbeat(campaign, "a", _hb(heartbeat_at=FRESH, live_run_ids=["x"]))
    _heartbeat(campaign, "b", _hb(heartbeat_at=FRESH_NEAR, live_run_ids=["y"]))
    overlap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert overlap.overlapping_heartbeats is True
    assert overlap.job_id in {"a", "b"}

    campaign2 = campaign / "apart"
    _heartbeat(campaign2, "old", _hb(heartbeat_at=OLD_HB, live_run_ids=["old"]))
    _heartbeat(campaign2, "new", _hb(heartbeat_at=FRESH, live_run_ids=["new"]))
    apart = read_health_snapshot(campaign2, "gemma4_31b", now=NOW)
    assert apart.overlapping_heartbeats is False
    assert apart.job_id == "new"
    assert apart.live_run_ids == ["new"]


def test_old_serve_startup_not_in_heartbeat_is_outside_window(campaign: Path):
    _heartbeat(campaign, "1001", _hb(live_run_ids=["live-a"], queued_run_ids=["q-1"]))
    for i in range(10):
        _meta(
            campaign,
            "gemma4_31b",
            "mixing",
            f"ok-{i}",
            {
                "run_id": f"ok-{i}",
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": "completed",
                "gate_passed": True,
                "t_gate": 8,
            },
        )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "old-serve",
        {
            "run_id": "old-serve",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 8,
            "run_status": "failed",
            "error_class": "serve_startup",
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "live-a",
        {
            "run_id": "live-a",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 2,
            "run_status": "in_progress",
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    old = next(row for row in snap.sidecars if row["run_id"] == "old-serve")
    live = next(row for row in snap.sidecars if row["run_id"] == "live-a")
    assert snap.in_verdict_window(old) is False
    assert snap.in_verdict_window(live) is True
    assert snap.verdict != "FAIL"


def test_does_not_open_events_or_pickle(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-1"]))
    events = campaign / "runs" / "gemma4_31b" / "mixing" / "x.events.jsonl"
    pkl = campaign / "runs" / "gemma4_31b" / "mixing" / "x.pkl"
    events.parent.mkdir(parents=True, exist_ok=True)
    events.write_text("this is not sidecar json\n", encoding="utf-8")
    pkl.write_bytes(b"pickle")
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "x",
        {
            "run_id": "x",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.completed == 1
    assert snap.unreadable == 0


def test_no_eligibility_and_no_invented_flip(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["cm:mixing:0-1:k=8"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "cm-1",
        {
            "run_id": "cm-1",
            "model_shorthand": "gemma4_31b",
            "program": "cm",
            "topology": "mixing",
            "cm_k": 8,
            "seed_index": 0,
            "run_status": "completed",
            "prepared_state_valid": True,
            "n_interactions": 20,
            "phase2_horizon": 100,
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.flip_true is None
    text = format_health_text(snap)
    assert "eligibility" not in text
    assert "flip" not in text
    layout = _export_layout(snap)
    assert "20/100" in layout


def test_stale_heartbeat_does_not_present_live_count(campaign: Path):
    _heartbeat(campaign, "1001", _hb(heartbeat_at=STALE, live_run_ids=["live-a"], live_runs=4))
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.heartbeat_stale is True
    assert snap.live_runs is None
    text = format_health_text(snap)
    assert "live stale" in text
    assert "live 4/" not in text


def test_health_ok_warn_fail_exit_codes(campaign: Path, capsys):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-3"], live_run_ids=["live-a"]))
    for i, status in enumerate(("completed", "completed", "in_progress")):
        rid = "live-a" if status == "in_progress" else f"c-{i}"
        _meta(
            campaign,
            "gemma4_31b",
            "mixing",
            rid,
            {
                "run_id": rid,
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": status,
                "gate_passed": True,
                "t_gate": 10,
            },
        )
    code = run_main.main(
        [
            "--campaign",
            "experiment",
            "--model",
            "gemma4_31b",
            "--health",
            "--artifact-root",
            str(campaign),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0] == "OK"
    assert verdict_exit_code("WARN") == 1
    assert verdict_exit_code("FAIL") == 2


def test_old_serve_startup_does_not_alone_force_fail(campaign: Path, capsys):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-12"], live_run_ids=[]))
    for i in range(10):
        _meta(
            campaign,
            "gemma4_31b",
            "mixing",
            f"ok-{i}",
            {
                "run_id": f"ok-{i}",
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": "completed",
                "gate_passed": True,
                "t_gate": 8,
            },
        )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "old-serve",
        {
            "run_id": "old-serve",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 11,
            "run_status": "failed",
            "error_class": "serve_startup",
        },
    )
    code = run_main.main(
        [
            "--campaign",
            "experiment",
            "--model",
            "gemma4_31b",
            "--health",
            "--artifact-root",
            str(campaign),
        ]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert out.splitlines()[0] == "WARN"
    assert code != 2


def test_overlapping_heartbeats_fail(campaign: Path, capsys):
    _heartbeat(campaign, "a", _hb(heartbeat_at=FRESH))
    _heartbeat(campaign, "b", _hb(heartbeat_at=FRESH_NEAR))
    code = run_main.main(
        [
            "--campaign",
            "experiment",
            "--model",
            "gemma4_31b",
            "--health",
            "--artifact-root",
            str(campaign),
        ]
    )
    assert code == 2
    assert capsys.readouterr().out.splitlines()[0] == "FAIL"


def test_infra_error_in_window_fails(campaign: Path):
    _heartbeat(campaign, "1001", _hb(live_run_ids=["live-a"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "live-a",
        {
            "run_id": "live-a",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "in_progress",
            "error_class": "serve_startup",
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.verdict == "FAIL"


def test_failed_share_and_gates_and_stall(campaign: Path):
    _heartbeat(
        campaign,
        "1001",
        _hb(tasks=["emergence:mixing:0-20"], live_run_ids=[], live_runs=0),
    )
    for i in range(8):
        _meta(
            campaign,
            "gemma4_31b",
            "mixing",
            f"e-{i}",
            {
                "run_id": f"e-{i}",
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": "completed",
                "gate_passed": i < 3,
                "t_gate": 5 if i < 3 else None,
            },
        )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.verdict == "WARN"
    assert snap.live_runs == 0
    assert snap.pending == 12

    share_root = campaign / "share"
    _heartbeat(share_root, "1001", _hb(tasks=["emergence:mixing:0-12"], live_run_ids=["z"]))
    for i in range(11):
        _meta(
            share_root,
            "gemma4_31b",
            "mixing",
            f"ok-{i}",
            {
                "run_id": f"ok-{i}",
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": "completed" if i < 10 else "failed",
                "gate_passed": True,
                "error_class": "timeout" if i == 10 else None,
            },
        )
    share = read_health_snapshot(share_root, "gemma4_31b", now=NOW)
    assert share.finished == 11
    assert share.failed == 1
    assert share.verdict == "WARN"

    fail_root = campaign / "failshare"
    _heartbeat(fail_root, "1001", _hb(tasks=["emergence:mixing:0-10"]))
    for i in range(10):
        _meta(
            fail_root,
            "gemma4_31b",
            "mixing",
            f"x-{i}",
            {
                "run_id": f"x-{i}",
                "model_shorthand": "gemma4_31b",
                "program": "emergence",
                "topology": "mixing",
                "seed_index": i,
                "run_status": "failed" if i < 2 else "completed",
                "gate_passed": True,
            },
        )
    fail_share = read_health_snapshot(fail_root, "gemma4_31b", now=NOW)
    assert fail_share.verdict == "FAIL"


def test_stale_while_in_progress_fail_ended_job_ok(campaign: Path):
    _heartbeat(campaign, "1001", _hb(heartbeat_at=STALE, live_run_ids=["live-a"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "live-a",
        {
            "run_id": "live-a",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "in_progress",
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.verdict == "FAIL"

    ended = campaign / "ended"
    _heartbeat(ended, "1001", _hb(heartbeat_at=STALE, tasks=["emergence:mixing:0-1"], live_run_ids=[]))
    _meta(
        ended,
        "gemma4_31b",
        "mixing",
        "done",
        {
            "run_id": "done",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
        },
    )
    ended_snap = read_health_snapshot(ended, "gemma4_31b", now=NOW)
    assert ended_snap.in_progress == 0
    assert ended_snap.verdict == "OK"


def test_prepared_state_invalid_on_finished_cm_fails(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["cm:mixing:0-1:k=8"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "cm-1",
        {
            "run_id": "cm-1",
            "model_shorthand": "gemma4_31b",
            "program": "cm",
            "topology": "mixing",
            "cm_k": 8,
            "seed_index": 0,
            "run_status": "completed",
            "prepared_state_valid": False,
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.verdict == "FAIL"


def test_missing_heartbeat_no_terminals_warn(campaign: Path):
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.verdict == "WARN"


def test_health_requires_campaign_and_model_and_exclusive_flags():
    with pytest.raises(SystemExit) as raised:
        run_main.main(["--health", "--model", "gemma4_31b"])
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(["--health", "--campaign", "experiment"])
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--health",
                "--task",
                "emergence:mixing:0-1",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--health",
                "--tech-check",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--health",
                "--watch",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--health",
                "--print-queue",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--watch",
                "--task",
                "emergence:mixing:0-1",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)
    with pytest.raises(SystemExit) as raised:
        run_main.main(
            [
                "--watch",
                "--tech-check",
                "--campaign",
                "experiment",
                "--model",
                "gemma4_31b",
            ]
        )
    assert raised.value.code not in (0, None)


def test_health_skips_clean_worktree_and_resolve_model(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-1"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done",
        {
            "run_id": "done",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
        },
    )
    with patch("run_main.require_clean_worktree", side_effect=RuntimeError("dirty")) as clean:
        with patch("run_main.resolve_model", side_effect=RuntimeError("resolve")) as resolve:
            with patch("run_main.load_config", side_effect=RuntimeError("config")):
                with patch("run_main.run_slice_async", side_effect=RuntimeError("slice")):
                    with patch("run_main.run_tech_check", side_effect=RuntimeError("tech")):
                        code = run_main.main(
                            [
                                "--campaign",
                                "experiment",
                                "--model",
                                "gemma4_31b",
                                "--health",
                                "--artifact-root",
                                str(campaign),
                            ]
                        )
    assert code == 0
    clean.assert_not_called()
    resolve.assert_not_called()


def test_watch_skips_clean_worktree(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-1"]))
    with patch("run_main.require_clean_worktree", side_effect=RuntimeError("dirty")) as clean:
        with patch("convention_topology.health._stdout_isatty", return_value=False):
            code = run_main.main(
                [
                    "--campaign",
                    "experiment",
                    "--model",
                    "gemma4_31b",
                    "--watch",
                    "--artifact-root",
                    str(campaign),
                ]
            )
    assert code in {0, 1, 2}
    clean.assert_not_called()


def test_health_without_task_is_valid(campaign: Path):
    code = run_main.main(
        [
            "--campaign",
            "experiment",
            "--model",
            "gemma4_31b",
            "--health",
            "--artifact-root",
            str(campaign),
        ]
    )
    assert code == 1


def test_campaign_root_matches_queue(tmp_path: Path):
    explicit = campaign_root(tmp_path, "experiment", REPO)
    assert explicit == tmp_path
    defaulted = campaign_root(None, "experiment", REPO)
    assert defaulted == REPO / "data" / "runs" / "experiment"


def test_watch_non_tty_equals_health(campaign: Path, capsys):
    _heartbeat(campaign, "1001", _hb(tasks=["emergence:mixing:0-1"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done",
        {
            "run_id": "done",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
        },
    )
    argv = [
        "--campaign",
        "experiment",
        "--model",
        "gemma4_31b",
        "--artifact-root",
        str(campaign),
    ]
    with patch("convention_topology.health._stdout_isatty", return_value=False):
        health_code = run_main.main([*argv, "--health"])
        health_out = capsys.readouterr().out
        watch_code = run_main.main([*argv, "--watch"])
        watch_out = capsys.readouterr().out
    assert health_code == watch_code
    assert health_out == watch_out
    with patch("convention_topology.health.Live") as live:
        with patch("convention_topology.health._stdout_isatty", return_value=False):
            run_main.main([*argv, "--watch"])
        live.assert_not_called()


def test_watch_tty_constructs_live(campaign: Path):
    _heartbeat(campaign, "1001", _hb())
    with patch("convention_topology.health._stdout_isatty", return_value=True):
        with patch("convention_topology.health.Live") as live_cls:
            with patch("convention_topology.health.time.sleep", side_effect=KeyboardInterrupt):
                live_cls.return_value.__enter__.return_value = MagicMock()
                live_cls.return_value.__exit__.return_value = False
                code = run_main.main(
                    [
                        "--campaign",
                        "experiment",
                        "--model",
                        "gemma4_31b",
                        "--watch",
                        "--artifact-root",
                        str(campaign),
                    ]
                )
    live_cls.assert_called()
    assert code in {0, 1, 2}


def test_watch_interrupt_writes_nothing(campaign: Path):
    hb = _heartbeat(campaign, "1001", _hb())
    meta = _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "done",
        {
            "run_id": "done",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "completed",
        },
    )
    hb_mtime = hb.stat().st_mtime_ns
    meta_mtime = meta.stat().st_mtime_ns
    with patch("convention_topology.health._stdout_isatty", return_value=True):
        with patch("convention_topology.health.Live") as live_cls:
            with patch("convention_topology.health.time.sleep", side_effect=KeyboardInterrupt):
                live_cls.return_value.__enter__.return_value = MagicMock()
                live_cls.return_value.__exit__.return_value = False
                run_main.main(
                    [
                        "--campaign",
                        "experiment",
                        "--model",
                        "gemma4_31b",
                        "--watch",
                        "--artifact-root",
                        str(campaign),
                    ]
                )
    assert hb.stat().st_mtime_ns == hb_mtime
    assert meta.stat().st_mtime_ns == meta_mtime
    assert list(campaign.rglob("*.fill.jsonl")) == []


def test_watch_header_elapsed_and_optional_wall(campaign: Path):
    _heartbeat(
        campaign,
        "4242",
        _hb(started_at="2026-09-14T11:00:00Z", slurm_timelimit="1-00:00:00", max_concurrent_runs=16),
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    text = _export_layout(snap)
    assert "01:00:00" in text
    assert "1-00:00:00" in text
    assert "16" in text

    no_wall = campaign / "nowall"
    _heartbeat(no_wall, "9", _hb(slurm_timelimit=None, max_concurrent_runs=48))
    text2 = _export_layout(read_health_snapshot(no_wall, "gemma4_31b", now=NOW))
    assert "1-00:00:00" not in text2
    assert "48" in text2


def test_health_source_has_no_eligibility():
    source = (REPO / "convention_topology" / "health.py").read_text(encoding="utf-8")
    assert "eligibility" not in source
    assert ".events.jsonl" not in source
    assert ".pkl" not in source


def test_slurm_has_no_health_watch_gpu_path():
    job = (REPO / "jobs" / "thesis_vllm.slurm").read_text(encoding="utf-8")
    assert "HAS_HEALTH" not in job
    assert "HAS_WATCH" not in job
    assert "--health" not in job
    assert "--watch" not in job
    assert "#SBATCH -t 1-00:00:00" in job
    assert "#SBATCH -t 1:00:00" not in job
    assert "submit requires --task or --tech-check" in job


def test_stale_constant_is_120():
    assert HEARTBEAT_STALE_S == 120


def test_boolean_flip_is_reported_when_present(campaign: Path):
    _heartbeat(campaign, "1001", _hb(tasks=["cm:mixing:0-1:k=8"]))
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "cm-1",
        {
            "run_id": "cm-1",
            "model_shorthand": "gemma4_31b",
            "program": "cm",
            "topology": "mixing",
            "cm_k": 8,
            "seed_index": 0,
            "run_status": "completed",
            "prepared_state_valid": True,
            "flip": True,
        },
    )
    snap = read_health_snapshot(campaign, "gemma4_31b", now=NOW)
    assert snap.flip_true == 1
    assert "flip" in format_health_text(snap)


def _export_layout(snap) -> str:
    from rich.console import Console

    console = Console(record=True, width=220, color_system=None)
    console.print(render_watch_layout(snap, now=NOW))
    return console.export_text()


def test_run_health_cli_prints_verdict_first(campaign: Path, capsys):
    code = run_health_cli(
        campaign_dir=campaign,
        model_shorthand="gemma4_31b",
        watch=False,
        now=NOW,
    )
    out = capsys.readouterr().out
    assert out.splitlines()[0] in {"OK", "WARN", "FAIL"}
    assert code == 1


def test_watch_progress_bars_study_kpis_and_live_fields(campaign: Path):
    _heartbeat(
        campaign,
        "1001",
        _hb(
            tasks=["emergence:mixing:0-1", "emergence:lattice:0-1", "cm:mixing:0-1:k=8"],
            live_run_ids=["live-mix"],
        ),
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "live-mix",
        {
            "run_id": "live-mix",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "mixing",
            "seed_index": 0,
            "run_status": "in_progress",
            "n_interactions": 508,
            "last_checkpoint_t": 500,
            "n_retries": 2,
            "error_class": "schema_retry",
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "lattice",
        "done-lat",
        {
            "run_id": "done-lat",
            "model_shorthand": "gemma4_31b",
            "program": "emergence",
            "topology": "lattice",
            "seed_index": 0,
            "run_status": "completed",
            "gate_passed": True,
            "t_gate": 1200,
        },
    )
    _meta(
        campaign,
        "gemma4_31b",
        "mixing",
        "cm-1",
        {
            "run_id": "cm-1",
            "model_shorthand": "gemma4_31b",
            "program": "cm",
            "topology": "mixing",
            "cm_k": 8,
            "seed_index": 0,
            "run_status": "completed",
            "prepared_state_valid": False,
            "n_interactions": 400,
            "phase2_horizon": 1000,
        },
    )
    snap = read_health_snapshot(
        campaign,
        "gemma4_31b",
        now=NOW,
        cap_phase1=5000,
        phase2_horizon=1000,
    )
    text = _export_layout(snap)
    assert "508/5000" in text
    assert "400/1000" in text
    assert "1200.0" in text
    live_block = text.split("Live cells")[-1]
    assert "508" in live_block
    assert "500" in live_block
    assert "live-mix" not in live_block
    s1 = text.split("Health (Study 1)")[1].split("Health (Study 2)")[0]
    assert "lattice" in s1
    assert "mixing" in s1
    s2 = text.split("Health (Study 2)")[1].split("Failures")[0]
    assert "400/1000" in s2
    source = (REPO / "convention_topology" / "health.py").read_text(encoding="utf-8")
    assert "last_checkpoint_t" in source
    assert "n_retries" in source
