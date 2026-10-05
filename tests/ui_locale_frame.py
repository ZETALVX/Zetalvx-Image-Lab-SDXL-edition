from pathlib import Path
import json, sys, threading, http.server
from playwright.sync_api import sync_playwright
import argparse, os, io, base64
from PIL import Image
fixture=io.BytesIO();Image.new('RGB',(960,480),'#294858').save(fixture,'PNG');fixture=fixture.getvalue()
parser=argparse.ArgumentParser();parser.add_argument('--output',default='ui-test-results');parser.add_argument('--regression-code',action='store_true');parser.add_argument('--chromium',default='/usr/bin/chromium');args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1];OUT=Path(args.output).resolve();OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from core.model_policy import catalog
from core.task_adapters import support_matrix
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_GET(self):
        if '/preview/' in self.path:
            self.send_response(200);self.send_header('Content-Type','image/png');self.end_headers();self.wfile.write(fixture);return
        if self.path=='/':self.path='/templates/index.html'
        super().do_GET()
    def log_message(self,*a):pass
srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{srv.server_port}'
model=json.loads((ROOT/'config/models.defaults.json').read_text())['models'][0]
model['config'].update(checkpoint='/home/demo/.local/share/CreatorStudioSDXL/models/SDXL/sd_xl_base_1.0.safetensors',checkpoint_roots='/home/demo/.local/share/CreatorStudioSDXL/models/SDXL',lora_root='/home/demo/.local/share/CreatorStudioSDXL/models/loras/SDXL')
model['task_support']=support_matrix(model)
model['validation']={'ready':True,'fields':[],'missing':[]};model['status']='Ready'
modelpath='/home/demo/.local/share/CreatorStudioSDXL/models';identitypath=modelpath+'/Identity'
project={'id':'a'*32,'name':'Prova locale','description':'','state':{},'artifacts':[],'jobs':[],'messages':[]}
asset={'id':'f'*32,'type':'image','url':'data:image/png;base64,'+base64.b64encode(fixture).decode(),'metadata':{'original_name':'itapigna_test.png','model_name':'SDXL'},'created_at':'2026-09-20'}
project['artifacts']=[asset]
settings={'host':'127.0.0.1','identity_root':identitypath,'identity_instantid_root':identitypath+'/InstantID','identity_insightface_root':identitypath+'/insightface','identity_swapper_model':identitypath+'/inswapper_128.onnx','identity_vendor':'/home/demo/.local/share/CreatorStudioSDXL/shared/identity/vendor/InstantID'}
identity={'instantid_root':settings['identity_instantid_root'],'instantid_face_pack_dir':settings['identity_insightface_root']+'/models/antelopev2','swap_face_pack_dir':settings['identity_insightface_root']+'/models/buffalo_l','swapper_path':settings['identity_swapper_model'],'instantid_enabled':True,'faceswap_enabled':True,'license_acknowledged':False}
checkpoints=[{'name':'SDXL Base 1.0','path':model['config']['checkpoint']}]
loras=[{'name':'demo_style.safetensors','path':modelpath+'/loras/SDXL/demo_style.safetensors'}]
boot={'models':[model],'projects':[project],'recipes':[],'loras':loras,'checkpoints':checkpoints,'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
accounts={'huggingface':{'stored':False},'civitai':{'stored':False}}
hub={'ok':True,'csrf':'mock_csrf','models':[model],'settings':settings,'sdxl':{'ready':True},'identity':identity,'accounts':accounts,'jobs':[],'catalog':catalog(),'paths':{'checkpoint':modelpath+'/SDXL','lora':modelpath+'/loras/SDXL','vae':modelpath+'/VAE'},'checkpoints':checkpoints,'loras':loras,'vaes':[],'disk_free':100000000000}
preview={'id':'d'*32,'filename':'demo.safetensors','size':1024000,'kind':'lora','license':'Test della GUI · non è un download reale','source':'https://example.org/demo','license_url':'https://example.org/license'}
import tempfile
from vision.service import Service
vision_temp=tempfile.TemporaryDirectory();vision=Service(vision_temp.name)
requests=[];errors=[];assertions=[]
code_state={'status':'idle'};code_polls=0;code_mode='success';code_start_count=0;csrf_rejects=0;token_reads=0
managed='/home/demo/.local/share/CreatorStudioSDXL/shared/identity/vendor/InstantID-2145b67f9607'

def mock_api(url,method='GET',body=None):
    global code_state,code_polls,code_mode,code_start_count,csrf_rejects,token_reads
    path=url.split('/api/',1)[1];requests.append((method,path))
    d={}
    if path=='session/tokens':
        token_reads+=1;d={'tokens':{'vision':'test_vision_csrf','model-hub':'mock_csrf'}}
    elif path=='setup/identity-code-status':
        if code_state['status']=='running':
            code_polls+=1
            if code_polls>1:
                if code_mode=='success':
                    code_state.update(status='completed',stage='ready',message='Code installed',completed=6)
                    identity.update(vendor_root=managed,vendor_ready=True,vendor_points_to_weights=False,instantid_files_ready=True)
                    settings['identity_vendor']=managed
                else:code_state.update(status='failed',stage='failed',error='SIMULATED NETWORK ERROR: file unavailable',message='Code was not activated. Existing files were preserved.')
        d={'installation':code_state.copy(),'status':identity.copy()}
    elif path=='setup/identity-prepare-code':
        if args.regression_code and csrf_rejects==0:
            csrf_rejects+=1;d={'error':'Simulated rejected old token','code':'csrf_failed','_http_status':403}
        else:
            code_start_count+=1;code_polls=0;code_state={'id':str(code_start_count),'status':'running','stage':'downloading','target':managed,'completed':1,'total':6,'message':'Downloading code'}
            d={'installation':code_state.copy(),'_http_status':202}

    elif path=='vision/session':d={'csrf':'test_vision_csrf'}
    elif path.startswith('vision/'):
        from urllib.parse import urlsplit,parse_qs
        u=urlsplit('/api/'+path);q={k:v[-1] for k,v in parse_qs(u.query).items()};d=vision.handle(u.path,method,json.loads(body) if body else {},q)
    elif path=='bootstrap':d=boot
    elif path.startswith('projects/'):d={'project':project}
    elif path=='model-hub/status':d=hub
    elif path=='model-hub/local':d={'ok':True,'catalog':{'checkpoint':[], 'lora':[], 'sources':[]}}
    elif path=='model-hub/downloads':
        if method=='POST':hub['jobs']=[{'id':'e'*32,'filename':'demo.safetensors','status':'downloading','total_bytes':100,'downloaded_bytes':25,'error':''}]
        d={'ok':True,'jobs':hub['jobs'],'job':hub['jobs'][0] if hub['jobs'] else {}}
    elif path=='model-hub/inspect':d={'ok':True,'preview':preview}
    elif path.startswith('model-hub/accounts/'):
        provider=path.rsplit('/',1)[-1];accounts[provider]={'stored':method!='DELETE','account':'Account di prova'};d={'accounts':accounts}
    elif path=='setup':d={'settings':settings,'models':[model],'image_runtime':{'ok':False},'identity_runtime':{'online':False},'training_runtime':{'ok':False}}
    elif path=='account':d={'username':'C'}
    elif path=='image-tools/video-picker':d={'ok':True,'video':{'id':'1'*32,'duration':5,'width':960,'height':480,'project_id':project['id']}}
    elif path.endswith('/preview'):d={'ok':True,'preview':{'id':'2'*32,'info':{'width':960,'height':480}}}
    elif path.endswith('/save'):d={'ok':True,'artifact':asset}
    elif path.endswith('/caption-check'):d={'ok':True,'report':{'images':1,'empty':0,'missing':0,'repeated':0}}
    elif path=='identity/bootstrap':d={'runtime':{'online':False,'ok':False},'models':{},'jobs':[],'queue':{},'loras':loras,'checkpoints':checkpoints,'default_sdxl':model['config']['checkpoint']}
    elif path=='training/bootstrap':d={'runtime':{'ok':False},'datasets':[],'loras':[],'full_unets':[],'full_models':[],'jobs':[]}
    elif path=='setup/browse?path=' or path.startswith('setup/browse?'):d={'path':modelpath,'parent':'/home/demo','entries':[]}
    return d
def check(name,condition):
    assertions.append({'name':name,'passed':bool(condition)});print(name,bool(condition),flush=True)
    if not condition:print('FAIL',name)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=args.chromium,args=['--no-sandbox'])
    for w,h in [(390,844),(1440,1000)]:
        c=browser.new_context(viewport={'width':w,'height':h},device_scale_factor=1)
        # In-memory API mock: no network/navigation needed to validate the frontend.
        page=c.new_page();page.set_default_timeout(7000);page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:(errors.append('DIALOG: '+d.message),d.dismiss()))
        from bs4 import BeautifulSoup
        html=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
        for tag in html.find_all(['script','link']):tag.decompose()
        head=html.find('head');base_tag=html.new_tag('base',href=base+'/');head.append(base_tag);page.set_content(str(html))
        page.expose_function('_mock_api',mock_api)
        page.evaluate("""() => {
          const makeStore=()=>{const s={};return {setItem:(k,v)=>s[k]=String(v),getItem:k=>s[k]??null,removeItem:k=>delete s[k],clear:()=>Object.keys(s).forEach(k=>delete s[k])}};
          Object.defineProperty(window,'localStorage',{value:makeStore()});Object.defineProperty(window,'sessionStorage',{value:makeStore()});
          window.fetch=async(url,opt={})=>{const d=await window._mock_api(String(url),opt.method||'GET',opt.body||null);const status=d._http_status||200;delete d._http_status;return new Response(JSON.stringify(d),{status,headers:{'Content-Type':'application/json'}})};
        }""")
        page.add_style_tag(content=(ROOT/'static/style.css').read_text());page.add_style_tag(content=(ROOT/'static/model-hub.css').read_text())
        page.add_style_tag(content=(ROOT/'static/studio-additions.css').read_text())
        page.add_script_tag(content=(ROOT/'static/locale-catalog.js').read_text());page.add_script_tag(content=(ROOT/'static/vision-locale.js').read_text());page.add_script_tag(content=(ROOT/'static/fixes-locale.js').read_text());page.add_script_tag(content=(ROOT/'static/training-locale.js').read_text());page.add_script_tag(content=(ROOT/'static/release-locale.js').read_text());page.add_script_tag(content=(ROOT/'static/i18n.js').read_text())
        page.add_script_tag(content=(ROOT/'static/app.js').read_text());page.add_script_tag(content=(ROOT/'static/edition.js').read_text())
        page.add_script_tag(content=(ROOT/'static/studio-additions.js').read_text());page.add_style_tag(content=(ROOT/'static/vision-ui.css').read_text());page.add_script_tag(content=(ROOT/'static/vision-ui.js').read_text());page.add_script_tag(content=(ROOT/'static/vision-sdxl.js').read_text());page.add_style_tag(content=(ROOT/'static/training-workspace.css').read_text());page.add_script_tag(content=(ROOT/'static/training-workspace.js').read_text());page.add_style_tag(content=(ROOT/'static/release-polish.css').read_text());page.add_script_tag(content=(ROOT/'static/local-models.js').read_text());page.wait_for_timeout(700)
        check(f'{w} home active',page.locator('#view-home').evaluate("e=>e.classList.contains('active')"))
        check(f'{w} home no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/f'home_{w}.png'),full_page=True)
        page.evaluate("showView('models')");page.wait_for_timeout(250)
        check(f'{w} models tab',page.locator('[data-hub-panel="installed"]').is_visible())
        check(f'{w} external download absent',page.locator('#mmDownloadInstantId,#mmDownloadSwapper,#mmDownloadBuffalo').count()==0)
        check(f'{w} no duplicate model fields',page.locator('#setupCheckpoint').count()==1)
        check(f'{w} models no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/f'models_{w}.png'),full_page=True)
        page.locator('[data-hub-tab="vision"]').click();page.locator('[data-add]').click();page.locator('[data-form] input[name="name"]').fill('Local Qwen test');page.locator('[data-form] select[name="backend"]').select_option('gguf')
        check(f'{w} Vision gguf paths visible',page.locator('input[name="mmproj_path"]').is_visible());check(f'{w} Vision native hidden',not page.locator('input[name="model_path"]').is_visible());page.locator('[data-form] button[type="submit"]').click();page.wait_for_selector('[data-editor]:not([open])',state='attached');page.wait_for_selector('.vision-model-row')
        check(f'{w} configured models saved',page.locator('.vision-model-row').count()>0);check(f'{w} vision no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'));page.screenshot(path=str(OUT/f'vision_{w}.png'),full_page=True)
        page.locator('[data-hub-tab="installed"]').click()
        page.locator('[data-hub-open="hubIdentityPaths"]').first.click()
        check(f'{w} identity guide opens',page.locator('#hubIdentityGuide').is_visible())
        check(f'{w} exact path report present',page.locator('#identityResolvedPanel').count()==1)
        check(f'{w} guide actual paths','/models/antelopev2' in page.locator('#hubIdentityGuide').inner_text())
        if args.regression_code:
            # Simulate the user's actual saved mistake: code path points at weights.
            weights=settings['identity_instantid_root'];settings['identity_vendor']=weights
            identity.update(vendor_root=weights,vendor_ready=False,vendor_points_to_weights=True,instantid_files_ready=False)
            code_state={'status':'idle'};code_mode='success';csrf_rejects=0
            page.locator('#hubRefresh').click();page.wait_for_timeout(100)
            before=code_start_count;writes=sum(m=='PUT' and p=='setup' for m,p in requests);reads=token_reads
            page.locator('#hubPrepareCode').click()
            page.wait_for_function("document.querySelector('#hubCodeInstallStatus').textContent.includes('Codice verificato')")
            check(f'{w} code install once despite CSRF retry',code_start_count==before+1 and csrf_rejects==1)
            check(f'{w} code click does not save stale paths',sum(m=='PUT' and p=='setup' for m,p in requests)==writes)
            check(f'{w} CSRF rejection refreshes token',token_reads>reads)
            page.locator('#hubCodeCurrentPath').evaluate('e=>e.closest("details").open=true')
            check(f'{w} effective code path updated',page.locator('#hubCodeCurrentPath').inner_text()==managed)
            check(f'{w} weights path unchanged',settings['identity_instantid_root']==weights)
            check(f'{w} code button re-enabled',page.locator('#hubPrepareCode').is_enabled())
            check(f'{w} code progress does not reload page',page.locator('#hubIdentityPaths').evaluate('e=>e.open'))
            # Second simulated attempt fails: report actual error next to the button.
            code_mode='failure';before=code_start_count
            page.locator('#hubPrepareCode').click()
            page.wait_for_function("document.querySelector('#hubCodeInstallStatus').textContent.includes('SIMULATED NETWORK ERROR')")
            check(f'{w} code failure shown inline','SIMULATED NETWORK ERROR' in page.locator('#hubCodeInstallStatus').inner_text())
            check(f'{w} failed operation not auto-replayed',code_start_count==before+1)
            check(f'{w} failed install preserves code setting',settings['identity_vendor']==managed)
            check(f'{w} code failure layout fits',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            page.screenshot(path=str(OUT/f'code_failure_{w}.png'),full_page=True)
            code_mode='success'
        page.locator('[data-hub-tab="add"]').click();page.locator('#hubUrl').fill('https://example.org/demo.safetensors');page.locator('#hubInspect').click();page.wait_for_timeout(200)
        check(f'{w} preview visible',page.locator('#hubPreview').is_visible())
        page.locator('#hubAcceptTerms').check();page.locator('#hubStartDownload').click();page.wait_for_timeout(250)
        check(f'{w} download progress visible',page.locator('#hubDownloads progress').is_visible())
        page.locator('[data-hub-tab="installed"]').click()
        page.locator('#hubSdxlPaths > summary').click();page.locator('#setupCheckpoint').fill('/my/custom.safetensors')
        page.wait_for_timeout(1800)
        check(f'{w} polling preserves form',page.locator('#setupCheckpoint').input_value()=='/my/custom.safetensors')
        page.evaluate("document.querySelector('[data-hub-tab=accounts]').click()");page.locator('#hubHfToken').fill('hf_FAKE_UI_TEST_ONLY');page.locator('[data-account-save="huggingface"]').click();page.wait_for_timeout(250)
        check(f'{w} token cleared',page.locator('#hubHfToken').input_value()=='')
        check(f'{w} token absent storage',page.evaluate("!JSON.stringify({...localStorage,...sessionStorage}).includes('hf_FAKE_UI_TEST_ONLY')"))
        page.screenshot(path=str(OUT/f'accounts_{w}.png'),full_page=True)
        page.evaluate("setTask('generate')");page.wait_for_timeout(200)
        check(f'{w} negative basic visible',page.locator('#negativePrompt').is_visible())
        check(f'{w} lora basic visible',page.locator('#addLoraBtn').is_visible())
        check(f'{w} dimensions visible',page.locator('#width').is_visible() and page.locator('#height').is_visible())
        check(f'{w} image no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.locator('#width').fill('896');check(f'{w} manual size selects custom',page.locator('#ratio').input_value()=='Custom')
        page.locator('#width').blur();page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(100)
        page.screenshot(path=str(OUT/f'create_{w}.png'),full_page=True)
        page.evaluate("showView('identity');setIdentityMode('instantid')");page.wait_for_timeout(500)
        check(f'{w} Identity manual dimensions',page.locator('#identityWidth').is_visible() and page.locator('#identityHeight').is_visible())
        check(f'{w} identity no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/f'identity_{w}.png'),full_page=True)
        page.evaluate("setTask('generate'); S.activeAsset='"+asset['id']+"';renderActivePreview()")
        page.wait_for_timeout(150)
        check(f'{w} active preview contained',page.locator('#mainPreview img').evaluate("e=>getComputedStyle(e).objectFit==='contain' && e.getBoundingClientRect().width<=innerWidth"))
        page.locator('#prompt').fill('a photo of itapigna walking at sunset')
        page.locator('#negativePrompt').fill('blur, low quality')
        for lang in ['it','en','es','fr','de','pt','ru','zh','ja','ko','tr','ar']:
            page.evaluate('(l)=>ZI18n.setLanguage(l)',lang);page.wait_for_timeout(80)
            check(f'{w} {lang} prompt preserved',page.locator('#prompt').input_value()=='a photo of itapigna walking at sunset')
            check(f'{w} {lang} no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.evaluate("ZI18n.setLanguage('it');showView('media-tools')")
        page.locator('#videoFramePicker > summary').click() if page.locator('#videoFramePicker > summary').count() else None
        # open the actual details containing our file input
        page.locator('#pickerFile').evaluate("e=>e.closest('details').open=true")
        page.locator('#pickerFile').set_input_files({'name':'clip.mp4','mimeType':'video/mp4','buffer':b'fakevideo'})
        page.locator('#pickerLoad').click();page.wait_for_timeout(180)
        check(f'{w} frame preview ready',page.locator('#pickerSave').is_enabled())
        page.locator('#pickerSave').click();page.wait_for_timeout(160)
        check(f'{w} exact preview save invoked',any(m=='POST' and path.endswith('/save') for m,path in requests))
        page.screenshot(path=str(OUT/f'frame_picker_{w}.png'),full_page=True)
        page.evaluate("showView('models')");page.wait_for_timeout(80);page.screenshot(path=str(OUT/f'models_it_{w}.png'),full_page=True)
        (OUT/f'missing_{w}.json').write_text(json.dumps(page.evaluate('ZI18n.missing()'),ensure_ascii=False,indent=2))
        c.close()
    browser.close()
srv.shutdown()
(OUT/'report.json').write_text(json.dumps({'test_type':'actual Chromium frontend, simulated backend, no inference','checks':assertions,'page_errors':errors,'requests':requests},indent=2))
print('CHECKS',len(assertions),'FAILS',sum(not a['passed'] for a in assertions),'ERRORS',errors)
if errors or any(not item['passed'] for item in assertions):raise SystemExit(1)
