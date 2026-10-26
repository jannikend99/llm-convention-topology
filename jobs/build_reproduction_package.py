#!/usr/bin/env python3
"""Freeze a standalone research snapshot without changing its authoring inputs."""
from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile

EXPERIMENT = '02_Topic/Experiment_Code/llm-convention-topology'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or '\\' in value or '\x00' in value:
        raise ValueError(f'unsafe relative path: {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'unsafe relative path: {value}')
    return path.as_posix()


def source_path(root, relative):
    """Keep selected source files inside the workspace without following links."""
    relative = safe_relative(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'symlink source is not allowed: {relative}')
    if not path.resolve(strict=True).is_relative_to(root):
        raise ValueError(f'source escapes project root: {relative}')
    if not path.is_file():
        raise ValueError(f'only regular source files are allowed: {relative}')
    return path


def excluded(relative, patterns):
    parts = PurePosixPath(relative).parts
    if any(part in {'.git', '.venv', '__pycache__', '.pytest_cache', 'graphify-out'} for part in parts):
        return True
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def collect(root, selection):
    files = {}
    repo = root / EXPERIMENT
    tracked = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z']).decode().split('\0')
    for name in filter(None, tracked):
        relative = f'{EXPERIMENT}/{safe_relative(name)}'
        if not excluded(relative, selection['exclude']):
            files[relative] = source_path(root, relative)
    for pattern in selection['include']:
        safe_relative(pattern)
        matched = [path for path in root.glob(pattern) if path.is_file()]
        if not matched and not any(c in pattern for c in '*?['):
            raise FileNotFoundError(f'required input not found: {pattern}')
        for path in matched:
            relative = path.relative_to(root).as_posix()
            if not excluded(relative, selection['exclude']):
                files[relative] = source_path(root, relative)
    for destination, source in selection.get('copy_files', {}).items():
        destination = safe_relative(destination)
        source = safe_relative(source)
        if destination == 'SOURCE_MANIFEST.json':
            raise ValueError('SOURCE_MANIFEST.json is reserved for generated metadata')
        if excluded(destination, selection['exclude']) or excluded(source, selection['exclude']):
            raise ValueError(f'excluded copy source or destination: {destination}')
        path = source_path(root, source)
        if destination in files and files[destination] != path:
            raise ValueError(f'copy destination collides with another selected source: {destination}')
        files[destination] = path
    if 'SOURCE_MANIFEST.json' in files:
        raise ValueError('SOURCE_MANIFEST.json is reserved for generated metadata')
    for relative in selection['required_files']:
        relative = safe_relative(relative)
        if relative not in files:
            raise FileNotFoundError(f'required packaged source/input omitted: {relative}')
    return dict(sorted(files.items()))


def stamp(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def descriptor_stamp(handle):
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('selected source descriptor is not a regular file')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def bindings(root, patterns):
    result = []
    for pattern in patterns:
        safe_relative(pattern)
        matches = sorted(root.glob(pattern))
        if not matches and not any(c in pattern for c in '*?['):
            raise FileNotFoundError(f'manuscript binding not found: {pattern}')
        for path in matches:
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                path = source_path(root, relative)
                before = stamp(path)
                digest = sha256(path)
                if stamp(path) != before:
                    raise RuntimeError(f'manuscript changed while hashing: {relative}')
                result.append({'path': relative, 'size': before[2], 'sha256': digest})
    return result


class HashReader:
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()
    def read(self, size=-1):
        data = self.handle.read(size)
        self.digest.update(data)
        return data


def freeze(root, selection_path, archive):
    root = Path(root).resolve()
    selection_path = Path(selection_path).resolve()
    archive = Path(archive).resolve()
    if not root.is_dir() or not (root / EXPERIMENT).is_dir():
        raise ValueError('project root must contain the experiment repository at its established relative path')
    sidecar_path = archive.with_name(archive.name + '.json')
    if archive.exists():
        raise FileExistsError(f'refusing to overwrite archive: {archive}')
    if sidecar_path.exists():
        raise FileExistsError(f'refusing to overwrite archive sidecar: {sidecar_path}')
    selection_before = stamp(selection_path)
    selection = json.loads(selection_path.read_text())
    for key in ('include', 'exclude', 'required_files', 'manuscript_bindings', 'rights_exceptions'):
        if not isinstance(selection.get(key), list):
            raise ValueError(f'selection field {key!r} must be a list')
    if not isinstance(selection.get('copy_files', {}), dict):
        raise ValueError('selection copy_files must map archive destinations to source paths')
    sources = collect(root, selection)
    if not sources:
        raise ValueError('selection is empty')
    before = {name: stamp(path) for name, path in sources.items()}
    manuscript = bindings(root, selection['manuscript_bindings'])
    rows = []
    base = subprocess.check_output(['git', '-C', str(root / EXPERIMENT), 'rev-parse', 'HEAD'], text=True).strip()
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_name(archive.name + '.partial')
    if partial.exists():
        raise FileExistsError(f'partial archive already exists: {partial}')
    if any(path.resolve() in {archive, partial, sidecar_path} for path in sources.values()):
        raise ValueError('archive, partial and sidecar outputs must not be selected source inputs')
    # No raw-data staging and no copied authoring tree. Each byte is hashed
    # while it is sent to the tar stream. Final manifests follow the members.
    with partial.open('xb') as output, gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=3) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as tar:
            for relative, path in sources.items():
                source_path(root, path.relative_to(root).as_posix())
                info = tar.gettarinfo(str(path), arcname='thesis-reproduction/' + relative)
                if not info.isfile():
                    raise ValueError(f'only regular source files are allowed: {relative}')
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                info.mtime = 0
                with path.open('rb') as source:
                    if descriptor_stamp(source) != before[relative]:
                        raise RuntimeError(f'input changed before packaging: {relative}')
                    reader = HashReader(source)
                    tar.addfile(info, reader)
                    descriptor_after = descriptor_stamp(source)
                source_path(root, path.relative_to(root).as_posix())
                if stamp(path) != before[relative] or descriptor_after != before[relative]:
                    raise RuntimeError(f'input changed during packaging: {relative}')
                rows.append({'path': relative, 'size': info.size, 'sha256': reader.digest.hexdigest()})
            if any(stamp(path) != before[name] for name, path in sources.items()):
                raise RuntimeError('selected source inputs changed during packaging; rebuild from a stable snapshot')
            if stamp(selection_path) != selection_before or collect(root, selection) != sources:
                raise RuntimeError('source selection changed during packaging; rebuild from a stable snapshot')
            if bindings(root, selection['manuscript_bindings']) != manuscript:
                raise RuntimeError('manuscript changed during packaging; refresh the snapshot')
            metadata = {
                'schema': 'thesis-reproduction.source-manifest.v2',
                'base_revision': base,
                'source_identity': 'selected working bytes; Git revision alone does not identify uncommitted inputs',
                'file_count': len(rows), 'files': rows,
                'snapshot_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'manuscript_bindings': manuscript,
                'raw_archive_external': 'main_raw_data.tar.gz',
                'rights_exceptions': selection['rights_exceptions'],
            }
            data = (json.dumps(metadata, indent=2, sort_keys=True) + '\n').encode()
            info = tarfile.TarInfo('thesis-reproduction/SOURCE_MANIFEST.json')
            info.size = len(data); info.mode = 0o644; info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    # Publishing the completed archive must not overwrite a file created by
    # another process after the initial existence check.
    os.link(partial, archive)
    partial.unlink()
    sidecar = {'archive': archive.name, 'archive_sha256': sha256(archive), 'archive_bytes': archive.stat().st_size,
               'source_manifest': metadata}
    with sidecar_path.open('x') as output:
        output.write(json.dumps(sidecar, indent=2) + '\n')
    return sidecar


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--selection', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = freeze(args.project_root, args.selection, args.archive)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f'ERROR: {error}\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'source_manifest'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
