# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
from core.runtime_env import initialize_environment, protect_worker, MODELS_ROOT
initialize_environment()
from core.gpu_session import gpu_session
from core.sdxl_config import single_file_config
import threading
#!/usr/bin/env python3
import os,sys,gc,traceback,inspect,json,time
from pathlib import Path
from flask import Flask,request,jsonify
from PIL import Image,ImageFilter

app=Flask(__name__)
protect_worker(app)
_execution_lock=threading.Lock()
loaded={"key":None,"pipe":None,"lora_signature":""}

def versions():
    out={"python":sys.version.split()[0]}
    for name in ("torch","diffusers","transformers","safetensors","accelerate","peft"):
        try:
            mod=__import__(name); out[name]=getattr(mod,"__version__","OK")
        except Exception as e: out[name]="MISSING: "+str(e)
    try:
        import torch
        out["cuda_available"]=torch.cuda.is_available()
        out["cuda_device"]=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        if torch.cuda.is_available():
            free,total=torch.cuda.mem_get_info()
            out["cuda_free_gib"]=round(free/1024**3,2)
            out["cuda_total_gib"]=round(total/1024**3,2)
    except Exception: pass
    return out

def dtype_from(cfg):
    import torch
    return {"float16":torch.float16,"bfloat16":torch.bfloat16,"float32":torch.float32}.get(cfg.get("dtype"),torch.bfloat16)

def clear():
    loaded["pipe"]=None; loaded["key"]=None; loaded["lora_signature"]=""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception: pass



def _enable_vae_memory(pipe):
    try:
        if hasattr(pipe,"enable_vae_tiling"): pipe.enable_vae_tiling()
        elif getattr(pipe,"vae",None) is not None and hasattr(pipe.vae,"enable_tiling"): pipe.vae.enable_tiling()
    except Exception: pass
    try:
        if hasattr(pipe,"enable_vae_slicing"): pipe.enable_vae_slicing()
    except Exception: pass

def _seed(job):
    import torch
    seed=int(job.get("seed",-1))
    if seed<0: seed=int(torch.randint(0,2**31-1,(1,)).item())
    return seed

def _generator(seed):
    import torch
    # CPU generator is friendlier to mixed CPU/GPU device maps.
    return torch.Generator(device="cpu").manual_seed(seed)


class JobCancelled(RuntimeError):
    pass

def _write_job_progress(job,phase,step_current=0,step_total=0,progress=None,**extra):
    path=job.get("progress_path")
    if not path:return
    try:
        started=float(job.get("started_epoch") or time.time())
        if progress is None:
            progress=(float(step_current)/float(step_total)) if step_total else 0.0
        payload={
            "job_id":job.get("job_id"),
            "phase":phase,
            "step_current":int(step_current or 0),
            "step_total":int(step_total or 0),
            "progress":max(0.0,min(1.0,float(progress))),
            "elapsed_seconds":max(0.0,time.time()-started),
            "updated_at":time.time(),
            **extra
        }
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass

def _check_cancel(job):
    p=job.get("cancel_path")
    if p and Path(p).exists():
        raise JobCancelled("Job cancelled by user.")

def _progress_args(pipe,job,total_steps):
    sig=inspect.signature(pipe.__call__).parameters
    if "callback_on_step_end" in sig:
        def cb(_pipe,step,timestep,callback_kwargs):
            _check_cancel(job)
            cur=int(step)+1
            _write_job_progress(job,"generating",cur,total_steps,cur/max(1,total_steps))
            return callback_kwargs
        return {"callback_on_step_end":cb}
    if "callback" in sig:
        def cb(step,timestep,latents):
            _check_cancel(job)
            cur=int(step)+1
            _write_job_progress(job,"generating",cur,total_steps,cur/max(1,total_steps))
        out={"callback":cb}
        if "callback_steps" in sig: out["callback_steps"]=1
        return out
    return {}

@app.get("/health")
def health():
    return jsonify(ok=True,runtime="native_worker",comfyui_required=False,python_executable=sys.executable,
                   versions=versions(),loaded=str(loaded["key"]) if loaded["key"] else None)

@app.post('/probe')
def probe():
    cfg=(request.get_json(force=True) or {}).get('config') or {}
    files={k:{'path':str(v),'exists':Path(str(v)).expanduser().exists()} for k,v in cfg.items() if k in ('checkpoint','inpaint_checkpoint','vae') and v}
    return jsonify(ok=True,provider='sdxl',files=files,capabilities=versions())

