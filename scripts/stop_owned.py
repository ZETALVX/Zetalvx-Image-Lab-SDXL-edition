"""Installer-side recovery uses the new lifecycle code even when updating .32."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.app_lifecycle import stop_owned
from core.listener_check import wait_ports
p=argparse.ArgumentParser();p.add_argument('--home',required=True);a=p.parse_args()
home=Path(a.home);print('Stopped verified services:',stop_owned(home),flush=True)
f=home/'shared/config/settings.json';wait_ports(json.loads(f.read_text()) if f.exists() else {})
print('Services stopped; configured listener ports released.',flush=True)
