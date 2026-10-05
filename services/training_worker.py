# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.18; see BUILD_PROVENANCE.json and docs/TESTS_0_1_0_18.md.
from core.runtime_env import initialize_environment, protect_worker, MODELS_ROOT
initialize_environment()
from core.gpu_session import gpu_session
from core.sdxl_config import single_file_config
import os, json, time, random, shutil, threading, traceback, sys, gc, logging, math, re
from pathlib import Path
from flask import Flask, request, jsonify

HOST=os.environ.get("CREATOR_TRAINING_WORKER_HOST","127.0.0.1")
PORT=int(os.environ.get("CREATOR_TRAINING_WORKER_PORT","8300"))
WORKER_STARTED_AT=time.time()
app=Flask(__name__)
protect_worker(app)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
lock=threading.Lock()
state={"thread":None,"job_id":None,"stop":None,"last_event":"worker_started","last_error":""}


def _json_safe(value):
    # Strict JSON-safe conversion for progress/events/log metadata.
    # pathlib.Path values are common during checkpoint/final-output logging.
    if isinstance(value,Path):return str(value)
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,dict):return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,set,frozenset)):return [_json_safe(v) for v in value]
    try:
        # numpy scalar / torch scalar-like values, without importing either package here.
        if hasattr(value,"item") and callable(value.item):
            scalar=value.item()
            if scalar is not value:return _json_safe(scalar)
    except Exception:pass
    return value


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(_json_safe(data),ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    tmp.replace(path)


def _ts(t=None):
    return time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(t or time.time()))


def _append(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):f.write("\n")
        f.flush()


def job_log(job,message,level="INFO",**fields):
    """Human-readable per-job log + structured JSONL event + global stdout."""
    now=time.time()
    line=f"[{_ts(now)}] [{level}] {message}"
    if fields:
        compact=" ".join(f"{k}={v}" for k,v in fields.items() if v is not None and v!="")
        if compact:line+=f" | {compact}"
    out=Path(job["output_dir"])
    _append(out/"job.log",line)
    event={"ts":now,"time":_ts(now),"level":level,"message":message,**fields}
    _append(out/"events.jsonl",json.dumps(_json_safe(event),ensure_ascii=False,allow_nan=False))
    state["last_event"]=message
    if level in ("ERROR","FATAL"):state["last_error"]=message
    print(f"[TRAIN:{job.get('id','?')}] {line}",flush=True)


def gpu_snapshot():
    snap={}
    try:
        import torch
        snap["cuda_available"]=bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            snap["gpu"]=torch.cuda.get_device_name(0)
            snap["allocated_mib"]=round(torch.cuda.memory_allocated()/1024/1024,1)
            snap["reserved_mib"]=round(torch.cuda.memory_reserved()/1024/1024,1)
            try:
                free,total=torch.cuda.mem_get_info()
                snap["free_mib"]=round(free/1024/1024,1);snap["total_mib"]=round(total/1024/1024,1)
            except Exception:pass
    except Exception as e:snap["gpu_error"]=str(e)
    return snap


def tensor_diagnostics(t):
    """Small, JSON-safe tensor health summary for training diagnostics."""
    try:
        import torch
        d={"shape":list(t.shape),"dtype":str(t.dtype),"device":str(t.device)}
        if torch.is_floating_point(t) or t.is_complex():
            finite=torch.isfinite(t)
            d["finite"]=bool(finite.all().item())
            d["nan_values"]=int(torch.isnan(t).sum().item())
            d["inf_values"]=int(torch.isinf(t).sum().item())
            if bool(finite.any().item()):
                vals=t.detach()[finite].float()
                d["min"]=float(vals.min().item());d["max"]=float(vals.max().item())
        return _json_safe(d)
    except Exception as e:
        return {"diagnostic_error":str(e)}


def assert_finite(job,t,name,step=None,item=None):
    try:
        import torch
        if not (torch.is_floating_point(t) or t.is_complex()):return
        if bool(torch.isfinite(t).all().item()):return
        diag=tensor_diagnostics(t)
        progress(job,status="failed",phase="failed",phase_detail=f"Non-finite {name} detected",nonfinite_component=name,error=f"Non-finite {name} detected" + (f" at step {step}" if step is not None else ""),tensor_diagnostics=diag)
        job_log(job,f"Non-finite tensor detected: {name}",level="ERROR",step=step,item=item,diagnostics=diag)
        raise FloatingPointError(f"Non-finite {name} detected" + (f" at step {step}" if step is not None else ""))
    except FloatingPointError:
        raise


