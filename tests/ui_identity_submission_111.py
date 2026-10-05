"""1.0.14 browser regression. Delivered page/scripts, simulated HTTP/GPU.
Browser networking is disabled by host policy; no native HTTPS claim.
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
  if path=='/api/identity/auto-test' and method=='POST':return {'ok':True,'batch_id':'batch111','batch_name':'fixture','count':1}
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
      if(fault?.html400)return new Response('<!doctype html><title>400 Bad Request</title>',{status:400,headers:{'Content-Type':'text/html'}});
      if(fault?.html500)return new Response('<h1>Internal Server Error</h1>',{status:500});
      if(fault?.json413)return new Response(JSON.stringify({error:'Identity upload exceeds the server limits. Use smaller images or fewer attachments.',code:'identity_upload_too_large'}),{status:413});
      if(fault?.delay)await new Promise(r=>realTimer(r,60));
      const data=await window._fixture(String(url),method,typeof opt.body==='string'?opt.body:null);
      if(fault?.after)throw new TypeError('Load failed');
      if(fault?.stall)return {status:200,ok:true,text:()=>new Promise(()=>{})};
      const status=data._status||200;delete data._status;return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
     };
    }''')
    for f in css:page.add_style_tag(content=f.read_text())
    for f in scripts:page.add_script_tag(content=f.read_text())
    page.wait_for_timeout(400);page.evaluate("ZI18n.setLanguage('en');showView('identity');setIdentityMode('face_swap');")
    buf=io.BytesIO();Image.new('RGB',(32,32)).save(buf,'PNG');file={'name':'ref.png','mimeType':'image/png','buffer':buf.getvalue()}
    page.locator('#identityReferences').set_input_files([file]);page.locator('#identityBaseImage').set_input_files(file)
    page.evaluate("document.querySelector('#identityPrompt').value='preserve this prompt';document.querySelector('#identitySeed').value='12345';")
    page.wait_for_timeout(200)
    page.evaluate("fault={path:'/api/identity/bootstrap',method:'GET',left:2,stall:true}")
    page.locator('#identityGenerate').click(force=True)
    page.wait_for_function("!document.querySelector('#identityGenerate').disabled")
    check(f'{width} accepted submit releases button before stalled history',page.locator('#identityGenerate').inner_text()!='Adding to queue…')
    page.wait_for_function("S.identity.boot?.jobs?.length===1")
    check(f'{width} live polling recovers without refresh',len(identity)==1)
    identity[0].update(status='completed',phase='completed',progress=1.0)
    page.wait_for_function("S.identity.boot.jobs[0].status==='completed'")
    check(f'{width} completion appears without refresh',True)
    check(f'{width} controls/files preserved',page.evaluate("document.querySelector('#identityPrompt').value==='preserve this prompt'&&document.querySelector('#identitySeed').value==='12345'&&document.querySelector('#identityReferences').files.length===1&&document.querySelector('#identityBaseImage').files.length===1"))
    page.evaluate("fault={path:'/api/identity/jobs',method:'POST',left:1,after:true};httpCalls=[]")
    page.locator('#identityGenerate').click(force=True);page.wait_for_function("!document.querySelector('#identityGenerate').disabled")
    page.wait_for_function("S.identity.boot.jobs.length===2")
    check(f'{width} lost POST response is not resubmitted',page.evaluate("httpCalls.filter(x=>x[0]==='/api/identity/jobs'&&x[1]==='POST').length===1"))
    check(f'{width} already accepted job still shown after network error',len(identity)==2)
    page.evaluate("clearInterval(S.identity.poll);fault=null;httpCalls=[]")
    page.wait_for_timeout(200)
    page.evaluate("Promise.all([identitySnapshot(),identitySnapshot(),identitySnapshot()])")
    check(f'{width} snapshot calls coalesced',page.evaluate("httpCalls.filter(x=>x[0]==='/api/identity/bootstrap').length===1"))
    page.evaluate("showView('image');document.querySelector('#prompt').value='test image';fault={path:'/api/projects/'+S.project.id,method:'GET',left:2,stall:true};")
    page.locator('#runImageBtn').click(force=True);page.wait_for_function("!document.querySelector('#runImageBtn').disabled")
    check(f'{width} image enqueue releases button despite failed refresh',len(project['jobs'])==1)
    page.wait_for_function("S.project.jobs.length===1")
    check(f'{width} image queue reconnects without refresh',True)
    project['jobs'][0]['status']='completed'
    # Actual filesystem deletion via fixture handler; backend safety is also
    # tested separately by test_training_history_104.
    jid='history'+str(width);folder=jobs/jid;folder.mkdir()
    (folder/'job.json').write_text(json.dumps({'id':jid,'name':'Old test','status':'completed','mode':'lora','max_steps':300,'step':300}))
    (folder/'progress.json').write_text('{}');(folder/'job.log').write_text('old log')
    page.evaluate("fault=null;showView('training')")
    page.wait_for_selector(f'[data-train-delete="{jid}"]',state='attached');page.evaluate("window.ZetalvxDatasetWorkspace?.selectPage('results',true)")
    check(f'{width} completed training exposes delete',True)
    page.locator(f'[data-train-delete="{jid}"]').click(force=True)
    page.wait_for_function('(id)=>!document.querySelector(`[data-train-delete="${id}"]`)',arg=jid)
    check(f'{width} history card and workspace removed',not folder.exists())
    check(f'{width} dataset and published LoRA preserved',(datasets/'preserved.txt').read_text()=='dataset stays' and published.read_bytes()==b'published model stays')
    page.evaluate("renderTrainingJobs([{id:'active1',name:'active',status:'running',mode:'lora',checkpoints:[]}])")
    check(f'{width} active training has no delete button',page.locator('[data-train-delete="active1"]').count()==0)
    page.evaluate("ZI18n.setLanguage('it');generationFeedback('identity','Connection interrupted while updating the queue. Reconnecting automatically.',true);generationStatusRecovered('identity');")
    check(f'{width} translated recovery message clears stale error',page.evaluate("!document.querySelector('#identityRequestStatus').classList.contains('training-error')&&document.querySelector('#identityRequestStatus').textContent.includes('Coda aggiornata')"))

    page.evaluate("fault=null;showView('identity');setIdentityMode('face_swap');")
    for kind in ('html400','html500','json413'):
     before=len(identity);page.evaluate("(kind)=>{fault={path:'/api/identity/jobs',method:'POST',left:1,[kind]:true}}",kind)
     page.locator('#identityGenerate').evaluate('button=>button.click()');page.wait_for_function('!identitySubmissionInFlight')
     check(f'{width} {kind} unlocks button without HTML',not page.locator('#identityGenerate').is_disabled() and 'Adding to queue' not in page.locator('#identityGenerate').inner_text() and '<' not in page.locator('#identityRequestStatus').inner_text())
     check(f'{width} {kind} not retried',len(identity)==before)
    page.evaluate("fault=null;window.modeRenderer=setIdentityMode;setIdentityMode=()=>{throw Error('deliberate mode-render failure')};void 0")
    page.locator('#identityGenerate').evaluate('button=>button.click()');page.wait_for_function('!identitySubmissionInFlight')
    check(f'{width} unlock no longer calls fragile mode renderer',not page.locator('#identityGenerate').is_disabled() and 'Adding' not in page.locator('#identityGenerate').inner_text())
    page.evaluate('setIdentityMode=window.modeRenderer;void 0')
    before=len(identity);page.evaluate("fault={path:'/api/identity/jobs',method:'POST',left:1,delay:true};void runIdentity();void runIdentity()")
    page.wait_for_function('!identitySubmissionInFlight')
    check(f'{width} direct double submit serializes upload',len(identity)==before+1)
    before=len(identity)
    for _ in range(3):
     page.evaluate('runIdentity()');page.wait_for_function('!identitySubmissionInFlight')
    check(f'{width} three consecutive submissions each accepted',len(identity)==before+3)
    before=len(identity);page.locator('#identityReferences').set_input_files({'name':'empty.png','mimeType':'image/png','buffer':b''})
    page.evaluate('runIdentity()');page.wait_for_function('!identitySubmissionInFlight')
    check(f'{width} empty attachment rejected before upload',len(identity)==before)
    page.locator('#identityReferences').set_input_files([file])
    page.evaluate("setIdentityMode('instantid');document.querySelector('#identitySweepIdentity').value='0.9';document.querySelector('#identitySweepPose').value='0.6';document.querySelector('#identitySweepCfg').value='5';document.querySelector('#identitySweepControlEnd').value='1';")
    page.evaluate('runIdentityAutoTest()');page.wait_for_function('!identitySubmissionInFlight')
    check(f'{width} Auto Test shared upload guard unlocks',not page.locator('#identityAutoTestRun').is_disabled() and 'Queuing' not in page.locator('#identityAutoTestRun').inner_text())
    page.evaluate("fault=null;showView('identity');bootstrap()")
    page.wait_for_timeout(350)
    check(f'{width} bootstrap restores stored Identity tab',page.locator('#view-identity').evaluate("e=>e.classList.contains('active')"))
    page.evaluate("showView('settings');bootstrap()")
    page.wait_for_timeout(350)
    check(f'{width} bootstrap restores stored Settings tab',page.locator('#view-settings').evaluate("e=>e.classList.contains('active')"))
    page.evaluate("sessionStorage.setItem('creator_sdxl_last_view','../../bad');bootstrap()")
    page.wait_for_timeout(350)
    check(f'{width} invalid tab falls back to Home',page.locator('#view-home').evaluate("e=>e.classList.contains('active')"))
    page.evaluate("showView('identity');ZI18n.setLanguage('it');generationFeedback('identity','Identity upload could not be read. No job was queued. Reselect the images and try again.',true)")
    check(f'{width} upload error localized', 'Nessun lavoro' in page.locator('#identityRequestStatus').inner_text())
    page.screenshot(path=str(OUT/f'ui_{width}.png'))
    context.close()
  finally:browser.close();patcher.stop()
print('BROWSER ERRORS',errors,flush=True);check('No unhandled browser exceptions or blocking alert',not errors)
(OUT/'result.json').write_text(json.dumps({'checks':checks,'errors':errors,'backend':'HTTP/GPU fixtures; actual filesystem deletion','native_safari':False},indent=2))
