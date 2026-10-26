#!/usr/bin/env python3
"""Reconstruct Main quantitative endpoints from the supplied raw trackers."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import pickle
import numpy as np

MODELS = {'gemma4_31b', 'glm4_32b', 'olmo31_32b', 'qwen38_27b'}
DATA = Path('02_Topic/Experiment_Code/llm-convention-topology/data/runs/experiment')
HYPOTHESIS = Path('specs/results-analysis/main-runs-2026-10-05/hypothesis-run-data.csv')


def truth(value):
    return str(value).lower() in {'true', '1', '1.0'}


def number(value):
    return None if value in ('', None) else float(value)


def audit(root, output):
    references = {row['run_id']: row for row in csv.DictReader((root / HYPOTHESIS).open()) if row['model'] in MODELS}
    data = root / DATA
    if not data.is_dir():
        raise FileNotFoundError(f'complete raw campaign is required: {data}')
    rows = []
    counts = Counter()
    seen = set()
    for meta_path in sorted((data / 'runs').rglob('*.meta.json')):
        meta = json.loads(meta_path.read_text())
        model, program, status = (meta[key] for key in ['model_shorthand', 'program', 'run_status'])
        if model not in MODELS or meta['campaign'] != 'experiment':
            raise ValueError('unexpected campaign/model in Main data')
        stem = meta_path.name.removesuffix('.meta.json')
        path = meta_path.with_name(stem + '.pkl')
        if not meta_path.with_name(stem + '.events.jsonl').is_file():
            raise FileNotFoundError('missing event stream: ' + stem)
        blob = path.read_bytes()
        tracker = pickle.loads(blob)['tracker']
        answers, success = tracker['answers'], tracker['outcome']
        n = len(success)
        if not (len(answers) == len(tracker['players']) == n == meta['n_interactions']):
            raise ValueError('tracker/sidecar length mismatch: ' + stem)
        if any(value != int(a == b) for value, (a, b) in zip(success, answers)):
            raise ValueError('recorded outcome disagrees with paired choices: ' + stem)
        counts[(program, status)] += 1
        row = dict(run_id=meta['run_id'], model=model, program=program, topology=meta['topology'],
                   k=meta.get('cm_k'), status=status, interactions=n, pickle_sha256=hashlib.sha256(blob).hexdigest(),
                   final_dominance=None, final_success=None, first_gate=None, ever_strict_flip=None,
                   terminal_strict_flip=None, first_strict_flip=None)
        if status not in {'completed', 'censored'}:
            if status != 'failed' or model != 'qwen38_27b':
                raise ValueError('unexpected nonterminal status: ' + stem)
            rows.append(row)
            continue
        if n != 1500:
            raise ValueError('usable run does not reach 1500: ' + stem)
        ref = references[meta['run_id']]
        seen.add(meta['run_id'])
        emissions = Counter(label for pair in answers[-144:] for label in pair)
        row['final_dominance'] = max(emissions.values()) / 288
        row['final_success'] = sum(success[-144:]) / 144
        cumulative = np.cumsum([0] + success)
        rolling_success = cumulative[144:] - cumulative[:-144]
        gates = np.flatnonzero(rolling_success >= 137)
        row['first_gate'] = int(gates[0] + 144) if len(gates) else None
        if program == 'emergence':
            for field, key in [('final_dominance', 'observed_endpoint_dominance'), ('final_success', 'observed_endpoint_success')]:
                if abs(row[field] - float(ref[key])) > 1e-12:
                    raise AssertionError(f'raw/frozen Study1 endpoint mismatch: {stem} {field}')
            if row['first_gate'] != number(ref['gate_interactions']):
                raise AssertionError('raw/frozen first gate mismatch: ' + stem)
        else:
            if len(meta['options']) != 2:
                raise AssertionError('CM endpoint audit expects the recorded binary task')
            target = meta['committed_to']
            target_counts = [sum(label == target for label in pair) for pair in answers]
            cumulative_target = np.cumsum([0] + target_counts)
            rolling_target = cumulative_target[144:] - cumulative_target[:-144]
            strict = (rolling_success >= 137) & (rolling_target > 144)
            flips = np.flatnonzero(strict)
            row.update(ever_strict_flip=bool(len(flips)), terminal_strict_flip=bool(strict[-1]),
                       first_strict_flip=int(flips[0] + 144) if len(flips) else None)
            if row['ever_strict_flip'] != truth(ref['flip']) or row['terminal_strict_flip'] != truth(ref['terminal_strict_flip']) or row['first_strict_flip'] != number(ref['first_flip']):
                raise AssertionError('raw/frozen CM strict outcome mismatch: ' + stem)
        rows.append(row)
    expected = {('emergence', 'completed'): 245, ('emergence', 'censored'): 394,
                ('emergence', 'failed'): 1, ('cm', 'completed'): 1912, ('cm', 'failed'): 8}
    if dict(counts) != expected or len(rows) != 2560 or len(seen) != 2551 or set(references) != seen:
        raise AssertionError('Main source/reference census mismatch')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'raw-endpoint-reconstruction.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    result = dict(status='PASS', attempted_runs=2560, usable_study1=639, usable_cm=1912, failed_prefixes=9,
                  all_usable_horizons=1500, frozen_quantitative_endpoints_match=True,
                  raw_events_scope='presence checked here; full journal/byte integrity belongs to the separate raw archive verifier',
                  provider_requests=0, new_fits=0)
    (output / 'raw-endpoint-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.package_root.resolve(), args.output.resolve())
    except Exception as error:
        parser.exit(2, f'ERROR: {type(error).__name__}: {error}\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
