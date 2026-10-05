# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.27: bounded preview/custom image-test planning.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.24: local/LAN first-account pairing.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.18; see BUILD_PROVENANCE.json and docs/TESTS_0_1_0_18.md.
import sqlite3
import os,json,uuid,re,shutil,threading,time,subprocess,signal,secrets,hmac,math,sys,tempfile
from pathlib import Path
from datetime import timedelta
from flask import Flask,render_template,jsonify,request,send_file,session,redirect,url_for,make_response
from werkzeug.exceptions import HTTPException, BadRequest, ClientDisconnected, RequestEntityTooLarge, UnsupportedMediaType
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from core.runtime_env import initialize_environment, DATA_ROOT, MODELS_ROOT, RUNTIME_ROOT, settings, atomic_json, worker_headers, VERSION
initialize_environment()
ROOT=Path(__file__).resolve().parent
from core.db import init,rows,one,execute,create_job,add_message
from core.paths import SHARED_ROOT,PROJECTS_DIR,ARTIFACTS_DIR,UPLOADS_DIR,THUMBNAILS_DIR,CACHE_DIR
from core.model_registry import load_registry,update_model,validate_model
from core.image_runtime import health as image_worker_health,probe as image_worker_probe
from core.media_tools import run_media_tool
from core.job_executor import start_job,recover_pending_jobs,read_progress,request_cancel,queue_snapshot
from core.task_adapters import support_matrix,task_support,task_from_tool

app=Flask(__name__)
from core.login_throttle import LoginThrottle
login_throttle=LoginThrottle(DATA_ROOT/"secrets/login-attempts.sqlite3")

# --- Simple local login gate (no sign-up) ---
AUTH_CONFIG_PATH=SHARED_ROOT/"config"/"creator_auth.json"
SESSION_SECRET_PATH=SHARED_ROOT/"config"/"creator_session_secret.txt"
from core.first_run_security import FirstRunCodes, SetupCodeError, local_setup_request, print_setup_code
first_run_codes = FirstRunCodes(AUTH_CONFIG_PATH, DATA_ROOT / "secrets")
_first_run_display_lock=threading.RLock()
_first_run_display_code=os.environ.get("SDXL_STUDIO_FIRST_RUN_DISPLAY_CODE","")
_SETUP_CONTROL_PURPOSE=b"zetalvx-first-run-code-control-v1"

def _setup_control_token():
    try:
        key=SESSION_SECRET_PATH.read_text(encoding="utf-8").strip().encode("utf-8")
    except OSError:
        return ""
    return hmac.new(key,_SETUP_CONTROL_PURPOSE,"sha256").hexdigest()

def _ensure_local_setup_code(*,rotate=False):
    """Return the live clear setup code kept only in the web process memory.

    Disk retains only the SHA-256 state managed by FirstRunCodes. A local page
    silently renews an expired code; an authenticated host-control request can
    rotate it immediately so SETUP-CODE.cmd and the local page stay in sync.
    """
    global _first_run_display_code
    with _first_run_display_lock:
        remaining=0 if rotate else first_run_codes.remaining_seconds(_first_run_display_code)
        if remaining<=0:
            code=first_run_codes.issue()
            _first_run_display_code=code or ""
            remaining=first_run_codes.remaining_seconds(_first_run_display_code) if code else 0
        return _first_run_display_code or None,remaining

