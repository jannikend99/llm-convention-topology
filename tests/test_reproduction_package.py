"""The publication snapshot must contain real bytes and fail closed on races."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'jobs/build_reproduction_package.py'
spec = importlib.util.spec_from_file_location('publication_builder', MODULE)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class ReproductionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'project'
        self.repo = self.root / builder.EXPERIMENT
        (self.repo / 'jobs').mkdir(parents=True)
        (self.repo / 'config.yaml').write_text('campaign: experiment\n')
        (self.repo / 'HANDOVER.md').write_text('Read the reproduction instructions.\n')
        self.new_runner = self.repo / 'jobs/new_runner.py'
        self.new_runner.write_text('print("real runner")\n')
        (self.root / 'analysis').mkdir()
        (self.root / 'analysis/fit.json').write_text('{"coefficient": 0.5}\n')
        self.chapter = self.root / 'chapter.tex'
        self.chapter.write_text('A recorded manuscript state.\n')
        self.selection = {
            'include': [builder.EXPERIMENT + '/jobs/new_runner.py', 'analysis/*.json'],
            'exclude': [],
            'required_files': [builder.EXPERIMENT + '/jobs/new_runner.py', 'README.md'],
            'copy_files': {'README.md': builder.EXPERIMENT + '/HANDOVER.md'},
            'manuscript_bindings': ['chapter.tex'],
            'rights_exceptions': [],
        }
        self.selection_path = self.root / 'selection.json'
        self.archive = self.base / 'snapshot.tar.gz'
        self.calls = patch.object(builder.subprocess, 'check_output', side_effect=self.git_output)
        self.calls.start()
        self.addCleanup(self.calls.stop)

    @staticmethod
    def git_output(command, **kwargs):
        if 'ls-files' in command:
            return b'config.yaml\0HANDOVER.md\0'
        if 'rev-parse' in command:
            return '1234567890abcdef\n'
        raise AssertionError(f'unexpected Git command: {command}')

    def freeze(self):
        self.selection_path.write_text(json.dumps(self.selection))
        return builder.freeze(self.root, self.selection_path, self.archive)

    def test_untracked_runner_and_entry_copy_have_verified_archive_bytes(self):
        result = self.freeze()
        rows = result['source_manifest']['files']
        by_path = {row['path']: row for row in rows}
        self.assertIn(builder.EXPERIMENT + '/jobs/new_runner.py', by_path)
        self.assertIn('README.md', by_path)
        self.assertEqual(by_path['README.md']['sha256'], hashlib.sha256((self.repo / 'HANDOVER.md').read_bytes()).hexdigest())
        with tarfile.open(self.archive) as archive:
            regular = {m.name: m for m in archive.getmembers() if m.isfile()}
            self.assertEqual(len(regular), len(rows) + 1)
            embedded = json.loads(archive.extractfile('thesis-reproduction/SOURCE_MANIFEST.json').read())
            self.assertEqual(embedded, result['source_manifest'])
            for row in rows:
                member = regular['thesis-reproduction/' + row['path']]
                payload = archive.extractfile(member).read()
                self.assertEqual(len(payload), row['size'])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), row['sha256'])
        self.assertEqual(result['archive_sha256'], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertFalse(self.archive.with_name(self.archive.name + '.partial').exists())

    def test_required_dependency_cannot_be_omitted(self):
        self.selection['required_files'].append('analysis/missing.csv')
        with self.assertRaisesRegex(FileNotFoundError, 'required packaged'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_unsafe_selection_or_copy_paths_are_rejected(self):
        for value in ('../outside', '/absolute/file', 'dir\\outside', ''):
            with self.subTest(path=value), self.assertRaises(ValueError):
                builder.safe_relative(value)
        self.selection['copy_files']['../escaped.md'] = builder.EXPERIMENT + '/HANDOVER.md'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_copy_source_cannot_escape_project(self):
        self.selection['copy_files']['README.md'] = '../outside.md'
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_leaf_and_ancestor_symlinks_are_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'asset.json').write_text('{"outside": true}')
        leaf = self.root / 'analysis/linked.json'
        leaf.symlink_to(outside / 'asset.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.freeze()
        leaf.unlink()
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        self.selection['include'].append('linked/asset.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_existing_archive_or_sidecar_is_not_overwritten(self):
        self.archive.write_bytes(b'preserve archive')
        with self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual(self.archive.read_bytes(), b'preserve archive')
        other = self.base / 'other.tar.gz'
        self.archive = other
        sidecar = other.with_name(other.name + '.json')
        sidecar.write_text('preserve sidecar')
        with self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual(sidecar.read_text(), 'preserve sidecar')
        self.assertFalse(other.exists())

    def mutate_during_read(self, mutation):
        original = builder.HashReader.read
        changed = False
        def reading(reader, size=-1):
            nonlocal changed
            data = original(reader, size)
            if data and not changed:
                changed = True
                mutation(Path(reader.handle.name))
            return data
        return patch.object(builder.HashReader, 'read', reading)

    def test_source_mutation_during_stream_aborts_snapshot(self):
        def mutate(path):
            with path.open('a') as stream:
                stream.write('changed during packaging')
        with self.mutate_during_read(mutate), self.assertRaisesRegex(RuntimeError, 'input changed'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_new_glob_input_during_stream_aborts_snapshot(self):
        with self.mutate_during_read(lambda _: (self.root / 'analysis/new.json').write_text('{}')), self.assertRaisesRegex(RuntimeError, 'selection changed'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_manuscript_mutation_during_stream_aborts_snapshot(self):
        with self.mutate_during_read(lambda _: self.chapter.write_text('A later manuscript state.')), self.assertRaisesRegex(RuntimeError, 'manuscript changed'):
            self.freeze()
        self.assertFalse(self.archive.exists())

    def test_competing_archive_creation_is_not_replaced(self):
        link = builder.os.link
        def compete(source, destination):
            Path(destination).write_bytes(b'concurrent owner')
            return link(source, destination)
        with patch.object(builder.os, 'link', side_effect=compete), self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual(self.archive.read_bytes(), b'concurrent owner')

    def test_manifest_name_is_reserved(self):
        self.selection['copy_files']['SOURCE_MANIFEST.json'] = builder.EXPERIMENT + '/HANDOVER.md'
        with self.assertRaisesRegex(ValueError, 'reserved'):
            self.freeze()
        self.assertFalse(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
