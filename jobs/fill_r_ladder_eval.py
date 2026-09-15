#!/usr/bin/env python3
"""Summarize fill-ladder campaigns: JSON-schema share + last Engine 000 lines."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ENGINE_RE = re.compile(
    r"Running:\s*(\d+)\s*reqs,\s*Waiting:\s*(\d+)\s*reqs.*?GPU KV cache usage:\s*([0-9.]+)%"
)


def _scratch() -> Path:
    if os.environ.get("SCRATCH"):
        return Path(os.environ["SCRATCH"])
    user = os.environ.get("USER")
    if not user:
        raise SystemExit("USER is unset; cannot resolve /scratch/shared/$USER")
    primary = Path("/scratch/shared") / user
    yen = Path("/yen/scratch/shared") / user
    if primary.is_dir():
        return primary
    if yen.is_dir():
        return yen
    return primary


def _schema_share(root: Path) -> tuple[int, int]:
    n = ok = 0
    if not root.exists():
        return 0, 0
    for path in root.rglob("*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("record_type") != "llm_attempt":
                continue
            n += 1
            if row.get("schema_valid") is True:
                ok += 1
    return n, ok


def _engine_stats(job_id: str) -> dict[str, float | int | None]:
    log = _scratch() / "vllm" / f"thesis_{job_id}.log"
    waiting: list[int] = []
    running: list[int] = []
    kv: list[float] = []
    if log.exists():
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for match in ENGINE_RE.finditer(text):
            running.append(int(match.group(1)))
            waiting.append(int(match.group(2)))
            kv.append(float(match.group(3)))
    return {
        "engine_lines": len(waiting),
        "waiting_max": max(waiting) if waiting else None,
        "waiting_last": waiting[-1] if waiting else None,
        "running_last": running[-1] if running else None,
        "kv_max": max(kv) if kv else None,
        "kv_last": kv[-1] if kv else None,
    }


def main() -> int:
    scratch = _scratch()
    manifest = Path(os.environ.get("FILL_LADDER_MANIFEST", scratch / "runs" / "fill-ladder" / "manifest.jsonl"))
    if not manifest.exists():
        print(f"missing manifest {manifest}")
        return 1
    rows = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    print(
        f"{'model':<14} {'R':>4} {'job':>8} {'attempts':>8} {'json':>8} "
        f"{'wait_max':>8} {'kv_max':>7} {'kv_last':>7} {'eng':>4}"
    )
    for row in rows:
        root = Path(row["artifact_root"])
        n, ok = _schema_share(root)
        share = f"{ok / n:.4f}" if n else "na"
        stats = _engine_stats(str(row["job_id"]))
        print(
            f"{row['model']:<14} {row['R']:>4} {row['job_id']:>8} {n:>8} {share:>8} "
            f"{str(stats['waiting_max']):>8} {str(stats['kv_max']):>7} "
            f"{str(stats['kv_last']):>7} {stats['engine_lines']:>4}"
        )
        row["attempts"] = n
        row["schema_valid"] = ok
        row["schema_share"] = None if n == 0 else ok / n
        row.update(stats)
    out = manifest.with_name("eval.jsonl")
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    print(f"wrote {out}")
    print("tip: json share << previous R, or waiting_max stays high, or kv_max ~100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
