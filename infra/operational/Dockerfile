# Same application image on Spark arm64 and H200 amd64; endpoints are runtime configuration.
FROM eclipse-temurin:25-jre AS java
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/ ./
ENV VITE_OPERATIONAL_REVIEW=true
RUN npm run build:operational

# nh-parser-fin requires Python >=3.13. Keep it isolated from the canonical
# application/RAG Python 3.11 environment instead of relaxing either runtime's
# declared contract.
FROM python:3.13-slim-trixie AS parser-runtime
WORKDIR /parser-source
COPY infra/operational/requirements-parser.txt /tmp/requirements-parser.txt
COPY private/nh-parser/ ./
RUN pip install --no-cache-dir -r /tmp/requirements-parser.txt .

# Only explicitly reviewed application files reach the final image.
FROM python:3.11-slim-trixie AS application-source
WORKDIR /source
COPY apps/backend/src apps/backend/src
COPY packages/ai-providers/src packages/ai-providers/src
COPY packages/parser-contracts/src packages/parser-contracts/src
COPY rag-pipeline/rag rag-pipeline/rag
COPY rag-pipeline/tools rag-pipeline/tools
COPY rag-pipeline/schemas rag-pipeline/schemas
COPY rag-pipeline/config rag-pipeline/config
COPY scripts scripts
COPY infra/operational/runtime-files.json infra/operational/
RUN python scripts/operational_runtime.py --output /runtime

FROM python:3.11-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:$PATH NH_LOCAL_SOFFICE=/usr/bin/soffice \
    LD_LIBRARY_PATH=/opt/python313/lib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-h2orestart libreoffice-java-common \
    fonts-noto-cjk fontconfig libgomp1 ca-certificates chromium \
    && rm -rf /var/lib/apt/lists/*
COPY --from=java /opt/java/openjdk /opt/java/openjdk
WORKDIR /app
COPY rag-pipeline/requirements-rag.txt /tmp/nh-dependencies/rag-pipeline/
COPY infra/operational/requirements-web.txt /tmp/nh-dependencies/infra/operational/
RUN pip install --no-cache-dir -r /tmp/nh-dependencies/infra/operational/requirements-web.txt \
    && rm -rf /tmp/nh-dependencies
COPY --from=parser-runtime /usr/local /opt/python313
# Supplied private sources are frozen by the package manifest; no credentials or .env are copied.
COPY private/nh-parser /opt/nh-parser
COPY private/document-processor /opt/document-processor
COPY --from=application-source /runtime/ /app/
COPY --from=frontend /frontend/dist apps/frontend/dist
RUN /opt/python313/bin/python3.13 -c "import nh_parser_fin, requests, pypdfium2, jpype" \
    && python -c "import sys; assert sys.version_info[:2] == (3, 11)"
RUN useradd --uid 10001 --create-home nhapp && mkdir -p /state /work \
    && chown nhapp:nhapp /state /work
USER nhapp
EXPOSE 5180
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import ssl,urllib.request; urllib.request.urlopen('https://127.0.0.1:5180/api/v1/health',context=ssl._create_unverified_context(),timeout=4)"
CMD ["python", "scripts/serve-operational-review.py", "--static-dir", "apps/frontend/dist", "--state-dir", "/state", "--execution-config", "/run/config/execution.json", "--server-config", "/run/config/server.json", "--port", "5180"]
