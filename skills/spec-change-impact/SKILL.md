---
name: spec-change-impact
description: Analyze and propagate behavior or contract changes across this repository's requirements, functions, screens, APIs, databases, tests, ADRs, deployment, and operations before implementation.
---

# Specification Change Impact

Use this skill for behavior, contract, data, architecture, deployment, or operations changes. It is unnecessary for typo-only edits.

## Identify The Upstream Source

State the requested change in one sentence and identify the authoritative upstream specification or Accepted ADR.

## Evaluate Every Layer

For requirements, functions, screens, APIs, databases, AI/RAG, tests, ADRs, deployment, operations, and schedules, identify whether the layer is affected and which file must change.

```bash
python3 -m scripts.doc_guard impact --scope working
```

## Apply In Dependency Order

Update upstream documents before downstream contracts, tests, and implementation. Reuse existing identifiers for existing behavior and allocate a new identifier only for a new item.

Confirm that requirements map to functions, functions map to screens/APIs/data, and acceptance criteria map to tests.

## Validate

```bash
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
```

Do not complete the change while governance errors remain.
