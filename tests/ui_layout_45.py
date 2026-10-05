from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import argparse,json
P=argparse.ArgumentParser();P.add_argument('--output',default='ui-layout-45');P.add_argument('--chromium',default='/usr/bin/chromium');a=P.parse_args()
ROOT=Path(__file__).resolve().parents[1];OUT=Path(a.output);OUT.mkdir(parents=True,exist_ok=True)
soup=BeautifulSoup((ROOT/'templates/index.html').read_text(encoding='utf-8'),'html.parser');css=[]
for tag in soup.find_all('link',href=True):
    p=tag['href'].split('?',1)[0]
    if p.startswith('/static/') and p.endswith('.css'):css.append(p[8:])
for t in soup.find_all(['script','link']):t.decompose()
checks=[]
def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail});assert ok,(name,detail)
with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True,executable_path=a.chromium,args=['--no-sandbox'])
    for w,h in [(320,800),(375,812),(390,844),(430,932)]:
        p=b.new_page(viewport={'width':w,'height':h});p.set_content(str(soup))
        for f in css:p.add_style_tag(content=(ROOT/'static'/f).read_text(encoding='utf-8'))
        p.evaluate("""() => {document.body.classList.add('image-simple-mode');document.querySelectorAll('.view').forEach(e=>e.style.display='none');view=document.querySelector('#view-image');view.style.display='block';checkpointWrap.classList.remove('hidden');checkpointSelect.innerHTML='<option>Model default · C:\\\\Users\\\\ExampleUser\\\\AppData\\\\Local\\\\CreatorStudioSDXL\\\\models\\\\SDXL\\\\very_long_checkpoint_name.safetensors</option>';inputPanel.classList.add('hidden')}""")
        d=p.evaluate('({i:innerWidth,d:document.documentElement.scrollWidth,v:view.scrollWidth,c:view.clientWidth})');check(f'{w} create document has no horizontal overflow',d['d']<=d['i']+1,d)
        p.close()
    p=b.new_page(viewport={'width':1440,'height':1000});p.set_content(str(soup))
    for f in css:p.add_style_tag(content=(ROOT/'static'/f).read_text(encoding='utf-8'))
    p.evaluate("""() => {document.querySelectorAll('.view').forEach(e=>e.style.display='none');view=document.querySelector('#view-image');view.style.display='block';inputPanel.classList.add('hidden');document.body.classList.add('image-simple-mode');mainPreview.innerHTML='<img class="main-image" src="data:image/svg+xml,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"768\" height=\"768\"></svg>">'}""")
    d=p.evaluate('''() => {const a=imageControlsColumn.getBoundingClientRect(),b=document.querySelector('#imagePreviewColumn>.preview-card').getBoundingClientRect();return {controls:a.height,preview:b.height,diff:Math.abs(a.height-b.height)}}''');check('desktop create cards share row height',d['diff']<2,d)
    b.close()
(OUT/'report.json').write_text(json.dumps({'checks':checks},indent=2),encoding='utf-8');print('CHECKS',len(checks),'FAILS',sum(not x['passed'] for x in checks))
