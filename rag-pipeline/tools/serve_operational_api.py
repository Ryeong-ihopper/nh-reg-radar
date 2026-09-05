#!/usr/bin/env python
"""Serve the canonical operational RAG pipeline as an asynchronous HTTP API."""
from __future__ import annotations

import argparse
import hmac
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.service import OperationalReviewService, config_from_env  # noqa: E402


def create_app(*, allow_unauthenticated: bool = False):
    token = os.environ.get("NH_RAG_API_TOKEN")
    if not token and not allow_unauthenticated:
        raise RuntimeError(
            "NH_RAG_API_TOKEN is required; use --allow-unauthenticated only for local development"
        )
    service = OperationalReviewService(config_from_env())
    app = FastAPI(
        title="NH Advertisement Compliance RAG API",
        version="1.0.0",
        description="Asynchronous advertisement review using regulation-list v2 only.",
    )

    def authorize(x_api_key: str | None) -> None:
        if token and (x_api_key is None or not hmac.compare_digest(x_api_key, token)):
            raise HTTPException(status_code=401, detail="invalid API key")

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "regulation_v2_available": service.config.regulation_path.is_file(),
            "queue_workers": service.config.queue_workers,
        }

    @app.post("/v1/reviews", status_code=status.HTTP_202_ACCEPTED)
    async def submit(request: Request, x_api_key: str | None = Header(default=None)):
        authorize(x_api_key)
        body = await request.body()
        if len(body) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="request exceeds 25 MiB")
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        return service.submit(payload)

    @app.get("/v1/reviews/{job_id}")
    async def job(job_id: str, x_api_key: str | None = Header(default=None)):
        authorize(x_api_key)
        try:
            return service.store.read(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.get("/v1/reviews/{job_id}/result")
    async def result(job_id: str, x_api_key: str | None = Header(default=None)):
        authorize(x_api_key)
        try:
            return service.result(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.post("/v1/reviews/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    async def retry(job_id: str, x_api_key: str | None = Header(default=None)):
        authorize(x_api_key)
        try:
            return service.retry(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--allow-unauthenticated", action="store_true")
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(
        create_app(allow_unauthenticated=args.allow_unauthenticated),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
