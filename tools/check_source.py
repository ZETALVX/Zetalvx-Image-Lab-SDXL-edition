#!/usr/bin/env python3
"""Read-only source integrity/syntax checker. Does not import the app or install anything."""
from __future__ import annotations
import argparse, ast, hashlib, json, subprocess, sys, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True

def check(root=ROOT, *, manifest=True, javascript=False):
    root=Path(root);errors=[];counts={'python_files':0,'json_files':0,'manifest_files':0,'javascript_files':0}
    for p in sorted(root.rglob('*')):
        if not p.is_file() or any(part in {'.git','__pycache__','release-reports','.venv','runtime','shared','models'} for part in p.relative_to(root).parts):continue
        rel=p.relative_to(root).as_posix()
        try:
            if p.suffix=='.py':
                compile(p.read_text(encoding='utf-8-sig'),rel,'exec');counts['python_files']+=1
            elif p.suffix=='.json':
                json.loads(p.read_text(encoding='utf-8-sig'));counts['json_files']+=1
            elif javascript and p.suffix in {'.js','.cjs'}:
                node=shutil.which('node')
                if not node:raise ValueError('node is required for --javascript')
                result=subprocess.run([node,'--check',str(p)],capture_output=True,text=True,timeout=30)
                if result.returncode:raise ValueError(result.stderr.strip())
                counts['javascript_files']+=1
        except Exception as exc:errors.append(f'{rel}: {exc}')
    if manifest:
        try:
            entries=(root/'MANIFEST.sha256').read_text().splitlines();seen=set()
            for line in entries:
                if not line.strip():continue
                digest,name=line.split('  ',1);p=root/name
                if name in seen or Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Unsafe/duplicate manifest path: '+name)
                seen.add(name)
                if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
                    errors.append('Checksum mismatch: '+name)
                counts['manifest_files']+=1
        except Exception as exc:errors.append('Manifest: '+str(exc))
    return {'ok':not errors,'counts':counts,'errors':errors,'runtime_or_gpu_validated':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--no-manifest',action='store_true');p.add_argument('--javascript',action='store_true');p.add_argument('--report',type=Path);a=p.parse_args()
    result=check(manifest=not a.no_manifest,javascript=a.javascript)
    text=json.dumps(result,indent=2);print(text)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(text+'\n',encoding='utf-8')
    return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
