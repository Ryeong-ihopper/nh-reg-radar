FROM python:3.11-slim AS source

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY packages/parser-contracts /parser-contracts
COPY packages/ai-providers /ai-providers
COPY apps/backend/pyproject.toml ./
COPY apps/backend/src ./src

FROM source AS development
RUN pip install --no-cache-dir --editable /parser-contracts --editable /ai-providers --editable .
CMD ["uvicorn", "nh_ad_backend.main:create_app", "--factory", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM source AS production
RUN pip install --no-cache-dir /parser-contracts /ai-providers .
RUN useradd --create-home --uid 10001 appuser
USER appuser
CMD ["uvicorn", "nh_ad_backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
