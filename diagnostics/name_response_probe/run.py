"""Small counterfactual response battery; independent of counted network runs."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import itertools
import json
import os
import random
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from convention_topology.config import is_localhost_url, load_config, resolve_model
from convention_topology.json_output import parse_decision
from convention_topology.llm import chat_completion_kwargs
from convention_topology.prompting import build_user_prompt

MODELS = ("olmo31_32b", "qwen38_27b", "gemma4_31b")
# I = incumbent; C = challenger. No actual committed agents in this probe.
HISTORIES = {
    "incumbent_control": [("I", "I")] * 12,
    "mismatch_oldest": [("I", "C")] + [("I", "I")] * 11,
    "mismatch_latest": [("I", "I")] * 11 + [("I", "C")],
    "repeated_mismatch": [("I", "I")] * 6 + [("I", "C")] * 6,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cases(repeats=3):
    rows = []
    for history, c_label, prompt_first, enum_first, repeat in itertools.product(
        HISTORIES, ("dicfv", "lwlsi"), ("I", "C"), ("I", "C"), range(repeats)
    ):
        labels = {"C": c_label, "I": "lwlsi" if c_label == "dicfv" else "dicfv"}
        player = {
            "my_history": [labels[a] for a, _ in HISTORIES[history]],
            "partner_history": [labels[b] for _, b in HISTORIES[history]],
            "outcome": [100 if a == b else -50 for a, b in HISTORIES[history]],
        }
        prompt_options = [labels[prompt_first], labels["C" if prompt_first == "I" else "I"]]
        enum_options = [labels[enum_first], labels["C" if enum_first == "I" else "I"]]
        row = dict(history=history, challenger=c_label, prompt_first=prompt_first,
                   enum_first=enum_first, repeat=repeat, seed=41000 + repeat,
                   player=player, prompt_options=prompt_options, enum_options=enum_options)
        row["prompt"] = build_user_prompt(player, 12, [-50, 100], prompt_options)
        row["id"] = digest(row)
        rows.append(row)
    random.Random(240106).shuffle(rows)
    return rows


def request(spec, row):
    result = chat_completion_kwargs(
        model_id=spec.model_id, prompt=row["prompt"], temperature=spec.temperature,
        max_tokens=spec.max_tokens, options=row["enum_options"], json_schema=True,
        thinking=spec.thinking, reasoning_effort=spec.reasoning_effort,
        send_chat_template_kwargs=spec.send_chat_template_kwargs,
        thinking_token_budget=spec.thinking_token_budget,
    )
    result["seed"] = row["seed"]
    return result


def validate(text, finish, options):
    if finish != "stop":
        raise ValueError(f"non-stop finish_reason: {finish}")
    return parse_decision(text, options)


def summarize(directory, records):
    groups = defaultdict(list)
    for r in records:
        c = r["case"]
        groups[(c["history"], c["challenger"], c["prompt_first"], c["enum_first"])].append(r)
    with (directory / "summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["history", "challenger", "prompt_first", "enum_first", "attempted",
                         "valid", "invalid", "challenger_choices", "challenger_share_valid"])
        for key, group in sorted(groups.items()):
            valid = [r for r in group if r["status"] == "valid"]
            chosen = sum(r["value"] == r["case"]["challenger"] for r in valid)
            writer.writerow([*key, len(group), len(valid), len(group)-len(valid), chosen,
                             chosen/len(valid) if valid else ""])
    # Contrast pairs hold all other manipulated factors and seed fixed.
    with (directory / "paired_contrasts.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["factor", "contrast", "complete_pairs", "missing_or_invalid_pairs",
                         "challenger_share_difference_pp"])
        definitions = [("challenger", "dicfv", "lwlsi"), ("prompt_first", "I", "C"),
                       ("enum_first", "I", "C"), ("history", "mismatch_oldest", "mismatch_latest")]
        for factor, low, high in definitions:
            pairs = defaultdict(dict)
            for r in records:
                c = r["case"]
                if c[factor] not in (low, high):
                    continue
                key = tuple(c[k] for k in ("history", "challenger", "prompt_first", "enum_first", "repeat") if k != factor)
                pairs[key][c[factor]] = r
            deltas = []
            for pair in pairs.values():
                if all(v in pair and pair[v]["status"] == "valid" for v in (low, high)):
                    y = lambda v: int(pair[v]["value"] == pair[v]["case"]["challenger"])
                    deltas.append(y(high)-y(low))
            writer.writerow([factor, f"{high} minus {low}", len(deltas), len(pairs)-len(deltas),
                             100*sum(deltas)/len(deltas) if deltas else ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("repeats must be between 1 and 10 (32–320 calls per model)")
    if not is_localhost_url(args.base_url):
        parser.error("only localhost inference is supported")
    spec = resolve_model(load_config(ROOT / "config.yaml"), args.model)
    battery = cases(args.repeats)
    # Include reused source hashes so a changed prompt/parser cannot silently resume.
    sources = [Path(__file__), Path(__file__).with_name("probe.slurm"), ROOT / "convention_topology/prompting.py",
               ROOT / "convention_topology/json_output.py", ROOT / "convention_topology/llm.py",
               ROOT / "convention_topology/config.py"]
    metadata = dict(design_version=1, model=asdict(spec), repeats=args.repeats, mock=args.mock,
                    cases=battery, source_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    # Port and API key are neither scientific settings nor saved credentials.
    metadata["model"].pop("api_key", None)
    metadata["model"].pop("base_url", None)
    fingerprint = digest(metadata)
    print(f"{args.model}: {len(battery)} calls; design {fingerprint[:12]}", flush=True)
    if args.dry_run:
        return
    if args.output is None:
        parser.error("--output is required for inference or mock")
    directory = args.output / ("mock" if args.mock else "live") / args.model / fingerprint[:12]
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / "writer.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another runner already writes this battery")
    metadata_path = directory / "design.json"
    if metadata_path.exists():
        if json.loads(metadata_path.read_text()) != metadata:
            raise ValueError("existing design differs; refusing resume")
    else:
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    records_path = directory / "responses.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()] if records_path.exists() else []
    ids = [r["case"]["id"] for r in records]
    expected = {r["id"] for r in battery}
    if len(ids) != len(set(ids)) or not set(ids) <= expected:
        raise ValueError("duplicate or unexpected response IDs; refusing resume")
    journal = directory / "attempts.jsonl"
    started = [json.loads(line)["id"] for line in journal.read_text().splitlines()] if journal.exists() else []
    if len(started) != len(set(started)) or not set(started) <= expected:
        raise ValueError("duplicate or unexpected attempt IDs; refusing resume")
    # A request interrupted after reservation has unknown outcome. Never resend it.
    interrupted = set(started) - set(ids)
    with records_path.open("a") as h:
        for row in battery:
            if row["id"] in interrupted:
                result = dict(case=row, status="invalid", value=None, error="interrupted reserved request; outcome unknown")
                h.write(json.dumps(result) + "\n")
                records.append(result)
    # Failed requests also consume the fixed budget. No automatic retries.
    done = set(ids) | interrupted
    client = None
    if not args.mock and len(done) < len(battery):
        from openai import OpenAI
        client = OpenAI(base_url=args.base_url, api_key="EMPTY", max_retries=0, timeout=120)
        server_models = client.models.list().model_dump()
        if spec.model_id not in [m["id"] for m in server_models["data"]]:
            raise ValueError("server does not advertise the configured model")
        with (directory / "servers.jsonl").open("a") as h:
            h.write(json.dumps(server_models) + "\n")
    try:
        consecutive_errors = 0
        with records_path.open("a") as handle, journal.open("a") as attempts:
            for row in battery:
                if row["id"] in done:
                    continue
                attempts.write(json.dumps({"id": row["id"]}) + "\n")
                attempts.flush()
                os.fsync(attempts.fileno())
                result = dict(case=row, status="invalid", value=None)
                try:
                    if args.mock:
                        text, finish, usage = json.dumps({"value": row["enum_options"][0], "reason": "MOCK enum-first fixture"}), "stop", {}
                    else:
                        response = client.chat.completions.create(**request(spec, row))
                        text = response.choices[0].message.content or ""
                        finish = response.choices[0].finish_reason
                        usage = response.usage.model_dump() if response.usage else {}
                        result["response"] = response.model_dump()
                    result.update(text=text, finish_reason=finish, usage=usage)
                    value, reason = validate(text, finish, row["enum_options"])
                    result.update(status="valid", value=value, reason=reason)
                    consecutive_errors = 0
                except Exception as exc:
                    result["error"] = f"{type(exc).__name__}: {exc}"
                    consecutive_errors += 1
                handle.write(json.dumps(result) + "\n")
                handle.flush()
                records.append(result)
                print(f"{len(records)}/{len(battery)} {result['status']}", flush=True)
                if consecutive_errors >= 3:
                    print("Stopping after three consecutive failures; inspect logs before resuming.", flush=True)
                    break
    finally:
        if client:
            client.close()
        summarize(directory, records)
    print(f"Results: {directory}", flush=True)
    lock.close()
    if any(r["status"] != "valid" for r in records):
        raise SystemExit("Battery contains failed/invalid responses. Inspect logs; no silent retries.")


if __name__ == "__main__":
    main()
