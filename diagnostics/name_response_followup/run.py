"""Run bounded isolated diagnostics against a local inference server; never retry a reserved request."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from design import MODELS, DEFAULT_REPEATS, make_cases, digest, advance_player
from convention_topology.config import is_localhost_url, load_config, resolve_model
from convention_topology.json_output import parse_decision
from convention_topology.llm import chat_completion_kwargs
from convention_topology.prompting import build_user_prompt


def request(spec, row):
    kwargs = chat_completion_kwargs(model_id=spec.model_id, prompt=row['prompt'],
        temperature=spec.temperature, max_tokens=spec.max_tokens, options=row['enum_options'],
        json_schema=True, thinking=spec.thinking, reasoning_effort=spec.reasoning_effort,
        send_chat_template_kwargs=spec.send_chat_template_kwargs,
        thinking_token_budget=spec.thinking_token_budget)
    kwargs['seed'] = row['seed']
    return kwargs


def validate(text, finish, options):
    if finish != 'stop':
        raise ValueError(f'non-stop finish_reason: {finish}')
    return parse_decision(text, options)


def materialize_case(row, by_id):
    case = json.loads(json.dumps(row))
    if row['parent_id'] is not None:
        parent = by_id.get(row['parent_id'])
        if parent is None or parent['status'] != 'valid':
            return None
        case['player'] = advance_player(parent)
    case['prompt'] = build_user_prompt(case['player'], 12, [-50, 100], case['prompt_options'])
    case['prompt_sha256'] = hashlib.sha256(case['prompt'].encode()).hexdigest()
    return case


def validate_resume(plan, records, started):
    expected = {r['id']: r for r in plan}
    ids = [r['case']['id'] for r in records]
    if len(ids) != len(set(ids)) or not set(ids) <= expected.keys():
        raise ValueError('duplicate or unexpected response IDs; refusing resume')
    starts = [r['id'] for r in started]
    if len(starts) != len(set(starts)) or not set(starts) <= expected.keys():
        raise ValueError('duplicate or unexpected attempt IDs; refusing resume')
    by_id = {}
    for result in records:
        row = expected[result['case']['id']]
        if result.get('plan_sha256') != digest(row):
            raise ValueError('response design hash mismatch; refusing resume')
        actual = materialize_case(row, by_id)
        if actual is None:
            if result['status'] != 'blocked' or result['case'] != row:
                raise ValueError('invalid parent provenance; refusing resume')
        elif result['case'] != actual or result['status'] not in ('valid', 'invalid'):
            raise ValueError('response history or prompt mismatch; refusing resume')
        if result['status'] == 'valid':
            value, reason = validate(result['text'], result['finish_reason'], actual['enum_options'])
            if result['value'] != value or result.get('reason') != reason:
                raise ValueError('response value differs from raw output; refusing resume')
        if result['status'] != 'blocked' and row['id'] not in starts:
            raise ValueError('response has no durable reservation; refusing resume')
        by_id[row['id']] = result
    if any(r.get('plan_sha256') != digest(expected[r['id']]) for r in started):
        raise ValueError('reservation design mismatch; refusing resume')
    return by_id, set(starts)-set(ids)


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def append_durable(handle, value):
    handle.write(json.dumps(value, sort_keys=True)+'\n')
    handle.flush()
    os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', choices=DEFAULT_REPEATS, required=True)
    parser.add_argument('--model', choices=MODELS, required=True)
    parser.add_argument('--repeats', type=int)
    parser.add_argument('--seed-base', type=int, default=20261008)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()
    repeats = DEFAULT_REPEATS[args.experiment] if args.repeats is None else args.repeats
    try:
        battery = make_cases(args.experiment, repeats, args.seed_base)
    except ValueError as exc:
        parser.error(str(exc))
    if not is_localhost_url(args.base_url):
        parser.error('only localhost inference is supported')
    spec = resolve_model(load_config(ROOT/'config.yaml'), args.model)
    sources = [Path(__file__), Path(__file__).with_name('design.py'), Path(__file__).with_name('probe.slurm'), ROOT/'config.yaml']
    sources += [ROOT/'convention_topology'/name for name in ('prompting.py', 'json_output.py', 'llm.py', 'config.py')]
    profile = asdict(spec)
    profile.pop('api_key', None)
    profile.pop('base_url', None)
    metadata = dict(design_version=1, experiment=args.experiment, model=args.model,
                    model_profile=profile, repeats=repeats, seed_base=args.seed_base,
                    expected_calls=len(battery), mock=args.mock, cases=battery,
                    source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    fingerprint = digest(metadata)
    print(f'{args.model} {args.experiment}: at most {len(battery)} requests; design {fingerprint[:12]}', flush=True)
    if args.dry_run:
        return
    if args.output is None:
        parser.error('--output is required for inference or mock')
    directory = args.output/('mock' if args.mock else 'live')/args.model/args.experiment/fingerprint[:12]
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'writer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('another runner already writes this battery')
        metadata_path = directory/'design.json'
        if metadata_path.exists():
            if json.loads(metadata_path.read_text()) != metadata:
                raise ValueError('existing design differs; refusing resume')
        else:
            with metadata_path.open('x') as handle:
                handle.write(json.dumps(metadata, indent=2)+'\n')
                handle.flush()
                os.fsync(handle.fileno())
        records_path, journal = directory/'responses.jsonl', directory/'attempts.jsonl'
        records, started = read_lines(records_path), read_lines(journal)
        by_id, interrupted = validate_resume(battery, records, started)
        client = None
        if not args.mock and len(by_id) < len(battery):
            from openai import OpenAI
            client = OpenAI(base_url=args.base_url, api_key='EMPTY', max_retries=0, timeout=120)
            server_models = client.models.list().model_dump()
            if spec.model_id not in [m['id'] for m in server_models['data']]:
                client.close()
                raise ValueError('server does not advertise the configured model')
            with (directory/'servers.jsonl').open('a') as handle:
                append_durable(handle, server_models)
        try:
            consecutive_errors = 0
            with records_path.open('a') as handle, journal.open('a') as attempts:
                for row in battery:
                    if row['id'] in by_id:
                        continue
                    case = materialize_case(row, by_id)
                    result = dict(case=case or row, plan_sha256=digest(row), status='invalid', value=None)
                    if case is None:
                        result.update(status='blocked', error='invalid or missing parent; no model request')
                    elif row['id'] in interrupted:
                        result['error'] = 'interrupted reserved request; outcome unknown; never resent'
                    else:
                        append_durable(attempts, dict(id=row['id'], plan_sha256=digest(row)))
                        try:
                            if args.mock:
                                text, finish, usage = json.dumps({'value': case['enum_options'][0], 'reason': 'MOCK enum-first fixture'}), 'stop', {}
                            else:
                                response = client.chat.completions.create(**request(spec, case))
                                text = response.choices[0].message.content or ''
                                finish = response.choices[0].finish_reason
                                usage = response.usage.model_dump() if response.usage else {}
                                result['response'] = response.model_dump()
                            result.update(text=text, finish_reason=finish, usage=usage)
                            value, reason = validate(text, finish, case['enum_options'])
                            result.update(status='valid', value=value, reason=reason)
                            consecutive_errors = 0
                        except Exception as exc:
                            result['error'] = f'{type(exc).__name__}: {exc}'
                            consecutive_errors += 1
                    append_durable(handle, result)
                    records.append(result)
                    by_id[row['id']] = result
                    if len(records) % 50 == 0 or result['status'] != 'valid' or len(records) == len(battery):
                        print(f'{len(records)}/{len(battery)} {result["status"]}', flush=True)
                    if consecutive_errors >= 3:
                        print('Stopping after three consecutive failures; inspect before resuming.', flush=True)
                        break
        finally:
            if client:
                client.close()
        report = dict(expected=len(battery), recorded=len(records),
                      valid=sum(r['status']=='valid' for r in records),
                      invalid=sum(r['status']=='invalid' for r in records),
                      blocked=sum(r['status']=='blocked' for r in records), design_sha256=fingerprint)
        (directory/'completion.json').write_text(json.dumps(report, indent=2)+'\n')
        print(f'Results: {directory}', flush=True)
        if len(records) != len(battery) or any(r['status'] != 'valid' for r in records):
            raise SystemExit('Battery incomplete or contains invalid/blocked responses; no silent retries.')


if __name__ == '__main__':
    main()
