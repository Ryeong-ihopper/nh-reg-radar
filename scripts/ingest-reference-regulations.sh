#!/usr/bin/env bash
# Ingest ADR-0002-approved local regulation PDFs through the explicit dev-only
# OpenAI boundary. The script prints only sanitized ingestion identifiers.
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

ENV_FILE="${NH_LOCAL_DEV_ENV_FILE:-.env.dev}"
if [[ "${1:-}" == "--env-file" ]]; then
  [[ -n "${2:-}" ]] || { printf '%s\n' '--env-file requires a path' >&2; exit 64; }
  ENV_FILE="$2"
  shift 2
fi
if [[ "$ENV_FILE" != /* ]]; then ENV_FILE="$ROOT/$ENV_FILE"; fi
[[ -f "$ENV_FILE" ]] || { printf 'environment file not found: %s\n' "$ENV_FILE" >&2; exit 66; }

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Docker Engine and Docker Compose v2 are required' >&2
  exit 69
fi

COMPOSE=(docker compose -f compose.yml -f compose.dev.yml --env-file "$ENV_FILE")
"${COMPOSE[@]}" config --quiet

env_value() {
  "${COMPOSE[@]}" config --environment | sed -n "s/^$1=//p" | head -n 1
}

enabled="$(env_value NH_EXTERNAL_AI_ENABLED)"
api_key="$(env_value OPENAI_API_KEY)"
model="$(env_value OPENAI_MODEL)"
embedding_model="$(env_value OPENAI_EMBEDDING_MODEL)"
if [[ "$enabled" != "true" || -z "$api_key" || -z "$model" || -z "$embedding_model" ]]; then
  printf '%s\n' 'set NH_EXTERNAL_AI_ENABLED=true plus OPENAI_API_KEY, OPENAI_MODEL, and OPENAI_EMBEDDING_MODEL in .env.dev' >&2
  exit 65
fi
unset api_key model embedding_model

printf '%s\n' '[reference-ingest] running dev-only approved-PDF ingestion'
"${COMPOSE[@]}" run --rm --no-deps \
  --env 'NH_REFERENCE_EXTRACTOR=nh_ad_backend.openai_reference_extractor:OpenAIReferenceExtractor' \
  backend python -m nh_ad_backend.reference_ingestion "$@"
