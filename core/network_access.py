# Modified in Zetalvx 0.1.0.42: targeted pre-release stabilization; see audit/STABILIZATION_0_1_0_42.md.
"""Windows LAN/firewall diagnostics and explicit repair for Zetalvx Image Lab.

No firewall changes are made silently. The GUI must request the repair after the
user confirms it. Existing Block rules are disabled only when they target the
exact executable hosting this Zetalvx Image Lab process and the user explicitly
allows conflict repair.
"""
from __future__ import annotations
import base64, hashlib, json, os, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from core.platform_support import hidden_kwargs, default_data_root
from core.private_files import private_directory
from core.safe_paths import is_link

RULE_NAME = 'Zetalvx Creator Studio LAN'


def host_program(program=None):
    program=str(program or sys.executable)
    if os.name!='nt' or os.path.normcase(program)!=os.path.normcase(sys.executable):return program
    import ctypes
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=(w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD))
    kernel.QueryFullProcessImageNameW.restype=w.BOOL
    n=w.DWORD(32768);buf=ctypes.create_unicode_buffer(n.value)
    if not kernel.QueryFullProcessImageNameW(kernel.GetCurrentProcess(),0,buf,ctypes.byref(n)):raise ctypes.WinError(ctypes.get_last_error())
    return buf.value


def _q(value):
    return "'" + str(value).replace("'", "''") + "'"


