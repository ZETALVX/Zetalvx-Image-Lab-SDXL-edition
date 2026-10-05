"""Workspace regression (suite originating in .28), current .33 HTML/CSS/JS in Chromium; mocked transport/database, real pure planner.
Not a native iPhone, Flask/auth, Windows or GPU test. No models/downloads needed.
"""
from pathlib import Path
import sys, argparse, json, copy, base64, ast, uuid, time, re, asyncio, mimetypes
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.image_test_plan import plan_image_test
from core.task_adapters import support_matrix
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();OUT=Path(args.output);OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];state={};page=None
ns={'re':re,'uuid':uuid,'time':time}
tree=ast.parse((ROOT/'app.py').read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'_safe_preset_id','_normalize_user_image_preset'}]
exec(compile(ast.Module(body=nodes,type_ignores=[]),'normalizer','exec'),ns)
model=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
model['config'].update(checkpoint='/fixtures/base.safetensors',checkpoint_roots='/fixtures',lora_root='/fixtures/loras')
model['validation']={'ready':True,'fields':[],'missing':[]};model['status']='Ready';model['task_support']=support_matrix(model)
checkpoint=[{'name':'base.safetensors','path':'/fixtures/base.safetensors'},{'name':'other.safetensors','path':'/fixtures/other.safetensors'}]
loras=[{'name':'Eyes.safetensors','path':'/fixtures/loras/Eyes.safetensors'}]
asset={'id':'b'*32,'type':'image','url':'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==','created_at':'2026-09-01','metadata':{'model_id':'sdxl'},'width':512,'height':512}
project={'id':'a'*32,'name':'Demo','description':'','sort_order':0,'trashed':0,'created_at':'2026-09-01','state':{},'jobs':[],'messages':[],'artifacts':[asset]}
def reset():state.clear();state.update(presets=[],project=copy.deepcopy(project),requests=[],enqueues=[],last_preview=None,writes=0,preview_delay=0)
def mock(path,method='GET',data=None):
 from urllib.parse import urlsplit
 path=urlsplit(path).path;state['requests'].append([method,path])
 d=json.loads(data) if isinstance(data,str) and data else data or {}
 if path=='/api/session/tokens':return {'tokens':{'model-hub':'test','vision':'test'}}
 if path=='/api/bootstrap':return {'projects':[state['project']],'models':[model],'runtime':{'ok':False},'recipes':[],'loras':loras,'checkpoints':checkpoint,'user_image_presets':copy.deepcopy(state['presets']),'image_preset_bindings':{'bindings':{}}}
 if path.startswith('/api/projects/') and path.count('/')==3:return {'project':copy.deepcopy(state['project'])}
 if path=='/api/image/auto-test/preview':
  task={'generate_image':'generate','edit_image':'edit','inpaint':'inpaint','reference':'reference','multi_image':'multi_image'}[d['tool']]
  plan=plan_image_test(d['params'],d['sweep'],task,random_seed=lambda:123456)
  request=copy.deepcopy(d);request['params']['seed']=plan['base_seed'];request['expected_count']=plan['count'];state['last_preview']={'plan':plan,'request':request}
  return {'ok':True,**state['last_preview']}
 if path=='/api/image/auto-test':
  task={'generate_image':'generate','edit_image':'edit','inpaint':'inpaint','reference':'reference','multi_image':'multi_image'}[d['tool']]
  plan=plan_image_test(d['params'],d['sweep'],task)
  assert d['expected_count']==plan['count'];state['enqueues'].append(copy.deepcopy(d))
  for v in plan['variants']:state['project']['jobs'].append({'id':uuid.uuid4().hex,'model_id':'sdxl','tool':d['tool'],'prompt':d['prompt'],'status':'completed','phase':'completed','progress':1,'duration_seconds':1,'params':{**d['params'],**v,'auto_test':True,'test_index':v['index'],'test_total':plan['count'],'test_label':'CFG '+str(v['cfg'])}})
  return {'ok':True,'count':plan['count']}
 if path=='/api/image/presets/user' and method=='POST':
  preset=ns['_normalize_user_image_preset'](d,d.get('id'));old=next((p for p in state['presets'] if p['id']==preset['id']),None)
  if not d.get('id') and old:preset['id']+='-copy'
  state['presets']=[p for p in state['presets'] if p['id']!=preset['id']]+[preset];state['writes']+=1
  return {'ok':True,'preset':preset,'presets':copy.deepcopy(state['presets'])}
 if path.startswith('/api/image/presets/user/'):
  id=path.split('/')[5]
  if path.endswith('/duplicate'):
   p=copy.deepcopy(next(p for p in state['presets'] if p['id']==id));p['id']+='-copy';p['name']+=' Copy';state['presets'].append(p);state['writes']+=1
   return {'ok':True,'preset':p,'presets':copy.deepcopy(state['presets'])}
  if method=='DELETE':state['presets']=[p for p in state['presets'] if p['id']!=id];state['writes']+=1;return {'ok':True,'presets':copy.deepcopy(state['presets'])}
 if path=='/api/model-hub/status':return {'ok':True,'models':[model],'settings':{},'sdxl':{'ready':True},'identity':{},'accounts':{},'jobs':[],'catalog':{},'checkpoints':checkpoint,'loras':loras,'vaes':[],'paths':{},'local_catalog':{'checkpoint':[],'lora':[],'sources':[]}}
 if path=='/api/model-hub/local':return {'catalog':{'checkpoint':[],'lora':[],'sources':[]}}
 if path=='/api/setup':return {'models':[model],'settings':{},'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
 if path=='/api/account':return {'username':'Test'}
 if path=='/api/training/bootstrap':return {'runtime':{},'datasets':[],'loras':[],'full_models':[],'full_unets':[],'jobs':[]}
 if path=='/api/identity/bootstrap':return {'runtime':{},'models':{},'jobs':[],'queue':{},'loras':loras,'checkpoints':checkpoint}
 if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{}}
 return {}
