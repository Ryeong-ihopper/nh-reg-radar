# Backend

FastAPI platform boundary. M1 exposes only `/health`; capability routes are added by their
own milestone contract gate.

```bash
uv run --package nh-ad-backend uvicorn nh_ad_backend.main:app --app-dir apps/backend/src --reload
uv run --package nh-ad-backend pytest apps/backend/tests
```
