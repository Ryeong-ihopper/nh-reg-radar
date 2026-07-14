# Worker

Queue-worker platform boundary. M1 exposes liveness (`/health`) and Redis-backed readiness
(`/ready`) without capability business logic; job consumption starts in M4.

```bash
uv run --package nh-ad-worker uvicorn nh_ad_worker.main:app --app-dir apps/worker/src --port 8001
uv run --package nh-ad-worker pytest apps/worker/tests
```
