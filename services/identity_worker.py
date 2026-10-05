# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
from core.runtime_env import initialize_environment, protect_worker, MODELS_ROOT, SHARED_ROOT, settings
initialize_environment()
from core.sdxl_config import single_file_config
from core.gpu_session import gpu_session
import os, sys, json, time, threading, traceback, gc, math, importlib, importlib.util
from pathlib import Path
from flask import Flask, request, jsonify

HOST=os.getenv('CREATOR_IDENTITY_WORKER_HOST','127.0.0.1')
PORT=int(os.getenv('CREATOR_IDENTITY_WORKER_PORT','8301'))
MODEL_ROOT=Path(os.getenv('CREATOR_IDENTITY_MODEL_ROOT',str(MODELS_ROOT/"Identity"))).expanduser()
INSTANTID_ROOT=Path(os.getenv('CREATOR_IDENTITY_INSTANTID_ROOT',str(MODEL_ROOT/'InstantID'))).expanduser()
FACE_ROOT=Path(os.getenv('CREATOR_IDENTITY_INSIGHTFACE_ROOT',str(MODEL_ROOT/'insightface'))).expanduser()
INSTANTID_FACE_PACK=os.getenv('CREATOR_IDENTITY_INSTANTID_FACE_PACK',os.getenv('CREATOR_IDENTITY_FACE_PACK','antelopev2'))
SWAP_FACE_PACK=os.getenv('CREATOR_IDENTITY_SWAP_FACE_PACK','buffalo_l')
SWAPPER_MODEL=Path(os.getenv('CREATOR_IDENTITY_SWAPPER_MODEL',str(MODEL_ROOT/'inswapper_128.onnx'))).expanduser()
VENDOR_ROOT=Path(os.getenv('CREATOR_IDENTITY_VENDOR_ROOT',str(SHARED_ROOT/"identity/vendor/InstantID"))).expanduser()
BASE_SDXL=os.getenv('CREATOR_IDENTITY_BASE_SDXL',str(MODELS_ROOT/"SDXL/sd_xl_base_1.0.safetensors"))

app=Flask(__name__)
protect_worker(app)
lock=threading.Lock()
state={'thread':None,'job_id':None,'mode':None,'last_error':'','started_at':time.time()}
cache={'pipe':None,'mode':None,'base_model':None,'lora_signature':'','instantid_face_app':None,'instantid_det_size':None,'swap_face_app':None,'swap_det_size':None,'swapper':None}


def _safe(v):
    if isinstance(v,Path):return str(v)
    if isinstance(v,float):return v if math.isfinite(v) else None
    if isinstance(v,dict):return {str(k):_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_safe(x) for x in v]
    try:
        if hasattr(v,'item') and callable(v.item):return _safe(v.item())
    except Exception:pass
    return v


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(_safe(data),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def log(job,msg,level='INFO',**fields):
    p=Path(job['output_dir'])/'job.log';p.parent.mkdir(parents=True,exist_ok=True)
    line=f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}"
    if fields:line+=' | '+' '.join(f'{k}={v}' for k,v in fields.items())
    with p.open('a',encoding='utf-8') as f:f.write(line+'\n')
    print(f"[IDENTITY:{job.get('id')}] {line}",flush=True)


def progress(job,**kw):
    d={'status':'running','phase':'running','progress':0.0,'updated_at':time.time(),**kw}
    atomic_json(Path(job['output_dir'])/'progress.json',d)


