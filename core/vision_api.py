# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.19; Vision browser upload + chooser polish.
"""Authenticated model registry and serial dataset captioning in SDXL Training."""
import contextlib,hmac,secrets,threading
from flask import request,jsonify,session,g
from vision.service import Service
from vision.batch import Batch
from vision.registry import VisionError
from .runtime_env import DATA_ROOT,SHARED_ROOT
from .gpu_session import gpu_session
from .csrf import token, valid
from vision.uploads import BrowserVisionUploads
from vision.link_imports import VisionLinkImports

def register(app,prepare_gpu):
    v=Service(DATA_ROOT)
    uploads=BrowserVisionUploads(DATA_ROOT)
    link_imports=VisionLinkImports(DATA_ROOT, start_worker=True)
    def before(m):
        if m['backend']!='api':prepare_gpu()
    v.batch=Batch(SHARED_ROOT/'vision/jobs',SHARED_ROOT/'training/datasets',v.registry,v.engine,before=before,scope=lambda:gpu_session('vision'))
    v.actions.before=before
    v.actions.scope=lambda m:gpu_session('vision') if m['backend']!='api' else contextlib.nullcontext()
    app.extensions['zetalvx_vision']=v
    app.extensions['zetalvx_vision_link_imports']=link_imports
    @app.get('/api/vision/session')
    def vision_session():
        return jsonify(csrf=token('vision'))
    @app.before_request
    def guard_vision():
        path=request.path
        protected=path.startswith('/api/vision/') or path.startswith('/api/training/vision/') or path.endswith('/vision-caption') or (path=='/api/setup' or path.startswith('/api/setup/identity-') or path.startswith('/api/setup/link-face-pack/'))
        if protected and request.method in ('POST','PUT','DELETE','PATCH'):
            if not valid('vision',request.headers.get('X-CSRF-Token','')):return jsonify(error='Session token expired. Please retry.',code='csrf_failed'),403
            chunk_upload = path.startswith('/api/vision/uploads/') and path.endswith('/chunk')
            if not chunk_upload:
                if not request.is_json or not isinstance(request.get_json(silent=True),dict):return jsonify(error='JSON object required'),400
        native_post=(path in ('/api/tools/run','/api/image/auto-test','/api/identity/jobs','/api/identity/auto-test','/api/training/jobs') or (path.startswith('/api/training/') and path.endswith(('/resume','/continue'))))
        if request.method=='POST' and native_post:
            if path.startswith('/api/training/') and v.batch.busy():
                return jsonify(error='Wait or stop captioning before starting or resuming training.'),409
            tests=any(x['status'] in ('running','cancelling') and x.get('kind')=='test' for x in v.actions.list())
            if (v.batch.busy() and v.batch.active_local) or tests:return jsonify(error='Vision is working. Wait or cancel captioning before using the GPU.'),409
            if not v.batch.busy() and v.engine.status().get('backend_process_running'):
                try:v.engine.unload()
                except VisionError as e:return jsonify(error=str(e)),409
        # Prevent losing concurrent manually saved captions during the file merge.
        if path.startswith('/api/training/datasets/') and request.method in ('PUT','DELETE','PATCH'):
            v.batch.lock.acquire();g.vision_dataset_locked=True
    @app.teardown_request
    def release_lock(exc):
        if getattr(g,'vision_dataset_locked',False):v.batch.lock.release();g.vision_dataset_locked=False
    @app.route('/api/vision/<path:subpath>',methods=['GET','POST','PUT','DELETE'])
    def vision(subpath):
        try:return jsonify(v.handle('/api/vision/'+subpath,request.method,request.get_json(silent=True) or {},request.args.to_dict()))
        except ValueError as e:return jsonify(error=str(e)),400

    @app.post('/api/vision/uploads')
    def vision_upload_create():
        try:
            d=request.get_json() or {}
            upload=uploads.create(d.get('filename'),d.get('size'),d.get('role'))
            return jsonify(ok=True,upload=upload,chunk_size=8*1024**2)
        except VisionError as e:return jsonify(error=str(e)),400

    @app.post('/api/vision/uploads/<uid>/chunk')
    def vision_upload_chunk(uid):
        try:
            state=uploads.append(uid,request.form.get('offset'),request.files.get('chunk'))
            return jsonify(ok=True,upload=state)
        except VisionError as e:return jsonify(error=str(e)),400

    @app.post('/api/vision/uploads/<uid>/finalize')
    def vision_upload_finalize(uid):
        try:return jsonify(ok=True,**uploads.finalize(uid))
        except VisionError as e:return jsonify(error=str(e)),400

    @app.delete('/api/vision/uploads/<uid>')
    def vision_upload_cancel(uid):
        try:return jsonify(ok=True,**uploads.cancel(uid))
        except VisionError as e:return jsonify(error=str(e)),400

    @app.get('/api/vision/link-imports')
    def vision_link_import_list():
        return jsonify(ok=True,jobs=link_imports.list())

    @app.post('/api/vision/link-imports')
    def vision_link_import_start():
        try:
            d=request.get_json() or {}
            job=link_imports.start(str(d.get('kind') or ''),str(d.get('url') or ''),str(d.get('role') or ''),d.get('confirm_terms') is True)
            return jsonify(ok=True,job=job),202
        except (VisionError,ValueError) as e:return jsonify(error=str(e)),400

    @app.get('/api/vision/link-imports/<jid>')
    def vision_link_import_status(jid):
        try:return jsonify(ok=True,job=link_imports.get(jid))
        except VisionError as e:return jsonify(error=str(e)),404

    @app.post('/api/vision/link-imports/<jid>/cancel')
    def vision_link_import_cancel(jid):
        try:return jsonify(ok=True,job=link_imports.cancel(jid))
        except VisionError as e:return jsonify(error=str(e)),400

    @app.get('/api/training/vision/jobs')
    def caption_jobs():return jsonify(jobs=v.batch.list())
    @app.post('/api/training/vision/cancel')
    def cancel():v.batch.cancel();return jsonify(ok=True)
    @app.post('/api/training/datasets/<did>/vision-caption')
    def caption(did):
        try:
            d=request.get_json() or {}
            if not d.get('confirm'):raise VisionError('Confirm sending dataset images to the selected model')
            if any(x['status'] in ('running','cancelling') for x in v.actions.list()):raise VisionError('Wait for the Vision test or installation to finish')
            w=app.extensions.get('zetalvx_dataset_workspace')
            if w:w.editable(did,structural=True)
            return jsonify(job=v.batch.start(did,d.get('model_id',''))),202
        except ValueError as e:return jsonify(error=str(e)),400
    import atexit
    atexit.register(v.engine.close)
    return v