def _ps_json(script: str, timeout=25):
    r = subprocess.run(
        ['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
        capture_output=True, text=True, timeout=timeout, check=True, **hidden_kwargs()
    )
    raw = r.stdout.strip()
    return json.loads(raw) if raw else {}


def firewall_status(port: int, program=None):
    port = int(port)
    program = host_program(program)
    if os.name != 'nt':
        return {
            'supported': False, 'platform': 'linux', 'rule_name': RULE_NAME,
            'port': port, 'program': program, 'needs_fix': False,
            'conflicting_blocks': []
        }
    script = f"""$ErrorActionPreference='Stop'
$Program={_q(program)}
$RuleName={_q(RULE_NAME)}
$Port={port}
$rule=Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Select-Object -First 1
$portFilter=$null;$addrFilter=$null
if($rule){{$portFilter=$rule|Get-NetFirewallPortFilter;$addrFilter=$rule|Get-NetFirewallAddressFilter}}
$blocks=@()
Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Where-Object {{$_.Program -ieq $Program}} | ForEach-Object {{
 $app=$_
 Get-NetFirewallRule -AssociatedNetFirewallApplicationFilter $app -ErrorAction SilentlyContinue | Where-Object {{
   $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' -and (($_.Profile.ToString()) -match 'Public|Any')
 }} | ForEach-Object {{$blocks += [pscustomobject]@{{name=$_.Name;display_name=$_.DisplayName;profile=$_.Profile.ToString();program=$app.Program}}}}
}}
$profile=Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object {{$_.IPv4Connectivity -ne 'Disconnected'}} | Select-Object -First 1
$out=[pscustomobject]@{{
 supported=$true;platform='windows';rule_name=$RuleName;port=$Port;program=$Program;
 rule_present=[bool]$rule;rule_enabled=if($rule){{$rule.Enabled -eq 'True'}}else{{$false}};
 rule_action=if($rule){{$rule.Action.ToString()}}else{{''}};rule_profile=if($rule){{$rule.Profile.ToString()}}else{{''}};
 rule_port=if($portFilter){{$portFilter.LocalPort.ToString()}}else{{''}};
 remote_address=if($addrFilter){{$addrFilter.RemoteAddress -join ','}}else{{''}};
 network_profile=if($profile){{$profile.NetworkCategory.ToString()}}else{{''}};
 conflicting_blocks=$blocks
}}
$out | ConvertTo-Json -Depth 6 -Compress"""
    try:
        d = _ps_json(script)
    except Exception as exc:
        return {
            'supported': True, 'platform': 'windows', 'rule_name': RULE_NAME,
            'port': port, 'program': program, 'query_error': str(exc),
            'needs_fix': True, 'conflicting_blocks': []
        }
    if isinstance(d.get('conflicting_blocks'), dict):
        d['conflicting_blocks'] = [d['conflicting_blocks']]
    d.setdefault('conflicting_blocks', [])
    remote = str(d.get('remote_address') or '')
    d['rule_ok'] = bool(
        d.get('rule_present') and d.get('rule_enabled') and
        str(d.get('rule_action')) == 'Allow' and
        str(d.get('rule_port')) == str(port) and
        ('LocalSubnet' in remote or remote == 'Any')
    )
    d['needs_fix'] = not d['rule_ok'] or bool(d['conflicting_blocks'])
    return d


def _journal_root(home=None):
    home=Path(home or os.environ.get('SDXL_STUDIO_HOME') or default_data_root()).absolute()
    root=home/'shared/audits/firewall'
    for p in (home,home/'shared',home/'shared/audits',root):
        if is_link(p):raise ValueError('Firewall journal cannot traverse a link')
    return private_directory(root)

def _run_elevated(body,params,journal,timeout=150):
    # The elevated command is encoded, not read as code from a user-writable temporary script.
    folder=journal.parent;result=folder/('result-'+uuid.uuid4().hex+'.json')
    inputs={**params,'Journal':str(journal),'Result':str(result)}
    lines=[]
    for key,value in inputs.items():
        val=('$true' if value else '$false') if type(value) is bool else str(value) if type(value) is int else _q(value)
        lines.append('$'+key+'='+val)
    encoded=base64.b64encode(('\n'.join(lines)+'\n'+body).encode('utf-16le')).decode('ascii')
    wrapper="$p=Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',"+_q(encoded)+"); exit $p.ExitCode"
    proc=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-Command',wrapper],capture_output=True,text=True,timeout=timeout,**hidden_kwargs())
    if not result.is_file():raise RuntimeError('Firewall authorization cancelled or failed. No success was recorded.')
    data=json.loads(result.read_text(encoding='utf-8-sig'))
    if not data.get('ok'):raise RuntimeError(str(data.get('error') or 'Firewall operation failed')+'; journal: '+str(journal))
    return data

def configure_firewall(port:int,*,disable_conflicts=False,program=None,timeout=150,home=None):
    if os.name!='nt':raise RuntimeError('Windows Firewall configuration is only available on Windows.')
    port=int(port)
    if not 1<=port<=65535:raise ValueError('Invalid port')
    program=host_program(program)
    folder=private_directory(_journal_root(home)/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]))
    journal=folder/'journal.json'
    managed='Zetalvx-LAN-'+uuid.uuid4().hex
    body=(Path(__file__).resolve().parents[1]/'scripts/firewall_operation.ps1').read_text(encoding='utf-8')
    return _run_elevated(body,{'Operation':'configure','Program':program,'Port':port,'DisableConflicts':bool(disable_conflicts),'ManagedName':managed},journal,timeout)

def restore_firewall(journal,*,home=None,apply=False,timeout=150):
    if os.name!='nt':raise RuntimeError('Windows Firewall restore is available only on Windows.')
    root=_journal_root(home);journal=Path(journal).absolute()
    if journal.name!='journal.json' or journal.parent.parent.resolve()!=root.resolve() or is_link(journal.parent) or is_link(journal):raise ValueError('Select an original journal from shared/audits/firewall')
    data=json.loads(journal.read_text(encoding='utf-8-sig'))
    if data.get('schema')!=1 or data.get('state')=='restored':raise ValueError('Invalid or already restored journal')
    if not apply:return {'preview':True,'journal':str(journal),'disabled_blocks':[x.get('snapshot',{}).get('name') for x in data.get('disabled',[]) if x.get('changed')],'created_rule':data.get('created_rule',{}),'warning':'Restoring these blocks can prevent LAN access again.'}
    body=(Path(__file__).resolve().parents[1]/'scripts/firewall_operation.ps1').read_text(encoding='utf-8')
    return _run_elevated(body,{'Operation':'restore'},journal,timeout)
