"""One Identity path contract for GUI, supervisor and inference worker.
No writes, model downloads or recursive scanning of external installations.
"""
from pathlib import Path
import hashlib, json, re

VENDOR_FILES = ('pipeline_stable_diffusion_xl_instantid.py',
    'pipeline_stable_diffusion_xl_instantid_img2img.py', 'ip_adapter/resampler.py',
    'ip_adapter/attention_processor.py', 'ip_adapter/utils.py')

def path(value):
    return Path(value).expanduser().absolute()

def vendor_files(root, img2img=True):
    return [path(root)/f for f in VENDOR_FILES if img2img or 'img2img' not in f]

def resolve_identity_paths(cfg, models_root, shared_root):
    models_root=path(models_root);shared_root=path(shared_root)
    standard=models_root/'Identity'
    root=path(cfg.get('identity_root') or standard)
    notes=[];origins={}
    def child(key, rel):
        value=str(cfg.get(key) or '').strip()
        # Older builds persisted absolute default children. Those aren't custom overrides.
        if not value or path(value)==standard/rel:
            origins[key]='identity_root';return root/rel
        origins[key]='custom';return path(value)
    iid=child('identity_instantid_root','InstantID')
    if (iid/'InstantID'/'ip-adapter.bin').is_file() and not (iid/'ip-adapter.bin').is_file():
        iid=iid/'InstantID';notes.append('InstantID parent folder recognized; using its InstantID subfolder.')
    face=child('identity_insightface_root','insightface')
    if face.name in ('antelopev2','buffalo_l') and face.parent.name=='models':
        face=face.parent.parent;notes.append('Face-pack path normalized to the InsightFace root (two levels up).')
    elif face.name=='models' and ((face/'antelopev2').is_dir() or (face/'buffalo_l').is_dir()):
        face=face.parent;notes.append('InsightFace models/ path normalized to its parent.')
    elif (face/'insightface'/'models').is_dir() and not (face/'models').is_dir():
        face=face/'insightface';notes.append('Identity parent folder recognized for InsightFace.')
    swap=child('identity_swapper_model','inswapper_128.onnx')
    vendor=path(cfg.get('identity_vendor') or shared_root/'identity/vendor/InstantID')
    # Offer the original app's code directory explicitly; never execute it silently.
    managed=shared_root/'identity/vendor'
    candidates=[vendor, root, iid, root.parent.parent/'shared/identity/vendor/InstantID',managed/'InstantID']
    if managed.is_dir():candidates.extend(sorted(managed.glob('InstantID-*'))[-20:])
    vendor_is_weights=(vendor/'ip-adapter.bin').is_file() or (vendor/'ControlNetModel').is_dir()
    if vendor_is_weights and not all(p.is_file() for p in vendor_files(vendor)):
        notes.append('The configured code directory contains weights. Install code separately or choose the folder containing the Python pipeline files.')
    candidate_reports=[]
    for p in dict.fromkeys(candidates):
        missing=[str(f) for f in vendor_files(p) if not f.is_file()]
        if p==vendor or not missing:candidate_reports.append({'path':str(p),'complete':not missing,'missing':missing})
    packs={}
    for key,default in [('instantid_face_pack','antelopev2'),('swap_face_pack','buffalo_l')]:
        name=str(cfg.get(key) or default)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ValueError('Invalid face pack name')
        packs[key]=name
    result={'identity_root':str(root),'instantid_root':str(iid),'insightface_root':str(face),
        'swapper_path':str(swap),'vendor_root':str(vendor),**packs,'path_notes':notes,
        'path_origins':origins,'vendor_candidates':candidate_reports,'vendor_points_to_weights':vendor_is_weights}
    result['path_signature']=hashlib.sha256(json.dumps({k:result[k] for k in ('identity_root','instantid_root','insightface_root','swapper_path','vendor_root',*packs)},sort_keys=True).encode()).hexdigest()[:20]
    return result

def identity_files(cfg, models_root, shared_root):
    s=resolve_identity_paths(cfg,models_root,shared_root)
    iid=path(s['instantid_root']);face=path(s['insightface_root']);vendor=path(s['vendor_root'])
    def exists(p):return p.is_file() and p.stat().st_size>0
    control=iid/'ControlNetModel';a=iid/'ip-adapter.bin';w=control/'diffusion_pytorch_model.safetensors'
    s.update(vendor_ready=all(exists(p) for p in vendor_files(vendor)),
        vendor_missing=[str(p) for p in vendor_files(vendor) if not exists(p)],
        txt2img_code_ready=all(exists(p) for p in vendor_files(vendor,False)),
        instantid_adapter_path=str(a),instantid_adapter_ready=exists(a),
        controlnet_dir=str(control),controlnet_config_ready=exists(control/'config.json'),
        controlnet_weights_ready=exists(w),controlnet_weights=[str(w)] if exists(w) else [],
        swapper_ready=exists(path(s['swapper_path'])))
    s['required_files']=[{'component':'adapter','path':str(a),'present':exists(a)},
        {'component':'controlnet config','path':str(control/'config.json'),'present':exists(control/'config.json')},
        {'component':'controlnet weights','path':str(w),'present':exists(w)},
        {'component':'swapper','path':s['swapper_path'],'present':s['swapper_ready']}]
    for key,pre in [('instantid_face_pack','instantid'),('swap_face_pack','swap')]:
        d=face/'models'/s[key];files=[p for p in sorted(d.glob('*.onnx')) if exists(p)] if d.is_dir() else []
        s[pre+'_face_pack_dir']=str(d);s[pre+'_face_pack_files']=[p.name for p in files];s[pre+'_face_pack_ready']=bool(files)
        s['required_files'].append({'component':s[key]+' ONNX (file presence only)','path':str(d),'present':bool(files)})
    s['instantid_enabled']=bool(cfg.get('identity_instantid_enabled',True));s['faceswap_enabled']=bool(cfg.get('identity_faceswap_enabled',True))
    s['license_acknowledged']=bool(cfg.get('identity_license_acknowledged',False))
    s['instantid_files_ready']=all(s[k] for k in ('vendor_ready','instantid_adapter_ready','controlnet_config_ready','controlnet_weights_ready','instantid_face_pack_ready'))
    s['face_swap_files_ready']=s['swap_face_pack_ready'] and s['swapper_ready']
    return s