def _lora_signature(loras):
    parts=[]
    for item in loras or []:
        try:
            path=Path(str(item.get("path") or "")).expanduser().resolve()
            strength=float(item.get("strength",1.0))
            parts.append(f"{path}@{strength:.6f}")
        except Exception:
            pass
    return "|".join(parts)

def _text_encoder_has_legacy_text_model_prefix(text_encoder):
    if text_encoder is None:return True
    try:
        names={name for name,_ in text_encoder.named_modules()}
        return "text_model" in names or any(name.startswith("text_model.") for name in names)
    except Exception:
        return True


def _normalize_kohya_sdxl_for_transformers5(pipe,state_dict):
    """Normalize classic Kohya SDXL TE keys for Transformers 5 flattened CLIPTextModel.

    Old Kohya files use keys such as:
      lora_te1_text_model_encoder_layers_0_...
    but Transformers>=5 exposes CLIP modules as:
      encoder.layers.0_...
    Diffusers' current Kohya converter can still emit the stale text_model prefix,
    leaving an empty PEFT rank map and raising IndexError: list index out of range.
    """
    te1_flat=not _text_encoder_has_legacy_text_model_prefix(getattr(pipe,"text_encoder",None))
    te2_flat=not _text_encoder_has_legacy_text_model_prefix(getattr(pipe,"text_encoder_2",None))
    if not (te1_flat or te2_flat):return state_dict,False
    changed=False;out={}
    for key,value in state_dict.items():
        nk=key
        if te1_flat:
            if nk.startswith("lora_te1_text_model_"):
                nk="lora_te1_"+nk[len("lora_te1_text_model_"):];changed=True
            elif nk.startswith("lora_te_text_model_"):
                nk="lora_te_"+nk[len("lora_te_text_model_"):];changed=True
        if te2_flat and nk.startswith("lora_te2_text_model_"):
            nk="lora_te2_"+nk[len("lora_te2_text_model_"):];changed=True
        out[nk]=value
    return out,changed


def _load_single_lora(pipe,path,adapter_name):
    # For .safetensors load into a dict first so we can repair legacy Kohya SDXL
    # text-encoder namespaces before Diffusers/PEFT sees them. Do NOT retry on the
    # same pipeline after a failed adapter injection: PEFT can leave the adapter
    # name partially registered, which caused the misleading "adapter already in use" error.
    try:
        if path.suffix.lower()==".safetensors":
            from safetensors.torch import load_file
            state_dict=load_file(str(path),device="cpu")
            state_dict,normalized=_normalize_kohya_sdxl_for_transformers5(pipe,state_dict)
            pipe.load_lora_weights(state_dict,adapter_name=adapter_name)
            return "state_dict+transformers5_normalized" if normalized else "state_dict"
        pipe.load_lora_weights(str(path),adapter_name=adapter_name)
        return "direct_file"
    except Exception as e:
        raise RuntimeError(f"Could not load LoRA {path.name}: {type(e).__name__}: {e}") from e


def apply_loras(pipe,loras):
    if not hasattr(pipe,"load_lora_weights"): return []
    names=[];weights=[];loaded_items=[]
    for i,item in enumerate(loras or []):
        path=Path(item.get("path") or "").expanduser()
        if not path.exists(): raise RuntimeError(f"LoRA not found: {path}")
        name=f"lora_{i}"
        load_mode=_load_single_lora(pipe,path,name)
        names.append(name);weights.append(float(item.get("strength",1.0)))
        loaded_items.append({"path":str(path),"strength":float(item.get("strength",1.0)),"load_mode":load_mode})
    if names:
        if hasattr(pipe,"set_adapters"):
            pipe.set_adapters(names,adapter_weights=weights)
        elif len(names)==1 and hasattr(pipe,"fuse_lora"):
            pipe.fuse_lora(lora_scale=weights[0])
        else:
            raise RuntimeError("This SDXL pipeline cannot apply the selected LoRA stack with the current Diffusers build.")
    return loaded_items

