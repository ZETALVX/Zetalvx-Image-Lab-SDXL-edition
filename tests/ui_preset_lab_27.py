"""Real .27 HTML/CSS/JS in Chromium; mocked transport/database, real pure planner.
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
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width,height,mobile in [(390,844,True),(320,740,True),(844,390,True),(1440,1000,False)]:
   reset();ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile,locale='it-IT')
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.expose_function('_fixture',bridge);boot(page)
   prefix=f'{width}: '
   check(prefix+'new header name',page.locator('.brand-copy b').inner_text()=='ZETALVX IMAGE LAB')
   logo=page.locator('.brand-logo-link').evaluate('(e)=>{const c=getComputedStyle(e);return {bg:c.backgroundColor,border:c.borderWidth,shadow:c.boxShadow}}')
   check(prefix+'transparent logo container',logo=={'bg':'rgba(0, 0, 0, 0)','border':'0px','shadow':'none'},logo)
   view('jobs');click('') if False else None;page.locator('.brand-home-link').click();check(prefix+'header logo stays inside Home',page.locator('#view-home').is_visible())
   for v in ['image','jobs','guide','models','training','identity','library']:
    view(v);dims=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');check(prefix+'no page overflow '+v,dims['scroll']<=dims['width']+1,dims)
   view('image');open_panel('workflowPresetSuite')
   check(prefix+'presets also in Simple',page.locator('#workflowPresetSuite').is_visible() and page.evaluate("S.imageUiMode==='simple'"))
   check(prefix+'retired menus hidden',not page.locator('#imageWorkModePanel').is_visible() and not page.locator('#guidedWorkflowPanel').is_visible())
   page.evaluate("window.PresetEngine.setMode('advanced')")
   fill('prompt','A photo of a car');fill('cfg',7) if page.locator('#cfg').is_visible() else page.evaluate("document.querySelector('#cfg').value='7'")
   before=page.evaluate("[document.querySelector('#steps').value,document.querySelector('#cfg').value,document.querySelector('#prompt').value]")
   select('presetChoice','technical:generate_cinematic');check(prefix+'selection does not apply',before==page.evaluate("[document.querySelector('#steps').value,document.querySelector('#cfg').value,document.querySelector('#prompt').value]"))
   click('presetApply');check(prefix+'built-in apply updates form',page.locator('#steps').input_value()=='40' and page.locator('#prompt').input_value()=='A photo of a car');check(prefix+'preset apply queues nothing',state['enqueues']==[])
   recipes=page.locator('#presetChoice option[value^="recipe:"]').evaluate_all('(es)=>es.map(e=>e.value)');check(prefix+'recipes share the catalog',bool(recipes))
   select('presetChoice',recipes[0]);select('imageWorkflowPromptMode','params_only');checked('imageWorkflowApplyParams',False)
   oldsteps=page.locator('#steps').input_value();click('presetApply');check(prefix+'recipe options survive Apply',page.evaluate("S.imageWorkflow.mode==='params_only'&&!S.imageWorkflow.applyParams"));check(prefix+'no parameter overwrite when unchecked',page.locator('#steps').input_value()==oldsteps)
   click('presetManual');check(prefix+'remove recipe no numeric reset',page.locator('#steps').input_value()==oldsteps and page.evaluate("!S.imageWorkflow.id"))
   if width==390:page.locator('#workflowPresetSuite').screenshot(path=str(OUT/'390-preset-use.png'))
   # Native inline save form (no browser prompt dialogs).
   click('presetTabSave');fill('presetSaveName','Mio preset');fill('presetSaveDescription','Example saved form')
   page.evaluate("document.querySelector('#seed').value='123';document.querySelector('#cfg').value='6.5';document.querySelector('#checkpointSelect').value='/fixtures/other.safetensors'")
   click('presetSaveNew');page.wait_for_function("S.boot.user_image_presets.length===1")
   saved=copy.deepcopy(state['presets'][0]);check(prefix+'save contains seed',saved['params']['seed']==123);check(prefix+'save no auto generation',state['enqueues']==[])
   if width==390:page.locator('#workflowPresetSuite').screenshot(path=str(OUT/'390-preset-save.png'))
   click('presetTabUse');select('presetChoice','user:'+saved['id']);page.evaluate("document.querySelector('#seed').value='999';document.querySelector('#cfg').value='8'");click('presetApply')
   check(prefix+'user preset roundtrip seed and CFG',page.locator('#seed').input_value()=='123' and page.locator('#cfg').input_value()=='6.5')
   check(prefix+'user preset restores checkpoint',page.locator('#checkpointSelect').input_value()=='/fixtures/other.safetensors')
   # Manage rename changes metadata, not live-form contents.
   click('presetTabManage');select('presetManageChoice',saved['id']);page.locator('#presetRename').evaluate('el=>el.closest("details").open=true');fill('presetRename','Rinominato <b>safe</b>');click('presetRenameSave')
   check(prefix+'rename preserves params',state['presets'][0]['params']==saved['params']);check(prefix+'user name remains plain text',page.locator('#presetManageChoice option').last.inner_text()=='Rinominato <b>safe</b>')
   n=state['writes'];page.once('dialog',lambda d:d.dismiss());click('presetReplace');check(prefix+'replace cancel no write',state['writes']==n)
   click('presetManageDuplicate');check(prefix+'duplicate saved preset',len(state['presets'])==2)
   page.once('dialog',lambda d:d.dismiss());click('presetManageDelete');check(prefix+'delete cancel preserves',len(state['presets'])==2)
   page.once('dialog',lambda d:d.accept());click('presetManageDelete');check(prefix+'delete removes only selected',len(state['presets'])==1 and state['project']['artifacts']==[asset])
   # Custom comparison: ranges are editable, accurate count, no implicit seed multiplication.
   open_panel('imageTestPanel');click('testModeCustom');checked('test_steps_enabled');fill('test_cfg_min',5);fill('test_cfg_max',9);fill('test_cfg_count',3);fill('test_steps_min',20);fill('test_steps_max',40);fill('test_steps_count',2)
   check(prefix+'six-count shown',page.locator('#imageAutoTestCount').inner_text()=='6 immagini')
   click('runImageAutoTestBtn');page.wait_for_selector('#imageTestPreview:not(.hidden)')
   check(prefix+'preview queues nothing',state['enqueues']==[]);check(prefix+'six preview rows',page.locator('#testPreviewRows tr').count()==6)
   seeds=page.locator('#testPreviewRows tr td:last-child').all_text_contents();check(prefix+'same seed across preview',len(set(seeds))==1)
   if width==390:page.locator('#imageTestPreview .modal-card').screenshot(path=str(OUT/'390-test-preview.png'))
   click('testPreviewCancel');check(prefix+'preview cancel no enqueue',state['enqueues']==[])
   fill('test_steps_count',24);check(prefix+'Cartesian over-limit blocks',page.locator('#runImageAutoTestBtn').is_disabled())
   fill('test_steps_count',2);fill('test_cfg_min',10);check(prefix+'reversed range blocks',page.locator('#runImageAutoTestBtn').is_disabled());fill('test_cfg_min',5)
   # Denoise only for source-based tasks, sample count multiplies.
   check(prefix+'denoise disabled in text-to-image',page.locator('#test_strength_enabled').is_disabled())
   page.evaluate("setTask('edit');S.sourceAsset='"+asset['id']+"';renderInputs()");page.wait_for_timeout(150);open_panel('imageTestPanel')
   checked('test_strength_enabled');fill('test_strength_min',.2);fill('test_strength_max',.5);fill('test_strength_count',2)
   check(prefix+'3 x 2 x 2 = 12 edits',page.locator('#imageAutoTestCount').inner_text()=='12 immagini')
   if width==390:page.locator('#imageTestPanel').screenshot(path=str(OUT/'390-custom-ranges.png'))
   click('runImageAutoTestBtn');page.wait_for_selector('#imageTestPreview:not(.hidden)');preview=copy.deepcopy(state['last_preview'])
   page.evaluate("document.querySelector('#testPreviewConfirm').click();document.querySelector('#testPreviewConfirm').click();")
   page.wait_for_function("document.querySelector('#view-jobs').classList.contains('active')");check(prefix+'double click queues once',len(state['enqueues'])==1)
   check(prefix+'enqueue uses frozen preview',state['enqueues'][0]==preview['request'])
   check(prefix+'one image per job',state['enqueues'][0]['params']['batch']==1)
   check(prefix+'job labels show test index',page.locator('#jobsList .job-test-label').count()==12)
   # Automatic mode still works; random seed is fixed at preview, not written to form.
   view('image');page.evaluate("setTask('generate');document.querySelector('#seed').value='-1'");open_panel('imageTestPanel');click('testModeAutomatic')
   select('imageAutoTestProfile','cfg_sweep');click('runImageAutoTestBtn');page.wait_for_selector('#imageTestPreview:not(.hidden)')
   check(prefix+'automatic profile three trials',page.locator('#testPreviewRows tr').count()==3)
   check(prefix+'random seed fixed in preview only',set(page.locator('#testPreviewRows tr td:last-child').all_text_contents())=={'123456'} and page.locator('#seed').input_value()=='-1')
   page.locator('#testPreviewClose').press('Escape');check(prefix+'Escape cancels preview without enqueue',len(state['enqueues'])==1 and not page.locator('#imageTestPreview').is_visible())
   click('testModeCustom');checked('test_cfg_enabled',False);checked('test_steps_enabled',False);checked('test_seed_enabled',True)
   fill('test_seed_min',1);fill('test_seed_max',3);fill('test_seed_count',3)
   check(prefix+'seed axis disables increment switch',page.locator('#imageAutoTestVarySeed').is_disabled())
   click('runImageAutoTestBtn');page.wait_for_selector('#imageTestPreview:not(.hidden)')
   check(prefix+'custom seed list exact',page.locator('#testPreviewRows tr td:last-child').all_text_contents()==['1','2','3']);click('testPreviewCancel')
   # Legacy and partial presets must not overwrite excluded fields.
   partial=copy.deepcopy(saved);partial['id']='partial';partial['name']='Technical scope';partial['preset_type']='technical';partial['includes']={'task':False,'model':False,'loras':False,'params':True,'style':False,'workflow':False,'technical_preset':False,'prompt':False};partial['params'].update(cfg=9,seed=555,checkpoint_override='/fixtures/other.safetensors')
   state['presets'].append(partial);page.evaluate("p=>{S.boot.user_image_presets.push(p);PresetEngine.refresh();}",partial)
   open_panel('workflowPresetSuite');click('presetTabUse');select('presetChoice','user:partial');page.evaluate("document.querySelector('#checkpointSelect').value='/fixtures/base.safetensors';document.querySelector('#prompt').value='Keep this prompt'")
   click('presetApply');check(prefix+'technical preset respects excluded prompt/checkpoint',page.locator('#prompt').input_value()=='Keep this prompt' and page.locator('#checkpointSelect').input_value()=='/fixtures/base.safetensors')
   check(prefix+'technical preset applies selected params/seed',page.locator('#cfg').input_value()=='9' and page.locator('#seed').input_value()=='555')
   modelonly=copy.deepcopy(partial);modelonly.update(id='modelonly',name='Model scope');modelonly['includes'].update(model=True,params=False)
   state['presets'].append(modelonly);page.evaluate("p=>{S.boot.user_image_presets.push(p);PresetEngine.refresh();}",modelonly);select('presetChoice','user:modelonly');page.evaluate("document.querySelector('#seed').value='323';document.querySelector('#steps').value='24';document.querySelector('#cfg').value='7.2'")
   click('presetApply');check(prefix+'model-only changes checkpoint without resetting numbers',page.locator('#checkpointSelect').input_value()=='/fixtures/other.safetensors' and page.locator('#seed').input_value()=='323' and page.locator('#steps').input_value()=='24' and page.locator('#cfg').input_value()=='7.2')
   legacy=copy.deepcopy(saved);legacy['id']='legacy';legacy['name']='Legacy without seed';legacy['params'].pop('seed',None)
   state['presets'].append(legacy);page.evaluate("p=>{S.boot.user_image_presets.push(p);PresetEngine.refresh();}",legacy);select('presetChoice','user:legacy');page.evaluate("document.querySelector('#seed').value='919'");click('presetApply');check(prefix+'legacy preset keeps current seed',page.locator('#seed').input_value()=='919')
   # Guide search and contextual navigation.
   view('guide');fill('guideSearch','minimo');check(prefix+'guide search finds comparisons',page.locator('#guide-tests').is_visible())
   fill('guideSearch','zzzz-no-topic');check(prefix+'guide no-results feedback',page.locator('#guideNoResults').is_visible());fill('guideSearch','')
   page.evaluate("ZI18n.setLanguage('en')");page.wait_for_timeout(150);check(prefix+'English guide fallback',page.locator('#guide-tests summary').inner_text()=='Compare variations: automatic or custom')
   page.evaluate("ZI18n.setLanguage('it')");view('image');open_panel('imageTestPanel');page.locator('[data-guide-topic=tests]').click();page.wait_for_timeout(200)
   check(prefix+'context help opens correct topic',page.locator('#view-guide').is_visible() and page.locator('#guide-tests').evaluate('el=>el.open'))
   if width==390:page.locator('#guide-tests').screenshot(path=str(OUT/'390-guide-tests.png'))
   check(prefix+'no uncaught JS errors',not errors,errors[:])
   page.close();ctx.close()
  browser.close()
except Exception as e:
 if page:
  try:page.screenshot(path=str(OUT/'failure.png'),full_page=True)
  except Exception:pass
 errors.append(str(e));raise
finally:
 (OUT/'results.json').write_text(json.dumps({'checks':checks,'count':len(checks),'passed':all(c['passed'] for c in checks) and not errors,'errors':errors,'transport':'simulated APIs; actual planner/normalizer; real Chromium/HTML/CSS/JS','native_iphone':False,'native_windows':False},indent=2,ensure_ascii=False))
