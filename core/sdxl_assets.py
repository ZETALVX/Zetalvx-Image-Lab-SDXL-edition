"""SDXL Base/config inventory and detached completion launcher.
Zetalvx Image Lab - SDXL Edition 0.1.0.32.
"""
from __future__ import annotations
import json, os, subprocess, time, uuid
from pathlib import Path
from core.runtime_env import MODELS_ROOT, SHARED_ROOT, settings, runtime_dir
from core.model_policy import SDXL_REPO, SDXL_FILE
from core.platform_support import detached_kwargs, process_start, venv_python

INPAINT_REPO='diffusers/stable-diffusion-xl-1.0-inpainting-0.1'
BASE_ALLOW_PATTERNS=['model_index.json','scheduler/*.json','text_encoder/config.json','text_encoder_2/config.json',
                     'tokenizer/*','tokenizer_2/*','unet/config.json','vae/config.json','LICENSE*','README.md']
BASE_REQUIRED=(
    'model_index.json','scheduler/scheduler_config.json','text_encoder/config.json','text_encoder_2/config.json',
    'tokenizer/tokenizer_config.json','tokenizer_2/tokenizer_config.json','unet/config.json','vae/config.json')


def _check_dir(path:Path):
    path=Path(path).expanduser()
    missing=[rel for rel in BASE_REQUIRED if not (path/rel).is_file()]
    return {'path':str(path),'ready':not missing,'missing_files':missing,'present_files':len(BASE_REQUIRED)-len(missing),'required_files':len(BASE_REQUIRED)}


def asset_status(model_cfg=None):
    cfg=settings();model_cfg=model_cfg if isinstance(model_cfg,dict) else {}
    default_checkpoint=MODELS_ROOT/'SDXL'/SDXL_FILE
    configured=str(model_cfg.get('checkpoint') or '').strip()
    configured_path=Path(configured).expanduser() if configured else None
    configured_exists=bool(configured_path and configured_path.is_file())
    default_exists=default_checkpoint.is_file()
    checkpoint_ready=configured_exists or (not configured and default_exists)
    selected_path=configured_path if configured_exists else default_checkpoint
    base=_check_dir(Path(cfg['sdxl_config']))
    inpaint=_check_dir(Path(cfg['inpaint_config']))
    missing=[]
    if not checkpoint_ready:missing.append('checkpoint')
    if not base['ready']:missing.append('base_config')
    if not inpaint['ready']:missing.append('inpaint_config')
    labels={'checkpoint':'checkpoint SDXL','base_config':'config/tokenizer SDXL','inpaint_config':'config/tokenizer inpaint'}
    return {
      'ready':not missing,
      'checkpoint':{'ready':checkpoint_ready,'path':str(selected_path),'configured_path':configured,'configured_exists':configured_exists,'default_path':str(default_checkpoint),'default_exists':default_exists},
      'base_config':base,'inpaint_config':inpaint,
      'missing_components':missing,'missing_labels':[labels[x] for x in missing],
      'present_components':3-len(missing),'total_components':3,
    }


class SDXLBaseInstaller:
    def __init__(self,shared_root=None,models_root=None,source_root=None):
        self.shared=Path(shared_root or SHARED_ROOT);self.models_root=Path(models_root or MODELS_ROOT)
        self.source=Path(source_root or Path(__file__).resolve().parents[1])
        self.state_file=self.shared/'config/sdxl_base_install.json'
        self.log_file=self.shared/'logs/sdxl-base-install.log'
        self.start_lock=self.shared/'run/sdxl-base-start.lock'
    def _read(self):
        try:d=json.loads(self.state_file.read_text(encoding='utf-8'))
        except (OSError,ValueError):d={'status':'idle'}
        if not isinstance(d,dict):d={'status':'idle'}
        return d
    def check(self,model_cfg=None):
        return {'status':'checked','message':'File check completed.','assets':asset_status(model_cfg)}
    def status(self,model_cfg=None):
        d=self._read();d.setdefault('status','idle');d['assets']=asset_status(model_cfg)
        if d.get('status') in ('queued','running'):
            pid=d.get('pid');identity=d.get('process_start');alive=bool(pid and identity and process_start(pid)==identity)
            if not alive and time.time()-float(d.get('updated_at') or 0)>4:
                d.update(status='interrupted',stage='interrupted',message='Previous SDXL download was interrupted. Press Download missing to resume safely; existing files are preserved.')
                from core.runtime_env import atomic_json
                atomic_json(self.state_file,d)
        return d
    def start(self,model_cfg=None):
        from core.install_layout import locked
        from core.runtime_env import atomic_json
        self.start_lock.parent.mkdir(parents=True,exist_ok=True);self.state_file.parent.mkdir(parents=True,exist_ok=True);self.log_file.parent.mkdir(parents=True,exist_ok=True)
        with locked(self.start_lock):
            current=self.status(model_cfg)
            if current.get('status') in ('queued','running'):return current
            assets=asset_status(model_cfg)
            if assets['ready']:
                state={'status':'completed','stage':'ready','completed':3,'total':3,'message':'Nothing to download. All required SDXL files are present.','error':'','assets':assets,'updated_at':time.time()}
                atomic_json(self.state_file,state);return state
            py=venv_python(runtime_dir('sdxl'))
            if not py.is_file():raise RuntimeError('SDXL runtime is not installed.')
            job_id=uuid.uuid4().hex
            state={'id':job_id,'status':'queued','stage':'queued','completed':assets['present_components'],'total':3,
                   'message':'Preparing SDXL download…','error':'','assets':assets,'updated_at':time.time()}
            atomic_json(self.state_file,state)
            env=dict(os.environ);env['SDXL_STUDIO_HOME']=str(self.shared.parent);env['PYTHONDONTWRITEBYTECODE']='1'
            log=self.log_file.open('ab',buffering=0)
            try:
                proc=subprocess.Popen([str(py),'-I',str(self.source/'scripts/sdxl_base_worker.py'),'--home',str(self.shared.parent),'--job-id',job_id],
                                      cwd=self.source,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,close_fds=True,**detached_kwargs())
            finally:log.close()
            identity=None
            for _ in range(20):
                identity=process_start(proc.pid)
                if identity:break
                time.sleep(.025)
            if not identity:
                finished=self._read()
                if finished.get('id')==job_id and finished.get('status') in ('completed','failed'):
                    return finished
                state.update(status='failed',stage='failed',message='Could not track the SDXL download worker.',error='process identity unavailable',updated_at=time.time())
                atomic_json(self.state_file,state);return state
            state.update(status='running',pid=proc.pid,process_start=identity,message='SDXL download worker started. Existing files will be reused.',updated_at=time.time())
            atomic_json(self.state_file,state)
            return state
