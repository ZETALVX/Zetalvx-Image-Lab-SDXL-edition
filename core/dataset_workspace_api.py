"""Host routes for the integrated Dataset Studio; parent login is mandatory."""
import io
from flask import request, jsonify
from PIL import Image, ImageOps
from .csrf import valid
from .dataset_workspace import Workspace, DatasetConflict, DatasetBusy
from .dataset_exchange import DatasetError
from .runtime_env import SHARED_ROOT


def register(app, vision):
    def caption_active(did):
        return vision.batch.busy() and any(j['dataset_id']==did and j['status'] in ('running','queued') for j in vision.batch.list())
    store=Workspace(SHARED_ROOT/'training/datasets',SHARED_ROOT/'training/jobs',
                    lock=vision.batch.lock,caption_active=caption_active)
    app.extensions['zetalvx_dataset_workspace']=store

    @app.before_request
    def dataset_edit_guard():
        if request.path.startswith('/api/training/datasets') and request.method in ('POST','PUT','PATCH','DELETE'):
            if not valid('vision',request.headers.get('X-CSRF-Token','')):
                return jsonify(error='Session token expired. Please retry.',code='csrf_failed'),403
            # Multipart image/ZIP ingestion keeps its proper Content-Type.
            if request.is_json and not isinstance(request.get_json(silent=True),dict):
                return jsonify(error='JSON object required'),400

    @app.errorhandler(DatasetConflict)
    def conflict(e):return jsonify(error=str(e),code='dataset_conflict',dataset=e.current),409
    @app.errorhandler(DatasetBusy)
    def busy(e):return jsonify(error=str(e),code='dataset_busy'),409
    @app.errorhandler(DatasetError)
    def invalid(e):return jsonify(error=str(e),code='dataset_error'),400

    @app.post('/api/training/datasets/<did>/apply-trigger')
    def dataset_apply_trigger(did):
        return jsonify(store.apply(did))

    @app.post('/api/training/datasets/<did>/use')
    def dataset_use_for_training(did):
        # No copy/export/import: the trainer uses this very dataset.json.
        return jsonify(store.preflight(did))

    @app.get('/api/training/datasets/<did>/items/<iid>/thumbnail')
    def dataset_thumbnail(did,iid):
        from flask import send_file
        p=store.image_path(did,iid)
        with Image.open(p) as im:
            if im.width*im.height>32_000_000:
                raise DatasetError('Image exceeds 32 megapixels')
            im=ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((256,256))
            buf=io.BytesIO();im.save(buf,'JPEG',quality=80);buf.seek(0)
        r=send_file(buf,mimetype='image/jpeg',max_age=0)
        r.headers['Cache-Control']='private, max-age=300'
        return r
    return store
