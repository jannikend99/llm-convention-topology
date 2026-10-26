"""Descriptive, paired, seed-block analysis for isolated response follow-ups."""
from __future__ import annotations
import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
try:
    from .design import make_cases, digest, MODELS
    from .run import validate_resume, read_lines
except ImportError:  # direct script execution from the repository checkout
    from design import make_cases, digest, MODELS
    from run import validate_resume, read_lines


def write_csv(path, rows):
    rows = list(rows)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def exact_sign(values):
    values = [v for v in values if v != 0]
    n = len(values)
    if not n:
        return 1.0
    k = min(sum(v > 0 for v in values), sum(v < 0 for v in values))
    return min(1., 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def block_effect(pairs):
    """Equal weight to each seed, then bootstrap whole seeds, not calls."""
    grouped = defaultdict(list)
    for seed, difference in pairs:
        grouped[seed].append(difference)
    values = [sum(v) / len(v) for _, v in sorted(grouped.items())]
    if not values:
        return dict(effect_pp='', ci_low_pp='', ci_high_pp='', seed_blocks=0,
                    nonzero_seed_blocks=0, seed_sign_p='', interval_status='no_valid_pairs')
    rng = random.Random(20261008)
    boots = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(2000))
    interval_status = 'insufficient_seeds' if len(values)<2 else ('degenerate_bootstrap' if len(set(values))==1 else 'estimated')
    return dict(effect_pp=100 * sum(values) / len(values), ci_low_pp=100 * boots[49] if interval_status=='estimated' else '',
                ci_high_pp=100 * boots[1949] if interval_status=='estimated' else '', interval_status=interval_status, seed_blocks=len(values),
                nonzero_seed_blocks=sum(v != 0 for v in values), seed_sign_p=exact_sign(values))


def holm(rows):
    valid = sorted((float(r['seed_sign_p']), i) for i, r in enumerate(rows) if r.get('seed_sign_p') != '')
    previous = 0.
    for rank, (p, i) in enumerate(valid):
        previous = max(previous, min(1., p * (len(valid) - rank)))
        rows[i]['seed_sign_p_holm'] = previous
        rows[i]['holm_family_tests'] = len(valid)


def replication(records):
    valid = [r for r in records if r['status'] == 'valid']
    factors = [('challenger', 'dicfv', 'lwlsi'), ('prompt_first', 'I', 'C'),
               ('enum_first', 'I', 'C'), ('history', 'incumbent_control', 'repeated_mismatch'),
               ('history', 'mismatch_oldest', 'mismatch_latest')]
    output = []
    for factor, control, treatment in factors:
        matched = defaultdict(dict)
        for row in valid:
            case = row['case']
            if case[factor] not in (control, treatment):
                continue
            key = tuple(case[k] for k in ('seed', 'history', 'challenger', 'prompt_first', 'enum_first') if k != factor)
            matched[key][case[factor]] = row
        pairs = []
        for pair in matched.values():
            if control in pair and treatment in pair:
                a, b = pair[control], pair[treatment]
                pairs.append((a['case']['seed'], int(b['value'] == b['case']['challenger']) - int(a['value'] == a['case']['challenger'])))
        output.append(dict(factor='recency' if control=='mismatch_oldest' else factor, control=control, treatment=treatment, paired_calls=len(pairs),
                           denominator='pairs with two valid responses', **block_effect(pairs)))
    holm(output)
    return output


def rules(records):
    valid = [r for r in records if r['status'] == 'valid']
    output = []
    for family in sorted({r['case']['family'] for r in records}):
        subset = [r for r in valid if r['case']['family'] == family]
        for prediction in ('own_last', 'partner_last', 'own_mode', 'partner_mode', 'combined_mode', 'option_first'):
            eligible = [r for r in subset if r['case']['predictions'][prediction] is not None]
            output.append(dict(family=family, metric='prediction_agreement', prediction=prediction,
                               eligible_valid=len(eligible), matches=sum(r['value'] == r['case']['predictions'][prediction] for r in eligible),
                               share=sum(r['value'] == r['case']['predictions'][prediction] for r in eligible) / len(eligible) if eligible else '',
                               note='Overlapping candidate predictions; agreement does not identify an internal rule'))
        matched = defaultdict(dict)
        for r in subset:
            c = r['case']
            matched[(c['seed'], tuple(sorted(c['labels'].items())), c['reverse'])][c['variant']] = r
        pairs = []
        changed = 0
        for pair in matched.values():
            if 'last_A' in pair and 'last_B' in pair:
                a, b = pair['last_A'], pair['last_B']
                changed += a['value'] != b['value']
                pairs.append((a['case']['seed'], int(b['value'] == b['case']['labels']['B']) - int(a['value'] == a['case']['labels']['B'])))
        output.append(dict(family=family, metric='paired_last_swap', prediction='role_B', paired_calls=len(pairs),
                           changed_choice=changed, **block_effect(pairs)))
    holm([r for r in output if r['metric'] == 'paired_last_swap'])
    return output


