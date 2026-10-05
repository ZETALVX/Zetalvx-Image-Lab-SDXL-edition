"""SDXL-only registry derived from Zetalvx Image Lab's model registry."""
import json, threading
from pathlib import Path
from core.paths import APP_ROOT, MODELS_CONFIG, MODELS_ROOT
from core.runtime_env import atomic_json
_LOCK=threading.RLock()

def ensure_config():
    with _LOCK:
        if MODELS_CONFIG.exists():return
        data=json.loads((APP_ROOT/'config/models.defaults.json').read_text())
        cfg=data['models'][0]['config']
        cfg.update(checkpoint=str(MODELS_ROOT/'SDXL/sd_xl_base_1.0.safetensors'),
                   checkpoint_roots=str(MODELS_ROOT/'SDXL'),lora_root=str(MODELS_ROOT/'loras/SDXL'))
        mapping=APP_ROOT/'.installed-runtime.json'
        if mapping.is_file() and json.loads(mapping.read_text()).get('backend')=='cpu':
            cfg.update(device='cpu',dtype='float32',memory_mode='full_gpu',cpu_offload=False)
        atomic_json(MODELS_CONFIG,data)

def load_registry():
    ensure_config()
    data=json.loads(MODELS_CONFIG.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('models'),list):raise ValueError('Invalid SDXL model registry')
    data['models']=[m for m in data['models'] if m.get('provider')=='sdxl']
    return data

def save_registry(data):
    if any(m.get('provider')!='sdxl' for m in data.get('models',[])):raise ValueError('This edition supports SDXL models only.')
    with _LOCK:atomic_json(MODELS_CONFIG,data)

def model_by_id(mid):return next((m for m in load_registry()['models'] if m.get('id')==mid),None)

def update_model(mid,patch):
    with _LOCK:
        data=load_registry()
        for m in data['models']:
            if m.get('id')!=mid:continue
            if 'enabled' in patch:m['enabled']=bool(patch['enabled'])
            cfg=patch.get('config')
            if isinstance(cfg,dict):
                allowed=set(m['config'])|{'config_dir','inpaint_config_dir','vae_tiling','vae_slicing'}
                m['config'].update({k:v for k,v in cfg.items() if k in allowed})
                if m['config'].get('device')=='cpu':
                    from core.execution_device import normalized_config
                    m['config']=normalized_config(m['config'],False)
            save_registry(data);return m
    return None

def validate_model(model):
    fields=[];cfg=model.get('config') or {}
    for field in ('checkpoint','inpaint_checkpoint','vae','checkpoint_roots','lora_root'):
        v=str(cfg.get(field) or '').strip()
        paths=[Path(x).expanduser() for x in v.split(':') if x] if field.endswith('_roots') else ([Path(v).expanduser()] if v else [])
        exists=bool(paths) and all(p.exists() for p in paths)
        fields.append({'field':field,'value':v,'exists':exists,'required':field=='checkpoint'})
    ready=bool(fields[0]['exists'])
    return {'ready':ready,'fields':fields,'missing':[f['field'] for f in fields if f['required'] and not f['exists']],
            'note':'Configure an SDXL checkpoint (.safetensors) or complete Diffusers directory.'}
