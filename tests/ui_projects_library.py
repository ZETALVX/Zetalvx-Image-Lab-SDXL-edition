import argparse,json,sys
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',default='');args=ap.parse_args();checks=[]
projects=[
 {'id':'a'*32,'name':'Alpha','description':'First','sort_order':10,'trashed':0,'created_at':'2026-01-01'},
 {'id':'b'*32,'name':'Beta','description':'Second','sort_order':20,'trashed':0,'created_at':'2026-01-02'},
 {'id':'c'*32,'name':'Gamma','description':'Third','sort_order':30,'trashed':0,'created_at':'2026-01-03'},
]
arts=[
 {'id':'1'*32,'type':'image','url':'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==','metadata':{'model_id':'sdxl','model_name':'SDXL','tool':'generate_image','params':{'seed':1}},'created_at':'2026-01-01'},
 {'id':'2'*32,'type':'image','url':'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==','metadata':{'model_id':'sdxl','model_name':'SDXL','tool':'inpaint','params':{'seed':2}},'created_at':'2026-01-02'},
]
def proj(pid):
 p=next(x for x in projects if x['id']==pid).copy();p.update(state={},artifacts=arts,jobs=[],messages=[]);return p

def mock(url,method='GET',body=None):
 from urllib.parse import urlsplit
 path=urlsplit(url).path;d=json.loads(body) if isinstance(body,str) and body.startswith('{') else {}
 if path=='/api/session/tokens': return {'tokens':{'model-hub':'m','vision':'v'}}
 if path=='/api/bootstrap': return {'projects':projects,'models':[],'recipes':[],'loras':[],'checkpoints':[],'runtime':{'ok':False},'user_image_presets':[],'image_preset_bindings':{}}
 if path.startswith('/api/projects/') and path.endswith('/move'):
  pid=path.split('/')[3];i=next(i for i,x in enumerate(projects) if x['id']==pid);j=i-1 if d.get('direction')=='up' else i+1
  if 0<=j<len(projects):projects[i],projects[j]=projects[j],projects[i];
  for k,x in enumerate(projects):x['sort_order']=(k+1)*10
  return {'ok':True,'changed':True}
 if path.startswith('/api/projects/') and method=='PUT' and not path.endswith('/active-artifact'):
  pid=path.split('/')[3];p=next(x for x in projects if x['id']==pid);p['name']=d['name'];p['description']=d.get('description','');return {'ok':True,'project':proj(pid)}
 if path.startswith('/api/projects/') and path.count('/')==3:return {'project':proj(path.split('/')[3])}
 if path=='/api/model-hub/status':return {'local_catalog':{'checkpoint':[],'lora':[],'sources':[]},'models':[],'sdxl':{},'checkpoints':[],'loras':[],'settings':{},'identity':{},'catalog':{},'accounts':{},'jobs':[],'vaes':[]}
 if path=='/api/model-hub/local':return {'catalog':{'checkpoint':[],'lora':[],'sources':[]}}
 if path=='/api/setup':return {'settings':{},'models':[],'image_runtime':{},'identity_runtime':{},'training_runtime':{}}
 if path=='/api/account':return {'username':'C'}
 if path.startswith('/api/vision'):return {'models':[],'actions':[],'jobs':[],'runtime':{}}
 if path=='/api/training/bootstrap':return {'runtime':{},'datasets':[],'loras':[],'full_models':[],'full_unets':[],'jobs':[]}
 if path=='/api/identity/bootstrap':return {'runtime':{},'models':{},'jobs':[],'queue':{},'loras':[],'checkpoints':[]}
 return {}

with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in (390,1440):
  projects[:]=[{'id':'a'*32,'name':'Alpha','description':'First','sort_order':10,'trashed':0,'created_at':'2026-01-01'},{'id':'b'*32,'name':'Beta','description':'Second','sort_order':20,'trashed':0,'created_at':'2026-01-02'},{'id':'c'*32,'name':'Gamma','description':'Third','sort_order':30,'trashed':0,'created_at':'2026-01-03'}]
  page=browser.new_page(viewport={'width':width,'height':900});page.expose_function('_api',mock)
  raw=BeautifulSoup((ROOT/'templates/index.html').read_text(),'html.parser')
  css=[ROOT/x['href'].split('?',1)[0].lstrip('/') for x in raw.select('link[rel=stylesheet]')]
  scripts=[ROOT/x['src'].split('?',1)[0].lstrip('/') for x in raw.select('script[src]')]
  for x in raw.find_all(['script','link']):x.decompose()
  raw.head.append(raw.new_tag('base',href='http://ui.local/'));page.set_content(str(raw))
  page.evaluate("""()=>{const st={};Object.defineProperty(window,'localStorage',{value:{getItem:k=>st[k]||null,setItem:(k,v)=>st[k]=String(v),removeItem:k=>delete st[k]}});window.fetch=async(u,o={})=>{const d=await window._api(String(u),o.method||'GET',o.body||null);return new Response(JSON.stringify(d),{status:200,headers:{'Content-Type':'application/json'}})}}""")
  for f in css:page.add_style_tag(content=f.read_text())
  for f in scripts:page.add_script_tag(content=f.read_text())
  page.wait_for_timeout(600);page.evaluate("showView('projects')")
  assert page.locator('[data-rename-project]').count()==3;checks.append({'viewport':width,'check':'rename controls','passed':True})
  assert page.locator('[data-move-project]').count()==6;checks.append({'viewport':width,'check':'move controls','passed':True})
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');checks.append({'viewport':width,'check':'project layout fits','passed':True})
  # open library and ensure labels are not SDXL
  page.evaluate("showView('library')");page.wait_for_timeout(100)
  texts=page.locator('#libraryGrid .asset-info>b').all_text_contents()
  assert texts==['001 · Text to image','002 · Inpaint'],texts;checks.append({'viewport':width,'check':'library operation labels','passed':True})
  # rename first project
  page.evaluate("showView('projects')");page.locator('[data-rename-project]').first.click();page.locator('#projectRenameName').fill('Renamed');page.locator('#saveProjectRename').click();page.wait_for_timeout(250)
  assert 'Renamed' in page.locator('#projectsList').inner_text();checks.append({'viewport':width,'check':'rename works','passed':True})
  # move third up
  page.locator('[data-move-project][data-direction=up]').nth(2).click();page.wait_for_timeout(250)
  names=page.locator('#projectsList .project-card:not(.trashed) .project-main b').all_text_contents();assert names[1]=='Gamma',names;checks.append({'viewport':width,'check':'move order works','passed':True})
  print('OK',width,texts,names)
  page.close()
 browser.close()

if args.output:
 Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps({'checks':checks,'count':len(checks),'passed':all(x['passed'] for x in checks)},indent=2))
