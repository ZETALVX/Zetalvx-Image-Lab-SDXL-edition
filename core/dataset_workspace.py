"""Integrated dataset editor for SDXL Training.

The on-disk schema, ZIP format and trigger functions are the SAME as Dataset
Studio (core.dataset_exchange). This is a host adapter, not another dataset store.
There are no model/GPU imports here. The host supplies the shared caption lock.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from .dataset_exchange import (
    DatasetError, IMAGE_EXTS, MAX_IMAGES, MAX_CAPTION, MAX_IMAGE_BYTES,
    atomic_json, safe_id, check_image, create_dataset, get_dataset,
    append_image, apply_trigger, caption_report, import_zip, export_zip,
)

MAX_UPLOAD_BYTES = 120 * 1024**2
ACTIVE_TRAINING = {'queued', 'running', 'starting', 'stopping', 'cancelling'}


class DatasetConflict(DatasetError):
    """An optimistic edit conflicted with a caption saved elsewhere."""
    def __init__(self, message, current=None):
        super().__init__(message)
        self.current = current


class DatasetBusy(DatasetError):
    pass


class Workspace:
    def __init__(self, root, jobs, lock=None, caption_active=None):
        self.root = Path(root).resolve()
        self.jobs = Path(jobs).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = lock or threading.RLock()
        self.caption_active = caption_active or (lambda did: False)

    def folder(self, did):
        p = self.root / safe_id(did)
        if p.is_symlink() or not p.resolve().is_relative_to(self.root):
            raise DatasetError('Unsafe dataset directory')
        return p

    def read(self, did):
        with self.lock:
            p = self.folder(did) / 'dataset.json'
            if p.is_symlink():
                raise DatasetError('Unsafe dataset manifest')
            d = get_dataset(self.root, did)
            if d.get('id') != did or not isinstance(d.get('items'), list):
                raise DatasetError('Invalid dataset manifest')
            return d

    def active_jobs(self, did):
        safe_id(did)
        active = []
        for p in self.jobs.glob('*/job.json'):
            try:
                job = json.loads(p.read_text('utf8'))
                if job.get('dataset_id') != did:
                    continue
                progress_file = p.parent / 'progress.json'
                progress = json.loads(progress_file.read_text('utf8')) if progress_file.is_file() else {}
                if progress.get('status', job.get('status')) in ACTIVE_TRAINING:
                    active.append(job.get('id') or p.parent.name)
            except (ValueError, OSError):
                continue
        return active

    def editable(self, did, structural=False):
        active = self.active_jobs(did)
        if active:
            raise DatasetBusy('Dataset is used by an active training job: ' + ', '.join(active))
        if structural and self.caption_active(did):
            raise DatasetBusy('Stop captioning before adding or removing dataset images')

    def info(self, d):
        report = caption_report(d)
        trigger = str(d.get('trigger') or '').strip()
        need = sum(not str(x.get('caption') or '').strip() or
                   (bool(trigger) and str(x.get('caption') or '').strip() == trigger)
                   for x in d['items'])
        return dict(report, needs_caption=need, captioned=len(d['items'])-need,
                    active_training_jobs=self.active_jobs(d['id']),
                    captioning=bool(self.caption_active(d['id'])))

    def response(self, d):
        return {'ok': True, 'dataset': d, 'report': self.info(d)}

    def create(self, payload):
        if not isinstance(payload, dict):
            raise DatasetError('JSON object required')
        name = self.text(payload.get('name', ''), 120)
        trigger = self.text(payload.get('trigger', ''), 256)
        common = self.text(payload.get('common_caption', ''), MAX_CAPTION)
        model = self.text(payload.get('vision_model_id', ''), 80)
        with self.lock:
            d = create_dataset(self.root, name, trigger,
                               payload.get('trigger_position', payload.get('position', 'context')))
            d['common_caption'] = common
            d['vision_model_id'] = model
            atomic_json(self.folder(d['id'])/'dataset.json', d)
            return d

    @staticmethod
    def text(value, limit):
        if not isinstance(value, str) or len(value) > limit:
            raise DatasetError(f'Text must be a string of at most {limit} characters')
        if '\x00' in value:
            raise DatasetError('NUL characters are not accepted')
        return value

    def update(self, did, payload):
        if not isinstance(payload, dict):
            raise DatasetError('JSON object required')
        with self.lock:
            self.editable(did)
            d = self.read(did)
            expected = payload.get('expected', {})
            expected_caps = payload.get('expected_captions', {})
            caps = payload.get('captions', {})
            if not all(isinstance(x, dict) for x in (expected, expected_caps, caps)):
                raise DatasetError('Invalid caption changes')
            # Validate ALL edits before touching any file.
            known = {x['id']: x for x in d['items']}
            for iid, value in caps.items():
                safe_id(iid)
                if iid not in known:
                    raise DatasetConflict('This image was removed. Reload the dataset before saving.', d)
                self.text(value, MAX_CAPTION)
                if iid in expected_caps and known[iid].get('caption', '') != expected_caps[iid] and known[iid].get('caption', '') != value:
                    raise DatasetConflict('Caption changed elsewhere. Your draft is kept; reload before replacing it.', d)
            for key, limit in [('name',120),('trigger',256),('common_caption',MAX_CAPTION),('vision_model_id',80)]:
                if key in payload:
                    value = self.text(payload[key], limit)
                    if key in expected and d.get(key, '') != expected[key] and d.get(key, '') != value:
                        raise DatasetConflict('Dataset settings changed elsewhere. Reload before saving.', d)
                    d[key] = value.strip() if key in ('name','trigger','vision_model_id') else value
            position = payload.get('trigger_position', payload.get('position'))
            if position is not None:
                if position not in ('prefix','suffix','context'):
                    raise DatasetError('Unknown trigger placement')
                if 'trigger_position' in expected and d.get('trigger_position','context') != expected['trigger_position'] and d.get('trigger_position','context') != position:
                    raise DatasetConflict('Trigger placement changed elsewhere. Reload before saving.', d)
                d['trigger_position'] = position
            for iid, caption in caps.items():
                known[iid].update(caption=caption, caption_source='manual', caption_flags=[], caption_updated_at=time.time())
            d['updated_at'] = time.time()
            atomic_json(self.folder(did)/'dataset.json', d)
            return d

    def uploads(self, did, files, common_caption=None):
        """Atomic image + TXT ingestion, duplicate detection and safe legacy matching.

        TXT-only additions can fill missing captions but never replace a written
        caption. Supplied TXT are preserved verbatim; triggers are a separate action.
        """
        files = list(files)
        if not files:
            raise DatasetError('Choose images and optional matching TXT files')
        if len(files) > MAX_IMAGES*2:
            raise DatasetError('Too many files')
        # Read and validate before staging/committing anything.
        total = 0
        images = []
        captions = {}
        stems = set()
        for f in files:
            name = Path(str(f.filename or '').replace('\\','/')).name
            ext = Path(name).suffix.lower()
            if ext not in IMAGE_EXTS | {'.txt'}:
                raise DatasetError('Unsupported dataset file: ' + name)
            cap = MAX_CAPTION*4 + 3 if ext=='.txt' else MAX_IMAGE_BYTES
            data = f.stream.read(cap+1)
            total += len(data)
            if len(data)>cap or total>MAX_UPLOAD_BYTES:
                raise DatasetError('Upload limit: 120 MiB; each image must be at most 64 MiB')
            stem = Path(name).stem
            if ext=='.txt':
                if stem in captions:
                    raise DatasetError('Duplicate caption filename: ' + name)
                try: caption=data.decode('utf-8-sig')
                except UnicodeDecodeError as e: raise DatasetError('Caption files must use UTF-8') from e
                captions[stem]=self.text(caption,MAX_CAPTION)
            else:
                if stem in stems:
                    raise DatasetError('Two images share the same caption stem: '+stem)
                stems.add(stem)
                check_image(data)
                images.append((name,stem,data,hashlib.sha256(data).hexdigest()))
        with self.lock:
            self.editable(did,structural=True)
            d=self.read(did)
            old_count=len(d['items'])
            # Old Creator datasets may predate SHA metadata. Calculate only for
            # managed existing files; no modification of their bytes or captions.
            for it in d['items']:
                if not it.get('sha256'):
                    p=self.image_path(did,it['id'],d)
                    it['sha256']=self.file_hash(p)
            existing_by_stem={}
            for it in d['items']:
                existing_by_stem.setdefault(Path(it.get('original_name') or '').stem,[]).append(it)
            unknown=set(captions)-stems-set(existing_by_stem)
            if unknown:
                raise DatasetError('No matching image for caption: '+', '.join(sorted(unknown)[:5]))
            for stem in set(captions)-stems:
                if len(existing_by_stem.get(stem,[]))!=1:
                    raise DatasetError('Ambiguous existing image name for caption: '+stem)
            stage=Path(tempfile.mkdtemp(prefix='.upload-',dir=self.root))
            (stage/did/'images').mkdir(parents=True)
            installed=[]
            try:
                duplicated=0
                for name,stem,data,sha in images:
                    if any(x.get('sha256')==sha for x in d['items']):
                        duplicated+=1
                        continue
                    caption=captions.get(stem, common_caption if common_caption is not None else d.get('common_caption',''))
                    it=append_image(stage,d,data,name,caption or '')
                    if it:
                        it['caption_source']='imported' if stem in captions else 'manual'
                imported_captions=preserved=0
                for stem in set(captions)-stems:
                    it=existing_by_stem[stem][0]
                    if not str(it.get('caption') or '').strip() or str(it.get('caption') or '').strip()==d.get('trigger'):
                        it.update(caption=captions[stem],caption_source='imported',caption_flags=[])
                        imported_captions+=1
                    else:preserved+=1
                for it in d['items'][old_count:]:
                    src=Path(it['file']);dest=self.folder(did)/'images'/src.name
                    if dest.exists(): raise DatasetError('Unexpected image filename collision')
                    os.replace(src,dest);installed.append(dest);it['file']=str(dest.resolve())
                d['updated_at']=time.time()
                atomic_json(self.folder(did)/'dataset.json',d)
                return dict(self.response(d),added=len(d['items'])-old_count,duplicates=duplicated,
                            captions_imported=imported_captions,captions_preserved=preserved)
            except BaseException:
                for p in installed:p.unlink(missing_ok=True)
                raise
            finally:shutil.rmtree(stage,ignore_errors=True)

    @staticmethod
    def file_hash(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as f:
            for part in iter(lambda:f.read(1024**2),b''):h.update(part)
        return h.hexdigest()

    def image_path(self,did,iid,dataset=None):
        safe_id(iid)
        d=dataset or self.read(did)
        it=next((x for x in d['items'] if x['id']==iid),None)
        if not it:raise DatasetError('Image not found')
        p=Path(it.get('file') or '')
        if p.is_symlink() or not p.resolve().is_relative_to(self.folder(did).resolve()) or not p.is_file():
            raise DatasetError('Dataset image is outside its directory or missing')
        return p.resolve()

    def remove_item(self,did,iid):
        with self.lock:
            self.editable(did,structural=True)
            d=self.read(did);p=self.image_path(did,iid,d)
            d['items']=[x for x in d['items'] if x['id']!=iid]
            atomic_json(self.folder(did)/'dataset.json',d)
            p.unlink(missing_ok=True)
            return d

    def remove(self,did):
        with self.lock:
            self.editable(did,structural=True)
            d=self.read(did)
            shutil.rmtree(self.folder(did))
            return {'id':did,'name':d.get('name') or did}

    def apply(self,did):
        with self.lock:
            self.editable(did)
            d=self.read(did);changed=0
            for it in d['items']:
                cap=apply_trigger(it.get('caption',''),d.get('trigger',''),d.get('trigger_position','context'))
                if cap!=it.get('caption',''):
                    it.update(caption=cap,caption_source='manual',caption_flags=[]);changed+=1
            atomic_json(self.folder(did)/'dataset.json',d)
            return dict(self.response(d),changed=changed)

    def import_archive(self,source):
        with self.lock:return import_zip(self.root,source)

    def export_archive(self,did,out):
        with self.lock:return export_zip(self.root,safe_id(did),out)

    def preflight(self,did):
        with self.lock:
            if self.caption_active(did):
                raise DatasetBusy('Wait or stop captioning before using this dataset for training')
            self.editable(did)
            d=self.read(did)
            if not d['items']:raise DatasetError('Add at least one image to the dataset')
            for it in d['items']:self.image_path(did,it['id'],d)
            return self.response(d)