async def bridge(path,method='GET',body=None):
 try:
  d=await asyncio.to_thread(mock,path,method,body)
  return {'status':200,'json':d}
 except Exception as e:return {'status':400,'json':{'error':str(e)}}
raw=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
css=[ROOT/x['href'].split('?',1)[0].lstrip('/') for x in raw.select('link[rel=stylesheet]')]
scripts=[ROOT/x['src'].split('?',1)[0].lstrip('/') for x in raw.select('script[src]')]
for el in raw.find_all(['script','link']):el.decompose()
for el in raw.select('img[src]'):
 f=ROOT/el['src'].split('?',1)[0].lstrip('/')
 if f.is_file():el['src']='data:image/png;base64,'+base64.b64encode(f.read_bytes()).decode()
raw.head.append(raw.new_tag('base',href='http://ui.local/'))
TRANSPORT=r'''()=>{
 const st={'zetalvx.ui.language':'it'};window.__storage=st;
 for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{value:{getItem:k=>st[k]??null,setItem:(k,v)=>st[k]=String(v),removeItem:k=>delete st[k]}});
 window.fetch=async(u,o={})=>{const signal=o.signal;if(signal?.aborted)throw new DOMException('Aborted','AbortError');const r=await window._fixture(String(u),o.method||'GET',o.body||null);if(signal?.aborted)throw new DOMException('Aborted','AbortError');return new Response(JSON.stringify(r.json),{status:r.status,headers:{'Content-Type':'application/json'}});};
}'''
def boot(page):
 page.goto('about:blank');page.set_content(str(raw));page.evaluate(TRANSPORT)
 for f in css:page.add_style_tag(content=f.read_text())
 for f in scripts:page.add_script_tag(content=f.read_text())
 page.wait_for_function('S.project?.id&&window.CreatorLab');page.wait_for_timeout(450)
def check(name,condition,detail=None):
 print(('PASS ' if condition else 'FAIL ')+name,flush=True);checks.append({'name':name,'passed':bool(condition),'detail':detail});assert condition,(name,detail)
