from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid


FRONTEND_DIR = Path(__file__).resolve().parents[2]
NGINX_CONFIG = FRONTEND_DIR / "nginx.conf"
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _location_block(config: str, location: str) -> str:
    match = re.search(
        rf"location\s+{re.escape(location)}\s*\{{(?P<body>.*?)\n\s*\}}", config, re.DOTALL
    )
    if match is None:
        raise AssertionError(f"missing nginx location: {location}")
    return match.group("body")


class NginxConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = NGINX_CONFIG.read_text(encoding="utf-8")

    def test_api_routes_proxy_to_compose_backend_without_rewriting_prefix(self) -> None:
        for location in ("= /api/v1", "^~ /api/v1/"):
            with self.subTest(location=location):
                block = _location_block(self.config, location)
                self.assertIn("proxy_pass http://backend:8000;", block)
                self.assertNotIn("try_files", block)
                self.assertIn("proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;", block)
                self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", block)

    def test_spa_fallback_is_limited_to_non_api_routes(self) -> None:
        self.assertIn("try_files $uri $uri/ /index.html;", _location_block(self.config, "/"))

    def test_spa_shell_is_not_cached_across_deployments(self) -> None:
        shell = _location_block(self.config, "= /index.html")
        self.assertIn('add_header Cache-Control "no-store, max-age=0" always;', shell)
        # nginx add_header directives do not inherit into a child location, so
        # the shell location must retain the browser security baseline too.
        self.assertIn('add_header X-Content-Type-Options "nosniff" always;', shell)
        self.assertIn('add_header Content-Security-Policy "default-src \'self\'', shell)

    def test_security_headers_apply_to_success_and_error_responses(self) -> None:
        expected = {
            'add_header X-Content-Type-Options "nosniff" always;',
            'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
            'add_header X-Frame-Options "DENY" always;',
        }
        for directive in expected:
            with self.subTest(directive=directive):
                self.assertIn(directive, self.config)
        self.assertRegex(
            self.config,
            r'add_header Content-Security-Policy "default-src \'self\'.*frame-ancestors \'none\'.*" always;',
        )

    def test_health_location_does_not_override_inherited_security_headers(self) -> None:
        health = _location_block(self.config, "= /health")
        self.assertIn("default_type text/plain;", health)
        self.assertNotIn("add_header", health)

    def test_proxy_accepts_the_documented_upload_limit(self) -> None:
        self.assertIn("client_max_body_size 50m;", self.config)


@unittest.skipUnless(
    os.environ.get("RUN_CONTAINER_TESTS") == "1",
    "set RUN_CONTAINER_TESTS=1 for Docker black-box coverage",
)
class NginxBlackBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is unavailable")

        cls.suffix = uuid.uuid4().hex[:12]
        cls.network = f"nh-ad-nginx-test-{cls.suffix}"
        cls.backend = f"nh-ad-backend-test-{cls.suffix}"
        cls.frontend = f"nh-ad-frontend-test-{cls.suffix}"
        cls.temp_dir = tempfile.TemporaryDirectory()
        root = Path(cls.temp_dir.name)
        frontend_root = root / "frontend"
        backend_root = root / "backend"
        frontend_root.mkdir()
        (backend_root / "api" / "v1").mkdir(parents=True)
        (frontend_root / "index.html").write_text("frontend-spa", encoding="utf-8")
        (backend_root / "api" / "v1" / "probe").write_text("backend-api", encoding="utf-8")
        backend_config = root / "backend.conf"
        backend_config.write_text(
            "server { listen 8000; server_name _; root /usr/share/nginx/html; }\n",
            encoding="utf-8",
        )

        try:
            cls._docker("network", "create", cls.network)
            cls._docker(
                "run",
                "--detach",
                "--name",
                cls.backend,
                "--network",
                cls.network,
                "--network-alias",
                "backend",
                "--volume",
                f"{backend_config}:/etc/nginx/conf.d/default.conf:ro",
                "--volume",
                f"{backend_root}:/usr/share/nginx/html:ro",
                "nginx:1.27-alpine",
            )
            cls._docker(
                "run",
                "--detach",
                "--name",
                cls.frontend,
                "--network",
                cls.network,
                "--publish",
                "127.0.0.1::8080",
                "--volume",
                f"{NGINX_CONFIG}:/etc/nginx/conf.d/default.conf:ro",
                "--volume",
                f"{frontend_root}:/usr/share/nginx/html:ro",
                "nginx:1.27-alpine",
            )
            port_output = cls._docker("port", cls.frontend, "8080/tcp").stdout.strip()
            cls.port = int(port_output.rsplit(":", 1)[1])
            cls._wait_until_ready()
        except Exception:
            cls._cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cleanup()

    @classmethod
    def _docker(cls, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=60,
        )

    @classmethod
    def _cleanup(cls) -> None:
        for container in (getattr(cls, "frontend", ""), getattr(cls, "backend", "")):
            if container:
                cls._docker("rm", "--force", container, check=False)
        network = getattr(cls, "network", "")
        if network:
            cls._docker("network", "rm", network, check=False)
        temp_dir = getattr(cls, "temp_dir", None)
        if temp_dir is not None:
            temp_dir.cleanup()

    @classmethod
    def _wait_until_ready(cls) -> None:
        deadline = time.monotonic() + 20
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(cls._url("/health"), timeout=1) as response:
                    if response.status == 200:
                        return
            except (ConnectionError, urllib.error.URLError, TimeoutError, socket.timeout) as error:
                last_error = error
            time.sleep(0.2)
        logs = cls._docker("logs", cls.frontend, check=False).stderr
        raise AssertionError(f"frontend nginx did not become ready: {last_error}\n{logs}")

    @classmethod
    def _url(cls, path: str) -> str:
        return f"http://127.0.0.1:{cls.port}{path}"

    def assert_security_headers(self, response: urllib.response.addinfourl) -> None:
        for name, expected in SECURITY_HEADERS.items():
            with self.subTest(header=name):
                self.assertIn(expected, response.headers[name])

    def test_api_path_is_served_by_backend_with_security_headers(self) -> None:
        with urllib.request.urlopen(self._url("/api/v1/probe"), timeout=2) as response:
            self.assertEqual("backend-api", response.read().decode())
            self.assert_security_headers(response)

    def test_spa_route_falls_back_to_frontend_index(self) -> None:
        with urllib.request.urlopen(self._url("/nested/client/route"), timeout=2) as response:
            self.assertEqual("frontend-spa", response.read().decode())
            self.assert_security_headers(response)
            self.assertEqual("no-store, max-age=0", response.headers["Cache-Control"])

    def test_missing_api_route_does_not_fall_back_to_spa(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self._url("/api/v1/missing"), timeout=2)
        self.assertEqual(404, raised.exception.code)
        self.assert_security_headers(raised.exception)


if __name__ == "__main__":
    unittest.main()
