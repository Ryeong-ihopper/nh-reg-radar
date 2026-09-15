# -*- coding: utf-8 -*-
"""Call an OpenAI-compatible GPU model service; retain DGX SSH fallback."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_HOST = os.environ.get("DGX_HOST")
DEFAULT_KEY = Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None
LOCAL_ENDPOINT = os.environ.get(
    "NH_GPU_GEMMA_ENDPOINT",
    os.environ.get("DGX_GEMMA_LOCAL_ENDPOINT", "http://127.0.0.1:8102/v1/chat/completions"),
)
REMOTE_ENDPOINT = os.environ.get(
    "NH_GPU_GEMMA_REMOTE_ENDPOINT",
    os.environ.get("DGX_GEMMA_REMOTE_ENDPOINT", LOCAL_ENDPOINT),
)


def post_json(
    payload: dict,
    *,
    host: str | None = DEFAULT_HOST,
    key: Path | None = DEFAULT_KEY,
    timeout: int = 900,
) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        LOCAL_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        pass

    if not host or key is None:
        raise RuntimeError(
            "GPU Gemma endpoint is unavailable; set NH_GPU_GEMMA_ENDPOINT or configure "
            "DGX_HOST and DGX_SSH_KEY for the interim SSH fallback"
        )

    remote = (
        "import sys,urllib.request;"
        "data=sys.stdin.buffer.read();"
        f"req=urllib.request.Request('{REMOTE_ENDPOINT}',data=data,headers={{'Content-Type':'application/json'}});"
        f"sys.stdout.buffer.write(urllib.request.urlopen(req,timeout={timeout}).read())"
    )
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-i", str(key), host, "python3", "-c", shlex.quote(remote),
    ]
    process = subprocess.run(
        command,
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 60,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace"))
    return json.loads(process.stdout.decode("utf-8"))