def assert_module_finite(job,module,name):
    import torch
    bad=[];checked=0
    for pname,param in module.named_parameters():
        if not param.requires_grad:continue
        if not (torch.is_floating_point(param) or param.is_complex()):continue
        checked+=1
        if not bool(torch.isfinite(param).all().item()):
            bad.append(pname)
            if len(bad)>=20:break
    if bad:
        job_log(job,f"Non-finite module weights detected: {name}",level="ERROR",count=len(bad),examples=bad[:10])
        raise FloatingPointError(f"Refusing to export {name}: non-finite weights detected ({len(bad)} tensor(s))")
    job_log(job,f"Finite-weight validation OK: {name}",tensors_checked=checked)


def export_complete_sdxl(unet,job,step):
    """Create a complete Diffusers SDXL model by combining the trained UNet with frozen base components."""
    import torch
    root=Path(job.get("full_register_dir") or str(MODELS_ROOT/"SDXL/trained"))
    root.mkdir(parents=True,exist_ok=True)
    safe="".join(c if c.isalnum() or c in "-_" else "_" for c in str(job.get("name") or job.get("id") or "sdxl_full"))[:80]
    dest=root/f"{safe}_step_{int(step):06d}"
    n=1
    while dest.exists():
        dest=root/f"{safe}_step_{int(step):06d}_{n}";n+=1
    progress(job,phase="exporting_full_model",phase_detail="Building complete SDXL model from base + trained UNet")
    job_log(job,"Loading frozen SDXL base components for complete model export",base_model=job["base_model"],destination=str(dest))
    base_pipe=load_pipeline(job["base_model"])
    # Training is finished: inference export is stored in fp16 to reduce disk/RAM footprint.
    unet=unet.to(device="cpu",dtype=torch.float16)
    base_pipe.register_modules(unet=unet)
    base_pipe.save_pretrained(str(dest),safe_serialization=True)
    manifest={
        "format":"diffusers_sdxl_complete",
        "family":"sdxl",
        "base_model":job["base_model"],
        "training_job_id":job.get("id"),
        "training_name":job.get("name"),
        "dataset_id":job.get("dataset_id"),
        "resolution":job.get("resolution"),
        "max_steps":job.get("max_steps"),
        "step":int(step),
        "learning_rate":job.get("learning_rate"),
        "seed":job.get("seed"),
        "created_at":time.time(),
        "note":"Complete SDXL Diffusers model: frozen base VAE/text encoders/tokenizers + fine-tuned UNet."
    }
    atomic_json(dest/"creator_training_manifest.json",manifest)
    del base_pipe
    gc.collect()
    if torch.cuda.is_available():torch.cuda.empty_cache()
    job_log(job,"Complete SDXL model exported",path=str(dest))
    return str(dest)


def runtime_info():
    v={"pid":os.getpid(),"worker_started_at":WORKER_STARTED_AT,"python":sys.version.split()[0]}
    try:
        import torch
        v["torch"]=torch.__version__;v["cuda"]=torch.version.cuda;v["cuda_available"]=bool(torch.cuda.is_available())
        if torch.cuda.is_available():v["gpu"]=torch.cuda.get_device_name(0)
    except Exception as e:v["torch_error"]=str(e)
    try:
        import diffusers;v["diffusers"]=diffusers.__version__
    except Exception as e:v["diffusers_error"]=str(e)
    try:
        import transformers;v["transformers"]=transformers.__version__
    except Exception as e:v["transformers_error"]=str(e)
    try:
        import accelerate;v["accelerate"]=accelerate.__version__
    except Exception as e:v["accelerate_error"]=str(e)
    try:
        import peft;v["peft"]=peft.__version__
    except Exception as e:v["peft_error"]=str(e)
    # diffusers 0.37.0 single-file SDXL loader is incompatible with transformers >= 5.6.
    compat=True;reason=""
    try:
        dv=tuple(int(x) for x in str(v.get("diffusers","0")).split(".")[:3])
        tv=tuple(int(x) for x in str(v.get("transformers","0")).split(".")[:2])
        if dv==(0,37,0) and tv>=(5,6):
            compat=False;reason="diffusers 0.37.0 + transformers >=5.6 breaks SDXL from_single_file CLIP loading; use the pinned SDXL edition runtime, not a shared external environment."
    except Exception:pass
    v["compatibility_ok"]=compat;v["compatibility_reason"]=reason
    return v


def progress(job, **kw):
    p=Path(job["output_dir"])/"progress.json"
    old={}
    try:old=json.loads(p.read_text(encoding="utf-8"))
    except Exception:pass
    now=time.time()
    old.update(kw)
    old["updated_at"]=now
    old["heartbeat_at"]=now
    old["worker_pid"]=os.getpid()
    old["worker_started_at"]=WORKER_STARTED_AT
    atomic_json(p,old)


