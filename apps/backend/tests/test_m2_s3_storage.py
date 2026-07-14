from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import ClassVar

from nh_ad_backend.s3_storage import S3ObjectStorage


class S3Handler(BaseHTTPRequestHandler):
    objects: ClassVar[dict[str, bytes]] = {}
    authorizations: ClassVar[list[str]] = []

    def do_PUT(self) -> None:  # noqa: N802
        self._record()
        size = int(self.headers.get("content-length", "0"))
        self.objects[self.path] = self.rfile.read(size)
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._record()
        if self.path not in self.objects:
            self.send_response(404)
            self.end_headers()
            return
        body = self.objects[self.path]
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self) -> None:  # noqa: N802
        self._record()
        self.objects.pop(self.path, None)
        self.send_response(204)
        self.end_headers()

    def _record(self) -> None:
        self.authorizations.append(self.headers.get("authorization", ""))
        assert self.headers.get("x-amz-content-sha256")
        assert self.headers.get("x-amz-date")

    def log_message(self, _format: str, *_args: object) -> None:
        return


def serve() -> Iterator[tuple[ThreadingHTTPServer, str]]:
    S3Handler.objects.clear()
    S3Handler.authorizations.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), S3Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def test_minio_sigv4_adapter_put_get_delete() -> None:
    for _server, endpoint in serve():
        storage = S3ObjectStorage(
            endpoint,
            "test-access-key",
            "test-secret-key",
            "private-bucket",
        )
        key = storage.put(b"private-advertisement")
        assert key.startswith("advertisements/")
        assert storage.open(key).read() == b"private-advertisement"
        storage.delete(key)
        assert not S3Handler.objects
        assert all(
            authorization.startswith("AWS4-HMAC-SHA256 Credential=test-access-key/")
            for authorization in S3Handler.authorizations
        )
