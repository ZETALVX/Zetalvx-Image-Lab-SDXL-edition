import json,os,uuid,threading,queue,time
from pathlib import Path
from PIL import Image,ImageOps
from core.db import one,rows,execute
from core.paths import ARTIFACTS_DIR,SHARED_ROOT
from core.model_registry import model_by_id,validate_model
from core.task_adapters import task_from_tool,task_support,resolve_strategy
from core.image_runtime import execute_job,unload as unload_image_runtime

CAP_MAP={
 "generate_image":"generate","edit_image":"edit","img2img":"img2img","inpaint":"inpaint",
 "reference":"reference","multi_image":"multi_image","refine_image":"refine"
}

PROGRESS_DIR=SHARED_ROOT/"cache"/"job_progress"
PROGRESS_DIR.mkdir(parents=True,exist_ok=True)
CANCEL_DIR=SHARED_ROOT/"cache"/"job_cancel"
CANCEL_DIR.mkdir(parents=True,exist_ok=True)

_job_queue=queue.Queue()
_queued=set()
_lock=threading.Lock()
_worker_started=False

def _params(job):
    try:return json.loads(job.get("params_json") or "{}")
    except:return {}

def _resolve_model(job):
    task=task_from_tool(job.get("tool"))
    if job.get("model_id")!="auto":
        m=model_by_id(job.get("model_id"))
        if not m:raise RuntimeError("Selected model not found.")
        if not m.get("enabled"):raise RuntimeError("Selected model is disabled.")
        support=task_support(m,task)
        if support.get("level")=="unavailable":raise RuntimeError(support.get("reason") or "Task unavailable for selected model.")
        return m
    from core.model_registry import load_registry
    candidates=[]
    for m in load_registry().get("models",[]):
        if not m.get("enabled"):continue
        support=task_support(m,task)
        if support.get("rank",0)<=0 or not support.get("executable",True):continue
        if not validate_model(m).get("ready"):continue
        priority=int((m.get("config") or {}).get("auto_priority") or 0)
        candidates.append((support.get("rank",0),priority,m))
    if candidates:
        candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
        return candidates[0][2]
    raise RuntimeError(f"No ready image model can execute '{task}'.")

