# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.29; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
"""Isolated, per-user paths for the SDXL edition. No global environment is edited."""
from __future__ import annotations
import json, os, secrets, tempfile
from pathlib import Path
from core.platform_support import default_data_root, venv_python

VERSION = '1.0.18'
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get('SDXL_STUDIO_HOME', str(default_data_root()))).expanduser().resolve()
SHARED_ROOT = DATA_ROOT/'shared'
MODELS_ROOT = DATA_ROOT/'models'
RUNTIME_ROOT = DATA_ROOT/'runtime'

def runtime_dir(name):
    from core.install_layout import runtime_dirs
    roots = runtime_dirs(DATA_ROOT, APP_ROOT)
    if name not in roots: raise ValueError('Unknown runtime')
    return roots[name]

SETTINGS_FILE = SHARED_ROOT/'config/settings.json'

DEFAULTS = {
    'host': '127.0.0.1', 'port': 8298, 'https': True,
    'image_port': 8299, 'training_port': 8300, 'identity_port': 8301,
    'identity_root': str(MODELS_ROOT/'Identity'),
    'identity_vendor': str(SHARED_ROOT/'identity/vendor/InstantID'),
    'identity_instantid_root': str(MODELS_ROOT/'Identity'/'InstantID'),
    'identity_insightface_root': str(MODELS_ROOT/'Identity'/'insightface'),
    'identity_swapper_model': str(MODELS_ROOT/'Identity'/'inswapper_128.onnx'),
    'instantid_face_pack': 'antelopev2', 'swap_face_pack': 'buffalo_l',
    'identity_instantid_enabled': True, 'identity_faceswap_enabled': True,
    'identity_license_acknowledged': False,
    'sdxl_config': str(SHARED_ROOT/'model-configs/SDXL/base'),
    'inpaint_config': str(SHARED_ROOT/'model-configs/SDXL/inpaint'),
}

def atomic_json(path: Path, data: object):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def settings():
    data=json.loads(SETTINGS_FILE.read_text(encoding='utf-8')) if SETTINGS_FILE.exists() else {}
    if not isinstance(data,dict): raise ValueError('Invalid settings.json (must be an object)')
    cfg={**DEFAULTS, **data}
    # One-launch CLI override. It is inherited by the supervisor/web process but never written to settings.json.
    override=os.environ.get('SDXL_STUDIO_HOST_OVERRIDE','').strip()
    if override in ('127.0.0.1','0.0.0.0'):cfg['host']=override
    return cfg

def initialize_environment():
    for d in [DATA_ROOT, SHARED_ROOT/'config', SHARED_ROOT/'logs', SHARED_ROOT/'run',
              MODELS_ROOT/'SDXL', MODELS_ROOT/'loras/SDXL', MODELS_ROOT/'Identity']:
        d.mkdir(parents=True, exist_ok=True)
    cfg=settings()
    if not SETTINGS_FILE.exists(): atomic_json(SETTINGS_FILE,cfg)
    token_file=SHARED_ROOT/'config/worker_key'
    if not token_file.exists():
        try:
            fd=os.open(token_file, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32))
        except FileExistsError:pass
    from core.identity_paths import resolve_identity_paths
    ip=resolve_identity_paths(cfg,MODELS_ROOT,SHARED_ROOT)
    # Always override inherited Creator environment: the parent app remains isolated.
    env={
        'CREATOR_SHARED_ROOT':str(SHARED_ROOT),
        'CREATOR_IDENTITY_ROOT':str(SHARED_ROOT/'identity'),
        'CREATOR_LORA_ROOTS':str(MODELS_ROOT/'loras/SDXL'),
        'HF_HOME':str(DATA_ROOT/'cache/huggingface'),
        'HF_HUB_CACHE':str(DATA_ROOT/'cache/huggingface/hub'),
        'CREATOR_HOST':str(cfg['host']), 'CREATOR_PORT':str(cfg['port']),
        'CREATOR_IDENTITY_MODEL_ROOT':ip['identity_root'],
        'CREATOR_IDENTITY_VENDOR_ROOT':ip['vendor_root'],
        'CREATOR_IDENTITY_INSTANTID_ROOT':ip['instantid_root'],
        'CREATOR_IDENTITY_INSIGHTFACE_ROOT':ip['insightface_root'],
        'CREATOR_IDENTITY_SWAPPER_MODEL':ip['swapper_path'],
        'CREATOR_IDENTITY_INSTANTID_FACE_PACK':ip['instantid_face_pack'],
        'CREATOR_IDENTITY_SWAP_FACE_PACK':ip['swap_face_pack'],
        'CREATOR_IDENTITY_BASE_SDXL':str(MODELS_ROOT/'SDXL/sd_xl_base_1.0.safetensors'),
        'CREATOR_TRAINING_VENV':str(runtime_dir('sdxl') or RUNTIME_ROOT/'not-installed'),
        'CREATOR_TRAINING_RUNTIME_PYTHON':str(venv_python(runtime_dir('sdxl') or RUNTIME_ROOT/'not-installed')),
        'SDXL_WORKER_KEY':token_file.read_text().strip(),
        'HF_HUB_DISABLE_TELEMETRY':'1',
    }
    # Network use by model loading is opt-in via the separate download command.
    os.environ.setdefault('HF_HOME',str(DATA_ROOT/'cache/huggingface'))
    for name in ['IMAGE','TRAINING','IDENTITY']:
        port=int(cfg[name.lower()+'_port'])
        env[f'CREATOR_{name}_WORKER_URL']=f'http://127.0.0.1:{port}'
        env[f'CREATOR_{name}_WORKER_HOST']='127.0.0.1'
        env[f'CREATOR_{name}_WORKER_PORT']=str(port)
    for k,v in env.items():os.environ[k]=str(v)
    return cfg

def worker_headers():return {'X-SDXL-Worker-Key':os.environ.get('SDXL_WORKER_KEY','')}

def protect_worker(app):
    import hmac
    from flask import request, jsonify
    @app.before_request
    def _check_internal_request():
        if request.method in ('POST','PUT','PATCH','DELETE'):
            key=os.environ.get('SDXL_WORKER_KEY','')
            if not key or not hmac.compare_digest(request.headers.get('X-SDXL-Worker-Key',''), key):
                return jsonify(ok=False,error='Internal worker authentication required'),403
