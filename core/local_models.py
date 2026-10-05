"""Local checkpoint/LoRA references. No downloads, inference, copies or weight deletion.

0.1.0.18: strict SDXL discovery; config-only folders are never listed as checkpoints.
Local administrator may explicitly choose external files; the registry stores references only.
"""
from __future__ import annotations
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from core.runtime_env import atomic_json
from core.model_downloads import classify_safetensors
from core.download_security import DownloadError

_LOCK = threading.RLock()
KINDS = {'checkpoint', 'lora'}
MAX_REFERENCES = 256
MAX_FILES = 1500
MAX_VISITED = 8000
MAX_DEPTH = 8

class LocalModelError(ValueError):
    pass

class LocalModels:
    def __init__(self, models_root, registry_path, blocked_roots=()):
        self.models_root = Path(models_root).expanduser().resolve()
        self.registry_path = Path(registry_path)
        self.blocked_roots = tuple(Path(p).expanduser().resolve() for p in blocked_roots)
        self._cache = {}
        # Keep the historical LoRA path for backward compatibility; checkpoints use a separate setting file.
        self.visibility_path = self.registry_path.with_name('lora_availability.json')
        self.checkpoint_visibility_path = self.registry_path.with_name('checkpoint_availability.json')

    def _path(self, raw):
        if not isinstance(raw, str) or not raw.strip() or '\x00' in raw or '\n' in raw or '://' in raw:
            raise LocalModelError('Choose an absolute local path, not a URL.')
        p = Path(raw.strip()).expanduser()
        if not p.is_absolute():
            raise LocalModelError('Use an absolute path or a path starting with ~/.')
        p = p.resolve()
        if p == Path('/') or any(p == x or p.is_relative_to(x) for x in self.blocked_roots):
            raise LocalModelError('This directory is not available for model imports.')
        if any(p == Path(x) or p.is_relative_to(Path(x)) for x in ('/proc', '/sys', '/dev')):
            raise LocalModelError('Select a folder containing models, not a system device directory.')
        return p

    def sources(self):
        with _LOCK:
            if not self.registry_path.exists():
                return []
            try:
                data = json.loads(self.registry_path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('entries'), list):
                    raise ValueError('schema')
                if len(data['entries']) > MAX_REFERENCES:
                    raise ValueError('limit')
                if any(not isinstance(x, dict) or x.get('kind') not in KINDS or x.get('entry_type') not in ('file', 'folder') or not isinstance(x.get('path'), str) for x in data['entries']):
                    raise ValueError('entry')
                return data['entries']
            except (OSError, ValueError) as e:
                raise LocalModelError('The local model registry is unreadable. It was not overwritten; restore or correct that file before retrying.') from e

    def _write(self, entries):
        atomic_json(self.registry_path, {'schema_version': 1, 'entries': entries})

    def _availability_for(self, kind):
        path = self.visibility_path if kind == 'lora' else self.checkpoint_visibility_path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            entries = data.get('enabled')
            if data.get('schema_version') != 1 or not isinstance(entries, dict):
                raise ValueError('schema')
            if any(not isinstance(k, str) or type(v) is not bool for k, v in entries.items()):
                raise ValueError('entry')
            return entries
        except (OSError, ValueError, AttributeError) as exc:
            label = 'LoRA' if kind == 'lora' else 'Checkpoint'
            raise LocalModelError(f'{label} availability settings are unreadable; no settings were overwritten.') from exc

    def _availability(self):
        # Historical helper retained for existing callers/tests.
        return self._availability_for('lora')

    def set_generation_availability(self, kind, entry_id, enabled, config=None, extra_roots=()):
        if kind not in KINDS:
            raise LocalModelError('Invalid model type.')
        if type(enabled) is not bool:
            raise LocalModelError('Availability must be true or false.')
        if not isinstance(entry_id, str) or len(entry_id) != 24 or any(c not in '0123456789abcdef' for c in entry_id):
            raise LocalModelError('Invalid model identifier.')
        cfg = config or {}
        with _LOCK:
            rows = self.scan(kind, cfg, extra_roots, include_missing=True, include_disabled=True)
            row = next((r for r in rows if r['id'] == entry_id), None)
            if row is None:
                raise LocalModelError(('LoRA' if kind == 'lora' else 'Checkpoint')+' not found in the model library.')
            if enabled and not row['present']:
                raise LocalModelError('The model file is missing.')
            if kind == 'checkpoint' and not enabled:
                protected = {str(Path(str(cfg.get(k))).expanduser().resolve()) for k in ('checkpoint','inpaint_checkpoint') if cfg.get(k)}
                if row['path'] in protected:
                    raise LocalModelError('Choose another default/inpaint checkpoint before disconnecting this one from Generate.')
            entries = self._availability_for(kind)
            entries[row['path']] = enabled
            path = self.visibility_path if kind == 'lora' else self.checkpoint_visibility_path
            atomic_json(path, {'schema_version': 1, 'enabled': entries})
        return {'id': entry_id, 'path': row['path'], 'generation_enabled': enabled, 'weights_deleted': False}

    def set_lora_availability(self, entry_id, enabled, config=None, extra_roots=()):
        return self.set_generation_availability('lora', entry_id, enabled, config, extra_roots)

    def set_checkpoint_availability(self, entry_id, enabled, config=None):
        return self.set_generation_availability('checkpoint', entry_id, enabled, config)

    def delete_managed_checkpoint(self, entry_id, config=None):
        cfg = config or {}
        with _LOCK:
            rows = self.scan('checkpoint', cfg, include_missing=True, include_disabled=True)
            row = next((r for r in rows if r['id'] == entry_id), None)
            if row is None:
                raise LocalModelError('Checkpoint not found in the model library.')
            p = Path(row['path']).expanduser().resolve()
            root = (self.models_root/'SDXL').resolve()
            try:
                p.relative_to(root)
            except ValueError:
                raise LocalModelError('Only checkpoint files stored in the Zetalvx Image Lab model folder can be deleted here.') from None
            protected = {str(Path(str(cfg.get(k))).expanduser().resolve()) for k in ('checkpoint','inpaint_checkpoint') if cfg.get(k)}
            if str(p) in protected:
                raise LocalModelError('Choose another default/inpaint checkpoint before deleting this file.')
            if not p.is_file() or p.suffix.lower() != '.safetensors':
                raise LocalModelError('Only managed .safetensors checkpoint files can be deleted here.')
            p.unlink()
            entries = [x for x in self.sources() if not (x.get('kind')=='checkpoint' and x.get('path')==str(p))]
            self._write(entries)
            availability = self._availability_for('checkpoint')
            if str(p) in availability:
                availability.pop(str(p), None)
                atomic_json(self.checkpoint_visibility_path, {'schema_version': 1, 'enabled': availability})
        return {'id': entry_id, 'path': str(p), 'deleted': True, 'weights_deleted': True}

    def _classify(self, p):
        st = p.stat()
        signature = (str(p), st.st_size, st.st_mtime_ns)
        if signature not in self._cache:
            if len(self._cache) > MAX_FILES * 2:
                self._cache.clear()
            self._cache[signature] = classify_safetensors(p)
        return dict(self._cache[signature])

    @staticmethod
    def _json(p):
        if p.stat().st_size > 4 * 1024 * 1024:
            raise LocalModelError('Configuration file is too large.')
        d = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(d, dict):
            raise LocalModelError('Invalid model configuration.')
        return d

    def _inspect_diffusers_dir(self, p):
        """Accept only a complete SDXL Diffusers model, never config/tokenizer-only folders."""
        index = p/'model_index.json'
        if not index.is_file():
            raise LocalModelError('Select a .safetensors file, a complete Diffusers directory, or use Add folder.')
        try:
            cfg = self._json(index)
            cls = str(cfg.get('_class_name') or '')
            if cls not in ('StableDiffusionXLPipeline', 'StableDiffusionXLImg2ImgPipeline', 'StableDiffusionXLInpaintPipeline'):
                raise LocalModelError('This directory does not declare an SDXL pipeline.')
            needed = ('unet/config.json', 'vae/config.json', 'text_encoder/config.json', 'text_encoder_2/config.json',
                      'tokenizer/tokenizer_config.json', 'tokenizer_2/tokenizer_config.json', 'scheduler/scheduler_config.json')
            missing = [n for n in needed if not (p/n).is_file()]
            for component in ('unet', 'vae', 'text_encoder', 'text_encoder_2'):
                comp = p/component
                weight_files = list(comp.glob('*.safetensors')) if comp.is_dir() else []
                if not weight_files:
                    missing.append(component+'/*.safetensors')
                else:
                    for weight in weight_files:
                        self._classify(weight)
                for i in comp.glob('*.safetensors.index.json') if comp.is_dir() else ():
                    mapping = self._json(i).get('weight_map')
                    if not isinstance(mapping, dict):
                        raise LocalModelError('Invalid Diffusers shard index.')
                    for name in set(mapping.values()):
                        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.safetensors'):
                            raise LocalModelError('Unsafe Diffusers shard index.')
                        if not (comp/name).is_file():
                            missing.append(component+'/'+name)
            if missing:
                raise LocalModelError('Incomplete Diffusers directory: '+', '.join(missing[:8]))
            return {'path': str(p), 'name': p.name, 'kind': 'checkpoint', 'format': 'diffusers', 'family': 'sdxl', 'needs_confirmation': False,
                    'note': 'Complete SDXL Diffusers configuration and safetensors weights found; inference not tested.'}
        except (ValueError, OSError, DownloadError) as e:
            raise LocalModelError(str(e)) from e

    def inspect(self, raw, kind):
        if kind not in KINDS:
            raise LocalModelError('Select Checkpoint or LoRA.')
        p = self._path(raw)
        if not p.exists():
            raise LocalModelError('File or folder not found on the server.')
        if p.is_dir():
            if kind != 'checkpoint':
                raise LocalModelError('For a LoRA folder, use Add folder, not Link file.')
            return self._inspect_diffusers_dir(p)
        if not p.is_file() or p.suffix.lower() != '.safetensors':
            raise LocalModelError('New local imports accept .safetensors, not .ckpt/.bin/.pt pickle files.')
        try:
            d = self._classify(p)
        except (ValueError, OSError, DownloadError) as e:
            raise LocalModelError(str(e)) from e
        if d['family'] == 'other' or d['kind'] not in (kind, 'unknown'):
            raise LocalModelError('This file is not compatible with the selected SDXL model type.')
        uncertain = d['family'] != 'sdxl' or d['kind'] == 'unknown'
        return {'path': str(p), 'name': p.name, 'kind': kind, 'format': 'safetensors', 'family': d['family'],
                'detected_kind': d['kind'], 'size_bytes': p.stat().st_size, 'needs_confirmation': uncertain,
                'note': 'Compatibility could not be established. Confirm only if you know it is an SDXL '+kind+'.' if uncertain else 'Header matches SDXL; inference not tested.'}

    def add(self, raw, kind, entry_type='file', accept_unknown=False):
        if kind not in KINDS or entry_type not in ('file', 'folder'):
            raise LocalModelError('Invalid model type or source type.')
        p = self._path(raw)
        if entry_type == 'folder':
            if not p.is_dir():
                raise LocalModelError('Choose an existing folder on the server.')
            detail = {'path': str(p), 'name': p.name, 'needs_confirmation': False}
        else:
            detail = self.inspect(str(p), kind)
            if detail['needs_confirmation'] and accept_unknown is not True:
                return {'needs_confirmation': True, 'preview': detail}
        with _LOCK:
            entries = self.sources()
            for e in entries:
                if (e['path'], e['kind'], e['entry_type']) == (str(p), kind, entry_type):
                    return {'already_linked': True, 'entry': e}
            if len(entries) >= MAX_REFERENCES:
                raise LocalModelError('Too many model locations. Remove an unused reference first.')
            e = {'id': uuid.uuid4().hex, 'kind': kind, 'entry_type': entry_type, 'path': str(p), 'created_at': time.time(),
                 'confirmed_unknown': bool(detail.get('needs_confirmation'))}
            entries.append(e)
            self._write(entries)
        return {'entry': e, 'needs_confirmation': False}

    def remove(self, entry_id):
        if not isinstance(entry_id, str) or len(entry_id) != 32 or any(c not in '0123456789abcdef' for c in entry_id):
            raise LocalModelError('Invalid local reference identifier.')
        with _LOCK:
            entries = self.sources()
            old = next((x for x in entries if x['id'] == entry_id), None)
            if old is None:
                raise LocalModelError('Reference not found.')
            self._write([x for x in entries if x['id'] != entry_id])
        return {'removed': entry_id, 'path': old['path'], 'weights_deleted': False}

    def scan(self, kind, config=None, extra_roots=(), include_missing=False, include_disabled=False):
        if kind not in KINDS:
            raise LocalModelError('Invalid model type.')
        cfg = config or {}
        availability = self._availability_for(kind)
        entries = [x for x in self.sources() if x['kind'] == kind]
        explicit = {x['path']: x for x in entries if x['entry_type'] == 'file'}
        roots = [self.models_root/('SDXL' if kind == 'checkpoint' else 'loras/SDXL')]
        setting = cfg.get('checkpoint_roots' if kind == 'checkpoint' else 'lora_root') or ''
        roots += [Path(x).expanduser() for x in str(setting).split(os.pathsep) if x.strip()]
        roots += [Path(x).expanduser() for x in extra_roots if x]
        roots += [Path(x['path']) for x in entries if x['entry_type'] == 'folder']
        active = str(Path(str(cfg.get('checkpoint') or '/nonexistent')).expanduser().resolve())
        fixed = []
        if kind == 'checkpoint':
            fixed = [str(cfg[x]) for x in ('checkpoint', 'inpaint_checkpoint') if cfg.get(x)]
        fixed += list(explicit)
        found, visited, seen_dirs = {}, 0, set()

        def add_row(p, root, trusted=False):
            if len(found) >= MAX_FILES:
                return
            try:
                p = p.expanduser().resolve()
                key = str(p)
                if key in found:
                    return
                present = p.exists()
                if not present and not include_missing:
                    return
                fmt = 'diffusers' if p.is_dir() else p.suffix.lstrip('.').lower()
                if present and p.is_dir():
                    if kind != 'checkpoint':
                        return
                    # A config/tokenizer cache can also contain model_index.json. It is not a checkpoint.
                    self._inspect_diffusers_dir(p)
                elif present and p.suffix.lower() == '.safetensors':
                    try:
                        d = self._classify(p)
                        # Automatic folder scans are intentionally strict: only confirmed SDXL files of the
                        # requested type are listed. Unknown files can still be linked explicitly after confirmation.
                        if not trusted and (d['family'] != 'sdxl' or d['kind'] != kind):
                            return
                    except (OSError, ValueError, DownloadError):
                        if not trusted:
                            return
                elif present and not (trusted and p.suffix.lower() == '.ckpt'):
                    return
                enabled = availability.get(key, True)
                if not enabled and not include_disabled:
                    return
                e = explicit.get(key)
                managed_root = (self.models_root/('SDXL' if kind == 'checkpoint' else 'loras/SDXL')).resolve()
                managed = p.is_relative_to(managed_root)
                inpaint_active = kind == 'checkpoint' and key == str(Path(str(cfg.get('inpaint_checkpoint') or '/nonexistent')).expanduser().resolve())
                found[key] = {'id': hashlib.sha256(key.encode()).hexdigest()[:24], 'name': p.name, 'path': key,
                    'root': str(root), 'kind': kind, 'format': fmt, 'present': present, 'active': key == active,
                    'inpaint_active': inpaint_active, 'generation_enabled': enabled, 'managed': managed,
                    'reference_id': e['id'] if e else None, 'size_bytes': p.stat().st_size if p.is_file() else None,
                    'origin': 'linked' if e else ('active' if key == active else 'folder'),
                    'legacy': fmt == 'ckpt'}
                if kind == 'lora':
                    found[key].update(training_id=hashlib.sha1(key.encode('utf-8', errors='replace')).hexdigest()[:16] if managed else None)
            except (OSError, ValueError, RuntimeError):
                return

        for raw in fixed:
            try:
                p = Path(raw).expanduser()
                add_row(p, p.parent, trusted=True)
            except (OSError, ValueError):
                continue
        for raw in roots:
            try:
                root = self._path(str(raw))
            except (OSError, ValueError):
                continue
            if not root.is_dir():
                continue
            stack = [(root, 0)]
            while stack and visited < MAX_VISITED and len(found) < MAX_FILES:
                current, depth = stack.pop()
                try:
                    sig = current.resolve()
                    if sig in seen_dirs:
                        continue
                    seen_dirs.add(sig)
                    if (current/'model_index.json').is_file():
                        if kind == 'checkpoint':
                            add_row(current, root)
                        continue  # Don't list individual Diffusers components as checkpoints.
                    children = sorted(current.iterdir(), key=lambda p: p.name.lower())
                except OSError:
                    continue
                for child in children:
                    visited += 1
                    if visited > MAX_VISITED or len(found) >= MAX_FILES:
                        break
                    if child.name.startswith('.'):
                        continue
                    if child.is_dir():
                        if depth < MAX_DEPTH and not child.is_symlink():
                            stack.append((child, depth+1))
                    elif child.suffix.lower() == '.safetensors':
                        add_row(child, root)
                    elif kind == 'checkpoint' and child.suffix.lower() == '.ckpt':
                        # Legacy checkpoints already present remain visibly marked, not offered by new imports.
                        add_row(child, root, trusted=True)
        return sorted(found.values(), key=lambda x: (not x['active'], x['name'].casefold(), x['path']))

    def inventory(self, config=None, extra_lora_roots=()):
        cfg = config or {}
        return {'checkpoint': self.scan('checkpoint', cfg, include_missing=True, include_disabled=True),
                'lora': self.scan('lora', cfg, extra_lora_roots, include_missing=True, include_disabled=True),
                'sources': [{**s, 'present': Path(s['path']).exists()} for s in self.sources()],
                'limits': {'max_files_per_type': MAX_FILES, 'max_depth': MAX_DEPTH,
                           'note': 'Bounded scan; symlink directories are not recursively followed.'}}
