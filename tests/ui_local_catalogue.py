"""Actual Chromium UI + actual LocalModels filesystem. Host HTTP/GPU services simulated.
No weight or model execution. Run from the source folder with playwright+bs4 installed.
"""
import argparse,base64,copy,io,json,os,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from PIL import Image
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();OUT=Path(args.output);OUT.mkdir(parents=True,exist_ok=True)
from core.local_models import LocalModels,LocalModelError
from tests.test_model_hub import sample
from core.task_adapters import support_matrix
from core.model_policy import catalog as policy_catalog
checks=[];errors=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)});print(name, bool(ok),flush=True)
    if not ok:raise AssertionError(name)
with tempfile.TemporaryDirectory() as t:
 root=Path(t);models=root/'models';(models/'SDXL').mkdir(parents=True);(models/'loras/SDXL').mkdir(parents=True)
 ext=root/'External weights';ext.mkdir()
 def weight(p,k='checkpoint',f='sdxl'):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sample(k,f));return str(p)
 initial=weight(models/'SDXL/base.safetensors');cp=weight(ext/'newCheckpoint.safetensors');lora=weight(ext/'Portrait LoRA.safetensors','lora');unknown=weight(ext/'unknown.safetensors','unknown','')
 many=ext/'Gallery';many.mkdir()
 for i in range(9):weight(many/f'model{i}.safetensors')
 registry=LocalModels(models,root/'config/local_models.json')
 cfgmodel=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
 cfgmodel['config'].update(checkpoint=initial,checkpoint_roots=str(models/'SDXL'),lora_root=str(models/'loras/SDXL'))
 cfgmodel.update(validation={'ready':True,'fields':[],'missing':[]},status='Ready');cfgmodel['task_support']=support_matrix(cfgmodel)
 settings={'host':'127.0.0.1','identity_root':str(models/'Identity')}
 project={'id':'a'*32,'name':'Test project','description':'','state':{},'artifacts':[],'jobs':[],'messages':[]}
 im=io.BytesIO();Image.new('RGB',(960,480),'#345a56').save(im,'PNG')
 asset={'id':'f'*32,'type':'image','url':'data:image/png;base64,'+base64.b64encode(im.getvalue()).decode(),'metadata':{'model_name':'SDXL','model_id':'sdxl','params':{'width':960,'height':480,'loras':[]}},'created_at':'2026-09-21'};project['artifacts']=[asset]
 def inventory():return registry.inventory(cfgmodel['config'])
 def boot():return {'models':[cfgmodel],'projects':[project],'recipes':[],'loras':registry.scan('lora',cfgmodel['config']),'checkpoints':registry.scan('checkpoint',cfgmodel['config']),'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
 def hub():return {'ok':True,'models':[cfgmodel],'sdxl':{'ready':True},'checkpoints':registry.scan('checkpoint',cfgmodel['config']),'loras':registry.scan('lora',cfgmodel['config']),'settings':settings,'identity':{},'paths':{'checkpoint':str(models/'SDXL'),'lora':str(models/'loras/SDXL')},'local_catalog':inventory(),'catalog':policy_catalog(),'accounts':{},'jobs':[],'vaes':[]}
 requests=[]
 def api_mock(url,method='GET',body=None):
  p=urlsplit(url);path=p.path;q=parse_qs(p.query);d=json.loads(body) if isinstance(body,str) and body.startswith('{') else {}
  requests.append([path,method])
  try:
   if path=='/api/session/tokens':return {'tokens':{'vision':'v','model-hub':'m'}}
   if path=='/api/bootstrap':return boot()
   if path.startswith('/api/projects/'):return {'project':project}
   if path=='/api/model-hub/status':return hub()
   if path=='/api/model-hub/local':
    if method=='POST':return {'ok':True,**registry.add(d.get('path'),d.get('kind'),d.get('entry_type','file'),d.get('accept_unknown') is True),'catalog':inventory()}
    return {'ok':True,'catalog':inventory()}
   if path=='/api/checkpoints':return {'ok':True,'checkpoints':registry.scan('checkpoint',cfgmodel['config']),'default_checkpoint':cfgmodel['config']['checkpoint']}
   if path.startswith('/api/model-hub/local/checkpoints/') and path.endswith('/availability') and method=='PUT':
    cid=path.split('/')[-2];result=registry.set_checkpoint_availability(cid,d.get('enabled'),cfgmodel['config']);return {'ok':True,**result,'catalog':inventory(),'checkpoints':registry.scan('checkpoint',cfgmodel['config'])}
   if path.startswith('/api/model-hub/local/checkpoints/') and path.endswith('/file') and method=='DELETE':
    cid=path.split('/')[-2];result=registry.delete_managed_checkpoint(cid,cfgmodel['config']);return {'ok':True,**result,'catalog':inventory(),'checkpoints':registry.scan('checkpoint',cfgmodel['config'])}
   if path.startswith('/api/model-hub/local/') and method=='DELETE':
    result=registry.remove(path.rsplit('/',1)[1]);inv=inventory();return {'ok':True,**result,'catalog':inv,'still_visible':any(x['path']==result['path'] for k in ('checkpoint','lora') for x in inv[k])}
   if path=='/api/model-hub/select':
    if d['path'] not in [x['path'] for x in registry.scan('checkpoint',cfgmodel['config'])]:raise LocalModelError('File not in inventory')
    cfgmodel['config']['checkpoint']=d['path'];return {'ok':True}
   if path=='/api/setup/browse':
    current=Path(q.get('path',[str(ext)])[0] or ext);return {'path':str(current),'parent':str(current.parent),'entries':[{'path':str(x),'name':x.name,'directory':x.is_dir()} for x in sorted(current.iterdir())]}
   if path=='/api/setup':return {'settings':settings,'models':[cfgmodel],'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
   if path=='/api/account':return {'username':'C'}
   if path=='/api/identity/bootstrap':return {'runtime':{},'models':{},'jobs':[],'queue':{},'loras':boot()['loras'],'checkpoints':boot()['checkpoints'],'default_sdxl':cfgmodel['config']['checkpoint']}
   if path=='/api/training/bootstrap':return {'runtime':{},'datasets':[],'loras':[],'full_models':[],'full_unets':[],'jobs':[]}
   if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{},'csrf':'v'}
   if path=='/api/setup/identity-code-status':return {'installation':{'status':'idle'},'status':{}}
   return {}
  except Exception as e:return {'error':str(e),'_http_status':400}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width,height in [(390,844),(1440,1000)]:
   # Reset actual catalogue for each viewport.
   registry.registry_path.unlink(missing_ok=True);cfgmodel['config']['checkpoint']=initial
   context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page();page.set_default_timeout(7000)
   page.on('pageerror',lambda e:errors.append(str(e)))
   dialogs=[]
   def dialog(d):
    dialogs.append(d.message)
    if d.type=='confirm':d.accept()
    else:errors.append('UNEXPECTED DIALOG: '+d.message);d.dismiss()
   page.on('dialog',dialog)
   raw=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
   css=[ROOT/x['href'].split('?',1)[0].lstrip('/') for x in raw.select('link[rel=stylesheet]')]
   scripts=[ROOT/x['src'].split('?',1)[0].lstrip('/') for x in raw.select('script[src]')]
   for x in raw.find_all(['script','link']):x.decompose()
   logo_b64=base64.b64encode((ROOT/'static/zetalvx-logo.png').read_bytes()).decode()
   for img in raw.select('img[src^="/static/zetalvx-logo.png"]'):img['src']='data:image/png;base64,'+logo_b64
   raw.head.append(raw.new_tag('base',href='http://ui.local/'))
   page.set_content(str(raw));page.expose_function('_api',api_mock)
   page.evaluate('''()=>{const store=()=>{const d={};return {getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}};Object.defineProperty(window,'localStorage',{value:store()});Object.defineProperty(window,'sessionStorage',{value:store()});window.fetch=async(u,o={})=>{const d=await window._api(String(u),o.method||'GET',o.body||null);const s=d._http_status||200;delete d._http_status;return new Response(JSON.stringify(d),{status:s,headers:{'Content-Type':'application/json'}})}}''')
   for f in css:page.add_style_tag(content=f.read_text())
   for f in scripts:page.add_script_tag(content=f.read_text())
   page.wait_for_timeout(700);page.evaluate("ZI18n.setLanguage('it');showView('models')");page.wait_for_selector('#localCheckpointList .local-model-row')
   check(f'{width} initial catalogue',page.locator('#localCheckpointList .local-model-row').count()==1)
   check(f'{width} no duplicate IDs',page.evaluate('(()=>{const ids=[...document.querySelectorAll("[id]")].map(e=>e.id);return ids.length===new Set(ids).size})()'))
   check(f'{width} checkpoint plus lora controls',page.locator('[data-local-add-menu]').count()==2)
   # Select local file with the actual browser picker UI.
   page.locator('[data-local-add-menu="checkpoint"]').click();check(f'{width} four add methods',page.locator('[data-local-method]').count()==4);check(f'{width} upload method available',page.locator('#localModelUploadFile').count()==1);check(f'{width} multi file picker',page.locator('#localModelUploadFile').get_attribute('multiple') is not None);page.locator('#localModelUploadFile').set_input_files([cp,unknown]);check(f'{width} picker accepts two files',page.locator('#localModelUploadFile').evaluate('e=>e.files.length')==2);page.locator('#localModelUploadFile').set_input_files([]);check(f'{width} zetalvx logo visible',page.locator('.brand-logo-link img').count()==1);page.locator('[data-local-method="server"]').click()
   page.locator('[data-browse="localModelPath"]').click();page.wait_for_selector('#browserEntries button')
   page.locator('#browserEntries button').filter(has_text='newCheckpoint.safetensors').click()
   check(f'{width} file picker selects exact file',page.locator('#localModelPath').input_value()==cp)
   page.locator('#localModelSave').click();page.wait_for_function('document.querySelector("#localModelModal").classList.contains("hidden")')
   check(f'{width} external checkpoint no copy',Path(cp).exists() and not (models/'SDXL/newCheckpoint.safetensors').exists())
   check(f'{width} linked checkpoint visible',page.locator('#localCheckpointList').inner_text().find('newCheckpoint.safetensors')>=0)
   check(f'{width} add does not select active',cfgmodel['config']['checkpoint']==initial)
   # A Models default replaces stale per-job checkpoint overrides, but preserves every other generation setting.
   page.evaluate('([p])=>{setTask("generate");document.querySelector("#checkpointSelect").value=p;document.querySelector("#seed").value="123";document.querySelector("#steps").value="37";captureImageSettings();showView("models")}',[initial])
   row=page.locator('#localCheckpointList .local-model-row').filter(has_text='newCheckpoint.safetensors');row.get_by_role('button').first.click();page.wait_for_timeout(300)
   check(f'{width} active checkpoint selected',cfgmodel['config']['checkpoint']==cp)
   check(f'{width} hub active selector agrees',page.locator('#hubCheckpoint').input_value()==cp)
   check(f'{width} composer follows new default',page.locator('#checkpointSelect').input_value()=='')
   check(f'{width} stale checkpoint overrides cleared',page.evaluate('Object.values(S.imageSettings||{}).every(x=>!x?.controls?.checkpointSelect)'))
   check(f'{width} numeric controls unchanged',page.locator('#seed').input_value()=='123' and page.locator('#steps').input_value()=='37')
   # The old app-managed base checkpoint can be hidden/re-enabled after another default is active.
   base_row=page.locator('#localCheckpointList .local-model-row').filter(has_text='base.safetensors')
   base_row.get_by_role('button',name='Scollega da Generate').click();page.wait_for_timeout(120)
   check(f'{width} checkpoint can disconnect without deleting',Path(initial).exists() and 'Solo in libreria' in base_row.inner_text())
   base_row.get_by_role('button',name='Collega a Generate').click();page.wait_for_timeout(120)
   check(f'{width} checkpoint can reconnect',Path(initial).exists() and 'Disponibile in Generate' in base_row.inner_text())
   check(f'{width} active default cannot disconnect',row.get_by_role('button',name='Scollega da Generate').is_disabled())
   check(f'{width} managed checkpoint exposes delete',base_row.get_by_role('button',name='Elimina file').count()==1)
   check(f'{width} external default uses unlink not file delete',row.get_by_role('button',name='Elimina file').count()==0)
   check(f'{width} viewer close is geometric',page.evaluate('''()=>{const e=document.querySelector('#imageViewerClose'),c=getComputedStyle(e),b=getComputedStyle(e,'::before'),a=getComputedStyle(e,'::after');return c.fontSize==='0px'&&c.width==='46px'&&c.height==='46px'&&b.width==='19px'&&a.width==='19px'}'''))
   # LoRA reference and use in composer.
   page.locator('[data-local-add-menu="lora"]').click();page.locator('[data-local-method="server"]').click();page.locator('#localModelPath').fill(lora);page.locator('#localModelSave').click();page.wait_for_function('document.querySelector("#localModelModal").classList.contains("hidden")')
   page.locator('#hubLoraFiles .local-model-row').get_by_role('button').first.click();page.wait_for_timeout(150)
   check(f'{width} use lora opens composer',page.locator('#view-image').evaluate('e=>e.classList.contains("active")'))
   check(f'{width} lora selected once',page.evaluate('(p)=>S.loras.filter(x=>x.path===p).length',lora)==1)
   page.evaluate("showView('models')");page.locator('#hubLoraFiles .local-model-row').get_by_role('button').first.click()
   check(f'{width} no duplicate lora stack',page.evaluate('(p)=>S.loras.filter(x=>x.path===p).length',lora)==1)
   page.evaluate("showView('image')");page.locator('#addLoraBtn').click();page.wait_for_selector('#loraList>button');check(f'{width} lora choices dark styled',page.locator('#loraList>button').first.evaluate("e=>getComputedStyle(e).backgroundColor!=='rgb(255, 255, 255)' && getComputedStyle(e).textAlign==='left'"));page.locator('#closeLora').click();page.evaluate("showView('models')")
   # Reuse no longer calls undefined renderLoras.
   page.evaluate('(id)=>reuseArtifact(id)',asset['id']);check(f'{width} reuse image works',page.locator('#width').input_value()=='960')
   page.evaluate("showView('models')")
   # folder auto refresh and pagination.
   page.locator('[data-local-add-menu="checkpoint"]').click();page.locator('[data-local-method="folder"]').click();page.locator('#localModelFolder').fill(str(many));page.locator('#localModelFolderSave').click();page.wait_for_function('document.querySelector("#localModelModal").classList.contains("hidden")')
   check(f'{width} bounded catalogue page',page.locator('#localCheckpointList .local-model-row').count()==6)
   check(f'{width} pager visible',page.locator('#localCheckpointPages button').count()==2)
   page.locator('#localCheckpointSearch').fill('model7');check(f'{width} search narrows',page.locator('#localCheckpointList .local-model-row').count()==1)
   page.locator('#localCheckpointSearch').fill('')
   page.locator('#localCheckpointPages button').last.click();check(f'{width} second catalogue page',page.locator('#localCheckpointPages').inner_text().find('2 / 2')>=0)
   # Missing compatibility asks confirmation, no GPU loading.
   page.locator('[data-local-add-menu="checkpoint"]').click();page.locator('[data-local-method="server"]').click();page.locator('#localModelPath').fill(unknown);page.locator('#localModelSave').click();page.wait_for_function('document.querySelector("#localModelModal").classList.contains("hidden")')
   check(f'{width} compatibility confirmation',any('Compatibility' in d or 'compatibil' in d.lower() for d in dialogs))
   # remove source without touching actual bytes.
   page.locator('#localSourcesPanel').evaluate('e=>e.open=true')
   source=page.locator('.local-source-row').filter(has_text='Portrait LoRA.safetensors');source.get_by_role('button').click();page.wait_for_timeout(200)
   check(f'{width} reference removed not weight',Path(lora).exists() and not any(x['path']==lora for x in registry.sources()))
   page.locator('#localSourcesPanel').evaluate('e=>e.open=false');page.locator('#localCheckpointSearch').fill('')
   page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'models_{width}.png'),full_page=True)
   check(f'{width} catalogue fits viewport',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
   # Details must stay open while a refresh only updates status/catalogue.
   page.locator('#hubSdxlPaths').evaluate('e=>e.open=true');page.locator('#setupCheckpoint').fill('/unsaved/draft.safetensors');page.evaluate('refreshModelsHub()');page.wait_for_timeout(200)
   check(f'{width} refresh preserves advanced open',page.locator('#hubSdxlPaths').evaluate('e=>e.open'))
   check(f'{width} refresh preserves unsaved path',page.locator('#setupCheckpoint').input_value()=='/unsaved/draft.safetensors')
   # Real training renderer with a deliberately extreme path.
   longpath='/home/user/.local/share/CreatorStudioSDXL/models/loras/SDXL/'+('long_filename_'*38)+'.safetensors'
   page.evaluate("showView('training')");page.wait_for_timeout(250)
   page.locator('[data-training-page=results]').click();page.wait_for_timeout(100)
   page.evaluate('''(longpath)=>{S.training.jobs=[{id:'b'.repeat(32),name:'Test LoRA',mode:'lora',status:'completed',stage:'completed',progress:1,step:300,max_steps:300,dataset_name:'Test',dataset_id:'c'.repeat(32),trigger_word:'subject',caption_policy:'saved_text_v1',caption_over_limit:4,registered_lora:longpath,checkpoints:[],created_at:'2026-09-21'}];renderTrainingJobs(S.training.jobs);document.querySelectorAll('[data-training-panel]').forEach(e=>e.hidden=e.dataset.trainingPanel!=='results');document.querySelector('#trainingLogPanel').classList.remove('hidden');document.querySelector('#trainingLogText').textContent=longpath.repeat(4);window.scrollTo(0,0)}''',longpath)
   # the actual workspace uses data-training-page instead; handle both gracefully.
   page.evaluate('''()=>{const b=[...document.querySelectorAll('#view-training [data-workspace-tab],#view-training [data-training-tab]')].find(e=>e.dataset.workspaceTab==='results'||e.dataset.trainingTab==='results');if(b)b.click()}''')
   page.wait_for_timeout(150)
   check(f'{width} long path fits viewport',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
   check(f'{width} training code wraps',page.locator('#trainingJobs code').first.evaluate("e=>getComputedStyle(e).overflowWrap==='anywhere' && e.getBoundingClientRect().width<=innerWidth"))
   page.screenshot(path=str(OUT/f'training_long_path_{width}.png'),full_page=True)
   page.evaluate("showView('models');document.querySelector('[data-hub-tab=installed]').click()")
   for lang in ['it','en','de','ar']:
    page.evaluate('(l)=>ZI18n.setLanguage(l)',lang);page.wait_for_timeout(100)
    check(f'{width} {lang} catalog no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
   context.close()
  browser.close()
(OUT/'report.json').write_text(json.dumps({'checks':checks,'errors':errors,'test_type':'Chromium + LocalModels real filesystem; HTTP host, inference and training simulated'},indent=2))
print('CHECKS',len(checks),'ERRORS',errors)
if errors:raise SystemExit(1)