def prep_image(path,resolution):
    from PIL import Image
    import numpy as np, torch
    im=Image.open(path).convert("RGB")
    scale=max(resolution/im.width,resolution/im.height)
    size=(max(resolution,round(im.width*scale)),max(resolution,round(im.height*scale)))
    im=im.resize(size,Image.Resampling.LANCZOS)
    left=(im.width-resolution)//2;top=(im.height-resolution)//2
    im=im.crop((left,top,left+resolution,top+resolution))
    a=np.asarray(im).astype("float32")/127.5-1.0
    return torch.from_numpy(a).permute(2,0,1).unsqueeze(0)


def save_trainable_state(unet, optimizer, scheduler, job, step):
    import torch
    cp=Path(job["output_dir"])/"checkpoints"/f"step_{step:06d}"
    job_log(job,"Saving checkpoint",step=step,path=str(cp))
    cp.mkdir(parents=True,exist_ok=True)
    trainable={}
    for n,p in unet.named_parameters():
        if not p.requires_grad:continue
        v=p.detach().cpu()
        if job.get("mode")=="full" and (torch.is_floating_point(v) or v.is_complex()):v=v.to(torch.float16)
        trainable[n]=v
    torch.save(trainable,cp/"trainable_state.pt")
    torch.save(optimizer.state_dict(),cp/"optimizer.pt")
    if scheduler is not None:torch.save(scheduler.state_dict(),cp/"scheduler.pt")
    atomic_json(cp/"trainer_state.json",{"step":step,"max_steps":job["max_steps"],"mode":job["mode"],"saved_at":time.time()})
    if job["mode"]=="lora":
        save_lora(unet,cp,job,step,register=False)
    else:
        atomic_json(cp/"full_checkpoint_manifest.json",{
            "format":"creator_exact_resume_checkpoint","family":"sdxl","mode":"full",
            "step":step,"base_model":job.get("base_model"),
            "note":"Exact-resume training checkpoint. Final inference UNet/complete SDXL are exported when training completes."
        })
    job_log(job,"Checkpoint saved",step=step,path=str(cp))
    return cp


def load_trainable_state(unet, optimizer, scheduler, cp, load_optimizer=True):
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    import torch
    cp=Path(cp)
    state_dict=torch.load(cp/"trainable_state.pt",map_location="cpu",weights_only=True)
    named=dict(unet.named_parameters())
    missing=[]
    for n,v in state_dict.items():
        if n in named:named[n].data.copy_(v.to(device=named[n].device,dtype=named[n].dtype))
        else:missing.append(n)
    if load_optimizer and (cp/"optimizer.pt").exists():optimizer.load_state_dict(torch.load(cp/"optimizer.pt",map_location="cpu",weights_only=True))
    if load_optimizer and scheduler is not None and (cp/"scheduler.pt").exists():scheduler.load_state_dict(torch.load(cp/"scheduler.pt",map_location="cpu",weights_only=True))
    st=json.loads((cp/"trainer_state.json").read_text(encoding="utf-8")) if (cp/"trainer_state.json").exists() else {"step":0}
    return int(st.get("step") or 0),missing


def save_lora(unet, directory, job, step, register=True):
    import torch
    from peft.utils import get_peft_model_state_dict
    from diffusers.utils import convert_state_dict_to_diffusers
    from diffusers import StableDiffusionXLPipeline
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    state_dict=get_peft_model_state_dict(unet)
    state_dict=convert_state_dict_to_diffusers(state_dict)
    bad=[]
    for name,t in state_dict.items():
        try:
            if (torch.is_floating_point(t) or t.is_complex()) and not bool(torch.isfinite(t).all().item()):bad.append(name)
        except Exception:pass
    if bad:
        raise FloatingPointError(f"Refusing to save LoRA with non-finite weights ({len(bad)} tensor(s)); first: {bad[:5]}")
    StableDiffusionXLPipeline.save_lora_weights(directory,unet_lora_layers=state_dict,safe_serialization=True)
    src=directory/"pytorch_lora_weights.safetensors"
    registered=None
    if register and src.exists():
        reg=Path(job["lora_register_dir"]);reg.mkdir(parents=True,exist_ok=True)
        safe="".join(c if c.isalnum() or c in "-_" else "_" for c in job["name"])[:80]
        registered=reg/f"{safe}_step_{step:06d}.safetensors"
        shutil.copy2(src,registered)
    return str(registered) if registered else None


def load_pipeline(base):
    import torch
    from diffusers import StableDiffusionXLPipeline
    p=Path(base)
    kwargs={"torch_dtype":torch.float16,"local_files_only":True}
    if p.is_dir():return StableDiffusionXLPipeline.from_pretrained(str(p),**kwargs)
    return StableDiffusionXLPipeline.from_single_file(str(p),config=single_file_config(),**kwargs)


