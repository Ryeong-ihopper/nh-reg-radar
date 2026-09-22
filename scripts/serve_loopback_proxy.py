"""Expose one verified HTTPS application on loopback, without copying its state."""
from __future__ import annotations

import argparse
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit

HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}


def make_handler(upstream: str, context: ssl.SSLContext, login: dict | None = None):
    target = urlsplit(upstream)
    if (target.scheme != "https" or not target.hostname or target.username
            or target.password or target.path or target.query or target.fragment):
        raise ValueError("upstream must be a bare HTTPS origin")

    class Proxy(BaseHTTPRequestHandler):
        def forward(self):
            port = self.server.server_port
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if (host not in allowed or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or (origin and origin not in {f"http://{h}" for h in allowed})):
                self.send_error(403, "Loopback requests only")
                return
            if not self.path.startswith("/") or self.path.startswith("//"):
                self.send_error(400, "Relative application path required")
                return
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) > 1:
                self.send_error(400, "One explicit body length required")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = -1
            if not 0 <= size <= 100 * 1024 * 1024:
                self.send_error(413, "Invalid or excessive request body")
                return
            body = self.rfile.read(size) if size else None
            connection_tokens = {x.strip().lower() for x in self.headers.get("Connection", "").split(",")}
            excluded = HOP_HEADERS | connection_tokens | {"host", "accept-encoding"}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
            headers["Host"] = target.netloc
            headers["Accept-Encoding"] = "identity"
            if origin:
                headers["Origin"] = upstream
            conn = http.client.HTTPSConnection(target.hostname, target.port or 443, context=context, timeout=120)
            try:
                method, path = self.command, self.path
                local_session = method == "GET" and path == "/api/v1/auth/local-session"
                if local_session:
                    method, path = "POST", "/api/v1/auth/refresh"
                    headers["Origin"] = upstream
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                payload = response.read()
                if local_session and response.status == 401 and login is not None:
                    # Explicit local demo mode: credentials stay in this
                    # process and are sent only to the verified upstream.
                    body = json.dumps(login).encode("utf-8")
                    conn.request("POST", "/api/v1/auth/login", body=body, headers={
                        "Host": target.netloc, "Origin": upstream,
                        "Content-Type": "application/json", "Content-Length": str(len(body)),
                    })
                    response = conn.getresponse()
                    payload = response.read()
                self.send_response(response.status)
                response_excluded = HOP_HEADERS | {"content-length"}
                response_excluded |= {x.strip().lower() for x in (response.getheader("Connection") or "").split(",")}
                for key, value in response.getheaders():
                    if key.lower() in response_excluded:
                        continue
                    if key.lower() == "set-cookie":
                        # Only the fixed loopback hop is HTTP; upstream remains verified TLS.
                        value = re.sub(r";\s*Secure(?=;|$)", "", value, flags=re.I)
                        value = re.sub(r";\s*Domain=[^;]*", "", value, flags=re.I)
                    elif key.lower() == "location" and (value == upstream or value.startswith(upstream + "/")):
                        value = f"http://{host}" + value[len(upstream):]
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)) if self.command != "HEAD" else response.getheader("Content-Length", "0"))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
            except (OSError, http.client.HTTPException) as exc:
                print(f"Upstream failure: {type(exc).__name__} (errno={getattr(exc, 'errno', None)})", flush=True)
                self.send_error(502, "Verified upstream connection failed")
            finally:
                conn.close()

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = forward

        def log_message(self, format, *args):
            # Do not log URLs, request bodies, cookies, or authorization tokens.
            pass

    return Proxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--ca-file", required=True, help="Trusted upstream public certificate or CA bundle")
    parser.add_argument("--port", type=int, default=5182)
    parser.add_argument("--login-file", type=Path, help="Private account JSON for explicitly enabled local automatic login")
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=args.ca_file)
    login = None
    if args.login_file:
        account = json.loads(args.login_file.read_text(encoding="utf-8"))
        login = {key: account[key] for key in ("email", "password")}
        if not all(isinstance(value, str) and value for value in login.values()):
            raise ValueError("Private login file needs a nonempty email and password")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.upstream.rstrip("/"), context, login))
    print(f"Local application: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
