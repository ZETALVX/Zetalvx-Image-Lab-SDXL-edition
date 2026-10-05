"""Authenticated two-password + one-time-word uninstall boundary."""
import hashlib, json, subprocess
from flask import jsonify, request, session
from werkzeug.security import check_password_hash
from core.csrf import token, valid
from core.app_uninstall import Challenges, UninstallService, UninstallError
from core.http_security import same_origin

def register(app,home,source,auth_config):
    service=UninstallService(home,source);challenges=Challenges()
    def access(write=False):
        cfg=auth_config()
        if not cfg.get('enabled') or not cfg.get('password_hash') or not session.get('creator_authenticated'):
            raise UninstallError('An authenticated app account is required.',403)
        if session.get('creator_username')!=cfg.get('username') or session.get('auth_stamp')!=cfg['password_hash'][-20:]:
            raise UninstallError('Sign in again before uninstalling.',403)
        if request.remote_addr not in ('127.0.0.1','::1') and not request.is_secure:
            raise UninstallError('Remote uninstall requires HTTPS.',403)
        if write:
            supplied=request.headers.get('X-CSRF-Token','')
            if not same_origin(request.headers.get('Origin'),request.host_url) or not supplied.isascii() or not valid('app-uninstall',supplied):
                raise UninstallError('Invalid uninstall session. Reload the app.',403)
        return cfg
    def owner(cfg):
        return hashlib.sha256(json.dumps([cfg['username'],cfg['password_hash'],session.get('creator_csrf_nonce','legacy')]).encode()).hexdigest()
    def data_object():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise UninstallError('Invalid confirmation',400)
        return d
    def error(e):return jsonify(error=str(e)),getattr(e,'status',409)
    @app.after_request
    def uninstall_no_cache(response):
        if request.path.startswith('/api/app-uninstall'):response.headers['Cache-Control']='no-store'
        return response
    @app.before_request
    def uninstall_maintenance():
        if request.method in ('POST','PUT','PATCH','DELETE') and not request.path.startswith('/api/app-uninstall') and request.path not in ('/login','/logout'):
            if (service.home/'uninstall-pending.json').exists():
                return jsonify(error='Uninstall in progress. New work and data changes are blocked.',maintenance=True),503
    @app.get('/api/app-uninstall')
    def uninstall_state():
        try:
            access();plan=service.plan();return jsonify(ok=True,csrf=token('app-uninstall'),plan=plan)
        except (ValueError,OSError,RuntimeError) as e:return error(e)
    @app.post('/api/app-uninstall/challenge')
    def uninstall_challenge():
        try:
            cfg=access(True);d=data_object();plan=service.plan(d.get('purge_data',False))
            return jsonify(ok=True,challenge=challenges.issue(owner(cfg),plan['purge_data']),plan=plan)
        except (ValueError,OSError,RuntimeError) as e:return error(e)
    @app.post('/api/app-uninstall/cancel')
    def uninstall_cancel():
        try:
            cfg=access(True);d=data_object();challenges.cancel(owner(cfg),d.get('challenge_id'))
            return jsonify(ok=True)
        except (ValueError,OSError,RuntimeError) as e:return error(e)
    @app.post('/api/app-uninstall/start')
    def uninstall_start():
        try:
            cfg=access(True);d=data_object()
            result=challenges.authorise(owner(cfg),cfg['username'],d,lambda p:check_password_hash(cfg['password_hash'],p),service.start)
            return jsonify(ok=True,uninstall=result),202
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as e:return error(e)
    return service
