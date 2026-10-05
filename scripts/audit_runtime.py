#!/usr/bin/env python3
"""Read-only installed-runtime inventory and optional PyPI advisory check.
Sends package names/public versions to pypi.org only with --online.
No model import, dataset access, uploads, pip install or automatic repair.
A missing feed result is UNKNOWN, never a clean/security-certified result.
Apache-2.0. Zetalvx Image Lab - SDXL Edition 1.0.1.
"""
from __future__ import annotations
import argparse, concurrent.futures, datetime, hashlib, json, os, re, ssl, subprocess, sys, tempfile
from pathlib import Path
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from core.platform_support import venv_python, default_data_root
from core.runtime_security import reviewed_torch_version, ADVISORY
def hidden_kwargs():
    return {"creationflags": 0x08000000} if os.name=="nt" else {}
QUERY = r"""
import importlib.metadata as m, json, sys
out=[]
for d in m.distributions():
 i=d.metadata
 out.append({'name':i.get('Name',''),'version':d.version,
  'license_expression':i.get('License-Expression',''),
  'license_metadata':(i.get('License','') or '')[:12000],
  'license_classifiers':[c for c in i.get_all('Classifier',[]) if c.startswith('License ::')]})
print(json.dumps({'python':sys.version.split()[0], 'packages':sorted(out,key=lambda p:p['name'].casefold())}))
"""
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected advisory endpoint redirect')

def inventory(executable):
    if not Path(executable).is_file():
        return {'state':'NOT_INSTALLED','packages':[]}
    try:
        p=subprocess.run([str(executable),'-I','-c',QUERY],capture_output=True,text=True,timeout=45,check=True, **hidden_kwargs())
        data=json.loads(p.stdout)
        if not isinstance(data.get('packages'),list):raise ValueError('Invalid inventory')
        return {'state':'INVENTORIED',**data}
    except (OSError,subprocess.SubprocessError,ValueError) as exc:
        return {'state':'UNKNOWN','error':str(exc)[:1000],'packages':[]}

def advisory_key(package):
    name=str(package['name']);version=str(package['version'])
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',name):
        raise ValueError('Unrecognized distribution name')
    canonical=re.sub(r'[-_.]+','-',name).lower()
    # PyTorch CUDA/CPU wheels refer to the same public Python-package release.
    # This does NOT audit vendor libraries embedded in that wheel.
    public=version.split('+',1)[0] if canonical in {'torch','torchvision','torchaudio'} else version
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_-]*',public):
        raise ValueError('Unrecognized distribution version')
    return canonical,public

def fetch_advisories(package):
    try:
        name,version=advisory_key(package)
        url=f'https://pypi.org/pypi/{name}/{version}/json'
        opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
        with opener.open(Request(url,headers={'User-Agent':'Zetalvx-SDXL-Release-Audit/1.0.1'}),timeout=12) as response:
            raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('Advisory response too large')
        data=json.loads(raw)
        if not isinstance(data.get('vulnerabilities'),list):raise ValueError('Advisory field is absent')
        if re.sub(r'[-_.]+','-',data.get('info',{}).get('name','')).lower()!=name:
            raise ValueError('Advisory package identity mismatch')
        if str(data.get('info',{}).get('version',''))!=version:
            raise ValueError('Advisory release identity mismatch')
        active=[v for v in data['vulnerabilities'] if not v.get('withdrawn')]
        return {'state':'ADVISORIES_FOUND' if active else 'NO_KNOWN_ADVISORIES_IN_CHECKED_FEED',
                'queried_public_version':version,'url':url,'advisories':active,
                'response_sha256':hashlib.sha256(raw).hexdigest()}
    except Exception as exc:
        return {'state':'UNKNOWN','error':type(exc).__name__+': '+str(exc)[:800]}

def audit(executables, online=False, fetcher=fetch_advisories):
    report={'schema':'zetalvx.runtime-audit.v1','version':'1.0.1',
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'online':bool(online),'runtimes':{},'issues':[],
        'limitations':['Only installed Python distribution metadata and one advisory feed.',
          'No guarantee against unknown vulnerabilities or malicious code.',
          'No GPU, model, binary provenance, CUDA/DLL/license-source compliance validation.',
          'Local paths/Python versions may be identifying. Review reports before sharing.',
          'License metadata is declared information, not a complete license audit.']}
    for label,exe in executables.items():
        data=inventory(exe);report['runtimes'][label]={'executable':str(exe),**data}
        if data['state']!='INVENTORIED':
            report['issues'].append({'runtime':label,'state':data['state']});continue
        packages=data['packages']
        if online:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                checks=list(pool.map(fetcher,packages))
        else:checks=[{'state':'NOT_CHECKED_OFFLINE'} for _ in packages]
        for p,check in zip(packages,checks):
            p['advisory_check']=check
            if p['name'].lower()=='torch' and not reviewed_torch_version(p['version']):
                report['issues'].append({'runtime':label,'package':p['name'],'version':p['version'],
                    'state':'BLOCKED_REVIEWED_TORCH_FLOOR','source':ADVISORY})
            if check['state']!='NO_KNOWN_ADVISORIES_IN_CHECKED_FEED':
                report['issues'].append({'runtime':label,'package':p['name'],'version':p['version'],'state':check['state']})
    states={i['state'] for i in report['issues']}
    report['result']=('BLOCKED' if states & {'ADVISORIES_FOUND','BLOCKED_REVIEWED_TORCH_FLOOR'}
        else 'INCOMPLETE' if report['issues'] or not executables or not online
        else 'NO_KNOWN_ADVISORIES_IN_CHECKED_FEED')
    report['release_approved']=False
    return report

def write_report(path,data):
    path=Path(path).expanduser();path.parent.mkdir(parents=True,exist_ok=True)
    # Deliberately refuse overwriting a previous report.
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=Path,default=default_data_root())
    p.add_argument('--python',type=Path,help='Audit one trusted runtime executable instead of a home')
    p.add_argument('--online',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.python:executables={'selected':args.python.expanduser().absolute()}
    else:
        executables={n:venv_python(args.home.expanduser()/'runtime'/n) for n in ('app','sdxl','vision')
                     if venv_python(args.home.expanduser()/'runtime'/n).is_file()}
    report=audit(executables,args.online);write_report(args.output,report)
    print(json.dumps({'result':report['result'],'report':str(args.output),'issues':len(report['issues']),
       'release_approved':False},indent=2))
    raise SystemExit(0 if report['result']=='NO_KNOWN_ADVISORIES_IN_CHECKED_FEED' else 2)
if __name__=='__main__':main()