def dependency_probe():
    d={'python':sys.version.split()[0]}
    try:
        import torch;d.update(torch=torch.__version__,cuda=torch.version.cuda,cuda_available=bool(torch.cuda.is_available()),gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')
    except Exception as e:d['torch_error']=str(e)
    for name in ('diffusers','transformers','insightface','onnxruntime','cv2'):
        try:
            m=__import__(name);d[name]=getattr(m,'__version__','OK')
        except Exception as e:d[name+'_error']=str(e)
    return d


def refresh_identity_paths():
    global MODEL_ROOT,INSTANTID_ROOT,FACE_ROOT,VENDOR_ROOT,SWAPPER_MODEL,INSTANTID_FACE_PACK,SWAP_FACE_PACK,_identity_signature
    from core.identity_paths import resolve_identity_paths
    p=resolve_identity_paths(settings(),MODELS_ROOT,SHARED_ROOT)
    if globals().get('_identity_signature')!=p['path_signature']:
        unload_all()
        for mod in list(sys.modules):
            if mod.startswith('pipeline_stable_diffusion_xl_instantid') or mod=='ip_adapter' or mod.startswith('ip_adapter.'):
                sys.modules.pop(mod,None)
        old=str(VENDOR_ROOT)
        if old in sys.path:sys.path.remove(old)
        MODEL_ROOT=Path(p['identity_root']);INSTANTID_ROOT=Path(p['instantid_root']);FACE_ROOT=Path(p['insightface_root'])
        VENDOR_ROOT=Path(p['vendor_root']);SWAPPER_MODEL=Path(p['swapper_path'])
        INSTANTID_FACE_PACK=p['instantid_face_pack'];SWAP_FACE_PACK=p['swap_face_pack'];_identity_signature=p['path_signature']
    return p

def _pack_ready(pack):
    d=FACE_ROOT/'models'/pack
    return d.is_dir() and any(p.stat().st_size>0 for p in d.glob('*.onnx') if p.is_file())

def _instantid_vendor_required(img2img=True):
    from core.identity_paths import vendor_files
    return vendor_files(VENDOR_ROOT,img2img)

def _instantid_vendor_status(img2img=True):
    missing=[str(p) for p in _instantid_vendor_required(img2img) if not p.is_file() or not p.stat().st_size]
    return (not missing),missing


def _instantid_vendor_module(img2img=False):
    ready,missing=_instantid_vendor_status(img2img)
    if not ready:
        raise RuntimeError(
            'InstantID inference code is incomplete. Missing: '+', '.join(missing)+
            '. Models → Identity → Code folder: select the original Creator shared/identity/vendor/InstantID, or install code only.'
        )
    root=str(VENDOR_ROOT)
    if root not in sys.path:sys.path.insert(0,root)
    module_name='pipeline_stable_diffusion_xl_instantid_img2img' if img2img else 'pipeline_stable_diffusion_xl_instantid'
    class_name='StableDiffusionXLInstantIDImg2ImgPipeline' if img2img else 'StableDiffusionXLInstantIDPipeline'
    try:
        mod=importlib.import_module(module_name)
    except Exception as e:
        raise RuntimeError(f'InstantID pipeline import failed from {VENDOR_ROOT}: {e}') from e
    if not hasattr(mod,class_name) or not hasattr(mod,'draw_kps'):
        raise RuntimeError(f'InstantID pipeline module at {getattr(mod,"__file__",VENDOR_ROOT)} is incomplete; missing {class_name} or draw_kps.')
    return mod


def model_probe():
    from core.model_registry import load_registry
    from core.identity_paths import identity_files
    s=identity_files({**settings(),'identity_root':str(MODEL_ROOT),'identity_instantid_root':str(INSTANTID_ROOT),'identity_insightface_root':str(FACE_ROOT),'identity_vendor':str(VENDOR_ROOT),'identity_swapper_model':str(SWAPPER_MODEL),'instantid_face_pack':INSTANTID_FACE_PACK,'swap_face_pack':SWAP_FACE_PACK},MODELS_ROOT,SHARED_ROOT)
    base=load_registry()['models'][0]['config'].get('checkpoint') or BASE_SDXL
    return {**s,'base_sdxl':base,'base_sdxl_exists':bool(base and Path(base).exists()),
        'controlnet_ready':s['controlnet_config_ready'] and s['controlnet_weights_ready'],
        'adapter_ready':s['instantid_adapter_ready'],'swapper_model':s['swapper_path'],
        'txt2img_pipeline_ready':s['txt2img_code_ready'],
        'path_signature':globals().get('_identity_signature',s['path_signature'])}


def unload_all():
    try:
        cache.update(pipe=None,mode=None,base_model=None,lora_signature='',instantid_face_app=None,instantid_det_size=None,swap_face_app=None,swap_det_size=None,swapper=None)
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try:torch.cuda.ipc_collect()
            except Exception:pass
    except Exception:pass


def _reset_instantid_pipe():
    """Drop only the diffusion pipeline after a failed inference; keep face-analysis models cached."""
    try:
        cache.update(pipe=None,mode=None,base_model=None,lora_signature='')
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            try: torch.cuda.ipc_collect()
            except Exception: pass
    except Exception:
        pass


def _face_app(kind='instantid',det_size=640):
    # ONNX Runtime GPU can reuse CUDA/cuDNN shipped with the private PyTorch runtime.
    # Import torch first, as recommended by ORT, before InsightFace creates sessions.
    import torch  # noqa: F401
    from insightface.app import FaceAnalysis
    det_size=max(128,min(2048,int(det_size or 640)))
    if kind=='swap':
        key='swap_face_app'; size_key='swap_det_size'; pack=SWAP_FACE_PACK
    else:
        key='instantid_face_app'; size_key='instantid_det_size'; pack=INSTANTID_FACE_PACK
    if cache[key] is not None and cache.get(size_key)==det_size:return cache[key]
    if not _pack_ready(pack):raise RuntimeError(f'Face model pack {pack} missing. Configure your locally licensed models in Setup.')
    providers=['CUDAExecutionProvider','CPUExecutionProvider']
    fa=FaceAnalysis(name=pack,root=str(FACE_ROOT),providers=providers)
    absent=[x for x in ('detection','recognition') if x not in fa.models]
    if absent:raise RuntimeError(f'Face pack {pack} is missing model tasks {absent}. Checked: {FACE_ROOT / "models" / pack}')
    fa.prepare(ctx_id=0,det_size=(det_size,det_size))
    cache[key]=fa;cache[size_key]=det_size
    return fa


def _faces(img_pil,kind='instantid',det_size=640):
    import cv2, numpy as np
    arr=cv2.cvtColor(np.asarray(img_pil.convert('RGB')),cv2.COLOR_RGB2BGR)
    return _face_app(kind,det_size).get(arr)


def _select_face(img_pil,kind='instantid',selector='largest',det_size=640):
    faces=_faces(img_pil,kind,det_size)
    if not faces:raise RuntimeError('No face detected in image.')
    selector=(selector or 'largest').lower()
    if selector=='leftmost':return min(faces,key=lambda f:float((f.bbox[0]+f.bbox[2])/2))
    if selector=='rightmost':return max(faces,key=lambda f:float((f.bbox[0]+f.bbox[2])/2))
    if selector=='center':
        w,h=img_pil.size;cx,cy=w/2,h/2
        return min(faces,key=lambda f:(float((f.bbox[0]+f.bbox[2])/2)-cx)**2+(float((f.bbox[1]+f.bbox[3])/2)-cy)**2)
    return max(faces,key=lambda f:float((f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1])))


