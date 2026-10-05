"""Portable image/caption datasets shared by Dataset Studio and SDXL. No GPU imports."""
from __future__ import annotations
import io, json, os, re, shutil, tempfile, time, uuid, zipfile, stat, hashlib
from pathlib import Path, PurePosixPath
from PIL import Image, ImageOps

IMAGE_EXTS={'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}
MAX_IMAGES=2000
MAX_IMAGE_BYTES=64*1024**2
MAX_PIXELS=32_000_000
MAX_CAPTION=16384
MAX_ARCHIVE_BYTES=2*1024**3

class DatasetError(ValueError): pass

def safe_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',str(value or '')):raise DatasetError('Invalid dataset or image identifier')
    return str(value)

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def trigger_spans(caption,trigger):
    """Literal, case-sensitive whole-token matches; underscores form part of a token."""
    trigger=str(trigger or '').strip()
    if not trigger:return []
    pattern=(r'(?<!\w)' if trigger[0].isalnum() or trigger[0]=='_' else '')+re.escape(trigger)+(r'(?!\w)' if trigger[-1].isalnum() or trigger[-1]=='_' else '')
    return list(re.finditer(pattern,str(caption or '')))

def apply_trigger(caption,trigger,position='context'):
    caption=str(caption or '');trigger=str(trigger or '').strip()
    if position not in {'prefix','suffix','context'}:raise DatasetError('Unknown trigger placement')
    if not trigger or position=='context' or trigger_spans(caption,trigger):return caption
    return (trigger+', '+caption if position=='prefix' else caption+', '+trigger) if caption.strip() else trigger

def caption_report(dataset):
    trigger=str(dataset.get('trigger') or '').strip();issues=[]
    for it in dataset.get('items',[]):
        cap=str(it.get('caption') or '');spans=trigger_spans(cap,trigger);flags=[]
        if not cap.strip():flags.append('empty_caption')
        if trigger and not spans:flags.append('missing_trigger')
        if len(spans)>1:flags.append('repeated_trigger')
        # This is NOT a token count; actual tokenisation happens in the training runtime.
        if len(cap.split())>60:flags.append('check_token_length')
        issues.append({'id':it['id'],'trigger_count':len(spans),'trigger_offsets':[m.start() for m in spans],'warnings':flags,'words':len(cap.split()),'characters':len(cap)})
    return {'trigger':trigger,'images':len(issues),'empty':sum('empty_caption' in x['warnings'] for x in issues),'missing':sum('missing_trigger' in x['warnings'] for x in issues),'repeated':sum('repeated_trigger' in x['warnings'] for x in issues),'items':issues,'token_count':'not_computed','caption_positions':'prefix, suffix and in-context are valid; only saved caption text is trained'}

def check_image(data):
    if not data or len(data)>MAX_IMAGE_BYTES:raise DatasetError('Image empty or larger than 64 MiB')
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height>MAX_PIXELS:raise DatasetError('Image exceeds 32 megapixels')
            dims=im.size;im.verify()
        return dims
    except (OSError,Image.DecompressionBombError) as exc:raise DatasetError('Invalid image file') from exc

def create_dataset(root,name,trigger='',position='context'):
    if position not in {'prefix','suffix','context'}:raise DatasetError('Unknown trigger placement')
    did=uuid.uuid4().hex[:12];folder=Path(root)/did;(folder/'images').mkdir(parents=True)
    d={'id':did,'name':str(name or 'Dataset').strip()[:120],'trigger':str(trigger or '').strip()[:256],'trigger_position':position,'common_caption':'','items':[],'created_at':time.time()}
    atomic_json(folder/'dataset.json',d);return d

def get_dataset(root,did):
    p=Path(root)/safe_id(did)/'dataset.json'
    if not p.is_file():raise DatasetError('Dataset not found')
    return json.loads(p.read_text('utf8'))

def append_image(root,d,data,name,caption=''):
    if len(d['items'])>=MAX_IMAGES:raise DatasetError('Dataset limit: 2000 images')
    ext=Path(name).suffix.lower()
    if ext not in IMAGE_EXTS:raise DatasetError('Unsupported image extension')
    w,h=check_image(data);sha=hashlib.sha256(data).hexdigest()
    if any(x.get('sha256')==sha for x in d['items']):return None
    iid=uuid.uuid4().hex[:12];dest=(Path(root)/d['id']/'images'/f'{iid}{ext}').resolve();dest.write_bytes(data)
    it={'id':iid,'file':str(dest),'original_name':Path(name.replace('\\','/')).name[:240],'caption':str(caption)[:MAX_CAPTION],'width':w,'height':h,'sha256':sha,'caption_source':'manual','quality':'','warnings':[]}
    d['items'].append(it);return it

def export_zip(root,did,out):
    d=get_dataset(root,did);items=[]
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for n,it in enumerate(d['items'],1):
            p=Path(it['file']).resolve()
            if not p.is_relative_to((Path(root)/did).resolve()) or not p.is_file():raise DatasetError('Dataset image is outside its directory or missing')
            stem=f'{n:05d}';rel=f'images/{stem}{p.suffix.lower()}'
            z.write(p,rel);z.writestr(f'images/{stem}.txt',str(it.get('caption') or '').encode('utf8'))
            items.append({'file':rel,'caption_file':f'images/{stem}.txt','original_name':it.get('original_name',p.name),'caption':str(it.get('caption') or '')})
        manifest={'schema':'zetalvx.dataset','schema_version':1,'name':d['name'],'trigger':d.get('trigger',''),'trigger_position':d.get('trigger_position','context'),'items':items}
        z.writestr('dataset.json',json.dumps(manifest,ensure_ascii=False,indent=2));z.writestr('caption_report.json',json.dumps(caption_report(d),ensure_ascii=False,indent=2))
    return out

def import_zip(root,source):
    """Never extracts archive paths. Validates and stages all files before publishing."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    try:z=zipfile.ZipFile(source)
    except (zipfile.BadZipFile,OSError) as e:raise DatasetError('Invalid ZIP archive') from e
    stage=Path(tempfile.mkdtemp(prefix='.import-',dir=root))
    try:
        with z:
            infos=z.infolist()
            if len(infos)>MAX_IMAGES*3+20:raise DatasetError('Too many files in archive')
            total=0;names=set()
            for info in infos:
                name=info.filename
                path=PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or stat.S_ISLNK(info.external_attr>>16):raise DatasetError('Unsafe ZIP path')
                if name in names:raise DatasetError('Duplicate ZIP entry')
                names.add(name);total+=info.file_size
                if total>MAX_ARCHIVE_BYTES or info.file_size>MAX_IMAGE_BYTES:raise DatasetError('Archive exceeds unpacked size limits')
            manifests=[i for i in infos if PurePosixPath(i.filename).name=='dataset.json']
            meta={}
            if len(manifests)==1:
                if manifests[0].file_size>8*1024**2:raise DatasetError('Manifest too large')
                try:meta=json.loads(z.read(manifests[0]))
                except (ValueError,UnicodeDecodeError):raise DatasetError('Invalid dataset manifest')
            if not isinstance(meta,dict):raise DatasetError('Invalid dataset manifest')
            images=[i for i in infos if not i.is_dir() and PurePosixPath(i.filename).suffix.lower() in IMAGE_EXTS]
            if not images or len(images)>MAX_IMAGES:raise DatasetError('ZIP must contain 1 to 2000 images')
            d=create_dataset(stage,meta.get('name','Imported dataset'),meta.get('trigger',''),meta.get('trigger_position','context'))
            # Only portable metadata is read. Ignore arbitrary file paths in legacy manifests.
            entries={str(x.get('file','')):x for x in meta.get('items',[]) if isinstance(x,dict)}
            seen_stems=set()
            for info in images:
                stem=str(PurePosixPath(info.filename).with_suffix(''))
                if stem in seen_stems:raise DatasetError('Two image files share the same caption stem')
                seen_stems.add(stem);capfile=stem+'.txt';entry=entries.get(info.filename,{})
                cap=str(entry.get('caption') or '')
                if capfile in names:
                    if z.getinfo(capfile).file_size>MAX_CAPTION*4:raise DatasetError('Caption file too large')
                    cap=z.read(capfile).decode('utf-8-sig')
                if len(cap)>MAX_CAPTION:raise DatasetError('Caption too long')
                it=append_image(stage,d,z.read(info),entry.get('original_name') or PurePosixPath(info.filename).name,cap)
                if it:it['caption_source']='imported'
            final=root/d['id']
            for it in d['items']:it['file']=str((final/'images'/Path(it['file']).name).resolve())
            atomic_json(stage/d['id']/'dataset.json',d)
            os.rename(stage/d['id'],final)
            return d
    except (zipfile.BadZipFile,UnicodeDecodeError,KeyError) as e:raise DatasetError('Corrupt archive or non-UTF8 caption') from e
    finally:shutil.rmtree(stage,ignore_errors=True)
