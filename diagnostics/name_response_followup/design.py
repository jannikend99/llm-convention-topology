"""Fixed, bounded plans for isolated response diagnostics (no network simulation)."""
from __future__ import annotations
import hashlib
import itertools
import json
import random
from collections import Counter

MODELS = ('olmo31_32b', 'qwen38_27b', 'gemma4_31b', 'glm4_32b')
DEFAULT_REPEATS = {'replication': 50, 'rules': 25, 'retention': 20}
OPTIONS = ('dicfv', 'lwlsi', 'acffw', 'emwuz', 'rlqcx', 'piseu', 'idhln', 'gzpvr', 'ptqsu', 'fouyt')
HISTORIES = {
    'incumbent_control': [('I', 'I')] * 12,
    'mismatch_oldest': [('I', 'C')] + [('I', 'I')] * 11,
    'mismatch_latest': [('I', 'I')] * 11 + [('I', 'C')],
    'repeated_mismatch': [('I', 'I')] * 6 + [('I', 'C')] * 6,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def player_from_pairs(pairs):
    return {'my_history': [a for a, b in pairs], 'partner_history': [b for a, b in pairs],
            'outcome': [100 if a == b else -50 for a, b in pairs]}


def unique_mode(values):
    counts = Counter(values)
    winners = [x for x, n in counts.items() if n == max(counts.values())]
    return winners[0] if len(winners) == 1 else None


def add_case(rows, **fields):
    row = dict(parent_id=None, partner_label=None, **fields)
    row['id'] = digest(row)
    rows.append(row)
    return row


def make_cases(experiment, repeats=None, seed_base=20261008):
    if experiment not in DEFAULT_REPEATS:
        raise ValueError('unknown experiment')
    repeats = DEFAULT_REPEATS[experiment] if repeats is None else repeats
    if not isinstance(repeats, int) or isinstance(repeats, bool) or not 1 <= repeats <= 200:
        raise ValueError('repeats must be between 1 and 200')
    if not isinstance(seed_base, int) or isinstance(seed_base, bool) or not 0 <= seed_base <= 2147483447:
        raise ValueError('seed_base must be 0–2147483447')
    rows = []
    if experiment in ('replication', 'retention'):
        for history, challenger, pf, ef, repeat in itertools.product(
                HISTORIES if experiment == 'replication' else ('mismatch_latest',),
                ('dicfv', 'lwlsi'), ('I', 'C'), ('I', 'C'), range(repeats)):
            labels = {'C': challenger, 'I': 'lwlsi' if challenger == 'dicfv' else 'dicfv'}
            base = dict(experiment=experiment, repeat=repeat, seed=seed_base+repeat,
                        incumbent=labels['I'], challenger=challenger, history=history,
                        prompt_first=pf, enum_first=ef,
                        prompt_options=[labels[pf], labels['C' if pf == 'I' else 'I']],
                        enum_options=[labels[ef], labels['C' if ef == 'I' else 'I']])
            pairs = [(labels[a], labels[b]) for a, b in HISTORIES[history]]
            initial = add_case(rows, **base, player=player_from_pairs(pairs),
                               phase='initial', branch=None, step=0)
            if experiment == 'retention':
                initial['partner_label'] = challenger
                # Recompute ID after setting the actual current partner.
                initial['id'] = digest({k: v for k, v in initial.items() if k != 'id'})
                for branch in ('reinforced', 'reverted', 'alternating'):
                    parent = initial['id']
                    for step in range(1, 13):
                        partner = challenger if branch == 'reinforced' or (branch == 'alternating' and step % 2) else labels['I']
                        row = dict(**base, phase='followup', branch=branch, step=step,
                                   parent_id=parent, partner_label=partner, player=None)
                        row['id'] = digest(row)
                        rows.append(row)
                        parent = row['id']
        if experiment == 'replication':
            random.Random(seed_base).shuffle(rows)
        else:
            # Randomize initial-condition blocks while preserving each parent DAG.
            blocks = [rows[i:i+37] for i in range(0, len(rows), 37)]
            random.Random(seed_base).shuffle(blocks)
            rows = [row for block in blocks for row in block]
    else:
        for family, assignment, reverse, repeat in itertools.product(
                ('partner_recency', 'own_recency', 'frequency_recency'),
                itertools.permutations(('dicfv', 'lwlsi', 'ptqsu')), (False, True), range(repeats)):
            labels = dict(zip(('I', 'A', 'B'), assignment))
            counts = ['A'] * (8 if family == 'frequency_recency' else 6) + ['B'] * (4 if family == 'frequency_recency' else 6)
            pairs = [(x, 'I') if family == 'own_recency' else ('I', x) for x in counts]
            options = list(OPTIONS)
            rng_seed = int(digest([seed_base, repeat, family, assignment])[:16], 16)
            random.Random(rng_seed).shuffle(options)
            if reverse:
                options.reverse()
            for last in ('A', 'B'):
                changed = list(pairs)
                column = 0 if family == 'own_recency' else 1
                ix = next(i for i, pair in enumerate(changed) if pair[column] == last)
                changed[ix], changed[-1] = changed[-1], changed[ix]
                player = player_from_pairs([(labels[a], labels[b]) for a, b in changed])
                predictions = dict(own_last=player['my_history'][-1], partner_last=player['partner_history'][-1],
                                   own_mode=unique_mode(player['my_history']), partner_mode=unique_mode(player['partner_history']),
                                   combined_mode=unique_mode(player['my_history']+player['partner_history']), option_first=options[0])
                add_case(rows, experiment=experiment, repeat=repeat, seed=seed_base+repeat,
                         challenger=labels['B'], incumbent=labels['I'], labels=labels,
                         family=family, variant='last_'+last, reverse=reverse,
                         prompt_options=options.copy(), enum_options=options.copy(), player=player,
                         predictions=predictions, phase='initial', branch=None, step=0)
        random.Random(seed_base).shuffle(rows)
    return rows


def advance_player(parent):
    """Append the parent's observed decision and partner; prompt rendering applies the 12-encounter window."""
    if parent['status'] != 'valid':
        raise ValueError('invalid parent cannot generate a history')
    case = parent['case']
    player = case['player']
    pairs = list(zip(player['my_history'], player['partner_history']))
    pairs.append((parent['value'], case['partner_label']))
    return player_from_pairs(pairs)