def _largest_face(img_pil,kind='instantid'):
    return _select_face(img_pil,kind,'largest',640)


def _cos(a,b):
    import numpy as np
    a=np.asarray(a,dtype=np.float32);b=np.asarray(b,dtype=np.float32)
    na=float(np.linalg.norm(a));nb=float(np.linalg.norm(b))
    return float(np.dot(a,b)/(max(na,1e-8)*max(nb,1e-8)))


def _identity_reference(ref_paths,job=None):
    """InstantID was trained around the raw antelopev2 ArcFace embedding.
    Use the FIRST reference as the actual conditioning identity; extra refs are diagnostics only.
    This avoids the old v0.1.53 normalized-average embedding that weakened/moved identity.
    """
    import numpy as np
    from PIL import Image
    if not ref_paths:raise RuntimeError('At least one face reference is required.')
    primary_img=Image.open(ref_paths[0]).convert('RGB')
    primary_face=_largest_face(primary_img,'instantid')
    emb=np.asarray(primary_face.embedding,dtype=np.float32)  # deliberately RAW, as official InstantID example
    if not np.isfinite(emb).all():raise RuntimeError('Primary face embedding contains non-finite values.')
    if job:
        log(job,'Primary InstantID reference',pack=INSTANTID_FACE_PACK,embedding_norm=f'{float(np.linalg.norm(emb)):.4f}',det_score=f'{float(getattr(primary_face,"det_score",0.0)):.4f}')
        for i,p in enumerate(ref_paths[1:],start=2):
            try:
                im=Image.open(p).convert('RGB');face=_largest_face(im,'instantid')
                sim=_cos(emb,face.embedding)
                log(job,'Extra reference diagnostic only',reference=i,cosine_similarity=f'{sim:.4f}')
                if sim<0.25:log(job,'Extra reference has low similarity to primary identity',level='WARN',reference=i,cosine_similarity=f'{sim:.4f}')
            except Exception as e:log(job,'Extra reference diagnostic failed',level='WARN',reference=i,error=str(e))
    return emb,primary_face,primary_img


