"""Browser regression for SDXL 0.1.0.26.
Actual application HTML/CSS/JS and actual VideoPicker + FFmpeg. Other APIs use fixtures.
Does NOT replace native iPhone/Safari, Flask/auth, Windows or GPU acceptance tests.
Requires dev-only playwright, beautifulsoup4, Pillow, Chromium and FFmpeg.
"""
from pathlib import Path
import argparse, asyncio, base64, copy, hashlib, io, json, mimetypes, subprocess, sys, tempfile, threading, time
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.video_picker import VideoPicker
from core.task_adapters import support_matrix
from core.model_policy import catalog
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
OUT=Path(args.output).resolve();OUT.mkdir(parents=True,exist_ok=True)
tmp=tempfile.TemporaryDirectory();DATA=Path(tmp.name);picker=VideoPicker(DATA/'video')
clip=DATA/'sample.mp4'
subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=320x180:rate=10:duration=2','-pix_fmt','yuv420p','-c:v','libx264','-threads','1','-y',str(clip)],check=True)
buf=io.BytesIO();Image.new('RGB',(240,160),'#456a59').save(buf,'PNG');image_bytes=buf.getvalue()
asset_url='data:image/png;base64,'+base64.b64encode(image_bytes).decode()
projects=[{'id':c*32,'name':n,'description':'','sort_order':i*10,'trashed':0,'created_at':'2026-09-01','state':{},'jobs':[],'messages':[],
           'artifacts':[{'id':str(i+1)*32,'type':'image','url':asset_url,'created_at':'2026-09-01','metadata':{'model_name':'SDXL','tool':'generate_image'}}]}
          for i,(c,n) in enumerate([('a','TEST 1'),('b','Test 2'),('c','Un progetto con un nome più lungo')])]
model=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
model['config'].update(checkpoint='/test/models/SDXL/base.safetensors',checkpoint_roots='/test/models/SDXL',lora_root='/test/models/loras/SDXL')
model['validation']={'ready':True,'fields':[],'missing':[]};model['task_support']=support_matrix(model);model['status']='Ready'
checkpoints=[{'name':'sd_xl_base_1.0.safetensors','path':model['config']['checkpoint']}]
local={'checkpoint':[{'name':'sd_xl_base_1.0.safetensors','path':model['config']['checkpoint'],'format':'safetensors','size_bytes':6*1024**3,'present':True,'active':True}],
       'lora':[{'name':'PerfectEyesXL.safetensors','path':'/test/models/loras/SDXL/PerfectEyesXL.safetensors','format':'safetensors','size_bytes':200*1024**2,'present':True}], 'sources':[]}
