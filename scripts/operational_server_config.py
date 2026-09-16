"""Explicit authenticated server settings; loopback demo defaults stay local."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ServerConfig:
    public_url: str
    bind_host: str
    login_id: str
    password: str
    jwt_secret: str
    tls_cert_file: str
    tls_key_file: str


def load_server_config(path: Path) -> ServerConfig:
    value = json.loads(path.read_text(encoding="utf-8"))
    public_url = str(value["public_url"]).rstrip("/")
    url = urlsplit(public_url)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment):
        raise ValueError("public_url must be a bare HTTPS origin")

    def secret(field: str, minimum: int) -> str:
        text = Path(value[field]).read_text(encoding="utf-8").strip()
        if len(text) < minimum:
            raise ValueError(f"{field} is too short")
        return text

    login_id = str(value["login_id"]).strip()
    if not login_id:
        raise ValueError("server login_id is required")
    for field in ("tls_cert_file", "tls_key_file"):
        if not Path(value[field]).is_file():
            raise ValueError(f"{field} is required for server TLS")
    return ServerConfig(public_url, str(value.get("bind_host", "0.0.0.0")), login_id,
                        secret("password_file", 16), secret("jwt_secret_file", 32),
                        value["tls_cert_file"], value["tls_key_file"])
