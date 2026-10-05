#!/usr/bin/env python3
"""Review an existing runtime_inventory JSON without importing GPU libraries or contacting servers.
This is a bounded list of observations, not a comprehensive vulnerability/license scanner.
"""
import argparse, json, re
from pathlib import Path

def summarize(data):
    envs={};names=set();warnings=[]
    for name, value in data.get('runtimes',{}).items():
        pkgs={str(p.get('name','')).lower().replace('_','-'):p for p in value.get('packages',[])}
        names.update(pkgs)
        envs[name]={'installed':bool(value.get('installed')), 'package_count':len(pkgs),
                   'python':value.get('python',''), 'torch':pkgs.get('torch',{}).get('version','')}
        t=envs[name]['torch']
        if t:
            m=re.match(r'^(\d+)\.(\d+)\.(\d+)',t)
            if m:
                v=tuple(int(i) for i in m.groups())
                if v<=(2,5,1):warnings.append({'runtime':name,'code':'GHSA-53q9-r3pm-6pq6','version':t,'action':'Known affected torch.load version. No automatic runtime upgrade performed.'})
                if v<=(2,9,1):warnings.append({'runtime':name,'code':'GHSA-63cw-57p8-fm3p','version':t,'action':'Known affected checkpoint loader. Upstream lists >=2.10.0 for this specific fix; test a coordinated runtime migration.'})
            else:warnings.append({'runtime':name,'code':'version_unparsed','version':t})
        for pkg in ('easydict','certifi','tqdm'):
            p=pkgs.get(pkg)
            if p:
                warnings.append({'runtime':name,'code':'review_license','package':pkg,'version':p.get('version'),
                  'declared_license':p.get('license_expression') or p.get('license_metadata') or p.get('license_classifiers'),
                  'action':'Keep covered library license/source obligations separate from the app license; metadata is not full license text.'})
    ff=data.get('ffmpeg',{});conf=ff.get('buildconf','')+' '+ff.get('version','')
    return {'collected_utc':data.get('collected_utc'), 'scope':'Input JSON package metadata + system FFmpeg, no on-device inspection or complete CVE scan',
            'runtimes':envs,'distribution_records':sum(e['package_count'] for e in envs.values()),'unique_names':len(names),
            'ffmpeg':{'present':bool(ff.get('path')),'gpl_enabled':'--enable-gpl' in conf,'nonfree_enabled':'--enable-nonfree' in conf},
            'observations':warnings, 'limitations':['Managed Vision runtime absent does not assess external llama.cpp or APIs.','No weights, authentication data, library license texts or individual grants were audited.','No environment or dependency is modified.','Fixed range in one advisory does not certify a version free of other vulnerabilities.']}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('inventory',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
    if a.inventory.stat().st_size>8*1024*1024:ap.error('Inventory exceeds 8 MiB.')
    data=json.loads(a.inventory.read_text(encoding='utf-8'));text=json.dumps(summarize(data),ensure_ascii=False,indent=2)+'\n'
    if a.output:
        # Do not overwrite an existing audit accidentally.
        with a.output.open('x',encoding='utf-8') as f:f.write(text)
    else:print(text,end='')
if __name__=='__main__':main()
