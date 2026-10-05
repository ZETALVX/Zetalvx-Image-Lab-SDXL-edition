"""Real Chromium/full shipped page; HTTP/GPU fixtures, real history filesystem.
Identity DOM and localized runtime UI regression, with mocked HTTP/GPU only.
"""
import argparse,base64,io,json,os,sys,tempfile,copy
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
from bs4 import BeautifulSoup
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();OUT=Path(a.output);OUT.mkdir(parents=True,exist_ok=True)
from core import training_manager as tm
from core.training_history import delete_job
from core.task_adapters import support_matrix
from core.model_policy import catalog
from core.local_models import LocalModels
from tests.test_model_hub import sample
checks=[];errors=[]
def check(name,ok):
 checks.append({'name':name,'passed':bool(ok)});print(name,bool(ok),flush=True)
 if not ok:raise AssertionError(name)
with tempfile.TemporaryDirectory() as td:
 root=Path(td);models=root/'models';(models/'SDXL').mkdir(parents=True);loras=models/'loras/SDXL';loras.mkdir(parents=True)
 cp=models/'SDXL/base.safetensors';cp.write_bytes(sample('checkpoint','sdxl'))
 cfgmodel=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
 cfgmodel['config'].update(checkpoint=str(cp),checkpoint_roots=str(cp.parent),lora_root=str(loras))
 cfgmodel.update(validation={'ready':True,'fields':[],'missing':[]},status='Ready');cfgmodel['task_support']=support_matrix(cfgmodel)
 store=LocalModels(models,root/'config/local_models.json')
 project={'id':'a'*32,'name':'Test','state':{},'artifacts':[],'jobs':[],'messages':[]}
 jobs=root/'training/jobs';jobs.mkdir(parents=True);datasets=root/'training/datasets';datasets.mkdir()
 (datasets/'preserved.txt').write_text('dataset stays');published=loras/'published.safetensors';published.write_bytes(b'published model stays')
 health={'ok':True,'busy':False};identity=[];requests=[]
 def boot():return {'models':[cfgmodel],'projects':[copy.deepcopy(project)],'recipes':[],'loras':[],'checkpoints':store.scan('checkpoint',cfgmodel['config']),'runtime':{'ok':True},'user_image_presets':[],'image_preset_bindings':{}}
 def ident():
  active=next((j for j in identity if j['status'] in ('queued','running')),None)
  return {'runtime':{'online':True,'ready':True,'runtime':{},'models':{}},'jobs':copy.deepcopy(identity),'queue':{'active':copy.deepcopy(active),'queued':[],'count':int(active is not None)},'batches':[],'checkpoints':boot()['checkpoints'],'loras':[],'default_base_model':str(cp)}
 def fixture(url,method='GET',body=None):
  path=urlsplit(url).path;requests.append((path,method));data=json.loads(body) if isinstance(body,str) and body.startswith('{') else {}
  if path=='/api/bootstrap':return boot()
  if path.startswith('/api/projects/'):return {'project':copy.deepcopy(project)}
  if path=='/api/jobs' and method=='POST':
   j={'id':'i'+str(len(project['jobs'])),'status':'queued','tool':'generate_image','params_json':'{}','progress':0,'prompt':'unchanged','model_id':'sdxl'};project['jobs'].insert(0,j);return {'ok':True,'id':j['id'],'ids':[j['id']],'batch':1}
  if path=='/api/identity/jobs' and method=='POST':
   j={'id':'face'+str(len(identity)),'mode':'face_swap','status':'queued','phase':'queued','progress':0,'prompt':'same prompt','output_exists':False};identity.insert(0,j);return {'ok':True,'job_id':j['id'],'status':'queued'}
  if path=='/api/identity/bootstrap':return ident()
  if path=='/api/training/bootstrap':return {'runtime':health,'datasets':[],'loras':[],'full_unets':[],'full_models':[],'jobs':tm.list_jobs(health)}
  if path.startswith('/api/training/jobs/') and method=='DELETE':
   try:return {'ok':True,'deleted':delete_job(path.rsplit('/',1)[-1],confirm=data.get('confirm'))}
   except Exception as e:return {'_status':409,'error':str(e)}
  if path=='/api/loras':return {'loras':[]}
  if path=='/api/model-hub/local':return {'catalog':store.inventory(cfgmodel['config'])}
  if path=='/api/session/tokens':return {'tokens':{'vision':'v','model-hub':'m'}}
  if path=='/api/model-hub/status':return {'models':[cfgmodel],'settings':{},'identity':{},'paths':{},'local_catalog':store.inventory(cfgmodel['config']),'catalog':catalog(),'jobs':[],'vaes':[]}
  if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{},'csrf':'v'}
  if path=='/api/setup/identity-code-status':return {'installation':{'status':'idle'},'status':{}}
  if path=='/api/setup':return {'settings':{'host':'127.0.0.1'},'models':[cfgmodel],'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
  return {}
 patcher=patch.multiple(tm,JOBS=jobs,DATASETS=datasets,LORA_ROOT=loras,FULL_ROOT=models/'trained',ensure=lambda:None,worker_health=lambda:health)
 patcher.start()
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  try:
   for width,height in ((390,844),(1440,1000)):
    identity.clear();project['jobs']=[];requests.clear()
    context=browser.new_context(viewport={'width':width,'height':height});page=context.new_page();page.set_default_timeout(8000)
    page.on('pageerror',lambda e:errors.append(e.stack))
    image_requests=[]
    page.route('**/api/identity/jobs/*/file',lambda route:(image_requests.append(route.request.url),route.fulfill(status=200,content_type='image/png',body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZtJkAAAAASUVORK5CYII='))))
    page.on('dialog',lambda d:d.accept() if d.type=='confirm' else (errors.append('unexpected dialog: '+d.message),d.dismiss()))
    raw=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
    css=[ROOT/x['href'].split('?')[0].lstrip('/') for x in raw.select('link[rel=stylesheet]')]
    scripts=[ROOT/x['src'].split('?')[0].lstrip('/') for x in raw.select('script[src]')]
    for el in raw.find_all(['script','link']):el.decompose()
    raw.head.append(raw.new_tag('base',href='https://creator.local/'))
    page.set_content(str(raw),wait_until='domcontentloaded');page.expose_function('_fixture',fixture)
    page.evaluate('''()=>{
     const memory=()=>{const d={};return {getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=String(v),removeItem:k=>delete d[k]}};
     Object.defineProperty(window,'localStorage',{value:memory()});Object.defineProperty(window,'sessionStorage',{value:memory()});
     window.fault=null;window.httpCalls=[];
     const realTimer=window.setTimeout;window.setTimeout=(fn,ms,...args)=>realTimer(fn,[15000,30000,120000].includes(ms)?180:ms,...args);
     window.fetch=async(url,opt={})=>{
      const path=new URL(url,document.baseURI).pathname,method=opt.method||'GET';httpCalls.push([path,method]);
      const fault=window.fault&&window.fault.path===path&&window.fault.method===method&&window.fault.left-->0?{...window.fault}:null;
      if(fault?.before)throw new TypeError('Load failed');
      const data=await window._fixture(String(url),method,typeof opt.body==='string'?opt.body:null);
      if(fault?.after)throw new TypeError('Load failed');
      if(fault?.stall)return {status:200,ok:true,text:()=>new Promise(()=>{})};
      const status=data._status||200;delete data._status;return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
     };
    }''')
    for f in css:page.add_style_tag(content=f.read_text())
    for f in scripts:page.add_script_tag(content=f.read_text())

    identity.extend([
      {'id':'done108','mode':'face_swap','status':'completed','phase':'completed','progress':1.0,'output_exists':True,'prompt':'completed image','seed':42},
      {'id':'live108','mode':'instantid','status':'running','phase':'generating','progress':0.1,'output_exists':False,'prompt':'running image','seed':43}])
    page.wait_for_timeout(400);page.evaluate("ZI18n.setLanguage('en');showView('identity');setIdentityMode('face_swap');")
    page.wait_for_selector('[data-identity-job-id="done108"]',state='attached')
    page.evaluate('clearInterval(S.identity.poll)')
    buf=io.BytesIO();Image.new('RGB',(32,32)).save(buf,'PNG');file={'name':'ref.png','mimeType':'image/png','buffer':buf.getvalue()}
    page.locator('#identityReferences').set_input_files([file]);page.locator('#identityBaseImage').set_input_files(file)
    page.evaluate("document.querySelector('#identityPrompt').value='KEEP my prompt';document.querySelector('#identitySeed').value='92814';")
    page.locator('[data-identity-job-id="done108"] img').scroll_into_view_if_needed()
    page.evaluate("document.querySelector('[data-identity-job-id=done108] img').loading='eager'");page.wait_for_timeout(500)
    page.wait_for_function("document.querySelector('[data-identity-job-id=done108] img').complete")
    page.wait_for_timeout(250)
    page.evaluate('''()=>{
      window.keptImage=document.querySelector('[data-identity-job-id=done108] img');
      window.keptRow=document.querySelector('[data-identity-job-id=done108]');
      window.keptLive=document.querySelector('[data-identity-job-id=live108]');
      window.oldScroll=window.scrollY;window.domMutations=[];
      window.observe108=new MutationObserver(xs=>domMutations.push(...xs));
      observe108.observe(document.querySelector('#identityJobs'),{subtree:true,childList:true,attributes:true,attributeOldValue:true,characterData:true});
    }''')
    before_requests=len(image_requests)
    page.evaluate('async()=>{for(let i=0;i<24;i++)await pollIdentityLive()}')
    page.wait_for_timeout(250)
    check(f'{width} 24 unchanged polls preserve image and history row',page.evaluate("keptImage===document.querySelector('[data-identity-job-id=done108] img')&&keptRow===document.querySelector('[data-identity-job-id=done108]')"))
    check(f'{width} no changed content or image URLs in unchanged history',page.evaluate("domMutations.filter(m=>m.type!=='attributes'||m.oldValue!==m.target.getAttribute(m.attributeName)).length===0"))
    check(f'{width} no image redownloads for unchanged polling',len(image_requests)==before_requests and before_requests>0)
    check(f'{width} scrolling unchanged by background reads',page.evaluate('Math.abs(window.scrollY-oldScroll)<1'))
    check(f'{width} prompt seed and reference files stay selected',page.evaluate("document.querySelector('#identityPrompt').value==='KEEP my prompt'&&document.querySelector('#identitySeed').value==='92814'&&document.querySelector('#identityReferences').files.length===1&&document.querySelector('#identityBaseImage').files.length===1"))
    identity[1].update(progress=0.6,phase='decoding')
    page.evaluate('pollIdentityLive()');page.wait_for_timeout(100)
    check(f'{width} running progress changes in same row',page.evaluate("keptLive===document.querySelector('[data-identity-job-id=live108]')&&keptLive.querySelector('.progress-fill').style.width==='60%'"))
    check(f'{width} changing another job preserves completed image',page.evaluate("keptImage===document.querySelector('[data-identity-job-id=done108] img')"))
    # Download handlers may inject a Save button; unchanged polls must keep it.
    page.evaluate("window.testSave=document.createElement('button');testSave.textContent='Save file';keptRow.querySelector('.asset-actions').append(testSave);")
    page.evaluate('pollIdentityLive()')
    check(f'{width} download save control survives unchanged polling',page.evaluate('testSave.isConnected'))
    identity.insert(0,{'id':'queued108','mode':'instantid','status':'queued','progress':0.0,'output_exists':False})
    page.evaluate('pollIdentityLive()')
    check(f'{width} insertion preserves existing completed row',page.evaluate("keptRow===document.querySelector('[data-identity-job-id=done108]')&&keptImage.isConnected&&testSave.isConnected"))
    identity[:]=[identity[2],identity[1]]
    page.evaluate('pollIdentityLive()')
    check(f'{width} reorder and deletion use stable job keys',page.evaluate("document.querySelector('#identityJobs').firstElementChild===keptLive&&!document.querySelector('[data-identity-job-id=queued108]')&&keptImage.isConnected"))
    page.evaluate("ZI18n.setLanguage('it')");page.wait_for_timeout(250)
    text_before=page.locator('[data-identity-job-id=done108]').inner_text()
    page.evaluate('async()=>{for(let i=0;i<5;i++)await pollIdentityLive()}');page.wait_for_timeout(150)
    check(f'{width} translated history does not revert on polling',page.locator('[data-identity-job-id=done108]').inner_text()==text_before)
    check(f'{width} language switch preserves completed image node',page.evaluate('keptImage.isConnected'))
    page.evaluate("fault={path:'/api/identity/bootstrap',method:'GET',left:2,before:true}")
    page.evaluate('pollIdentityLive()')
    check(f'{width} network error does not destroy results',page.evaluate('keptImage.isConnected&&testSave.isConnected'))
    page.evaluate('fault=null;pollIdentityLive()');page.wait_for_timeout(100)
    check(f'{width} runtime label recovers after transient error',not 'reconnect' in page.locator('#identityRuntimeState').inner_text().lower() and not 'riconn' in page.locator('#identityRuntimeState').inner_text().lower())
    check(f'{width} status recovery performs no job POST',not any(path=='/api/identity/jobs' and method=='POST' for path,method in requests))
    page.screenshot(path=str(OUT/f'identity_{width}.png'))
    # Keep the original full page, render a second Vision manager for deterministic metadata fixtures.
    page.evaluate('''()=>{
      window.vstate={state:'failed',error_code:'llama_no_stable',error:'original technical metadata error',log_path:'test/runtime.log',installed:false};
      window.vactions=[{id:'runtime108',kind:'llama_runtime',status:'failed',error_code:'llama_no_stable',message:'original technical metadata error',created_at:1}];
      window.vcalls=[];
      const root=document.createElement('section');root.id='testVision108';document.body.append(root);
      window.vm108=ZetalvxVisionUI.mount(root,async(url,options={})=>{
        vcalls.push([url,options.method||'GET']);
        if(url==='/api/vision/llama-runtime')return {runtime:vstate};
        if(url==='/api/vision/llama-runtime-install'){vstate={state:'searching',installed:false,progress:2};return {action:{id:'new108'}};}
        return {models:[],actions:vactions,runtime:{},jobs:[]};
      });
      vm108.edit({name:'Vision fixture',backend:'gguf'});
    }''')
    page.wait_for_timeout(300)
    expected=json.JSONDecoder().raw_decode((ROOT/'static/vision-runtime-locale.js').read_text().split('const entries=',1)[1])[0]
    wanted=next(x['text'] for x in expected if x['sources']==['No published stable release was found.'])
    for lang,text in wanted.items():
     page.evaluate('(lang)=>ZI18n.setLanguage(lang)',lang);page.wait_for_timeout(75)
     check(f'{width} Vision runtime failure localized {lang}',page.locator('#testVision108 [data-llama-status]').inner_text()==text)
    page.evaluate("ZI18n.setLanguage('en')");page.wait_for_timeout(100)
    page.locator('#testVision108 [data-llama-prepare]').click(force=True);page.wait_for_timeout(250)
    check(f'{width} Prepare runtime submits once with auto preference',page.evaluate("vcalls.filter(x=>x[0]==='/api/vision/llama-runtime-install'&&x[1]==='POST').length===1"))
    page.evaluate("vstate={state:'ready',installed:true,version:'v-test',backend:'cpu',fallbacks:[{backend:'cuda12'}]}")
    page.wait_for_function("document.querySelector('#testVision108 [data-llama-status]').textContent.includes('Official runtime ready')")
    check(f'{width} fallback is visibly reported and button unlocked',page.evaluate("document.querySelector('#testVision108 [data-llama-status]').textContent.includes('Automatic fallback')&&!document.querySelector('#testVision108 [data-llama-prepare]').disabled"))
    page.screenshot(path=str(OUT/f'runtime_{width}.png'))
    page.locator('#testVision108 [data-close]').click(force=True)
    context.close()
  finally:browser.close();patcher.stop()
print('BROWSER ERRORS',errors,flush=True);check('No unhandled browser exceptions or blocking alerts',not errors)
(OUT/'result.json').write_text(json.dumps({'checks':checks,'errors':errors,'backend':'HTTP/GPU fixtures; shipped HTML/CSS/JavaScript; completed image requests counted','native_safari':False},indent=2))
