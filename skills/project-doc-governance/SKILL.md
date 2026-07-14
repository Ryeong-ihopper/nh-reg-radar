---
name: project-doc-governance
description: Enforce this repository's specification-driven document workflow when changing code, requirements, screens, APIs, databases, AI/RAG behavior, tests, infrastructure, deployment, or project documents.
---

# Project Document Governance

Use this workflow for every repository-changing task.

## Load The Source Of Truth

Read in this order:

1. `AGENTS.md`
2. `docs/project-rules.md`
3. Relevant specification documents
4. `docs/adr/README.md` and relevant Accepted ADRs
5. `governance/document-policy.json`

## Classify And Propagate The Change

Classify impact across requirements, functions, screens, APIs, databases, AI/RAG, infrastructure, tests, operations, and security.

```bash
python3 -m scripts.doc_guard impact --scope working
```

Update the authoritative upstream specification first, then every affected downstream document and implementation. Preserve existing requirement, function, screen, API, test, and ADR identifiers.

If the change requires a new architecture, security, or operations decision, record a candidate and question before editing an Accepted ADR. Wait for the user's decision.

## Validate

```bash
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
python3 -m unittest discover -s tests/governance -v
```

Fix every error. Review and explain each warning before completing the task.
