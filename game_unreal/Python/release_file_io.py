"""Local file reads supporting existing long Windows evidence/asset paths.

No OS/registry policy change. Callers still enforce their own workspace bounds.
"""
from pathlib import Path
import hashlib
import os
import sys


def io_path(path):
    value = os.path.abspath(os.fspath(path))
    if sys.platform == 'win32' and not value.startswith('\\\\?\\'):
        value = ('\\\\?\\UNC\\' + value[2:]) if value.startswith('\\\\') else ('\\\\?\\' + value)
    return Path(value)


def sha(path):
    return hashlib.sha256(io_path(path).read_bytes()).hexdigest()


def is_file(path):
    return io_path(path).is_file()


def logical_path(path):
    value = os.fspath(path)
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)


def files(root, pattern):
    # Enumeration also needs the prefix; ordinary pathlib.rglob can silently
    # omit descendants of an overlong directory even when read_bytes is fixed.
    return [logical_path(p) for p in io_path(root).rglob(pattern)]
