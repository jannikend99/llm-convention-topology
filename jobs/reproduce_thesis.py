#!/usr/bin/env python3
"""Run real analysis producers in a fresh isolated copy of a restored package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
import os
import re
import unicodedata
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time

CODE = Path('02_Topic/Experiment_Code/llm-convention-topology')
RAW = CODE / 'data/runs/experiment'
REGISTRY = Path(__file__).with_name('reproduction-stages.json')
REQUIRED_IMPORTS = ('numpy', 'pandas', 'scipy', 'statsmodels', 'matplotlib', 'networkx', 'yaml', 'pypdf', 'cffi')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe manifest path: ' + value)
    return path


def source_manifest(root):
    root = Path(root).resolve()
    if (root / '.git').exists() or (root / CODE / '.git').exists():
        raise ValueError('refusing to run producers in a Git authoring checkout; restore the checked package first')
    path = root / 'SOURCE_MANIFEST.json'
    if not path.is_file():
        raise ValueError('SOURCE_MANIFEST.json is required; this is not a restored package')
    manifest = json.loads(path.read_text())
    if not manifest.get('files'):
        raise ValueError('source manifest has no file hashes')
    return manifest


def integrity(root, manifest):
    missing, changed = [], []
    seen = set()
    for row in manifest['files']:
        name = str(relative(row['path']))
        if name in seen:
            raise ValueError('duplicate manifest path: ' + name)
        seen.add(name)
        path = root / name
        if not path.is_file() or path.is_symlink():
            missing.append(name)
        elif path.stat().st_size != row['size'] or sha256(path) != row['sha256']:
            changed.append(name)
    if missing or changed:
        raise ValueError(f'source integrity failed: missing={missing[:5]}, changed={changed[:5]}')
    return {'files': len(seen), 'status': 'PASS'}


def doctor(args):
    errors = []
    for name in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(name)
            print(f'{name}={getattr(module, "__version__", "imported")}')
        except Exception as error:
            errors.append(f'{name}: {type(error).__name__}: {error}')
    if not Path('/usr/bin/clang').is_file():
        errors.append('frozen engine requires /usr/bin/clang; a different compiler on PATH is insufficient')
    if errors:
        raise RuntimeError('; '.join(errors))
    check = Path(__file__).with_name('reproduction_checks.py')
    result = subprocess.run([sys.executable, str(check), '--package-root', str(Path(args.package_root).resolve())], text=True)
    if result.returncode:
        raise RuntimeError('actual frozen-function/CFFI compile-execution check failed')
    return 0


def atom_equal(expected, actual, rtol=1e-9, atol=1e-11):
    if expected == actual:
        return True
    try:
        a, b = float(expected), float(actual)
    except (ValueError, TypeError):
        return False
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)


def compare_csv(expected, actual):
    with expected.open(newline='') as left, actual.open(newline='') as right:
        a, b = csv.reader(left), csv.reader(right)
        count = 0
        for row_a, row_b in __import__('itertools').zip_longest(a, b):
            if row_a is None or row_b is None or len(row_a) != len(row_b):
                raise AssertionError(f'CSV row/schema mismatch: {expected.name} row{count}')
            if not all(atom_equal(x, y) for x, y in zip(row_a, row_b)):
                raise AssertionError(f'CSV value mismatch: {expected.name} row{count}')
            count += 1
    return {'kind': 'csv', 'rows_including_header': count, 'rtol': 1e-9, 'atol': 1e-11}


def compare_json(expected, actual):
    def same(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        return atom_equal(a, b)
    if not same(json.loads(expected.read_text()), json.loads(actual.read_text())):
        raise AssertionError('JSON scientific-value mismatch: ' + expected.name)
    return {'kind': 'json', 'rtol': 1e-9, 'atol': 1e-11}


def pdf_text(value):
    value = unicodedata.normalize('NFKC', value).replace('−', '-')
    # PDF font maps can omit an interword en dash. Do not remove numeric signs.
    value = re.sub(r'(?<=[^\W\d_])[-‐‑‒–—](?=[^\W\d_])', ' ', value)
    return ' '.join(value.split())


def compare_pdf(expected, actual):
    from pypdf import PdfReader
    left, right = PdfReader(expected), PdfReader(actual)
    if len(left.pages) != len(right.pages):
        raise AssertionError('PDF page-count mismatch: ' + expected.name)
    for a, b in zip(left.pages, right.pages):
        if not all(atom_equal(x, y) for x, y in zip(a.mediabox, b.mediabox)):
            raise AssertionError('PDF page-size mismatch: ' + expected.name)
        if pdf_text(a.extract_text() or '') != pdf_text(b.extract_text() or ''):
            raise AssertionError('PDF displayed-text mismatch: ' + expected.name)
    return {'kind': 'pdf', 'pages': len(left.pages),
            'scope': 'page count, size and displayed text after Unicode/interword-dash normalization (numeric signs preserved); numeric outputs checked separately; not pixel identity'}


def comparison(expected, actual):
    if not actual.is_file():
        raise FileNotFoundError('producer did not create required output: ' + str(actual))
    if expected.suffix == '.csv':
        return compare_csv(expected, actual)
    if expected.suffix == '.json':
        return compare_json(expected, actual)
    if expected.suffix == '.pdf':
        return compare_pdf(expected, actual)
    if sha256(expected) != sha256(actual):
        raise AssertionError('output byte mismatch: ' + expected.name)
    return {'kind': 'byte-identical'}


def create_workspace(package, destination, manifest, raw_data=None):
    package, destination = package.resolve(), destination.resolve()
    raw_source = Path(raw_data).resolve() if raw_data else (package / RAW).resolve()
    if destination == raw_source or raw_source in destination.parents:
        raise ValueError('work directory must be outside the raw input tree')
    if destination == package or package in destination.parents:
        raise ValueError('work directory must be outside the immutable restored package')
    if any((parent / '.git').exists() for parent in [destination, *destination.parents]):
        raise ValueError('work directory must be outside authoring Git checkouts')
    if destination.exists():
        raise FileExistsError('work directory must not exist: ' + str(destination))
    destination.mkdir(parents=True)
    for row in manifest['files']:
        name = relative(row['path'])
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package / name, target)
        if sha256(target) != row['sha256']:
            raise RuntimeError('source changed while copying: ' + str(name))
    shutil.copyfile(package / 'SOURCE_MANIFEST.json', destination / 'SOURCE_MANIFEST.json')
    if raw_source.is_dir():
        target = destination / RAW
        target.parent.mkdir(parents=True, exist_ok=True)
        if raw_source.stat().st_dev != destination.stat().st_dev:
            raise ValueError('raw inputs and work directory must share a filesystem for zero-copy hardlinks; choose a work directory on the input filesystem')
        target.mkdir()
        for source in sorted(raw_source.rglob('*')):
            if source.is_symlink():
                raise ValueError('raw input tree must contain regular files, not symlinks')
            local = target / source.relative_to(raw_source)
            if source.is_dir():
                local.mkdir(exist_ok=True)
            elif source.is_file():
                local.parent.mkdir(parents=True, exist_ok=True)
                os.link(source, local)
    return destination


def run_stages(args):
    package = Path(args.package_root).resolve()
    manifest = source_manifest(package)
    integrity(package, manifest)
    registry = json.loads(REGISTRY.read_text())
    wanted = args.stage or registry['default_' + args.command]
    by_id = {stage['id']: stage for stage in registry['stages']}
    if any(name not in by_id for name in wanted):
        raise ValueError('unknown stage; use list to inspect the explicit stage map')
    selected = [by_id[name] for name in wanted]
    if any(stage.get('raw_required') for stage in selected):
        data = Path(args.raw_data).resolve() if args.raw_data else package / RAW
        if not data.is_dir() or not (data / 'graphs.json').is_file():
            raise FileNotFoundError('complete raw campaign is required; extract the separate data archive or supply --raw-data for a read-only existing campaign')
    work = create_workspace(package, Path(args.work_dir), manifest, args.raw_data)
    logs = work / 'reproduction-logs'; logs.mkdir()
    result = {'source_snapshot_sha256': manifest['snapshot_sha256'], 'python': sys.version.split()[0],
              'package_root': str(package), 'working_copy': str(work),
              'raw_data_mode': 'zero-copy hardlinks on the input filesystem; included analysis producers only read campaign files; not a write sandbox',
              'stages': [], 'costly_refits_executed': False, 'llm_requests': 0, 'canonical_figures': []}
    try:
        for stage in selected:
            # Remove only declared outputs inside the fresh disposable work copy.
            # Otherwise a no-op producer could appear to reproduce a supplied file.
            for name in dict.fromkeys(stage.get('compare_outputs', []) + stage.get('required_outputs', [])):
                output_relative = Path(relative(name))
                if output_relative == RAW or RAW in output_relative.parents:
                    raise ValueError('declared output escapes permitted write scope: raw campaign is input-only')
                path = work / output_relative
                if work not in path.resolve().parents:
                    raise ValueError('declared output escapes the isolated workspace: ' + name)
                if path.exists():
                    path.unlink()
            command = [sys.executable, str(work / relative(stage['script']))]
            command += [value.replace('{ROOT}', str(work)) for value in stage.get('args', [])]
            started = time.monotonic()
            process = subprocess.run(command, cwd=work, capture_output=True, text=True,
                                     env={**os.environ, 'MPLBACKEND': 'Agg'})
            (logs / (stage['id'] + '.log')).write_text('$ ' + repr(command) + '\n' + process.stdout + process.stderr)
            entry = {'id': stage['id'], 'command': command, 'exit_code': process.returncode,
                     'runtime_seconds': round(time.monotonic() - started, 3), 'comparisons': []}
            result['stages'].append(entry)
            if process.returncode:
                raise RuntimeError(f'producer failed: {stage["id"]}; see {logs / (stage["id"] + ".log")}')
            for name in stage.get('compare_outputs', []):
                baseline = package / relative(name)
                if not baseline.is_file():
                    raise FileNotFoundError('frozen comparison output absent: ' + name)
                checked = comparison(baseline, work / name)
                entry['comparisons'].append({'path': name, 'reference_sha256': sha256(baseline), 'generated_sha256': sha256(work / name), **checked})
            for name in stage.get('required_outputs', []):
                if not (work / relative(name)).is_file():
                    raise FileNotFoundError('stage did not write required result: ' + name)
            for generated, retained in stage.get('canonical_figures', {}).items():
                if generated not in stage.get('compare_outputs', []):
                    raise ValueError('canonical figure must have an explicit comparison: ' + generated)
                checked = comparison(package / relative(retained), work / relative(generated))
                destination = work / 'reproduced-figures' / Path(retained).name
                if destination.exists():
                    raise ValueError('duplicate canonical figure destination: ' + retained)
                destination.parent.mkdir(exist_ok=True)
                shutil.copyfile(work / generated, destination)
                result['canonical_figures'].append({'retained': retained, 'producer_stage': stage['id'],
                    'generated': generated, 'result': str(destination.relative_to(work)),
                    'sha256': sha256(destination), 'comparison': checked})
            entry['status'] = 'PASS'
        complete = set(registry['default_report']).issubset(wanted)
        if complete:
            expected_figures = {row['figure'] for row in registry.get('manuscript_figure_map', [])}
            if {row['retained'] for row in result['canonical_figures']} != expected_figures:
                raise AssertionError('the final canonical figure set is incomplete')
        result['complete_retained_project_figure_set'] = complete
        integrity(package, manifest)
        result['status'] = 'PASS'
    except Exception as error:
        result['status'] = 'FAIL'; result['error'] = f'{type(error).__name__}: {error}'
        (work / 'reproduction-report.json').write_text(json.dumps(result, indent=2) + '\n')
        raise
    (work / 'reproduction-report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    quick = sub.add_parser('doctor'); quick.add_argument('--package-root', required=True)
    check = sub.add_parser('integrity'); check.add_argument('--package-root', required=True)
    sub.add_parser('list')
    for mode in ('report', 'reconstruct'):
        command = sub.add_parser(mode)
        command.add_argument('--package-root', required=True)
        command.add_argument('--work-dir', required=True)
        command.add_argument('--raw-data')
        command.add_argument('--stage', action='append')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            print(REGISTRY.read_text()); return 0
        if args.command == 'doctor':
            return doctor(args)
        if args.command == 'integrity':
            root = Path(args.package_root).resolve()
            print(json.dumps(integrity(root, source_manifest(root)), indent=2)); return 0
        return run_stages(args)
    except Exception as error:
        parser.exit(2, f'ERROR: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
