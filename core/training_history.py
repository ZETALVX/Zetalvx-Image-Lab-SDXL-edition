"""Explicit deletion of terminal training workspaces; never model-library files.

No training algorithm or dataset is modified. All UI training submissions share
this lock so a resume cannot race a workspace deletion. The worker is checked
again under the lock. Unknown/offline state fails closed.
"""
from __future__ import annotations
import contextlib
import functools
import json
import os
from pathlib import Path
import shutil
import threading
from core.file_lock import flock, LOCK_EX, LOCK_UN
from core.safe_paths import is_link

TERMINAL = frozenset({'completed', 'failed', 'stopped', 'cancelled', 'interrupted', 'worker_offline'})
_REFERENCE_KEYS = ('resume_from', 'resume_from_checkpoint', 'checkpoint_path',
                   'continue_from', 'init_lora_path', 'source_weights_checkpoint',
                   'resume_checkpoint', 'weights_checkpoint', 'base_model')
_LOCK = threading.RLock()
_LOCAL = threading.local()

@contextlib.contextmanager
def operation_lock():
    from core import training_manager as tm
    with _LOCK:
        depth = getattr(_LOCAL, 'depth', 0)
        if depth:
            _LOCAL.depth = depth + 1
            try: yield
            finally: _LOCAL.depth = depth
            return
        root = Path(tm.JOBS)
        if is_link(root) or is_link(root.parent):
            raise RuntimeError('Unsafe training jobs directory')
        root.mkdir(parents=True, exist_ok=True)
        path = root / '.history-operations.lock'
        if is_link(path): raise RuntimeError('Unsafe training history lock')
        with path.open('a+b') as stream:
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            flock(stream, LOCK_EX)
            _LOCAL.depth = 1
            try: yield
            finally:
                _LOCAL.depth = 0
                flock(stream, LOCK_UN)

def guarded(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with operation_lock(): return fn(*args, **kwargs)
    return wrapped

def _read(path):
    if is_link(path): raise RuntimeError('Linked training metadata cannot be deleted')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise RuntimeError('Unreadable training metadata; nothing deleted') from exc
    if not isinstance(data, dict): raise RuntimeError('Invalid training metadata; nothing deleted')
    return data

def _record(folder):
    data = _read(folder / 'job.json')
    prog = folder / 'progress.json'
    if prog.exists() or is_link(prog): data.update(_read(prog))
    return data

def _tree_size(folder):
    size = 0
    for here, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            p = Path(here) / name
            if is_link(p) or os.path.ismount(p):
                raise RuntimeError('Linked or mounted files found in training workspace; nothing deleted')
            if p.is_file(): size += p.stat().st_size
    return size

def _references(record, folder, jid):
    if str(record.get('continuation_of') or '') == jid: return True
    for key in _REFERENCE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            p = Path(value).expanduser().resolve()
            if p == folder or p.is_relative_to(folder): return True
    return False

def delete_job(jid, *, confirm=False):
    """Delete job.json/progress/logs/checkpoints and unexported local outputs.

    Datasets, published LoRAs/full models, downloaded models, and export ZIPs
    outside this single workspace are never followed, copied or removed.
    """
    from core import training_manager as tm
    from core.lora_files import library_lock
    if confirm is not True: raise ValueError('Explicit training deletion confirmation required')
    jid = tm._safe_jid(jid)
    with operation_lock(), library_lock(tm.LORA_ROOT):
        root = Path(tm.JOBS).resolve()
        folder = Path(tm.JOBS) / jid
        if is_link(folder) or os.path.ismount(folder): raise RuntimeError('Unsafe training workspace')
        if not folder.exists(): return {'deleted': False, 'already_absent': True, 'job_id': jid}
        folder = folder.resolve()
        if folder.parent != root: raise RuntimeError('Training workspace outside jobs directory')
        job = _record(folder)
        if job.get('id') != jid: raise RuntimeError('Training job identity mismatch; nothing deleted')
        if job.get('status') not in TERMINAL:
            raise RuntimeError('Only finished, stopped or failed training jobs can be deleted')
        health = tm.worker_health()
        if not isinstance(health, dict) or not health.get('ok'):
            raise RuntimeError('Training worker unavailable: cannot verify that deletion is safe. Start the app and retry.')
        if str(health.get('job_id') or '') == jid and health.get('busy'):
            raise RuntimeError('Training job is still active in the worker')
        if health.get('busy') and not health.get('job_id'):
            raise RuntimeError('Worker is busy with an unidentified job; nothing deleted')
        for entry in root.iterdir():
            if entry.name == jid or not entry.is_dir(): continue
            if is_link(entry): raise RuntimeError('Linked training workspace found; nothing deleted')
            if not (entry/'job.json').exists(): continue
            other = _record(entry)
            active = other.get('status') not in TERMINAL or (
                health.get('busy') and str(health.get('job_id') or '') == entry.name)
            if active and _references(other, folder, jid):
                raise RuntimeError('Another active training or continuation uses this workspace')
        # The path roots must be separate; a mistaken configuration must not
        # make the dataset or library a child of the workspace being removed.
        for protected in (tm.DATASETS, tm.LORA_ROOT, tm.FULL_ROOT):
            p = Path(protected).resolve()
            if p == folder or p.is_relative_to(folder):
                raise RuntimeError('Workspace contains a protected dataset/model library')
        size = _tree_size(folder)
        shutil.rmtree(folder)
        return {'deleted': True, 'job_id': jid, 'removed_bytes': size,
                'dataset_preserved': True, 'published_models_preserved': True}
