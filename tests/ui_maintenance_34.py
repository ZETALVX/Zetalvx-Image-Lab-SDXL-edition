"""Real .34 HTML/CSS/JS in Chromium; mocked transport/database, real pure planner.
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


base_mock=mock
removal={'starts':[],'challenges':0,'purge':False,'cancels':0}
def mock(path,method='GET',data=None):
 from urllib.parse import urlsplit
 p=urlsplit(path).path;d=json.loads(data) if isinstance(data,str) and data else data or {}
 if p=='/api/app-uninstall':return {'ok':True,'csrf':'remove-csrf','plan':{'home':'C:/Users/Test/AppData/Local/CreatorStudioSDXL','can_purge_data':True,'purge_data':False}}
 if p=='/api/app-uninstall/challenge':
  removal['challenges']+=1;removal['purge']=d['purge_data']
  return {'ok':True,'challenge':{'id':'f'*32,'word':'PINETA-12A3FF','expires_in':300},'plan':{'home':'C:/Users/Test/AppData/Local/CreatorStudioSDXL','can_purge_data':True,'purge_data':d['purge_data']}}
 if p=='/api/app-uninstall/cancel':
  removal['cancels']+=1;return {'ok':True}
 if p=='/api/app-uninstall/start':
  removal['starts'].append(d)
  return {'ok':True,'uninstall':{'status':'starting','data_preserved':not d['purge_data'],'home':'C:/Users/Test/AppData/Local/CreatorStudioSDXL','report':'C:/Temp/zetalvx-uninstall/result.json'}}
 return base_mock(path,method,data)

def card_bounds(selector):
 return page.locator(selector).evaluate_all("""cards=>cards.map(card=>{
  const c=card.getBoundingClientRect();return {w:c.width,overflow:card.scrollWidth>card.clientWidth+1,actions:[...card.querySelectorAll('.asset-actions>*')].map(b=>{const r=b.getBoundingClientRect();return {fits:r.left>=c.left-1&&r.right<=c.right+1&&r.bottom<=c.bottom+1,w:r.width,h:r.height}})};
 })""")
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width,height,mobile in [(1920,1080,False),(1440,900,False),(1366,768,False),(1280,720,False),(1024,768,False),(390,844,True),(320,740,True)]:
   prefix=str(width)+' ';reset();removal['starts']=[];removal['cancels']=0
   state['project']['artifacts']=[{**asset,'id':str(i).zfill(32),'metadata':{'model_id':'sdxl'},'created_at':'2026-09-26 21:45:20'} for i in range(3)]
   ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.expose_function('_fixture',bridge)
   boot28(page)
   # All three occurrences use the same card template; Home was omitted by the old CSS.
   for lang in ['en','it','de','ru','ja','ar']:
    page.evaluate('(l)=>ZI18n.setLanguage(l)',lang);page.wait_for_timeout(90)
    for v,selector in [('home','#homeRecent .asset-card'),('library','#libraryGrid .asset-card'),('image','#imageHistoryGrid .asset-card')]:
     view(v);cards=card_bounds(selector);check(prefix+lang+' '+v+' actions fit',bool(cards) and all(not c['overflow'] and all(a['fits'] and a['w']>25 for a in c['actions']) for c in cards),cards)
   page.evaluate("ZI18n.setLanguage('en')");view('image');before=values()
   page.locator('#imageModeAdvancedBtn').click();page.wait_for_timeout(80)
   if width>1100:
    panel=page.locator('#imageStartPanel').bounding_box();cfg=page.locator('#imageControlsColumn').bounding_box();prev=page.locator('#mainPreview').bounding_box()
    check(prefix+'compact top panel',panel['height']<145,panel)
    check(prefix+'prompt and image visible without scroll',cfg['y']<290 and prev['y']<290,{'cfg':cfg,'preview':prev})
    check(prefix+'image fits first viewport',prev['y']+prev['height']<=height+12,prev)
    check(prefix+'preview right retained',prev['x']>cfg['x'])
    page.locator('.prompt-inspect>summary').click();check(prefix+'mode explanation still reachable',page.locator('#imageModeHelp').is_visible())
    page.locator('.prompt-inspect>summary').click();click('imageLayoutSwapBtn')
    check(prefix+'swap still works',page.locator('#mainPreview').bounding_box()['x']<page.locator('#imageControlsColumn').bounding_box()['x']);click('imageLayoutSwapBtn')
   else:check(prefix+'layout toggle hidden on narrow screen',not page.locator('#imageLayoutSwapBtn').is_visible())
   check(prefix+'layout did not change generation values',values()==before)
   page.evaluate("S.activeAsset=S.project.artifacts[0].id;renderActivePreview()")
   page.wait_for_function("document.querySelector('#mainPreview img')?.complete")
   if width>1100:
    ib=page.locator('#mainPreview img').bounding_box();stage=page.locator('#mainPreview').bounding_box()
    check(prefix+'loaded image fits stage without cropping',ib is not None and ib['x']>=stage['x']-1 and ib['x']+ib['width']<=stage['x']+stage['width']+1 and ib['y']>=stage['y']-1 and ib['y']+ib['height']<=stage['y']+stage['height']+1,ib)
   page.screenshot(path=str(OUT/(str(width)+'-create.png')))
   view('home');page.screenshot(path=str(OUT/(str(width)+'-home.png')))
   # Explicit uninstall review, cancel, password mismatch and a single submit.
   view('settings');open_panel('appUninstallPanel');check(prefix+'keep data default',not page.locator('#uninstallPurge').is_checked())
   click('uninstallPrepare');check(prefix+'word review visible',page.locator('#uninstallModal').is_visible());check(prefix+'opening review cannot start',not removal['starts'])
   check(prefix+'confirm initially disabled',page.locator('#uninstallConfirm').is_disabled())
   fill('uninstallWordInput','PINETA-12A3FF');fill('uninstallPassword','pass12345');fill('uninstallPasswordRepeat','wrong');checked('uninstallUnderstand')
   check(prefix+'password mismatch cannot submit',page.locator('#uninstallConfirm').is_disabled())
   click('uninstallClose');check(prefix+'cancel closes and clears',not page.locator('#uninstallModal').is_visible() and page.locator('#uninstallPassword').input_value()=='' and not removal['starts'])
   check(prefix+'cancel invalidation requested',removal['cancels']==1)
   checked('uninstallPurge');click('uninstallPrepare');check(prefix+'purge review explicit','PERMANENT REMOVAL' in page.locator('#uninstallWarning').inner_text())
   fill('uninstallWordInput','PINETA-12A3FF');fill('uninstallPassword','pass12345');fill('uninstallPasswordRepeat','pass12345');checked('uninstallUnderstand')
   page.screenshot(path=str(OUT/(str(width)+'-uninstall-review.png')))
   page.locator('#uninstallConfirm').evaluate('e=>{e.click();e.click();}');page.wait_for_timeout(200)
   check(prefix+'only one uninstall accepted',len(removal['starts'])==1,removal['starts'])
   check(prefix+'two password entries sent',removal['starts'][0]['password']=='pass12345' and removal['starts'][0]['password_repeat']=='pass12345')
   check(prefix+'word and purge bound',removal['starts'][0]['word']=='PINETA-12A3FF' and removal['starts'][0]['purge_data'] is True)
   check(prefix+'passwords cleared',page.locator('#uninstallPassword').input_value()=='' and page.locator('#uninstallPasswordRepeat').input_value()=='')
   check(prefix+'accepted banner not fake success',page.locator('#uninstallBanner').is_visible() and 'does not confirm successful removal' in page.locator('#uninstallBanner').inner_text())
   check(prefix+'no console JS errors',not errors,errors[:]);page.close();ctx.close()
  browser.close()
except Exception as e:
 if page:
  try:page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  except Exception:pass
 errors.append(str(e));raise
finally:
 (OUT/'results.json').write_text(json.dumps({'version':'1.0.1','transport':'real Chromium, mocked HTTP API; no actual uninstall through browser','checks':checks,'errors':errors,'passed':sum(c['passed'] for c in checks)},ensure_ascii=False,indent=2))
