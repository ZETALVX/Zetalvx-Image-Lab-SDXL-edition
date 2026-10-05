from core.runtime_env import SHARED_ROOT, MODELS_ROOT, RUNTIME_ROOT, worker_headers
import json, os, time, uuid, shutil, math
from pathlib import Path
import requests

SHARED=SHARED_ROOT
ROOT=Path(os.getenv('CREATOR_IDENTITY_ROOT',str(SHARED/'identity'))).expanduser()
JOBS=ROOT/'jobs'
BATCHES=ROOT/'batches'
JOBS.mkdir(parents=True,exist_ok=True)
BATCHES.mkdir(parents=True,exist_ok=True)
WORKER_URL=os.getenv('CREATOR_IDENTITY_WORKER_URL','http://127.0.0.1:8301').rstrip('/')


def _safe(v):
    if isinstance(v,Path): return str(v)
    if isinstance(v,float): return v if math.isfinite(v) else None
    if isinstance(v,dict): return {str(k):_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [_safe(x) for x in v]
    return v


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(_safe(data),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    tmp.replace(path)


def _read_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:return default if default is not None else {}


def worker_health(timeout=1.2):
    try:
        r=requests.get(f'{WORKER_URL}/health',timeout=timeout)
        d=r.json() if r.content else {}
        d.setdefault('ok',r.ok)
        return d
    except Exception as e:
        return {'ok':False,'online':False,'error':str(e),'url':WORKER_URL}


def create_job(config):
    """Persist an Identity job in queued state.

    v0.1.60 deliberately does NOT call /generate here. A Creator-side dispatcher
    serializes Identity work so submissions never fail just because the worker is busy.
    """
    jid=str((config or {}).get('id') or uuid.uuid4().hex[:12])
    out=JOBS/jid
    out.mkdir(parents=True,exist_ok=True)
    cfg=dict(config or {})
    now=time.time()
    cfg.update({'id':jid,'output_dir':str(out),'created_at':float(cfg.get('created_at') or now)})
    atomic_json(out/'job.json',cfg)
    atomic_json(out/'progress.json',{
        'status':'queued','phase':'queued','progress':0.0,
        'phase_detail':'Waiting in Identity queue','created_at':now,'updated_at':now
    })
    return cfg


def patch_job(jid,**fields):
    d=JOBS/str(jid)
    if not d.exists():return None
    job=_read_json(d/'job.json',{})
    job.update(_safe(fields))
    atomic_json(d/'job.json',job)
    return job


def patch_progress(jid,**fields):
    d=JOBS/str(jid)
    if not d.exists():return None
    p=_read_json(d/'progress.json',{})
    p.update(_safe(fields));p['updated_at']=time.time()
    atomic_json(d/'progress.json',p)
    return p


def submit_job(jid,timeout=8):
    """Submit one already-persisted job to the worker.

    409/busy is not a failure: the caller can put it back into queued state.
    """
    job=get_job(jid)
    if not job:raise RuntimeError('Identity job not found')
    payload=_read_json(JOBS/str(jid)/'job.json',{})
    r=requests.post(f'{WORKER_URL}/generate',json=payload,headers=worker_headers(),timeout=timeout)
    try:d=r.json() if r.content else {}
    except Exception:d={}
    if r.status_code==409:
        return {'ok':False,'busy':True,'status_code':409,'error':d.get('error') or 'Identity worker is busy','job_id':d.get('job_id')}
    if not r.ok:
        raise RuntimeError(d.get('error') or f'Identity worker HTTP {r.status_code}')
    return {'ok':True,**d}


def list_jobs(limit=250):
    out=[]
    if not JOBS.exists():return out
    dirs=sorted((p for p in JOBS.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True)
    for d in dirs[:limit]:
        job=_read_json(d/'job.json',{})
        prog=_read_json(d/'progress.json',{})
        merged={**job,**prog}
        merged['id']=job.get('id') or d.name
        merged['job_dir']=str(d)
        op=Path(str(merged.get('output_path') or d/'output.png'))
        merged['output_exists']=op.exists()
        merged['output_path']=str(op) if op.exists() else str(merged.get('output_path') or '')
        out.append(merged)
    # Queue positions are oldest-first, independent from history ordering.
    waiting=sorted((j for j in out if j.get('status')=='queued'),key=lambda j:(float(j.get('queue_order') or j.get('created_at') or 0),float(j.get('created_at') or 0)))
    qpos={j['id']:i+1 for i,j in enumerate(waiting)}
    for j in out:
        if j['id'] in qpos:j['queue_position']=qpos[j['id']]
    return out


def next_queued_job():
    jobs=list_jobs(1000)
    waiting=[j for j in jobs if j.get('status')=='queued']
    if not waiting:return None
    waiting.sort(key=lambda j:(float(j.get('queue_order') or j.get('created_at') or 0),float(j.get('created_at') or 0)))
    return waiting[0]


def queue_snapshot():
    jobs=list_jobs(500)
    running=next((j for j in jobs if j.get('status') in ('running','dispatching')),None)
    queued=sorted((j for j in jobs if j.get('status')=='queued'),key=lambda j:(float(j.get('queue_order') or j.get('created_at') or 0),float(j.get('created_at') or 0)))
    return {'active':running,'queued':queued,'count':len(queued)+(1 if running else 0)}


def list_batches(limit=60):
    jobs=list_jobs(1000)
    grouped={}
    for j in jobs:
        bid=str(j.get('batch_id') or '').strip()
        if not bid:continue
        b=grouped.setdefault(bid,{
            'id':bid,'name':j.get('batch_name') or f'Identity Auto Test {bid}',
            'created_at':j.get('batch_created_at') or j.get('created_at') or 0,
            'total':0,'queued':0,'running':0,'completed':0,'failed':0,'cancelled':0,
            'project_id':j.get('project_id'),'mode':j.get('mode')
        })
        b['total']+=1
        st=str(j.get('status') or 'unknown')
        if st in b:b[st]+=1
    return sorted(grouped.values(),key=lambda b:float(b.get('created_at') or 0),reverse=True)[:limit]


def get_job(jid):
    d=JOBS/str(jid)
    if not d.exists():return None
    return {**_read_json(d/'job.json',{}),**_read_json(d/'progress.json',{}),'id':jid,'job_dir':str(d)}


def read_log(jid,tail=50000):
    p=JOBS/str(jid)/'job.log'
    if not p.exists():return ''
    data=p.read_text(encoding='utf-8',errors='replace')
    return data[-tail:]


def output_path(jid):
    j=get_job(jid)
    if not j:return None
    p=Path(str(j.get('output_path') or JOBS/str(jid)/'output.png'))
    return p if p.exists() else None


def cancel_job(jid):
    j=get_job(jid)
    if not j:return False
    if j.get('status')=='queued' or j.get('status')=='dispatching':
        patch_progress(jid,status='cancelled',phase='cancelled',progress=0.0,phase_detail='Cancelled before execution',completed_at=time.time())
        return True
    return False


def delete_job(jid):
    d=JOBS/str(jid)
    if not d.exists():return False
    shutil.rmtree(d)
    return True
