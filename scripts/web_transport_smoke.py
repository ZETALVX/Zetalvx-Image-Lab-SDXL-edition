#!/usr/bin/env python3
"""Real HTTPS/WSGI gate using a disposable home, before version activation.

Keeps the negative Origin test strict: a disconnect is NOT a valid denial.
All requests use generated local-only test credentials, no user tokens/models.
"""
import http.client
import http.cookiejar
import importlib.metadata
import json
import os
from pathlib import Path
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
home = os.environ.get('SDXL_STUDIO_HOME', '')
if not home or os.environ.get('SDXL_STUDIO_NO_BACKGROUND') != '1':
    raise SystemExit('Disposable smoke home is required')

import app
from core.local_certificate import generate_certificate
from core.web_server import make_server
from core.download_security import TokenStore
from core.maintenance_state import busy_jobs
from core.socket_retry import retry_address_in_use
from werkzeug.security import generate_password_hash


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def request_result(client, url, *, data=None, headers=None):
    """Read the full response, including expected HTTP errors; no retry."""
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        response = client.open(req, timeout=12)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def opener(context, cookies=None):
    handlers = [urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)]
    if cookies is not None:
        handlers.append(urllib.request.HTTPCookieProcessor(cookies))
    return urllib.request.build_opener(*handlers)


