"""Small, dependency-free security primitives with injectable time for tests."""

import base64
import hashlib
import hmac
import json
import secrets
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from nh_ad_backend.domain import CurrentUser, User


class TokenError(ValueError):
    """Raised when a bearer token cannot be trusted."""


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class TokenService:
    """Issue and verify HS256 access tokens and opaque refresh tokens."""

    def __init__(
        self,
        secret: str,
        *,
        now: Callable[[], datetime] | None = None,
        access_ttl: timedelta = timedelta(minutes=30),
        refresh_ttl: timedelta = timedelta(days=7),
    ) -> None:
        if len(secret) < 32:
            raise ValueError("JWT secret must contain at least 32 characters")
        self._secret = secret.encode("utf-8")
        self._now = now or (lambda: datetime.now(UTC))
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

    def issue_access_token(self, user: User) -> str:
        issued_at = self._now()
        payload: dict[str, Any] = {
            "sub": user.user_id,
            "user_id": user.user_id,
            "department_id": user.department_id,
            "roles": list(user.roles),
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + self.access_ttl).timestamp()),
            "jti": secrets.token_urlsafe(18),
            "token_version": user.auth_token_version,
        }
        header = {"alg": "HS256", "typ": "JWT"}
        encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"

    def verify_access_token(self, token: str) -> dict[str, Any]:
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
            expected = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, _b64url_decode(encoded_signature)):
                raise TokenError("invalid token signature")
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise TokenError("invalid access token") from exc
        if header != {"alg": "HS256", "typ": "JWT"}:
            raise TokenError("unsupported token header")
        required = {
            "sub",
            "user_id",
            "department_id",
            "roles",
            "iat",
            "exp",
            "jti",
            "token_version",
        }
        if not required.issubset(payload):
            raise TokenError("missing token claim")
        if not all(
            isinstance(payload[key], str) and payload[key]
            for key in ("sub", "user_id", "department_id", "jti")
        ):
            raise TokenError("invalid identity claim")
        if payload["sub"] != payload["user_id"]:
            raise TokenError("subject mismatch")
        if not isinstance(payload["roles"], list) or not all(
            isinstance(role, str) for role in payload["roles"]
        ):
            raise TokenError("invalid roles claim")
        if not all(type(payload[key]) is int for key in ("iat", "exp", "token_version")):
            raise TokenError("invalid numeric claim")
        now_timestamp = int(self._now().timestamp())
        if payload["iat"] > now_timestamp + 60 or payload["exp"] <= payload["iat"]:
            raise TokenError("invalid token lifetime")
        if payload["exp"] - payload["iat"] > int(self.access_ttl.total_seconds()):
            raise TokenError("invalid token lifetime")
        if payload["token_version"] < 1:
            raise TokenError("invalid token version")
        if payload["exp"] <= now_timestamp:
            raise TokenError("expired access token")
        if not isinstance(payload, dict):
            raise TokenError("invalid token payload")
        return cast(dict[str, Any], payload)

    def new_refresh_token(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(48)
        return token, self.hash_refresh_token(token)

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Return an encoded scrypt password hash; the clear text is never retained."""

    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${_b64url_encode(actual_salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64url_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(digest, _b64url_decode(expected))
    except (ValueError, TypeError):
        return False


def validate_password(password: str, user: User) -> bool:
    lowered = password.casefold()
    forbidden = (user.email.casefold(), user.user_name.casefold(), user.user_id.casefold())
    return len(password) >= 10 and all(value not in lowered for value in forbidden if value)


def current_user(user: User) -> CurrentUser:
    return CurrentUser(
        user_id=user.user_id,
        user_name=user.user_name,
        department_id=user.department_id,
        department_name=user.department_name,
        roles=user.roles,
        token_version=user.auth_token_version,
    )


class LoginRateLimiter:
    """Process-local IP limiter implementing the ADR-0058 observation thresholds."""

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, ip_address: str) -> bool:
        current = self._now()
        attempts = self._attempts[ip_address]
        ten_minutes_ago = current - timedelta(minutes=10)
        while attempts and attempts[0] <= ten_minutes_ago:
            attempts.popleft()
        one_minute_ago = current - timedelta(minutes=1)
        recent = sum(attempt > one_minute_ago for attempt in attempts)
        if recent >= 10 or len(attempts) >= 50:
            return False
        attempts.append(current)
        return True