def load_sdxl(cfg,task,loras=None):
    import torch
    from core.execution_device import normalized_config
    cfg=normalized_config(cfg,torch.cuda.is_available())
    from diffusers import StableDiffusionXLPipeline,StableDiffusionXLImg2ImgPipeline,StableDiffusionXLInpaintPipeline
    checkpoint=cfg.get("checkpoint")
    if task=="inpaint":
        checkpoint=cfg.get("inpaint_checkpoint") or ""
        if not checkpoint: raise RuntimeError("SDXL inpainting requires 'inpaint_checkpoint' in Model configuration.")
        cls=StableDiffusionXLInpaintPipeline
    elif task in ("edit","img2img"):
        cls=StableDiffusionXLImg2ImgPipeline
    else:
        cls=StableDiffusionXLPipeline
    if not checkpoint or not Path(checkpoint).exists():
        raise RuntimeError(f"SDXL checkpoint not found: {checkpoint}")
    lora_sig=_lora_signature(loras or [])
    key=("sdxl",str(checkpoint),task,lora_sig,cfg.get("vae"),cfg.get("dtype"),cfg.get("memory_mode"),cfg.get("cpu_offload"),cfg.get("device"))
    if loaded["key"]==key and loaded["pipe"] is not None:return loaded["pipe"]
    clear()
    dtype=dtype_from(cfg)
    kwargs={"torch_dtype":dtype,"local_files_only":True}
    p=Path(checkpoint)
    if p.is_dir(): pipe=cls.from_pretrained(str(p),use_safetensors=True,**kwargs)
    else: pipe=cls.from_single_file(str(p),config=single_file_config(task=="inpaint"),use_safetensors=True,**kwargs)
    vae=cfg.get("vae")
    if vae and Path(vae).exists():
        try:
            from diffusers import AutoencoderKL
            pipe.vae=AutoencoderKL.from_single_file(vae,torch_dtype=dtype,local_files_only=True)
        except Exception as e: raise RuntimeError(f"Could not load custom SDXL VAE: {e}")
    if cfg.get("cpu_offload") or cfg.get("memory_mode") in ("cpu_offload","model_cpu_offload"):
        pipe.enable_model_cpu_offload()
    else: pipe.to(cfg.get("device","cuda"))
    try:
        apply_loras(pipe,loras or [])
    except Exception:
        clear()
        raise
    loaded.update(key=key,pipe=pipe,lora_signature=lora_sig)
    return pipe


def set_scheduler(pipe, name):
    if not hasattr(pipe, '_sdxl_default_scheduler'):
        pipe._sdxl_default_scheduler=(type(pipe.scheduler), dict(pipe.scheduler.config))
    cls, config=pipe._sdxl_default_scheduler
    if not name or name=='default':
        pipe.scheduler=cls.from_config(config);return
    from diffusers import DPMSolverMultistepScheduler, EulerDiscreteScheduler, EulerAncestralDiscreteScheduler, UniPCMultistepScheduler, DDIMScheduler
    choices={'dpmpp_2m':DPMSolverMultistepScheduler,'dpmpp_2m_karras':DPMSolverMultistepScheduler,'euler':EulerDiscreteScheduler,'euler_a':EulerAncestralDiscreteScheduler,'unipc':UniPCMultistepScheduler,'ddim':DDIMScheduler}
    if name not in choices:raise ValueError('Unsupported SDXL scheduler: '+str(name))
    kw={'algorithm_type':'dpmsolver++','use_karras_sigmas':name.endswith('karras')} if name.startswith('dpmpp') else {}
    pipe.scheduler=choices[name].from_config(config,**kw)

def run_sdxl(job,cfg):
    import torch
    task=job.get("task","generate");pipe=load_sdxl(cfg,task,job.get("loras") or [])
    set_scheduler(pipe,job.get("scheduler","default"))
    seed=_seed(job)
    # SDXL runs on one device in the current adapter.
    gen=torch.Generator(device=cfg.get("device","cuda")).manual_seed(seed)
    common=dict(prompt=job.get("prompt",""),negative_prompt=job.get("negative_prompt") or None,
                num_inference_steps=int(job.get("steps") or cfg.get("default_steps") or 30),
                guidance_scale=float(job.get("cfg") if job.get("cfg") is not None else cfg.get("default_cfg",7.0)),
                generator=gen)
    if task=="generate":
        common.update(width=int(job.get("width",1024)),height=int(job.get("height",1024)))
    elif task in ("edit","img2img"):
        src=job.get("source_path")
        if not src or not Path(src).exists(): raise RuntimeError("SDXL edit/img2img requires a source image.")
        source_image=Image.open(src).convert("RGB")
        common.update(image=source_image,width=source_image.width,height=source_image.height,
                      strength=float(job.get("strength",.6)))
    elif task=="inpaint":
        src=job.get("source_path");mask=job.get("mask_path")
        if not src or not Path(src).exists(): raise RuntimeError("Inpaint requires source image.")
        if not mask or not Path(mask).exists(): raise RuntimeError("Inpaint requires mask image.")
        source_image=Image.open(src).convert("RGB")
        mask_image=Image.open(mask).convert("L").resize(source_image.size,Image.Resampling.NEAREST)
        common.update(image=source_image,mask_image=mask_image,width=source_image.width,height=source_image.height,
                      strength=float(job.get("strength",.8)))
    total_steps=int(common.get("num_inference_steps") or 0)
    _write_job_progress(job,"generating",0,total_steps,0)
    common.update(_progress_args(pipe,job,total_steps))
    out=pipe(**common).images[0]
    _check_cancel(job)
    if task in ("edit","img2img","inpaint") and job.get("source_path") and Path(job["source_path"]).exists():
        original_size=Image.open(job["source_path"]).size
        if out.size!=original_size:
            out=out.resize(original_size,Image.Resampling.LANCZOS)
    _write_job_progress(job,"saving",total_steps,total_steps,1.0)
    op=Path(job["output_path"]);op.parent.mkdir(parents=True,exist_ok=True);out.save(op)
    return {"output_path":str(op),"seed":seed}