print('Web transport dependencies: ' + ', '.join(
    name + '=' + importlib.metadata.version(name) for name in ('Flask', 'Werkzeug', 'cheroot')
), flush=True)
print('Python: ' + sys.version.split()[0] + ' / ' + ssl.OPENSSL_VERSION, flush=True)
home = Path(home)
app._save_auth_config('smoke-user', generate_password_hash('temporary-password-for-smoke'))
folder = home / 'shared/config'
generate_certificate(folder)
store = TokenStore(home / 'secrets')
store.put('huggingface', 'hf_SMOKE_NOT_A_REAL_CREDENTIAL')
check(store.get('huggingface') == 'hf_SMOKE_NOT_A_REAL_CREDENTIAL', 'Token roundtrip failed')
check('hf_SMOKE_NOT_A_REAL_CREDENTIAL' not in json.dumps(store.public()), 'Token leaked in public output')
store.delete('huggingface')
check(store.get('huggingface') == '', 'Token deletion failed')
state = home / 'shared/vision/link-imports/smoke.json'
state.parent.mkdir(parents=True, exist_ok=True)
state.write_text(json.dumps({'status': 'downloading'}), encoding='utf-8')
check(busy_jobs(home), 'Active Vision download did not block maintenance')
state.unlink()
ctx = ssl.create_default_context(cafile=str(folder / 'cert.pem'))
# The client verifies the locally generated certificate; never CERT_NONE.
for host in ('127.0.0.1', '0.0.0.0'):
    # Each bind mode gets its own OS-assigned ephemeral port. Reusing the
    # loopback port for a subsequent wildcard bind can transiently fail on
    # Linux even after a clean Cheroot stop because the two address scopes
    # overlap. That is a smoke-test artifact, not the product's fixed port.
    port = 0
    observations = deque(maxlen=16)

    def start_transport_attempt(_attempt):
        server = make_server(app.app, host, port, tls=(str(folder/'cert.pem'), str(folder/'key.pem')))
        original = server.wsgi_app

        def only_loopback(env, start_response, original=original, observations=observations):
            if env.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
                start_response('403 Forbidden', [('Content-Length', '0')])
                return [b'']
            def observed_start(status, headers, exc_info=None):
                # Metadata only: no request body, password, token or cookie.
                observations.append({
                    'method': env.get('REQUEST_METHOD'), 'path': env.get('PATH_INFO'),
                    'status': status, 'connection': env.get('HTTP_CONNECTION', ''),
                    'unread_body_bytes_before_transport_cleanup': getattr(env.get('wsgi.input'), 'remaining', None),
                })
                return start_response(status, headers, exc_info)
            return original(env, observed_start)

        server.wsgi_app = only_loopback
        errors = []
        def run():
            try:
                server.start()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        deadline = time.monotonic()+15
        while not server.ready and not errors and time.monotonic() < deadline:
            time.sleep(.05)
        if errors:
            error = errors[0]
            try: server.stop()
            except Exception: pass
            thread.join(3)
            raise error
        if not server.ready:
            try: server.stop()
            except Exception: pass
            thread.join(3)
            raise TimeoutError('WSGI startup timed out')
        return server, thread

    def bind_retry_notice(attempt, attempts, error, delay):
        print('[HTTPS '+host+'] temporary bind collision on port '+str(port)+
              '; retry '+str(attempt)+'/'+str(attempts)+' in '+format(delay,'.2f')+'s', flush=True)

    step = 'start'
    try:
        server, thread = retry_address_in_use(start_transport_attempt, attempts=10, on_retry=bind_retry_notice)
        port = server.socket.getsockname()[1]
        base = 'https://127.0.0.1:' + str(port)
        cookies = http.cookiejar.CookieJar()
        client = opener(ctx, cookies)
        anonymous = opener(ctx)
        def stage(name):
            global step
            step = name
            print('[HTTPS '+host+'] '+name, flush=True)

        stage('health')
        status, headers, body = request_result(client, base+'/api/health')
        check(status == 200 and json.loads(body)['ok'] is True, 'Health failed')

        data = urllib.parse.urlencode({'username':'smoke-user','password':'temporary-password-for-smoke'}).encode()
        stage('same-origin login and secure cookie')
        status, headers, body = request_result(client, base+'/login', data=data, headers={'Origin':base})
        check(status == 200, 'Login failed')
        check(any(c.secure and c.name == 'creator_sdxl_session' for c in cookies), 'Secure cookie missing')
        status, headers, body = request_result(client, base+'/api/account')
        check(status == 200 and json.loads(body)['username'] == 'smoke-user', 'Account failed')

        stage('Origin rejection with unread POST and Connection: close (three requests)')
        for _ in range(3):
            status, headers, body = request_result(client, base+'/login', data=data,
                headers={'Origin':'https://unrelated.invalid', 'Connection':'close'})
            check(status == 403, 'Cross-origin login not rejected with HTTP 403')
            check(json.loads(body).get('error') == 'Cross-origin request refused', 'Wrong Origin refusal body')
            check(headers.get('X-Content-Type-Options') == 'nosniff', 'Security header missing')

        stage('anonymous POST rejection with unread body')
        status, headers, body = request_result(anonymous, base+'/api/account', data=data,
            headers={'Origin':base})
        check(status == 401 and json.loads(body).get('auth_required') is True, 'Anonymous request not rejected')

        stage('Origin rejection with HTTP keep-alive, followed by health on same connection')
        connection = http.client.HTTPSConnection('127.0.0.1', port, context=ctx, timeout=12)
        try:
            connection.connect()
            original_socket = connection.sock
            connection.request('POST', '/login', body=data, headers={
                'Origin':'https://unrelated.invalid', 'Content-Type':'application/x-www-form-urlencoded'})
            with connection.getresponse() as response:
                check(response.status == 403, 'Keep-alive Origin rejection failed')
                check(json.loads(response.read()).get('error') == 'Cross-origin request refused', 'Keep-alive response invalid')
                check(not response.will_close, 'Small fully drained keep-alive request should stay open')
            connection.request('GET', '/api/health')
            with connection.getresponse() as response:
                check(response.status == 200 and json.loads(response.read())['ok'], 'Health after rejection failed')
            check(connection.sock is original_socket, 'Test did not reuse the same TLS socket')
        finally:
            connection.close()

        if host == '0.0.0.0':
            stage('login throttling: eight wrong passwords, then HTTP 429 with body')
            bad = urllib.parse.urlencode({'username':'smoke-user','password':'not-the-password'}).encode()
            for _ in range(8):
                status, headers, body = request_result(anonymous, base+'/login', data=bad)
                check(status == 200, 'Wrong-password response changed before limit')
            status, headers, body = request_result(anonymous, base+'/login', data=bad)
            check(status == 429 and int(headers['Retry-After']) > 0 and body, 'Login attempts not throttled')
        stage('complete')
    except BaseException as error:
        print('[HTTPS FAIL] stage='+step+' error='+type(error).__name__+': '+str(error), file=sys.stderr, flush=True)
        print('Recent WSGI response metadata (no credentials): '+json.dumps(list(observations)), file=sys.stderr, flush=True)
        raise
    finally:
        failed = sys.exc_info()[0] is not None
        server.stop()
        thread.join(10)
        if thread.is_alive():
            print('WSGI stop timed out', file=sys.stderr, flush=True)
            if not failed:
                raise AssertionError('WSGI stop timed out')
print('HTTPS/WSGI loopback + LAN bind, independent ephemeral ports, verified TLS, login, cookie, Origin (close/keep-alive), HTTP 401/403/429, token storage, Vision idle guard: OK', flush=True)
