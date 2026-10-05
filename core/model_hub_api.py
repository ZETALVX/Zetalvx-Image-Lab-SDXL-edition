# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.18; model upload + strict local discovery polish.
"""Authenticated Models hub HTTP API. Injects existing app callbacks, no GPU work."""
from __future__ import annotations
import hmac, os, re, secrets, shutil
from pathlib import Path
from flask import request, jsonify, session
from core.model_policy import catalog, SDXL_REPO, SDXL_FILE, POLICY_VERSION
from core.model_downloads import ModelDownloads
from core.download_security import PublicHTTPS, TokenStore, DownloadError
from core.runtime_env import DATA_ROOT, MODELS_ROOT, SHARED_ROOT
from core.csrf import token, valid
from core.task_adapters import support_matrix
from core.local_models import LocalModelError
from core.model_uploads import BrowserModelUploads
from core.sdxl_assets import SDXLBaseInstaller, asset_status


def register_model_hub(app, cb):
    tokens=TokenStore(DATA_ROOT/'secrets')
    transport=PublicHTTPS(tokens)
    def installed(kind,path):
        if kind=='checkpoint':
            model=cb['model_by_id']('sdxl') or {};cfg=model.get('config') or {}
            if not Path(str(cfg.get('checkpoint') or '/nonexistent')).expanduser().exists():
                cb['update_model']('sdxl',{'config':{'checkpoint':str(path)}})
    dl=ModelDownloads(MODELS_ROOT,SHARED_ROOT/'downloads/model-hub',transport,installed,
                      start_worker=os.environ.get('SDXL_STUDIO_NO_BACKGROUND')!='1')
    uploads=BrowserModelUploads(MODELS_ROOT,cb['local_models'])
    base_installer=SDXLBaseInstaller(SHARED_ROOT, MODELS_ROOT)
    app.extensions['model_hub']={'downloads':dl,'tokens':tokens,'transport':transport,'uploads':uploads,'base_installer':base_installer}

    @app.before_request
    def _model_hub_guard():
        if not request.path.startswith('/api/model-hub/'):return
        if request.method in ('POST','PUT','DELETE','PATCH'):
            if not valid('model-hub',request.headers.get('X-CSRF-Token','')):
                return jsonify(error='Session token expired. Please retry.',code='csrf_failed'),403
            chunk_upload = request.path.startswith('/api/model-hub/uploads/') and request.path.endswith('/chunk')
            if chunk_upload:
                return
            if not request.is_json:return jsonify(error='È richiesto un corpo JSON.'),415
            if not isinstance(request.get_json(silent=True),dict):return jsonify(error='È richiesto un oggetto JSON.'),400

    @app.errorhandler(LocalModelError)
    def _local_model_error(exc):return jsonify(error=str(exc)),400

    @app.errorhandler(DownloadError)
    def _download_error(exc):return jsonify(error=str(exc)),400

    @app.get('/api/model-hub/status')
    def hub_status():
        models=[{**m,'validation':cb['validate_model'](m),'task_support':support_matrix(m)} for m in cb['models']()];model=next((m for m in models if m.get('id')=='sdxl'),{})
        cfg=model.get('config') or {}
        vaes=[]
        root=MODELS_ROOT/'VAE';root.mkdir(parents=True,exist_ok=True)
        for p in sorted(root.glob('*.safetensors'))[:200]:vaes.append({'name':p.name,'path':str(p)})
        return jsonify(ok=True,csrf=token('model-hub'),policy_version=POLICY_VERSION,
            catalog=catalog(),accounts=tokens.public(),jobs=dl.list(),models=models,
            settings=cb['settings'](),sdxl=cb['validate_model'](model),sdxl_assets=asset_status(cfg),base_installation=base_installer.status(cfg),identity=cb['identity_status'](),
            checkpoints=cb['scan_checkpoints'](),loras=cb['scan_loras'](),vaes=vaes,
            paths={'checkpoint':str(MODELS_ROOT/'SDXL'),'lora':str(MODELS_ROOT/'loras/SDXL'),'vae':str(root)},
            local_catalog=local_inventory(),
            disk_free=shutil.disk_usage(MODELS_ROOT).free)

    def local_inventory():
        cfg=(cb['model_by_id']('sdxl') or {}).get('config') or {}
        return cb['local_models'].inventory(cfg, [x for x in os.getenv('CREATOR_LORA_ROOTS','').split(os.pathsep) if x])

    @app.get('/api/model-hub/local')
    def hub_local_list():
        return jsonify(ok=True, csrf=token('model-hub'), catalog=local_inventory())

    @app.put('/api/model-hub/local/loras/<lid>/availability')
    def hub_lora_availability(lid):
        cfg=(cb['model_by_id']('sdxl') or {}).get('config') or {}
        roots=[x for x in os.getenv('CREATOR_LORA_ROOTS','').split(os.pathsep) if x]
        result=cb['local_models'].set_lora_availability(lid, request.get_json().get('enabled'), cfg, roots)
        return jsonify(ok=True,**result,catalog=local_inventory(),loras=cb['scan_loras']())

    @app.put('/api/model-hub/local/checkpoints/<cid>/availability')
    def hub_checkpoint_availability(cid):
        cfg=(cb['model_by_id']('sdxl') or {}).get('config') or {}
        result=cb['local_models'].set_checkpoint_availability(cid, request.get_json().get('enabled'), cfg)
        return jsonify(ok=True,**result,catalog=local_inventory(),checkpoints=cb['scan_checkpoints']())

    @app.delete('/api/model-hub/local/checkpoints/<cid>/file')
    def hub_checkpoint_delete_file(cid):
        cfg=(cb['model_by_id']('sdxl') or {}).get('config') or {}
        result=cb['local_models'].delete_managed_checkpoint(cid, cfg)
        return jsonify(ok=True,**result,catalog=local_inventory(),checkpoints=cb['scan_checkpoints']())

    @app.post('/api/model-hub/local')
    def hub_local_add():
        d=request.get_json()
        result=cb['local_models'].add(d.get('path'),d.get('kind'),d.get('entry_type','file'),d.get('accept_unknown') is True)
        return jsonify(ok=True,**result,catalog=local_inventory())

    @app.delete('/api/model-hub/local/<rid>')
    def hub_local_remove(rid):
        result=cb['local_models'].remove(rid)
        inv=local_inventory()
        result['still_visible']=any(x['path']==result['path'] for k in ('checkpoint','lora') for x in inv[k])
        return jsonify(ok=True,**result,catalog=inv)


    @app.post('/api/model-hub/uploads')
    def hub_upload_create():
        d=request.get_json() or {}
        upload=uploads.create(d.get('filename'),d.get('size'),d.get('kind'))
        return jsonify(ok=True,upload=upload,chunk_size=8*1024**2)

    @app.post('/api/model-hub/uploads/<uid>/chunk')
    def hub_upload_chunk(uid):
        chunk=request.files.get('chunk')
        state=uploads.append(uid,request.form.get('offset'),chunk)
        return jsonify(ok=True,upload=state)

    @app.post('/api/model-hub/uploads/<uid>/finalize')
    def hub_upload_finalize(uid):
        d=request.get_json() or {}
        result=uploads.finalize(uid,d.get('accept_unknown') is True)
        result['catalog']=local_inventory()
        return jsonify(ok=True,**result)

    @app.delete('/api/model-hub/uploads/<uid>')
    def hub_upload_cancel(uid):
        return jsonify(ok=True,**uploads.cancel(uid))

    @app.get('/api/model-hub/downloads')
    def hub_downloads():return jsonify(ok=True,jobs=dl.list())

    @app.post('/api/model-hub/inspect')
    def hub_inspect():
        d=request.get_json() or {}
        if d.get('package')=='sdxl_base':
            preview=dl.inspect(f'https://huggingface.co/{SDXL_REPO}/blob/main/{SDXL_FILE}',kind='checkpoint',builtin=True)
        else:preview=dl.inspect(str(d.get('url') or ''),str(d.get('kind') or 'auto'),str(d.get('filename') or ''))
        return jsonify(ok=True,preview=preview)

    @app.post('/api/model-hub/downloads')
    def hub_start():
        d=request.get_json() or {}
        return jsonify(ok=True,job=dl.start(d.get('preview_id'),d.get('accept_terms') is True)),202

    @app.post('/api/model-hub/downloads/<jid>/cancel')
    def hub_cancel(jid):return jsonify(ok=True,job=dl.cancel(jid))

    @app.post('/api/model-hub/downloads/<jid>/install')
    def hub_install(jid):
        d=request.get_json() or {}
        return jsonify(ok=True,job=dl.finalize(jid,d.get('kind'),d.get('accept_unknown') is True))

    @app.put('/api/model-hub/accounts/<provider>')
    def hub_account_save(provider):
        if provider not in tokens.PROVIDERS:raise DownloadError('Piattaforma non supportata.')
        d=request.get_json() or {};token=d.get('token')
        if not isinstance(token,str) or not 8<=len(token.strip())<=2048 or any(not 33<=ord(c)<=126 for c in token.strip()):
            raise DownloadError('Incolla un token valido, senza spazi.')
        token=token.strip()
        if provider=='huggingface' and not token.startswith('hf_'):raise DownloadError('Inserisci un token personale Hugging Face (hf_...).')
        if d.get('store_without_test') is True:
            account='Token salvato · non verificato'
        else:
            url='https://huggingface.co/api/whoami-v2' if provider=='huggingface' else 'https://civitai.com/api/v1/me'
            data=transport.json(url,token_override=token)
            if not isinstance(data,dict):raise DownloadError('Risposta account non valida.')
            account=str(data.get('name') or data.get('username') or 'Accesso verificato')[:120]
        tokens.put(provider,token,account)
        return jsonify(ok=True,accounts=tokens.public())

    @app.delete('/api/model-hub/accounts/<provider>')
    def hub_account_delete(provider):
        tokens.delete(provider)
        return jsonify(ok=True,accounts=tokens.public())


    @app.post('/api/model-hub/sdxl-base-check')
    def hub_sdxl_base_check():
        model=(cb['model_by_id']('sdxl') or {})
        return jsonify(ok=True,installation=base_installer.check(model.get('config') or {}))

    @app.post('/api/model-hub/sdxl-base-install')
    def hub_sdxl_base_install():
        model=(cb['model_by_id']('sdxl') or {})
        state=base_installer.start(model_cfg=model.get('config') or {})
        return jsonify(ok=True,installation=state),202 if state.get('status') in ('queued','running') else 200

    @app.post('/api/model-hub/select')
    def hub_select():
        d=request.get_json() or {};kind=d.get('kind');path=str(d.get('path') or '')
        inventory={'checkpoint':cb['scan_checkpoints'](),'lora':cb['scan_loras'](),
                   'vae':[{'path':str(p)} for p in (MODELS_ROOT/'VAE').glob('*.safetensors')]}
        if kind not in ('checkpoint','vae') or path not in {v['path'] for v in inventory[kind]}:
            raise DownloadError('Seleziona un file presente nell’elenco. Per altri percorsi usa Configura.')
        cb['update_model']('sdxl',{'config':{'checkpoint' if kind=='checkpoint' else 'vae':path}})
        return jsonify(ok=True)
