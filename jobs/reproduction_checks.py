#!/usr/bin/env python3
"""Bounded numerical checks of unchanged frozen response-function sources."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

MODELS = ('gemma4_31b', 'glm4_32b', 'olmo31_32b', 'qwen38_27b')
AUDIT = Path('specs/results-analysis/individual-decision-audit')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(root):
    import numpy as np
    import cffi
    import subprocess
    compiler = Path('/usr/bin/clang')
    if not compiler.is_file():
        raise RuntimeError('frozen engine requires /usr/bin/clang; install clang at that path; its sealed sources are not patched')
    subprocess.run([str(compiler), '--version'], check=True, capture_output=True)
    fit_dir = root / AUDIT / 'simplified-functions'
    sys.path.insert(0, str(fit_dir))
    fit = load('fit_simplified', fit_dir / 'fit_simplified.py')
    slices = load('reproduction_slices', root / '02_Topic/Thesis_Writing/development/04_Results/baseline_response_slices.py')
    engine_path = root / AUDIT / 'population-test/engine.py'
    engine = load('reproduction_engine', engine_path)
    errors = []
    values = 0
    max_difference = 0.0
    for model in MODELS:
        for program in ('emergence', 'cm'):
            for fold in range(5):
                bundle, beta, code, arg = engine.load_parameters(model, program, fold)
                options = bundle['options']
                alternative, incumbent = options[0], options[1]
                arrays, _ = slices.history_grid(options, program, alternative, incumbent)
                x, names = fit.basis(arrays, np.arange(13), program, 'FULL_VISIBLE')
                saved = next(f for f in bundle['outer_folds'] if f['outer_fold'] == fold)['candidate_models']['FULL_VISIBLE']
                if names != saved['feature_names']:
                    raise ValueError('saved visible feature names disagree')
                expected = fit.predict(x, saved)
                for row in range(13):
                    q = engine.scalar_probability(beta, code, arg, arrays['own_counts'][row], arrays['partner_counts'][row],
                        int(arrays['memory_size'][row]), int(arrays['lastown'][row]), int(arrays['lastpartner'][row]),
                        int(arrays['mismatch_streak'][row]), int(arrays['total_matches'][row]),
                        int(arrays['own_round'][row]), int(arrays['prepared_remaining'][row]), arrays['positions'][row])
                    difference = float(np.max(np.abs(q - expected[row])))
                    max_difference = max(max_difference, difference)
                    if not np.isfinite(q).all() or not np.allclose(q, expected[row], rtol=1e-10, atol=1e-12):
                        errors.append((model, program, fold, row, difference))
                    values += len(q)
    if errors:
        raise AssertionError(f'C/Python FULL_VISIBLE mismatch: {errors[:3]}')
    # Exercise the actual compiled trajectory and metric backend, with a bounded
    # synthetic schedule. This is a numerical backend test, not a new LLM run.
    _, beta, code, arg = engine.load_parameters(MODELS[0], 'cm', 0)
    players = np.tile(np.array([[0, 1]], dtype=np.uint8), (144, 1))
    positions = np.tile(np.arange(2, dtype=np.uint8), (144, 2, 1))
    draws = np.full((2, 144, 2), .5)
    answers = engine.simulate(players, positions, [2, 3, 4, 5, 6], 0, 1, beta, code, arg, draws)
    if answers.shape != (2, 144, 2) or not np.isin(answers, [0, 1]).all():
        raise AssertionError('compiled population backend returned invalid bounded trajectory')
    adjacency = np.ones((48, 48), dtype=np.uint8) - np.eye(48, dtype=np.uint8)
    config = dict(options=['incumbent', 'challenger'], committed_ids=[2, 3, 4, 5, 6], target_index=1, adjacency=adjacency)
    trajectory, summary = engine.calculate_metrics(answers[0], players, config, checkpoints=[144])
    if trajectory.shape != (1, len(engine.TRAJECTORY_METRICS)) or summary.shape != (16,):
        raise AssertionError('compiled metric backend returned invalid shape')
    for value in [summary[0], summary[3], summary[4]]:
        if not np.isfinite(value) or not 0 <= value <= 1:
            raise AssertionError('compiled gate/success/dominance metric outside bounds')
    # The earlier role-conditioned fits are a distinct fit set. Exercise their
    # own saved API rather than treating the visible-only baseline as a proxy.
    initial = load('reproduction_initial', root / AUDIT / 'fitted-functions/response_function.py')
    initial_cases = 0
    for model in MODELS:
        for program in ('emergence', 'cm'):
            parameter = root / AUDIT / f'fitted-functions/parameters-{model}-{program}.json'
            options = json.loads(parameter.read_text())['options']
            incumbent, target = options[0], options[1]
            history = dict(my_history=[], partner_history=[], outcome=[])
            if program == 'cm':
                history = dict(my_history=[incumbent]*12, partner_history=[incumbent]*12,
                               outcome=[100]*12, committed_to=target)
            for variant, topology in [('pooled', None)] + [(v, t) for v in ('topology_delta', 'separate_topology') for t in initial.TOPOS]:
                probabilities = initial.predict_next_choice(parameter, history, options, variant, topology)
                values_array = np.asarray(list(probabilities.values()))
                if not np.isfinite(values_array).all() or (values_array < 0).any() or not np.isclose(values_array.sum(), 1):
                    raise AssertionError('initial fitted-choice API probability bounds failed')
                initial_cases += 1
    # Check saved first-return hazards as probabilities and their survival curve.
    hazard = load('reproduction_hazard', root / AUDIT / 'fitted-adoption/response_function.py')
    features = dict(target_lwlsi=0, own_target_frequency=.25, partner_target_frequency=.5,
                    last_partner_target=1, mismatch_fraction=.5, mismatch_streak_fraction=.25,
                    log_player_round=float(np.log(25)), synthetic_remaining=0)
    hazard_cases = 0
    for model in MODELS:
        survival = [hazard.predict_retention(root / AUDIT / 'fitted-adoption/functions.json', model, features, h) for h in range(1, 13)]
        if not all(np.isfinite(p) and 0 <= p <= 1 for p in survival) or any(a < b - 1e-12 for a, b in zip(survival, survival[1:])):
            raise AssertionError('saved first-return hazard violates survival bounds')
        hazard_cases += len(survival)
    return dict(status='PASS', visible_probability_values=values, c_python_max_absolute_difference=max_difference,
                population_backend_replicas=2, population_backend_interactions=144, initial_fitted_function_cases=initial_cases, hazard_probabilities=hazard_cases,
                engine_sha256=hashlib.sha256(engine_path.read_bytes()).hexdigest(), cffi=cffi.__version__,
                actual_compiler=str(compiler), source_modified=False, refits=0, llm_requests=0,
                scope='bounded backend and frozen-function checks; not a rerun of the full population study')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="thesis-cffi-check-") as cache:
            original_cache = tempfile.tempdir
            tempfile.tempdir = cache
            try:
                result = check(args.package_root.resolve())
                result["fresh_compiler_cache"] = True
            finally:
                tempfile.tempdir = original_cache
    except Exception as error:
        parser.exit(2, f'ERROR: {type(error).__name__}: {error}\n')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