def _ensure_auth_files():
    from core.private_files import private_directory, protect
    private_directory(AUTH_CONFIG_PATH.parent)
    if not AUTH_CONFIG_PATH.exists():
        AUTH_CONFIG_PATH.write_text(json.dumps({
            "enabled":True,
            "username":"",
            "password_hash":"",
            "session_hours":12
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        try:AUTH_CONFIG_PATH.chmod(0o600)
        except Exception:pass
    if not SESSION_SECRET_PATH.exists():
        try:
            fd=os.open(SESSION_SECRET_PATH, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as f:f.write(secrets.token_hex(48)+"\n")
        except FileExistsError:pass
    protect(AUTH_CONFIG_PATH)
    protect(SESSION_SECRET_PATH)
    private_directory(DATA_ROOT/"secrets")
    for protected in (AUTH_CONFIG_PATH.parent/"key.pem", DATA_ROOT/"secrets/first-run-code.json"):
        if protected.exists():protect(protected)

def _load_auth_config():
    _ensure_auth_files()
    try:
        cfg=json.loads(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg={}
    return {
        "enabled":bool(cfg.get("enabled",True)),
        "username":str(cfg.get("username") or ""),
        "password_hash":str(cfg.get("password_hash") or ""),
        "session_hours":max(1,min(int(cfg.get("session_hours",12) or 12),168)),
    }

def _auth_ok():
    cfg=_load_auth_config()
    if not cfg["enabled"]:
        return True
    return bool(session.get("creator_authenticated")) and hmac.compare_digest(str(session.get("creator_username") or "").encode("utf-8"),cfg["username"].encode("utf-8")) and session.get("auth_stamp")==cfg["password_hash"][-20:]


def _save_auth_config(username,password_hash,session_hours=12,enabled=True):
    username=str(username or "C").strip()[:80] or "C"
    atomic_json(AUTH_CONFIG_PATH,{"enabled":bool(enabled),"username":username,"password_hash":str(password_hash or ""),"session_hours":max(1,min(int(session_hours or 12),168))})
    return _load_auth_config()

def _login_session(cfg):
    session.clear()
    session["creator_authenticated"]=True
    session["creator_csrf_nonce"]=secrets.token_urlsafe(32)
    session["creator_username"]=cfg["username"]
    session["auth_stamp"]=cfg["password_hash"][-20:]
    session.permanent=True
    app.permanent_session_lifetime=timedelta(hours=cfg["session_hours"])

_ensure_auth_files()
app.secret_key=SESSION_SECRET_PATH.read_text(encoding="utf-8").strip()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_NAME="creator_sdxl_session",
    MAX_CONTENT_LENGTH=128*1024*1024,
    SESSION_COOKIE_SECURE=bool(settings().get("https",True)),
)

@app.before_request
def _creator_login_gate():
    from core.http_security import same_origin
    if request.method in {"POST","PUT","PATCH","DELETE"}:
        if not same_origin(request.headers.get("Origin"), request.host_url):
            return jsonify(error="Cross-origin request refused"),403
    if request.endpoint in {"login","first_run","first_run_local_code","static","edition_health"} or request.path in {"/login","/first-run","/api/first-run/local-code"}:
        return None
    if _auth_ok():
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Authentication required",auth_required=True),401
    nxt=request.full_path if request.query_string else request.path
    return redirect(url_for("login",next=nxt))

@app.after_request
def _security_headers(response):
    # Log status/endpoint only: never request bodies, prompts, cookies or tokens.
    if request.endpoint in {'job_create','api_identity_create','api_identity_auto_test','api_training_job_delete'}:
        print(f"[REQUEST] {time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())} method={request.method} endpoint={request.endpoint} status={response.status_code}",flush=True)
    if request.path.endswith(('/download','/export')):
        print(f"[DOWNLOAD] method={request.method} endpoint={request.endpoint or 'unmatched'} status={response.status_code} bytes={response.headers.get('Content-Length','stream')}",flush=True)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response

@app.route("/first-run",methods=["GET","POST"])
def first_run():
    request.max_content_length=16*1024
    cfg=_load_auth_config()
    if cfg["password_hash"]:
        response=redirect(url_for("login"))
        response.headers["Cache-Control"]="no-store"
        return response
    local_client=local_setup_request(request.remote_addr,request.host_url,request.headers)
    # An explicitly proxied request is not treated as local. Direct LAN setup
    # requires HTTPS; forwarding headers do not grant transport trust.
    if not local_client and not request.is_secure:
        return "La prima configurazione da un altro dispositivo richiede HTTPS.",403,{"Cache-Control":"no-store"}
    error="";status=200;retry_after=0
    setup_code_display=None; setup_code_expires_in=0
    if local_client:
        try:
            setup_code_display,setup_code_expires_in=_ensure_local_setup_code()
        except (OSError,RuntimeError):
            setup_code_display=None;setup_code_expires_in=0
    username=(str(request.form.get("username") or "").strip() if request.method=="POST" else "")
    network=str(request.form.get("network") or ("local" if local_client else "lan"))
    csrf=session.get("first_run_csrf")
    if not csrf:
        csrf=secrets.token_urlsafe(32)
        session["first_run_csrf"]=csrf
    if request.method=="POST":
        supplied=request.form.get("first_run_csrf","")
        if not supplied.isascii() or not secrets.compare_digest(supplied,csrf):
            error="Sessione di configurazione scaduta. Ricarica la pagina e riprova.";status=403
        else:
            try:
                # Serializes parallel local/LAN submissions and code rotation.
                # Account existence is rechecked INSIDE the lock, not only above.
                with first_run_codes.locked():
                    if first_run_codes.account_exists_locked():
                        raise SetupCodeError("Account già configurato. Usa il login.",409)
                    if not local_client:
                        first_run_codes.verify_locked(request.form.get("setup_code",""))
                    password=str(request.form.get("password") or "")
                    confirm=str(request.form.get("confirm_password") or "")
                    if not 1<=len(username)<=80:
                        error="Il nome utente deve avere da 1 a 80 caratteri.";status=400
                    elif not 10<=len(password)<=1024:
                        error="La password deve avere da 10 a 1024 caratteri.";status=400
                    elif password!=confirm:
                        error="Le password non coincidono.";status=400
                    elif network not in {"local","lan"}:
                        error="Scegli accesso locale oppure LAN.";status=400
                    else:
                        password_hash=generate_password_hash(password)
                        from core.runtime_env import SETTINGS_FILE
                        app_cfg=settings()
                        old_host=app_cfg["host"]
                        new_host="0.0.0.0" if network=="lan" else "127.0.0.1"
                        app_cfg.update(host=new_host,https=True)
                        atomic_json(SETTINGS_FILE,app_cfg)
                        cfg=_save_auth_config(username,password_hash,12,True)
                        # Persisted account itself makes all bootstrap codes
                        # unusable even if cleanup is interrupted by a crash.
                        try:first_run_codes.revoke_locked()
                        except OSError:app.logger.warning("First-setup state cleanup failed; account is already configured.")
                        _login_session(cfg)
                        response=redirect('/?onboarding=1'+('&network_restart=1' if new_host!=old_host else ''))
                        response.headers["Cache-Control"]="no-store"
                        return response
            except SetupCodeError as exc:
                error=str(exc);status=exc.status;retry_after=exc.retry_after
            except (OSError,RuntimeError):
                error="Impossibile salvare la configurazione. Controlla i permessi sul computer host e riprova.";status=503
    response=make_response(render_template("first_run.html",username=username,error=error,
        network=network,code_required=not local_client,setup_code_display=setup_code_display,
        setup_code_expires_in=setup_code_expires_in,setup_code_command=('SETUP-CODE.cmd' if os.name=='nt' else 'creator-sdxl setup-code'),first_run_csrf=csrf),status)
    response.headers["Cache-Control"]="no-store"
    response.headers["Referrer-Policy"]="no-referrer"
    if retry_after:response.headers["Retry-After"]=str(retry_after)
    return response

@app.route("/api/first-run/local-code",methods=["GET","POST"])
def first_run_local_code():
    if not local_setup_request(request.remote_addr,request.host_url,request.headers):
        return jsonify(error="Local host only"),403,{"Cache-Control":"no-store"}
    cfg=_load_auth_config()
    if cfg["password_hash"]:
        return jsonify(error="First setup already completed"),409,{"Cache-Control":"no-store"}
    rotate=request.method=="POST"
    if rotate:
        supplied=str(request.headers.get("X-Zetalvx-Setup-Control") or "")
        expected=_setup_control_token()
        if not expected or not supplied.isascii() or not hmac.compare_digest(supplied,expected):
            return jsonify(error="Host control authentication failed"),403,{"Cache-Control":"no-store"}
    try:
        code,remaining=_ensure_local_setup_code(rotate=rotate)
    except (OSError,RuntimeError):
        return jsonify(error="Setup code unavailable"),503,{"Cache-Control":"no-store"}
    if not code:
        return jsonify(error="First setup already completed"),409,{"Cache-Control":"no-store"}
    response=jsonify(code=code,expires_in=int(remaining))
    response.headers["Cache-Control"]="no-store"
    response.headers["Referrer-Policy"]="no-referrer"
    return response

@app.route("/login",methods=["GET","POST"])
def login():
    cfg=_load_auth_config()
    if not cfg["enabled"]:
        return redirect(url_for("home"))
    if not cfg["password_hash"]:
        return redirect(url_for("first_run"))
    if _auth_ok():
        return redirect(url_for("home"))
    error="";status=200;wait=0
    if request.method=="POST":
        request.max_content_length=16*1024
        try:wait=login_throttle.reserve(request.remote_addr)
        except (OSError,RuntimeError,sqlite3.Error):
            return render_template("login.html",username=cfg["username"],error="Accesso temporaneamente non disponibile. Riprova.",next_path="/"),503
        if wait:
            error="Troppi tentativi di accesso. Attendi un minuto e riprova.";status=429
        else:
            username=str(request.form.get("username") or "").strip()
            password=str(request.form.get("password") or "")
            correct=False
            if 1<=len(username)<=80 and 1<=len(password)<=1024:
                valid_hash=check_password_hash(cfg["password_hash"],password)
                correct=hmac.compare_digest(username.encode("utf-8"),cfg["username"].encode("utf-8")) and valid_hash
            if correct:
                login_throttle.success(request.remote_addr)
                _login_session(cfg)
                nxt=str(request.form.get("next") or request.args.get("next") or "/")
                if len(nxt)>2048 or not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or any(ord(c)<32 for c in nxt):nxt="/"
                return redirect(nxt)
            error="Utente o password non corretti."
    response=make_response(render_template("login.html",username=cfg["username"],error=error,next_path=request.args.get("next") or "/"),status)
    response.headers["Cache-Control"]="no-store"
    if wait:response.headers["Retry-After"]=str(wait)
    return response

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

init()
if os.environ.get("SDXL_STUDIO_NO_BACKGROUND")!="1":recover_pending_jobs()

def models():return load_registry().get("models",[])
def model_by_id(mid):return next((m for m in models() if m.get("id")==mid),None)

def recipes():
    out=[]
    for r in rows("SELECT * FROM recipes ORDER BY name"):
        try:r["params"]=json.loads(r.pop("params_json") or "{}")
        except:r["params"]={}
        out.append(r)
    return out

from core.local_models import LocalModels
local_models = LocalModels(MODELS_ROOT, SHARED_ROOT/'config/local_models.json', (DATA_ROOT/'secrets',))

def _local_model_config():
    return (next((m for m in models() if m.get('provider') == 'sdxl'), {}) or {}).get('config') or {}

def scan_loras():
    roots = [x for x in os.getenv('CREATOR_LORA_ROOTS', '').split(os.pathsep) if x.strip()]
    return local_models.scan('lora', _local_model_config(), roots)

def training_lora_inventory():
    roots=[x for x in os.getenv('CREATOR_LORA_ROOTS','').split(os.pathsep) if x.strip()]
    catalog={x['path']:x for x in local_models.scan('lora',_local_model_config(),roots,include_disabled=True)}
    result=[]
    for row in training_loras():
        entry=catalog.get(row['path'])
        result.append({**row,'catalog_id':entry['id'] if entry else None,
            'generation_enabled':bool(entry and entry.get('generation_enabled',True))})
    return result

def scan_checkpoints():
    return local_models.scan('checkpoint', _local_model_config())

def _download_attachment(path, download_name=None):
    p=Path(path).expanduser().resolve()
    if not p.is_file():raise FileNotFoundError(str(p))
    response=send_file(p,as_attachment=True,download_name=download_name or p.name,conditional=True,max_age=0,mimetype='application/octet-stream' if p.suffix.lower()=='.safetensors' else None)
    response.headers['Cache-Control']='private, no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Accept-Ranges']='bytes'
    return response


# --- Persistent Image preset system (v0.1.70) ---
USER_IMAGE_PRESETS_DIR=SHARED_ROOT/"presets"/"user"/"image"
IMAGE_PRESET_BINDINGS_PATH=SHARED_ROOT/"config"/"image_preset_bindings.json"

def _ensure_image_preset_storage():
    USER_IMAGE_PRESETS_DIR.mkdir(parents=True,exist_ok=True)
    IMAGE_PRESET_BINDINGS_PATH.parent.mkdir(parents=True,exist_ok=True)
    if not IMAGE_PRESET_BINDINGS_PATH.exists():
        IMAGE_PRESET_BINDINGS_PATH.write_text(json.dumps({
            "_help": {
                "note": "Optional model/LoRA bindings for built-in styles, workflows or technical presets.",
                "example": {
                    "anime": {
                        "model_id": "",
                        "loras": [{"path": "", "name": "anime_style.safetensors", "strength": 0.8, "auto_apply": True}]
                    }
                }
            }
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def _load_image_preset_bindings():
    _ensure_image_preset_storage()
    try:
        raw=json.loads(IMAGE_PRESET_BINDINGS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw,dict) else {}
    except Exception:
        return {}

def _safe_preset_id(raw):
    value=re.sub(r"[^a-zA-Z0-9_-]+","-",str(raw or "").strip()).strip("-").lower()
    return value[:80]

def _normalize_user_image_preset(payload,preset_id=None):
    d=dict(payload or {})
    name=str(d.get("name") or "User preset").strip()[:120]
    pid=_safe_preset_id(preset_id or d.get("id") or name) or uuid.uuid4().hex[:12]
    preset_type=str(d.get("preset_type") or ("complete" if int(d.get("schema_version") or 1)<=1 else "complete")).strip().lower()
    if preset_type not in {"style","technical","complete"}:preset_type="complete"
    includes=d.get("includes") if isinstance(d.get("includes"),dict) else {}
    # v1 presets were effectively complete presets. Preserve that behaviour on load/import.
    if int(d.get("schema_version") or 1)<=1 and not includes:
        includes={"model":True,"loras":True,"params":True,"style":True,"workflow":True,"technical_preset":True,"prompt":bool(d.get("include_prompt",False)),"task":True}
    defaults={
        "style":{"model":True,"loras":True,"params":False,"style":True,"workflow":True,"technical_preset":True,"prompt":False,"task":False},
        "technical":{"model":True,"loras":True,"params":True,"style":False,"workflow":False,"technical_preset":False,"prompt":False,"task":False},
        "complete":{"model":True,"loras":True,"params":True,"style":True,"workflow":True,"technical_preset":True,"prompt":True,"task":True},
    }[preset_type]
    normalized_includes={k:bool(includes.get(k,defaults[k])) for k in defaults}
    include_prompt=bool(normalized_includes.get("prompt",False))
    out={
        "schema_version":2,
        "id":pid,
        "name":name,
        "description":str(d.get("description") or "").strip()[:500],
        "preset_type":preset_type,
        "includes":normalized_includes,
        "created_at":float(d.get("created_at") or time.time()),
        "updated_at":time.time(),
        "task":str(d.get("task") or "generate")[:40],
        "model_id":str(d.get("model_id") or "auto")[:160],
        "quick_style":str(d.get("quick_style") or "clean")[:80],
        "workflow":d.get("workflow") if isinstance(d.get("workflow"),dict) else {},
        "technical_preset_id":str(d.get("technical_preset_id") or "")[:100],
        "params":d.get("params") if isinstance(d.get("params"),dict) else {},
        "loras":d.get("loras") if isinstance(d.get("loras"),list) else [],
        "include_prompt":include_prompt,
        "prompt":str(d.get("prompt") or "") if include_prompt else "",
        "negative_prompt":str(d.get("negative_prompt") or "") if include_prompt else "",
    }
    return out

def _user_image_preset_path(pid):
    return USER_IMAGE_PRESETS_DIR/f"{_safe_preset_id(pid)}.json"

def _list_user_image_presets():
    _ensure_image_preset_storage()
    out=[]
    for path in USER_IMAGE_PRESETS_DIR.glob("*.json"):
        try:
            d=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(d,dict):out.append(d)
        except Exception:pass
    return sorted(out,key=lambda x:(str(x.get("name") or "").lower(),str(x.get("id") or "")))

_ensure_image_preset_storage()

# --- Persistent Video preset system (v0.1.75) ---






def decode_artifact(a):
    if not a:return None
    try:a["metadata"]=json.loads(a.get("metadata_json") or "{}")
    except:a["metadata"]={}
    a["url"]=f"/api/artifacts/{a['id']}/file"
    return a

def project_payload(pid):
    p=one("SELECT * FROM projects WHERE id=?",(pid,))
    if not p:return None
    p["state"]=one("SELECT * FROM project_state WHERE project_id=?",(pid,)) or {"active_artifact_id":""}
    p["artifacts"]=[decode_artifact(x) for x in rows("SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at DESC LIMIT 400",(pid,))]
    jobs=rows("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC LIMIT 200",(pid,))
    for j in jobs:
        live=read_progress(j["id"])
        if live and j.get("status") in ("queued","running"):
            j.update({k:v for k,v in live.items() if k in ("phase","progress","step_current","step_total","elapsed_seconds","error")})
        if not j.get("elapsed_seconds"):
            j["elapsed_seconds"]=j.get("duration_seconds") or live.get("elapsed_seconds",0) if live else (j.get("duration_seconds") or 0)
        try:j["params"]=json.loads(j.get("params_json") or "{}")
        except:j["params"]={}
    p["jobs"]=jobs
    p["messages"]=rows("SELECT role,content,created_at FROM conversations WHERE project_id=? ORDER BY created_at LIMIT 400",(pid,))
    return p


from core.training_manager import (
    list_datasets as training_datasets, get_dataset as training_get_dataset,
    create_dataset as training_create_dataset, add_dataset_file as training_add_dataset_file,
    update_dataset as training_update_dataset, delete_dataset as training_delete_dataset,
    delete_dataset_item as training_delete_dataset_item,
    list_jobs as training_jobs, create_job as training_create_job, stop_job as training_stop_job,
    resume_job as training_resume_job, continue_job as training_continue_job,
    worker_health as training_worker_health, list_recipes as training_recipes, read_job_log as training_read_job_log,
    list_loras as training_loras, validate_lora as training_validate_lora, recover_lora as training_recover_lora, delete_lora as training_delete_lora,
    lora_download_path as training_lora_download_path,
    validate_checkpoint as training_validate_checkpoint, promote_checkpoint as training_promote_checkpoint, checkpoint_download_path as training_checkpoint_download_path, delete_checkpoint as training_delete_checkpoint,
    list_full_models as training_full_models, validate_full_model as training_validate_full_model, full_model_download_path as training_full_model_download_path, delete_full_model as training_delete_full_model,
    list_full_unets as training_full_unets, validate_full_unet as training_validate_full_unet, full_unet_download_path as training_full_unet_download_path, delete_full_unet as training_delete_full_unet,
    DEFAULT_SDXL as TRAINING_DEFAULT_SDXL, DATASETS as TRAINING_DATASETS
)

from core.identity_manager import (
    worker_health as identity_worker_health, create_job as identity_create_job, submit_job as identity_submit_job,
    list_jobs as identity_jobs, get_job as identity_get_job, read_log as identity_read_log,
    output_path as identity_output_path, delete_job as identity_delete_job, cancel_job as identity_cancel_job,
    next_queued_job as identity_next_queued_job, queue_snapshot as identity_queue_snapshot, list_batches as identity_batches,
    patch_job as identity_patch_job, patch_progress as identity_patch_progress,
    JOBS as IDENTITY_JOBS, BATCHES as IDENTITY_BATCHES
)



def _creator_gpu_jobs_busy():
    active=rows("SELECT id,tool,status FROM jobs WHERE status IN ('queued','running') ORDER BY created_at LIMIT 1")
    return active[0] if active else None

def _identity_gpu_busy():
    h=identity_worker_health() or {}
    if h.get("busy"):return h
    q=identity_queue_snapshot() or {}
    active=q.get("active") or {}
    if active and active.get("status")=="dispatching":
        return {"busy":True,"online":bool(h.get("online")),"job_id":active.get("id"),"mode":active.get("mode"),"phase":"dispatching"}
    return None

def _gpu_guard_payload():
    tr=training_worker_health() or {}
    if tr.get("busy"):
        return {"busy":True,"owner":"training","job_id":tr.get("job_id")}
    ident=_identity_gpu_busy()
    if ident:return {"busy":True,"owner":"identity","job_id":ident.get("job_id")}
    j=_creator_gpu_jobs_busy()
    if j:return {"busy":True,"owner":f"creator_{j.get('tool') or 'job'}","job_id":j.get("id")}
    return {"busy":False,"owner":"","job_id":None}

def _release_creator_gpu():
    from core.image_runtime import unload
    import requests
    result={"image":unload()}
    try:result["identity"]=requests.post(os.environ["CREATOR_IDENTITY_WORKER_URL"]+"/unload",headers=worker_headers(),timeout=4).json()
    except Exception as e:result["identity"]={"ok":False,"error":str(e)}
    return result






@app.get("/")
def home():return render_template("index.html")

@app.get("/api/loras")
def api_loras_inventory():
    return jsonify(ok=True,loras=scan_loras())

@app.get("/api/checkpoints")
def api_checkpoints_inventory():
    return jsonify(ok=True,checkpoints=scan_checkpoints(),default_checkpoint=_local_model_config().get('checkpoint',''))

@app.get("/api/bootstrap")
def bootstrap():
    return jsonify(projects=rows("SELECT * FROM projects ORDER BY trashed ASC, sort_order ASC, created_at ASC"),
      models=[{**m,"validation":validate_model(m),"task_support":support_matrix(m)} for m in models()],
      recipes=recipes(),loras=scan_loras(),checkpoints=scan_checkpoints(),
      user_image_presets=_list_user_image_presets(),image_preset_bindings=_load_image_preset_bindings(),
      shared_root=str(SHARED_ROOT),runtime=image_worker_health(),edition="sdxl",version=VERSION)


@app.get("/api/image/presets/user")
def image_user_presets_list():
    return jsonify(ok=True,presets=_list_user_image_presets())

@app.post("/api/image/presets/user")
def image_user_presets_save():
    d=request.get_json(force=True) or {}
    requested_id=_safe_preset_id(d.get("id"))
    preset=_normalize_user_image_preset(d,requested_id or None)
    path=_user_image_preset_path(preset["id"])
    if path.exists() and not requested_id:
        preset["id"]=_safe_preset_id(f"{preset['id']}-{uuid.uuid4().hex[:6]}")
        path=_user_image_preset_path(preset["id"])
    elif path.exists():
        try:
            old=json.loads(path.read_text(encoding="utf-8"))
            preset["created_at"]=float(old.get("created_at") or preset["created_at"])
        except Exception:pass
    path.write_text(json.dumps(preset,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return jsonify(ok=True,preset=preset,presets=_list_user_image_presets())

@app.post("/api/image/presets/user/import")
def image_user_presets_import():
    data=None
    if request.files.get("file"):
        try:data=json.loads(request.files["file"].read().decode("utf-8"))
        except Exception as e:return jsonify(error=f"Invalid preset JSON: {e}"),400
    else:
        data=request.get_json(force=True) or {}
    items=data if isinstance(data,list) else [data]
    saved=[]
    for item in items[:100]:
        if not isinstance(item,dict):continue
        preset=_normalize_user_image_preset(item,item.get("id"))
        path=_user_image_preset_path(preset["id"])
        if path.exists():
            preset["id"]=_safe_preset_id(f"{preset['id']}-{uuid.uuid4().hex[:6]}")
            path=_user_image_preset_path(preset["id"])
        path.write_text(json.dumps(preset,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        saved.append(preset)
    return jsonify(ok=True,imported=len(saved),presets=_list_user_image_presets())

@app.post("/api/image/presets/user/<pid>/duplicate")
def image_user_presets_duplicate(pid):
    path=_user_image_preset_path(pid)
    if not path.exists():return jsonify(error="Preset not found"),404
    try:d=json.loads(path.read_text(encoding="utf-8"))
    except Exception:return jsonify(error="Preset is invalid"),400
    d["id"]=_safe_preset_id(f"{d.get('id') or pid}-copy-{uuid.uuid4().hex[:5]}")
    d["name"]=f"{d.get('name') or 'User preset'} Copy"
    d["created_at"]=time.time()
    preset=_normalize_user_image_preset(d,d["id"])
    _user_image_preset_path(preset["id"]).write_text(json.dumps(preset,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return jsonify(ok=True,preset=preset,presets=_list_user_image_presets())

@app.delete("/api/image/presets/user/<pid>")
def image_user_presets_delete(pid):
    path=_user_image_preset_path(pid)
    if path.exists():path.unlink()
    return jsonify(ok=True,presets=_list_user_image_presets())

@app.get("/api/image/presets/user/<pid>/download")
def image_user_presets_download(pid):
    path=_user_image_preset_path(pid)
    if not path.exists():return jsonify(error="Preset not found"),404
    return _download_attachment(path,path.name)


def _write_image_preset_bindings(data):
    _ensure_image_preset_storage()
    IMAGE_PRESET_BINDINGS_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

@app.get("/api/image/preset-bindings")
def image_preset_bindings_get():
    return jsonify(ok=True,bindings=_load_image_preset_bindings())

@app.put("/api/image/preset-bindings/<key>")
def image_preset_bindings_put(key):
    bind_key=_safe_preset_id(key)
    if not bind_key:return jsonify(error="Invalid binding key"),400
    d=request.get_json(force=True) or {}
    model_id=str(d.get("model_id") or "")[:160]
    loras=[]
    for raw in (d.get("loras") if isinstance(d.get("loras"),list) else [])[:12]:
        if not isinstance(raw,dict):continue
        path=str(raw.get("path") or "")[:2000]
        name=str(raw.get("name") or (Path(path).name if path else "LoRA"))[:240]
        try:strength=max(-4.0,min(4.0,float(raw.get("strength",1.0))))
        except Exception:strength=1.0
        loras.append({"path":path,"name":name,"strength":strength,"auto_apply":bool(raw.get("auto_apply",True))})
    bindings=_load_image_preset_bindings()
    bindings[bind_key]={"model_id":model_id,"loras":loras,"updated_at":time.time()}
    _write_image_preset_bindings(bindings)
    return jsonify(ok=True,key=bind_key,binding=bindings[bind_key],bindings=bindings)

@app.delete("/api/image/preset-bindings/<key>")
def image_preset_bindings_delete(key):
    bind_key=_safe_preset_id(key)
    bindings=_load_image_preset_bindings()
    if bind_key in bindings:bindings.pop(bind_key,None)
    _write_image_preset_bindings(bindings)
    return jsonify(ok=True,key=bind_key,bindings=bindings)








@app.get("/api/projects/<pid>")
def project_get(pid):
    p=project_payload(pid)
    return jsonify(project=p) if p else (jsonify(error="Project not found"),404)

@app.post("/api/projects")
def project_create():
    d=request.get_json(force=True) or {}
    pid=uuid.uuid4().hex
    name=(d.get("name") or "Untitled Project").strip()[:120]
    description=(d.get("description") or "").strip()[:500]
    next_order=(one("SELECT COALESCE(MAX(sort_order),0)+10 AS n FROM projects WHERE trashed=0") or {}).get("n") or 10
    execute("INSERT INTO projects(id,name,description,sort_order) VALUES(?,?,?,?)",
            (pid,name,description,int(next_order)))
    execute("INSERT OR IGNORE INTO project_state(project_id) VALUES(?)",(pid,))
    return jsonify(ok=True,project=project_payload(pid))



@app.put("/api/projects/<pid>")
def project_update(pid):
    if not one("SELECT id FROM projects WHERE id=?",(pid,)):
        return jsonify(error="Project not found"),404
    d=request.get_json(force=True) or {}
    name=str(d.get("name") or "").strip()
    if not name:
        return jsonify(error="Project name cannot be empty"),400
    if len(name)>120:
        return jsonify(error="Project name is too long"),400
    description=str(d.get("description") or "").strip()[:500]
    execute("UPDATE projects SET name=?,description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(name,description,pid))
    return jsonify(ok=True,project=project_payload(pid))


def _normalize_project_order():
    current=rows("SELECT id FROM projects WHERE trashed=0 ORDER BY sort_order ASC, created_at ASC, id ASC")
    for idx,row in enumerate(current,1):
        execute("UPDATE projects SET sort_order=? WHERE id=?",(idx*10,row["id"]))
    return current

@app.post("/api/projects/<pid>/move")
def project_move(pid):
    d=request.get_json(force=True) or {}
    direction=str(d.get("direction") or "").lower()
    if direction not in ("up","down"):
        return jsonify(error="Choose up or down"),400
    current=_normalize_project_order()
    ids=[x["id"] for x in current]
    if pid not in ids:
        return jsonify(error="Project not found"),404
    i=ids.index(pid);j=i-1 if direction=="up" else i+1
    if j<0 or j>=len(ids):
        return jsonify(ok=True,changed=False)
    a=one("SELECT sort_order FROM projects WHERE id=?",(ids[i],)) or {}
    b=one("SELECT sort_order FROM projects WHERE id=?",(ids[j],)) or {}
    execute("UPDATE projects SET sort_order=? WHERE id=?",(int(b.get("sort_order") or ((j+1)*10)),ids[i]))
    execute("UPDATE projects SET sort_order=? WHERE id=?",(int(a.get("sort_order") or ((i+1)*10)),ids[j]))
    return jsonify(ok=True,changed=True)


@app.put("/api/projects/<pid>/active-artifact")
def active_artifact(pid):
    d=request.get_json(force=True) or {};aid=d.get("artifact_id") or ""
    execute("""INSERT INTO project_state(project_id,active_artifact_id,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(project_id) DO UPDATE SET active_artifact_id=excluded.active_artifact_id,updated_at=CURRENT_TIMESTAMP""",(pid,aid))
    return jsonify(ok=True)

@app.post('/api/projects/<pid>/upload')
def upload(pid):
    from PIL import Image, ImageOps
    if not one('SELECT id FROM projects WHERE id=?',(pid,)):return jsonify(error='Project not found'),404
    f=request.files.get('file')
    if not f:return jsonify(error='Choose an image'),400
    aid=uuid.uuid4().hex;directory=UPLOADS_DIR/pid;directory.mkdir(parents=True,exist_ok=True)
    dest=directory/f'{aid}.png'
    try:
        with Image.open(f.stream) as im:
            if im.width*im.height>40000000:raise ValueError('Maximum input size: 40 megapixels.')
            ImageOps.exif_transpose(im).convert('RGB').save(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        return jsonify(error='Invalid/unsupported image: '+str(e)),400
    role=request.form.get('role') or 'reference'
    meta={'source':'upload','original_name':secure_filename(f.filename or 'image.png'),'role':role,'media_type':'image'}
    execute('INSERT INTO artifacts(id,project_id,type,path,parent_id,metadata_json) VALUES(?,?,?,?,?,?)',(aid,pid,'image',str(dest),None,json.dumps(meta)))
    return jsonify(ok=True,artifact=decode_artifact(one('SELECT * FROM artifacts WHERE id=?',(aid,))))


@app.post('/api/image-tools/extract-frame')
def edition_extract_frame():
    import tempfile
    from core.frame_extract import extract_frame
    pid=str(request.form.get('project_id') or '')
    if not re.fullmatch('[a-f0-9]{32}',pid) or not one('SELECT id FROM projects WHERE id=?',(pid,)):return jsonify(error='Apri prima un progetto.'),400
    f=request.files.get('file')
    if not f or Path(f.filename or '').suffix.lower() not in {'.mp4','.mkv','.webm','.mov','.avi'}:return jsonify(error='Scegli un video MP4, MOV, MKV, WebM o AVI.'),400
    aid=uuid.uuid4().hex;dest=ARTIFACTS_DIR/pid/(aid+'.png');dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        (SHARED_ROOT/'cache').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='frame-',dir=SHARED_ROOT/'cache') as folder:
            src=Path(folder)/('input'+Path(f.filename).suffix.lower());total=0
            with src.open('wb') as out:
                while True:
                    chunk=f.stream.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>120*1024**2:raise ValueError('Per estrarre un frame usa un video fino a 120 MiB.')
                    out.write(chunk)
            info=extract_frame(src,dest,request.form.get('mode') or 'first',request.form.get('timestamp') or '0')
        meta={'source':'media_tools','operation':'extract_frame','original_name':secure_filename(f.filename),'extraction':info,'width':info['width'],'height':info['height']}
        execute('INSERT INTO artifacts(id,project_id,type,path,parent_id,metadata_json) VALUES(?,?,?,?,?,?)',(aid,pid,'image',str(dest),None,json.dumps(meta)))
        return jsonify(ok=True,artifact=decode_artifact(one('SELECT * FROM artifacts WHERE id=?',(aid,))))
    except (ValueError,OSError) as exc:
        dest.unlink(missing_ok=True)
        return jsonify(error=str(exc) if isinstance(exc,ValueError) else 'Impossibile salvare il frame. Controlla spazio e permessi.'),400

@app.post("/api/media-tools/run")
def api_media_tools_run():
    d=request.get_json(force=True) or {}
    project_id=(d.get("project_id") or "").strip()
    source_ids=[str(x).strip() for x in (d.get("source_artifact_ids") or []) if str(x).strip()]
    legacy=(d.get("source_artifact_id") or "").strip()
    if legacy and not source_ids:
        source_ids=[legacy]
    operation=(d.get("operation") or "").strip()
    params=d.get("params") or {}

    if not project_id:
        return jsonify(error="Select a project first"),400
    if not one("SELECT id FROM projects WHERE id=?",(project_id,)):
        return jsonify(error="Project not found"),404
    if not source_ids:
        return jsonify(error="Choose or upload one or more source assets"),400
    if not operation:
        return jsonify(error="Choose an operation"),400

    artifacts=[]
    results=[]
    errors=[]
    for source_id in source_ids:
        src=one("SELECT * FROM artifacts WHERE id=? AND project_id=?",(source_id,project_id))
        if not src:
            errors.append({"source_id":source_id,"error":"Source asset not found in the active project"})
            continue
        try:
            result=run_media_tool(project_id,src,operation,params)
            artifact=decode_artifact(one("SELECT * FROM artifacts WHERE id=?",(result["artifact_id"],)))
            results.append(result)
            artifacts.append(artifact)
        except Exception as e:
            errors.append({"source_id":source_id,"error":str(e)})

    if not artifacts:
        return jsonify(error="All media operations failed",errors=errors),400

    # Keep legacy single-result fields for older frontends.
    payload={"ok":True,"results":results,"artifacts":artifacts,"errors":errors}
    if len(artifacts)==1:
        payload["result"]=results[0]
        payload["artifact"]=artifacts[0]
    return jsonify(**payload)


@app.post("/api/projects/<pid>/trash")
def api_project_trash(pid):
    p=one("SELECT * FROM projects WHERE id=?",(pid,))
    if not p:
        return jsonify(error="Project not found"),404

    # Stop/mark pending work belonging to the project.
    for j in rows("SELECT id,status FROM jobs WHERE project_id=?",(pid,)):
        if j.get("status") in ("queued","running"):
            try:
                request_cancel(j["id"])
            except Exception:
                pass

    execute(
        "UPDATE projects SET trashed=1,trashed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (pid,)
    )
    return jsonify(ok=True)


@app.post("/api/projects/<pid>/restore")
def api_project_restore(pid):
    if not one("SELECT id FROM projects WHERE id=?",(pid,)):
        return jsonify(error="Project not found"),404
    execute(
        "UPDATE projects SET trashed=0,trashed_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (pid,)
    )
    return jsonify(ok=True)


@app.post("/api/projects/<pid>/delete-forever")
def api_project_delete_forever(pid):
    p=one("SELECT * FROM projects WHERE id=?",(pid,))
    if not p:
        return jsonify(error="Project not found"),404
    if not int(p.get("trashed") or 0):
        return jsonify(error="Project must be moved to Trash first"),400

    jobs=rows("SELECT id,status FROM jobs WHERE project_id=?",(pid,))
    if any(j.get("status")=="running" for j in jobs):
        return jsonify(error="A project job is still stopping. Wait a moment and try Delete forever again."),409

    # Remove every concrete artifact path first.
    for art in rows("SELECT path FROM artifacts WHERE project_id=?",(pid,)):
        try:
            path=Path(art.get("path") or "")
            if path.exists() and path.is_file():
                path.unlink()
        except Exception:
            pass

    # Remove job progress/cancel files.
    for j in jobs:
        for pth in (
            SHARED_ROOT/"cache"/"job_progress"/f"{j['id']}.json",
            SHARED_ROOT/"cache"/"job_cancel"/f"{j['id']}.cancel",
        ):
            try:
                pth.unlink(missing_ok=True)
            except Exception:
                pass

    # Remove project-owned directories.
    for base in (PROJECTS_DIR,ARTIFACTS_DIR,UPLOADS_DIR,THUMBNAILS_DIR):
        try:
            shutil.rmtree(base/pid,ignore_errors=True)
        except Exception:
            pass

    # Database dependants first, then project.
    execute("DELETE FROM conversations WHERE project_id=?",(pid,))
    execute("DELETE FROM project_state WHERE project_id=?",(pid,))
    execute("DELETE FROM artifacts WHERE project_id=?",(pid,))
    execute("DELETE FROM jobs WHERE project_id=?",(pid,))
    execute("DELETE FROM projects WHERE id=?",(pid,))
    return jsonify(ok=True)


@app.get("/api/artifacts/<aid>")
def artifact_get(aid):
    a=decode_artifact(one("SELECT * FROM artifacts WHERE id=?",(aid,)))
    return jsonify(artifact=a) if a else (jsonify(error="Artifact not found"),404)

@app.delete("/api/artifacts/<aid>")
def artifact_delete(aid):
    art=one("SELECT * FROM artifacts WHERE id=?",(aid,))
    if not art:return jsonify(error="Artifact not found"),404
    try:
        p=Path(art.get("path") or "")
        if p.exists() and p.is_file(): p.unlink()
    except Exception as e:
        return jsonify(error=f"Could not delete artifact file: {e}"),500
    execute("UPDATE jobs SET output_artifact_id=NULL WHERE output_artifact_id=?",(aid,))
    execute("UPDATE project_state SET active_artifact_id='' WHERE active_artifact_id=?",(aid,))
    execute("DELETE FROM artifacts WHERE id=?",(aid,))
    return jsonify(ok=True)

@app.post('/api/jobs/<jid>/cancel')
def job_cancel(jid):
    j=one('SELECT * FROM jobs WHERE id=?',(jid,))
    if not j:return jsonify(error='Job not found'),404
    request_cancel(jid)
    return jsonify(ok=True)


def _run_worker_script(name):
    return {"ok":False,"error":"Use creator-sdxl stop/start to restart this isolated installation."}

@app.post("/api/jobs/cleanup")
def jobs_cleanup():
    waiting=rows("SELECT id FROM jobs WHERE status='queued'")
    for j in waiting:request_cancel(j["id"])
    return jsonify(ok=True,cancelled=len(waiting),queue=queue_snapshot())

@app.get("/api/queue")
def queue_get():
    return jsonify(queue=queue_snapshot())

@app.get("/api/artifacts/<aid>/file")
def artifact_file(aid):
    a=one("SELECT * FROM artifacts WHERE id=?",(aid,))
    if not a:return jsonify(error="Artifact not found"),404
    p=Path(a["path"])
    if not p.exists():return jsonify(error="Artifact file missing"),404
    if request.args.get('download')=='1':return _download_attachment(p,p.name)
    return send_file(p)

def validate_image_request(pid,tool,params):
    if tool not in {'generate_image','edit_image','img2img','inpaint','reference','multi_image'}:raise ValueError('Unsupported SDXL task')
    for key,default,lo,hi in [('width',1024,64,4096),('height',1024,64,4096),('steps',30,1,150),('batch',1,1,8)]:
        value=params.get(key,default)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or int(value)!=value or not lo<=value<=hi:raise ValueError(f'Invalid {key} ({lo}–{hi})')
    for key in ('width','height'):
        if int(params.get(key,1024))%8:raise ValueError(key+' must be a multiple of 8')
    for key,default,lo,hi in [('cfg',6.0,0.0,30.0),('strength',0.35,0.01,1.0)]:
        value=float(params.get(key,default))
        if not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f'Invalid {key}')
    ids=[params.get('source_artifact_id'),params.get('mask_artifact_id')]+list(params.get('reference_artifact_ids') or [])
    for aid in filter(None,ids):
        if not one("SELECT id FROM artifacts WHERE id=? AND project_id=? AND type='image'",(aid,pid)):raise ValueError('Input image not in this project')

@app.post("/api/jobs")
def job_create():
    tr=training_worker_health() or {}
    if tr.get("busy"):return jsonify(error="Training is using the GPU. Stop/finish training before generating."),409
    ident=_identity_gpu_busy()
    if ident:return jsonify(error="Identity Studio is using the GPU. Wait for the Identity job to finish."),409
    d=request.get_json(force=True) or {}
    pid=d.get("project_id")
    if not one("SELECT id FROM projects WHERE id=?",(pid,)):return jsonify(error="Select a project first"),400
    tool=d.get("tool") or "generate_image";model=d.get("model_id") or "auto"
    params=dict(d.get("params") or {})
    try:validate_image_request(pid,tool,params)
    except (ValueError,TypeError) as e:return jsonify(error=str(e)),400
    batch=max(1,min(8,int(params.get("batch") or 1)))
    ids=[]
    base_seed=int(params.get("seed",-1))
    for i in range(batch):
        p=dict(params);p["batch"]=1
        if base_seed>=0:p["seed"]=base_seed+i
        jid=create_job(pid,tool,model,d.get("prompt") or "",p)
        ids.append(jid);start_job(jid)
    return jsonify(ok=True,id=ids[0],ids=ids,batch=batch)

@app.get("/api/jobs/<jid>")
def job_get(jid):
    j=one("SELECT * FROM jobs WHERE id=?",(jid,))
    return jsonify(job=j) if j else (jsonify(error="Job not found"),404)


# 0.1.0.27: one planner for preview and enqueue; no silent Cartesian truncation.
from core.image_test_plan import plan_image_test

def _prepare_image_test(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid image test request")
    pid=str(data.get("project_id") or "").strip()
    if not pid or not one("SELECT id FROM projects WHERE id=?",(pid,)):
        raise ValueError("Open a project first.")
    tool=str(data.get("tool") or "generate_image").strip()
    task=task_from_tool(tool)
    params=data.get("params") or {}
    sweep=data.get("sweep") or {}
    if not isinstance(params,dict) or not isinstance(sweep,dict):
        raise ValueError("Invalid parameters or test configuration")
    params=dict(params);sweep=dict(sweep)
    validate_image_request(pid,tool,params)
    if task in {"edit","inpaint"} and not params.get("source_artifact_id"):
        raise ValueError("Select a source image.")
    if task=="inpaint" and not params.get("mask_artifact_id"):
        raise ValueError("Select or paint a mask.")
    if task in {"reference","multi_image"} and not params.get("reference_artifact_ids"):
        raise ValueError("Select at least one reference image.")
    plan=plan_image_test(params,sweep,task)
    # A random seed is chosen only at preview, then sent back as a concrete value.
    params["seed"]=plan["base_seed"];params["batch"]=1
    payload={"project_id":pid,"tool":tool,"model_id":str(data.get("model_id") or "auto"),
             "prompt":str(data.get("prompt") or ""),"params":params,"sweep":sweep}
    return payload,plan

@app.post("/api/image/auto-test/preview")
def image_auto_test_preview():
    try:
        payload,plan=_prepare_image_test(request.get_json(force=True))
    except (ValueError,TypeError,OverflowError) as exc:
        return jsonify(error=str(exc)),400
    payload["expected_count"]=plan["count"]
    return jsonify(ok=True,plan=plan,request=payload)

@app.post("/api/image/auto-test")
def image_auto_test():
    data=request.get_json(force=True)
    try:
        payload,plan=_prepare_image_test(data)
        if "expected_count" in data and data["expected_count"] != plan["count"]:
            raise ValueError("The test count changed: open the preview again.")
    except (ValueError,TypeError,OverflowError) as exc:
        return jsonify(error=str(exc)),400
    pid,tool,model_id,prompt=(payload[k] for k in ("project_id","tool","model_id","prompt"))
    params,sweep=payload["params"],payload["sweep"]
    profile=str(sweep.get("profile") or "custom")[:80]
    name=str(sweep.get("name") or f"Image test {profile}")[:140]
    batch_id=uuid.uuid4().hex[:10];created=time.time();ids=[]
    # Every field/range and the full count have been validated before creating jobs.
    for variant in plan["variants"]:
        p=dict(params)
        for key in ("cfg","steps","strength","seed"):
            if key in variant:p[key]=variant[key]
        label=f"CFG {p['cfg']:g} · Steps {p['steps']}"
        if plan["task"]!="generate":label=f"Denoise {p['strength']:.3f} · "+label
        label+=f" · Seed {p['seed']}"
        p.update(batch=1,auto_test=True,batch_id=batch_id,batch_name=name,
                 batch_created_at=created,test_index=variant["index"],test_total=plan["count"],
                 test_profile=profile,test_label=label)
        jid=create_job(pid,tool,model_id,prompt,p);ids.append(jid);start_job(jid)
    return jsonify(ok=True,batch_id=batch_id,batch_name=name,count=len(ids),job_ids=ids),202

@app.get("/api/runtime/gpu/guard")
def gpu_guard():
    return jsonify(ok=True,**_gpu_guard_payload())

@app.post("/api/runtime/gpu/release")
def gpu_release():
    guard=_gpu_guard_payload()
    if guard.get("busy"):
        return jsonify(ok=False,error="Zetalvx Image Lab GPU is busy",**guard),409
    return jsonify(ok=True,released=_release_creator_gpu())

@app.get("/api/runtime/image/health")
def image_runtime_health():return jsonify(image_worker_health())

@app.post("/api/runtime/image/unload")
def image_runtime_unload():
    if _gpu_guard_payload().get("busy"):return jsonify(error="A GPU job is active"),409
    return jsonify(_release_creator_gpu())

@app.get("/api/models/<mid>")
def model_get(mid):
    m=model_by_id(mid)
    if not m:return jsonify(error="Model not found"),404
    return jsonify(model=m,validation=validate_model(m))

@app.put("/api/models/<mid>")
def model_put(mid):
    d=request.get_json(force=True) or {};m=update_model(mid,d)
    if not m:return jsonify(error="Model not found"),404
    return jsonify(ok=True,model=m,validation=validate_model(m))

@app.post("/api/models/<mid>/validate")
def model_validate(mid):
    m=model_by_id(mid)
    if not m:return jsonify(error="Model not found"),404
    return jsonify(validation=validate_model(m))

@app.post("/api/models/<mid>/probe")
def model_probe(mid):
    m=model_by_id(mid)
    if not m:return jsonify(error="Model not found"),404
    return jsonify(probe=image_worker_probe(m))













def _identity_num(form,name,default,typ=float):
    try:return typ(form.get(name,default))
    except Exception:return typ(default)


def _identity_form_loras(form):
    try:
        raw=json.loads(form.get("loras") or "[]")
        if not isinstance(raw,list):raw=[]
    except Exception:raw=[]
    out=[]
    for item in raw[:4]:
        if not isinstance(item,dict):continue
        path=str(item.get("path") or "").strip()
        if not path:continue
        try:strength=float(item.get("strength",1.0))
        except Exception:strength=1.0
        out.append({"path":path,"name":str(item.get("name") or Path(path).name),"strength":strength})
    return out


def _identity_save_inputs(root,refs,base,pose):
    inp=Path(root)/"inputs";inp.mkdir(parents=True,exist_ok=True)
    ref_paths=[]
    for i,f in enumerate(refs[:4]):
        ext=Path(secure_filename(f.filename) or "ref.png").suffix.lower() or ".png"
        dest=inp/f"reference_{i+1}{ext}";f.save(dest);ref_paths.append(str(dest))
    base_path=""
    if base and base.filename:
        ext=Path(secure_filename(base.filename) or "base.png").suffix.lower() or ".png"
        dest=inp/f"base{ext}";base.save(dest);base_path=str(dest)
    pose_path=""
    if pose and pose.filename:
        ext=Path(secure_filename(pose.filename) or "pose.png").suffix.lower() or ".png"
        dest=inp/f"pose{ext}";pose.save(dest);pose_path=str(dest)
    return ref_paths,base_path,pose_path


def _identity_cfg_from_form(form,jid,project_id,ref_paths,base_path,pose_path,overrides=None):
    mode=(form.get("mode") or "instantid").strip().lower()
    cfg={
        "id":jid,"project_id":project_id,"mode":mode,
        "prompt":(form.get("prompt") or "").strip(),
        "negative_prompt":(form.get("negative_prompt") or "").strip(),
        "reference_paths":ref_paths,"base_image_path":base_path,"pose_image_path":pose_path,
        "base_model":(form.get("base_model") or (models()[0].get("config") or {}).get("checkpoint",str(MODELS_ROOT/"SDXL/sd_xl_base_1.0.safetensors"))).strip(),
        "loras":_identity_form_loras(form),
        "identity_strength":_identity_num(form,"identity_strength",0.8),"pose_strength":_identity_num(form,"pose_strength",0.8),
        "denoise_strength":_identity_num(form,"denoise_strength",0.35),"steps":_identity_num(form,"steps",30,int),"guidance":_identity_num(form,"guidance",5.0),
        "seed":_identity_num(form,"seed",-1,int),"width":_identity_num(form,"width",0,int),"height":_identity_num(form,"height",0,int),
        "face_mask_padding":_identity_num(form,"face_mask_padding",0.18),
        "enhance_face_region":(form.get("enhance_face_region") or "false").lower() in ("1","true","yes","on"),
        "instantid_generation_mode":(form.get("instantid_generation_mode") or "txt2img").strip(),
        "control_guidance_start":_identity_num(form,"control_guidance_start",0.0),"control_guidance_end":_identity_num(form,"control_guidance_end",1.0),
        "scheduler":(form.get("scheduler") or "default").strip(),"eta":_identity_num(form,"eta",0.0),
        "clip_skip":_identity_num(form,"clip_skip",0,int),"guess_mode":(form.get("guess_mode") or "false").lower() in ("1","true","yes","on"),
        "detection_size":_identity_num(form,"detection_size",640,int),"target_face":(form.get("target_face") or "largest").strip(),
        "source_face":(form.get("source_face") or "largest").strip(),"swap_all":(form.get("swap_all") or "false").lower() in ("1","true","yes","on"),
        "refine_with_sdxl":(form.get("refine_with_sdxl") or "false").lower() in ("1","true","yes","on"),
        "swap_refine_denoise":_identity_num(form,"swap_refine_denoise",0.18),"swap_refine_steps":_identity_num(form,"swap_refine_steps",24,int),
        "swap_refine_guidance":_identity_num(form,"swap_refine_guidance",4.5),"swap_refine_scheduler":(form.get("swap_refine_scheduler") or "dpmpp_2m_karras").strip(),
        "swap_refine_seed":_identity_num(form,"swap_refine_seed",-1,int)
    }
    if overrides:cfg.update(overrides)
    return cfg


@app.get("/api/identity/bootstrap")
def api_identity_bootstrap():
    return jsonify(ok=True,runtime=identity_worker_health(),jobs=identity_jobs(),queue=identity_queue_snapshot(),batches=identity_batches(),
                   checkpoints=scan_checkpoints(),loras=scan_loras(),
                   default_base_model=(models()[0].get("config") or {}).get("checkpoint",str(MODELS_ROOT/"SDXL/sd_xl_base_1.0.safetensors")))


# 1.0.11: an upload failure is not an inference failure. Keep this boundary
# scoped to Identity, before any input file/job is committed. Never read the
# raw WSGI stream here: Werkzeug owns multipart parsing and enforces the same
# MAX_CONTENT_LENGTH / form-memory / part-count limits as before.
def _identity_upload_boundary(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        diagnostic_id=uuid.uuid4().hex[:12]
        try:
            if request.mimetype != "multipart/form-data":
                raise UnsupportedMediaType()
            if not request.mimetype_params.get("boundary"):
                raise BadRequest()
            # Parse once; all later request.form/files accesses use the cache.
            form=request.form
            files=request.files
            if not form and not files:
                raise BadRequest()
        except (BadRequest, RequestEntityTooLarge, UnsupportedMediaType) as exc:
            if isinstance(exc, ClientDisconnected):
                code="identity_upload_incomplete"
                message="Identity upload was interrupted before queuing. Reselect the images and try again."
            elif isinstance(exc, RequestEntityTooLarge):
                code="identity_upload_too_large"
                message="Identity upload exceeds the server limits. Use smaller images or fewer attachments."
            elif isinstance(exc, UnsupportedMediaType):
                code="identity_upload_type"
                message="Identity requires an image upload form. Reload the page and try again."
            else:
                code="identity_upload_invalid"
                message="Identity upload could not be read. No job was queued. Reselect the images and try again."
            print(f"[IDENTITY UPLOAD] id={diagnostic_id} phase=parse endpoint={request.endpoint} status={exc.code} error={type(exc).__name__} content_length={request.content_length}",flush=True)
            return jsonify(ok=False,error=message,code=code,diagnostic_id=diagnostic_id,queued=False),exc.code
        return fn(*args, **kwargs)
    return wrapped


@app.post("/api/identity/jobs")
@_identity_upload_boundary
def api_identity_create():
    project_id=(request.form.get("project_id") or "").strip()
    if not project_id or not one("SELECT id FROM projects WHERE id=?",(project_id,)):
        return jsonify(error="Open a project first."),400
    mode=(request.form.get("mode") or "instantid").strip().lower()
    if mode not in {"face_swap","instantid"}:return jsonify(error="Unsupported Identity mode"),400
    icfg=settings()
    if mode=="instantid" and not bool(icfg.get('identity_instantid_enabled',True)):return jsonify(error="InstantID is disabled in Models."),400
    if mode=="face_swap" and not bool(icfg.get('identity_faceswap_enabled',True)):return jsonify(error="Face Swap is disabled in Models."),400
    refs=[f for f in request.files.getlist("references") if f and f.filename]
    if not refs:return jsonify(error="At least one face reference is required."),400
    base=request.files.get("base_image");pose=request.files.get("pose_image")
    if mode=="face_swap" and (not base or not base.filename):return jsonify(error="Base image is required for Face Swap."),400
    if mode=="instantid" and (request.form.get("instantid_generation_mode") or "txt2img")=="img2img" and (not base or not base.filename):
        return jsonify(error="Base image is required for InstantID Img2Img."),400
    jid=uuid.uuid4().hex[:12]
    ref_paths,base_path,pose_path=_identity_save_inputs(IDENTITY_JOBS/jid,refs,base,pose)
    cfg=_identity_cfg_from_form(request.form,jid,project_id,ref_paths,base_path,pose_path,{"queue_order":time.time()})
    try:
        identity_create_job(cfg)
        return jsonify(ok=True,job_id=jid,status="queued",queue=identity_queue_snapshot()),202
    except Exception as e:return jsonify(error=str(e)),500


@app.post("/api/identity/auto-test")
@_identity_upload_boundary
def api_identity_auto_test():
    import itertools,secrets
    project_id=(request.form.get("project_id") or "").strip()
    if not project_id or not one("SELECT id FROM projects WHERE id=?",(project_id,)):
        return jsonify(error="Open a project first."),400
    mode=(request.form.get("mode") or "instantid").strip().lower()
    if mode!="instantid":return jsonify(error="Auto Test is currently available for InstantID / Face Consistency."),400
    refs=[f for f in request.files.getlist("references") if f and f.filename]
    if not refs:return jsonify(error="At least one face reference is required."),400
    base=request.files.get("base_image");pose=request.files.get("pose_image")
    gen_mode=(request.form.get("instantid_generation_mode") or "txt2img").strip()
    if gen_mode=="img2img" and (not base or not base.filename):return jsonify(error="InstantID Img2Img Auto Test requires a Base image."),400
    try:sweep=json.loads(request.form.get("sweep_config") or "{}")
    except Exception as e:return jsonify(error=f"Invalid sweep configuration: {e}"),400
    def vals(key,default,lo=None,hi=None):
        raw=sweep.get(key,default)
        if not isinstance(raw,list):raw=[raw]
        out=[]
        for x in raw:
            try:v=float(x)
            except Exception:continue
            if lo is not None:v=max(lo,v)
            if hi is not None:v=min(hi,v)
            if v not in out:out.append(v)
        return out or list(default)
    ids=vals("identity",[_identity_num(request.form,"identity_strength",0.85)],0,1.5)
    poses=vals("pose",[_identity_num(request.form,"pose_strength",0.8)],0,1.5)
    cfgs=vals("cfg",[_identity_num(request.form,"guidance",5.0)],1,30)
    dens=vals("denoise",[_identity_num(request.form,"denoise_strength",0.35)],0.01,1.0) if gen_mode=="img2img" else [_identity_num(request.form,"denoise_strength",0.35)]
    cends=vals("control_end",[_identity_num(request.form,"control_guidance_end",1.0)],0,1)
    combos=list(itertools.product(ids,poses,cfgs,dens,cends))
    max_jobs=max(1,min(48,int(sweep.get("max_jobs") or 24)))
    if len(combos)>max_jobs:
        return jsonify(error=f"This sweep creates {len(combos)} jobs; current limit is {max_jobs}. Reduce the value lists."),400
    bid=uuid.uuid4().hex[:10];created=time.time();broot=IDENTITY_BATCHES/bid
    ref_paths,base_path,pose_path=_identity_save_inputs(broot,refs,base,pose)
    base_seed=_identity_num(request.form,"seed",-1,int)
    vary_seed=bool(sweep.get("vary_seed",False))
    if base_seed<0 and not vary_seed:base_seed=secrets.randbelow(2**31-2)+1
    auto_save=bool(sweep.get("auto_save_library",True))
    batch_name=str(sweep.get("name") or f"InstantID Auto Test {bid}")[:120]
    ids_out=[]
    total=len(combos)
    for i,(ident,pose_v,cfg_v,den,ce) in enumerate(combos,1):
        jid=uuid.uuid4().hex[:12]
        if vary_seed:
            seed=(base_seed+i-1) if base_seed>=0 else secrets.randbelow(2**31-2)+1
        else:seed=base_seed
        label=f"ID {ident:.2f} · Pose {pose_v:.2f} · CFG {cfg_v:.2f}"+(f" · D {den:.2f}" if gen_mode=="img2img" else "")+(f" · End {ce:.2f}" if len(cends)>1 else "")
        overrides={
            "identity_strength":ident,"pose_strength":pose_v,"guidance":cfg_v,"denoise_strength":den,
            "control_guidance_end":ce,"seed":seed,"batch_id":bid,"batch_name":batch_name,"batch_created_at":created,
            "test_index":i,"test_total":total,"test_label":label,"auto_save_library":auto_save,"queue_order":created+i/10000.0
        }
        cfg=_identity_cfg_from_form(request.form,jid,project_id,ref_paths,base_path,pose_path,overrides)
        identity_create_job(cfg);ids_out.append(jid)
    broot.mkdir(parents=True,exist_ok=True)
    (broot/'batch.json').write_text(json.dumps({"id":bid,"name":batch_name,"created_at":created,"project_id":project_id,"jobs":ids_out,"sweep":sweep},ensure_ascii=False,indent=2),encoding='utf-8')
    return jsonify(ok=True,batch_id=bid,batch_name=batch_name,count=len(ids_out),job_ids=ids_out,queue=identity_queue_snapshot()),202


@app.post("/api/identity/jobs/<jid>/cancel")
def api_identity_job_cancel(jid):
    j=identity_get_job(jid)
    if not j:return jsonify(error="Identity job not found"),404
    if j.get("status")=="running":return jsonify(error="Running Identity inference cannot be interrupted safely yet. You can cancel queued jobs."),409
    if identity_cancel_job(jid):return jsonify(ok=True,status="cancelled",queue=identity_queue_snapshot())
    return jsonify(ok=True,status=j.get("status"))


@app.get("/api/identity/jobs/<jid>/file")
def api_identity_job_file(jid):
    p=identity_output_path(jid)
    if not p:return jsonify(error="Identity output not found"),404
    return send_file(p,as_attachment=False,download_name=p.name)

@app.get("/api/identity/jobs/<jid>/download")
def api_identity_job_download(jid):
    p=identity_output_path(jid)
    if not p:return jsonify(error="Identity output not found"),404
    return _download_attachment(p,f"identity_{jid}.png")

@app.get("/api/identity/jobs/<jid>/log")
def api_identity_job_log(jid):
    if not identity_get_job(jid):return jsonify(error="Identity job not found"),404
    return jsonify(ok=True,log=identity_read_log(jid))

@app.delete("/api/identity/jobs/<jid>")
def api_identity_job_delete(jid):
    j=identity_get_job(jid)
    if not j:return jsonify(error="Identity job not found"),404
    if j.get("status") in ("running","dispatching"):return jsonify(error="Cannot delete an active Identity job"),409
    identity_delete_job(jid);return jsonify(ok=True)


def _identity_save_to_library(jid):
    j=identity_get_job(jid)
    if not j:raise RuntimeError("Identity job not found")
    existing=str(j.get("library_artifact_id") or "").strip()
    if existing and one("SELECT id FROM artifacts WHERE id=?",(existing,)):
        return decode_artifact(one("SELECT * FROM artifacts WHERE id=?",(existing,)))
    p=identity_output_path(jid)
    if not p:raise RuntimeError("Identity output not found")
    project_id=(j.get("project_id") or "").strip()
    if not one("SELECT id FROM projects WHERE id=?",(project_id,)):raise RuntimeError("Project not found")
    aid=uuid.uuid4().hex
    outdir=ARTIFACTS_DIR/project_id;outdir.mkdir(parents=True,exist_ok=True)
    dst=outdir/f"{aid}.png";shutil.copy2(p,dst)
    params_keys=(
        "identity_strength","pose_strength","denoise_strength","steps","guidance","seed","width","height",
        "instantid_generation_mode","control_guidance_start","control_guidance_end","scheduler","eta","clip_skip",
        "guess_mode","enhance_face_region","face_mask_padding","detection_size","target_face","source_face","swap_all",
        "refine_with_sdxl","swap_refine_denoise","swap_refine_steps","swap_refine_guidance","swap_refine_scheduler","swap_refine_seed"
    )
    meta={
        "source":"identity_studio","original_name":f"identity_{jid}.png","identity_job_id":jid,"identity_mode":j.get("mode"),
        "prompt":j.get("prompt"),"negative_prompt":j.get("negative_prompt"),"base_model":j.get("base_model"),"loras":j.get("loras") or [],
        "batch_id":j.get("batch_id"),"batch_name":j.get("batch_name"),"test_index":j.get("test_index"),"test_total":j.get("test_total"),
        "test_label":j.get("test_label"),"params":{k:j.get(k) for k in params_keys}
    }
    execute("INSERT INTO artifacts(id,project_id,type,path,parent_id,metadata_json) VALUES(?,?,?,?,?,?)",(aid,project_id,"image",str(dst),None,json.dumps(meta,ensure_ascii=False)))
    execute("""INSERT INTO project_state(project_id,active_artifact_id,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(project_id) DO UPDATE SET active_artifact_id=excluded.active_artifact_id,updated_at=CURRENT_TIMESTAMP""",(project_id,aid))
    identity_patch_job(jid,library_artifact_id=aid,library_saved_at=time.time())
    return decode_artifact(one("SELECT * FROM artifacts WHERE id=?",(aid,)))


@app.post("/api/identity/jobs/<jid>/library")
def api_identity_job_to_library(jid):
    try:return jsonify(ok=True,artifact=_identity_save_to_library(jid))
    except Exception as e:return jsonify(error=str(e)),404


def _release_non_identity_creator_gpu():
    from core.image_runtime import unload
    return {"image":unload()}


_IDENTITY_DISPATCHER_STARTED=False
_IDENTITY_DISPATCHER_LOCK=threading.Lock()

def _identity_dispatch_loop():
    while True:
        try:
            # Auto Test can optionally publish every finished variant to the project Library.
            for finished in identity_jobs(120):
                if finished.get("status")=="completed" and finished.get("auto_save_library") and not finished.get("library_artifact_id"):
                    try:_identity_save_to_library(finished["id"])
                    except Exception as e:
                        identity_patch_job(finished["id"],library_save_error=str(e))
            health=identity_worker_health() or {}
            if not health.get("online") or health.get("busy"):
                time.sleep(1.0);continue
            # If Creator/worker was restarted during a job, the worker is now idle but
            # progress may still say running/dispatching. Identity inference has no
            # resumable sampler state, so safely requeue it from the beginning.
            for stale in identity_jobs(250):
                if stale.get("status") in ("running","dispatching"):
                    identity_patch_progress(stale["id"],status="queued",phase="queued",progress=0.0,phase_detail="Recovered after Identity worker/app restart; job will restart from the beginning")
            job=identity_next_queued_job()
            if not job:
                time.sleep(1.0);continue
            # Identity queue may fill while Training, Auto Dataset, or the normal Image/Video queue is active.
            # It waits rather than returning BUSY to the user.
            tr=training_worker_health() or {}
            if tr.get("busy") or _creator_gpu_jobs_busy():
                time.sleep(1.0);continue
            identity_patch_progress(job["id"],status="dispatching",phase="dispatching",progress=0.01,phase_detail="Preparing GPU and dispatching queued Identity job")
            _release_non_identity_creator_gpu()
            try:
                r=identity_submit_job(job["id"])
                if r.get("busy"):
                    identity_patch_progress(job["id"],status="queued",phase="queued",progress=0.0,phase_detail="Worker busy; retained in queue")
                # On success the worker immediately owns progress.json and moves it to running.
            except Exception as e:
                identity_patch_progress(job["id"],status="failed",phase="failed",progress=0.0,error=str(e),phase_detail="Identity dispatch failed")
        except Exception:
            # Never let a malformed historical job kill the queue dispatcher.
            pass
        time.sleep(0.35)


def _ensure_identity_dispatcher():
    global _IDENTITY_DISPATCHER_STARTED
    if _IDENTITY_DISPATCHER_STARTED:return
    with _IDENTITY_DISPATCHER_LOCK:
        if _IDENTITY_DISPATCHER_STARTED:return
        threading.Thread(target=_identity_dispatch_loop,daemon=True,name="creator-identity-serial-queue").start()
        _IDENTITY_DISPATCHER_STARTED=True


@app.post("/api/runtime/identity/unload")
def api_identity_runtime_unload():
    import requests as _requests
    try:
        u=os.getenv("CREATOR_IDENTITY_WORKER_URL","http://127.0.0.1:8205").rstrip("/")
        r=_requests.post(u+"/unload",headers=worker_headers(),timeout=3)
        return (r.text,r.status_code,{"Content-Type":r.headers.get("Content-Type","application/json")})
    except Exception as e:return jsonify(error=str(e)),503

@app.get("/api/training/bootstrap")
def api_training_bootstrap():
    runtime=training_worker_health()
    base=(models()[0].get("config") or {}).get("checkpoint") or TRAINING_DEFAULT_SDXL
    return jsonify(ok=True,runtime=runtime,datasets=training_datasets(),loras=training_lora_inventory(),
      full_models=training_full_models(),full_unets=training_full_unets(),jobs=training_jobs(runtime),
      recipes=training_recipes(),default_sdxl=base)

@app.get("/api/training/datasets")
def api_training_datasets_list():
    return jsonify(ok=True,datasets=training_datasets())

def _dataset_workspace():
    return app.extensions['zetalvx_dataset_workspace']

@app.post("/api/training/datasets")
def api_training_dataset_create():
    w=_dataset_workspace()
    return jsonify(w.response(w.create(request.get_json(force=True) or {})))

@app.delete("/api/training/datasets/<did>")
def api_training_dataset_delete(did):
    return jsonify(ok=True,deleted=_dataset_workspace().remove(did),datasets=training_datasets())

@app.get("/api/training/datasets/<did>")
def api_training_dataset_get(did):
    w=_dataset_workspace()
    return jsonify(w.response(w.read(did)))

@app.post("/api/training/datasets/<did>/upload")
def api_training_dataset_upload(did):
    files=request.files.getlist("files") or request.files.getlist("file")
    return jsonify(_dataset_workspace().uploads(did,files,request.form.get('caption')))

@app.put("/api/training/datasets/<did>")
def api_training_dataset_update(did):
    w=_dataset_workspace()
    return jsonify(w.response(w.update(did,request.get_json(force=True) or {})))

@app.delete("/api/training/datasets/<did>/items/<iid>")
def api_training_dataset_item_delete(did,iid):
    w=_dataset_workspace()
    return jsonify(w.response(w.remove_item(did,iid)))

@app.get("/api/training/datasets/<did>/items/<iid>/file")
def api_training_dataset_item_file(did,iid):
    r=send_file(_dataset_workspace().image_path(did,iid))
    r.headers['Cache-Control']='private, max-age=300'
    return r

@app.get("/api/training/loras")
def api_training_loras_list():
    return jsonify(ok=True,loras=training_lora_inventory())

@app.post("/api/training/loras/<lid>/validate")
def api_training_lora_validate(lid):
    try:return jsonify(ok=True,validation=training_validate_lora(lid))
    except Exception as e:return jsonify(error=str(e)),400

@app.post("/api/training/loras/<lid>/recover")
def api_training_lora_recover(lid):
    active=_creator_gpu_jobs_busy()
    if active:return jsonify(error="A Creator generation job is active. Wait for it to finish before recovering a LoRA."),409
    try:return jsonify(ok=True,recovered=training_recover_lora(lid),loras=training_lora_inventory())
    except Exception as e:return jsonify(error=str(e)),409

@app.delete("/api/training/loras/<lid>")
def api_training_lora_delete(lid):
    active=_gpu_guard_payload().get('busy')
    if active:return jsonify(error="A Creator generation job is active. Wait for it to finish before deleting a LoRA."),409
    try:return jsonify(ok=True,deleted=training_delete_lora(lid),loras=training_lora_inventory())
    except Exception as e:return jsonify(error=str(e)),409

@app.get("/api/training/loras/<lid>/download")
def api_training_lora_download(lid):
    try:
        p=training_lora_download_path(lid)
        return _download_attachment(p,p.name)
    except HTTPException:raise
    except Exception as e:return jsonify(error=str(e)),404

@app.post("/api/training/jobs/<jid>/checkpoints/<int:step>/validate")
def api_training_checkpoint_validate(jid,step):
    try:return jsonify(ok=True,validation=training_validate_checkpoint(jid,step))
    except Exception as e:return jsonify(error=str(e)),400

@app.post("/api/training/jobs/<jid>/checkpoints/<int:step>/promote")
def api_training_checkpoint_promote(jid,step):
    try:return jsonify(ok=True,promoted=training_promote_checkpoint(jid,step),loras=training_lora_inventory())
    except Exception as e:return jsonify(error=str(e)),400

@app.get("/api/training/jobs/<jid>/checkpoints/<int:step>/download")
def api_training_checkpoint_download(jid,step):
    try:
        p=training_checkpoint_download_path(jid,step)
        return _download_attachment(p,p.name)
    except HTTPException:raise
    except Exception as e:return jsonify(error=str(e)),404

@app.delete("/api/training/jobs/<jid>/checkpoints/<int:step>")
def api_training_checkpoint_delete(jid,step):
    try:return jsonify(ok=True,deleted=training_delete_checkpoint(jid,step))
    except Exception as e:return jsonify(error=str(e)),409

@app.get("/api/training/full-models")
def api_training_full_models_list():
    return jsonify(ok=True,models=training_full_models())

@app.post("/api/training/full-models/<mid>/validate")
def api_training_full_model_validate(mid):
    try:return jsonify(ok=True,validation=training_validate_full_model(mid))
    except Exception as e:return jsonify(error=str(e)),400

@app.get("/api/training/full-models/<mid>/download")
def api_training_full_model_download(mid):
    try:
        p=training_full_model_download_path(mid)
        return _download_attachment(p,p.name)
    except HTTPException:raise
    except Exception as e:return jsonify(error=str(e)),404

@app.delete("/api/training/full-models/<mid>")
def api_training_full_model_delete(mid):
    try:return jsonify(ok=True,deleted=training_delete_full_model(mid),models=training_full_models())
    except Exception as e:return jsonify(error=str(e)),409

@app.get("/api/training/full-unets")
def api_training_full_unets_list():
    return jsonify(ok=True,unets=training_full_unets())

@app.post("/api/training/full-unets/<uid>/validate")
def api_training_full_unet_validate(uid):
    try:return jsonify(ok=True,validation=training_validate_full_unet(uid))
    except Exception as e:return jsonify(error=str(e)),400

@app.get("/api/training/full-unets/<uid>/download")
def api_training_full_unet_download(uid):
    try:
        p=training_full_unet_download_path(uid)
        return _download_attachment(p,p.name)
    except HTTPException:raise
    except Exception as e:return jsonify(error=str(e)),404

@app.delete("/api/training/full-unets/<uid>")
def api_training_full_unet_delete(uid):
    try:return jsonify(ok=True,deleted=training_delete_full_unet(uid),unets=training_full_unets())
    except Exception as e:return jsonify(error=str(e)),409

@app.post("/api/training/jobs")
def api_training_job_create():
    active=_creator_gpu_jobs_busy()
    if active:return jsonify(error=f"Creator GPU job is active: {active.get('tool')}"),409
    ident=_identity_gpu_busy()
    if ident:return jsonify(error="Identity Studio is using the GPU. Wait for it to finish."),409
    try:
        creator_release=_release_creator_gpu()
        payload=request.get_json(force=True) or {}
        w=_dataset_workspace()
        with w.lock:
            w.preflight(str(payload.get('dataset_id') or ''))
            job=training_create_job(payload)
        return jsonify(ok=True,job=job,vram_handoff={"creator":creator_release}),202
    except Exception as e:return jsonify(error=str(e)),400

@app.get("/api/training/jobs/<jid>/log")
def api_training_job_log(jid):
    try:
        lines=max(20,min(int(request.args.get("lines",180)),1000))
        return jsonify(ok=True,log=training_read_job_log(jid,lines))
    except Exception as e:return jsonify(error=str(e)),404


@app.delete("/api/training/jobs/<jid>")
def api_training_job_delete(jid):
    from core.training_history import delete_job
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload,dict) or payload.get('confirm') is not True:
        return jsonify(error='Explicit training deletion confirmation required'),400
    if _creator_gpu_jobs_busy() or _identity_gpu_busy():
        return jsonify(error='A generation is active. Wait for it to finish before deleting training files.'),409
    try:
        result=delete_job(jid,confirm=True)
        return jsonify(ok=True,deleted=result)
    except ValueError as e:return jsonify(error=str(e)),400
    except Exception as e:return jsonify(error=str(e)),409


@app.post("/api/training/jobs/<jid>/stop")
def api_training_job_stop(jid):
    try:return jsonify(training_stop_job(jid))
    except Exception as e:return jsonify(error=str(e)),400

@app.post("/api/training/jobs/<jid>/resume")
def api_training_job_resume(jid):
    d=request.get_json(force=True) or {}
    active=_creator_gpu_jobs_busy()
    if active:return jsonify(error=f"Creator GPU job is active: {active.get('tool')}"),409
    ident=_identity_gpu_busy()
    if ident:return jsonify(error="Identity Studio is using the GPU. Wait for it to finish."),409
    try:
        creator_release=_release_creator_gpu()
        result=training_resume_job(jid,d.get("checkpoint_path",""))
        return jsonify(ok=bool(result.get("ok",True)),result=result,vram_handoff={"creator":creator_release}),202
    except Exception as e:return jsonify(error=str(e)),400

@app.post("/api/training/jobs/<jid>/continue")
def api_training_job_continue(jid):
    d=request.get_json(force=True) or {}
    active=_creator_gpu_jobs_busy()
    if active:return jsonify(error=f"Creator GPU job is active: {active.get('tool')}"),409
    ident=_identity_gpu_busy()
    if ident:return jsonify(error="Identity Studio is using the GPU. Wait for it to finish."),409
    try:
        creator_release=_release_creator_gpu()
        job=training_continue_job(jid,d.get("additional_steps",200),d.get("checkpoint_path",""))
        return jsonify(ok=True,job=job,vram_handoff={"creator":creator_release}),202
    except Exception as e:return jsonify(error=str(e)),400


if os.environ.get("SDXL_STUDIO_NO_BACKGROUND")!="1":_ensure_identity_dispatcher()


@app.get('/api/health')
def edition_health():
    return jsonify(ok=True,edition='sdxl',version=VERSION)

@app.before_request
def edition_input_guard():
    # Route IDs are identifiers, never filesystem paths.
    for k,v in (request.view_args or {}).items():
        if isinstance(v,str) and k in {'pid','jid','did','iid','aid','lid','mid','uid','key'} and not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',v):
            return jsonify(error='Invalid identifier'),400
    if request.is_json:
        try:
            data=request.get_json(silent=False)
            json.dumps(data,allow_nan=False)
        except (ValueError,TypeError):return jsonify(error='Invalid JSON or non-finite value'),400

@app.after_request
def edition_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    if request.path.startswith('/api/') or request.path=='/login':response.headers['Cache-Control']='no-store'
    return response

@app.get('/api/account')
def edition_account_get():
    cfg=_load_auth_config()
    return jsonify(ok=True,username=cfg["username"],session_hours=cfg["session_hours"],enabled=cfg["enabled"])

@app.put('/api/account')
def edition_account_put():
    cfg=_load_auth_config();d=request.get_json(force=True) or {}
    current=str(d.get('current_password') or '')
    username=str(d.get('username') or cfg['username']).strip()[:80] or cfg['username']
    new_password=str(d.get('new_password') or '')
    confirm=str(d.get('confirm_password') or '')
    if not current or not check_password_hash(cfg['password_hash'],current):return jsonify(error='Password attuale non corretta'),400
    password_hash=cfg['password_hash']
    if new_password or confirm:
        if len(new_password)<10:return jsonify(error='La nuova password deve avere almeno 10 caratteri'),400
        if new_password!=confirm:return jsonify(error='Le nuove password non coincidono'),400
        password_hash=generate_password_hash(new_password)
    new_cfg=_save_auth_config(username,password_hash,cfg['session_hours'],cfg['enabled'])
    _login_session(new_cfg)
    return jsonify(ok=True,username=new_cfg['username'],message='Account aggiornato.')

def _identity_setup_status():
    from core.identity_paths import identity_files
    status=identity_files(settings(),MODELS_ROOT,SHARED_ROOT)
    worker=identity_worker_health() or {}
    status['worker']=worker
    online=bool(worker.get('online',worker.get('ok',False)))
    status['instantid_ready']=bool(status['instantid_enabled'] and status['instantid_files_ready'] and online)
    status['face_swap_ready']=bool(status['faceswap_enabled'] and status['face_swap_files_ready'] and online)
    actual=(worker.get('models') or {}).get('path_signature')
    status['worker_path_signature']=actual
    status['worker_paths_match']=(actual==status['path_signature']) if actual else None
    return status

@app.get('/api/setup/identity-status')
def edition_identity_status():
    return jsonify(ok=True,status=_identity_setup_status())

# Restricted weight downloads are deliberately unavailable in this distribution.
# Existing local models remain configurable; acknowledgement does not grant rights.
@app.get('/api/setup/model-manager')
def edition_model_manager():
    reg=load_registry();sdxl=next((m for m in reg.get('models',[]) if m.get('provider')=='sdxl'),None)
    return jsonify(ok=True,version=VERSION,sdxl={'model':sdxl,'validation':validate_model(sdxl)},
                   identity=_identity_setup_status(),downloads={},settings=settings())

@app.get('/api/setup/model-downloads')
def edition_model_downloads():
    return jsonify(ok=True,downloads={},identity=_identity_setup_status())

@app.post('/api/setup/model-download/<component>')
def edition_model_download(component):
    from core.model_policy import catalog
    item=next((x for x in catalog() if x['id']==component),{})
    return jsonify(error='Pesi esterni con termini separati: usa la fonte ufficiale e collega i tuoi file. La conferma dei termini non abilita un download in questa build.',source=item.get('source','')),403

@app.post('/api/setup/link-face-pack/<pack>')
def edition_link_face_pack(pack):
    pack=str(pack or '').strip()
    if pack not in {'antelopev2','buffalo_l'}:return jsonify(error='Unsupported face pack'),400
    d=request.get_json(force=True) or {};src=Path(str(d.get('path') or '')).expanduser().resolve()
    if not src.is_dir() or not any(src.glob('*.onnx')):return jsonify(error='Choose the actual model pack folder containing ONNX files.'),400
    from core.identity_paths import resolve_identity_paths
    cfg=settings();root=Path(resolve_identity_paths(cfg,MODELS_ROOT,SHARED_ROOT)['insightface_root'])
    target=root/'models'/pack;target.parent.mkdir(parents=True,exist_ok=True)
    try:
        if target.resolve()==src:return jsonify(ok=True,message='This folder is already configured.',status=_identity_setup_status())
    except Exception:pass
    if target.exists() or target.is_symlink():
        if target.is_symlink():target.unlink()
        elif target.is_dir() and not any(target.iterdir()):target.rmdir()
        else:return jsonify(error=f'Target already exists and is not empty: {target}'),400
    target.symlink_to(src,target_is_directory=True)
    return jsonify(ok=True,message=f'{pack} linked without copying files.',target=str(target),status=_identity_setup_status())

from core.identity_code import CodeInstaller, settings_lock
_identity_code_installer=CodeInstaller()

@app.get('/api/setup/identity-code-status')
def edition_identity_code_status():
    return jsonify(ok=True,installation=_identity_code_installer.status(),status=_identity_setup_status())

@app.post('/api/setup/identity-prepare-code')
def edition_identity_prepare_code():
    try:
        state=_identity_code_installer.start()
        return jsonify(ok=True,installation=state),202
    except (ValueError,OSError) as e:
        return jsonify(ok=False,error=str(e)),400

@app.post('/api/setup/identity-create-layout')
def edition_identity_create_layout():
    cfg=settings();root=Path(cfg.get('identity_root') or (MODELS_ROOT/'Identity')).expanduser()
    instant=Path(cfg.get('identity_instantid_root') or root/'InstantID').expanduser()
    insight=Path(cfg.get('identity_insightface_root') or root/'insightface').expanduser()
    swapper=Path(cfg.get('identity_swapper_model') or root/'inswapper_128.onnx').expanduser()
    for d in [instant/'ControlNetModel',insight/'models'/str(cfg.get('instantid_face_pack') or 'antelopev2'),insight/'models'/str(cfg.get('swap_face_pack') or 'buffalo_l'),swapper.parent]:
        d.mkdir(parents=True,exist_ok=True)
    return jsonify(ok=True,message=f'Identity folders ready under {root}',status=_identity_setup_status())

@app.get('/api/session/tokens')
def edition_session_tokens():
    from core.csrf import token
    return jsonify(tokens={name:token(name) for name in ('model-hub','vision')})

@app.get('/api/setup')
def edition_setup_get():
    cfg=settings(); effective=os.environ.get('SDXL_STUDIO_EFFECTIVE_HOST',cfg.get('host','127.0.0.1'))
    import socket
    lan_ip=''
    try:
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.connect(('1.1.1.1',80));lan_ip=sock.getsockname()[0];sock.close()
    except OSError:
        try: lan_ip=socket.gethostbyname(socket.gethostname())
        except OSError: pass
    from core.desktop_shortcuts import desktop_shortcut_status
    from core.network_access import firewall_status
    firewall=firewall_status(int(cfg.get('port',8298)),program=sys.executable) if os.name=='nt' else {'supported':False,'needs_fix':False}
    return jsonify(ok=True,settings=cfg,effective_host=effective,lan_ip=lan_ip,platform=('windows' if os.name=='nt' else 'linux'),models=models(),models_root=str(MODELS_ROOT),data_root=str(DATA_ROOT),version=VERSION,
                   image_runtime=image_worker_health(),identity_runtime=identity_worker_health(),training_runtime=training_worker_health(),
                   desktop_shortcut=desktop_shortcut_status(DATA_ROOT),firewall=firewall)

@app.put('/api/setup')
def edition_setup_put():
    with settings_lock():
        from core.runtime_env import SETTINGS_FILE
        d=request.get_json(force=True) or {};cfg=settings()
        # Saving unrelated fields must not persist a CLI-only --lan/--local override.
        from core.runtime_env import DEFAULTS
        try: saved=json.loads(SETTINGS_FILE.read_text())
        except (OSError,ValueError): saved={}
        cfg['host']=saved.get('host',DEFAULTS['host'])
        mod=d.get('sdxl') or {}
        if mod:update_model('sdxl',{'config':mod})
        if 'identity_root' in d and str(d['identity_root']).strip():
            old_root=Path(cfg['identity_root']).expanduser();new_root=Path(str(d['identity_root'])).expanduser()
            for field,relative in [('identity_instantid_root','InstantID'),('identity_insightface_root','insightface'),('identity_swapper_model','inswapper_128.onnx')]:
                if field not in d and (not cfg.get(field) or Path(cfg[field]).expanduser()==old_root/relative):
                    cfg[field]=str(new_root/relative)
        allowed={'identity_root','identity_vendor','identity_instantid_root','identity_insightface_root','identity_swapper_model','instantid_face_pack','swap_face_pack','identity_instantid_enabled','identity_faceswap_enabled','identity_license_acknowledged','sdxl_config','inpaint_config'}
        for k in allowed:
            if k in d:cfg[k]=bool(d[k]) if k in {'identity_license_acknowledged','identity_instantid_enabled','identity_faceswap_enabled'} else str(d[k]).strip()
        if 'network_mode' in d:cfg['host']='0.0.0.0' if str(d.get('network_mode'))=='lan' else '127.0.0.1'
        atomic_json(SETTINGS_FILE,cfg)
        return jsonify(ok=True,restart_required=True,message='Salvato. Identity rilegge i percorsi al prossimo lavoro; per modifiche LAN riavvia l’app.')

@app.get('/api/desktop-shortcut')
def edition_desktop_shortcut_get():
    from core.desktop_shortcuts import desktop_shortcut_status
    return jsonify(ok=True,shortcut=desktop_shortcut_status(DATA_ROOT))

@app.post('/api/desktop-shortcut')
def edition_desktop_shortcut_set():
    from core.desktop_shortcuts import set_desktop_shortcut,desktop_shortcut_status
    d=request.get_json(silent=True) or {};enabled=bool(d.get('enabled',True))
    try:set_desktop_shortcut(DATA_ROOT,ROOT,enabled)
    except Exception as exc:return jsonify(ok=False,error=str(exc)),400
    return jsonify(ok=True,shortcut=desktop_shortcut_status(DATA_ROOT),message=('Desktop shortcut created.' if enabled else 'Desktop shortcut removed.'))

@app.get('/api/network/firewall')
def edition_network_firewall_get():
    from core.network_access import firewall_status
    cfg=settings();return jsonify(ok=True,firewall=firewall_status(int(cfg.get('port',8298)),program=sys.executable))

@app.post('/api/network/firewall/configure')
def edition_network_firewall_configure():
    if os.name!='nt':return jsonify(ok=False,error='Windows Firewall configuration is only available on Windows.'),400
    d=request.get_json(silent=True) or {};cfg=settings()
    if str(cfg.get('host'))!='0.0.0.0':return jsonify(ok=False,error='Enable LAN access first, then configure Windows Firewall.'),400
    from core.network_access import configure_firewall,firewall_status
    before=firewall_status(int(cfg.get('port',8298)),program=sys.executable)
    disable=bool(d.get('disable_conflicts',False))
    if before.get('conflicting_blocks') and not disable:
        return jsonify(ok=False,confirmation_required=True,error='Windows has inbound Block rules for the Python executable hosting Zetalvx Image Lab.',firewall=before),409
    try:result=configure_firewall(int(cfg.get('port',8298)),disable_conflicts=disable,program=sys.executable)
    except Exception as exc:return jsonify(ok=False,error=str(exc),firewall=before),400
    after=firewall_status(int(cfg.get('port',8298)),program=sys.executable)
    return jsonify(ok=True,result=result,firewall=after,message='Windows Firewall configured for the local network.')

@app.post('/api/app-control/<action>')
def edition_app_control(action):
    if action not in {'stop','restart'}:return jsonify(error='Unknown app action'),404
    from scripts.install import ensure_idle
    try:ensure_idle(DATA_ROOT)
    except (OSError,ValueError,RuntimeError) as exc:return jsonify(error=str(exc)),409
    pending=SHARED_ROOT/'run/app-control.pending'
    try:
        fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(action+'\n')
    except FileExistsError:return jsonify(error='Another app control action is already running.'),409
    try:
        cmd=[sys.executable,str(ROOT/'scripts/app_host_control.py'),'--home',str(DATA_ROOT),'--action',action]
        env={**os.environ,'SDXL_STUDIO_HOME':str(DATA_ROOT),'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
        for key in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE','SDXL_STUDIO_INSTALLER_ACTIVE'):env.pop(key,None)
        kwargs={'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'cwd':tempfile.gettempdir(),'env':env}
        if os.name=='nt':kwargs['creationflags']=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        else:kwargs['start_new_session']=True
        subprocess.Popen(cmd,**kwargs)
    except Exception:
        pending.unlink(missing_ok=True);raise
    return jsonify(ok=True,action=action,message=('Restart scheduled.' if action=='restart' else 'Shutdown scheduled.')),202

@app.post('/api/setup/identity-resolve')
def edition_identity_resolve():
    from core.identity_paths import identity_files
    d=request.get_json(silent=True) or {};cfg=settings().copy()
    if d.get('root'):
        cfg['identity_root']=str(d['root']).strip()
        if d.get('derive_children',True):
            for key in ('identity_instantid_root','identity_insightface_root','identity_swapper_model'):cfg[key]=''
    return jsonify(ok=True,status=identity_files(cfg,MODELS_ROOT,SHARED_ROOT))

@app.post('/api/setup/identity-reload')
def edition_identity_reload():
    from core.runtime_env import worker_headers
    import requests
    try:
        r=requests.post(os.environ['CREATOR_IDENTITY_WORKER_URL']+'/reload-config',headers=worker_headers(),timeout=20)
        d=r.json()
        return jsonify(d),r.status_code
    except Exception:
        return jsonify(ok=False,error='Identity worker offline. Start the app with Identity installed.'),503

@app.get('/api/setup/browse')
def edition_browse():
    path=Path(request.args.get('path') or MODELS_ROOT).expanduser().resolve()
    if path.is_relative_to((DATA_ROOT/'secrets').resolve()):return jsonify(error='Credential directory is private'),403
    if not path.is_dir():return jsonify(error='Directory not found'),404
    try:
        entries=[]
        for p in sorted(path.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower())):
            if p.name.startswith('.'):continue
            if p.is_dir() or p.suffix.lower() in {'.safetensors','.onnx','.bin','.json'}:
                entries.append({'name':p.name,'path':str(p),'directory':p.is_dir()})
            if len(entries)>=600:break
        return jsonify(path=str(path),parent=str(path.parent),entries=entries)
    except OSError as e:return jsonify(error=str(e)),400

from core.model_hub_api import register_model_hub
register_model_hub(app,{
    'models':models,'model_by_id':model_by_id,'validate_model':validate_model,'update_model':update_model,
    'settings':settings,'identity_status':_identity_setup_status,'scan_checkpoints':scan_checkpoints,'scan_loras':scan_loras,
    'local_models':local_models,
})

from core.studio_extensions import register as register_studio_extensions
register_studio_extensions(app,one,execute,decode_artifact)

from core.vision_api import register as register_vision_api

def _prepare_vision_gpu():
    from vision.registry import VisionError
    if bool(_gpu_guard_payload().get('busy')):
        raise VisionError('GPU is in use by generation, Identity or Training. Wait before local Vision captioning.')
    _release_creator_gpu()

vision_service=register_vision_api(app,_prepare_vision_gpu)
from core.download_manager_api import register as register_download_manager
register_download_manager(app)
from core.dataset_workspace_api import register as register_dataset_workspace
register_dataset_workspace(app,vision_service)

from core.app_uninstall_api import register as register_app_uninstall
app_uninstall_service=register_app_uninstall(app,DATA_ROOT,ROOT,_load_auth_config)

from core.app_update_api import register as register_app_updates
app_update_store=register_app_updates(app,DATA_ROOT,ROOT,_load_auth_config)

def main():
    cfg=settings()
    # Direct foreground `run.py web` also supports a host-issued code. The
    # supervisor passes a marker (never the code) to prevent logging a second one.
    if os.environ.get("SDXL_STUDIO_SETUP_CODE_MANAGED")!="1":
        print_setup_code(first_run_codes.issue())
    cert=SHARED_ROOT/'config/cert.pem';key=SHARED_ROOT/'config/key.pem'
    tls=(str(cert),str(key)) if cfg.get('https') else None
    os.environ['SDXL_STUDIO_EFFECTIVE_HOST']=str(cfg['host'])
    from core.web_server import serve
    serve(app, cfg['host'], int(cfg['port']), tls=tls)


if __name__ == "__main__":
    main()
