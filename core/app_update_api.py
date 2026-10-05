"""Authenticated GUI update API. Import is data-only; execution needs reauthentication."""
from __future__ import annotations
import threading,time,subprocess,os
from flask import jsonify,request
from werkzeug.security import check_password_hash
from core.csrf import token,valid
from core.app_updates import UpdateStore,UpdateError,MAX_ZIP
from core.platform_support import venv_python,detached_kwargs
from core.install_layout import VERSION,pointers,release_path,runtime_dirs

def register(app,home,source,auth_config):
    store=UpdateStore(home,source,VERSION)
    failures={};mutex=threading.Lock()
    def reply_error(exc):
        return jsonify(error=str(exc)),getattr(exc,'status',409)
    def rollback_info():
        try:
            state=pointers(home);previous=state.get('previous') or ''
            if not previous:return {'available':False,'current':state.get('current') or VERSION,'previous':'','reason':'No previous version is available for rollback.'}
            target=release_path(home,previous)
            roots=runtime_dirs(home,target);app_runtime=roots.get('app')
            if not target.is_dir() or not app_runtime or not venv_python(app_runtime).is_file():
                return {'available':False,'current':state.get('current') or VERSION,'previous':previous,'reason':'Previous version runtime is not available.'}
            return {'available':True,'current':state.get('current') or VERSION,'previous':previous,'reason':''}
        except (OSError,ValueError,RuntimeError) as exc:
            return {'available':False,'current':VERSION,'previous':'','reason':str(exc)}
    def require_access(write=False):
        # General app login gate runs first, including Origin checking.
        cfg=auth_config()
        if not cfg.get('enabled') or not cfg.get('password_hash'):
            raise UpdateError('Set an enabled app account and password before using GUI updates',403)
        if request.remote_addr not in ('127.0.0.1','::1') and not request.is_secure:
            raise UpdateError('Remote updates require HTTPS',403)
        supplied=request.headers.get('X-CSRF-Token','')
        if write and (not supplied.isascii() or not valid('app-updates',supplied)):
            raise UpdateError('Update session expired. Refresh the page.',403)
        return cfg
    @app.before_request
    def _update_maintenance():
        if request.method not in {'POST','PUT','PATCH','DELETE'} or request.path.startswith('/api/app-updates') or request.path in {'/login','/logout'}:
            return None
        try:
            if store.maintenance():
                return jsonify(error='An app update is in progress. Wait before modifying data or queuing jobs.',maintenance=True),503
        except (ValueError,OSError):
            return jsonify(error='Update state needs inspection on the host; writes temporarily blocked.'),503
    @app.get('/api/app-updates')
    def _app_updates_state():
        try:
            require_access();available=True;reason=''
            try:store.check_installed()
            except UpdateError as exc:available=False;reason=str(exc)
            response=jsonify(ok=True,version=VERSION,available=available,reason=reason,csrf=token('app-updates'),update=store.public_state(),rollback=rollback_info())
            response.headers['Cache-Control']='no-store';return response
        except (ValueError,OSError) as exc:return reply_error(exc)
    @app.post('/api/app-updates/import')
    def _app_updates_import():
        try:
            require_access(True)
            if request.content_length and request.content_length>MAX_ZIP+1024**2:raise UpdateError('Update ZIP exceeds 128 MiB',413)
            f=request.files.get('file')
            if not f or not f.filename:raise UpdateError('Select an update ZIP')
            store.import_zip(f.stream,f.filename,request.form.get('sha256',''))
            return jsonify(ok=True,update=store.public_state())
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:return reply_error(exc)
    @app.post('/api/app-updates/<id>/start')
    def _app_updates_start(id):
        try:
            cfg=require_access(True);data=request.get_json(silent=True) or {}
            if not isinstance(data,dict):raise UpdateError('Invalid update confirmation object')
            if data.get('trust_source') is not True:raise UpdateError('Confirm that you trust the source of this ZIP')
            password=data.get('password')
            if not isinstance(password,str) or not 1<=len(password)<=1024:raise UpdateError('Enter the current app password',403)
            key=request.remote_addr or 'local';now=time.monotonic()
            with mutex:
                if len(failures)>128:failures.clear()
                failures[key]=[x for x in failures.get(key,[]) if now-x<60]
                if len(failures[key])>=5:raise UpdateError('Too many password attempts. Wait one minute.',429)
                if not check_password_hash(cfg['password_hash'],password):
                    failures[key].append(now);raise UpdateError('Incorrect app password',403)
                failures.pop(key,None)
            if not isinstance(data.get('allow_new_runtime',False),bool):raise UpdateError('Invalid runtime policy')
            store.start(id,data.get('allow_new_runtime',False))
            return jsonify(ok=True,update=store.public_state()),202
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:return reply_error(exc)
    @app.delete('/api/app-updates/<id>')
    def _app_updates_discard(id):
        try:
            require_access(True);store.discard(id);return jsonify(ok=True,update=store.public_state())
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:return reply_error(exc)
    @app.post('/api/app-updates/rollback')
    def _app_updates_rollback():
        try:
            cfg=require_access(True);data=request.get_json(silent=True) or {}
            if not isinstance(data,dict):raise UpdateError('Invalid rollback confirmation object')
            password=data.get('password')
            if not isinstance(password,str) or not 1<=len(password)<=1024:raise UpdateError('Enter the current app password',403)
            key=request.remote_addr or 'local';now=time.monotonic()
            with mutex:
                if len(failures)>128:failures.clear()
                failures[key]=[x for x in failures.get(key,[]) if now-x<60]
                if len(failures[key])>=5:raise UpdateError('Too many password attempts. Wait one minute.',429)
                if not check_password_hash(cfg['password_hash'],password):
                    failures[key].append(now);raise UpdateError('Incorrect app password',403)
                failures.pop(key,None)
            current_update=store.public_state()
            if current_update and current_update.get('status') in {'ready','starting','running'}:
                raise UpdateError('Discard or finish the pending update before rollback.',409)
            info=rollback_info()
            if not info.get('available'):raise UpdateError(info.get('reason') or 'Rollback is not available.',409)
            from scripts.install import ensure_idle
            ensure_idle(home)
            pending=home/'shared/run/app-control.pending';pending.parent.mkdir(parents=True,exist_ok=True)
            try:
                fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'w',encoding='utf-8') as f:f.write('rollback\n')
            except FileExistsError:raise UpdateError('Another app control action is already running.',409)
            try:
                env={**os.environ,'SDXL_STUDIO_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
                for name in ('PYTHONPATH','PYTHONHOME','SDXL_STUDIO_HOST_OVERRIDE','SDXL_STUDIO_INSTALLER_ACTIVE'):env.pop(name,None)
                cmd=[os.fspath(venv_python(runtime_dirs(home,release_path(home,info['current']))['app'])),os.fspath(source/'scripts/app_host_control.py'),'--home',os.fspath(home),'--action','rollback']
                subprocess.Popen(cmd,cwd=os.fspath(home),env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True,**detached_kwargs())
            except BaseException:
                try:pending.unlink()
                except FileNotFoundError:pass
                raise
            return jsonify(ok=True,rollback=info,message='Rollback scheduled. The app will restart.'),202
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:return reply_error(exc)
    return store
