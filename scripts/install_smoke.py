#!/usr/bin/env python3
"""Real Flask smoke test in a disposable HOME supplied by the installer.
No model download/load, background job, live user database, or fake Flask.
"""
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
if not os.environ.get('SDXL_STUDIO_HOME') or os.environ.get('SDXL_STUDIO_NO_BACKGROUND')!='1':
    raise SystemExit('Smoke test requires an explicitly isolated test home')
import flask, werkzeug, requests, PIL, cryptography, psutil
import app
app.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
client=app.app.test_client()
r=client.get('/api/health');assert r.status_code==200
assert r.get_json()['edition']=='sdxl'
assert r.headers['X-Content-Type-Options']=='nosniff'
# A remote client cannot claim the first account without the host-issued code.
r=client.post('/first-run',data={'password':'smoke-test-only-password','confirm_password':'smoke-test-only-password'},environ_overrides={'REMOTE_ADDR':'192.168.1.123'})
assert r.status_code==403,r.status_code
assert not app._load_auth_config()['password_hash']
# Exercise each supported claim path in its own disposable home/process.
remote='--remote' in sys.argv
base='https://192.168.1.12:8298' if remote else 'https://localhost:8298'
peer={'REMOTE_ADDR':'192.168.1.123' if remote else '127.0.0.1'}
r=client.get('/first-run',base_url=base,environ_overrides=peer)
assert r.status_code==200,r.status_code
with client.session_transaction(base_url=base) as session:nonce=session['first_run_csrf']
data={'first_run_csrf':nonce,'username':'smoketest',
    'password':'smoke-test-only-password','confirm_password':'smoke-test-only-password'}
if remote:
    issued=app.first_run_codes.issue();assert issued
    data['setup_code']=issued
r=client.post('/first-run',data=data,base_url=base,environ_overrides=peer)
assert r.status_code==302,(r.status_code,r.get_data(as_text=True)[:300])
assert app._load_auth_config()['password_hash']
assert app.first_run_codes.issue() is None
assert client.post('/login',headers={'Origin':'https://unrelated.invalid'}).status_code==403
print('Actual Flask health, headers, account '+('LAN with code' if remote else 'local')+', code revocation, Origin: OK')

# 0.1.0.27: exercise the new HTTP preview and preset persistence in this disposable
# home, never in the installed user's project. No worker or image job is started.
r=client.post('/api/projects',json={'name':'Installer preview smoke'},base_url=base,environ_overrides=peer)
assert r.status_code==200,(r.status_code,r.get_data(as_text=True)[:300])
pid=r.get_json()['project']['id']
before=app.one('SELECT COUNT(*) AS n FROM jobs')['n']
payload={'project_id':pid,'tool':'generate_image','model_id':'sdxl','prompt':'Smoke test only',
    'params':{'width':512,'height':512,'cfg':7,'steps':30,'seed':-1,'batch':1},
    'sweep':{'mode':'custom','ranges':{'cfg':{'min':5,'max':9,'count':3},'steps':{'min':20,'max':40,'count':2}},'max_jobs':24}}
r=client.post('/api/image/auto-test/preview',json=payload,base_url=base,environ_overrides=peer)
assert r.status_code==200,(r.status_code,r.get_data(as_text=True)[:300])
preview=r.get_json();assert preview['plan']['count']==6
assert len({v['seed'] for v in preview['plan']['variants']})==1
assert preview['request']['params']['seed']>=0
payload['sweep']['ranges']['steps']['count']=24
r=client.post('/api/image/auto-test/preview',json=payload,base_url=base,environ_overrides=peer)
assert r.status_code==400,r.status_code
assert app.one('SELECT COUNT(*) AS n FROM jobs')['n']==before
r=client.post('/api/image/presets/user',json={'schema_version':2,'name':'Smoke saved setup','params':{'seed':123,'steps':30}},base_url=base,environ_overrides=peer)
assert r.status_code==200,(r.status_code,r.get_data(as_text=True)[:300])
assert r.get_json()['preset']['params']['seed']==123
print('Actual Flask custom preview/count/seed, oversize rejection, no queued jobs, preset seed roundtrip: OK')
