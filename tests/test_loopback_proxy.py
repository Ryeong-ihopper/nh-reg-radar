import http.client
import ssl
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from scripts.serve_loopback_proxy import make_handler


class LoopbackProxyTests(unittest.TestCase):
    def setUp(self):
        self.context = ssl.create_default_context()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler("https://app.example", self.context))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        self.addCleanup(self.conn.close)

    def test_untrusted_host_and_origin_cannot_forward(self):
        for headers in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"}):
            with self.subTest(headers=headers), patch("scripts.serve_loopback_proxy.http.client.HTTPSConnection") as upstream:
                self.conn.request("GET", "/", headers=headers)
                response = self.conn.getresponse()
                response.read()
                self.assertEqual(response.status, 403)
                upstream.assert_not_called()

    def test_local_session_restores_cookie_with_verified_upstream(self):
        response = Mock(status=200)
        response.read.return_value = b'{}'
        response.getheader.return_value = None
        response.getheaders.return_value = [("Set-Cookie", "refreshToken=rotated; HttpOnly; Secure; SameSite=lax; Path=/api/v1/auth")]
        with patch("scripts.serve_loopback_proxy.http.client.HTTPSConnection") as upstream:
            upstream.return_value.getresponse.return_value = response
            self.conn.request("GET", "/api/v1/auth/local-session", headers={"Cookie": "refreshToken=current"})
            actual = self.conn.getresponse()
            self.assertEqual(actual.status, 200)
            self.assertEqual(actual.read(), b'{}')
            cookie = actual.getheader("Set-Cookie")
            self.assertIn("HttpOnly", cookie)
            self.assertNotIn("Secure", cookie)
            request = upstream.return_value.request.call_args
            self.assertEqual(request.args, ("POST", "/api/v1/auth/refresh"))
            self.assertEqual(request.kwargs["headers"]["Origin"], "https://app.example")
            self.assertEqual(request.kwargs["headers"]["Cookie"], "refreshToken=current")
            self.assertIs(upstream.call_args.kwargs["context"], self.context)
            self.assertTrue(self.context.check_hostname)
            self.assertEqual(self.context.verify_mode, ssl.CERT_REQUIRED)

    def test_tls_failure_does_not_retry_insecurely(self):
        with patch("scripts.serve_loopback_proxy.http.client.HTTPSConnection") as upstream:
            upstream.return_value.request.side_effect = ssl.SSLError("certificate rejected")
            self.conn.request("GET", "/")
            response = self.conn.getresponse()
            response.read()
            self.assertEqual(response.status, 502)
            self.assertEqual(upstream.call_count, 1)


if __name__ == "__main__":
    unittest.main()
