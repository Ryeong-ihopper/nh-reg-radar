# Same application image on Spark arm64 and H200 amd64; endpoints are runtime configuration.
FROM eclipse-temurin:25-jre AS java
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
ENV VITE_OPERATIONAL_REVIEW=true
RUN npm run build:operational

FROM python:3.11-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH NH_LOCAL_SOFFICE=/usr/bin/soffice
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-h2orestart libreoffice-java-common \
    fonts-noto-cjk fontconfig libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=java /opt/java/openjdk /opt/java/openjdk
WORKDIR /app
COPY rag-pipeline/requirements-rag.txt rag-pipeline/
COPY infra/operational/requirements-web.txt infra/operational/requirements-parser.txt infra/operational/
RUN pip install --no-cache-dir -r infra/operational/requirements-web.txt \
    && python -m venv /opt/parser-venv \
    && /opt/parser-venv/bin/pip install --no-cache-dir -r infra/operational/requirements-parser.txt
# Supplied private sources are frozen by the package manifest; no credentials or .env are copied.
COPY private/nh-parser /opt/nh-parser
COPY private/document-processor /opt/document-processor
COPY apps/backend/src apps/backend/src
COPY packages/ai-providers/src packages/ai-providers/src
COPY packages/parser-contracts/src packages/parser-contracts/src
COPY rag-pipeline/rag rag-pipeline/rag
COPY rag-pipeline/tools rag-pipeline/tools
COPY rag-pipeline/schemas rag-pipeline/schemas
COPY scripts scripts
COPY --from=frontend /frontend/dist apps/frontend/dist
RUN useradd --uid 10001 --create-home nhapp && mkdir -p /state /work \
    && chown nhapp:nhapp /state /work
USER nhapp
EXPOSE 5180
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import ssl,urllib.request; urllib.request.urlopen('https://127.0.0.1:5180/api/v1/health',context=ssl._create_unverified_context(),timeout=4)"
CMD ["python", "scripts/serve-operational-review.py", "--static-dir", "apps/frontend/dist", "--state-dir", "/state", "--execution-config", "/run/config/execution.json", "--server-config", "/run/config/server.json", "--port", "5180"]
