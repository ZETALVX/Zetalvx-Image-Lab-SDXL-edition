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
from tests.test_lora_management_102 import weights
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
 managed=[models/'loras/SDXL'/f'test_step_{n}.safetensors' for n in (100,200,300)]
 for p in managed:p.write_bytes(weights())
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
   if path=='/api/loras':return {'loras':registry.scan('lora',cfgmodel['config'])}
   if path.endswith('/availability') and method=='PUT':
    cid=path.split('/')[-2];changed=registry.set_lora_availability(cid,d.get('enabled'),cfgmodel['config']);return {'ok':True,**changed,'catalog':inventory(),'loras':registry.scan('lora',cfgmodel['config'])}
   if path=='/api/model-hub/local':
    if method=='POST':return {'ok':True,**registry.add(d.get('path'),d.get('kind'),d.get('entry_type','file'),d.get('accept_unknown') is True),'catalog':inventory()}
    return {'ok':True,'catalog':inventory()}
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
   if path=='/api/training/bootstrap':return {'runtime':{},'datasets':[],'loras':[dict(x,id=x['training_id'],catalog_id=x['id'],size=x['size_bytes'],status='ready') for x in inventory()['lora']],'full_models':[],'full_unets':[],'jobs':[]}
   if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{},'csrf':'v'}
   if path=='/api/setup/identity-code-status':return {'installation':{'status':'idle'},'status':{}}
   return {}
  except Exception as e:return {'error':str(e),'_http_status':400}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width,height in [(390,844),(1440,1000)]:
   # Reset actual catalogue for each viewport.
   registry.registry_path.unlink(missing_ok=True);registry.visibility_path.unlink(missing_ok=True);cfgmodel['config']['checkpoint']=initial
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
   page.set_content(str(raw),wait_until='domcontentloaded');page.expose_function('_api',api_mock)
   page.evaluate('''()=>{const store=()=>{const d={};return {getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}};Object.defineProperty(window,'localStorage',{value:store()});Object.defineProperty(window,'sessionStorage',{value:store()});window.fetch=async(u,o={})=>{const d=await window._api(String(u),o.method||'GET',o.body||null);const s=d._http_status||200;delete d._http_status;return new Response(JSON.stringify(d),{status:s,headers:{'Content-Type':'application/json'}})}}''')
   for f in css:page.add_style_tag(content=f.read_text())
   for f in scripts:page.add_script_tag(content=f.read_text())
   page.wait_for_timeout(650);page.evaluate("ZI18n.setLanguage('en');showView('models')");page.wait_for_selector('#hubLoraFiles .local-model-row')
   check(f'{width} three existing Diffusers UNet-only files visible',page.locator('#hubLoraFiles .local-model-row').count()==3)
   # Select step100 first, then disconnect it. It must not remain invisibly active.
   row100=page.locator('#hubLoraFiles .local-model-row').filter(has_text='test_step_100.safetensors')
   row100.get_by_role('button',name='Use in Create',exact=True).click();page.wait_for_timeout(150)
   check(f'{width} step100 selected',page.evaluate('(p)=>S.loras.some(x=>x.path===p)',str(managed[0])))
   page.evaluate("showView('models')");page.wait_for_timeout(150)
   for step in (100,200):
    row=page.locator('#hubLoraFiles .local-model-row').filter(has_text=f'test_step_{step}.safetensors')
    row.get_by_role('button',name='Disconnect from Generate',exact=True).click();page.wait_for_timeout(200)
   check(f'{width} disconnected selection removed',page.evaluate('S.loras.length')==0)
   check(f'{width} files all kept',all(p.exists() for p in managed))
   check(f'{width} library still has three',page.locator('#hubLoraFiles .local-model-row').count()==3)
   check(f'{width} disconnected use button disabled',row100.get_by_role('button',name='Use in Create',exact=True).is_disabled())
   check(f'{width} only300 from actual catalog', [x['name'] for x in registry.scan('lora',cfgmodel['config'])]==['test_step_300.safetensors'])
   page.evaluate("showView('image')");page.locator('#addLoraBtn').click();page.wait_for_selector('#loraList>button')
   check(f'{width} Generate offers only300',page.locator('#loraList>button').count()==1 and '300' in page.locator('#loraList').inner_text())
   page.locator('#closeLora').click();page.evaluate("showView('models')");page.wait_for_timeout(150)
   row=page.locator('#hubLoraFiles .local-model-row').filter(has_text='test_step_100.safetensors');row.get_by_role('button',name='Connect to Generate',exact=True).click();page.wait_for_timeout(200)
   page.evaluate("showView('image')");page.locator('#addLoraBtn').click();page.wait_for_selector('#loraList>button')
   check(f'{width} reconnect100 returns to choices',page.locator('#loraList>button').count()==2)
   page.locator('#closeLora').click();page.evaluate("showView('training')");page.wait_for_timeout(350)
   check(f'{width} Training has availability switches',page.locator('[data-lora-availability]').count()==3)
   cid=next(x['id'] for x in inventory()['lora'] if x['name']=='test_step_300.safetensors')
   # Training has tab panels; inspect renderer and call its actual change handler.
   switch=page.locator('[data-lora-availability="'+cid+'"]');switch.evaluate('e=>{e.checked=false;e.dispatchEvent(new Event("change",{bubbles:true}))}');page.wait_for_timeout(200)
   check(f'{width} Training switch persists',next(x for x in inventory()['lora'] if x['id']==cid)['generation_enabled'] is False)
   check(f'{width} visibility survives new registry object',[x['name'] for x in LocalModels(models,registry.registry_path).scan('lora',cfgmodel['config'])]==['test_step_100.safetensors'])
   page.evaluate("showView('models')");page.wait_for_timeout(150)
   check(f'{width} no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
   page.screenshot(path=str(OUT/f'lora_management_{width}.png'),full_page=True)
   check(f'{width} no inference/training request',not any('/jobs' in x[0] and x[1]=='POST' for x in requests))
   context.close()
  browser.close()
(OUT/'report.json').write_text(json.dumps({'checks':checks,'errors':errors,'test_type':'Actual Chromium and actual LocalModels files; HTTP routes and GPU services are fixtures, not Flask acceptance'},indent=2))
print('CHECKS',len(checks),'ERRORS',errors)
if errors:raise SystemExit(1)
