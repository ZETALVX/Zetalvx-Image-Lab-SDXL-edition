"""Regression tests for bounded early-response cleanup (no optional imports)."""
import io
import unittest
from types import SimpleNamespace

from core.http_body_cleanup import finish_unread_body, MAX_DRAIN_BYTES


class FakeSocket:
    def __init__(self, timeout=120):
        self.timeout = timeout
        self.timeouts = []
    def gettimeout(self):
        return self.timeout
    def settimeout(self, value):
        self.timeout = value
        self.timeouts.append(value)


class LengthBody:
    """Interface contract of Cheroot's KnownLengthRFile; not its implementation."""
    def __init__(self, raw, length):
        self.rfile = raw
        self.remaining = length
    def read(self, size):
        size = min(size, self.remaining)
        data = self.rfile.read(size)
        self.remaining -= len(data)
        return data


def request(data=b'username=user&password=fake', *, length=None, close=True, raw=None):
    raw = io.BytesIO(data) if raw is None else raw
    body = LengthBody(raw, len(data) if length is None else length)
    return SimpleNamespace(
        rfile=body, conn=SimpleNamespace(socket=FakeSocket(), rfile=raw),
        chunked_read=False, close_connection=close, status=b'403 Forbidden',
        outheaders=[(b'Content-Type', b'application/json')])