def retention(records, plan=None):
    by_id = {r['case']['id']: r for r in records}
    initials = [r for r in records if r['case']['phase'] == 'initial']
    expected_initials = sum(c['phase']=='initial' for c in plan) if plan is not None else len(initials)
    valid_initials = [r for r in initials if r['status'] == 'valid']
    adopted = {r['case']['id'] for r in valid_initials if r['value'] == r['case']['challenger']}
    output = [dict(branch='shared_initial', step=0, initial_contexts=expected_initials, recorded_initials=len(initials), valid_initials=len(valid_initials),
                   initial_adopters=len(adopted), initial_adoption_share=len(adopted)/len(valid_initials) if valid_initials else '',
                   note='One initial response shared across all three branches')]
    for branch in ('reinforced', 'reverted', 'alternating'):
        for step in (1, 3, 12):
            endpoints = [r for r in records if r['case']['branch'] == branch and r['case']['step'] == step]
            complete, adopters, uninterrupted = [], [], []
            for endpoint in endpoints:
                chain = [endpoint]
                while chain[-1]['case']['parent_id']:
                    parent = by_id.get(chain[-1]['case']['parent_id'])
                    if parent is None:
                        break
                    chain.append(parent)
                root = chain[-1]
                if root['case']['phase'] != 'initial' or len(chain) != step+1 or any(r['status'] != 'valid' for r in chain):
                    continue
                complete.append(endpoint)
                if root['case']['id'] in adopted:
                    adopters.append(endpoint)
                    if all(r['value'] == r['case']['challenger'] for r in chain):
                        uninterrupted.append(endpoint)
            output.append(dict(branch=branch, step=step, initial_contexts=expected_initials, recorded_initials=len(initials), valid_initials=len(valid_initials),
                               initial_adopters=len(adopted), complete_trajectories=len(complete), censored_or_missing=expected_initials-len(complete),
                               endpoint_challenger_share=sum(r['value'] == r['case']['challenger'] for r in complete)/len(complete) if complete else '',
                               complete_adopter_trajectories=len(adopters), retained_adopters=sum(r['value'] == r['case']['challenger'] for r in adopters),
                               uninterrupted_adopters=len(uninterrupted),
                               uninterrupted_share_among_complete_adopters=len(uninterrupted)/len(adopters) if adopters else '',
                               note='Invalid or missing ancestor censors trajectory; branches share initial answers'))
    for step in (1, 3, 12):
        grouped = defaultdict(dict)
        for row in records:
            c = row['case']
            if c['step'] == step and row['status'] == 'valid':
                grouped[(c['seed'], c['challenger'], c['prompt_first'], c['enum_first'])][c['branch']] = row
        for treatment in ('reverted', 'alternating'):
            pairs = []
            for group in grouped.values():
                if treatment in group and 'reinforced' in group:
                    a, b = group['reinforced'], group[treatment]
                    pairs.append((a['case']['seed'], int(b['value']==b['case']['challenger'])-int(a['value']==a['case']['challenger'])))
            output.append(dict(branch=treatment, step=step, metric='paired_endpoint_vs_reinforced',
                               paired_contexts=len(pairs), **block_effect(pairs),
                               note=('Pre-feedback consistency control: branch histories are identical' if step == 1 else
                                     'Paired branches share the initial response; bootstrap whole seeds')))
    holm([r for r in output if r.get('metric') == 'paired_endpoint_vs_reinforced'])
    return output


