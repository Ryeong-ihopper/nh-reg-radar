"""Private multi-bucket S3/MinIO adapter for parser workers."""

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


class S3ArtifactStorage:
    """AWS SigV4 adapter implementing the parser artifact storage protocol."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        region: str = "us-east-1",
    ) -> None:
        parsed = urlsplit(endpoint.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("object storage endpoint must be absolute")
        self._endpoint = endpoint.rstrip("/")
        self._host = parsed.netloc
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region

    def put(self, bucket: str, object_key: str, body: bytes, content_type: str) -> None:
        self._request("PUT", bucket, object_key, body, content_type)

    def get(self, bucket: str, object_key: str) -> bytes:
        return self._request("GET", bucket, object_key, b"", None)

    def delete(self, bucket: str, object_key: str) -> None:
        self._request("DELETE", bucket, object_key, b"", None)

    def _request(
        self,
        method: str,
        bucket: str,
        object_key: str,
        body: bytes,
        content_type: str | None,
    ) -> bytes:
        if not bucket or object_key.startswith("/") or ".." in object_key.split("/"):
            raise ValueError("invalid object storage identifier")
        uri = f"/{quote(bucket, safe='')}/{quote(object_key, safe='/')}"
        now = datetime.now(UTC)
        amz_date, date_stamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        header_values = {
            "host": self._host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            header_values["content-type"] = content_type
        signed_names = sorted(header_values)
        canonical_headers = "".join(f"{name}:{header_values[name]}\n" for name in signed_names)
        signed_headers = ";".join(signed_names)
        canonical = "\n".join((method, uri, "", canonical_headers, signed_headers, payload_hash))
        scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical.encode()).hexdigest(),
            )
        )
        signature = hmac.new(
            self._signing_key(date_stamp), to_sign.encode(), hashlib.sha256
        ).hexdigest()
        headers = {name.title(): value for name, value in header_values.items() if name != "host"}
        headers["Host"] = self._host
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self._access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        request = Request(
            f"{self._endpoint}{uri}",
            data=body if method == "PUT" else None,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - private endpoint
                return bytes(response.read())
        except HTTPError as exc:
            raise OSError(f"object storage request failed with status {exc.code}") from exc

    def _signing_key(self, stamp: str) -> bytes:
        date_key = hmac.new(
            f"AWS4{self._secret_key}".encode(), stamp.encode(), hashlib.sha256
        ).digest()
        region_key = hmac.new(date_key, self._region.encode(), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