class BodyCleanup43Tests(unittest.TestCase):
    def test_close_request_consumes_small_unread_body(self):
        req = request()
        self.assertEqual(finish_unread_body(req), 'drained')
        self.assertEqual(req.rfile.remaining, 0)
        self.assertTrue(req.close_connection)
        self.assertEqual(req.status, b'403 Forbidden')

    def test_keepalive_request_retains_keepalive_after_complete_drain(self):
        req = request(close=False)
        self.assertEqual(finish_unread_body(req), 'drained')
        self.assertFalse(req.close_connection)

    def test_already_read_request_performs_no_io(self):
        req = request(length=0)
        req.conn.socket.settimeout = lambda value: self.fail('Socket must not be touched')
        self.assertEqual(finish_unread_body(req), 'already-read')

    def test_no_next_request_consumed(self):
        req = request(b'abcGET /next HTTP/1.1\r\n\r\n', length=3, close=False)
        finish_unread_body(req)
        self.assertEqual(req.rfile.rfile.read(), b'GET /next HTTP/1.1\r\n\r\n')

    def test_only_remaining_tail_consumed(self):
        req = request(b'abcdef')
        self.assertEqual(req.rfile.read(2), b'ab')
        finish_unread_body(req)
        self.assertEqual(req.rfile.remaining, 0)

    def test_original_timeout_restored(self):
        req = request()
        finish_unread_body(req)
        self.assertEqual(req.conn.socket.gettimeout(), 120)
        self.assertTrue(all(0 < t <= 1 for t in req.conn.socket.timeouts[:-1]))

    def test_shorter_socket_timeout_not_increased(self):
        req = request()
        req.conn.socket.timeout = .03
        finish_unread_body(req)
        self.assertTrue(all(t <= .03 for t in req.conn.socket.timeouts))

    def test_unbounded_socket_gets_bounded_drain_timeout(self):
        req = request()
        req.conn.socket.timeout = None
        finish_unread_body(req)
        self.assertIsNone(req.conn.socket.gettimeout())
        self.assertLessEqual(req.conn.socket.timeouts[0], 1)

    def test_large_unread_upload_is_not_buffered_or_read(self):
        req = request(b'small', length=MAX_DRAIN_BYTES + 1, close=False)
        self.assertEqual(finish_unread_body(req), 'limit-close')
        self.assertEqual(req.rfile.rfile.tell(), 0)
        self.assertTrue(req.close_connection)

    def test_exact_size_cap(self):
        req = request(b'x' * MAX_DRAIN_BYTES)
        self.assertEqual(finish_unread_body(req), 'drained')
        self.assertEqual(req.rfile.remaining, 0)

    def test_unknown_framing_closed_without_read(self):
        req = request()
        req.rfile = SimpleNamespace()
        self.assertEqual(finish_unread_body(req), 'unknown-close')
        self.assertTrue(req.close_connection)

    def test_invalid_remaining_closed_without_read(self):
        for length in [-1, '5', True]:
            with self.subTest(length=length):
                req = request(length=length)
                self.assertEqual(finish_unread_body(req), 'invalid-close')
                self.assertTrue(req.close_connection)

    def test_chunked_unread_no_unbounded_drain(self):
        req = request(close=False)
        req.chunked_read = True
        req.rfile = SimpleNamespace(closed=False)
        self.assertEqual(finish_unread_body(req), 'chunked-close')
        self.assertTrue(req.close_connection)

    def test_chunked_already_read_unchanged(self):
        req = request(close=False)
        req.chunked_read = True
        req.rfile = SimpleNamespace(closed=True)
        self.assertEqual(finish_unread_body(req), 'already-read')
        self.assertFalse(req.close_connection)

    def test_truncated_body_closes_and_preserves_status(self):
        req = request(b'ab', length=10, close=False)
        self.assertEqual(finish_unread_body(req), 'eof-close')
        self.assertTrue(req.close_connection)
        self.assertEqual(req.status, b'403 Forbidden')
        self.assertEqual(req.rfile.remaining, 8)

    def test_read_error_closes_and_restores_timeout(self):
        class Broken(io.BytesIO):
            def read1(self, _):
                raise TimeoutError('injected')
        req = request(raw=Broken(), length=10, close=False)
        self.assertEqual(finish_unread_body(req), 'read-error-close')
        self.assertTrue(req.close_connection)
        self.assertEqual(req.conn.socket.gettimeout(), 120)

    def test_budget_is_total_not_per_read(self):
        class Dribble(io.BytesIO):
            def read1(self, _):
                return super().read(1)
        ticks = iter([0.0, .1, .6, 1.1])
        req = request(raw=Dribble(b'abcdef'), length=6, close=False)
        self.assertEqual(finish_unread_body(req, clock=lambda: next(ticks)), 'timeout-close')
        self.assertEqual(req.rfile.remaining, 4)
        self.assertTrue(req.close_connection)

    def test_bytewise_fallback_for_no_read1(self):
        class NoRead1:
            def __init__(self):
                self.inner = io.BytesIO(b'abcdefNEXT')
                self.sizes = []
            def read(self, size):
                self.sizes.append(size)
                return self.inner.read(size)
        raw = NoRead1()
        req = request(raw=raw, length=6)
        self.assertEqual(finish_unread_body(req), 'drained')
        self.assertEqual(raw.sizes, [1] * 6)
        self.assertEqual(raw.inner.read(), b'NEXT')

    def test_forced_close_replaces_keepalive_only(self):
        req = request(length=1000000, close=False)
        req.outheaders += [(b'connection', b'keep-alive'), (b'Retry-After', b'60')]
        finish_unread_body(req)
        self.assertNotIn((b'connection', b'keep-alive'), req.outheaders)
        self.assertEqual(req.outheaders.count((b'Connection', b'close')), 1)
        self.assertIn((b'Retry-After', b'60'), req.outheaders)

    def test_response_status_and_headers_not_rewritten(self):
        for status in [b'200 OK', b'302 Found', b'401 Unauthorized', b'403 Forbidden', b'429 Too Many Requests']:
            with self.subTest(status=status):
                req = request()
                req.status = status
                req.outheaders += [(b'Retry-After', b'60')]
                expected = list(req.outheaders)
                finish_unread_body(req)
                self.assertEqual(req.status, status)
                self.assertEqual(req.outheaders, expected)

    def test_model_upload_already_read_has_no_64kb_limit(self):
        req = request(b'', length=0, close=False)
        # The cleanup cap is not an upload cap. Routes have consumed the upload.
        req.inheaders = {b'Content-Length': b'104857600'}
        self.assertEqual(finish_unread_body(req), 'already-read')
        self.assertFalse(req.close_connection)


if __name__ == '__main__':
    unittest.main()