state={'delay':{},'preview_delay':0,'saves':[],'requests':[],'cleanup':0}
lock=threading.Lock();checks=[];errors=[]
def project(pid):return next(p for p in projects if p['id']==pid)
def api(path,method,data,files):
 state['requests'].append([method,path])
 if path=='/api/session/tokens':return {'tokens':{'vision':'test','model-hub':'test'}}
 if path=='/api/bootstrap':return {'projects':copy.deepcopy(projects),'models':[model],'recipes':[],'loras':[],'checkpoints':checkpoints,'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
 if path.startswith('/api/projects/') and path.count('/')==3:
  pid=path.split('/')[-1];snapshot=copy.deepcopy(project(pid))
  with lock:delay=state['delay'].pop(pid,0)
  if delay:time.sleep(delay)
  return {'project':snapshot}
 if path=='/api/model-hub/status':return {'ok':True,'models':[model],'settings':{},'sdxl':{'ready':True},'identity':{},'accounts':{},'jobs':[],'catalog':catalog(),'paths':{'checkpoint':'/test/models/SDXL','lora':'/test/models/loras/SDXL'},'checkpoints':checkpoints,'loras':[],'vaes':[],'local_catalog':local}
 if path=='/api/model-hub/local':return {'catalog':local}
 if path=='/api/setup':return {'settings':{},'models':[model],'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
 if path=='/api/account':return {'username':'Demo'}
 if path=='/api/identity/bootstrap':return {'runtime':{},'models':{},'jobs':[],'queue':{},'loras':[],'checkpoints':checkpoints}
 if path=='/api/training/bootstrap':return {'runtime':{},'datasets':[],'loras':[],'full_models':[],'full_unets':[],'jobs':[],'default_sdxl':model['config']['checkpoint']}
 if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{}}
 if path=='/api/jobs/cleanup':state['cleanup']+=1;return {'cancelled':0}
 if path=='/api/image-tools/video-picker' and method=='POST':return {'video':picker.upload(io.BytesIO(files['file'][1]),files['file'][0],data['project_id'],'owner')}
 if path.startswith('/api/image-tools/video-picker/'):
  parts=path.split('/');vid=parts[4]
  if len(parts)==5 and method=='DELETE':picker.discard(vid,'owner');return {'ok':True}
  if len(parts)==7 and parts[5]=='preview':
   src,meta,info=picker.selected(vid,'owner',parts[6]);return ('image/png',src.read_bytes())
  if parts[5]=='preview':
   if state['preview_delay']:time.sleep(state['preview_delay'])
   return {'preview':picker.preview(vid,'owner',data.get('mode','timestamp'),data.get('timestamp',0))}
  if parts[5]=='save':
   src,meta,info=picker.selected(vid,'owner',data['preview_id']);saved=src.read_bytes()
   state['saves'].append({'preview_id':data['preview_id'],'info':info,'sha256':hashlib.sha256(saved).hexdigest()})
   p=project(meta['project_id']);p['artifacts'].append({'id':str(len(p['artifacts'])+5)*32,'type':'image','url':'data:image/png;base64,'+base64.b64encode(saved).decode(),'created_at':'2026-09-26','metadata':{'source':'media_tools','operation':'extract_frame'}})
   return {'ok':True,'artifact':p['artifacts'][-1]}
 return {}
# Network-free test transport. Browser HTTP requests are prohibited in the test
# container. Real app fetches cross a fixture bridge; real FFmpeg PNG bytes are
# decoded by Chromium as data URLs. This does NOT test Flask routing/auth/HTTP.
async def bridge(path,method='GET',body=None):
 data={};files={}
 if isinstance(body,dict) and body.get('__multipart'):
  for name,item in body['entries']:
   if isinstance(item,dict) and 'base64' in item:files[name]=(item['name'],base64.b64decode(item['base64']))
   else:data[name]=item
 elif isinstance(body,str) and body:data=json.loads(body)
 try:
  result=await asyncio.to_thread(api,urlsplit(path).path,method,data,files)
  if isinstance(result,tuple):return {'status':200,'mime':result[0],'base64':base64.b64encode(result[1]).decode()}
  return {'status':200,'json':result}
 except Exception as e:return {'status':400,'json':{'error':str(e)}}
raw=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
css=[ROOT/x['href'].split('?',1)[0].lstrip('/') for x in raw.select('link[rel=stylesheet]')]
scripts=[ROOT/x['src'].split('?',1)[0].lstrip('/') for x in raw.select('script[src]')]
for x in raw.find_all(['script','link']):x.decompose()
for x in raw.select('img[src]'):
 f=ROOT/x['src'].lstrip('/')
 if f.is_file():x['src']='data:'+str(mimetypes.guess_type(f)[0])+';base64,'+base64.b64encode(f.read_bytes()).decode()
raw.head.append(raw.new_tag('base',href='http://ui.local/'))
TRANSPORT=r"""initial=>{
 const st={...initial};window.__testStorage=st;
 Object.defineProperty(window,'localStorage',{value:{getItem:k=>st[k]??null,setItem:(k,v)=>st[k]=String(v),removeItem:k=>delete st[k]}});
 window.fetch=async(u,o={})=>{
  const signal=o.signal;if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  let body=o.body??null;
  if(body instanceof FormData){const entries=[];for(const [key,value] of body.entries()){
   if(value instanceof Blob){const bytes=new Uint8Array(await value.arrayBuffer());let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
    entries.push([key,{name:value.name,base64:btoa(binary)}]);}
   else entries.push([key,value]);}body={__multipart:true,entries};}
  const r=await window._fixtureApi(String(u),o.method||'GET',body);
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  const bytes=r.base64?Uint8Array.from(atob(r.base64),c=>c.charCodeAt(0)):JSON.stringify(r.json);
  return new Response(bytes,{status:r.status,headers:{'Content-Type':r.mime||'application/json'}});
 };
 const nativeSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
 Object.defineProperty(HTMLImageElement.prototype,'src',{
  configurable:true,get(){return this.__testEndpoint||nativeSrc.get.call(this)},
  set(value){const img=this;if(String(value).startsWith('/api/')){
   img.__testEndpoint=String(value);window._fixtureApi(String(value),'GET',null).then(r=>{
    if(img.__testEndpoint!==String(value))return;
    if(r.base64)nativeSrc.set.call(img,'data:'+r.mime+';base64,'+r.base64);else img.dispatchEvent(new Event('error'));
   });
  }else{img.__testEndpoint=null;nativeSrc.set.call(img,value);}}
 });
}"""
def boot_page(page,initial=None):
 page.goto('about:blank');page.set_content(str(raw));page.evaluate(TRANSPORT,initial or {})
 for f in css:page.add_style_tag(content=f.read_text())
 for f in scripts:page.add_script_tag(content=f.read_text())
 page.wait_for_function('S.project?.id');page.wait_for_timeout(400)
def check(name,ok,detail=None):
 checks.append({'name':name,'passed':bool(ok),'detail':detail});assert ok,(name,detail)
def wait_project(page,pid):page.wait_for_function('pid=>S.project?.id===pid&&!pendingProjectId',arg=pid)
def view(page,name):page.evaluate('(v)=>showView(v)',name);page.wait_for_timeout(120)
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for width,height,mobile in [(390,844,True),(320,700,True),(844,390,True),(1440,1000,False)]:
   ctx=browser.new_context(viewport={'width':width,'height':height},is_mobile=mobile,has_touch=mobile,device_scale_factor=1,locale='it-IT')
   page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.expose_function('_fixtureApi',bridge);boot_page(page)
   check(f'{width} viewport fit', 'viewport-fit=cover' in page.locator('meta[name=viewport]').get_attribute('content'))
   for name in ['projects','library','models','jobs','media-tools','training','image','identity']:
    view(page,name)
    overflow=page.evaluate('({w:innerWidth,s:document.documentElement.scrollWidth})')
    check(f'{width} no page overflow {name}',overflow['s']<=overflow['w']+1,overflow)
   view(page,'models');page.wait_for_selector('.local-model-row')
   order=page.evaluate("(()=>{const a=document.querySelector('#hubSdxlPaths'),b=document.querySelector('#localSourcesPanel'),c=document.querySelector('[data-local-kind=checkpoint]'),d=document.querySelector('[data-local-kind=lora]');return [a.compareDocumentPosition(b)&4,b.compareDocumentPosition(c)&4,c.compareDocumentPosition(d)&4]})()")
   check(f'{width} model paths above lists',all(order))
   check(f'{width} no duplicate extraction panel',page.locator('#frameExtractPanel').count()==0)
   if mobile:
    page.evaluate("document.documentElement.style.setProperty('--ui-safe-bottom','34px')")
    rect=page.locator('.mobile-dock').bounding_box();check(f'{width} dock clears simulated 34px home indicator',rect['y']+rect['height']<=height-44+.5,rect)
   view(page,'jobs');bg=page.locator('#cleanupJobs').evaluate('(e)=>getComputedStyle(e).backgroundColor')
   check(f'{width} cleanup uses dark danger component',bg=='rgb(48, 31, 37)',bg)
   page.once('dialog',lambda d:d.dismiss());page.locator('#cleanupJobs').click();check(f'{width} cleanup cancel sends no request',state['cleanup']==0)
   # Header/action geometry and a training parameter grid with two-line labels.
   view(page,'training');page.evaluate("document.querySelector('#trainingPageDataset').hidden=true;document.querySelector('#trainingPageTrain').hidden=false;document.querySelector('#dsTrainName').textContent='Demo dataset'")
   boxes=[page.locator('#'+x).bounding_box() for x in ['trainingMode','trainingProfile','trainingResolution','trainingSteps']]
   check(f'{width} training controls equal height',len({round(x['height']) for x in boxes})==1,boxes)
   if width>=359:check(f'{width} first training row aligned',abs(boxes[0]['y']-boxes[1]['y'])<1,boxes[:2])
   # Inspect advanced training controls and image-model/ratio alignment too.
   page.locator('.training-advanced').evaluate('e=>e.open=true')
   advanced=[page.locator('#'+x).bounding_box() for x in ['trainingSaveEvery','trainingLR','trainingRank','trainingAlpha','trainingGradAccum','trainingSeed']]
   check(f'{width} advanced training controls equal height',len({round(x['height']) for x in advanced})==1,advanced)
   if width>=359:check(f'{width} advanced training row aligned',abs(advanced[4]['y']-advanced[5]['y'])<1,advanced[4:])
   view(page,'image')
   model_box=page.locator('#modelPickerButton').bounding_box();ratio_box=page.locator('#ratio').bounding_box()
   check(f'{width} model picker and ratio equal height',abs(model_box['height']-ratio_box['height'])<1,[model_box,ratio_box])
   view(page,'training')
   if width in (390,1440):
    for name in ['training','models','jobs','projects','media-tools']:
     if name!='training':view(page,name)
     page.evaluate('()=>{window.scrollTo(0,0);document.querySelector(".workspace").scrollTop=0}');page.screenshot(path=str(OUT/f'{width}-{name}.png'),full_page=True)
   if width==390:
    # Native More toggle keeps ARIA state and does not require a second touch.
    page.locator('#mobileMoreToggle').tap();page.wait_for_timeout(80)
    check('More opens on one touch',page.locator('#mobileMoreMenu').is_visible() and page.locator('#mobileMoreToggle').get_attribute('aria-expanded')=='true')
    page.locator('#mobileMoreClose').tap();page.wait_for_timeout(80)
    check('More closes and restores expanded state',not page.locator('#mobileMoreMenu').is_visible() and page.locator('#mobileMoreToggle').get_attribute('aria-expanded')=='false')
    # Native tap on card padding selects and opens the library once.
    view(page,'projects');target=page.locator('[data-open-project="'+projects[1]['id']+'"]');target.tap(position={'x':14,'y':80});wait_project(page,projects[1]['id'])
    check('single touch opens project and library',page.locator('#view-library').evaluate("e=>e.classList.contains('active')"))
    check('library selector follows project',page.locator('#libraryProjectSelect').input_value()==projects[1]['id'])
    boot_page(page,page.evaluate("window.__testStorage"));wait_project(page,projects[1]['id']);check('last project restored after reload',True);page.evaluate("document.documentElement.style.setProperty('--ui-safe-bottom','34px')")
    # Force a stale polling reply to arrive after a new selection.
    pid=projects[1]['id'];state['delay'][pid]=.7
    page.evaluate("()=>{window.pollBeforeSwitch=pollProjectStatus(S.project.id)}")
    time.sleep(.08);page.evaluate('pid=>{selectLibraryProject(pid)}',projects[0]['id']);wait_project(page,projects[0]['id']);page.wait_for_timeout(800)
    check('old poll cannot restore previous project',page.evaluate('S.project.id')==projects[0]['id'])
    # Ignore AbortController in the mock transport to check the epoch guard itself.
    page.evaluate("()=>{window.originalFetch=window.fetch;window.fetch=(u,o={})=>originalFetch(u,{...o,signal:undefined})}")
    state['delay'][projects[1]['id']]=.7
    page.evaluate('pid=>{openProject(pid)}',projects[1]['id']);page.wait_for_timeout(70)
    page.evaluate('pid=>{openProject(pid)}',projects[2]['id']);wait_project(page,projects[2]['id']);page.wait_for_timeout(800)
    check('rapid selections keep the last choice even without abort',page.evaluate('S.project.id')==projects[2]['id'])
    page.evaluate('()=>{window.fetch=window.originalFetch}')
    # An old openProjectNoPoll (e.g. an upload completing) must not switch context.
    state['delay'][projects[2]['id']]=.6
    page.evaluate('()=>{openProjectNoPoll(S.project.id)}');page.wait_for_timeout(60)
    page.evaluate('pid=>{openProject(pid)}',projects[0]['id']);wait_project(page,projects[0]['id']);page.wait_for_timeout(700)
    check('old refresh cannot replace new project',page.evaluate('S.project.id')==projects[0]['id'])
    # Simulated keyboard viewport, without claiming to emulate native Safari.
    view(page,'image');page.locator('#prompt').focus()
    page.evaluate("()=>{Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>innerHeight-320});visualViewport.dispatchEvent(new Event('resize'))}")
    page.wait_for_timeout(120);check('dock hidden while text keyboard overlaps',page.locator('.mobile-dock').evaluate('(e)=>getComputedStyle(e).visibility')=='hidden')
    page.evaluate("()=>{document.activeElement.blur();delete visualViewport.height;visualViewport.dispatchEvent(new Event('resize'))}");page.wait_for_timeout(120)
    check('dock restored after keyboard closes',page.locator('.mobile-dock').evaluate('(e)=>getComputedStyle(e).visibility')=='visible')
    page.set_viewport_size({'width':390,'height':690});page.wait_for_timeout(80)
    rect=page.locator('.mobile-dock').bounding_box();check('dock adapts to toolbar viewport resize',rect['y']+rect['height']<=690-44+.5,rect)
    page.set_viewport_size({'width':390,'height':844})
    # Real FFmpeg upload/preview/save. Player remains a browser-local blob.
    view(page,'media-tools');page.locator('#pickerFile').set_input_files(str(clip));page.locator('#pickerLoad').click()
    page.wait_for_function("!document.querySelector('#pickerSave').disabled",timeout=20000)
    check('video is a local inline player',page.locator('#pickerVideo').evaluate("e=>e.src.startsWith('blob:')&&e.controls&&e.playsInline"))
    page.locator('#pickerSeconds').fill('00:00:00.400');page.locator('#pickerRefresh').click()
    page.wait_for_function("document.querySelector('#pickerFrameInfo').textContent.startsWith('0.400 s')&&!document.querySelector('#pickerSave').disabled")
    check('HH:MM:SS time produces actual PNG preview',True)
    page.locator('#pickerSeconds').fill('::');page.locator('#pickerRefresh').click()
    check('invalid timestamp cannot save an old preview',page.locator('#pickerSave').is_disabled())
    page.locator('#pickerSeconds').fill('00:00:00.400');page.locator('#pickerRefresh').click()
    page.wait_for_function("!document.querySelector('#pickerSave').disabled")
    src=page.locator('#pickerPreview').evaluate('e=>e.src');vid,preview_id=src.split('/')[-3],src.split('/')[-1]
    expected=hashlib.sha256(picker.selected(vid,'owner',preview_id)[0].read_bytes()).hexdigest()
    page.locator('#pickerSave').click();page.wait_for_function("document.querySelector('#pickerStatus').textContent.includes('salvato')")
    check('saved PNG is byte-identical to displayed preview',state['saves'][-1]['sha256']==expected)
    page.locator('#pickerLast').click();page.wait_for_function("document.querySelector('#pickerFrameInfo').textContent.includes('Ultimo frame esatto')&&!document.querySelector('#pickerSave').disabled")
    check('exact last-frame mode retained',True)
    page.locator('#pickerVideo').evaluate("e=>e.dispatchEvent(new Event('error'))");check('unsupported playback has a frame-extraction fallback',page.locator('#pickerPlaybackWarning').is_visible())
    # Latest selection during an in-flight preview isn't silently discarded.
    state['preview_delay']=.25
    page.locator('#pickerSeconds').fill('0.6');page.locator('#pickerRefresh').click();page.wait_for_timeout(60)
    page.locator('#pickerSeconds').fill('0.8');page.locator('#pickerRefresh').click()
    page.wait_for_function("document.querySelector('#pickerFrameInfo').textContent.startsWith('0.800 s')&&!document.querySelector('#pickerSave').disabled",timeout=20000)
    check('rapid frame changes preview latest selection',True)
    page.locator('#pickerPlaybackWarning').evaluate('e=>e.hidden=true');page.evaluate('()=>{window.scrollTo(0,0)}');page.screenshot(path=str(OUT/'390-video-loaded.png'),full_page=True)
    # Project change invalidates the video and any late result.
    page.locator('#pickerSeconds').fill('1.2');page.locator('#pickerRefresh').click();page.wait_for_timeout(40)
    page.evaluate('pid=>{openProject(pid)}',projects[1]['id']);wait_project(page,projects[1]['id']);page.wait_for_timeout(700)
    check('project switch closes old video workspace',page.locator('#pickerWorkspace').get_attribute('hidden') is not None)
    check('project switch prevents stale-frame save',page.locator('#pickerSave').is_disabled())
    state['preview_delay']=0
   ctx.close()
  check('no uncaught browser exceptions',not errors,errors)
  browser.close()
finally:
 tmp.cleanup()
 report={'checks':checks,'passed':sum(c['passed'] for c in checks),'count':len(checks),'browser_errors':errors,
         'scope':'Chromium with touch emulation and simulated safe-area/keyboard. Network-free fixture transport. Actual FFmpeg PNGs decoded in browser; no Flask/auth/HTTP coverage.',
         'native_iphone_safari_tested':False,'gpu_tested':False}
 (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='checks'},ensure_ascii=False,indent=2))