def view(name):page.evaluate('(name)=>showView(name)',name);page.wait_for_timeout(120)
def click(id):page.locator('#'+id).click();page.wait_for_timeout(100)
def fill(id,value):page.locator('#'+id).fill(str(value));page.locator('#'+id).dispatch_event('change');page.wait_for_timeout(60)
def select(id,value):page.locator('#'+id).select_option(value);page.wait_for_timeout(120)
def checked(id,value=True):page.locator('#'+id).set_checked(value);page.wait_for_timeout(60)
def open_panel(id):page.locator('#'+id).evaluate('el=>el.open=true');page.wait_for_timeout(120)

old_mock=mock
update_fixture={'status':None,'starts':[],'imports':0,'reads':0}
def mock(path,method='GET',data=None):
 from urllib.parse import urlsplit
 p=urlsplit(path).path
 if p.startswith('/api/app-updates'):
  d=json.loads(data) if isinstance(data,str) and data else data or {}
  if p=='/api/app-updates':
   update_fixture['reads']+=1
   return {'ok':True,'version':'0.1.0.29','available':True,'csrf':'update-token','update':copy.deepcopy(update_fixture['status'])}
  if p.endswith('/import'):
   update_fixture['imports']+=1
   update_fixture['status']={'id':'d'*32,'status':'ready','version':'0.1.0.29','platform':'linux','sha256':'e'*64,'files':300,'extracted_bytes':6000000,'signature_verified':False}
   return {'ok':True,'update':copy.deepcopy(update_fixture['status'])}
  if p.endswith('/start'):
   update_fixture['starts'].append(d)
   update_fixture['status']['status']='running'
   return {'ok':True,'update':copy.deepcopy(update_fixture['status'])}
  if method=='DELETE':
   update_fixture['status']['status']='discarded';return {'ok':True,'update':copy.deepcopy(update_fixture['status'])}
 return old_mock(path,method,data)
TRANSPORT=r"""initial=>{
 const st={'zetalvx.ui.language':'it',...initial};window.__storage=st;
 for(const name of ['localStorage','sessionStorage'])Object.defineProperty(window,name,{value:{getItem:k=>st[k]??null,setItem:(k,v)=>st[k]=String(v),removeItem:k=>delete st[k]}});
 window.fetch=async(u,o={})=>{
  const signal=o.signal;if(signal?.aborted)throw new DOMException('Aborted','AbortError');let body=o.body||null;
  if(body instanceof FormData){const obj={};for(const [key,value] of body.entries())obj[key]=value instanceof File?value.name:value;body=JSON.stringify(obj);}
  const r=await window._fixture(String(u),o.method||'GET',body);if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  return new Response(JSON.stringify(r.json),{status:r.status,headers:{'Content-Type':'application/json'}});
 };
}"""
def boot28(page,storage=None):
 page.goto('about:blank');page.set_content(str(raw));page.evaluate(TRANSPORT,storage or {})
 for f in css:page.add_style_tag(content=f.read_text())
 for f in scripts:page.add_script_tag(content=f.read_text())
 page.wait_for_function('S.project?.id&&window.CreatorLab');page.wait_for_timeout(400)
