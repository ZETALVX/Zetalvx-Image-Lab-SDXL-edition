"""Chunked browser uploads for SDXL checkpoint/LoRA safetensors.

Files selected on the user's browser are copied into the app's standard model folders.
This is deliberately separate from local/server-path linking, which never copies weights.
"""
from __future__ import annotations
import json
import os
import shutil
import time
import uuid
import re
from pathlib import Path
from core.local_models import LocalModelError
from core.runtime_env import atomic_json

MAX_UPLOAD_BYTES = 32 * 1024**3
MAX_CHUNK_BYTES = 24 * 1024**2
STALE_SECONDS = 24 * 3600


class BrowserModelUploads:
    def __init__(self, models_root, local_models):
        self.models_root = Path(models_root).expanduser().resolve()
        self.local_models = local_models
        self.root = self.models_root / '.incoming' / 'browser-uploads'
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, uid):
        if not isinstance(uid, str) or len(uid) != 32 or any(c not in '0123456789abcdef' for c in uid):
            raise LocalModelError('Invalid upload identifier.')
        return self.root / f'{uid}.json'

    def _load(self, uid):
        p = self._meta_path(uid)
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise LocalModelError('Upload not found or expired.') from e
        if not isinstance(d, dict) or d.get('id') != uid or d.get('kind') not in ('checkpoint', 'lora'):
            raise LocalModelError('Invalid upload state.')
        return d

    def _stage(self, d):
        # Stage keeps .safetensors suffix so the same inspector can validate the completed file.
        return self.root / f"{d['id']}-{d['filename']}"

    def cleanup(self):
        now = time.time()
        for p in self.root.glob('*.json'):
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
                if now - float(d.get('created_at', 0)) <= STALE_SECONDS:
                    continue
                stage = self._stage(d)
                stage.unlink(missing_ok=True)
                p.unlink(missing_ok=True)
            except Exception:
                continue

    def create(self, filename, size, kind):
        self.cleanup()
        if kind not in ('checkpoint', 'lora'):
            raise LocalModelError('Select Checkpoint or LoRA.')
        if not isinstance(filename, str):
            raise LocalModelError('Choose a .safetensors file.')
        raw_name = Path(filename).name
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', raw_name).strip('._')
        if not name or not name.lower().endswith('.safetensors'):
            raise LocalModelError('Browser upload accepts only .safetensors files.')
        try:
            size = int(size)
        except (TypeError, ValueError):
            raise LocalModelError('Invalid file size.') from None
        if size <= 0 or size > MAX_UPLOAD_BYTES:
            raise LocalModelError('File size must be between 1 byte and 32 GiB.')
        free = shutil.disk_usage(self.models_root).free
        if free < size + 512 * 1024**2:
            raise LocalModelError('Not enough free disk space for this upload.')
        uid = uuid.uuid4().hex
        d = {'id': uid, 'filename': name, 'size': size, 'kind': kind, 'created_at': time.time(), 'received': 0}
        stage = self._stage(d)
        stage.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidentally appending to stale content.
        with open(stage, 'xb'):
            pass
        atomic_json(self._meta_path(uid), d)
        return self.public(d)

    def public(self, d):
        return {k: d.get(k) for k in ('id', 'filename', 'size', 'kind', 'created_at', 'received')}

    def append(self, uid, offset, file_storage):
        d = self._load(uid)
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            raise LocalModelError('Invalid upload offset.') from None
        stage = self._stage(d)
        try:
            current = stage.stat().st_size
        except OSError as e:
            raise LocalModelError('Upload staging file is missing.') from e
        if offset != current or offset != int(d.get('received', current)):
            raise LocalModelError(f'Upload offset mismatch. Expected {current}.')
        if file_storage is None:
            raise LocalModelError('Missing upload chunk.')
        declared = getattr(file_storage, 'content_length', None)
        if declared and declared > MAX_CHUNK_BYTES:
            raise LocalModelError('Upload chunk is too large.')
        remaining = int(d['size']) - current
        if remaining <= 0:
            return self.public(d)
        written = 0
        with open(stage, 'ab') as out:
            while True:
                block = file_storage.stream.read(min(1024 * 1024, remaining - written))
                if not block:
                    break
                out.write(block); written += len(block)
                if written > MAX_CHUNK_BYTES or written > remaining:
                    raise LocalModelError('Upload chunk exceeds the allowed size.')
                if written == remaining:
                    break
            out.flush(); os.fsync(out.fileno())
        if written <= 0:
            raise LocalModelError('Empty upload chunk.')
        d['received'] = current + written
        d['updated_at'] = time.time()
        atomic_json(self._meta_path(uid), d)
        return self.public(d)

    def finalize(self, uid, accept_unknown=False):
        d = self._load(uid); stage = self._stage(d)
        try:
            size = stage.stat().st_size
        except OSError as e:
            raise LocalModelError('Upload staging file is missing.') from e
        if size != int(d['size']):
            raise LocalModelError(f'Upload incomplete: {size} of {d["size"]} bytes received.')
        detail = self.local_models.inspect(str(stage), d['kind'])
        if detail.get('needs_confirmation') and accept_unknown is not True:
            return {'needs_confirmation': True, 'preview': {**detail, 'name': d['filename']}, 'upload': self.public(d)}
        target_root = self.models_root / ('SDXL' if d['kind'] == 'checkpoint' else 'loras/SDXL')
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / d['filename']
        if target.exists():
            stem, suffix = target.stem, target.suffix
            for n in range(2, 10000):
                candidate = target_root / f'{stem}-{n}{suffix}'
                if not candidate.exists():
                    target = candidate; break
            else:
                raise LocalModelError('Too many files with the same name in the destination folder.')
        os.replace(stage, target)
        self._meta_path(uid).unlink(missing_ok=True)
        return {'needs_confirmation': False, 'path': str(target), 'name': target.name, 'kind': d['kind'], 'copied': True,
                'note': 'Uploaded from this device into the app model folder.'}

    def cancel(self, uid):
        d = self._load(uid)
        self._stage(d).unlink(missing_ok=True)
        self._meta_path(uid).unlink(missing_ok=True)
        return {'cancelled': uid}