from core.training_captions import training_caption, job_policy, clip_training_caption


def _caption_tokenizers(pipe):
    return [t for t in (getattr(pipe,"tokenizer",None),getattr(pipe,"tokenizer_2",None)) if t is not None]

def _effective_training_caption(pipe,item,dataset,job):
    cap=training_caption(item,dataset,job)
    for tok in _caption_tokenizers(pipe):cap=clip_training_caption(cap,dataset,tok)
    return cap

def _caption_token_diagnostics(pipe,items,dataset,job):
    toks=_caption_tokenizers(pipe)
    if not toks:return
    limit=min(int(getattr(t,"model_max_length",77) or 77) for t in toks);adjusted=[];remaining=[]
    for item in items:
        raw=training_caption(item,dataset,job);cap=raw
        for tok in toks:cap=clip_training_caption(cap,dataset,tok,int(getattr(tok,"model_max_length",77) or 77))
        try:
            raw_n=max(len(t(raw,truncation=False,add_special_tokens=True).input_ids) for t in toks)
            n=max(len(t(cap,truncation=False,add_special_tokens=True).input_ids) for t in toks)
            if raw_n>limit:adjusted.append((item.get("id"),raw_n,n))
            if any(len(t(cap,truncation=False,add_special_tokens=True).input_ids)>int(getattr(t,"model_max_length",77) or 77) for t in toks):remaining.append((item.get("id"),n))
        except Exception:pass
    progress(job,caption_policy=job_policy(job),caption_over_limit=len(remaining),caption_adjusted=len(adjusted),caption_limit=limit)
    if remaining:job_log(job,"Caption token warning remains after safe reduction",level="WARN",count=len(remaining),limit=limit,examples=remaining[:5])
    elif adjusted:job_log(job,"CLIP captions reduced for training; saved caption text preserved",count=len(adjusted),limit=limit,examples=adjusted[:5],trigger_position=dataset.get("trigger_position","context"))
    else:job_log(job,"Caption token check OK",count=len(items))


