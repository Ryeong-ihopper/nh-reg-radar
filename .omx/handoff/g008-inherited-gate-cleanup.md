# G008 inherited gate cleanup plan

## Scope and stop condition

- Preserve product behavior and test expectations.
- Change only formatting in `apps/backend/src/nh_ad_backend/support_api.py`, `apps/backend/tests/test_m6_support_api.py`, and `scripts/validate_goal_manifest.py`.
- Change only trace metadata in `governance/goal-manifests/G004-m3.json` and `governance/goal-manifests/G007-m6-support-outputs.json`.
- Do not change dependencies, schedules/Kanban, `.omx/ultragoal`, Accepted ADRs, or executable product logic.
- Stop when the exact manifest validator reports zero errors and all required regression/governance gates pass.

## Baseline failures recorded before edits

- `uv run ruff format --check apps/backend/src/nh_ad_backend/support_api.py apps/backend/tests/test_m6_support_api.py scripts/validate_goal_manifest.py` exited 1: exactly those three files would be reformatted.
- `python3 scripts/validate_goal_manifest.py` exited 1 with 11 inherited errors:
  - one invalid G007 integration test node without `::`;
  - one stale G004 OpenAPI node symbol (`M5 source document`);
  - two missing G007 contract node symbols;
  - six ranged/undeclared test-case IDs (`TC-SUG`, `TC-QA`, `TC-OPN`, `TC-RPT`, `TC-CMP`, `TC-NFR-HIS`);
  - one undeclared G007 requirement trace (`AC-014`).

## Minimal repair sequence

1. Run Ruff formatter only on the three named Python files and confirm semantic diffs are formatting-only.
2. Inspect declared test-case IDs and executable node symbols, then replace only stale/ranged manifest metadata with exact declared IDs and real executable symbols.
3. Preserve G007 coverage when removing undeclared `AC-014` by mapping the same history behavior to declared source IDs and executable history tests.
4. Run focused M6 tests/contracts, exact manifest validation, Ruff format/check, mypy, documentation consistency, doc_guard validation, governance tests, and `git diff --check`.
5. Review the final diff for the five-file scope plus this plan artifact and create one Lore commit.
