# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.18; see BUILD_PROVENANCE.json and docs/TESTS_0_1_0_18.md.
from core.training_history import guarded as history_guarded
from core.training_captions import job_policy, SAVED_TEXT, LEGACY, POLICIES
from core.runtime_env import SHARED_ROOT, MODELS_ROOT, RUNTIME_ROOT, worker_headers, runtime_dir
import json, os, re, time, uuid, shutil, math, hashlib, subprocess
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from core.platform_support import hidden_kwargs

SHARED = SHARED_ROOT
ROOT = SHARED / "training"
DATASETS = ROOT / "datasets"
JOBS = ROOT / "jobs"
RECIPES = ROOT / "recipes"
CACHE = ROOT / "cache"
LOGS = ROOT / "logs"
GLOBAL_LOG = SHARED / "logs" / "training-worker.log"
TRAINING_URL = os.environ.get("CREATOR_TRAINING_WORKER_URL", "http://127.0.0.1:8300").rstrip("/")
LORA_ROOT = MODELS_ROOT/"loras/SDXL"
FULL_ROOT = MODELS_ROOT/"SDXL/trained"
EXPORTS = ROOT / "exports"
DEFAULT_SDXL = str(MODELS_ROOT/"SDXL/sd_xl_base_1.0.safetensors")
TRAINING_VENV = Path(os.environ.get("CREATOR_TRAINING_VENV", str(runtime_dir("sdxl") or RUNTIME_ROOT/"not-installed")))

def ensure():
    for p in (DATASETS, JOBS, RECIPES, CACHE, LOGS, LORA_ROOT, FULL_ROOT, EXPORTS):
        p.mkdir(parents=True, exist_ok=True)
    recipes = {
        "sdxl_lora_local_24gb.json": {
            "name":"SDXL LoRA · Local 24 GB","family":"sdxl","mode":"lora",
            "resolution":768,"rank":16,"alpha":16,"learning_rate":1e-4,
            "max_steps":300,"save_every":100,"gradient_accumulation":1,
            "gradient_checkpointing":True,"optimizer":"adamw"
        },
        "sdxl_lora_server_96gb.json": {
            "name":"SDXL LoRA · Server 96 GB","family":"sdxl","mode":"lora",
            "resolution":1024,"rank":32,"alpha":32,"learning_rate":1e-4,
            "max_steps":1000,"save_every":100,"gradient_accumulation":1,
            "gradient_checkpointing":True,"optimizer":"adamw"
        },
        "sdxl_full_unet_server.json": {
            "name":"SDXL Full SDXL · Server","family":"sdxl","mode":"full",
            "resolution":1024,"learning_rate":1e-5,"max_steps":1000,
            "save_every":100,"gradient_accumulation":1,
            "gradient_checkpointing":True,"optimizer":"adamw8bit"
        }
    }
    for fn, data in recipes.items():
        p=RECIPES/fn
        if not p.exists():
            p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def _slug(s):
    s=re.sub(r"[^a-zA-Z0-9_-]+","_",str(s or "").strip()).strip("_")
    return s[:80] or "item"

