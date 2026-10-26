"""Publication producers must execute in disposable, verified workspaces."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'jobs/reproduce_thesis.py'
spec = importlib.util.spec_from_file_location('publication_runner', MODULE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ReproductionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.package = self.base / 'package'
        (self.package / 'analysis').mkdir(parents=True)
        self.producer = self.package / 'analysis/produce.py'
        self.producer.write_text('from pathlib import Path\nPath("analysis/result.csv").write_text("value\\n1.0\\n")\n')
        (self.package / 'analysis/result.csv').write_text('value\n1.0\n')
        (self.package / 'analysis/required.txt').write_text('supplied baseline\n')
        self.registry = self.base / 'registry.json'
        self.stage = {
            'id': 'quantitative', 'script': 'analysis/produce.py',
            'compare_outputs': ['analysis/result.csv'], 'required_outputs': [],
        }
        self.registry.write_text(json.dumps({
            'default_report': ['quantitative'], 'default_reconstruct': ['quantitative'],
            'stages': [self.stage],
        }))
        self.manifest = self.write_manifest()
        self.args = SimpleNamespace(
            package_root=str(self.package), command='report', stage=None,
            work_dir=str(self.base / 'work'), raw_data=None,
        )
        self.registry_patch = patch.object(runner, 'REGISTRY', self.registry)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def write_manifest(self):
        rows = []
        for path in sorted(self.package.rglob('*')):
            if path.is_file() and path.name != 'SOURCE_MANIFEST.json':
                payload = path.read_bytes()
                rows.append({'path': path.relative_to(self.package).as_posix(), 'size': len(payload),
                             'sha256': hashlib.sha256(payload).hexdigest()})
        manifest = {'files': rows, 'snapshot_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
        (self.package / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
        return manifest

    def update_stage(self):
        self.registry.write_text(json.dumps({
            'default_report': ['quantitative'], 'default_reconstruct': ['quantitative'],
            'stages': [self.stage],
        }))

    def run_stage(self):
        with redirect_stdout(StringIO()):
            return runner.run_stages(self.args)

    def test_missing_source_manifest_is_rejected(self):
        (self.package / 'SOURCE_MANIFEST.json').unlink()
        with self.assertRaisesRegex(ValueError, 'SOURCE_MANIFEST.json'):
            runner.source_manifest(self.package)

    def test_authoring_root_and_experiment_git_markers_are_rejected(self):
        for marker in (self.package / '.git', self.package / runner.CODE / '.git'):
            with self.subTest(marker=marker):
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text('authoring marker')
                with self.assertRaisesRegex(ValueError, 'authoring checkout'):
                    runner.source_manifest(self.package)
                marker.unlink()

    def test_work_directory_must_be_new_and_outside_package(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            runner.create_workspace(self.package, self.package / 'work', self.manifest)
        existing = self.base / 'existing'
        existing.mkdir()
        with self.assertRaises(FileExistsError):
            runner.create_workspace(self.package, existing, self.manifest)
        self.assertEqual(list(existing.iterdir()), [])

    def test_work_directory_cannot_equal_or_enter_raw_input_before_writes(self):
        raw = self.base / 'raw-input'
        raw.mkdir()
        sentinel = raw / 'graphs.json'
        sentinel.write_text('{"preserve": true}\n')
        original_raw = {p.relative_to(raw): p.read_bytes() for p in raw.rglob('*') if p.is_file()}
        original_package = {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob('*') if p.is_file()}
        for destination in (raw, raw / 'nested' / 'work'):
            with self.subTest(destination=destination), patch.object(runner.shutil, 'copyfile') as copy, patch.object(runner.os, 'link') as link:
                with self.assertRaisesRegex(ValueError, 'outside the raw input tree'):
                    runner.create_workspace(self.package, destination, self.manifest, str(raw))
                copy.assert_not_called()
                link.assert_not_called()
            self.assertFalse((raw / 'nested').exists())
            self.assertEqual(original_raw, {p.relative_to(raw): p.read_bytes() for p in raw.rglob('*') if p.is_file()})
            self.assertEqual(original_package, {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob('*') if p.is_file()})

    def test_raw_input_alias_is_resolved_before_work_directory_check(self):
        raw = self.base / 'raw-input'
        raw.mkdir()
        sentinel = raw / 'graphs.json'
        sentinel.write_text('{"preserve": true}\n')
        alias = self.base / 'raw-alias'
        alias.symlink_to(raw, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'outside the raw input tree'):
            runner.create_workspace(self.package, alias / 'nested' / 'work', self.manifest, str(alias))
        self.assertFalse((raw / 'nested').exists())
        self.assertEqual(sentinel.read_text(), '{"preserve": true}\n')

    def test_separate_raw_input_keeps_zero_copy_hardlink_mode(self):
        raw = self.base / 'raw-input'
        raw.mkdir()
        sentinel = raw / 'graphs.json'
        sentinel.write_text('{"preserve": true}\n')
        destination = self.base / 'legitimate-work'
        runner.create_workspace(self.package, destination, self.manifest, str(raw))
        linked = destination / runner.RAW / 'graphs.json'
        self.assertEqual(linked.read_bytes(), sentinel.read_bytes())
        self.assertEqual(linked.stat().st_ino, sentinel.stat().st_ino)
        self.assertEqual(linked.stat().st_dev, sentinel.stat().st_dev)
        self.assertEqual(sorted(p.name for p in raw.iterdir()), ['graphs.json'])

    def test_work_directory_cannot_be_inside_an_authoring_checkout(self):
        authoring = self.base / 'authoring'
        (authoring / '.git').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'authoring Git'):
            runner.create_workspace(self.package, authoring / 'work', self.manifest)
        self.assertFalse((authoring / 'work').exists())

    def test_mutated_frozen_input_is_rejected_before_execution(self):
        self.producer.write_text('raise RuntimeError("mutated")\n')
        with self.assertRaisesRegex(ValueError, 'integrity failed'):
            self.run_stage()
        self.assertFalse(Path(self.args.work_dir).exists())

    def test_unknown_stage_is_rejected_without_creating_workspace(self):
        self.args.stage = ['not-declared']
        with self.assertRaisesRegex(ValueError, 'unknown stage'):
            self.run_stage()
        self.assertFalse(Path(self.args.work_dir).exists())

    def test_success_runs_the_producer_and_preserves_the_input_package(self):
        original = {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob('*') if p.is_file()}
        self.assertEqual(self.run_stage(), 0)
        work = Path(self.args.work_dir)
        report = json.loads((work / 'reproduction-report.json').read_text())
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['stages'][0]['exit_code'], 0)
        self.assertEqual(report['stages'][0]['comparisons'][0]['kind'], 'csv')
        self.assertEqual((work / 'analysis/result.csv').read_text(), 'value\n1.0\n')
        self.assertEqual(original, {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob('*') if p.is_file()})

    def test_failing_producer_has_nonzero_status_and_failure_evidence(self):
        self.producer.write_text('raise SystemExit(7)\n')
        self.write_manifest()
        with self.assertRaisesRegex(RuntimeError, 'producer failed'):
            self.run_stage()
        report = json.loads((Path(self.args.work_dir) / 'reproduction-report.json').read_text())
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['stages'][0]['exit_code'], 7)
        self.assertNotIn('status', report['stages'][0])

    def test_noop_producer_cannot_reuse_supplied_comparison_output(self):
        self.producer.write_text('pass\n')
        self.write_manifest()
        with self.assertRaisesRegex(FileNotFoundError, 'did not create required output'):
            self.run_stage()
        self.assertFalse((Path(self.args.work_dir) / 'analysis/result.csv').exists())

    def test_noop_producer_cannot_reuse_supplied_required_output(self):
        self.producer.write_text('pass\n')
        self.write_manifest()
        self.stage['compare_outputs'] = []
        self.stage['required_outputs'] = ['analysis/required.txt']
        self.update_stage()
        with self.assertRaisesRegex(FileNotFoundError, 'required|result'):
            self.run_stage()
        self.assertFalse((Path(self.args.work_dir) / 'analysis/required.txt').exists())

    def test_declared_output_cannot_delete_a_readonly_raw_symlink_target(self):
        raw = self.base / 'raw'
        raw.mkdir()
        sentinel = raw / 'graphs.json'
        sentinel.write_text('{"preserve": true}\n')
        self.args.raw_data = str(raw)
        self.stage['compare_outputs'] = [str(runner.RAW / 'graphs.json')]
        self.update_stage()
        with self.assertRaises(ValueError):
            self.run_stage()
        self.assertEqual(sentinel.read_text(), '{"preserve": true}\n')


class NumericalComparisonTests(unittest.TestCase):
    def test_pdf_text_normalizes_only_interword_dash_separators(self):
        for label in ('Watts–Strogatz', 'Watts—Strogatz', 'Watts-Strogatz'):
            with self.subTest(label=label):
                self.assertEqual(runner.pdf_text(label), runner.pdf_text('Watts Strogatz'))

    def test_pdf_text_preserves_numeric_signs_and_csv_rejects_sign_changes(self):
        for value in ('-0.5', '−0.5'):
            with self.subTest(value=value):
                self.assertEqual(runner.pdf_text(value), '-0.5')
                self.assertNotEqual(runner.pdf_text(value), runner.pdf_text('0.5'))
        with TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'expected.csv'
            actual = Path(tmp) / 'actual.csv'
            expected.write_text('mean\n-0.5\n')
            actual.write_text('mean\n0.5\n')
            with self.assertRaisesRegex(AssertionError, 'CSV value mismatch'):
                runner.compare_csv(expected, actual)

    def test_numeric_tolerance_and_nan_semantics(self):
        for a, b in [('1.0', '1.0000000001'), ('NaN', 'nan'), ('', '')]:
            with self.subTest(expected=a, actual=b):
                self.assertTrue(runner.atom_equal(a, b))
        for a, b in [('NaN', '0'), ('', 'nan'), ('1.0', '1.01'), ('name-a', 'name-b')]:
            with self.subTest(expected=a, actual=b):
                self.assertFalse(runner.atom_equal(a, b))

    def test_csv_accepts_only_matching_values_and_shape(self):
        with TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'expected.csv'
            actual = Path(tmp) / 'actual.csv'
            expected.write_text('value,undefined\n1.0,NaN\n')
            actual.write_text('value,undefined\n1.0000000001,nan\n')
            self.assertEqual(runner.compare_csv(expected, actual)['rows_including_header'], 2)
            for payload in ('value,undefined\n2.0,nan\n', 'value,undefined\n1.0,0\n', 'value,undefined\n'):
                with self.subTest(payload=payload):
                    actual.write_text(payload)
                    with self.assertRaises(AssertionError):
                        runner.compare_csv(expected, actual)


if __name__ == '__main__':
    unittest.main()
