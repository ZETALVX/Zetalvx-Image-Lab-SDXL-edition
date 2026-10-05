"""Actual shared Vision UI with controlled API history. No model execution."""
import argparse,base64,io,json,sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args();R=Path(a.root);OUT=Path(a.output);OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];calls=[]
def check(n,x):checks.append({'name':n,'passed':bool(x)});print(n,bool(x),flush=True)
buf=io.BytesIO();Image.new('RGB',(80,60),(80,120,100)).save(buf,'PNG')
original={'id':'1'*32,'name':'Qwen test','backend':'gguf','enabled':True,'terms_reviewed':True,'llama_path':'/home/user/ai/llama.cpp/build/bin/llama-server','gguf_path':'/home/user/ai/modelli/Qwen.gguf','mmproj_path':'/home/user/ai/modelli/mmproj.gguf','temperature':.2,'max_tokens':200}
old={'id':'2'*32,'model_id':original['id'],'model_name':'Qwen test','kind':'test','status':'failed','created_at':1,'message':'OLD FAILURE: Missing configuration runtime/llama.cpp/build/bin/llama-server','execution':{'llama_server':'/old/default/llama-server'},'profile_fingerprint':'old'}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for w,h in [(390,844),(1440,1000)]:
  model=original.copy();actions=[old.copy()];counter=3;result='success';polls=0
  def mock(path,method='GET',body=None):
   global counter,result,polls,actions,model
   d=json.loads(body) if body else {};calls.append([method,path])
   if path=='/api/vision/models':return {'models':[model],'default_python':'/test/runtime/python'}
   if path.endswith('/inspect'):return {'inspection':{'ok':True,'checks':[{'label':'llama-server executable','path':model['llama_path'],'ok':True}],'notes':[]}}
   if path.endswith('/'+model['id']) and method=='PUT':model.update(d);return {'model':model.copy()}
   if path=='/api/vision/caption':
    counter+=1;polls=0
    j={'id':str(counter)*32,'kind':'test','model_id':model['id'],'model_name':model['name'],'backend':'gguf','status':'running','message':'','created_at':counter,'execution':{'llama_server':model['llama_path'],'gguf_model':model['gguf_path']},'profile_fingerprint':'saved_profile'}
    actions=[j,*actions];return {'action':j.copy()}
   if path.endswith('/cancel'):
    actions[0].update(status='cancelled',message='Test cancelled.');return {'action':actions[0]}
   if path=='/api/vision/actions':
    polls+=1
    if actions and actions[0]['status']=='running' and polls>1 and result!='hold':
     if result=='success':actions[0].update(status='completed',caption='CURRENT SUCCESS CAPTION',message='CURRENT SUCCESS CAPTION')
     else:actions[0].update(status='failed',message='CURRENT LEGITIMATE FAILURE')
    return {'actions':actions,'runtime':{}}
   return {}
  ctx=browser.new_context(viewport={'width':w,'height':h});page=ctx.new_page();page.set_default_timeout(5000);page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());page.expose_function('_mock',mock)
  page.set_content('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="hub"></main></body></html>')
  page.evaluate("""()=>{const s={};Object.defineProperty(window,'localStorage',{value:{getItem:k=>s[k]??null,setItem:(k,v)=>s[k]=v}})}""")
  page.add_style_tag(content='*{box-sizing:border-box} body{margin:0;padding:14px;font:16px sans-serif;background:#111918;color:#e3ebe7} button,input,select,textarea{font:inherit;max-width:100%} main{max-width:1100px;margin:auto} [hidden]{display:none!important} dialog{background:#162220;color:inherit} dialog::backdrop{background:#0009}')
  page.add_style_tag(content=(R/'static/vision-ui.css').read_text())
  for f in ['locale-catalog.js','vision-locale.js','fixes-locale.js','i18n.js','vision-ui.js']:page.add_script_tag(content=(R/'static'/f).read_text())
  page.evaluate("""async()=>{window.manager=ZetalvxVisionUI.mount(document.querySelector('#hub'),async(path,opt={})=>window._mock(path,opt.method||'GET',opt.body||null));await manager.load();await manager.resume();} """)
  def test_start():
   page.locator('.vision-model-row button').nth(2).click()
   page.locator('[data-test-image]').set_input_files({'name':'test.png','mimeType':'image/png','buffer':buf.getvalue()})
   page.locator('[data-test-run]').click()
  page.locator('.vision-model-row button').nth(1).click();page.wait_for_selector('.vision-inspection');check(f'{w} file check custom path',model['llama_path'] in page.locator('.vision-inspection').inner_text())
  page.locator('.vision-model-row button').nth(0).click();check(f'{w} saved llama path in form',page.locator('input[name=llama_path]').input_value()==original['llama_path']);check(f'{w} GGUF upload controls',page.locator('[data-upload-trigger]').count()==2 and page.locator('[data-upload-input]').count()==2);check(f'{w} llama server remains server-only',page.locator('[data-upload-trigger="llama_path"]').count()==0 and page.locator('[data-browse="llama_path"]').count()==1);check(f'{w} vision editor no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'));page.locator('textarea[name=instructions]').evaluate('e=>e.closest("details").open=true');page.locator('textarea[name=instructions]').fill('Describe image.');page.locator('[data-form] button[type=submit]').click();page.wait_for_selector('[data-editor]:not([open])',state='attached');check(f'{w} save retains custom path',model['llama_path']==original['llama_path'])
  page.locator('.vision-model-row button').nth(1).click()
  page.locator('.vision-model-row button').nth(2).click();check(f'{w} opening test does not reuse old error','OLD FAILURE' not in page.locator('[data-test-output]').inner_text());page.locator('[data-test-close]').click()
  test_start();page.wait_for_function("document.querySelector('[data-test-output]').textContent.includes('CURRENT SUCCESS')")
  check(f'{w} latest success not overwritten','OLD FAILURE' not in page.locator('[data-test-output]').inner_text());check(f'{w} modal success','CURRENT SUCCESS CAPTION' in page.locator('[data-test-output]').inner_text())
  page.locator('[data-test-diagnostics] summary').click();check(f'{w} test exact path',original['llama_path'] in page.locator('[data-test-execution]').inner_text());check(f'{w} path no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
  page.evaluate('manager.resume()');check(f'{w} repeated poll stable','CURRENT SUCCESS' in page.locator('[data-test-output]').inner_text())
  page.locator('[data-test-close]').click();check(f'{w} current panel only newest','OLD FAILURE' not in page.locator('[data-actions]').inner_text());check(f'{w} prior history collapsed',not page.locator('.vision-history').evaluate('e=>e.open'))
  page.locator('.vision-history > summary').click();check(f'{w} old error preserved in history','OLD FAILURE' in page.locator('[data-history]').inner_text());check(f'{w} file check survived polls',page.locator('.vision-inspection').count()==1);page.locator('.vision-history > summary').click()
  result='failure';test_start();page.wait_for_function("document.querySelector('[data-test-output]').textContent.includes('CURRENT LEGITIMATE')");check(f'{w} genuine new failure not hidden','CURRENT LEGITIMATE FAILURE' in page.locator('[data-test-output]').inner_text());check(f'{w} no old success inside failed modal','CURRENT SUCCESS' not in page.locator('[data-test-output]').inner_text());page.locator('[data-test-close]').click()
  result='hold';test_start();page.wait_for_selector('[data-test-cancel]:visible');check(f'{w} running disables duplicate start',page.locator('[data-test-run]').is_disabled());page.locator('[data-test-cancel]').click();page.wait_for_function("document.querySelector('[data-test-output]').textContent.includes('cancelled')");check(f'{w} cancel exact action',actions[0]['status']=='cancelled');check(f'{w} old failure unchanged after cancel',actions[-1]['status']=='failed');page.locator('[data-test-close]').click()
  page.evaluate("ZI18n.setLanguage('it')");page.wait_for_timeout(100);check(f'{w} Italian latest label','Ultima operazione' in page.locator('.vision-current').inner_text());check(f'{w} Italian history label','Test e operazioni precedenti' in page.locator('.vision-history > summary').inner_text());page.screenshot(path=str(OUT/f'vision_history_{w}.png'),full_page=True)
  ctx.close()
 browser.close()
(OUT/'report.json').write_text(json.dumps({'type':'Actual shared JS, simulated actions only; no Vision inference','checks':checks,'errors':errors,'requests':calls},indent=2));print('CHECKS',len(checks),'FAILS',sum(not x['passed'] for x in checks),'ERRORS',errors)
if errors or any(not x['passed'] for x in checks):raise SystemExit(1)
