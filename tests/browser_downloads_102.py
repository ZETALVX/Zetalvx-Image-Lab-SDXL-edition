"""Actual Chromium + local HTTPS binary fixture; NOT actual Flask/Cheroot/iOS.
No user credentials/weights. TLS trust in Chromium is bypassed only for this
throwaway self-signed fixture; this cannot certify Safari certificate behavior.
"""
import argparse,hashlib,json,ssl,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.local_certificate import generate_certificate
ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];seen=[]
def check(name,passed):
 checks.append({'name':name,'passed':bool(passed)});print(name,passed,flush=True)
 if not passed:raise AssertionError(name)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
with tempfile.TemporaryDirectory(prefix='sdxl102-browser-') as td:
 root=Path(td);generate_certificate(root/'tls')
 small=root/'small.bin';large=root/'large.bin';pattern=bytes(range(256))*4096
 for p,size in [(small,93065304),(large,128*1024*1024+1)]:
  with p.open('wb') as f:
   while size:n=min(size,len(pattern));f.write(pattern[:n]);size-=n
 hashes={small.name:sha(small),large.name:sha(large)}
 class Handler(BaseHTTPRequestHandler):
  protocol_version='HTTP/1.1'
  def log_message(self,*args):pass
  def do_POST(self):
   n=int(self.headers.get('Content-Length','0'));self.rfile.read(n)
   self.send_response(204);self.send_header('Set-Cookie','fixture_session=ok; Path=/; HttpOnly; Secure; SameSite=Strict');self.send_header('Content-Length','0');self.end_headers()
  def do_HEAD(self):self.serve(True)
  def do_GET(self):self.serve(False)
  def serve(self,head):
   path=urlsplit(self.path).path;seen.append({'path':path,'method':self.command,'authenticated':'fixture_session=ok' in self.headers.get('Cookie','')})
   if path=='/':
    body=b'''<!doctype html><meta charset="utf-8"><div><a data-safe-download id="small" href="/small/download">Small</a></div><div><a data-safe-download id="large" href="/large/download">Large</a></div><div><a data-safe-download id="missing" href="/missing/download">Missing</a></div><div><a data-safe-download id="invalid" href="/invalid/download">Invalid</a></div><div><a data-safe-download id="changed" href="/changed/download">Changed</a></div><div><a data-safe-download id="foreign" href="https://foreign.invalid/file">Foreign</a></div><script src="/download-script.js"></script>'''
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
    if not head:self.wfile.write(body)
    return
   if path=='/download-script.js':
    body=(ROOT/'static/file-downloads.js').read_bytes();self.send_response(200);self.send_header('Content-Type','application/javascript');self.send_header('Content-Length',str(len(body)));self.end_headers()
    if not head:self.wfile.write(body)
    return
   if 'fixture_session=ok' not in self.headers.get('Cookie','') or path=='/missing/download':
    status=401 if 'fixture_session=ok' not in self.headers.get('Cookie','') else 404
    body=b'{"error":"fixture error"}';self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
    if not head:self.wfile.write(body)
    return
   if path=='/invalid/download':
    body=b'{"error":"not a weight"}';self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
    if not head:self.wfile.write(body)
    return
   p=large if path=='/large/download' else small
   if path=='/changed/download':p=small if head else large
   size=p.stat().st_size
   self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition',"attachment; filename=\"step.safetensors\"; filename*=UTF-8''prova%20%C3%A8.safetensors");self.send_header('Content-Length',str(size));self.send_header('Cache-Control','private, no-store');self.end_headers()
   if head:return
   try:
    with p.open('rb') as f:
     for b in iter(lambda:f.read(1024*1024),b''):self.wfile.write(b)
   except (BrokenPipeError,ConnectionResetError,ssl.SSLError):pass
 srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'tls/cert.pem',root/'tls/key.pem');srv.socket=ctx.wrap_socket(srv.socket,server_side=True)
 thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start();base='https://127.0.0.1:'+str(srv.server_port)
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   for width,height in [(390,844),(1440,1000)]:
    context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True,ignore_https_errors=True)
    page=context.new_page();page.set_default_timeout(10000);page.on('pageerror',lambda e:errors.append(str(e)));downloads=[];page.on('download',lambda d:downloads.append(d))
    page.goto(base);page.locator('#small').click();page.wait_for_function("document.querySelector('[data-file-download-status]').textContent.includes('Session expired')")
    check(f'{width} unauthenticated export rejected',len(downloads)==0)
    page.evaluate("fetch('/login',{method:'POST',credentials:'same-origin'})")
    check(f'{width} secure httponly session cookie',any(c['secure'] and c['httpOnly'] for c in context.cookies()))
    start=len(seen)
    with page.expect_download(timeout=45000) as info:page.locator('#small').click()
    d=info.value;dest=root/f'result{width}.bin';d.save_as(dest)
    check(f'{width} 93MB exact SHA256',sha(dest)==hashes[small.name]);check(f'{width} unicode name',d.suggested_filename=='prova è.safetensors')
    req=[x for x in seen[start:] if x['path']=='/small/download']
    check(f'{width} HEAD+GET same session',[(x['method'],x['authenticated']) for x in req]==[('HEAD',True),('GET',True)])
    dest.unlink()
    for name,text in [('missing','404'),('invalid','downloadable file'),('changed','size changed'),('foreign','same-origin')]:
     count=len(downloads);page.locator('#'+name).click();page.wait_for_function("([id,text])=>document.querySelector('#'+id).parentElement.textContent.includes(text)",arg=[name,text])
     check(f'{width} {name} error not downloaded',len(downloads)==count)
    if width==1440:
     start=len(seen)
     with page.expect_download(timeout=45000) as info:page.locator('#large').click()
     d=info.value;dest=root/'large-result.bin';d.save_as(dest)
     check('large >128MiB native full SHA256',sha(dest)==hashes[large.name])
     check('large native branch reported', 'handed to the browser' in page.locator('#large').evaluate('e=>e.parentElement.textContent'))
     check('large HEAD+GET cookie',[(x['method'],x['authenticated']) for x in seen[start:] if x['path']=='/large/download']==[('HEAD',True),('GET',True)])
     dest.unlink()
    context.close()
   browser.close()
 finally:srv.shutdown();srv.server_close();thread.join(5)
(out/'report.json').write_text(json.dumps({'checks':checks,'errors':errors,'test_type':'Chromium desktop + 390px viewport on local HTTPS fixture, not actual application HTTP stack or iPhone','small_bytes':93065304,'large_bytes':128*1024*1024+1,'chromium_fixture_trust_bypassed':True},indent=2))
print('CHECKS',len(checks),'ERRORS',errors)
if errors:raise SystemExit(1)
