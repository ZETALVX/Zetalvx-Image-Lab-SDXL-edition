#!/usr/bin/env python3
# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
"""Inventory installed runtimes without importing AI packages or reading user data.
Writes one private JSON report; no network, package installation, or server changes.
"""
from __future__ import annotations
import argparse,datetime,json,os,platform,shutil,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.platform_support import venv_python, default_data_root
def hidden_kwargs():
    return {"creationflags": 0x08000000} if os.name=="nt" else {}
QUERY=r'''
import importlib.metadata as m,json,sys
out=[]
for d in m.distributions():
    info=d.metadata
    out.append({'name':info.get('Name',''), 'version':d.version,
      'license_expression':info.get('License-Expression',''),
      'license_metadata':(info.get('License','') or '')[:600],
      'license_classifiers':[s for s in info.get_all('Classifier',[]) if s.startswith('License ::')]})
print(json.dumps({'python':sys.version,'packages':sorted(out,key=lambda x:x['name'].casefold())}))
'''
def run(args,timeout=40):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout,check=False, **hidden_kwargs())
    if p.returncode:raise RuntimeError('Command failed, exit '+str(p.returncode))
    return p.stdout

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--home',default=os.getenv('SDXL_STUDIO_HOME',str(default_data_root())));parser.add_argument('--output');args=parser.parse_args()
    root=Path(args.home).expanduser().resolve()
    report={'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'system':platform.platform(),'data_root':str(root),'scope':'installed package metadata and system FFmpeg only; no weights, datasets, captions, account files or tokens','runtimes':{},'warnings':[]}
    for label in ('app','sdxl','vision'):
        py=venv_python(root/'runtime'/label)
        if not py.is_file():report['runtimes'][label]={'installed':False};continue
        try:report['runtimes'][label]={'installed':True,**json.loads(run([py,'-I','-c',QUERY]))}
        except Exception as e:report['runtimes'][label]={'installed':True,'error':type(e).__name__+': '+str(e)}
    exe=shutil.which('ffmpeg')
    if exe:
        try:report['ffmpeg']={'path':exe,'version':run([exe,'-version'],15)[:16000],'buildconf':run([exe,'-buildconf'],15)[:16000]}
        except Exception as e:report['ffmpeg']={'error':str(e)}
    else:report['ffmpeg']={'installed':False}
    report['warnings'].append('Declared license metadata is not a complete license audit or vulnerability scan; review bundled dependencies and model licenses separately.')
    out=Path(args.output).expanduser() if args.output else root/'shared/audits'/('runtime-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    print(out)
if __name__=='__main__':main()
