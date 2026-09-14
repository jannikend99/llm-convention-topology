"""Read-only campaign health snapshot from sidecars and heartbeat files."""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, TextIO

from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from convention_topology.orchestration import TaskSpecError, flatten_tasks, parse_task


HEARTBEAT_STALE_S = 120
WATCH_REFRESH_S = 1.5
_INFRA_FAIL = frozenset({"serve_startup", "persistence", "config"})
_TERMINAL = frozenset({"completed", "censored", "failed"})
_OCCUPIED = frozenset({"completed", "censored", "failed", "in_progress", "interrupted"})
_STAMP = "%Y-%m-%dT%H:%M:%SZ"


def _stdout_isatty() -> bool:
    return sys.stdout.isatty()


def _wall_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_stamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.strptime(raw, _STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _cell_key(row: Mapping[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (row.get("program"), row.get("topology"), row.get("cm_k"), row.get("seed_index"))


def _is_true(value: Any) -> bool:
    return value is True


def _format_unknown(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def _elapsed_label(started_at: str | None, now: datetime) -> str | None:
    start = _parse_stamp(started_at)
    if start is None:
        return None
    seconds = max(0, int((now - start).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class HealthSnapshot:
    model_shorthand: str
    campaign_label: str
    overlapping_heartbeats: bool = False
    heartbeat: dict[str, Any] | None = None
    heartbeat_stale: bool = False
    job_id: str | None = None
    live_runs: int | None = None
    max_concurrent_runs: int | None = None
    in_flight_http: int | None = None
    live_run_ids: list[str] = field(default_factory=list)
    queued_run_ids: list[str] = field(default_factory=list)
    started_at: str | None = None
    slurm_timelimit: str | None = None
    pending: int | None = None
    total: int | None = None
    completed: int = 0
    censored: int = 0
    failed: int = 0
    interrupted: int = 0
    in_progress: int = 0
    unreadable: int = 0
    error_class_counts: Counter[str] = field(default_factory=Counter)
    emergence_finished: int = 0
    gate_passed: int = 0
    median_t_gate: float | None = None
    prepared_state_invalid: int = 0
    flip_true: int | None = None
    sidecars: list[dict[str, Any]] = field(default_factory=list)
    recent_failures: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "OK"

    @property
    def finished(self) -> int:
        return self.completed + self.censored + self.failed

    def in_verdict_window(self, sidecar: Mapping[str, Any]) -> bool:
        run_id = sidecar.get("run_id")
        if isinstance(run_id, str) and run_id and (
            run_id in self.live_run_ids or run_id in self.queued_run_ids
        ):
            return True
        return sidecar.get("run_status") in {"in_progress", "interrupted"}


def _select_heartbeat(
    campaign_dir: Path, model_shorthand: str
) -> tuple[dict[str, Any] | None, str | None, bool]:
    matches: list[tuple[datetime, Path, dict[str, Any]]] = []
    jobs_dir = Path(campaign_dir) / "jobs"
    if jobs_dir.is_dir():
        for path in jobs_dir.glob("*.live.json"):
            payload = _read_json_object(path)
            if payload is None:
                continue
            if payload.get("model_shorthand") != model_shorthand:
                continue
            stamped = _parse_stamp(payload.get("heartbeat_at"))
            if stamped is None:
                continue
            matches.append((stamped, path, payload))
    overlapping = False
    if len(matches) >= 2:
        times = [item[0] for item in matches]
        for i, left in enumerate(times):
            for right in times[i + 1 :]:
                if abs((left - right).total_seconds()) <= HEARTBEAT_STALE_S:
                    overlapping = True
                    break
            if overlapping:
                break
    if not matches:
        return None, None, overlapping
    matches.sort(key=lambda item: item[0], reverse=True)
    _stamped, path, payload = matches[0]
    job_id = path.name[: -len(".live.json")] if path.name.endswith(".live.json") else path.stem
    return payload, job_id, overlapping


def _queue_cells(tasks: Any) -> list[dict[str, Any]] | None:
    if not isinstance(tasks, list):
        return None
    parsed = []
    try:
        for spec in tasks:
            if not isinstance(spec, str):
                return None
            parsed.append(parse_task(spec))
        return flatten_tasks(parsed)
    except TaskSpecError:
        return None


def _assign_verdict(snap: HealthSnapshot) -> None:
    failed_share: float | None = None
    if snap.finished > 0:
        failed_share = snap.failed / snap.finished
    infra_fail = False
    for row in snap.sidecars:
        if row.get("error_class") in _INFRA_FAIL and snap.in_verdict_window(row):
            infra_fail = True
            break
    if snap.overlapping_heartbeats:
        snap.verdict = "FAIL"
        return
    if infra_fail:
        snap.verdict = "FAIL"
        return
    if failed_share is not None and failed_share >= 0.10:
        snap.verdict = "FAIL"
        return
    if snap.heartbeat is not None and snap.heartbeat_stale and snap.in_progress > 0:
        snap.verdict = "FAIL"
        return
    if snap.prepared_state_invalid > 0:
        snap.verdict = "FAIL"
        return
    if snap.heartbeat is None and snap.finished == 0:
        snap.verdict = "WARN"
        return
    if failed_share is not None and 0 < failed_share < 0.10:
        snap.verdict = "WARN"
        return
    if snap.emergence_finished >= 8 and (snap.gate_passed / snap.emergence_finished) < 0.50:
        snap.verdict = "WARN"
        return
    if (
        snap.heartbeat is not None
        and not snap.heartbeat_stale
        and snap.live_runs == 0
        and snap.pending is not None
        and snap.pending > 0
    ):
        snap.verdict = "WARN"
        return
    snap.verdict = "OK"


def read_health_snapshot(
    campaign_dir: Path,
    model_shorthand: str,
    now: datetime | None = None,
) -> HealthSnapshot:
    when = now or _wall_now()
    root = Path(campaign_dir)
    heartbeat, job_id, overlapping = _select_heartbeat(root, model_shorthand)
    snap = HealthSnapshot(
        model_shorthand=model_shorthand,
        campaign_label=root.name,
        overlapping_heartbeats=overlapping,
        heartbeat=heartbeat,
        job_id=job_id,
    )
    if heartbeat is not None:
        stamped = _parse_stamp(heartbeat.get("heartbeat_at"))
        snap.heartbeat_stale = stamped is None or (when - stamped).total_seconds() > HEARTBEAT_STALE_S
        live_ids = heartbeat.get("live_run_ids") or []
        queued_ids = heartbeat.get("queued_run_ids") or []
        snap.live_run_ids = [str(item) for item in live_ids] if isinstance(live_ids, list) else []
        snap.queued_run_ids = [str(item) for item in queued_ids] if isinstance(queued_ids, list) else []
        snap.started_at = heartbeat.get("started_at") if isinstance(heartbeat.get("started_at"), str) else None
        if "slurm_timelimit" in heartbeat and heartbeat["slurm_timelimit"] is not None:
            snap.slurm_timelimit = str(heartbeat["slurm_timelimit"])
        max_conc = heartbeat.get("max_concurrent_runs")
        snap.max_concurrent_runs = int(max_conc) if isinstance(max_conc, int) else None
        in_flight = heartbeat.get("in_flight_http")
        snap.in_flight_http = int(in_flight) if isinstance(in_flight, int) else None
        if not snap.heartbeat_stale:
            live = heartbeat.get("live_runs")
            snap.live_runs = int(live) if isinstance(live, int) else len(snap.live_run_ids)
        cells = _queue_cells(heartbeat.get("tasks"))
        if cells is not None:
            snap.total = len(cells)

    sidecars: list[dict[str, Any]] = []
    unreadable = 0
    runs_root = root / "runs"
    if runs_root.is_dir():
        for path in runs_root.rglob("*.meta.json"):
            payload = _read_json_object(path)
            if payload is None:
                unreadable += 1
                continue
            if payload.get("model_shorthand") != model_shorthand:
                continue
            row = dict(payload)
            row["_path"] = str(path)
            row["_mtime"] = path.stat().st_mtime
            sidecars.append(row)
    snap.unreadable = unreadable
    snap.sidecars = sidecars

    flip_seen = False
    flip_true = 0
    t_gates: list[float] = []
    for row in sidecars:
        status = row.get("run_status")
        if status == "completed":
            snap.completed += 1
        elif status == "censored":
            snap.censored += 1
        elif status == "failed":
            snap.failed += 1
        elif status == "interrupted":
            snap.interrupted += 1
        elif status == "in_progress":
            snap.in_progress += 1
        err = row.get("error_class")
        if isinstance(err, str) and err:
            snap.error_class_counts[err] += 1
        if row.get("program") == "emergence" and status in _TERMINAL:
            snap.emergence_finished += 1
            if _is_true(row.get("gate_passed")):
                snap.gate_passed += 1
                t_gate = row.get("t_gate")
                if isinstance(t_gate, (int, float)):
                    t_gates.append(float(t_gate))
        if row.get("program") == "cm" and status in _TERMINAL:
            if row.get("prepared_state_valid") is False:
                snap.prepared_state_invalid += 1
        if isinstance(row.get("flip"), bool):
            flip_seen = True
            if row["flip"]:
                flip_true += 1
    if t_gates:
        snap.median_t_gate = float(statistics.median(t_gates))
    if flip_seen:
        snap.flip_true = flip_true

    failures = [
        row
        for row in sidecars
        if isinstance(row.get("error_class"), str) and row.get("error_class")
    ]

    def _fail_sort(row: dict[str, Any]) -> tuple[float, float]:
        finished = _parse_stamp(row.get("finished_at"))
        stamp = finished.timestamp() if finished is not None else 0.0
        return (stamp, float(row.get("_mtime") or 0.0))

    failures.sort(key=_fail_sort, reverse=True)
    snap.recent_failures = failures[:5]

    if heartbeat is not None and snap.total is not None:
        cells = _queue_cells(heartbeat.get("tasks")) or []
        occupied: set[tuple[Any, Any, Any, Any]] = set()
        by_cell = {_cell_key(row): row for row in sidecars}
        pending = 0
        for cell in cells:
            key = _cell_key(cell)
            sidecar = by_cell.get(key)
            if sidecar is None or sidecar.get("run_status") not in _OCCUPIED:
                pending += 1
            occupied.add(key)
        snap.pending = pending
    if heartbeat is None:
        snap.live_runs = snap.in_progress
        snap.max_concurrent_runs = None

    _assign_verdict(snap)
    return snap


def verdict_exit_code(verdict: str) -> int:
    if verdict == "OK":
        return 0
    if verdict == "WARN":
        return 1
    return 2


def format_health_text(snap: HealthSnapshot) -> str:
    if snap.heartbeat is None:
        live = f"live {snap.in_progress}"
    elif snap.heartbeat_stale:
        live = "live stale"
    elif snap.max_concurrent_runs is None:
        live = f"live {_format_unknown(snap.live_runs)}"
    else:
        live = f"live {snap.live_runs}/{snap.max_concurrent_runs}"
    median = "unknown" if snap.median_t_gate is None else str(snap.median_t_gate)
    errors = ", ".join(
        f"{name}={count}" for name, count in snap.error_class_counts.most_common()
    ) or "none"
    flip_line = ""
    if snap.flip_true is not None:
        flip_line = f"\nflip {snap.flip_true}"
    return (
        f"{snap.verdict}\n"
        f"{live}  pending {_format_unknown(snap.pending)}  total {_format_unknown(snap.total)}  "
        f"completed {snap.completed}  censored {snap.censored}  failed {snap.failed}  "
        f"interrupted {snap.interrupted}\n"
        f"emergence gate_passed {snap.gate_passed}/{snap.emergence_finished}  median_t_gate {median}\n"
        f"error_class {errors}\n"
        f"unreadable {snap.unreadable}"
        f"{flip_line}"
    )


def render_watch_layout(snap: HealthSnapshot, now: datetime | None = None) -> RenderableType:
    when = now or _wall_now()
    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()
    elapsed = _elapsed_label(snap.started_at, when)
    fill = (
        "stale"
        if snap.heartbeat_stale
        else (
            f"{_format_unknown(snap.live_runs)}/{_format_unknown(snap.max_concurrent_runs)}"
            if snap.heartbeat is not None
            else str(snap.in_progress)
        )
    )
    header_bits = [
        f"campaign {snap.campaign_label}",
        f"model {snap.model_shorthand}",
        f"job {snap.job_id or 'none'}",
        f"verdict {snap.verdict}",
    ]
    if elapsed is not None:
        header_bits.append(f"elapsed {elapsed}")
    if snap.slurm_timelimit:
        header_bits.append(f"wall {snap.slurm_timelimit}")
    header_bits.append(f"fill {fill}")
    if snap.in_flight_http is not None:
        header_bits.append(f"in_flight_http {snap.in_flight_http}")
    header.add_row(Text(" ".join(header_bits)))

    bars = Table(title="Campaign", expand=True)
    bars.add_column("done/total")
    bars.add_column("running")
    done = snap.completed + snap.censored + snap.failed
    bars.add_row(
        f"{done}/{_format_unknown(snap.total)}",
        f"in_progress {snap.in_progress}",
    )

    by_task = Table(title="By task / topology", expand=True)
    by_task.add_column("program")
    by_task.add_column("topology")
    by_task.add_column("k")
    by_task.add_column("pending")
    by_task.add_column("live")
    by_task.add_column("completed")
    by_task.add_column("censored")
    by_task.add_column("failed")
    by_task.add_column("interrupted")
    groups: dict[tuple[Any, Any, Any], dict[str, int]] = {}
    for row in snap.sidecars:
        key = (row.get("program"), row.get("topology"), row.get("cm_k"))
        bucket = groups.setdefault(
            key,
            {
                "pending": 0,
                "live": 0,
                "completed": 0,
                "censored": 0,
                "failed": 0,
                "interrupted": 0,
            },
        )
        status = row.get("run_status")
        if status in bucket:
            bucket[status] += 1
        if status == "in_progress":
            bucket["live"] += 1
    if snap.heartbeat is not None and snap.total is not None:
        cells = _queue_cells(snap.heartbeat.get("tasks")) or []
        occupied = {_cell_key(row) for row in snap.sidecars if row.get("run_status") in _OCCUPIED}
        pending_groups: Counter[tuple[Any, Any, Any]] = Counter()
        for cell in cells:
            if _cell_key(cell) not in occupied:
                pending_groups[(cell.get("program"), cell.get("topology"), cell.get("cm_k"))] += 1
        for key, count in pending_groups.items():
            groups.setdefault(
                key,
                {
                    "pending": 0,
                    "live": 0,
                    "completed": 0,
                    "censored": 0,
                    "failed": 0,
                    "interrupted": 0,
                },
            )["pending"] = count
    if not groups:
        by_task.add_row("-", "-", "-", "-", "-", "-", "-", "-", "-")
    else:
        for (program, topology, cm_k), bucket in sorted(groups.items(), key=lambda item: str(item[0])):
            by_task.add_row(
                str(program or "-"),
                str(topology or "-"),
                str(cm_k if cm_k is not None else "-"),
                str(bucket["pending"]),
                str(bucket["live"]),
                str(bucket["completed"]),
                str(bucket["censored"]),
                str(bucket["failed"]),
                str(bucket["interrupted"]),
            )

    study1 = Table(title="Health (Study 1)", expand=True)
    study1.add_column("gate_passed / finished")
    study1.add_column("median t_gate")
    study1.add_column("censored")
    study1.add_row(
        f"{snap.gate_passed}/{snap.emergence_finished}",
        "unknown" if snap.median_t_gate is None else str(snap.median_t_gate),
        str(sum(1 for row in snap.sidecars if row.get("program") == "emergence" and row.get("run_status") == "censored")),
    )

    study2 = Table(title="Health (Study 2)", expand=True)
    study2.add_column("prepared_state_valid failures")
    study2.add_column("progress")
    progress_bits = []
    if snap.flip_true is not None:
        progress_bits.append(f"flip {snap.flip_true}")
    else:
        n_vals = [
            row.get("n_interactions")
            for row in snap.sidecars
            if row.get("program") == "cm" and isinstance(row.get("n_interactions"), (int, float))
        ]
        h_vals = [
            row.get("phase2_horizon")
            for row in snap.sidecars
            if row.get("program") == "cm" and isinstance(row.get("phase2_horizon"), (int, float))
        ]
        if n_vals or h_vals:
            progress_bits.append(
                f"n_interactions {n_vals[0] if n_vals else 'unknown'} / "
                f"phase2_horizon {h_vals[0] if h_vals else 'unknown'}"
            )
    study2.add_row(str(snap.prepared_state_invalid), " ".join(progress_bits) or "-")

    failures = Table(title="Failures", expand=True)
    failures.add_column("error_class")
    failures.add_column("count")
    if snap.error_class_counts:
        for name, count in snap.error_class_counts.most_common():
            failures.add_row(name, str(count))
    else:
        failures.add_row("none", "0")
    recent = Table(title="Recent failures", expand=True)
    recent.add_column("run_id")
    recent.add_column("error_class")
    recent.add_column("topology")
    if snap.recent_failures:
        for row in snap.recent_failures:
            recent.add_row(str(row.get("run_id") or ""), str(row.get("error_class") or ""), str(row.get("topology") or ""))
    else:
        recent.add_row("-", "-", "-")

    live = Table(title="Live cells", expand=True)
    live.add_column("topology")
    live.add_column("seed")
    live.add_column("program")
    live.add_column("t")
    live.add_column("status")
    live.add_column("run_id")
    by_id = {row.get("run_id"): row for row in snap.sidecars}
    rows = snap.live_run_ids[:32] if snap.live_run_ids else [
        row.get("run_id") for row in snap.sidecars if row.get("run_status") == "in_progress"
    ][:32]
    if not rows:
        live.add_row("-", "-", "-", "-", "-", "-")
    else:
        for run_id in rows:
            row = by_id.get(run_id, {})
            status = str(row.get("run_status") or "")
            show_id = str(run_id or "") if status == "failed" else ""
            t_val = row.get("n_interactions")
            if t_val is None:
                t_val = row.get("last_checkpoint_t")
            live.add_row(
                str(row.get("topology") or "-"),
                str(row.get("seed_index") if row.get("seed_index") is not None else "-"),
                str(row.get("program") or "-"),
                str(t_val if t_val is not None else "-"),
                status or "-",
                show_id,
            )

    return Group(
        Panel(header, title="Header"),
        bars,
        by_task,
        study1,
        study2,
        failures,
        recent,
        live,
    )


def run_health_cli(
    *,
    campaign_dir: Path,
    model_shorthand: str,
    watch: bool = False,
    now: datetime | None = None,
    isatty: bool | None = None,
    stdout: TextIO | None = None,
    sleep=None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    tty = _stdout_isatty() if isatty is None else isatty
    sleeper = time.sleep if sleep is None else sleep
    if watch and tty:
        snap = read_health_snapshot(campaign_dir, model_shorthand, now=now or _wall_now())
        try:
            with Live(
                render_watch_layout(snap, now=now or _wall_now()),
                refresh_per_second=1 / WATCH_REFRESH_S,
                console=None,
            ) as live:
                while True:
                    sleeper(WATCH_REFRESH_S)
                    tick = now or _wall_now()
                    snap = read_health_snapshot(campaign_dir, model_shorthand, now=tick)
                    live.update(render_watch_layout(snap, now=tick))
        except KeyboardInterrupt:
            return verdict_exit_code(snap.verdict)
        return verdict_exit_code(snap.verdict)
    snap = read_health_snapshot(campaign_dir, model_shorthand, now=now or _wall_now())
    print(format_health_text(snap), file=out)
    return verdict_exit_code(snap.verdict)