def analyze(directory):
    directory = Path(directory)
    design = json.loads((directory / 'design.json').read_text())
    if not isinstance(design, dict) or design.get('model') not in MODELS:
        raise ValueError('missing or unsupported model metadata')
    hashes = design.get('source_hashes', {})
    if not hashes or any(not isinstance(v,str) or len(v)!=64 or any(ch not in '0123456789abcdef' for ch in v) for v in hashes.values()):
        raise ValueError('invalid or missing recorded source hashes')
    if directory.name != digest(design)[:12]:
        raise ValueError('metadata fingerprint does not match battery directory')
    # The runner's complete static cases provide the authoritative expected IDs.
    plan = design['cases'] if isinstance(design, dict) and 'cases' in design else design
    if not isinstance(plan, list) or not plan:
        raise ValueError('design.json must contain non-empty cases')
    records = [json.loads(line) for line in (directory / 'responses.jsonl').read_text().splitlines() if line.strip()]
    expected = {c['id'] for c in plan}
    ids = [r['case']['id'] for r in records]
    if len(expected) != len(plan) or len(ids) != len(set(ids)) or set(ids)-expected:
        raise ValueError('duplicate or unknown case IDs')
    if any(r['status'] not in ('valid', 'invalid', 'blocked') for r in records):
        raise ValueError('unknown response status')
    if any(r['status'] == 'valid' and r['value'] not in r['case']['enum_options'] for r in records):
        raise ValueError('valid status with illegal answer')
    experiment = plan[0]['experiment']
    repeats = design.get('repeats', max(c['repeat'] for c in plan)+1)
    seed_base = design.get('seed_base', min(c['seed'] for c in plan))
    if plan != make_cases(experiment, repeats, seed_base):
        raise ValueError('static cases do not match the deterministic design')
    validate_resume(plan, records, read_lines(directory/'attempts.jsonl'))
    if any(c['experiment'] != experiment for c in plan):
        raise ValueError('mixed experiment design')
    counts = Counter(r['status'] for r in records)
    verification = dict(experiment=experiment, model=design.get('model'), mock=design.get('mock'), expected=len(plan), recorded=len(records), missing=len(expected-set(ids)),
                        valid=counts['valid'], invalid=counts['invalid'], blocked=counts['blocked'],
                        complete=set(ids)==expected, all_valid=set(ids)==expected and counts['valid']==len(plan),
                        inference='Isolated response diagnostics; seed-block sign tests and bootstrap are conditional on seed blocks being independent')
    summary = [dict(experiment=experiment, **{k:v for k,v in verification.items() if k!='experiment'})]
    if experiment == 'replication':
        groups = defaultdict(list)
        for row in records:
            c = row['case']
            groups[(c['history'], c['challenger'], c['prompt_first'], c['enum_first'])].append(row)
        for (history, challenger, prompt_first, enum_first), subset in sorted(groups.items()):
            valid_subset = [r for r in subset if r['status']=='valid']
            successes = sum(r['value']==challenger for r in valid_subset)
            summary.append(dict(experiment=experiment, model=design.get('model'), mock=design.get('mock'),
                                history=history, challenger=challenger, prompt_first=prompt_first, enum_first=enum_first,
                                expected=repeats, recorded=len(subset), valid=len(valid_subset), excluded=len(subset)-len(valid_subset),
                                missing=repeats-len(subset), challenger_choices=successes,
                                challenger_share=successes/len(valid_subset) if valid_subset else '',
                                denominator='valid responses within exact condition'))
    write_csv(directory/'summary.csv', summary)
    write_csv(directory/'contrasts.csv', replication(records) if experiment=='replication' else [])
    write_csv(directory/'rules.csv', rules(records) if experiment=='rules' else [])
    write_csv(directory/'retention.csv', retention(records, plan) if experiment=='retention' else [])
    (directory/'verification.json').write_text(json.dumps(verification, indent=2)+'\n')
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input', type=Path, help='Exact fingerprint battery directory')
    group.add_argument('--results-root', type=Path, help='Recursively analyze separate batteries without pooling')
    args = parser.parse_args()
    if args.input:
        result = analyze(args.input)
        print(json.dumps(result, indent=2))
        return 0 if result['all_valid'] else 2
    directories = sorted(p.parent for p in args.results_root.rglob('design.json'))
    if not directories:
        raise ValueError('No design.json batteries found under results root')
    results = []
    tables = {name: [] for name in ('summary', 'contrasts', 'rules', 'retention')}
    for directory in directories:
        result = analyze(directory)
        result['battery_directory'] = str(directory)
        results.append(result)
        for name in tables:
            with (directory/(name+'.csv')).open() as handle:
                if not handle.read(1):
                    continue
                handle.seek(0)
                for row in csv.DictReader(handle):
                    tables[name].append(dict(row, battery_directory=str(directory), model=result['model'], mock=result['mock']))
    # These are concatenated tables. No pooling, cross-model inference, or averaging.
    for name, rows in tables.items():
        write_csv(args.results_root/('aggregate-'+name+'.csv'), rows)
    report = dict(batteries=results, all_valid=all(r['all_valid'] for r in results),
                  scope='Separate fingerprint batteries; Holm families remain separate by battery and model; no pooling')
    (args.results_root/'aggregate-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['all_valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
