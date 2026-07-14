---
name: adr-management
description: Review ADR candidates, compare alternatives, record accepted decisions, and synchronize the ADR index and affected source-of-truth documents. Use when creating, changing, superseding, or checking an architecture decision in this repository.
---

# ADR Management

Use this skill when reviewing ADR candidates, preparing decision options, or recording accepted architecture decisions for this project.

## Source Of Truth

Read these files before changing ADR-related content:

- `docs/adr-candidates.md`
- `docs/adr/README.md`
- `docs/adr/decision-questions.md`
- Relevant existing `docs/adr/ADR-*.md`
- `docs/project-rules.md`

## Workflow

1. Identify the next undecided ADR candidate from `docs/adr-candidates.md`.
2. Check whether the same decision is already covered by an accepted ADR.
3. Present options, tradeoffs, and one recommended option to the user.
4. After the user decides, create or update the ADR document.
5. Update the ADR index, decision questions, candidate status, and any affected source-of-truth docs in the same change.
6. Run the ADR and document consistency checks before finishing.

```bash
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
```

## Rules

- Do not create duplicate ADRs for decisions already accepted.
- Do not edit an Accepted ADR to reverse its decision before the user approves a new superseding decision.
- Keep accepted decisions concrete enough to guide implementation.
- Link related ADRs when decisions constrain each other.
- Treat AI-generated ADR text as a draft; the responsible developer owns final consistency.
- Do not include customer confidential data, secrets, or personal information in examples.