def _set_scheduler(pipe,name):
    from services.image_worker import set_scheduler
    set_scheduler(pipe,name)


def _lora_signature(loras):
    parts=[]
    for item in (loras or [])[:4]:
        try:parts.append(f"{Path(str(item.get('path') or '')).expanduser()}@{float(item.get('strength',1.0)):.6f}")
        except Exception:pass
    return "|".join(parts)


def _load_identity_loras(pipe,loras,job=None):
    from services.image_worker import _load_single_lora
    loaded=[];names=[];weights=[]
    for i,item in enumerate(loras or []):
        path=Path(item.get('path') or '').expanduser()
        if not path.is_file():raise RuntimeError('LoRA missing: '+str(path))
        name=f'identity_lora_{i}'
        _load_single_lora(pipe,path,name)
        names.append(name);weights.append(float(item.get('strength',1.0)));loaded.append(str(path))
    if names:pipe.set_adapters(names,adapter_weights=weights)
    return loaded


def _load_instantid_pipeline(base_model,generation_mode='txt2img',scheduler='default',loras=None,job=None):
    generation_mode='img2img' if generation_mode=='img2img' else 'txt2img'
    cache_mode='instantid_'+generation_mode
    lora_sig=_lora_signature(loras)
    if cache['pipe'] is not None and cache['mode']==cache_mode and cache['base_model']==str(base_model) and cache.get('lora_signature','')==lora_sig:
        _set_scheduler(cache['pipe'],scheduler);return cache['pipe']
    cache['pipe']=None;cache['mode']=None;cache['base_model']=None;cache['lora_signature']='';gc.collect()
    import torch
    if torch.cuda.is_available():torch.cuda.empty_cache()
    from diffusers import ControlNetModel
    vendor=_instantid_vendor_module(img2img=(generation_mode=='img2img'))
    Pipe=vendor.StableDiffusionXLInstantIDImg2ImgPipeline if generation_mode=='img2img' else vendor.StableDiffusionXLInstantIDPipeline
    control=ControlNetModel.from_pretrained(str(INSTANTID_ROOT/'ControlNetModel'),torch_dtype=torch.float16,local_files_only=True)
    kwargs={'controlnet':control,'torch_dtype':torch.float16,'local_files_only':True}
    p=Path(base_model)
    if not p.exists():raise RuntimeError(f'SDXL checkpoint/model not found: {p}')
    pipe=Pipe.from_single_file(str(p),config=single_file_config(),**kwargs) if p.is_file() else Pipe.from_pretrained(str(p),**kwargs)
    pipe.to('cuda')
    pipe.load_ip_adapter_instantid(str(INSTANTID_ROOT/'ip-adapter.bin'))
    loaded=_load_identity_loras(pipe,loras,job=job)
    _set_scheduler(pipe,scheduler)
    try:pipe.enable_vae_tiling()
    except Exception:pass
    cache['pipe']=pipe;cache['mode']=cache_mode;cache['base_model']=str(base_model);cache['lora_signature']=lora_sig
    if job is not None:log(job,'InstantID SDXL generator loaded',base_model=str(p),lora_count=len(loaded))
    return pipe


def _load_swap_refine_pipeline(base_model,scheduler='default',loras=None,job=None):
    cache_mode='swap_refine'
    lora_sig=_lora_signature(loras)
    if cache['pipe'] is not None and cache['mode']==cache_mode and cache['base_model']==str(base_model) and cache.get('lora_signature','')==lora_sig:
        _set_scheduler(cache['pipe'],scheduler);return cache['pipe']
    cache['pipe']=None;cache['mode']=None;cache['base_model']=None;cache['lora_signature']='';gc.collect()
    import torch
    if torch.cuda.is_available():torch.cuda.empty_cache()
    from diffusers import StableDiffusionXLImg2ImgPipeline
    p=Path(base_model)
    if not p.exists():raise RuntimeError(f'SDXL checkpoint/model not found for swap refine: {p}')
    kwargs={'torch_dtype':torch.float16,'local_files_only':True}
    pipe=StableDiffusionXLImg2ImgPipeline.from_single_file(str(p),config=single_file_config(),**kwargs) if p.is_file() else StableDiffusionXLImg2ImgPipeline.from_pretrained(str(p),**kwargs)
    pipe.to('cuda')
    loaded=_load_identity_loras(pipe,loras,job=job)
    _set_scheduler(pipe,scheduler)
    try:pipe.enable_vae_tiling()
    except Exception:pass
    cache['pipe']=pipe;cache['mode']=cache_mode;cache['base_model']=str(base_model);cache['lora_signature']=lora_sig
    if job is not None:log(job,'Swap refine SDXL generator loaded',base_model=str(p),lora_count=len(loaded))
    return pipe


