"""Native Node FormData/fetch over real loopback TLS to a MIME fixture server.
NOT a Flask/Cheroot test; validates byte transport and multipart boundaries.
"""
import argparse,hashlib,json,os,ssl,subprocess,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.local_certificate import generate_certificate
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();received=[];errors=[]
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def do_POST(self):
  raw=self.rfile.read(int(self.headers['Content-Length']))
  parts=BytesParser(policy=default).parsebytes(b'Content-Type: '+self.headers['Content-Type'].encode()+b'\r\n\r\n'+raw)
  data=[{'field':part.get_param('name',header='content-disposition'),'size':len(part.get_payload(decode=True)),'sha256':hashlib.sha256(part.get_payload(decode=True)).hexdigest()} for part in parts.iter_parts()]
  received.append(data)
  status=400 if len(received)==4 else 202;body=b'<h1>Bad Request</h1>' if status==400 else b'{"ok":true,"job_id":"fixture"}'
  self.send_response(status);self.send_header('Content-Type','text/html' if status==400 else 'application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
with tempfile.TemporaryDirectory() as td:
 generate_certificate(Path(td));server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
 ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(td+'/cert.pem',td+'/key.pem');server.socket=ctx.wrap_socket(server.socket,server_side=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 code=r'''
require(process.argv[1]);
(async()=>{const b=Buffer.alloc(1024*512,73),f=new File([b],'same.png',{type:'image/png'});for(let i=0;i<6;i++){
 const fd=new FormData();fd.append('project_id','fixture');fd.append('mode',i%2?'face_swap':'instantid');fd.append('references',f);fd.append('base_image',f);
 const body=await ZetalvxIdentitySubmit.prepare(fd);const r=await fetch(process.argv[2],{method:'POST',body});const text=await r.text();
 if(i===3){if(r.status!==400)throw Error('expected 400');if(ZetalvxIdentitySubmit.nonJsonError(r.status).submissionUncertain)throw Error('unexpected uncertainty');}
 else if(r.status!==202)throw Error(text);
}console.log('TRANSPORT_OK');})().catch(e=>{console.error(e);process.exit(1)});
'''
 try:
  env={**os.environ,'NODE_EXTRA_CA_CERTS':td+'/cert.pem'}
  r=subprocess.run(['node','-e',code,str(ROOT/'static/identity-submit.js'),'https://127.0.0.1:'+str(server.server_address[1])+'/api/identity/jobs'],env=env,capture_output=True,text=True,timeout=30)
  assert r.returncode==0,r.stdout+r.stderr
  digest=hashlib.sha256(bytes([73])*(512*1024)).hexdigest()
  assert len(received)==6
  assert all(p['sha256']==digest for req in received for p in req if p['field'] in ('references','base_image'))
  result={'requests':6,'file_parts_verified':12,'bytes_unchanged':True,'recovery_after_http400':True,'transport':'Node native fetch / HTTPS / MIME fixture, NOT Flask/Cheroot or Safari','stdout':r.stdout.strip()}
  Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps(result))
 finally:server.shutdown();server.server_close();thread.join(timeout=5)
