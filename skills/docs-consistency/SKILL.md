---
name: docs-consistency
description: Check and maintain consistency among project specifications, README, ADRs, API examples, and OpenAPI contracts. Use whenever documentation or implementation changes may require synchronized source-of-truth updates.
---

# Docs Consistency

Use this skill whenever project documentation changes, especially Markdown docs under `docs/`, API examples, ADRs, README, or OpenAPI-related files.

## Required Checks

Run:

```bash
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
```

The script checks:

- Markdown internal links in `docs/**/*.md` and `README.md`
- JSON code blocks in `docs/api-specification.md`
- OpenAPI lint when `openapi/openapi.yaml` and a Spectral executable are available
- Required documents, metadata, ADR index, traceability, and change-impact rules from `governance/document-policy.json`

Before changing a contract or behavior, inspect the expected propagation targets:

```bash
python3 -m scripts.doc_guard impact --scope working
```

## Manual Review Checklist

When a document changes, also check whether related source-of-truth documents need updates:

- Requirement changes: `docs/requirements-definition.md`, `docs/functional-specification.md`, `docs/test-cases.md`
- Screen changes: `docs/screen-specification.md`, `docs/screen-api-mapping.md`, `docs/api-specification.md`
- API changes: `openapi/openapi.yaml`, `docs/api-specification.md`, `docs/screen-api-mapping.md`, `docs/test-cases.md`
- DB changes: `docs/database-specification.md`, API docs, test cases
- Architecture decisions: `docs/adr/README.md`, `docs/adr/decision-questions.md`, `docs/adr-candidates.md`

## Rules

- Git `docs/` is the development source of truth.
- Notion is not the authoritative source for implementation contracts.
- If a hook fails, fix the document inconsistency instead of bypassing the hook.
- Local hooks can be bypassed, so important checks should also run in CI when CI is available.