def _run_job_unlocked(job,resume_checkpoint="",weights_checkpoint=""):
    import torch
    from torch.nn import functional as F
    from diffusers import DDPMScheduler
    from peft import LoraConfig

    stop_event=state["stop"]
    job_policy(job)  # Reject unknown policies before touching the model.
    random.seed(job["seed"]);torch.manual_seed(job["seed"])
    if torch.cuda.is_available():torch.cuda.manual_seed_all(job["seed"])
    device="cuda" if torch.cuda.is_available() else "cpu"
    if device!="cuda":raise RuntimeError("SDXL training requires CUDA in this first Training Studio release.")

    info=runtime_info()
    if not info.get("compatibility_ok",True):raise RuntimeError(info.get("compatibility_reason") or "Training runtime compatibility check failed.")

    started=time.time()
    progress(job,status="running",phase="starting",phase_detail="Initializing training job",started_at=started,step=0,max_steps=job["max_steps"],progress=0.0,error="",traceback="")
    job_log(job,"="*70)
    job_log(job,"Training attempt started",name=job.get("name"),mode=job.get("mode"),resolution=job.get("resolution"),max_steps=job.get("max_steps"),save_every=job.get("save_every"))
    job_log(job,"Runtime",torch=info.get("torch"),cuda=info.get("cuda"),gpu=info.get("gpu"),diffusers=info.get("diffusers"),transformers=info.get("transformers"),peft=info.get("peft"),pid=os.getpid())
    job_log(job,"Initial GPU memory",**gpu_snapshot())

    dataset=json.loads(Path(job["dataset_path"]).read_text(encoding="utf-8"))
    items=dataset.get("items") or []
    if not items:raise RuntimeError("Dataset is empty.")
    job_log(job,"Dataset loaded",dataset_id=job.get("dataset_id"),items=len(items),trigger=dataset.get("trigger") or "-")
    if dataset.get("trigger"):
        job_log(job,"Training trigger policy",trigger=dataset.get("trigger"),policy=job_policy(job))

    progress(job,status="running",phase="loading_model",phase_detail="Loading SDXL pipeline",step=0,max_steps=job["max_steps"],progress=0.0)
    job_log(job,"Loading SDXL pipeline",base_model=job["base_model"])
    pipe=load_pipeline(job["base_model"])
    pipe.set_progress_bar_config(disable=True)
    job_log(job,"SDXL pipeline loaded",**gpu_snapshot())
    _caption_token_diagnostics(pipe,items,dataset,job)

    unet=pipe.unet;vae=pipe.vae;text_encoder=pipe.text_encoder;text_encoder_2=pipe.text_encoder_2
    noise_scheduler=DDPMScheduler.from_config(pipe.scheduler.config)

    progress(job,phase="caching_prompts",phase_detail="Encoding text captions",cache_current=0,cache_total=len(items))
    job_log(job,"Caching prompt embeddings",items=len(items))
    text_encoder.to(device);text_encoder_2.to(device)
    prompt_cache={}
    with torch.no_grad():
        for idx,item in enumerate(items):
            cap=_effective_training_caption(pipe,item,dataset,job)
            if cap not in prompt_cache:
                pe,_,pooled,_=pipe.encode_prompt(prompt=cap,device=device,do_classifier_free_guidance=False,num_images_per_prompt=1)
                assert_finite(job,pe,"prompt embeddings",item=item.get("id"))
                assert_finite(job,pooled,"pooled prompt embeddings",item=item.get("id"))
                prompt_cache[cap]=(pe.detach().cpu(),pooled.detach().cpu())
            progress(job,phase="caching_prompts",phase_detail=f"Encoding captions {idx+1}/{len(items)}",cache_current=idx+1,cache_total=len(items))
            if idx==0 or idx+1==len(items) or (idx+1)%10==0:job_log(job,"Prompt cache progress",current=idx+1,total=len(items),unique=len(prompt_cache))
    text_encoder.to("cpu");text_encoder_2.to("cpu")
    del text_encoder,text_encoder_2
    torch.cuda.empty_cache()
    job_log(job,"Prompt embeddings cached",unique=len(prompt_cache),**gpu_snapshot())

    progress(job,phase="caching_latents",phase_detail="Encoding dataset images",cache_current=0,cache_total=len(items))
    job_log(job,"Caching VAE latents",items=len(items),resolution=job["resolution"])
    # SDXL's stock VAE is numerically unsafe for training-time encoding in fp16.
    # Keep UNet/text inference in fp16, but encode dataset images in fp32.
    vae.to(device=device,dtype=torch.float32);latent_cache=[]
    job_log(job,"VAE moved to FP32 for stable latent encoding",vae_dtype=str(vae.dtype),force_upcast=getattr(vae.config,"force_upcast",None),**gpu_snapshot())
    with torch.no_grad():
        for idx,item in enumerate(items):
            pix=prep_image(item["file"],job["resolution"]).to(device=device,dtype=torch.float32)
            assert_finite(job,pix,"input pixels",item=item.get("id"))
            lat=vae.encode(pix).latent_dist.sample()*vae.config.scaling_factor
            assert_finite(job,lat,"VAE latent",item=item.get("id"))
            cap=_effective_training_caption(pipe,item,dataset,job)
            latent_cache.append((lat.detach().cpu(),cap,item.get("id")))
            progress(job,phase="caching_latents",phase_detail=f"Encoding images {idx+1}/{len(items)}",cache_current=idx+1,cache_total=len(items))
            if idx==0 or idx+1==len(items) or (idx+1)%5==0:job_log(job,"Latent cache progress",current=idx+1,total=len(items),item=item.get("id"))
    vae.to("cpu");del vae,pipe
    torch.cuda.empty_cache()
    job_log(job,"VAE latents cached",items=len(latent_cache),**gpu_snapshot())

    progress(job,phase="preparing_optimizer",phase_detail="Preparing trainable parameters")
    unet.to(device)
    if job.get("gradient_checkpointing",True):
        try:
            unet.enable_gradient_checkpointing();job_log(job,"Gradient checkpointing enabled")
        except Exception as e:job_log(job,"Gradient checkpointing could not be enabled",level="WARN",error=str(e))

    if job["mode"]=="lora":
        unet.requires_grad_(False)
        lcfg=LoraConfig(r=int(job["rank"]),lora_alpha=int(job["alpha"]),init_lora_weights="gaussian",target_modules=["to_q","to_k","to_v","to_out.0"])
        unet.add_adapter(lcfg)
        fp32_params=0
        for p in unet.parameters():
            if p.requires_grad and p.dtype!=torch.float32:
                p.data=p.data.float();fp32_params+=1
        job_log(job,"LoRA adapter attached",rank=job["rank"],alpha=job["alpha"],fp32_trainable_tensors=fp32_params)
    else:
        # Full fine-tuning keeps master trainable weights in FP32. Autocast still performs the forward pass in FP16.
        # This avoids GradScaler/FP16-gradient failures and is intended primarily for high-VRAM servers.
        unet.to(device=device,dtype=torch.float32)
        unet.requires_grad_(True)
        job_log(job,"Full UNet parameters enabled with FP32 master weights",level="WARN",unet_dtype=str(unet.dtype),**gpu_snapshot())

    params=[p for p in unet.parameters() if p.requires_grad]
    if not params:raise RuntimeError("No trainable SDXL parameters were selected.")
    trainable_count=sum(p.numel() for p in params)
    job_log(job,"Trainable parameters ready",parameters=trainable_count)

    optimizer_name=job.get("optimizer")
    if optimizer_name=="adamw8bit":
        try:
            import bitsandbytes as bnb
            optimizer=bnb.optim.AdamW8bit(params,lr=float(job["learning_rate"]));job_log(job,"Optimizer ready",optimizer="AdamW8bit",lr=job["learning_rate"])
        except Exception as e:
            job_log(job,"AdamW8bit unavailable; falling back to torch AdamW",level="WARN",error=str(e))
            optimizer=torch.optim.AdamW(params,lr=float(job["learning_rate"]))
    else:
        optimizer=torch.optim.AdamW(params,lr=float(job["learning_rate"]));job_log(job,"Optimizer ready",optimizer="AdamW",lr=job["learning_rate"])

    max_steps=int(job["max_steps"])
    scheduler=torch.optim.lr_scheduler.LambdaLR(optimizer,lambda s:max(0.1,1.0-s/max(1,max_steps)))
    scaler=torch.cuda.amp.GradScaler(enabled=True)
    job_log(job,"FP16 gradient scaler enabled",initial_scale=scaler.get_scale())
    start_step=0
    if resume_checkpoint:
        job_log(job,"Loading exact resume checkpoint",path=resume_checkpoint)
        start_step,missing=load_trainable_state(unet,optimizer,scheduler,resume_checkpoint,load_optimizer=True)
        job_log(job,"Resume checkpoint loaded",step=start_step,missing=len(missing))
    elif weights_checkpoint:
        job_log(job,"Loading continuation weights",path=weights_checkpoint)
        _,missing=load_trainable_state(unet,optimizer,scheduler,weights_checkpoint,load_optimizer=False)
        start_step=0;job_log(job,"Continuation weights loaded",missing=len(missing))

    accum=max(1,int(job.get("gradient_accumulation") or 1))
    optimizer.zero_grad(set_to_none=True)
    t0=time.time();order=list(range(len(latent_cache)));random.shuffle(order)
    progress(job,status="running",phase="training",phase_detail=f"Training step {start_step}/{max_steps}",step=start_step,max_steps=max_steps,progress=start_step/max_steps if max_steps else 0.0,cache_current=len(items),cache_total=len(items))
    job_log(job,"Training loop started",start_step=start_step,max_steps=max_steps,grad_accum=accum,first_latent=tensor_diagnostics(latent_cache[0][0]) if latent_cache else None,**gpu_snapshot())
    log_every=max(1,min(10,max_steps//20 if max_steps>=20 else 1))

    for local_step in range(start_step,max_steps):
        if stop_event.is_set():
            job_log(job,"Stop requested; saving recoverable checkpoint",level="WARN",step=local_step)
            cp=save_trainable_state(unet,optimizer,scheduler,job,local_step)
            progress(job,status="stopped",phase="stopped",phase_detail="Stopped by user after saving checkpoint",step=local_step,max_steps=max_steps,progress=local_step/max_steps,checkpoint=str(cp),elapsed_seconds=time.time()-t0)
            job_log(job,"Training stopped cleanly",level="WARN",step=local_step,checkpoint=str(cp))
            return

        if local_step and local_step%len(order)==0:random.shuffle(order)
        lat,cap,item_id=latent_cache[order[local_step%len(order)]]
        lat=lat.to(device=device,dtype=unet.dtype)
        pe,pooled=prompt_cache[cap]
        pe=pe.to(device=device,dtype=unet.dtype);pooled=pooled.to(device=device,dtype=unet.dtype)
        step_no=local_step+1
        assert_finite(job,lat,"training latent",step=step_no,item=item_id)
        assert_finite(job,pe,"training prompt embeddings",step=step_no,item=item_id)
        assert_finite(job,pooled,"training pooled embeddings",step=step_no,item=item_id)
        noise=torch.randn_like(lat)
        timesteps=torch.randint(0,noise_scheduler.config.num_train_timesteps,(lat.shape[0],),device=device).long()
        noisy=noise_scheduler.add_noise(lat,noise,timesteps)
        assert_finite(job,noise,"training noise",step=step_no,item=item_id)
        assert_finite(job,noisy,"noisy latent",step=step_no,item=item_id)
        time_ids=torch.tensor([[job["resolution"],job["resolution"],0,0,job["resolution"],job["resolution"]]],device=device,dtype=pe.dtype)
        with torch.autocast(device_type="cuda",dtype=torch.float16):
            pred=unet(noisy,timesteps,encoder_hidden_states=pe,added_cond_kwargs={"text_embeds":pooled,"time_ids":time_ids}).sample
            assert_finite(job,pred,"UNet prediction",step=step_no,item=item_id)
            if noise_scheduler.config.prediction_type=="v_prediction":target=noise_scheduler.get_velocity(lat,noise,timesteps)
            else:target=noise
            assert_finite(job,target,"training target",step=step_no,item=item_id)
            loss=F.mse_loss(pred.float(),target.float(),reduction="mean")/accum
        if not bool(torch.isfinite(loss).all().item()):
            progress(job,status="failed",phase="failed",phase_detail=f"Non-finite loss detected before backward at step {local_step+1}",step=local_step,max_steps=max_steps,nonfinite_loss_detected=True,error=f"Non-finite loss detected at step {local_step+1}; training stopped before saving invalid weights.")
            job_log(job,"Non-finite loss detected; aborting before backward/save",level="ERROR",step=local_step+1,item=item_id)
            raise FloatingPointError(f"Non-finite loss detected at step {local_step+1}")
        scaler.scale(loss).backward()
        grad_norm=None
        if (local_step+1)%accum==0:
            scaler.unscale_(optimizer)
            grad_norm=torch.nn.utils.clip_grad_norm_(params,1.0)
            if not bool(torch.isfinite(grad_norm).all().item()):
                optimizer.zero_grad(set_to_none=True)
                progress(job,status="failed",phase="failed",phase_detail=f"Non-finite gradient detected at step {local_step+1}",step=local_step,max_steps=max_steps,nonfinite_gradient_detected=True,error=f"Non-finite gradient detected at step {local_step+1}; optimizer step was skipped.")
                job_log(job,"Non-finite gradient detected; optimizer step skipped",level="ERROR",step=local_step+1,item=item_id)
                raise FloatingPointError(f"Non-finite gradient detected at step {local_step+1}")
            scaler.step(optimizer);scaler.update();scheduler.step();optimizer.zero_grad(set_to_none=True)

        step=local_step+1;elapsed=time.time()-t0
        loss_value=float(loss.item()*accum);lr=float(optimizer.param_groups[0]["lr"])
        eta=(elapsed/max(1,step-start_step))*(max_steps-step)
        progress(job,status="running",phase="training",phase_detail=f"Training step {step}/{max_steps}",step=step,max_steps=max_steps,progress=step/max_steps,loss=loss_value,learning_rate=lr,elapsed_seconds=elapsed,eta_seconds=eta,last_item_id=item_id,grad_norm=(float(grad_norm.item()) if grad_norm is not None else None),grad_scale=float(scaler.get_scale()))
        if step==1 or step==max_steps or step%log_every==0:
            job_log(job,"Training progress",step=f"{step}/{max_steps}",percent=f"{step/max_steps*100:.1f}%",loss=f"{loss_value:.6f}",lr=f"{lr:.8g}",grad_norm=(f"{float(grad_norm.item()):.6f}" if grad_norm is not None else "-"),grad_scale=f"{float(scaler.get_scale()):.1f}",elapsed=f"{elapsed:.1f}s",eta=f"{eta:.1f}s",item=item_id,**gpu_snapshot())

        if step%max(1,int(job["save_every"]))==0 or step==max_steps:
            cp=save_trainable_state(unet,optimizer,scheduler,job,step)
            progress(job,checkpoint=str(cp),phase_detail=f"Training step {step}/{max_steps} · checkpoint saved")

    final=Path(job["output_dir"])/"final";final.mkdir(parents=True,exist_ok=True)
    progress(job,phase="saving_final",phase_detail="Validating and saving final trained weights")
    job_log(job,"Saving final output",path=str(final))
    registered=None;registered_full=None;final_unet=None
    assert_module_finite(job,unet,"trained UNet")
    if job["mode"]=="lora":
        registered=save_lora(unet,final,job,max_steps,register=True)
    else:
        # Release optimizer state before CPU export; it can be very large during a full fine-tune.
        try:del optimizer,scheduler,scaler,params
        except Exception:pass
        gc.collect();torch.cuda.empty_cache()
        unet=unet.to(device="cpu",dtype=torch.float16)
        final_unet=final/"unet"
        unet.save_pretrained(final_unet,safe_serialization=True)
        atomic_json(final/"full_unet_manifest.json",{
            "base_model":job["base_model"],"unet_path":str(final_unet),"step":max_steps,
            "note":"Fine-tuned SDXL UNet inference output. Complete SDXL export is registered separately."
        })
        job_log(job,"Final fine-tuned UNet saved",path=str(final_unet))
        registered_full=export_complete_sdxl(unet,job,max_steps)
    progress(job,status="completed",phase="completed",phase_detail="Training completed successfully",step=max_steps,max_steps=max_steps,progress=1.0,elapsed_seconds=time.time()-t0,eta_seconds=0,registered_lora=registered,registered_full_model=registered_full,final_unet=(str(final_unet) if final_unet else ""),final_dir=str(final))
    job_log(job,"Training completed successfully",elapsed=f"{time.time()-t0:.1f}s",registered_lora=registered or "-",registered_full_model=registered_full or "-",final_unet=str(final_unet) if final_unet else "-",final_dir=str(final))


def run_job(job,resume_checkpoint="",weights_checkpoint=""):
    with gpu_session('training'):
        return _run_job_unlocked(job,resume_checkpoint,weights_checkpoint)

def thread_entry(job,resume_checkpoint="",weights_checkpoint=""):
    try:
        run_job(job,resume_checkpoint,weights_checkpoint)
    except BaseException as e:
        tb=traceback.format_exc()
        try:
            job_log(job,"Training failed",level="ERROR",error=f"{type(e).__name__}: {e}")
            _append(Path(job["output_dir"])/"job.log",tb)
            _append(Path(job["output_dir"])/"events.jsonl",json.dumps(_json_safe({"ts":time.time(),"time":_ts(),"level":"ERROR","message":"traceback","traceback":tb}),ensure_ascii=False,allow_nan=False))
            progress(job,status="failed",phase="failed",phase_detail=f"{type(e).__name__}: {e}",error=str(e),traceback=tb)
        except Exception:
            traceback.print_exc()
        traceback.print_exc()
    finally:
        try:
            import torch
            if torch.cuda.is_available():
                job_log(job,"Worker cleanup before CUDA cache release",**gpu_snapshot())
                gc.collect()
                torch.cuda.empty_cache()
                try:torch.cuda.ipc_collect()
                except Exception:pass
                job_log(job,"Worker cleanup completed",**gpu_snapshot())
        except Exception as e:
            try:job_log(job,"Cleanup warning",level="WARN",error=str(e))
            except Exception:pass
        with lock:
            state["thread"]=None;state["job_id"]=None;state["stop"]=None
        print(f"[TRAIN:{job.get('id','?')}] [{_ts()}] [INFO] Training thread ended; worker is idle.",flush=True)


@app.get("/health")
def health():
    info=runtime_info();thr=state.get("thread")
    info.update({"ok":True,"runtime":"training_worker","busy":bool(thr and thr.is_alive()),"job_id":state.get("job_id"),"thread_alive":bool(thr and thr.is_alive()),"last_event":state.get("last_event"),"last_error":state.get("last_error"),"gpu_memory":gpu_snapshot()})
    return jsonify(info)


@app.post("/train")
def train():
    d=request.get_json(force=True) or {};job=d.get("job") or {}
    if not job.get("id") or not job.get("output_dir"):return jsonify(error="Invalid training job"),400
    info=runtime_info()
    if not info.get("compatibility_ok",True):return jsonify(error=info.get("compatibility_reason"),runtime=info),409
    with lock:
        if state["thread"] is not None and state["thread"].is_alive():return jsonify(error=f"Training worker busy with {state['job_id']}"),409
        ev=threading.Event();state["stop"]=ev;state["job_id"]=job["id"];state["last_error"]=""
        t=threading.Thread(target=thread_entry,args=(job,d.get("resume_checkpoint") or "",d.get("weights_checkpoint") or ""),daemon=True,name=f"train-{job['id']}")
        state["thread"]=t;t.start()
    return jsonify(ok=True,job_id=job["id"],worker_pid=os.getpid(),runtime=info)


@app.post("/stop")
def stop():
    d=request.get_json(force=True) or {};jid=d.get("job_id")
    if state["thread"] is None or not state["thread"].is_alive():return jsonify(ok=True,stopped=False)
    if jid and jid!=state["job_id"]:return jsonify(error="Another training job is running"),409
    state["stop"].set()
    return jsonify(ok=True,stopping=True,job_id=state["job_id"])


def main():
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    print(f"[{_ts()}] Zetalvx Image Lab - SDXL Edition 0.1.0.8 training worker starting on {HOST}:{PORT} pid={os.getpid()}",flush=True)
    print(json.dumps(runtime_info(),ensure_ascii=False),flush=True)
    app.run(host=HOST,port=PORT,threaded=True)


if __name__ == "__main__":
    main()
