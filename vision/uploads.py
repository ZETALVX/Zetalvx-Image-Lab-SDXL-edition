"""Chunked browser uploads for local Vision GGUF files.

The browser can upload a GGUF model or its mmproj to an app-managed folder.
Server-path selection remains available and never copies files. Executables are
never accepted here; llama-server must be selected from the server filesystem.
"""
from __future__ import annotations
import json, os, re, shutil, tempfile, time, uuid
from pathlib import Path
from .registry import VisionError, atomic_json

MAX_UPLOAD_BYTES = 64 * 1024**3
MAX_CHUNK_BYTES = 24 * 1024**2
STALE_SECONDS = 24 * 3600
ROLES = {'gguf_path', 'mmproj_path'}

class BrowserVisionUploads:
    def __init__(self, home):
        self.home = Path(home).expanduser().resolve()
        self.dest = self.home / 'models' / 'Vision' / 'GGUF'
        self.root = self.home / 'models' / '.incoming' / 'vision-browser-uploads'
        self.dest.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, uid):
        if not isinstance(uid, str) or len(uid) != 32 or any(c not in '0123456789abcdef' for c in uid):
            raise VisionError('Invalid upload identifier')
        return self.root / f'{uid}.json'

    def _load(self, uid):
        p = self._meta_path(uid)
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            raise VisionError('Upload not found or expired') from e
        if not isinstance(d, dict) or d.get('id') != uid or d.get('role') not in ROLES:
            raise VisionError('Invalid upload state')
        return d

    def _stage(self, d):
        return self.root / f"{d['id']}-{d['filename']}"

    def cleanup(self):
        now = time.time()
        for p in self.root.glob('*.json'):
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
                if now - float(d.get('created_at', 0)) <= STALE_SECONDS:
                    continue
                self._stage(d).unlink(missing_ok=True); p.unlink(missing_ok=True)
            except Exception:
                continue

    def create(self, filename, size, role):
        self.cleanup()
        if role not in ROLES:
            raise VisionError('Unsupported Vision upload target')
        if not isinstance(filename, str):
            raise VisionError('Choose a .gguf file')
        raw = Path(filename).name
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', raw).strip('._')
        if not name or not name.lower().endswith('.gguf'):
            raise VisionError('Vision browser upload accepts only .gguf files')
        try: size = int(size)
        except (TypeError, ValueError): raise VisionError('Invalid file size') from None
        if size <= 0 or size > MAX_UPLOAD_BYTES:
            raise VisionError('File size must be between 1 byte and 64 GiB')
        free = shutil.disk_usage(self.home).free
        if free < size + 512 * 1024**2:
            raise VisionError('Not enough free disk space for this upload')
        uid = uuid.uuid4().hex
        d = {'id': uid, 'filename': name, 'size': size, 'role': role, 'created_at': time.time(), 'received': 0}
        with open(self._stage(d), 'xb'): pass
        atomic_json(self._meta_path(uid), d)
        return self.public(d)

    @staticmethod
    def public(d):
        return {k: d.get(k) for k in ('id','filename','size','role','created_at','received')}

    def append(self, uid, offset, file_storage):
        d = self._load(uid)
        try: offset = int(offset)
        except (TypeError, ValueError): raise VisionError('Invalid upload offset') from None
        stage = self._stage(d)
        try: current = stage.stat().st_size
        except OSError as e: raise VisionError('Upload staging file is missing') from e
        if offset != current or offset != int(d.get('received', current)):
            raise VisionError(f'Upload offset mismatch. Expected {current}')
        if file_storage is None: raise VisionError('Missing upload chunk')
        remaining = int(d['size']) - current
        if remaining <= 0: return self.public(d)
        written = 0
        with open(stage, 'ab') as out:
            while True:
                block = file_storage.stream.read(min(1024*1024, remaining-written))
                if not block: break
                out.write(block); written += len(block)
                if written > MAX_CHUNK_BYTES or written > remaining:
                    raise VisionError('Upload chunk exceeds the allowed size')
                if written == remaining: break
            out.flush(); os.fsync(out.fileno())
        if written <= 0: raise VisionError('Empty upload chunk')
        d['received'] = current + written; d['updated_at'] = time.time(); atomic_json(self._meta_path(uid), d)
        return self.public(d)

    def finalize(self, uid):
        d = self._load(uid); stage = self._stage(d)
        try: size = stage.stat().st_size
        except OSError as e: raise VisionError('Upload staging file is missing') from e
        if size != int(d['size']):
            raise VisionError(f'Upload incomplete: {size} of {d["size"]} bytes received')
        try:
            with stage.open('rb') as f: magic = f.read(4)
        except OSError as e:
            raise VisionError('Cannot validate uploaded GGUF file') from e
        if magic != b'GGUF':
            raise VisionError('The selected file is not a valid GGUF file')
        target = self.dest / d['filename']
        if target.exists():
            stem, suffix = target.stem, target.suffix
            for n in range(2, 10000):
                candidate = self.dest / f'{stem}-{n}{suffix}'
                if not candidate.exists(): target = candidate; break
            else: raise VisionError('Too many files with the same name in the Vision folder')
        os.replace(stage, target); self._meta_path(uid).unlink(missing_ok=True)
        return {'path': str(target), 'filename': target.name, 'role': d['role'], 'copied': True}

    def cancel(self, uid):
        d = self._load(uid); self._stage(d).unlink(missing_ok=True); self._meta_path(uid).unlink(missing_ok=True)
        return {'cancelled': uid}
