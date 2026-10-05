"""Real .33 HTML/CSS/JS in Chromium; mocked transport/database, real pure planner.
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
  for width,height,mobile in [(1440,1000,False),(390,844,True),(320,740,True)]:
   prefix=str(width)+' '
   reset();ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.expose_function('_fixture',bridge)
   boot28(page);view('image')
   check(prefix+'default right set',page.locator('#imageCreatorLayout').evaluate("e=>e.classList.contains('image-preview-right')"))
   if not mobile:
    a=page.locator('#imagePreviewColumn').bounding_box();b=page.locator('#imageControlsColumn').bounding_box();check(prefix+'desktop preview visually right',a['x']>b['x'])
    click('imageLayoutSwapBtn');check(prefix+'user can switch left',not page.locator('#imageCreatorLayout').evaluate("e=>e.classList.contains('image-preview-right')"));saved=page.evaluate('window.__storage');boot28(page,saved);view('image');check(prefix+'saved left preserved',not page.locator('#imageCreatorLayout').evaluate("e=>e.classList.contains('image-preview-right')"))
   before=values();view('settings')
   accents=[]
   for theme in ['forest','blue','violet','amber','rose','graphite']:
    page.locator('[data-theme="'+theme+'"]').click();page.wait_for_timeout(100)
    check(prefix+theme+' applied',page.evaluate('document.documentElement.dataset.uiTheme')==theme)
    accents.append(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent')"))
   check(prefix+'six distinct palettes',len(set(accents))==6,accents);check(prefix+'theme does not change generation',values()==before)
   saved=page.evaluate('window.__storage');boot28(page,saved);view('settings');check(prefix+'theme persisted',page.evaluate('document.documentElement.dataset.uiTheme')=='graphite')
   page.locator('[data-theme=blue]').click();view('library');page.wait_for_timeout(150)
   active=page.evaluate('S.activeAsset');requests_before=len(state['requests'])
   z=page.locator('#libraryGrid .image-zoom').first;check(prefix+'enlarge control present',z.is_visible());z.click();page.wait_for_timeout(80)
   check(prefix+'lightbox opened',page.locator('#imageViewer').is_visible());check(prefix+'zoom does not change active asset',page.evaluate('S.activeAsset')==active)
   check(prefix+'zoom not enqueue',len(state['enqueues'])==0)
   page.locator('#imageViewerImage').click(force=True);check(prefix+'image click keeps preview open',page.locator('#imageViewer').is_visible())
   page.keyboard.press('Escape');check(prefix+'Escape closes',not page.locator('#imageViewer').is_visible())
   z.click();click('imageViewerClose');check(prefix+'X closes',not page.locator('#imageViewer').is_visible())
   z.click();page.locator('#imageViewer').click(position={'x':3,'y':40});check(prefix+'backdrop closes',not page.locator('#imageViewer').is_visible())
   view('user-presets');before=values();orig=page.evaluate('JSON.stringify(IMAGE_PRESETS)')
   page.locator('[data-preset-key="technical:generate_clean"]').click();check(prefix+'built-in editable as own copy',page.locator('#pmEditor').is_visible() and not page.evaluate('CreatorPresetManager.read().id'))
   check(prefix+'choosing preset does not affect generation',values()==before)
   fill('pmName','Mobile custom '+str(width));fill('pm_cfg','6.5');fill('pm_steps','24');click('pmSave')
   check(prefix+'one personal preset saved',len(state['presets'])==1,state['presets'])
   check(prefix+'base presets unchanged',page.evaluate('JSON.stringify(IMAGE_PRESETS)')==orig)
   check(prefix+'save not apply or enqueue',values()==before and len(state['enqueues'])==0)
   click('pmUse');check(prefix+'use opens Create',page.locator('#view-image').is_visible());check(prefix+'new values applied',page.locator('#cfg').input_value()=='6.5' and page.locator('#steps').input_value()=='24')
   check(prefix+'excluded seed kept',page.locator('#seed').input_value()==before[4])
   view('user-presets');page.locator('[data-preset-key^="user:"]').first.click();fill('pm_cfg','8');click('pmUse');check(prefix+'unsaved changes cannot be applied',page.locator('#view-user-presets').is_visible() and page.locator('#cfg').input_value()=='6.5')
   click('pmSave');check(prefix+'update replaces not duplicates',len(state['presets'])==1 and state['presets'][0]['params']['cfg']==8)
   click('pmCopy');check(prefix+'save copy creates second',len(state['presets'])==2)
   click('pmDelete');check(prefix+'delete only own copy',len(state['presets'])==1 and page.evaluate('JSON.stringify(IMAGE_PRESETS)')==orig)
   page.locator('[data-preset-key^="recipe:"]').first.click();p=page.evaluate('CreatorPresetManager.read()');check(prefix+'recipe copy includes editable instructions',bool(p['prompt']) and not p['workflow']['id'])
   click('pmClose');view('image');fill('prompt','Snapshot prompt');view('user-presets');click('pmNew');check(prefix+'new from form includes prompt',page.locator('#pmPrompt').input_value()=='Snapshot prompt');click('pmClose')
   for lang in ['it','en','es','fr','de','pt','ru','zh','ja','ko','tr','ar']:
    page.evaluate('(l)=>ZI18n.setLanguage(l)',lang);page.wait_for_timeout(110)
    title=page.locator('#view-user-presets h2').inner_text();expected=page.evaluate("ZI18n.t('User presets')")
    check(prefix+'preset title translated '+lang,title==expected and (lang=='en' or title!='User presets'),title)
    wh=page.evaluate('({w:innerWidth,s:document.documentElement.scrollWidth})');check(prefix+'manager fits '+lang,wh['s']<=wh['w']+1,wh)
   page.evaluate("ZI18n.setLanguage('it')");page.wait_for_timeout(100)
   page.locator('[data-preset-key^="user:"]').first.click();page.wait_for_timeout(100)
   wh=page.evaluate('({w:innerWidth,s:document.documentElement.scrollWidth})');check(prefix+'editor no horizontal overflow',wh['s']<=wh['w']+1,wh)
   page.locator('.workspace').evaluate('e=>e.scrollTop=0');page.screenshot(path=str(OUT/(str(width)+'-preset-manager.png')))
   view('settings');page.locator('#appearanceSettings').scroll_into_view_if_needed();page.screenshot(path=str(OUT/(str(width)+'-themes.png')))
   view('library');page.locator('#libraryGrid .image-zoom').first.click();page.screenshot(path=str(OUT/(str(width)+'-viewer.png')));page.keyboard.press('Escape')
   check(prefix+'no unhandled script errors',not errors,errors[:]);page.close();ctx.close()
  browser.close()
except Exception as e:
 if page:
  try:page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  except Exception:pass
 errors.append(str(e));raise
finally:
 (OUT/'results.json').write_text(json.dumps({'version':'1.0.1','transport':'simulated APIs, real Chromium/HTML/CSS/JS','checks':checks,'errors':errors,'passed':sum(c['passed'] for c in checks)},ensure_ascii=False,indent=2))
