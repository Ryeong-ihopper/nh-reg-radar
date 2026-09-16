"""Server authentication and HTTPS boundaries, without GPU or private data."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from operational_server_config import load_server_config  # noqa: E402


def config(tmp_path):
    values = {"public_url": "https://review.example:5180", "login_id": "reviewer"}
    for field, text in (("password_file", "synthetic-test-password-only"),
                        ("jwt_secret_file", "synthetic-jwt-secret-for-tests-only-1234"),
                        ("tls_cert_file", "fixture"), ("tls_key_file", "fixture")):
        path = tmp_path / field
        path.write_text(text, encoding="utf-8")
        values[field] = str(path)
    path = tmp_path / "server.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path, values


@pytest.mark.parametrize("origin", ["http://review.example", "https://a:b@review.example",
                                    "https://review.example/path", "https://review.example?q=1"])
def test_server_rejects_non_https_or_ambiguous_origin(tmp_path, origin):
    path, values = config(tmp_path)
    values["public_url"] = origin
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ValueError):
        load_server_config(path)


def test_server_requires_real_secret_files_and_certificate_paths(tmp_path):
    path, values = config(tmp_path)
    Path(values["password_file"]).write_text("admin", encoding="utf-8")
    with pytest.raises(ValueError, match="too short"):
        load_server_config(path)
    Path(values["password_file"]).unlink()
    with pytest.raises(FileNotFoundError):
        load_server_config(path)


def test_server_disables_auto_login_and_never_exports_credentials(tmp_path):
    path, values = config(tmp_path)
    spec = importlib.util.spec_from_file_location("operational_server_test", ROOT / "scripts/serve-operational-review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html>fixture</html>", encoding="utf-8")
    args = SimpleNamespace(state_dir=tmp_path / "state", static_dir=static, port=5180,
                           server_config=path, execution_config=tmp_path / "execution.json")
    with patch("operational_web_bridge.ExecutionBridge"):
        app = module.build_operational_server(args)
    with TestClient(app, base_url=values["public_url"]) as client:
        assert client.get("/open/anything").status_code == 404
        assert client.get("/api/v1/advertisements").status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": "admin", "password": "admin"}).status_code == 401
        login = client.post("/api/v1/auth/login", json={"email": "reviewer", "password": "synthetic-test-password-only"})
        assert login.status_code == 200
        assert "Secure" in login.headers["set-cookie"]
        assert "HttpOnly" in login.headers["set-cookie"]
        assert login.headers["cache-control"] == "no-store"
        token = login.json()["accessToken"]
        assert client.get("/api/v1/advertisements", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    manifest = json.loads((args.state_dir / "viewer-session.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"url", "mode"}


def test_linux_soffice_resolution_and_isolated_user_profile(tmp_path):
    import local_hwp_preview as preview
    binary = tmp_path / "soffice"
    binary.write_bytes(b"fixture")
    with patch.dict("os.environ", {}, clear=True), patch.object(preview.shutil, "which", return_value=str(binary)):
        assert preview.resolve_soffice() == binary
    commands = []

    def convert(command, **kwargs):
        commands.append(command)
        out = Path(command[command.index("--outdir") + 1])
        (out / "input.pdf").write_bytes(b"%PDF-fixture")
        return SimpleNamespace(returncode=0)

    with patch.object(preview, "resolve_soffice", return_value=binary), patch.object(preview.subprocess, "run", side_effect=convert):
        assert preview.convert_hwp_to_pdf(b"input", "a.hwp").startswith(b"%PDF-")
        assert preview.convert_hwp_to_pdf(b"input", "b.hwpx").startswith(b"%PDF-")
    assert commands[0][1].startswith("-env:UserInstallation=file:")
    assert commands[0][1] != commands[1][1]
