import errno
import unittest
from core.socket_retry import is_address_in_use, retry_address_in_use


class SocketRetry46Tests(unittest.TestCase):
    def test_linux_eaddrinuse_retries_then_succeeds(self):
        calls=[]
        def action(index):
            calls.append(index)
            if index < 2:
                raise OSError(errno.EADDRINUSE, "busy")
            return "ok"
        waits=[]
        self.assertEqual(retry_address_in_use(action, attempts=5, sleeper=waits.append), "ok")
        self.assertEqual(calls, [0,1,2])
        self.assertEqual(len(waits), 2)

    def test_windows_wsaeaddrinuse_is_recognized(self):
        err=OSError(10048, "Only one usage")
        err.winerror=10048
        self.assertTrue(is_address_in_use(err))

    def test_other_errors_are_not_retried(self):
        calls=[]
        def action(index):
            calls.append(index)
            raise OSError(errno.EACCES, "denied")
        with self.assertRaises(OSError):
            retry_address_in_use(action, attempts=10, sleeper=lambda _:None)
        self.assertEqual(calls,[0])

    def test_exhaustion_remains_fatal(self):
        calls=[]
        def action(index):
            calls.append(index)
            raise OSError(errno.EADDRINUSE, "busy")
        with self.assertRaises(OSError):
            retry_address_in_use(action, attempts=3, sleeper=lambda _:None)
        self.assertEqual(calls,[0,1,2])

if __name__ == '__main__': unittest.main()
