"""Socket/TLS tests of the cleanup helper with a minimal protocol harness.

These are NOT Flask/Cheroot integration tests. The real integration remains
scripts/web_transport_smoke.py and is executed by the installed app runtime.
"""
import http.client
import io
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.http_body_cleanup import finish_unread_body
from core.local_certificate import generate_certificate
from tests.test_http_body_cleanup_43 import LengthBody


class TLSCleanup43Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sdxl-tls-harness-')
        root = Path(cls.tmp.name)
        generate_certificate(root)
        cls.server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        cls.server_ctx.load_cert_chain(str(root/'cert.pem'), str(root/'key.pem'))
        cls.client_ctx = ssl.create_default_context(cafile=str(root/'cert.pem'))
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def exchange(self, *, status=403, declared=32, data=b'x'*32,
                 timeout=.2, next_request=False, tls=ssl.TLSVersion.TLSv1_3):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)
        port = listener.getsockname()[1]
        captured = {}
        errors = []
        def server():
            try:
                raw, _ = listener.accept()
                with self.server_ctx.wrap_socket(raw, server_side=True) as sock:
                    sock.settimeout(3)
                    stream = sock.makefile('rb')
                    first = stream.readline()
                    headers = {}
                    while True:
                        line = stream.readline()
                        if line == b'\r\n':
                            break
                        if not line:
                            raise ValueError('Unexpected EOF in harness headers')
                        key, value = line.split(b':', 1)
                        headers[key.lower()] = value.strip()
                    body = LengthBody(stream, int(headers.get(b'content-length', 0)))
                    req = SimpleNamespace(rfile=body, conn=SimpleNamespace(socket=sock, rfile=stream),
                        chunked_read=False, close_connection=not next_request, outheaders=[], status=str(status).encode())
                    began = time.monotonic()
                    captured['result'] = finish_unread_body(req, timeout=timeout)
                    captured['elapsed'] = time.monotonic() - began
                    captured['remaining'] = body.remaining
                    captured['timeout'] = sock.gettimeout()
                    captured['close'] = req.close_connection
                    text = b'{"denied":true}'
                    conn_hdr = b'close' if req.close_connection else b'keep-alive'
                    sock.sendall(b'HTTP/1.1 ' + str(status).encode() + b' Test\r\nContent-Length: '
                        + str(len(text)).encode() + b'\r\nConnection: '+conn_hdr+b'\r\n\r\n'+text)
                    if next_request and not req.close_connection:
                        captured['next_line'] = stream.readline()
                        while stream.readline() != b'\r\n':
                            pass
                        sock.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK')
                    stream.close()
                    sock.shutdown(socket.SHUT_RDWR)
            except BaseException as error:
                errors.append(error)
            finally:
                listener.close()
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        ctx = ssl.create_default_context(cafile=str(Path(self.tmp.name)/'cert.pem'))
        ctx.minimum_version = tls
        ctx.maximum_version = tls
        connection = http.client.HTTPSConnection('127.0.0.1', port, context=ctx, timeout=3)
        try:
            connection.connect()
            self.assertNotEqual(connection.sock.context.verify_mode, ssl.CERT_NONE)
            connection.putrequest('POST', '/denied')
            connection.putheader('Content-Length', str(declared))
            connection.putheader('Origin', 'https://unrelated.invalid')
            if not next_request:
                connection.putheader('Connection', 'close')
            connection.endheaders()
            if data:
                connection.send(data)
            with connection.getresponse() as response:
                self.assertEqual(response.status, status)
                self.assertEqual(response.read(), b'{"denied":true}')
            if next_request:
                connection.request('GET', '/health')
                with connection.getresponse() as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b'OK')
        finally:
            connection.close()
            thread.join(5)
        self.assertFalse(thread.is_alive(), 'Harness thread did not exit')
        self.assertEqual(errors, [])
        return captured

    def test_tls13_403_body_delivered(self):
        self.assertEqual(self.exchange()['result'], 'drained')

    def test_tls12_403_body_delivered(self):
        self.assertEqual(self.exchange(tls=ssl.TLSVersion.TLSv1_2)['result'], 'drained')

    def test_tls_401_keeps_rejection(self):
        self.assertEqual(self.exchange(status=401)['remaining'], 0)

    def test_tls_429_keeps_rejection(self):
        self.assertEqual(self.exchange(status=429)['remaining'], 0)

    def test_tls_302_handles_unread_post(self):
        self.assertEqual(self.exchange(status=302)['remaining'], 0)

    def test_keepalive_does_not_consume_next_request(self):
        result = self.exchange(next_request=True)
        self.assertEqual(result['next_line'], b'GET /health HTTP/1.1\r\n')
        self.assertFalse(result['close'])

    def test_peer_never_sends_body_is_time_bounded(self):
        result = self.exchange(data=b'', declared=100)
        self.assertIn(result['result'], {'timeout-close', 'read-error-close'})
        self.assertTrue(result['close'])
        self.assertLess(result['elapsed'], 1.5)
        self.assertEqual(result['timeout'], 3)

    def test_large_body_not_drained(self):
        result = self.exchange(data=b'', declared=10000000)
        self.assertEqual(result['result'], 'limit-close')
        self.assertLess(result['elapsed'], .5)


class ServerWiring43Tests(unittest.TestCase):
    def test_cleanup_is_used_without_global_cheroot_monkeypatch(self):
        import types
        from core.web_server import make_server
        calls = []
        class FakeRequest:
            def send_headers(self):
                calls.append('headers')
        class FakeConnection:
            RequestHandlerClass = FakeRequest
        class FakeServer:
            ConnectionClass = FakeConnection
            def __init__(self, address, app, **kwargs):
                self.address, self.wsgi_app, self.kwargs = address, app, kwargs
        class FakeAdapter:
            def __init__(self, *args):
                self.context = SimpleNamespace(minimum_version=None)
        modules = {}
        for name in ['cheroot', 'cheroot.wsgi', 'cheroot.ssl', 'cheroot.ssl.builtin', 'cheroot.server']:
            modules[name] = types.ModuleType(name)
        modules['cheroot.wsgi'].Server = FakeServer
        modules['cheroot.ssl.builtin'].BuiltinSSLAdapter = FakeAdapter
        modules['cheroot.server'].HTTPRequest = FakeRequest
        modules['cheroot.server'].HTTPConnection = FakeConnection
        sentinel = object()
        with patch.dict('sys.modules', modules):
            server = make_server(sentinel, '0.0.0.0', 8298, tls=('cert', 'key'))
            self.assertIs(server.wsgi_app, sentinel)
            self.assertEqual(server.address, ('0.0.0.0', 8298))
            self.assertEqual(server.max_request_body_size, 0)
            self.assertEqual(server.ssl_adapter.context.minimum_version, ssl.TLSVersion.TLSv1_2)
            self.assertIs(FakeConnection.RequestHandlerClass, FakeRequest)
            self.assertIsNot(server.ConnectionClass, FakeConnection)
            with patch('core.http_body_cleanup.finish_unread_body', side_effect=lambda req: calls.append('cleanup')):
                # The closure captured the imported function, so instantiate a
                # fresh server while patched, then exercise method dispatch.
                server = make_server(sentinel, '127.0.0.1', 8298)
                req = server.ConnectionClass.RequestHandlerClass()
                req.send_headers()
            self.assertEqual(calls, ['cleanup', 'headers'])

if __name__ == '__main__':
    unittest.main()
