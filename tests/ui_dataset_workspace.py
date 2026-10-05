"""Browser integration: actual Workspace, ZIP and Batch with a fake Vision engine.
Non-dataset endpoints and GPU training dispatch are simulated. Not a Flask/GPU test.
"""
import argparse,http.server,threading,json,sys,io,tempfile,hashlib,time,zipfile,traceback
from pathlib import Path
from email.parser import BytesParser
from email.policy import default
from types import SimpleNamespace
from urllib.parse import urlparse
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.dataset_workspace import Workspace,DatasetConflict,DatasetBusy
from core.dataset_exchange import DatasetError
from core.task_adapters import support_matrix
from core.model_policy import catalog
from vision.registry import Registry,atomic_json
from vision.batch import Batch
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
OUT=Path(args.output).resolve();OUT.mkdir(parents=True,exist_ok=True)
tmp=tempfile.TemporaryDirectory();DATA=Path(tmp.name)
reg=Registry(DATA);profiles=[reg.save({'name':name,'backend':'api','api_model':'mock','endpoint':'http://127.0.0.1:1/v1','terms_reviewed':True,'enabled':True}) for name in ['Test Vision A','Test Vision B']]
entered=threading.Event();release=threading.Event();release.set();train_requests=[];errors=[];checks=[];requests=[];dialogs=[]
class Engine:
 def caption(self,m,image,prompt,stop):
  entered.set();release.wait(8)
  if 'itapigna' in prompt:return 'a portrait of itapigna outside'
  return 'a person outside'
 def unload(self):pass
