#!/usr/bin/env python3
"""Preview/apply a recorded Windows firewall change; never reset the system firewall."""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.network_access import restore_firewall
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('journal',type=Path);p.add_argument('--home',type=Path);p.add_argument('--apply',action='store_true')
a=p.parse_args()
try:
    result=restore_firewall(a.journal,home=a.home,apply=False)
    print(json.dumps(result,indent=2))
    if a.apply:
        answer=input('Re-enable only recorded, unchanged Block rules? This may close LAN access. Type RESTORE: ')
        if answer.strip()!='RESTORE':raise SystemExit('Cancelled. No firewall change.')
        print(json.dumps(restore_firewall(a.journal,home=a.home,apply=True),indent=2))
except (OSError,ValueError,RuntimeError) as e:
    print('ERROR:',e,file=sys.stderr);raise SystemExit(1)
