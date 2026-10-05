"""Versioned installation helpers; standard library only, no import-time writes.
Zetalvx Image Lab - SDXL Edition 0.1.0.29, Apache-2.0.
Linux keeps the historical current/previous symlinks. Windows uses one atomic
JSON pointer so installation never needs administrator symlink privileges.
"""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from core import file_lock
from core.platform_support import default_data_root, venv_python

VERSION = '1.0.18'
RUNTIME_MAP = '.installed-runtime.json'


def atomic_json(path: Path, data: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def home_path(value=None) -> Path:
    return Path(value or os.environ.get('SDXL_STUDIO_HOME') or default_data_root()).expanduser().absolute()


def child(root: Path, relative: str) -> Path:
    """Reject absolute/escaping paths, including Windows paths on POSIX test hosts."""
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Invalid installation-relative path')
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts or any(ord(c)<32 for c in relative):
        raise ValueError('Installation path may not escape its root')
    dest = (root/p).resolve()
    if dest == root or root not in dest.parents:
        raise ValueError('Installation path escapes its root (possibly a symlink)')
    return dest


def release_path(home: Path, name: str) -> Path:
    if not re.fullmatch(r'[0-9][0-9A-Za-z._-]{0,119}', name or ''):
        raise ValueError('Invalid release identifier')
    return child(home, 'versions/'+name)


def pointers(home: Path, *, windows=None) -> dict:
    windows = os.name == 'nt' if windows is None else windows
    if windows:
        f = home/'install-state.json'
        d = json.loads(f.read_text(encoding='utf-8')) if f.is_file() else {}
        if not isinstance(d, dict): raise ValueError('Invalid installation state')
        result = {key: d.get(key) for key in ('current', 'previous')}
        for name in result.values():
            if name: release_path(home, name)
        return result
    result = {}
    for key in ('current', 'previous'):
        p = home/key
        if p.is_symlink():
            resolved = p.resolve(strict=True)
            name = resolved.name
            if resolved != release_path(home, name):
                raise ValueError(f'{key} points outside the SDXL versions directory')
            result[key] = name
        elif p.exists():
            raise ValueError(f'{p} is not the expected version symlink; refusing to overwrite it')
        else:
            result[key] = None
    return result


def set_pointer(home: Path, key: str, name: str | None) -> None:
    if key not in ('current', 'previous'): raise ValueError('Invalid pointer')
    target = release_path(home, name) if name else None
    if target and not target.is_dir(): raise ValueError('Release does not exist')
    link = home/key
    if link.exists() and not link.is_symlink():
        raise ValueError(f'Refusing to overwrite directory/file {link}')
    if name is None:
        link.unlink(missing_ok=True); return
    temp = home/(key+'.new-'+os.urandom(6).hex())
    try:
        temp.symlink_to(target, target_is_directory=True)
        os.replace(temp, link)
    finally:
        temp.unlink(missing_ok=True)


def set_pointers(home: Path, current: str | None, previous: str | None, *, windows=None) -> None:
    windows = os.name == 'nt' if windows is None else windows
    for name in (current, previous):
        if name and not release_path(home, name).is_dir():
            raise ValueError('Cannot activate a missing release')
    if windows:
        atomic_json(home/'install-state.json', {'schema':1, 'current':current, 'previous':previous})
    else:
        # Record previous before flipping current. Each individual replacement is atomic.
        set_pointer(home, 'previous', previous)
        set_pointer(home, 'current', current)


def runtime_dirs(home: Path, release: Path | None) -> dict[str, Path | None]:
    if release is None or not (release/RUNTIME_MAP).is_file():
        return {'app':home/'runtime/app', 'sdxl':home/'runtime/sdxl'}
    m = json.loads((release/RUNTIME_MAP).read_text(encoding='utf-8'))
    if m.get('schema') != 1 or not isinstance(m.get('runtimes'), dict):
        raise ValueError('Invalid per-version runtime mapping')
    result = {}
    for key in ('app', 'sdxl'):
        rel = m['runtimes'].get(key)
        if rel is None and key == 'sdxl': result[key] = None; continue
        if not isinstance(rel, str) or not rel.startswith('runtime/'):
            raise ValueError('Runtime must live inside this SDXL installation')
        result[key] = child(home, rel)
    return result


def write_runtime_map(home: Path, release: Path, runtimes: dict, **metadata) -> None:
    mapping = {}
    for key in ('app', 'sdxl'):
        p = runtimes.get(key)
        if p is None and key == 'sdxl': mapping[key] = None; continue
        # Resolve directories, not bin/python: venv's Python executable can be a symlink.
        rel = Path(p).resolve().relative_to(home.resolve()).as_posix()
        if not rel.startswith('runtime/') or child(home, rel) != Path(p).resolve():
            raise ValueError('Invalid runtime directory')
        mapping[key] = rel
    atomic_json(release/RUNTIME_MAP, {'schema':1, 'runtimes':mapping, **metadata})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def verify_manifest(root: Path) -> list[str]:
    f = root/'MANIFEST.sha256'
    if not f.is_file(): raise ValueError('MANIFEST.sha256 missing; incomplete package')
    checked = []
    for line in f.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        parts = line.split('  ', 1)
        if len(parts) != 2 or not re.fullmatch('[a-f0-9]{64}', parts[0]):
            raise ValueError('Malformed package manifest')
        digest, name = parts
        p = child(root, name)
        original = root/name
        linked = any(q.is_symlink() for q in (original, *original.parents) if q != root and root in q.parents)
        if name in checked or linked or not p.is_file() or sha256(p) != digest:
            raise ValueError('Package checksum mismatch: '+name)
        checked.append(name)
    for required in ('launcher.py', 'app.py', 'core/runtime_env.py', 'LICENSE'):
        if required not in checked: raise ValueError('Incomplete manifest: '+required)
    return checked


@contextlib.contextmanager
def locked(path: Path, *, blocking=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise ValueError('Refusing symlink lock file')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'r+b') as f:
        if os.fstat(fd).st_size == 0: f.write(b'\0'); f.flush()
        file_lock.flock(f, file_lock.LOCK_EX | (0 if blocking else file_lock.LOCK_NB))
        try: yield
        finally: file_lock.flock(f, file_lock.LOCK_UN)
