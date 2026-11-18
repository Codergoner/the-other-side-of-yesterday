"""Read/hash every existing file using explicit Win32 long-path I/O.

Manifests retain canonical ordinary absolute paths. No file is skipped because
its path exceeds MAX_PATH; vanished/unreadable enumerated files fail the guard.
"""
from pathlib import Path
import hashlib
import os


def canonical(path):
    value = os.path.abspath(os.fspath(path))
    if value.startswith('\\\\?\\UNC\\'):
        return '\\\\' + value[8:]
    if value.startswith('\\\\?\\'):
        return value[4:]
    return value


def io_path(path):
    value = canonical(path)
    if os.name != 'nt':
        return value
    return '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value


def sha(path):
    result = hashlib.sha256()
    with open(io_path(path), 'rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def matches(root, pattern):
    return [Path(canonical(p)) for p in Path(io_path(root)).rglob(pattern)]


def files(root):
    # is_file operates on the explicit extended path, not the canonical label.
    return [Path(canonical(p)) for p in Path(io_path(root)).rglob('*') if p.is_file()]


def native(project, excluded=None):
    project = Path(project)
    paths = matches(project / 'Content', '*.uasset') + matches(project / 'Content', '*.umap')
    paths += [Path(canonical(p)) for p in Path(io_path(project / 'Config')).glob('*.ini')]
    paths += [Path(canonical(p)) for p in Path(io_path(project)).glob('*.uproject')]
    if excluded is not None:
        excluded = Path(canonical(excluded))
        paths = [p for p in paths if not p.is_relative_to(excluded)]
    return {canonical(p): sha(p) for p in paths}