batch=Batch(DATA/'visionjobs',DATA/'datasets',reg,Engine())
store=Workspace(DATA/'datasets',DATA/'trainjobs',lock=batch.lock,caption_active=lambda did:batch.busy() and any(j['dataset_id']==did and j['status'] in ('queued','running') for j in batch.list()))
model=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
model['config'].update(checkpoint='/test/sdxl.safetensors',checkpoint_roots='/test',lora_root='/test/loras')
model['validation']={'ready':True,'fields':[],'missing':[]};model['task_support']=support_matrix(model);model['status']='Ready'
project={'id':'a'*32,'name':'Workspace test','description':'','state':{},'artifacts':[],'jobs':[],'messages':[]}
settings={'host':'127.0.0.1','identity_root':'/test/Identity'}
boot={'models':[model],'projects':[project],'recipes':[],'loras':[],'checkpoints':[{'name':'SDXL','path':'/test/sdxl.safetensors'}],'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
train_jobs=[]
def datasets():
 return [{**store.read(p.parent.name),'item_count':len(store.read(p.parent.name)['items'])} for p in sorted(store.root.glob('*/dataset.json'))]
def serve_api(path,method,d,files):
 requests.append([method,path]);segments=path.split('/')
 if path=='/api/session/tokens':return {'tokens':{'vision':'test-csrf','model-hub':'test-csrf'}}
 if path=='/api/model-hub/local':return {'ok':True,'catalog':{'checkpoint':[], 'lora':[], 'sources':[]}}
 if path=='/api/bootstrap':return boot
 if path.startswith('/api/projects/'):return {'project':project}
 if path=='/api/model-hub/status':return {'ok':True,'settings':settings,'models':[model],'sdxl':{'ready':True},'identity':{},'accounts':{},'jobs':[],'catalog':catalog(),'paths':{},'checkpoints':boot['checkpoints'],'loras':[],'vaes':[]}
 if path=='/api/setup':return {'models':[model],'settings':settings,'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
 if path=='/api/account':return {'username':'C'}
 if path=='/api/identity/bootstrap':return {'runtime':{},'models':{},'jobs':[],'queue':{},'loras':[],'checkpoints':[]}
 if path=='/api/vision/models':return {'models':reg.list(),'default_python':'/test/python'}
 if path=='/api/vision/actions':return {'actions':[],'runtime':{}}
 if path=='/api/training/bootstrap':return {'runtime':{'ok':True},'datasets':datasets(),'loras':[],'full_unets':[],'full_models':[],'jobs':train_jobs,'default_sdxl':'/test/sdxl.safetensors'}
 if path=='/api/training/vision/jobs':return {'jobs':batch.list()}
 if path=='/api/training/vision/cancel':batch.cancel();release.set();return {'ok':True}
 if path=='/api/training/datasets':
  if method=='GET':return {'datasets':datasets()}
  return store.response(store.create(d))
 if path=='/api/training/datasets/import-zip':return {'ok':True,'dataset':store.import_archive(files[0].stream)}
 if path.startswith('/api/training/datasets/'):
  did=segments[4];tail=segments[5:]
  if not tail:
   if method=='GET':return store.response(store.read(did))
   if method=='DELETE':return {'ok':True,'deleted':store.remove(did)}
   return store.response(store.update(did,d))
  if tail==['upload']:return store.uploads(did,files)
  if tail==['apply-trigger']:return store.apply(did)
  if tail==['caption-check']:return {'report':store.info(store.read(did))}
  if tail==['use']:return store.preflight(did)
  if tail==['vision-caption']:
   if not d.get('confirm'):raise DatasetError('Confirm images')
   store.editable(did,structural=True);return {'job':batch.start(did,d['model_id'])}
  if tail==['export']:
   p=DATA/'export.zip';store.export_archive(did,p);return ('application/zip',p.read_bytes())
  if len(tail)>=2 and tail[0]=='items':
   iid=tail[1]
   if method=='DELETE':return store.response(store.remove_item(did,iid))
   p=store.image_path(did,iid)
   if tail[-1]=='thumbnail':
    with Image.open(p) as im:
     im=im.convert('RGB');im.thumbnail((256,256));b=io.BytesIO();im.save(b,'JPEG');return ('image/jpeg',b.getvalue())
   return ('image/png',p.read_bytes())
 if path=='/api/training/jobs' and method=='POST':
  store.preflight(d['dataset_id']);train_requests.append(d);j={'id':('e'*31)+str(len(train_requests)),**d,'status':'queued','mode':d.get('mode','lora'),'progress':{'status':'queued','step':0,'max_steps':d.get('max_steps',1)}};train_jobs.insert(0,j);return {'job':j,'ok':True}
 if path.startswith('/api/training/jobs/') and path.endswith('/log'):return {'text':'simulated dispatch'}
 return {}
class Handler(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path.startswith('/api/'):return self.api()
  if self.path=='/':self.path='/templates/index.html'
  return super().do_GET()
 def do_POST(self):return self.api()
 def do_PUT(self):return self.api()
 def do_DELETE(self):return self.api()
 def api(self):
  try:
   d={};files=[];path=urlparse(self.path).path;raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
   if self.command!='GET' and path.startswith(('/api/training/datasets','/api/training/vision')) and self.headers.get('X-CSRF-Token')!='test-csrf':raise DatasetError('Missing CSRF')
   typ=self.headers.get('Content-Type','')
   if raw and typ.startswith('multipart/'):
    msg=BytesParser(policy=default).parsebytes(('Content-Type: '+typ+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
    for part in msg.iter_parts():
     if part.get_filename():files.append(SimpleNamespace(filename=part.get_filename(),stream=io.BytesIO(part.get_payload(decode=True))))
   elif raw:d=json.loads(raw)
   out=serve_api(path,self.command,d,files);status=200
  except (DatasetConflict,DatasetBusy) as e:out={'error':str(e),'code':'dataset_conflict' if isinstance(e,DatasetConflict) else 'dataset_busy'};status=409
  except Exception as e:
   out={'error':str(e)};status=400
   if not isinstance(e,DatasetError):traceback.print_exc();errors.append(type(e).__name__+': '+str(e))
  if isinstance(out,tuple):mime,body=out
  else:mime='application/json';body=json.dumps(out).encode()
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
  if mime=='application/zip':self.send_header('Content-Disposition','attachment; filename=dataset.zip')
  self.end_headers();self.wfile.write(body)
def png(color):
 b=io.BytesIO();Image.new('RGB',(120,200),color).save(b,'PNG');return b.getvalue()
def fi(name,buffer,mime='image/png'):return {'name':name,'mimeType':mime,'buffer':buffer}
def check(name,condition):
 checks.append({'name':name,'passed':bool(condition)});print(name, bool(condition),flush=True)
 if not condition:raise AssertionError(name)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width,height in [(390,844),(1440,1000)]:
  ctx=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
  page=ctx.new_page();page.set_default_timeout(8000);page.on('pageerror',lambda e:errors.append(str(e)))
  def dialog(d):dialogs.append(d.message);d.accept()
  # Browser navigation is disabled in the build environment. Bind fetch to the
  # actual stdlib host. Non-dataset endpoints are explicitly simulated above.
  import base64
  from bs4 import BeautifulSoup
  def bridge(path,method,body,headers):
   from urllib.request import Request,urlopen
   from urllib.error import HTTPError
   target=f'http://127.0.0.1:{server.server_port}'+urlparse(path).path+('?' + urlparse(path).query if urlparse(path).query else '')
   data=base64.b64decode(body) if body is not None else None
   try:r=urlopen(Request(target,data=data,headers=headers,method=method),timeout=10)
   except HTTPError as e:r=e
   with r:return {'status':r.status,'type':r.headers.get('Content-Type',''),'body':base64.b64encode(r.read()).decode()}
  html=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
  styles=[urlparse(tag.get('href','')).path for tag in html.find_all('link',rel='stylesheet')]
  scripts=[urlparse(tag.get('src','')).path for tag in html.find_all('script') if tag.get('src')]
  for tag in html.find_all(['script','link']):tag.decompose()
  basetag=html.new_tag('base',href='https://workspace.test/');html.head.append(basetag)
  page.set_content(str(html));page.expose_function('_bridge',bridge);page.on('dialog',dialog)
  page.evaluate("""()=>{
   const makeStore=()=>{const s={};return {setItem:(k,v)=>s[k]=String(v),getItem:k=>s[k]??null,removeItem:k=>delete s[k],clear:()=>Object.keys(s).forEach(k=>delete s[k])}};
   Object.defineProperty(window,'localStorage',{value:makeStore()});Object.defineProperty(window,'sessionStorage',{value:makeStore()});
   window.fetch=async(url,opt={})=>{const headers=new Headers(opt.headers||{});let body=null;
    if(opt.body instanceof FormData){const r=new Response(opt.body);headers.set('Content-Type',r.headers.get('Content-Type'));const bytes=new Uint8Array(await r.arrayBuffer());body=btoa(Array.from(bytes,x=>String.fromCharCode(x)).join(''));}
    else if(opt.body!==undefined&&opt.body!==null)body=btoa(unescape(encodeURIComponent(opt.body)));
    const d=await window._bridge(String(url),opt.method||'GET',body,Object.fromEntries(headers));return new Response(Uint8Array.from(atob(d.body),c=>c.charCodeAt(0)),{status:d.status,headers:{'Content-Type':d.type}});
   };
   const desc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src'),getattr=Element.prototype.getAttribute;
   Object.defineProperty(HTMLImageElement.prototype,'src',{get(){return this.__sourceUrl||desc.get.call(this)},set(v){
    if(v.startsWith('/api/')){this.__sourceUrl=v;window._bridge(v,'GET',null,{}).then(d=>desc.set.call(this,'data:'+d.type+';base64,'+d.body));}else{delete this.__sourceUrl;desc.set.call(this,v)}
   }});
   Element.prototype.getAttribute=function(n){if(n==='src'&&this.__sourceUrl)return this.__sourceUrl;return getattr.call(this,n)};
  }""")
  for style in styles:page.add_style_tag(content=(ROOT/style.lstrip('/')).read_text())
  for script in scripts:
   content=(ROOT/script.lstrip('/')).read_text()
   if script.endswith('training-workspace.js'):
    content=content.replace("window.location.href='/api/training/datasets/'+did()+'/export'", "window.__exportHref='/api/training/datasets/'+did()+'/export'")
   page.add_script_tag(content=content)
  page.wait_for_function('!!window.ZetalvxDatasetWorkspace');page.wait_for_timeout(500)
  page.evaluate("ZI18n.setLanguage('it');showView('training')")
  page.wait_for_selector('#trainingPageDataset:visible');page.wait_for_timeout(500)
  check(f'{width} no separate frame/app',page.locator('#view-training iframe').count()==0)
  check(f'{width} one active training page',page.locator('#view-training > section:visible').count()==1)
  page.locator('#trainingCreateDataset').click();page.locator('#dsCreateName').fill('UI Dataset '+str(width));page.locator('#dsCreateTrigger').fill('itapigna');page.locator('#dsCreatePosition').select_option('suffix');page.locator('#dsCreateForm button[type=submit]').click()
  page.wait_for_selector('#dsWorkspace:visible');page.wait_for_function(f"document.querySelector('#dsTrainName').textContent==='UI Dataset {width}'")
  did=page.evaluate('S.training.dataset.id');check(f'{width} created dataset at canonical path',(store.root/did/'dataset.json').is_file())
  images=[fi('a.png',png('navy')),fi('a.txt',b'a portrait of itapigna\n','text/plain'),fi('b.png',png('olive')),fi('c.png',png('teal')),fi('dupe.png',png('olive'))]
  page.locator('#trainingUploadImages').set_input_files(images);page.wait_for_function('S.training.dataset.items.length===3')
  check(f'{width} images uploaded deduplicated',len(store.read(did)['items'])==3)
  check(f'{width} matching TXT unchanged',store.read(did)['items'][0]['caption']=='a portrait of itapigna\n')
  page.wait_for_function('document.querySelector("#dsImagePreview").naturalWidth>0')
  check(f'{width} preview contain',page.locator('#dsImagePreview').evaluate("e=>getComputedStyle(e).objectFit==='contain'"))
  check(f'{width} no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
  check(f'{width} thumbnails not fullsize',page.locator('#dsGallery img').first.evaluate('e=>e.__sourceUrl').endswith('thumbnail'))
  page.locator('#dsCaption').fill('MANUAL itapigna draft ')
  page.wait_for_timeout(3300)
  check(f'{width} poll preserves dirty text',page.locator('#dsCaption').input_value()=='MANUAL itapigna draft ')
  page.locator('#dsNext').click();page.wait_for_function("document.querySelector('#dsImageName').textContent==='b.png'")
  check(f'{width} next saved exact caption',store.read(did)['items'][0]['caption']=='MANUAL itapigna draft ')
  page.locator('#dsCaption').fill('')
  page.locator('#trainingVisionModel').select_option(profiles[0]['id']);page.wait_for_function(f"S.training.dataset.vision_model_id==='{profiles[0]['id']}'")
  check(f'{width} profile saved in dataset',store.read(did)['vision_model_id']==profiles[0]['id'])
  page.locator('#dsFilter').select_option('missing');page.wait_for_timeout(200)
  check(f'{width} missing filter',page.locator('#dsGallery [data-dataset-image]').count()==2)
  entered.clear();release.clear();page.locator('#trainingAutoCaption').click();check(f'{width} caption request reached actual Batch',entered.wait(5))
  page.wait_for_selector('#trainingCancelCaption:visible')
  check(f'{width} handoff blocked while captioning',page.locator('#dsUseForTraining').is_disabled())
  page.locator('#dsCaption').fill('Manual during vision itapigna');page.locator('#trainingSaveCaptions').click()
  page.wait_for_function("!ZetalvxDatasetWorkspace.dirty")
  release.set();batch.thread.join(5);page.locator('#dsFilter').select_option('all');page.locator('#dsRefresh').click()
  page.wait_for_function('S.training.dataset.items.every(x=>x.caption)')
  check(f'{width} manual concurrent caption preserved',store.read(did)['items'][1]['caption']=='Manual during vision itapigna')
  check(f'{width} automatic suffix',store.read(did)['items'][2]['caption']=='a person outside, itapigna')
  check(f'{width} all captions canonical',store.info(store.read(did))['needs_caption']==0)
  page.locator('.ds-settings').evaluate('e=>e.open=true')
  page.locator('#trainingTriggerPosition').select_option('context');page.locator('#dsSaveSettings').click();page.wait_for_function('!ZetalvxDatasetWorkspace.dirty')
  page.locator('.ds-settings').evaluate('e=>e.open=false')
  page.locator('#dsGallery [data-dataset-image]').nth(2).click();page.locator('#dsCaption').fill('');page.locator('#trainingSaveCaptions').click();page.wait_for_function('!ZetalvxDatasetWorkspace.dirty')
  page.locator('#trainingAutoCaption').click();page.wait_for_timeout(500)
  if batch.thread:batch.thread.join(5)
  page.locator('#dsRefresh').click();page.wait_for_function("S.training.dataset.items[2].caption==='a portrait of itapigna outside'")
  check(f'{width} context automatic through shared engine',store.read(did)['items'][2]['caption']=='a portrait of itapigna outside')
  check(f'{width} prior actions retained',len(batch.list())>=2)
  before=(store.root/did/'dataset.json').read_bytes();count_before=len(datasets())
  page.locator('#dsUseForTraining').click();page.wait_for_selector('#trainingPageTrain:visible')
  check(f'{width} handoff no dataset copy',len(datasets())==count_before)
  check(f'{width} handoff no manifest rewrite',(store.root/did/'dataset.json').read_bytes()==before)
  check(f'{width} no automatic train',len(train_requests)==(0 if width==390 else 1))
  page.locator('#trainingSteps').fill('432')
  page.evaluate("showView('home');showView('training')");page.wait_for_timeout(400)
  check(f'{width} training custom values preserved',page.locator('#trainingSteps').input_value()=='432')
  page.screenshot(path=str(OUT/f'training_{width}.png'),full_page=True)
  page.locator('#trainingStart').click();page.wait_for_selector('#trainingPageResults:visible');page.wait_for_timeout(250)
  check(f'{width} dispatch uses selected dataset',train_requests[-1]['dataset_id']==did)
  check(f'{width} dispatch uses custom steps',train_requests[-1]['max_steps']==432)
  page.locator('[data-training-page="dataset"]').click();page.wait_for_selector('#trainingPageDataset:visible')
  # Switch to a new dataset, then back, keeping both per-dataset model selections.
  page.locator('#trainingCreateDataset').click();page.locator('#dsCreateName').fill('Other '+str(width));page.locator('#dsCreateForm button[type=submit]').click();page.wait_for_function(f"S.training.dataset.id!=='{did}'")
  other=page.evaluate('S.training.dataset.id');page.locator('#trainingVisionModel').select_option(profiles[1]['id']);page.wait_for_function('!ZetalvxDatasetWorkspace.dirty')
  page.locator('#trainingDatasetSelect').select_option(did);page.wait_for_function(f"S.training.dataset.id==='{did}'")
  check(f'{width} restore per-dataset Vision profile',page.locator('#trainingVisionModel').input_value()==profiles[0]['id'])
  # Export via real endpoint, import into same training store, then verify captions.
  page.locator('.ds-menu > summary').click()
  page.locator('#datasetZipExport').click();page.wait_for_function('!!window.__exportHref');export_path=page.evaluate('window.__exportHref');check(f'{width} export points to canonical dataset',export_path==f'/api/training/datasets/{did}/export');z=base64.b64decode(bridge(export_path,'GET',None,{})['body'])
  with zipfile.ZipFile(io.BytesIO(z)) as arc:
   check(f'{width} export exact captions',arc.read('images/00001.txt').decode()=='MANUAL itapigna draft ')
  page.locator('#datasetZipImport').set_input_files(fi('dataset.zip',z,'application/zip'));page.wait_for_function(f"S.training.dataset.id!=='{did}' && S.training.dataset.items.length===3")
  imported=page.evaluate('S.training.dataset.id');check(f'{width} import captions unchanged',[x['caption'] for x in store.read(imported)['items']]==[x['caption'] for x in store.read(did)['items']])
  page.locator('.ds-menu').evaluate('e=>e.open=false')
  page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(200)
  check(f'{width} Italian labels','Dataset' in page.locator('[data-training-page="dataset"]').inner_text() and 'Allena' in page.locator('[data-training-page="train"]').inner_text())
  check(f'{width} UI below mobile viewport width',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
  page.screenshot(path=str(OUT/f'dataset_{width}.png'),full_page=True)
  extra=[fi('page'+str(n)+'.png',png((20+n*10,100,130))) for n in range(13)]
  page.locator('#trainingUploadImages').set_input_files(extra);page.wait_for_function('S.training.dataset.items.length===16')
  check(f'{width} gallery bounded to 12 thumbnails',page.locator('#dsGallery [data-dataset-image]').count()==12)
  page.locator('#dsPageNext').click();page.wait_for_timeout(3000)
  check(f'{width} gallery pagination survives polling',page.locator('#dsGallery [data-dataset-image]').count()==4)
  page.locator('#dsGallery [data-dataset-image]').first.click();page.locator('#dsCaption').fill('preserved selected page');page.locator('#trainingSaveCaptions').click();page.wait_for_function('!ZetalvxDatasetWorkspace.dirty')
  check(f'{width} caption edit does not jump gallery page',page.locator('#dsGallery [data-dataset-image]').count()==4)
  page.locator('#dsRemoveImage').click();page.wait_for_function('S.training.dataset.items.length===15')
  check(f'{width} remove image updates canonical dataset',len(store.read(imported)['items'])==15)
  page.locator('#trainingManageVision').click();page.wait_for_selector('#visionHub:visible')
  check(f'{width} opens same-app Vision manager',page.locator('.vision-model-row').count()==2)
  check(f'{width} configured API available',page.locator('#visionHub').inner_text().find('Test Vision A')>=0)
  page.evaluate("showView('identity');setIdentityMode('instantid')");page.wait_for_timeout(150)
  check(f'{width} Identity still present',page.locator('#identityWidth').is_visible())
  page.evaluate("setTask('generate')")
  check(f'{width} image controls intact',page.locator('#negativePrompt').is_visible() and page.locator('#width').is_visible())
  ctx.close()
 browser.close()
server.shutdown();release.set()
(OUT/'report.json').write_text(json.dumps({'kind':'actual UI+Workspace+Batch; stdlib host; mocked Vision/GPU and unrelated endpoints','checks':checks,'errors':errors,'dialogs':dialogs,'requests':requests},indent=2))
print('CHECKS',len(checks),'FAILURES',sum(not x['passed'] for x in checks),'ERRORS',errors)
if errors or any(not x['passed'] for x in checks):raise SystemExit(1)