def _resize_multiple8(im):
    from PIL import Image
    w,h=im.size
    nw=max(64,(w//8)*8);nh=max(64,(h//8)*8)
    return im if (nw,nh)==(w,h) else im.resize((nw,nh),Image.Resampling.LANCZOS)


def _run_swap_refine(job,image):
    import torch
    base_model=job.get('base_model') or BASE_SDXL
    scheduler=job.get('swap_refine_scheduler') or job.get('scheduler') or 'default'
    pipe=_load_swap_refine_pipeline(base_model,scheduler,job.get('loras') or [],job)
    original_size=image.size
    init=_resize_multiple8(image.convert('RGB'))
    steps=max(1,int(job.get('swap_refine_steps') or 24))
    guidance=float(job.get('swap_refine_guidance') or 4.5)
    strength=max(0.01,min(1.0,float(job.get('swap_refine_denoise') or 0.18)))
    seed=int(job.get('swap_refine_seed',job.get('seed',-1)) or -1)
    if seed<0:seed=int.from_bytes(os.urandom(4),'little')
    gen=torch.Generator(device='cuda').manual_seed(seed)
    prompt=(job.get('prompt') or '').strip() or 'photorealistic face, natural skin texture, realistic lighting, detailed eyes, seamless face integration'
    negative=(job.get('negative_prompt') or '').strip() or 'painting, illustration, wax skin, deformed face, blurry, low quality, text, watermark'
    log(job,'Starting optional SDXL face-swap refine',base_model=base_model,denoise=strength,steps=steps,guidance=guidance,scheduler=scheduler,seed=seed)
    out=pipe(prompt=prompt,negative_prompt=negative,image=init,strength=strength,num_inference_steps=steps,guidance_scale=guidance,generator=gen).images[0]
    if out.size!=original_size:
        from PIL import Image
        out=out.resize(original_size,Image.Resampling.LANCZOS)
    log(job,'SDXL face-swap refine completed',output_size=f'{out.width}x{out.height}',seed=seed)
    return out,seed


def _load_swapper():
    if cache['swapper'] is not None:return cache['swapper']
    if not SWAPPER_MODEL.exists():
        raise RuntimeError(f'True Face Swap model missing: {SWAPPER_MODEL}. Put a properly licensed inswapper_128.onnx there, or use InstantID generation.')
    import insightface
    pack=SWAP_FACE_PACK
    if not _pack_ready(pack):raise RuntimeError(f'Face model pack {pack} missing at {FACE_ROOT / "models" / pack}.')
    providers=['CUDAExecutionProvider','CPUExecutionProvider']
    try:sw=insightface.model_zoo.get_model(str(SWAPPER_MODEL),providers=providers)
    except TypeError:sw=insightface.model_zoo.get_model(str(SWAPPER_MODEL))
    if sw is None:raise RuntimeError(f'Could not load swap model: {SWAPPER_MODEL}')
    cache['swapper']=sw
    return sw


def _resize_official(im,max_side=1280,min_side=1024,size=None):
    """Aspect-preserving resize matching InstantID's reference helper; no forced square distortion."""
    from PIL import Image
    w,h=im.size
    if size and size[0]>0 and size[1]>0:
        w_new=max(64,int(size[0])//64*64);h_new=max(64,int(size[1])//64*64)
    else:
        ratio=min_side/min(h,w)
        w1,h1=round(w*ratio),round(h*ratio)
        ratio=max_side/max(w1,h1)
        w_new=max(64,(round(w1*ratio)//64)*64);h_new=max(64,(round(h1*ratio)//64)*64)
    return im.resize((w_new,h_new),Image.Resampling.LANCZOS)


def _face_mask(image,face,pad=0.18):
    import numpy as np
    from PIL import Image
    w,h=image.size
    x1,y1,x2,y2=[float(x) for x in face.bbox]
    bw=x2-x1;bh=y2-y1
    x1=max(0,int(x1-bw*pad));x2=min(w,int(x2+bw*pad));y1=max(0,int(y1-bh*pad));y2=min(h,int(y2+bh*pad))
    arr=np.zeros((h,w,3),dtype=np.uint8);arr[y1:y2,x1:x2]=255
    return Image.fromarray(arr)


def _run_true_swap(job):
    import cv2, numpy as np
    from PIL import Image
    refs=job.get('reference_paths') or []
    source=Image.open(refs[0]).convert('RGB')
    target=Image.open(job['base_image_path']).convert('RGB')
    det_size=int(job.get('detection_size') or 640)
    source_face=_select_face(source,'swap',job.get('source_face','largest'),det_size)
    target_faces=_faces(target,'swap',det_size)
    if not target_faces:raise RuntimeError('No face detected in target image.')
    if job.get('swap_all'):
        selected=target_faces
    else:
        selected=[_select_face(target,'swap',job.get('target_face','largest'),det_size)]
    swapper=_load_swapper()
    result_bgr=cv2.cvtColor(np.asarray(target),cv2.COLOR_RGB2BGR)
    for target_face in selected:
        result_bgr=swapper.get(result_bgr,target_face,source_face,paste_back=True)
        if result_bgr is None:raise RuntimeError('Face swap model returned no image.')
    result=Image.fromarray(cv2.cvtColor(result_bgr,cv2.COLOR_BGR2RGB))
    log(job,'True face swap completed',engine=SWAPPER_MODEL.name,source_pack=SWAP_FACE_PACK,target_size=f'{target.width}x{target.height}',faces_swapped=len(selected),det_size=det_size,target_selector=job.get('target_face','largest'))
    return result


def _run_instantid(job):
    import torch
    from PIL import Image
    refs=job.get('reference_paths') or []
    emb,ref_face,ref_img=_identity_reference(refs,job)
    generation_mode='img2img' if job.get('instantid_generation_mode')=='img2img' else 'txt2img'
    base_path=job.get('base_image_path') or ''
    if generation_mode=='img2img' and not base_path:
        raise RuntimeError('InstantID Img2Img requires a base image.')
    pose_path=job.get('pose_image_path') or base_path or ''
    pose_img=Image.open(pose_path).convert('RGB') if pose_path else ref_img
    requested_w=int(job.get('width') or 0);requested_h=int(job.get('height') or 0)
    explicit=(requested_w,requested_h) if requested_w>0 and requested_h>0 else None
    pose_img=_resize_official(pose_img,size=explicit)
    pose_face=_largest_face(pose_img,'instantid')
    vendor=_instantid_vendor_module(img2img=(generation_mode=='img2img'))
    kps=vendor.draw_kps(pose_img,pose_face.kps)
    use_region_mask=bool(job.get('enhance_face_region',False)) and generation_mode=='txt2img'
    control_mask=_face_mask(pose_img,pose_face,float(job.get('face_mask_padding',0.18))) if use_region_mask else None
    scheduler=job.get('scheduler') or 'default'
    pipe=_load_instantid_pipeline(job.get('base_model') or BASE_SDXL,generation_mode,scheduler,job.get('loras') or [],job)
    identity_strength=float(job.get('identity_strength',0.8));pose_strength=float(job.get('pose_strength',0.8))
    pipe.set_ip_adapter_scale(identity_strength)
    steps=max(1,int(job.get('steps',30)));guidance=float(job.get('guidance',5.0));seed=int(job.get('seed',-1))
    if seed<0:seed=int.from_bytes(os.urandom(4),'little')
    gen=torch.Generator(device='cuda').manual_seed(seed)
    prompt=(job.get('prompt') or '').strip() or 'high quality realistic portrait, natural skin texture, detailed face'
    negative=(job.get('negative_prompt') or '').strip() or 'lowres, low quality, worst quality, deformed face, mutated, cross-eyed, blurry, disfigured'
    cstart=max(0.0,min(1.0,float(job.get('control_guidance_start',0.0))))
    cend=max(cstart,min(1.0,float(job.get('control_guidance_end',1.0))))
    eta=max(0.0,float(job.get('eta',0.0)));clip_skip=int(job.get('clip_skip') or 0);guess_mode=bool(job.get('guess_mode',False))
    common=dict(prompt=prompt,negative_prompt=negative,image_embeds=emb,
                width=pose_img.width,height=pose_img.height,num_inference_steps=steps,guidance_scale=guidance,
                controlnet_conditioning_scale=pose_strength,control_guidance_start=cstart,control_guidance_end=cend,
                guess_mode=guess_mode,eta=eta,generator=gen)
    if clip_skip>0:common['clip_skip']=clip_skip
    if generation_mode=='img2img':
        init_img=Image.open(base_path).convert('RGB')
        init_img=_resize_official(init_img,size=(pose_img.width,pose_img.height))
        common.update(image=init_img,control_image=kps,strength=max(0.0,min(1.0,float(job.get('denoise_strength',0.35)))))
    else:
        common.update(image=kps)
        import inspect
        try:
            if 'control_mask' in inspect.signature(pipe.__call__).parameters:common['control_mask']=control_mask
        except Exception:pass
    log(job,'InstantID inference parameters',generation_mode=generation_mode,base_model=job.get('base_model') or BASE_SDXL,lora_count=len(job.get('loras') or []),pose_size=f'{pose_img.width}x{pose_img.height}',region_mask=use_region_mask,mask_padding=job.get('face_mask_padding',0.18) if use_region_mask else 'off',identity_strength=identity_strength,pose_strength=pose_strength,guidance=guidance,steps=steps)
    try:
        result=pipe(**common).images[0]
    except RuntimeError as e:
        msg=str(e)
        # The optional region-control implementation in upstream InstantID can fail
        # with a 2x CFG batch/spatial tensor mismatch on some image sizes.
        if use_region_mask and 'size of tensor' in msg and 'must match' in msg:
            log(job,'Region mask caused tensor-shape mismatch; retrying once without experimental mask',level='WARN',error=msg)
            common.pop('control_mask',None)
            _reset_instantid_pipe()
            pipe=_load_instantid_pipeline(job.get('base_model') or BASE_SDXL,generation_mode,scheduler,job.get('loras') or [],job)
            pipe.set_ip_adapter_scale(identity_strength)
            result=pipe(**common).images[0]
            use_region_mask=False
        else:
            raise
    log(job,'InstantID generation completed',pack=INSTANTID_FACE_PACK,generation_mode=generation_mode,identity_strength=identity_strength,pose_strength=pose_strength,denoise=job.get('denoise_strength') if generation_mode=='img2img' else 'n/a',control_start=cstart,control_end=cend,scheduler=scheduler,guess_mode=guess_mode,clip_skip=clip_skip,eta=eta,region_mask=use_region_mask,output_size=f'{result.width}x{result.height}',seed=seed)
    return result,seed


def _run_job_unlocked(job):
    from PIL import Image
    mode=job.get('mode','instantid')
    outdir=Path(job['output_dir']);outdir.mkdir(parents=True,exist_ok=True)
    try:
        log(job,'Identity job started',mode=mode,batch_id=job.get('batch_id') or 'single',test_label=job.get('test_label') or '')
        if mode=='face_swap':
            progress(job,status='running',phase='detecting_faces',progress=.12,phase_detail='Detecting source and target faces for true swap')
            result=_run_true_swap(job);seed=None
            if bool(job.get('refine_with_sdxl',False)):
                progress(job,status='running',phase='sdxl_refine',progress=.62,phase_detail='Refining swapped result with selected SDXL checkpoint')
                result,seed=_run_swap_refine(job,result)
        else:
            progress(job,status='running',phase='loading_identity',progress=.08,phase_detail='Loading antelopev2 + InstantID')
            progress(job,status='running',phase='generating',progress=.22,phase_detail='Running corrected InstantID conditioning')
            result,seed=_run_instantid(job)
        op=outdir/'output.png';result.save(op)
        progress(job,status='completed',phase='completed',progress=1.0,phase_detail='Identity output ready',output_path=str(op),seed=seed,completed_at=time.time())
        log(job,'Identity job completed',output=str(op),seed=seed if seed is not None else 'n/a')
    except Exception as e:
        tb=traceback.format_exc();state['last_error']=str(e)
        progress(job,status='failed',phase='failed',progress=0.0,error=str(e),traceback=tb)
        log(job,str(e),level='ERROR');print(tb,flush=True)
        if mode=='instantid' or bool(job.get('refine_with_sdxl',False)):
            _reset_instantid_pipe()
            log(job,'Diffusion pipeline cache reset after failure',level='WARN')
    finally:
        with lock:
            state['thread']=None;state['job_id']=None;state['mode']=None


def run_job(job):
    log(job,'Resolved Identity paths',**job.get('resolved_identity_paths',{}))
    with gpu_session('identity'):
        _run_job_unlocked(job)

@app.get('/health')
def health():
    dep=dependency_probe();mods=model_probe();busy=bool(state.get('thread') and state['thread'].is_alive())
    instantid_ready=bool(dep.get('cuda_available') and not dep.get('diffusers_error') and not dep.get('insightface_error') and mods['base_sdxl_exists'] and mods['controlnet_ready'] and mods['adapter_ready'] and mods['instantid_face_pack_ready'] and mods['txt2img_pipeline_ready'])
    swap_ready=bool(not dep.get('insightface_error') and mods['swap_face_pack_ready'] and mods['swapper_ready'])
    return jsonify(ok=True,online=True,busy=busy,job_id=state.get('job_id'),mode=state.get('mode'),ready=instantid_ready or swap_ready,instantid_ready=instantid_ready,swap_ready=swap_ready,last_error=state.get('last_error'),runtime=dep,models=mods)

@app.post('/unload')
def unload():
    if state.get('thread') and state['thread'].is_alive():return jsonify(ok=False,error='Identity generation is running.'),409
    unload_all();return jsonify(ok=True)

@app.post('/reload-config')
def reload_config():
    with lock:
        if state.get('thread') and state['thread'].is_alive():return jsonify(error='Identity is busy; the new paths will be used for the next job'),409
        refresh_identity_paths()
        return jsonify(ok=True,models=model_probe())

@app.post('/generate')
def generate():
    job=request.get_json(force=True) or {}
    with lock:
        if state.get('thread') and state['thread'].is_alive():return jsonify(error='Identity worker is busy',job_id=state.get('job_id')),409
        refresh_identity_paths()
        if not settings().get('identity_license_acknowledged'):return jsonify(error='Review the separate Identity model licenses in Setup before using these models.'),403
        mode=job.get('mode')
        if mode not in ('face_swap','instantid'):return jsonify(error='Unsupported identity mode'),400
        if not job.get('reference_paths'):return jsonify(error='At least one face reference is required'),400
        if mode=='face_swap' and not job.get('base_image_path'):return jsonify(error='Base image is required for Face Swap'),400
        mods=model_probe()
        if mode=='instantid':
            missing=[]
            if not Path(job.get('base_model') or BASE_SDXL).exists():missing.append('SDXL base model')
            if not mods.get('controlnet_ready'):missing.append('InstantID ControlNet')
            if not mods.get('adapter_ready'):missing.append('InstantID IP adapter')
            if not mods.get('instantid_face_pack_ready'):missing.append(f'InsightFace pack {INSTANTID_FACE_PACK}')
            code_ready=mods.get('vendor_ready') if job.get('instantid_generation_mode')=='img2img' else mods.get('txt2img_pipeline_ready')
            if not code_ready:
                vm=mods.get('vendor_missing') or []
                missing.append('InstantID inference code'+(f' ({", ".join(vm)})' if vm else ''))
            if missing:
                return jsonify(error='InstantID runtime is not ready: '+ '; '.join(missing)+'. Open Setup or run creator-sdxl doctor.'),503
        if mode=='face_swap':
            missing=[]
            if not mods.get('swap_face_pack_ready'):missing.append(f'InsightFace pack {SWAP_FACE_PACK}')
            if not mods.get('swapper_ready'):missing.append(str(SWAPPER_MODEL))
            if missing:return jsonify(error='True Face Swap runtime is not ready: '+ '; '.join(missing)),503
        job['resolved_identity_paths']={k:mods[k] for k in ('instantid_root','insightface_root','vendor_root','swapper_path','path_signature')}
        t=threading.Thread(target=run_job,args=(job,),daemon=True)
        state['thread']=t;state['job_id']=job.get('id');state['mode']=mode;t.start()
    return jsonify(ok=True,accepted=True,job_id=job.get('id'))

def main():
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    app.run(host=HOST,port=PORT,debug=False,use_reloader=False,threaded=True)


if __name__ == "__main__":
    main()
