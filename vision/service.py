# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
"""Framework-neutral authenticated API handler. Parent app must authenticate every call."""
import base64, json
from pathlib import Path
from core.platform_support import venv_python
from .registry import Registry,VisionError
from .runtime import Engine
from .llama_runtime import LlamaRuntimeManager
from .jobs import Actions

class Service:
    def __init__(self,home):
        self.registry=Registry(home);self.engine=Engine(self.registry);self.actions=Actions(self.registry,self.engine);self.batch=None
    def busy(self):return bool(self.batch and self.batch.busy())
    def action_busy(self):return any(x['status'] in ('running','cancelling','queued') for x in self.actions.list())
    def handle(self,path,method,d=None,query=None):
        d=d or {};query=query or {};seg=path.strip('/').split('/')
        if not path.startswith('/api/vision/'):return None
        if path=='/api/vision/models':
            if method=='GET':return {'models':self.registry.list(),'runtime':self.engine.status(),'default_python':'','migration_warning':getattr(self,'migration_warning','')}
            if method=='POST':return {'model':self.registry.save(d)}
        if path=='/api/vision/browse' and method=='GET':return self.registry.browse(query.get('path',''))
        if path=='/api/vision/actions' and method=='GET':return {'actions':self.actions.list(),'runtime':self.engine.status()}
        if path=='/api/vision/llama-runtime' and method=='GET':return {'runtime':LlamaRuntimeManager(self.registry.home).status()}
        if path=='/api/vision/llama-runtime-install' and method=='POST':
            if not d.get('confirm'):raise VisionError('Confirm preparation of the managed llama.cpp runtime')
            if self.busy() or self.action_busy():raise VisionError('Wait for the active Vision job to finish')
            self.engine.unload();return {'action':self.actions.start('llama_runtime',options={'preference':d.get('preference','auto')})}
        if len(seg)==5 and seg[:3]==['api','vision','actions'] and seg[4]=='cancel' and method=='POST':return {'action':self.actions.cancel(seg[3])}
        if path=='/api/vision/unload' and method=='POST':
            if self.busy() or any(x['status'] in ('running','cancelling') for x in self.actions.list()):raise VisionError('Wait for the active job before unloading')
            self.engine.unload();return {'ok':True}
        if path=='/api/vision/runtime-install' and method=='POST':
            return {'available':False,'status':'paused','message':'Automatic Transformers Vision runtime preparation is currently paused. Existing explicit local runtimes remain selectable.'}
        if path=='/api/vision/caption' and method=='POST':
            if not d.get('confirm'):raise VisionError('Confirm sending this image to the selected model')
            if self.busy():raise VisionError('Captioning is busy')
            image=d.get('image') or ''
            if len(image)>24*1024**2:raise VisionError('Test image too large')
            prompt=d.get('prompt') or ''
            if not isinstance(prompt,str) or len(prompt)>4096:raise VisionError('Invalid caption prompt')
            return {'action':self.actions.start('test',d.get('model_id'),image,prompt)}
        if len(seg)>=4 and seg[:3]==['api','vision','models']:
            mid=seg[3];m=self.registry.get(mid)
            if len(seg)==4:
                if method=='GET':return {'model':self.registry.public(m)}
                if method=='PUT':return {'model':self.registry.save(d,mid)}
                if method=='DELETE':
                    if self.busy() or self.action_busy():raise VisionError('Stop captioning or the active test before removing a model configuration')
                    if self.engine.mid==mid:self.engine.unload()
                    self.registry.delete(mid);return {'ok':True}
            if len(seg)==5 and seg[4]=='inspect' and method=='POST':return {'inspection':self.registry.inspect(m)}
            if len(seg)==5 and seg[4]=='export' and method=='GET':
                return {'schema':'zetalvx.vision.profile','model':{k:v for k,v in m.items() if k not in ('id','created_at','updated_at')}}
        if path=='/api/vision/import' and method=='POST':
            if d.get('schema')!='zetalvx.vision.profile':raise VisionError('Not a Zetalvx Vision profile')
            return {'model':self.registry.save({**d['model'],'terms_reviewed':False})}
        raise VisionError('Unknown Vision operation')
    def migrate_legacy(self,config,token=''):
        if self.registry.list() or not config.get('endpoint') or not config.get('model'):return
        try:self.registry.save({'name':'Previous API connection','backend':'api','endpoint':config['endpoint'],'api_model':config['model'],
            'instructions':config.get('instructions',''),'token':token,'terms_reviewed':False})
        except VisionError:self.migration_warning='Previous API connection could not be migrated. Its original file is preserved; add a corrected model profile.'
