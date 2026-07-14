# Worker

Queue-worker platform boundary. Liveness (`/health`) remains process-local. Readiness (`/ready`)
requires both Redis and a live consumer. The FastAPI lifespan supervises a dependency-injected
`JobRunner`; production starts the infrastructure consumer with no synthetic provider. Until the
external-engine lane supplies real adapters, claimed jobs fail closed with an explicit reason.

```bash
uv run --package nh-ad-worker uvicorn nh_ad_worker.main:app --app-dir apps/worker/src --port 8001
uv run --package nh-ad-worker pytest apps/worker/tests
```