def values():return page.evaluate("['prompt','negativePrompt','steps','cfg','seed','width','height','batch','scheduler','strength'].map(id=>document.getElementById(id)?.value)")
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width,height,mobile in [(390,844,True),(320,740,True),(1024,900,False),(1440,1000,False)]:
   reset();update_fixture.update(status=None,starts=[],imports=0,reads=0)
   state['project']['artifacts']=[{**asset,'id':str(i)*32} for i in range(1,8)]
   state['project']['state']['active_artifact_id']='1'*32
   ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile,locale='it-IT')
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.expose_function('_fixture',bridge);boot28(page)
   prefix=f'{width}: '
   view('media-tools')
   check(prefix+'both media tools closed',not page.locator('#videoPickerPanel').evaluate('e=>e.open') and not page.locator('#imageToolsPanel').evaluate('e=>e.open'))
   check(prefix+'image tool controls hidden',not page.locator('#mtRunBtn').is_visible())
   page.locator('#imageToolsPanel>summary').click();page.wait_for_timeout(100)
   check(prefix+'image tool opens',page.locator('#mtRunBtn').is_visible())
   select('mtOperation','rotate_image');page.locator('#imageToolsPanel>summary').click();page.locator('#imageToolsPanel>summary').click()
   check(prefix+'closing does not reset image operation',page.locator('#mtOperation').input_value()=='rotate_image')
   view('image');open_panel('workflowPresetSuite')
   check(prefix+'simple hides comparison and manual',not page.locator('#imageTestPanel').is_visible() and not page.locator('#seed').is_visible())
   check(prefix+'simple hides preset authoring tabs',not page.locator('#presetTabSave').is_visible() and not page.locator('#presetTabManage').is_visible())
   check(prefix+'simple retains preset application',page.locator('#presetChoice').is_visible() and page.locator('#presetApply').is_visible())
   check(prefix+'simple explanation present','Semplice:' in page.locator('#imageModeHelp').inner_text())
   page.evaluate("document.querySelector('#seed').value='8123';document.querySelector('#cfg').value='6.3';document.querySelector('#steps').value='39';document.querySelector('#prompt').value='A car under soft light'")
   before=values();click('imageModeAdvancedBtn')
   check(prefix+'advanced switch keeps all values',values()==before)
   open_panel('workflowPresetSuite');check(prefix+'advanced authoring tabs visible',page.locator('#presetTabSave').is_visible() and page.locator('#presetTabManage').is_visible())
   check(prefix+'advanced compare panel visible',page.locator('#imageTestPanel').is_visible())
   click('presetTabSave');fill('presetSaveName','Unfinished preset')
   click('imageModeSimpleBtn');open_panel('workflowPresetSuite')
   check(prefix+'simple selects use pane after Save',page.locator('#presetPaneUse').is_visible() and not page.locator('#presetPaneSave').is_visible())
   check(prefix+'mode changes never reset prompt or parameters',values()==before)
   click('openAdvancedPresets');check(prefix+'shortcut opens Advanced Save',page.evaluate("S.imageUiMode==='advanced'") and page.locator('#presetPaneSave').is_visible())
   check(prefix+'unfinished preset name retained',page.locator('#presetSaveName').input_value()=='Unfinished preset')
   page.evaluate("document.querySelector('#workflowPresetSuite').open=false")
   dims=page.evaluate("(()=>{let layout=document.querySelector('#imageCreatorLayout').getBoundingClientRect(),out=document.querySelector('#imageOutputs').getBoundingClientRect(),history=document.querySelector('#imageHistoryGrid').getBoundingClientRect();return {lw:layout.width,ow:out.width,bottom:layout.bottom,top:out.top,hw:history.width}})()")
   check(prefix+'queue/history take full layout width',abs(dims['lw']-dims['ow'])<2,dims)
   check(prefix+'outputs below both columns',dims['top']>=dims['bottom'],dims)
   check(prefix+'outputs not inside settings',page.locator('#imageControlsColumn #liveQueue').count()==0 and page.locator('#imageControlsColumn #imageHistoryGrid').count()==0)
   fit=page.locator('#imageHistoryGrid .asset-card').evaluate_all("cards=>cards.every(card=>[...card.querySelectorAll('.asset-actions>*')].every(b=>b.getBoundingClientRect().right<=card.getBoundingClientRect().right&&b.getBoundingClientRect().left>=card.getBoundingClientRect().left))")
   check(prefix+'history buttons stay inside each card',fit)
   if width>1100:
    a=page.locator('#imagePreviewColumn').bounding_box();b=page.locator('#imageControlsColumn').bounding_box();check(prefix+'default preview on right',a['x']>b['x'])
    beforewidth=page.locator('#imageOutputs').bounding_box()['width'];click('imageLayoutSwapBtn')
    a=page.locator('#imagePreviewColumn').bounding_box();b=page.locator('#imageControlsColumn').bounding_box();check(prefix+'swap moves preview left',a['x']<b['x'])
    check(prefix+'history width unaffected by swap',abs(page.locator('#imageOutputs').bounding_box()['width']-beforewidth)<1)
    check(prefix+'swap keeps prompt and values',values()==before)
    columns=page.locator('#imageHistoryGrid').evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ').length")
    check(prefix+'desktop history uses more than two columns',columns>=3,columns)
    page.locator('.workspace').evaluate('el=>el.scrollTop=0');page.screenshot(path=str(OUT/'desktop-preview-right.png'))
    page.locator('#imageOutputs').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'desktop-history-fullwidth.png'))
    storage=page.evaluate('window.__storage');boot28(page,storage);view('image')
    check(prefix+'side restored after reload',not page.locator('#imageCreatorLayout').evaluate("e=>e.classList.contains('image-preview-right')"))
   else:check(prefix+'no desktop swap control on single-column view',not page.locator('#imageLayoutSwapBtn').is_visible())
   if mobile:
    page.evaluate("document.querySelector('#imageCreatorLayout').classList.add('image-preview-right')")
    a=page.locator('#imagePreviewColumn').bounding_box();b=page.locator('#imageControlsColumn').bounding_box()
    check(prefix+'stored desktop orientation does not affect mobile',b['y']<a['y'])
   for target in ['image','media-tools','settings','guide','jobs','training']:
    view(target);wh=page.evaluate('({w:innerWidth,s:document.documentElement.scrollWidth})');check(prefix+'no horizontal overflow '+target,wh['s']<=wh['w']+1,wh)
   view('settings');click('appUpdateRefresh')
   check(prefix+'import disabled until file chosen',page.locator('#appUpdateImport').is_disabled())
   page.locator('#appUpdateFile').set_input_files({'name':'release.zip','mimeType':'application/zip','buffer':b'fixture'});click('appUpdateImport')
   check(prefix+'import only validates, no execution',update_fixture['imports']==1 and not update_fixture['starts'])
   check(prefix+'default runtime reuse only',not page.locator('#appUpdateAllowRuntime').is_checked())
   check(prefix+'install requires both consent and password',page.locator('#appUpdateStart').is_disabled())
   checked('appUpdateTrust');check(prefix+'consent alone insufficient',page.locator('#appUpdateStart').is_disabled())
   fill('appUpdatePassword','fixture-password');check(prefix+'install enabled after confirmation',page.locator('#appUpdateStart').is_enabled())
   click('appUpdateStart');check(prefix+'exactly one update started',len(update_fixture['starts'])==1)
   check(prefix+'runtime reuse flag passed',update_fixture['starts'][0]['allow_new_runtime'] is False)
   check(prefix+'password field cleared',page.locator('#appUpdatePassword').input_value()=='')
   check(prefix+'maintenance banner visible',page.locator('#appUpdateBanner').is_visible())
   # Reload UI while update is still in progress: host state is recovered.
   boot28(page);view('settings');page.wait_for_timeout(150)
   check(prefix+'observation survives page reload',page.locator('#appUpdateBanner').is_visible() and len(update_fixture['starts'])==1)
   update_fixture['status'].update(status='completed',log_tail='Fixture update completed')
   click('appUpdateRefresh');check(prefix+'completion offers reload',page.locator('#appUpdateReload').is_visible() and not page.locator('#appUpdateBanner').is_visible())
   if width==390:
    page.locator('#appUpdatesPanel').screenshot(path=str(OUT/'mobile-update-complete.png'))
    view('media-tools');page.locator('#view-media-tools').screenshot(path=str(OUT/'mobile-tools-closed.png'))
    view('image');click('imageModeSimpleBtn');open_panel('workflowPresetSuite');page.locator('#workflowPresetSuite').screenshot(path=str(OUT/'mobile-simple-presets.png'))
   check(prefix+'no uncaught script errors',not errors,errors[:])
   page.close();ctx.close()
  browser.close()
except Exception as e:
 if page:
  try:page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  except Exception:pass
 errors.append(str(e));raise
finally:
 (OUT/'results.json').write_text(json.dumps({'version':'1.0.1','suite_origin':'workspace .28/.29','checks':checks,'count':len(checks),'passed':all(c['passed'] for c in checks) and not errors,'errors':errors,'transport':'simulated APIs; real Chromium and shipped HTML/CSS/JS','native_iphone':False,'native_windows':False},indent=2,ensure_ascii=False))
