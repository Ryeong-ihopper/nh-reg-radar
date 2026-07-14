"""Minimal path-style S3/MinIO adapter using AWS Signature Version 4."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO, cast
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


class S3StorageError(OSError):
    """Raised when MinIO rejects or cannot complete an object operation."""


class S3ObjectStorage:
    """Private MinIO-compatible storage; it never creates public or presigned URLs."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        *,
        region: str = "us-east-1",
    ) -> None:
        parsed = urlsplit(endpoint.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("object storage endpoint must be an absolute HTTP(S) URL")
        if not access_key or not secret_key or not bucket:
            raise ValueError("object storage credentials and bucket are required")
        self._endpoint = endpoint.rstrip("/")
        self._host = parsed.netloc
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region

    def put(self, body: bytes) -> str:
        storage_key = f"advertisements/{secrets.token_hex(24)}"
        self._request("PUT", storage_key, body)
        return storage_key

    def open(self, storage_key: str) -> BinaryIO:
        return BytesIO(self._request("GET", storage_key, b""))

    def delete(self, storage_key: str) -> None:
        self._request("DELETE", storage_key, b"")

    def _request(self, method: str, storage_key: str, body: bytes) -> bytes:
        if storage_key.startswith("/") or ".." in storage_key.split("/"):
            raise FileNotFoundError("invalid storage identifier")
        canonical_uri = f"/{quote(self._bucket, safe='')}/{quote(storage_key, safe='/')}"
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_headers = (
            f"host:{self._host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            (method, canonical_uri, "", canonical_headers, signed_headers, payload_hash)
        )
        scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            )
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self._access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        request = Request(
            f"{self._endpoint}{canonical_uri}",
            data=body if method == "PUT" else None,
            method=method,
            headers={
                "Authorization": authorization,
                "Host": self._host,
                "X-Amz-Content-Sha256": payload_hash,
                "X-Amz-Date": amz_date,
            },
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - configured private endpoint
                return cast(bytes, response.read())
        except HTTPError as exc:
            raise S3StorageError(f"object storage request failed with status {exc.code}") from exc

    def _signing_key(self, date_stamp: str) -> bytes:
        date_key = hmac.new(
            f"AWS4{self._secret_key}".encode(), date_stamp.encode(), hashlib.sha256
        ).digest()
        region_key = hmac.new(date_key, self._region.encode(), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