def _json_safe(value):
    """Return strict-JSON-safe data. Python accepts NaN/Infinity; browsers do not."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    try:
        if hasattr(value, "item") and callable(value.item):
            scalar=value.item()
            if scalar is not value:
                return _json_safe(scalar)
    except Exception:
        pass
    return value

def _read(p, default=None):
    try:return _json_safe(json.loads(Path(p).read_text(encoding="utf-8")))
    except Exception:return {} if default is None else default

def _write(p, data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(_json_safe(data),ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    tmp.replace(p)

def worker_call(path, payload=None, timeout=6):
    try:
        body=None
        headers=worker_headers()
        if payload is not None:
            body=json.dumps(payload).encode("utf-8");headers={**worker_headers(),"Content-Type":"application/json"}
        req=urlrequest.Request(TRAINING_URL+path,data=body,headers=headers,method="POST" if payload is not None else "GET")
        with urlrequest.urlopen(req,timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:
        return {"ok":False,"error":str(e)}

def worker_health():
    return worker_call("/health",None,2)

def list_recipes():
    ensure()
    out=[]
    for p in sorted(RECIPES.glob("*.json")):
        d=_read(p,{})
        d["id"]=p.stem
        out.append(d)
    return out

def list_datasets():
    ensure();out=[]
    job_refs={}
    for jp in JOBS.glob("*/job.json"):
        j=_read(jp,{})
        did=str(j.get("dataset_id") or "")
        if did:job_refs[did]=job_refs.get(did,0)+1
    for p in sorted(DATASETS.glob("*/dataset.json"),key=lambda x:x.stat().st_mtime,reverse=True):
        d=_read(p,{})
        d["item_count"]=len(d.get("items") or [])
        d["job_count"]=job_refs.get(str(d.get("id") or p.parent.name),0)
        try:d["modified_at"]=p.stat().st_mtime
        except Exception:d["modified_at"]=None
        out.append(d)
    return out

def get_dataset(did):
    ensure()
    p=DATASETS/did/"dataset.json"
    return _read(p,{}) if p.exists() else None

def create_dataset(name, trigger="", common_caption=""):
    ensure();did=uuid.uuid4().hex[:12]
    d={"id":did,"name":(name or "Untitled dataset").strip(),"trigger":trigger.strip(),
       "common_caption":common_caption.strip(),"created_at":time.time(),"items":[]}
    (DATASETS/did/"images").mkdir(parents=True,exist_ok=True)
    _write(DATASETS/did/"dataset.json",d)
    return d

def add_dataset_file(did, file_storage, caption=""):
    d=get_dataset(did)
    if not d:raise RuntimeError("Dataset not found")
    original=file_storage.filename or "image.png"
    ext=Path(original).suffix.lower()
    if ext not in {".png",".jpg",".jpeg",".webp",".bmp",".tif",".tiff"}:
        raise RuntimeError(f"Training dataset accepts images only: {original}")
    iid=uuid.uuid4().hex[:12]
    dest=DATASETS/did/"images"/f"{iid}{ext}"
    file_storage.save(dest)
    cap=(caption or "").strip() or d.get("common_caption","") or d.get("trigger","")
    item={"id":iid,"file":str(dest),"original_name":original,"caption":cap,"quality":"","warnings":[],"caption_source":"manual"}
    d.setdefault("items",[]).append(item)
    _write(DATASETS/did/"dataset.json",d)
    return item

def update_dataset(did, payload):
    d=get_dataset(did)
    if not d:raise RuntimeError("Dataset not found")
    if "name" in payload:d["name"]=str(payload["name"]).strip()
    if "trigger" in payload:d["trigger"]=str(payload["trigger"]).strip()
    if "trigger_position" in payload:
        if payload['trigger_position'] not in ('prefix','suffix','context'):raise ValueError('Invalid trigger position')
        d['trigger_position']=payload['trigger_position']
    if 'vision_model_id' in payload:d['vision_model_id']=str(payload['vision_model_id'])[:80]
    if "common_caption" in payload:d["common_caption"]=str(payload["common_caption"]).strip()
    captions=payload.get("captions") or {}
    for item in d.get("items") or []:
        if item["id"] in captions:item["caption"]=str(captions[item["id"]]).strip()
    _write(DATASETS/did/"dataset.json",d)
    return d

def delete_dataset(did):
    ensure()
    did=str(did or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",did):raise RuntimeError("Invalid dataset id")
    d=get_dataset(did)
    if not d:raise RuntimeError("Dataset not found")
    active=[]
    for p in JOBS.glob("*/job.json"):
        j=_read(p,{})
        if str(j.get("dataset_id") or "")!=did:continue
        prog=_read(p.parent/"progress.json",{})
        if prog.get("status") in ("running","queued"):
            active.append(p.parent.name)
    if active:
        raise RuntimeError("Dataset is used by an active training job: "+", ".join(active))
    root=(DATASETS/did).resolve()
    try:root.relative_to(DATASETS.resolve())
    except Exception:raise RuntimeError("Unsafe dataset path")
    shutil.rmtree(root)
    return {"id":did,"name":d.get("name") or did}

def delete_dataset_item(did, iid):
    d=get_dataset(did)
    if not d:raise RuntimeError("Dataset not found")
    kept=[]
    for item in d.get("items") or []:
        if item.get("id")==iid:
            try:Path(item.get("file","")).unlink(missing_ok=True)
            except Exception:pass
        else:kept.append(item)
    d["items"]=kept
    _write(DATASETS/did/"dataset.json",d)
    return d

def _safe_jid(jid):
    jid=str(jid or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",jid):raise RuntimeError("Invalid training job id")
    return jid

def _tail_text(path, lines=180, max_bytes=512000):
    p=Path(path)
    if not p.exists():return ""
    lines=max(20,min(int(lines or 180),1000))
    try:
        size=p.stat().st_size
        with p.open("rb") as f:
            if size>max_bytes:f.seek(size-max_bytes)
            raw=f.read().decode("utf-8",errors="replace")
        return "\n".join(raw.splitlines()[-lines:])
    except Exception as e:return f"[log read error] {e}"

def read_job_log(jid, lines=180):
    ensure();jid=_safe_jid(jid);jdir=JOBS/jid
    if not (jdir/"job.json").exists():raise RuntimeError("Training job not found")
    log=jdir/"job.log";events=jdir/"events.jsonl"
    return {
      "id":jid,"path":str(log),"exists":log.exists(),"text":_tail_text(log,lines),
      "events_path":str(events),"global_log_path":str(GLOBAL_LOG),
      "global_tail":_tail_text(GLOBAL_LOG,80)
    }

def _job_payload(jid):
    jid=_safe_jid(jid)
    p=JOBS/jid/"job.json"
    if not p.exists():return None
    d=_read(p,{})
    progress=_read(JOBS/jid/"progress.json",{})
    d.update(progress)
    cps=[]
    cpdir=JOBS/jid/"checkpoints"
    if cpdir.exists():
        for pth in sorted(cpdir.glob("step_*")):
            if pth.is_dir():
                try:step=int(pth.name.split("_")[-1])
                except:step=0
                lora_file=pth/"pytorch_lora_weights.safetensors"
                state_file=pth/"trainable_state.pt"
                cps.append({
                    "step":step,"path":str(pth),
                    "mode":d.get("mode") or "lora",
                    "lora_file":str(lora_file) if lora_file.is_file() else "",
                    "state_file":str(state_file) if state_file.is_file() else "",
                    "size_bytes":sum(x.stat().st_size for x in pth.rglob("*") if x.is_file())
                })
    for cp in cps:
        mapped=(d.get('checkpoint_loras') or {}).get(str(cp['step']),{})
        candidates=[mapped.get('path','')]
        suffix=f"_step_{cp['step']:06d}"
        candidates.extend(x for x in (d.get('promoted_loras') or []) if suffix in Path(str(x)).stem)
        reg=str(d.get('registered_lora') or '')
        if suffix in Path(reg).stem:candidates.append(reg)
        cp['promoted_lora_path']=next((str(Path(x).resolve()) for x in candidates
            if x and Path(x).is_file() and Path(x).resolve().is_relative_to(LORA_ROOT.resolve())), '')
    d["checkpoints"]=cps
    lp=JOBS/jid/"job.log"
    d["job_log_path"]=str(lp);d["job_log_exists"]=lp.exists()
    if lp.exists() and d.get("status")=="completed" and d.get("loss") is None:
        tail=_tail_text(lp,80,65536).lower()
        if re.search(r"\bloss=(?:nan|inf|-inf)\b|non-finite (?:loss|gradient|weights)",tail):
            d["historical_nonfinite_loss"]=True
            d["training_health_warning"]="Training log contains a non-finite loss/gradient marker. Validate the exported LoRA before using it."
    if d.get("registered_lora"):
        try:d["registered_lora_exists"]=Path(d["registered_lora"]).is_file()
        except Exception:d["registered_lora_exists"]=False
    if d.get("registered_full_model"):
        try:d["registered_full_model_exists"]=Path(d["registered_full_model"]).is_dir()
        except Exception:d["registered_full_model_exists"]=False
    if d.get("final_unet"):
        try:d["final_unet_exists"]=Path(d["final_unet"]).is_dir()
        except Exception:d["final_unet_exists"]=False
    return _json_safe(d)

def reconcile_jobs(health=None):
    """Convert stale 'running' records into explicit interrupted/offline states.
    This never deletes a job or checkpoint and never changes completed/failed jobs.
    """
    ensure();health=health if isinstance(health,dict) else worker_health();now=time.time()
    online=bool(health.get("ok"));busy=bool(health.get("busy"));active=str(health.get("job_id") or "")
    changed=[]
    for p in JOBS.glob("*/progress.json"):
        prog=_read(p,{})
        if prog.get("status") not in ("running","queued"):continue
        jid=p.parent.name;updated=float(prog.get("heartbeat_at") or prog.get("updated_at") or 0)
        age=now-updated if updated else 999999
        reason=None;status=None
        if online and not busy and age>2:
            status="interrupted";reason="Training worker is online but no longer reports this job as active. The training thread ended or the worker was restarted. Check the per-job log."
        elif online and busy and active and active!=jid and age>5:
            status="interrupted";reason=f"Training worker is now busy with another job ({active}); this job is no longer active."
        elif not online and age>30:
            status="worker_offline";reason="Training worker is offline and this job has stopped sending heartbeats. Check the per-job/global log before resuming."
        if status:
            prog.update(status=status,phase=status,phase_detail=reason,error=prog.get("error") or reason,interrupted_at=now,updated_at=now)
            _write(p,prog);changed.append(jid)
    return changed

def list_jobs(health=None):
    ensure();reconcile_jobs(health);out=[]
    for p in sorted(JOBS.glob("*/job.json"),key=lambda x:x.stat().st_mtime,reverse=True):
        j=_job_payload(p.parent.name)
        if j:out.append(j)
    return out

def _lora_id(path):
    try:key=str(Path(path).resolve())
    except Exception:key=str(path)
    return hashlib.sha1(key.encode("utf-8",errors="replace")).hexdigest()[:16]

def _safe_lora_path(path):
    """Allow managed library files plus final LoRA artifacts inside training jobs."""
    p=Path(path).resolve()
    root=LORA_ROOT.resolve()
    try:
        p.relative_to(root);return p
    except Exception:pass
    try:
        rel=p.relative_to(JOBS.resolve())
        parts=rel.parts
        if len(parts)>=3 and parts[1]=="final" and p.suffix.lower()==".safetensors":return p
    except Exception:pass
    raise RuntimeError("LoRA path is outside the managed SDXL LoRA/library output directories")


def _job_final_loras(j):
    jid=str(j.get("id") or "")
    if not jid:return []
    candidates=[]
    fd=j.get("final_dir")
    if fd:candidates.append(Path(fd))
    candidates.append(JOBS/jid/"final")
    seen=set();out=[]
    for d in candidates:
        try:d=d.resolve()
        except Exception:continue
        if str(d) in seen:continue
        seen.add(str(d))
        if not d.is_dir():continue
        for p in sorted(d.glob("*.safetensors")):
            try:
                rp=p.resolve();rp.relative_to((JOBS/jid/"final").resolve())
                out.append(rp)
            except Exception:continue
    return out


def _training_job_index():
    out={}
    for jp in JOBS.glob("*/job.json"):
        j=_job_payload(jp.parent.name)
        if not j:continue
        rp=j.get("registered_lora")
        if rp:
            try:out[str(Path(rp).resolve())]=j
            except Exception:out[str(rp)]=j
        for promoted in (j.get("promoted_loras") or []):
            try:out[str(Path(promoted).resolve())]=j
            except Exception:pass
        for fp in _job_final_loras(j):out[str(fp)]=j
    return out


def _lora_item(p,j=None,source="library"):
    rp=str(p.resolve());st=p.stat()
    item={
      "id":_lora_id(rp),"name":p.name,"path":rp,"exists":True,
      "size_bytes":st.st_size,"modified_at":st.st_mtime,"source":source,
      "recoverable":source=="job_output"
    }
    if j:
        item["job"]={k:j.get(k) for k in ("id","name","status","dataset_id","resolution","rank","alpha","learning_rate","step","max_steps","loss","created_at","elapsed_seconds","historical_nonfinite_loss","training_health_warning")}
        # Library metadata describes this snapshot, not the last step of its job.
        if source=="checkpoint_promoted":
            stem=_slug(j.get("name") or j.get("id") or "")
            match=re.fullmatch(re.escape(stem)+r"_step_(\d{6})(?:_\d+|_sha256_[0-9a-f]{64})?\.safetensors",p.name)
            if match:item["job"]["step"]=int(match.group(1))
    return _json_safe(item)


def list_loras():
    """List registered SDXL LoRAs and recoverable final outputs from historical jobs."""
    ensure();jobs=_training_job_index();out=[];seen=set();jobs_with_registered=set()
    root=LORA_ROOT.resolve()
    for p in sorted(root.rglob("*.safetensors"),key=lambda x:x.stat().st_mtime,reverse=True):
        try:rp=str(p.resolve())
        except Exception:continue
        j=jobs.get(rp)
        source="library"
        if j:
            reg=str(j.get("registered_lora") or "")
            try:reg=str(Path(reg).resolve()) if reg else ""
            except Exception:pass
            promoted=set()
            for x in (j.get("promoted_loras") or []):
                try:promoted.add(str(Path(x).resolve()))
                except Exception:pass
            if rp==reg:
                source="training";jobs_with_registered.add(str(j.get("id") or ""))
            elif rp in promoted:source="checkpoint_promoted"
        out.append(_lora_item(p,j,source));seen.add(rp)

    historical=[]
    for jp in JOBS.glob("*/job.json"):
        j=_job_payload(jp.parent.name)
        if not j:continue
        jid=str(j.get("id") or "")
        if jid in jobs_with_registered:continue
        for p in _job_final_loras(j):
            rp=str(p.resolve())
            if rp in seen:continue
            historical.append(_lora_item(p,j,"job_output"));seen.add(rp)
    historical.sort(key=lambda x:x.get("modified_at") or 0,reverse=True)
    out.extend(historical)
    return out


def _find_lora(lid):
    lid=str(lid or "")
    if not re.fullmatch(r"[0-9a-f]{16}",lid):raise RuntimeError("Invalid LoRA id")
    for item in list_loras():
        if item.get("id")==lid:return item
    raise RuntimeError("LoRA not found")


def validate_lora(lid, timeout=120):
    item=_find_lora(lid);p=_safe_lora_path(item["path"])
    py=__import__("core.platform_support",fromlist=["venv_python"]).venv_python(TRAINING_VENV)
    if not py.is_file():raise RuntimeError(f"Training Python not found: {py}")
    code='''import json,sys,torch
from safetensors import safe_open
p=sys.argv[1]
res={"valid":False,"tensors":0,"parameters":0,"nan_values":0,"inf_values":0,"nonfinite_tensors":[],"metadata":{}}
try:
    with safe_open(p,framework="pt",device="cpu") as f:
        res["metadata"]=f.metadata() or {}
        for k in f.keys():
            t=f.get_tensor(k);res["tensors"]+=1;res["parameters"]+=int(t.numel())
            if torch.is_floating_point(t) or t.is_complex():
                nan=int(torch.isnan(t).sum().item());inf=int(torch.isinf(t).sum().item())
                if nan or inf:
                    res["nan_values"]+=nan;res["inf_values"]+=inf
                    if len(res["nonfinite_tensors"])<30:res["nonfinite_tensors"].append({"name":k,"nan":nan,"inf":inf,"shape":list(t.shape),"dtype":str(t.dtype)})
    res["valid"]=res["tensors"]>0 and res["nan_values"]==0 and res["inf_values"]==0
except Exception as e:
    res["error"]=f"{type(e).__name__}: {e}"
print(json.dumps(res,ensure_ascii=False,allow_nan=False))'''
    cp=subprocess.run([str(py),"-c",code,str(p)],capture_output=True,text=True,timeout=max(10,int(timeout)), **hidden_kwargs())
    raw=(cp.stdout or "").strip().splitlines()
    if cp.returncode!=0 or not raw:
        raise RuntimeError((cp.stderr or cp.stdout or "LoRA validator failed")[-3000:])
    try:result=json.loads(raw[-1])
    except Exception as e:raise RuntimeError(f"Could not parse LoRA validation result: {e}")
    result.update({"id":lid,"name":item["name"],"path":str(p),"size_bytes":item.get("size_bytes"),"source":item.get("source")})
    return _json_safe(result)


def recover_lora(lid):
    from core.lora_files import library_lock, publish
    with library_lock(LORA_ROOT):
        item=_find_lora(lid)
        if item.get("source")!="job_output":
            return {"recovered":True,"already_registered":True,"path":item['path'],"name":item['name']}
        src=_safe_lora_path(item["path"])
        j=item.get("job") or {};job_name=_slug(j.get("name") or src.parent.parent.name)
        step=int(j.get("step") or j.get("max_steps") or 0)
        stem=f"{job_name}_step_{step:06d}" if step else job_name
        dst,reused,sha256=publish(src,LORA_ROOT,stem)
        jid=str(j.get("id") or "")
        if jid:
            pp=JOBS/jid/"progress.json";prog=_read(pp,{})
            prog["registered_lora"]=str(dst);prog["lora_recovered_at"]=time.time();_write(pp,prog)
        return {"recovered":True,"already_registered":reused,"from":str(src),"path":str(dst),"name":dst.name,"sha256":sha256}


def delete_lora(lid):
    from core.lora_files import library_lock
    with library_lock(LORA_ROOT):
        return _delete_lora_locked(lid)

def _delete_lora_locked(lid):
    item=_find_lora(lid);p=_safe_lora_path(item["path"])
    if not p.is_file():raise RuntimeError("LoRA file is already missing")
    deleted=[str(p)];p.unlink()
    j=item.get("job") or {};jid=str(j.get("id") or "")
    if jid:
        pp=JOBS/jid/"progress.json";prog=_read(pp,{})
        if isinstance(prog,dict):
            if str(prog.get("registered_lora") or "")==str(p):prog["registered_lora"]=""
            prog["promoted_loras"]=[x for x in (prog.get("promoted_loras") or []) if str(x)!=str(p)]
            prog["lora_deleted_at"]=time.time();prog["lora_deleted_paths"]=deleted;_write(pp,prog)
    return {"id":lid,"name":item.get("name"),"deleted":True,"deleted_paths":deleted}


def lora_download_path(lid):
    item=_find_lora(lid);p=_safe_lora_path(item["path"])
    if not p.is_file():raise RuntimeError("LoRA file is missing")
    return p


def _checkpoint_dir(jid,step):
    jid=_safe_jid(jid)
    try:step=int(step)
    except Exception:raise RuntimeError("Invalid checkpoint step")
    if step<0:raise RuntimeError("Invalid checkpoint step")
    from core.safe_paths import is_link
    job=JOBS/jid;root=job/"checkpoints";p=root/f"step_{step:06d}"
    if any(is_link(x) for x in (job,root,p)):
        raise RuntimeError("Unsafe checkpoint link; no files were changed")
    try:p.resolve().relative_to(JOBS.resolve())
    except Exception:raise RuntimeError("Unsafe checkpoint path")
    if not p.is_dir():raise RuntimeError("Checkpoint not found")
    return p


def _run_tensor_validator(args,timeout=300):
    py=__import__("core.platform_support",fromlist=["venv_python"]).venv_python(TRAINING_VENV)
    if not py.is_file():raise RuntimeError(f"Training Python not found: {py}")
    code=r'''import json,sys,torch
from pathlib import Path
from safetensors import safe_open
mode=sys.argv[1];paths=[Path(x) for x in sys.argv[2:]]
res={"valid":False,"files":0,"tensors":0,"parameters":0,"nan_values":0,"inf_values":0,"nonfinite_tensors":[]}
def add(name,t):
    res["tensors"]+=1;res["parameters"]+=int(t.numel())
    if torch.is_floating_point(t) or t.is_complex():
        nan=int(torch.isnan(t).sum().item());inf=int(torch.isinf(t).sum().item())
        res["nan_values"]+=nan;res["inf_values"]+=inf
        if (nan or inf) and len(res["nonfinite_tensors"])<40:
            res["nonfinite_tensors"].append({"name":name,"nan":nan,"inf":inf,"shape":list(t.shape),"dtype":str(t.dtype)})
try:
    if mode=="safe":
        for p in paths:
            with safe_open(str(p),framework="pt",device="cpu") as f:
                res["files"]+=1
                for k in f.keys():add(f"{p.name}:{k}",f.get_tensor(k))
    elif mode=="torch":
        for p in paths:
            obj=torch.load(str(p),map_location="cpu",weights_only=True);res["files"]+=1
            if isinstance(obj,dict):
                for k,t in obj.items():
                    if torch.is_tensor(t):add(f"{p.name}:{k}",t)
    res["valid"]=res["files"]>0 and res["tensors"]>0 and res["nan_values"]==0 and res["inf_values"]==0
except Exception as e:res["error"]=f"{type(e).__name__}: {e}"
print(json.dumps(res,ensure_ascii=False,allow_nan=False))'''
    # Insert only our trusted application source directory in the child interpreter.
    gate="import sys;sys.path.insert(0,"+repr(str(Path(__file__).resolve().parents[1]))+");from core.runtime_security import require_reviewed_torch;require_reviewed_torch()\n"
    cp=subprocess.run([str(py),"-I","-c",gate+code,*[str(x) for x in args]],capture_output=True,text=True,timeout=max(20,int(timeout)), **hidden_kwargs())
    lines=(cp.stdout or "").strip().splitlines()
    if cp.returncode!=0 or not lines:raise RuntimeError((cp.stderr or cp.stdout or "Tensor validator failed")[-4000:])
    try:return _json_safe(json.loads(lines[-1]))
    except Exception as e:raise RuntimeError(f"Could not parse validator result: {e}")


def validate_checkpoint(jid,step,timeout=300):
    cpdir=_checkpoint_dir(jid,step);j=_job_payload(jid) or {}
    lf=cpdir/"pytorch_lora_weights.safetensors"
    sf=cpdir/"trainable_state.pt"
    if lf.is_file():result=_run_tensor_validator(["safe",lf],timeout)
    elif sf.is_file():result=_run_tensor_validator(["torch",sf],timeout)
    else:raise RuntimeError("Checkpoint has no trainable weights to validate")
    result.update({"job_id":jid,"step":int(step),"mode":j.get("mode"),"path":str(cpdir)})
    return _json_safe(result)


def promote_checkpoint(jid,step):
    from core.lora_files import library_lock, publish
    with library_lock(LORA_ROOT):
        cpdir=_checkpoint_dir(jid,step);j=_job_payload(jid) or {}
        if j.get("mode")!="lora":raise RuntimeError("Promote to LoRA Library is available for LoRA checkpoints only")
        src=cpdir/"pytorch_lora_weights.safetensors"
        stem=f"{_slug(j.get('name') or jid)}_step_{int(step):06d}"
        dst,reused,sha256=publish(src,LORA_ROOT,stem)
        pp=JOBS/jid/"progress.json";prog=_read(pp,{})
        promoted=list(prog.get("promoted_loras") or [])
        if str(dst) not in promoted:promoted.append(str(dst))
        prog["promoted_loras"]=promoted
        mapping=dict(prog.get("checkpoint_loras") or {})
        mapping[str(int(step))]={"path":str(dst),"sha256":sha256}
        prog["checkpoint_loras"]=mapping;_write(pp,prog)
        return {"promoted":True,"already_promoted":reused,"path":str(dst),"name":dst.name,"job_id":jid,"step":int(step),"sha256":sha256}


def checkpoint_download_path(jid,step):
    cpdir=_checkpoint_dir(jid,step);j=_job_payload(jid) or {}
    lf=cpdir/"pytorch_lora_weights.safetensors"
    if lf.is_file():return lf
    EXPORTS.mkdir(parents=True,exist_ok=True)
    base=EXPORTS/f"{_slug(j.get('name') or jid)}_checkpoint_step_{int(step):06d}"
    z=Path(str(base)+".zip")
    if not z.exists() or z.stat().st_mtime<cpdir.stat().st_mtime:
        if z.exists():z.unlink()
        shutil.make_archive(str(base),"zip",root_dir=str(cpdir))
    return z


def delete_checkpoint(jid,step):
    from core.lora_files import library_lock
    with library_lock(LORA_ROOT):
        return _delete_checkpoint_locked(jid,step)

def _delete_checkpoint_locked(jid,step):
    cpdir=_checkpoint_dir(jid,step);j=_job_payload(jid) or {}
    active={"running","queued","starting","preparing","loading","saving","cancelling","dispatching"}
    if j.get("status") in active:
        raise RuntimeError("Cannot delete checkpoints while this training job is active")
    # A continuation may be reading a checkpoint belonging to another job.
    for jp in JOBS.glob("*/job.json"):
        other=_job_payload(jp.parent.name) or {}
        if other.get('status') not in active:continue
        for key in ('resume_from','resume_from_checkpoint','checkpoint_path','continue_from','init_lora_path','source_weights_checkpoint','resume_checkpoint'):
            value=other.get(key)
            if isinstance(value,str) and value:
                q=Path(value).expanduser().resolve()
                if q==cpdir.resolve() or q.is_relative_to(cpdir.resolve()):
                    raise RuntimeError("Checkpoint is in use by another training job")
    shutil.rmtree(cpdir)
    return {"deleted":True,"job_id":jid,"step":int(step)}


def _full_id(path):
    return hashlib.sha1(str(Path(path).resolve()).encode("utf-8",errors="replace")).hexdigest()[:16]


def _dir_size(p):
    try:return sum(x.stat().st_size for x in Path(p).rglob("*") if x.is_file())
    except Exception:return 0


def list_full_models():
    ensure();out=[];job_index={}
    for jp in JOBS.glob("*/job.json"):
        j=_job_payload(jp.parent.name)
        if not j:continue
        rp=j.get("registered_full_model")
        if rp:
            try:job_index[str(Path(rp).resolve())]=j
            except Exception:pass
    for d in sorted([x for x in FULL_ROOT.iterdir() if x.is_dir()],key=lambda x:x.stat().st_mtime,reverse=True):
        if not (d/"model_index.json").is_file():continue
        rp=str(d.resolve());j=job_index.get(rp);manifest=_read(d/"creator_training_manifest.json",{})
        item={"id":_full_id(rp),"name":d.name,"path":rp,"size_bytes":_dir_size(d),"modified_at":d.stat().st_mtime,"manifest":manifest}
        if j:item["job"]={k:j.get(k) for k in ("id","name","status","dataset_id","resolution","learning_rate","step","max_steps","loss","elapsed_seconds","base_model")}
        out.append(_json_safe(item))
    return out


def _find_full_model(mid):
    mid=str(mid or "")
    if not re.fullmatch(r"[0-9a-f]{16}",mid):raise RuntimeError("Invalid full model id")
    for x in list_full_models():
        if x.get("id")==mid:return x
    raise RuntimeError("Full SDXL model not found")


def validate_full_model(mid,timeout=600):
    item=_find_full_model(mid);root=Path(item["path"]).resolve()
    try:root.relative_to(FULL_ROOT.resolve())
    except Exception:raise RuntimeError("Unsafe full model path")
    files=sorted(root.rglob("*.safetensors"))
    if not files:raise RuntimeError("No safetensors weights found in full SDXL model")
    result=_run_tensor_validator(["safe",*files],timeout)
    result.update({"id":mid,"name":item["name"],"path":str(root),"size_bytes":item.get("size_bytes")})
    return _json_safe(result)


def full_model_download_path(mid):
    item=_find_full_model(mid);root=Path(item["path"]).resolve()
    try:root.relative_to(FULL_ROOT.resolve())
    except Exception:raise RuntimeError("Unsafe full model path")
    EXPORTS.mkdir(parents=True,exist_ok=True)
    base=EXPORTS/f"{_slug(item['name'])}_diffusers"
    z=Path(str(base)+".zip")
    if not z.exists() or z.stat().st_mtime<root.stat().st_mtime:
        if z.exists():z.unlink()
        shutil.make_archive(str(base),"zip",root_dir=str(root))
    return z


def delete_full_model(mid):
    item=_find_full_model(mid);root=Path(item["path"]).resolve()
    try:root.relative_to(FULL_ROOT.resolve())
    except Exception:raise RuntimeError("Unsafe full model path")
    shutil.rmtree(root)
    j=item.get("job") or {};jid=str(j.get("id") or "")
    if jid:
        pp=JOBS/jid/"progress.json";prog=_read(pp,{})
        if str(prog.get("registered_full_model") or "")==str(root):
            prog["registered_full_model"]="";prog["full_model_deleted_at"]=time.time();_write(pp,prog)
    return {"deleted":True,"id":mid,"name":item.get("name"),"path":str(root)}


def list_full_unets():
    ensure();out=[]
    for jp in JOBS.glob("*/job.json"):
        j=_job_payload(jp.parent.name)
        if not j or j.get("mode")!="full":continue
        p=JOBS/j["id"]/"final"/"unet"
        if not (p/"config.json").is_file():continue
        out.append({"id":_full_id(p),"name":f"{j.get('name') or j['id']} · UNet","path":str(p),"size_bytes":_dir_size(p),"modified_at":p.stat().st_mtime,"job":{k:j.get(k) for k in ("id","name","status","dataset_id","resolution","step","max_steps","loss","elapsed_seconds")}})
    out.sort(key=lambda x:x.get("modified_at") or 0,reverse=True)
    return _json_safe(out)


def _find_full_unet(uid):
    uid=str(uid or "")
    if not re.fullmatch(r"[0-9a-f]{16}",uid):raise RuntimeError("Invalid UNet id")
    for x in list_full_unets():
        if x.get("id")==uid:return x
    raise RuntimeError("Full UNet output not found")


def validate_full_unet(uid,timeout=600):
    item=_find_full_unet(uid);p=Path(item["path"]);files=sorted(p.rglob("*.safetensors"))
    if not files:raise RuntimeError("No safetensors weights found in UNet output")
    result=_run_tensor_validator(["safe",*files],timeout);result.update({"id":uid,"name":item["name"],"path":str(p)})
    return _json_safe(result)


def full_unet_download_path(uid):
    item=_find_full_unet(uid);root=Path(item["path"]).resolve()
    try:root.relative_to(JOBS.resolve())
    except Exception:raise RuntimeError("Unsafe UNet output path")
    EXPORTS.mkdir(parents=True,exist_ok=True);base=EXPORTS/f"{_slug(item['name'])}_unet";z=Path(str(base)+".zip")
    if not z.exists() or z.stat().st_mtime<root.stat().st_mtime:
        if z.exists():z.unlink()
        shutil.make_archive(str(base),"zip",root_dir=str(root))
    return z


def delete_full_unet(uid):
    item=_find_full_unet(uid);root=Path(item["path"]).resolve()
    try:root.relative_to(JOBS.resolve())
    except Exception:raise RuntimeError("Unsafe UNet output path")
    shutil.rmtree(root)
    return {"deleted":True,"id":uid,"name":item.get("name"),"path":str(root)}

@history_guarded
def create_job(config, submit=True):
    ensure()
    did=str(config.get("dataset_id") or "")
    dataset=get_dataset(did)
    if not dataset or not dataset.get("items"):
        raise RuntimeError("Select a dataset containing at least one image.")
    base=str(config.get("base_model") or DEFAULT_SDXL)
    if not Path(base).exists():
        raise RuntimeError(f"SDXL base model not found: {base}")
    mode=str(config.get("mode") or "lora")
    if mode not in ("lora","full"):raise RuntimeError("Training mode must be lora or full.")
    policy=config.get('caption_policy', SAVED_TEXT)
    if policy not in POLICIES:raise ValueError('Unknown training caption policy')
    jid=uuid.uuid4().hex[:12]
    jdir=JOBS/jid;jdir.mkdir(parents=True,exist_ok=True)
    cfg={
      "id":jid,"name":str(config.get("name") or f"sdxl_{mode}_{jid[:6]}"),
      "caption_policy":policy,
      "family":"sdxl","mode":mode,"dataset_id":did,"dataset_path":str(DATASETS/did/"dataset.json"),
      "base_model":base,"resolution":int(config.get("resolution") or 768),
      "max_steps":int(config.get("max_steps") or 300),"save_every":int(config.get("save_every") or 100),
      "rank":int(config.get("rank") or 16),"alpha":int(config.get("alpha") or config.get("rank") or 16),
      "learning_rate":float(config.get("learning_rate") or (1e-4 if mode=="lora" else 1e-5)),
      "gradient_accumulation":max(1,int(config.get("gradient_accumulation") or 1)),
      "gradient_checkpointing":bool(config.get("gradient_checkpointing",True)),
      "optimizer":str(config.get("optimizer") or ("adamw" if mode=="lora" else "adamw8bit")),
      "seed":int(config.get("seed") if config.get("seed") is not None else 42),
      "continuation_of":str(config.get("continuation_of") or ""),
      "continuation_from_step":int(config.get("continuation_from_step") or 0),
      "source_weights_checkpoint":str(config.get("source_weights_checkpoint") or ""),
      "continue_from_weights":bool(config.get("continue_from_weights",False)),
      "output_dir":str(jdir),"lora_register_dir":str(LORA_ROOT),"full_register_dir":str(FULL_ROOT),
      "created_at":time.time(),"status":"queued","phase":"queued","step":0,"progress":0.0
    }
    _write(jdir/"job.json",cfg)
    _write(jdir/"progress.json",{"status":"queued","phase":"queued","step":0,"max_steps":cfg["max_steps"],"progress":0.0})
    if submit:
        result=worker_call("/train",{"job":cfg},8)
        if not result.get("ok"):
            prog=_read(jdir/"progress.json",{})
            prog.update(status="worker_offline",phase="worker_offline",error=result.get("error","Training worker unavailable"))
            _write(jdir/"progress.json",prog)
    return _job_payload(jid)

def stop_job(jid):
    j=_job_payload(jid)
    if not j:raise RuntimeError("Training job not found")
    return worker_call("/stop",{"job_id":jid},5)

@history_guarded
def resume_job(jid, checkpoint_path=""):
    j=_job_payload(jid)
    if not j:raise RuntimeError("Training job not found")
    if not checkpoint_path:
        cps=j.get("checkpoints") or []
        if not cps:raise RuntimeError("No checkpoint available to resume.")
        checkpoint_path=cps[-1]["path"]
    base=_read(JOBS/jid/"job.json",{})
    return worker_call("/train",{"job":base,"resume_checkpoint":checkpoint_path,"resume_mode":"exact"},8)

@history_guarded
def continue_job(jid, additional_steps=200, checkpoint_path=""):
    old=_job_payload(jid)
    if not old:raise RuntimeError("Training job not found")
    cps=old.get("checkpoints") or []
    if not checkpoint_path:
        if not cps:raise RuntimeError("No checkpoint available.")
        checkpoint_path=cps[-1]["path"]
    cp=Path(checkpoint_path)
    if not cp.is_dir():raise RuntimeError("Continuation checkpoint is missing.")
    try:
        source_step=int(cp.name.split("_")[-1])
    except Exception:
        source_step=0
    newcfg=_read(JOBS/jid/"job.json",{})
    newcfg["caption_policy"]=job_policy(newcfg)
    newcfg["name"]=f"{newcfg.get('name','training')}_continue_{source_step or 'latest'}"
    newcfg["max_steps"]=max(1,int(additional_steps))
    newcfg["source_weights_checkpoint"]=str(cp)
    newcfg["continue_from_weights"]=True
    newcfg["continuation_of"]=jid
    newcfg["continuation_from_step"]=source_step
    newcfg.pop("id",None);newcfg.pop("output_dir",None);newcfg.pop("created_at",None)
    # IMPORTANT: create the branch metadata without submitting a fresh training first.
    # The worker must receive exactly one /train request, with weights_checkpoint attached.
    new=create_job(newcfg,submit=False)
    result=worker_call("/train",{"job":_read(JOBS/new["id"]/"job.json",{}),"weights_checkpoint":str(cp),"resume_mode":"weights"},8)
    if not result.get("ok"):
        prog=_read(JOBS/new["id"]/"progress.json",{})
        prog.update(status="worker_offline",phase="worker_offline",error=result.get("error","Training worker unavailable"))
        _write(JOBS/new["id"]/"progress.json",prog)
    return _job_payload(new["id"])

ensure()