def run_sdxl_generic_inpaint(job,cfg):
    import torch
    src=job.get("source_path");mask=job.get("mask_path")
    if not src or not Path(src).exists():raise RuntimeError("Generic inpaint requires a source image.")
    if not mask or not Path(mask).exists():raise RuntimeError("Generic inpaint requires a mask image.")
    pipe=load_sdxl(cfg,"edit",job.get("loras") or [])
    set_scheduler(pipe,job.get("scheduler","default"))
    seed=_seed(job);gen=torch.Generator(device=cfg.get("device","cuda")).manual_seed(seed)
    original=Image.open(src).convert("RGB")
    total_steps=int(job.get("steps") or cfg.get("default_steps") or 30)
    callargs=dict(prompt=job.get("prompt",""),negative_prompt=job.get("negative_prompt") or None,
                  image=original,strength=float(job.get("strength",.65)),
                  num_inference_steps=total_steps,
                  guidance_scale=float(job.get("cfg") if job.get("cfg") is not None else cfg.get("default_cfg",7.0)),
                  generator=gen)
    _write_job_progress(job,"generating",0,total_steps,0)
    callargs.update(_progress_args(pipe,job,total_steps))
    edited=pipe(**callargs).images[0].convert("RGB").resize(original.size,Image.Resampling.LANCZOS)
    _check_cancel(job)
    mask_im=Image.open(mask).convert("L").resize(original.size,Image.Resampling.LANCZOS)
    blur=max(1,min(original.size)//300)
    if blur>0:mask_im=mask_im.filter(ImageFilter.GaussianBlur(blur))
    result=Image.composite(edited,original,mask_im)
    if result.size!=original.size:result=result.resize(original.size,Image.Resampling.LANCZOS)
    _write_job_progress(job,"saving",total_steps,total_steps,1)
    op=Path(job["output_path"]);op.parent.mkdir(parents=True,exist_ok=True);result.save(op)
    return {"output_path":str(op),"seed":seed,"fallback":"generic_masked_img2img",
            "width":result.width,"height":result.height,"source_width":original.width,"source_height":original.height}































@app.post('/unload')
def unload():
    # A waiting worker has no active GPU work; the owner requests this after locking.
    clear();return jsonify(ok=True)

@app.post('/execute')
def execute():
    d=request.get_json(force=True) or {};cfg=d.get('config') or {};job=d.get('job') or {}
    if d.get('provider')!='sdxl':return jsonify(ok=False,error='SDXL only'),400
    if not _execution_lock.acquire(False):return jsonify(ok=False,error='SDXL worker busy'),409
    try:
        _check_cancel(job)
        _write_job_progress(job,'waiting_gpu',0,int(job.get('steps') or 30),0)
        with gpu_session('image'):
            _write_job_progress(job,'loading_model',0,int(job.get('steps') or 30),0)
            if job.get('task')=='generic_inpaint':result=run_sdxl_generic_inpaint(job,cfg)
            else:result=run_sdxl(job,cfg)
        return jsonify(ok=True,provider='sdxl',**result)
    except Exception as e:
        clear()
        return jsonify(ok=False,error=str(e),traceback=traceback.format_exc()[-8000:]),500
    finally:_execution_lock.release()

def main():
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    app.run(host=os.getenv("CREATOR_IMAGE_WORKER_HOST","127.0.0.1"),
            port=int(os.getenv("CREATOR_IMAGE_WORKER_PORT","8299")),threaded=True)


if __name__ == "__main__":
    main()