def _make_contact_sheet(paths,jid):
    images=[]
    for path in paths:
        if path and Path(path).exists():
            try:images.append(Image.open(path).convert("RGB"))
            except:pass
    if not images: return None
    thumb_w=768;thumb_h=768
    cells=[]
    for im in images:
        c=ImageOps.contain(im,(thumb_w,thumb_h))
        cell=Image.new("RGB",(thumb_w,thumb_h),"black")
        cell.paste(c,((thumb_w-c.width)//2,(thumb_h-c.height)//2))
        cells.append(cell)
    cols=2 if len(cells)>1 else 1
    rows_n=(len(cells)+cols-1)//cols
    sheet=Image.new("RGB",(thumb_w*cols,thumb_h*rows_n),"black")
    for i,c in enumerate(cells):sheet.paste(c,((i%cols)*thumb_w,(i//cols)*thumb_h))
    p=SHARED_ROOT/"cache"/"reference_sheets"/f"{jid}.jpg";p.parent.mkdir(parents=True,exist_ok=True)
    sheet.save(p,quality=92)
    return str(p)

def _artifact_record(aid):
    if not aid:return None
    a=one("SELECT * FROM artifacts WHERE id=?",(aid,))
    if not a:return None
    try:a["metadata"]=json.loads(a.get("metadata_json") or "{}")
    except:a["metadata"]={}
    try:
        path=Path(a.get("path") or "")
        if path.exists():
            with Image.open(path) as im:
                a["width"],a["height"]=im.size
                a["format"]=im.format
    except Exception:
        pass
    return a

def _artifact_path(aid):
    a=_artifact_record(aid)
    return a.get("path") if a else None

def _progress_path(jid): return PROGRESS_DIR/f"{jid}.json"
def _cancel_path(jid): return CANCEL_DIR/f"{jid}.cancel"

def write_progress(jid,**data):
    p=_progress_path(jid)
    payload={"job_id":jid,"updated_at":time.time(),**data}
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    tmp.replace(p)

def read_progress(jid):
    p=_progress_path(jid)
    try:return json.loads(p.read_text(encoding="utf-8"))
    except:return {}

def request_cancel(jid):
    execute("UPDATE jobs SET cancel_requested=1 WHERE id=?",(jid,))
    _cancel_path(jid).write_text("1",encoding="utf-8")

def queue_snapshot():
    active=one("SELECT id,project_id,tool,model_id,status,phase,progress,step_current,step_total,queue_order FROM jobs WHERE status='running' ORDER BY started_at LIMIT 1")
    waiting=rows("SELECT id,project_id,tool,model_id,status,phase,queue_order FROM jobs WHERE status='queued' AND cancel_requested=0 ORDER BY queue_order,created_at")
    return {"active":active,"queued":waiting}

def run_job(jid):
    job=one("SELECT * FROM jobs WHERE id=?",(jid,))
    if not job:return
    if int(job.get("cancel_requested") or 0):
        execute("UPDATE jobs SET status='cancelled',phase='cancelled',completed_at=CURRENT_TIMESTAMP WHERE id=?",(jid,))
        write_progress(jid,phase="cancelled",progress=0)
        return

    started=time.time()
    try:
        model=_resolve_model(job)
        if not validate_model(model).get("ready"):
            raise RuntimeError(f"Model '{model['name']}' is not ready. Configure its required files in Models.")
        p=_params(job)
        aid=uuid.uuid4().hex
        outdir=ARTIFACTS_DIR/job["project_id"];outdir.mkdir(parents=True,exist_ok=True)
        outpath=outdir/f"{aid}.png"
        source_id=p.get("source_artifact_id")
        mask_id=p.get("mask_artifact_id")
        refs=p.get("reference_artifact_ids") or []
        strategy=resolve_strategy(model,job.get("tool"),p)

        source_record=_artifact_record(source_id) if source_id else None
        reference_records=[x for x in (_artifact_record(r) for r in refs) if x]
        input_assets=[]
        if source_record:
            input_assets.append({"id":source_record.get("id"),"type":source_record.get("type"),"role":"source","path":source_record.get("path")})
        input_assets.extend({"id":r.get("id"),"type":r.get("type"),"role":"reference","path":r.get("path")} for r in reference_records)

        image_providers={"sdxl"}
        if model.get("provider") in image_providers:
            bad=[x for x in input_assets if x.get("type")!="image"]
            if bad:
                names=", ".join(Path(x.get("path") or "").name for x in bad)
                raise RuntimeError(
                    f"{model['name']} currently accepts image inputs only in Zetalvx Image Lab. "
                    f"Remove video input(s): {names}"
                )

        source_path=source_record.get("path") if source_record else None
        reference_paths=[r.get("path") for r in reference_records if r.get("type")=="image" and r.get("path")]
        if strategy.get("source_mode")=="first_reference":
            if not reference_paths:raise RuntimeError("Reference fallback requires at least one reference image.")
            source_path=reference_paths[0]
        elif strategy.get("source_mode")=="contact_sheet":
            source_path=_make_contact_sheet(reference_paths,jid)
            if not source_path:raise RuntimeError("Multi-image fallback requires reference images.")

        requested_width=int(p.get("width") or 1024)
        requested_height=int(p.get("height") or 1024)
        source_width=source_height=None
        if source_path and Path(source_path).exists():
            try:
                with Image.open(source_path) as sim:
                    source_width,source_height=sim.size
            except Exception:
                pass
        preserve_source_size=job.get("tool") in ("edit_image","inpaint") and bool(source_width and source_height)
        worker_width=source_width if preserve_source_size else requested_width
        worker_height=source_height if preserve_source_size else requested_height
        steps=int(p.get("steps") or (model.get("config") or {}).get("default_steps") or 0)
        progress_path=str(_progress_path(jid))
        cancel_path=str(_cancel_path(jid))
        try: Path(cancel_path).unlink(missing_ok=True)
        except: pass

        execute("""UPDATE jobs
                   SET model_id=?,status='running',phase='loading_model',progress=0,
                       step_current=0,step_total=?,error='',started_at=CURRENT_TIMESTAMP,
                       completed_at=NULL,duration_seconds=0,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",(model["id"],steps,jid))
        write_progress(jid,phase="loading_model",progress=0,step_current=0,step_total=steps,elapsed_seconds=0)

        effective_config=dict(model.get("config") or {})
        checkpoint_override=str(p.get("checkpoint_override") or "").strip()
        inpaint_checkpoint_override=str(p.get("inpaint_checkpoint_override") or "").strip()
        if model.get("provider")=="sdxl":
            if checkpoint_override and Path(checkpoint_override).exists():
                effective_config["checkpoint"]=checkpoint_override
            if inpaint_checkpoint_override and Path(inpaint_checkpoint_override).exists():
                effective_config["inpaint_checkpoint"]=inpaint_checkpoint_override

        payload={
          "provider":model.get("provider"),"config":effective_config,
          "job":{
            "job_id":jid,
            "task":strategy.get("worker_task") or CAP_MAP.get(job.get("tool"),job.get("tool")),
            "prompt":job.get("prompt") or "",
            "negative_prompt":p.get("negative_prompt") or "",
            "width":worker_width,"height":worker_height,
            "requested_width":requested_width,"requested_height":requested_height,
            "preserve_source_size":preserve_source_size,
            "steps":p.get("steps"),"cfg":p.get("cfg"),"seed":p.get("seed",-1),"scheduler":p.get("scheduler","default"),
            "strength":p.get("strength",.35),"loras":p.get("loras") or [],
            "source_path":source_path,
            "mask_path":_artifact_path(mask_id) if mask_id else None,
            "reference_paths":reference_paths,
            "input_assets":input_assets,
            "output_path":str(outpath),
            "progress_path":progress_path,
            "cancel_path":cancel_path,
            "started_epoch":started
          }
        }
        result=execute_job(payload)
        duration=time.time()-started
        output_width=output_height=None
        try:
            with Image.open(outpath) as oim:
                output_width,output_height=oim.size
        except Exception:
            pass
        source_snapshot=_artifact_record(source_id) if source_id else None
        if source_snapshot:
            source_snapshot={k:source_snapshot.get(k) for k in ("id","type","path","created_at","width","height","format","metadata")}

        meta={"model_id":model["id"],"model_name":model["name"],"provider":model.get("provider"),
              "tool":job["tool"],"prompt":job.get("prompt") or "","params":p,
              "runtime_result":result,"source_artifact_id":source_id,"mask_artifact_id":mask_id,
              "reference_artifact_ids":refs,"input_assets":input_assets,"duration_seconds":duration,
              "requested_width":requested_width,"requested_height":requested_height,
              "source_width":source_width,"source_height":source_height,
              "output_width":output_width,"output_height":output_height,
              "preserved_source_size":preserve_source_size,
              "source_snapshot":source_snapshot,
              "checkpoint_override":checkpoint_override or None,
              "inpaint_checkpoint_override":inpaint_checkpoint_override or None,
              "effective_checkpoint":effective_config.get("checkpoint"),
              "effective_inpaint_checkpoint":effective_config.get("inpaint_checkpoint"),
              "task_strategy":strategy}

        execute("INSERT INTO artifacts(id,project_id,type,path,parent_id,metadata_json) VALUES(?,?,?,?,?,?)",
                (aid,job["project_id"],"image",str(outpath),source_id,json.dumps(meta,ensure_ascii=False)))
        execute("""UPDATE jobs SET status='completed',phase='completed',progress=1,
                   step_current=CASE WHEN step_total>0 THEN step_total ELSE step_current END,
                   output_artifact_id=?,duration_seconds=?,completed_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",(aid,duration,jid))
        execute("""INSERT INTO project_state(project_id,active_artifact_id,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(project_id) DO UPDATE SET active_artifact_id=excluded.active_artifact_id,updated_at=CURRENT_TIMESTAMP""",
                (job["project_id"],aid))
        write_progress(jid,phase="completed",progress=1,step_current=steps,step_total=steps,elapsed_seconds=duration,duration_seconds=duration)
    except Exception as e:
        duration=time.time()-started
        current=one("SELECT cancel_requested FROM jobs WHERE id=?",(jid,)) or {}
        cancelled=int(current.get("cancel_requested") or 0)==1 or "cancel" in str(e).lower()
        status="cancelled" if cancelled else "failed"
        execute("""UPDATE jobs SET status=?,phase=?,error=?,duration_seconds=?,
                   completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (status,status,str(e),duration,jid))
        write_progress(jid,phase=status,progress=0,elapsed_seconds=duration,error=str(e))

def _worker_loop():
    while True:
        jid=_job_queue.get()
        try:
            with _lock:_queued.discard(jid)
            job=one("SELECT status,cancel_requested FROM jobs WHERE id=?",(jid,))
            if not job:continue
            if int(job.get("cancel_requested") or 0):
                execute("UPDATE jobs SET status='cancelled',phase='cancelled',completed_at=CURRENT_TIMESTAMP WHERE id=?",(jid,))
                continue
            run_job(jid)
        finally:
            _job_queue.task_done()

def ensure_worker():
    global _worker_started
    if _worker_started:return
    with _lock:
        if _worker_started:return
        threading.Thread(target=_worker_loop,daemon=True,name="creator-serial-job-queue").start()
        _worker_started=True

def start_job(jid):
    ensure_worker()
    with _lock:
        if jid in _queued:return
        _queued.add(jid)
    _job_queue.put(jid)

def recover_pending_jobs():
    ensure_worker()
    execute("UPDATE jobs SET status='queued',phase='queued',progress=0,step_current=0,started_at=NULL WHERE status='running'")
    for j in rows("SELECT id FROM jobs WHERE status='queued' AND cancel_requested=0 ORDER BY queue_order,created_at"):
        start_job(j['id'])

if os.environ.get("SDXL_STUDIO_NO_BACKGROUND")!="1":ensure_worker()
