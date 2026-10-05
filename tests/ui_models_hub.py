from pathlib import Path
import json, sys, threading, http.server
from playwright.sync_api import sync_playwright
import argparse, os
parser=argparse.ArgumentParser();parser.add_argument('--output',default='ui-test-results');parser.add_argument('--chromium',default='/usr/bin/chromium');args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1];OUT=Path(args.output).resolve();OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from core.model_policy import catalog
from core.task_adapters import support_matrix
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_GET(self):
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
settings={'host':'127.0.0.1','identity_root':identitypath,'identity_instantid_root':identitypath+'/InstantID','identity_insightface_root':identitypath+'/insightface','identity_swapper_model':identitypath+'/inswapper_128.onnx','identity_vendor':'/home/demo/.local/share/CreatorStudioSDXL/shared/identity/vendor/InstantID'}
identity={'instantid_root':settings['identity_instantid_root'],'instantid_face_pack_dir':settings['identity_insightface_root']+'/models/antelopev2','swap_face_pack_dir':settings['identity_insightface_root']+'/models/buffalo_l','swapper_path':settings['identity_swapper_model'],'instantid_enabled':True,'faceswap_enabled':True,'license_acknowledged':False}
checkpoints=[{'name':'SDXL Base 1.0','path':model['config']['checkpoint']}]
loras=[{'name':'demo_style.safetensors','path':modelpath+'/loras/SDXL/demo_style.safetensors'}]
boot={'models':[model],'projects':[project],'recipes':[],'loras':loras,'checkpoints':checkpoints,'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
accounts={'huggingface':{'stored':False},'civitai':{'stored':False}}
hub={'ok':True,'csrf':'mock_csrf','models':[model],'settings':settings,'sdxl':{'ready':True},'identity':identity,'accounts':accounts,'jobs':[],'catalog':catalog(),'paths':{'checkpoint':modelpath+'/SDXL','lora':modelpath+'/loras/SDXL','vae':modelpath+'/VAE'},'checkpoints':checkpoints,'loras':loras,'vaes':[],'disk_free':100000000000}
preview={'id':'d'*32,'filename':'demo.safetensors','size':1024000,'kind':'lora','license':'Test della GUI · non è un download reale','source':'https://example.org/demo','license_url':'https://example.org/license'}
requests=[];errors=[];assertions=[]
def mock_api(url,method='GET',body=None):
    path=url.split('/api/',1)[1];requests.append((method,path))
    d={}
    if path=='bootstrap':d=boot
    elif path.startswith('projects/'):d={'project':project}
    elif path=='model-hub/status':d=hub
    elif path=='model-hub/downloads':
        if method=='POST':hub['jobs']=[{'id':'e'*32,'filename':'demo.safetensors','status':'downloading','total_bytes':100,'downloaded_bytes':25,'error':''}]
        d={'ok':True,'jobs':hub['jobs'],'job':hub['jobs'][0] if hub['jobs'] else {}}
    elif path=='model-hub/inspect':d={'ok':True,'preview':preview}
    elif path.startswith('model-hub/accounts/'):
        provider=path.rsplit('/',1)[-1];accounts[provider]={'stored':method!='DELETE','account':'Account di prova'};d={'accounts':accounts}
    elif path=='setup':d={'settings':settings,'models':[model],'image_runtime':{'ok':False},'identity_runtime':{'online':False},'training_runtime':{'ok':False}}
    elif path=='account':d={'username':'C'}
    elif path=='identity/bootstrap':d={'runtime':{'online':False,'ok':False},'models':{},'jobs':[],'queue':{},'loras':loras,'checkpoints':checkpoints,'default_sdxl':model['config']['checkpoint']}
    elif path=='training/bootstrap':d={'runtime':{'ok':False},'datasets':[],'loras':[],'full_unets':[],'full_models':[],'jobs':[]}
    elif path=='setup/browse?path=' or path.startswith('setup/browse?'):d={'path':modelpath,'parent':'/home/demo','entries':[]}
    return d
def check(name,condition):
    assertions.append({'name':name,'passed':bool(condition)})
    if not condition:print('FAIL',name)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=args.chromium,args=['--no-sandbox'])
    for w,h in [(390,844),(768,1024),(1440,1000)]:
        c=browser.new_context(viewport={'width':w,'height':h},device_scale_factor=1)
        # In-memory API mock: no network/navigation needed to validate the frontend.
        page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:(errors.append('DIALOG: '+d.message),d.dismiss()))
        from bs4 import BeautifulSoup
        html=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
        for tag in html.find_all(['script','link']):tag.decompose()
        page.set_content(str(html))
        page.expose_function('_mock_api',mock_api)
        page.evaluate("""() => {
          const makeStore=()=>{const s={};return {setItem:(k,v)=>s[k]=String(v),getItem:k=>s[k]??null,removeItem:k=>delete s[k],clear:()=>Object.keys(s).forEach(k=>delete s[k])}};
          Object.defineProperty(window,'localStorage',{value:makeStore()});Object.defineProperty(window,'sessionStorage',{value:makeStore()});
          window.fetch=async(url,opt={})=>new Response(JSON.stringify(await window._mock_api(String(url),opt.method||'GET',opt.body||null)),{status:200,headers:{'Content-Type':'application/json'}});
        }""")
        page.add_style_tag(content=(ROOT/'static/style.css').read_text());page.add_style_tag(content=(ROOT/'static/model-hub.css').read_text())
        page.add_script_tag(content=(ROOT/'static/app.js').read_text());page.add_script_tag(content=(ROOT/'static/edition.js').read_text())
        page.wait_for_timeout(700)
        check(f'{w} home active',page.locator('#view-home').evaluate("e=>e.classList.contains('active')"))
        check(f'{w} home no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/f'home_{w}.png'),full_page=True)
        page.evaluate("showView('models')");page.wait_for_timeout(250)
        check(f'{w} models tab',page.locator('[data-hub-panel="installed"]').is_visible())
        check(f'{w} external download absent',page.locator('#mmDownloadInstantId,#mmDownloadSwapper,#mmDownloadBuffalo').count()==0)
        check(f'{w} no duplicate model fields',page.locator('#setupCheckpoint').count()==1)
        check(f'{w} models no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/f'models_{w}.png'),full_page=True)
        page.locator('[data-hub-open="hubIdentityPaths"]').first.click()
        check(f'{w} identity guide opens',page.locator('#hubIdentityGuide').is_visible())
        check(f'{w} guide actual paths','/models/antelopev2' in page.locator('#hubIdentityGuide').inner_text())
        page.locator('[data-hub-tab="add"]').click();page.locator('#hubUrl').fill('https://example.org/demo.safetensors');page.locator('#hubInspect').click();page.wait_for_timeout(200)
        check(f'{w} preview visible',page.locator('#hubPreview').is_visible())
        page.locator('#hubAcceptTerms').check();page.locator('#hubStartDownload').click();page.wait_for_timeout(250)
        check(f'{w} download progress visible',page.locator('#hubDownloads progress').is_visible())
        page.locator('[data-hub-tab="installed"]').click()
        page.locator('#hubSdxlPaths > summary').click();page.locator('#setupCheckpoint').fill('/my/custom.safetensors')
        page.wait_for_timeout(1800)
        check(f'{w} polling preserves form',page.locator('#setupCheckpoint').input_value()=='/my/custom.safetensors')
        page.locator('[data-hub-tab="accounts"]').click();page.locator('#hubHfToken').fill('hf_FAKE_UI_TEST_ONLY');page.locator('[data-account-save="huggingface"]').click();page.wait_for_timeout(250)
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
        c.close()
    browser.close()
srv.shutdown()
(OUT/'report.json').write_text(json.dumps({'test_type':'actual Chromium frontend, simulated backend, no inference','checks':assertions,'page_errors':errors,'requests':requests},indent=2))
print('CHECKS',len(assertions),'FAILS',sum(not a['passed'] for a in assertions),'ERRORS',errors)
