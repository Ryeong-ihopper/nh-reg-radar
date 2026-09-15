# Parser integration audit

## 문서 현행 정보

| Item | Value |
| --- | --- |
| 현행 버전 | v1.4 |
| 기준일 | 2026-09-15 |
| Status | Python 3.11 migration and bridge pilot ready; original-advertisement E2E pending |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.4 | 2026-09-15 | Standardized metadata headings for the repository documentation checks; preserved the original verification scope. |
| v1.3 | 2026-09-10 | Locked the reviewed parser to Python 3.11, verified its non-editable wheel, ran its full suite (188 passed, 38 skipped), and switched the private browser pilot profile to the versioned external-parser runner. |
| v1.2 | 2026-09-10 | Verified the reviewed parser source and CLI import under an isolated Python 3.11 environment with the parser dependency pin. |
| v1.1 | 2026-09-10 | Added the versioned adapter and explicit operational parser-runner selection. |
| v1.0 | 2026-09-10 | Recorded the active parser, reviewed parser, contract, visibility, and Python compatibility gaps. |

## Current state

- The reviewed `nh-ad-parser` revision is `f27b263` (2026-09-09).  The private browser pilot profile now invokes it through the explicit `nh_ad_parser_cli` runner using an isolated Python 3.11.5 interpreter.
- The canonical RAG continues to consume `nh-ad-review-evidence-v6` and `nh-ad-review-region-input-v1`; the versioned adapter accepts the reviewed parser's external pair only and converts it after ownership validation.
- The old `nh-parsing-test` lineage remains an explicit fallback runner (`nh_parsing_test_batch`).  It is not selected by the current private pilot profile.
- No new original advertisement has yet completed this profile end-to-end.  The current browser server is live, but a real upload is required before parser/OCR/VLM, retrieval, judgment, and bbox rendering can be accepted as operationally verified.

## Contract comparison

| Concern | Current operational parser | Reviewed `nh-ad-parser` | Required action |
| --- | --- | --- | --- |
| P1 contract | `nh-ad-review-evidence-v6` | `nh-ad-parse-evidence-v1` | Do not switch the bridge directly; add a versioned adapter or make the parser emit the canonical P1. |
| P3 contract | `nh-ad-review-region-input-v1` | `nh-ad-region-review-input-v1` | Same: translate and validate exact line ownership before RAG ingestion. |
| Text ownership | P1/P3 line references are checked by the existing RAG combiner. | The parser preserves line references and asserts one P3 ownership per P1 line. | Preserve this invariant in an adapter test; never merge same-label regions. |
| Coordinates and evidence | page/region/line bbox, OCR confidence, style, table data, parser/VLM provenance | canvas, region/line bbox, OCR confidence, style, table data, parser/VLM provenance | Sufficient for search evidence and viewer highlighting when coordinates exist. |
| Visibility | relative position, OCR line-height, and style availability | raw bbox plus font size/weight/color where available | Neither contract guarantees physical page dimensions or measured foreground/background contrast.  Do not auto-decide physical-size or contrast rules without those observations. |
| Classification/template | parser observation is retained but intake-confirmed detailed product classification controls routing | parser can infer classification/template | Keep parser classification as an observation only; the uploader must remain the source of confirmed product subtype. |

## Environment compatibility

- Both reviewed parser codebases compile under Python 3.11, so there is no syntax-level blocker.
- An isolated Python 3.11.5 environment successfully installed `pydantic`, `pypdfium2==5.12.0`, `Pillow`, and `requests`; it imported `nh_parser` and started `tools/parse.py --help` successfully.
- Both pin `pypdfium2==5.12.0`; the current RAG environment has 5.13.0.  The parser repository documents coordinate/text differences between those releases, so the parser service must keep its own 5.12.0 lock unless a coordinate regression suite approves an upgrade.
- PyPI currently marks the exact 5.12.0 artifact as yanked despite the Windows wheel being installable.  The DAP/Spark deployment must receive the verified wheel through its approved internal package source; it must not silently substitute 5.12.1 or 5.13.0.
- `nh-ad-parser` now declares Python `>=3.11,<3.12` and its `uv.lock` is fixed to Python 3.11.  Its non-editable wheel imported successfully with Python 3.11.5 and `pypdfium2==5.12.0`; its source suite passed with `PYTHONPATH=src` (188 passed, 38 skipped).  The optional private `document-processor` dependency for HWP/HWPX still needs an approved package source in the target environment when that file type is enabled.
- OCR and VLM endpoint addresses are configuration inputs.  A Spark profile and an H200 profile can use the same parser adapter only if the target VLM supports the required image request and structured JSON response contract.

## Safe migration sequence

1. Done: the canonical adapter accepts only the exact external P1/P3 pair, preserves original-file hashes, rejects line partition errors, and records adapter provenance in the integrated diagnostics.  The bridge has explicit `nh_parsing_test_batch` and `nh_ad_parser_cli` runner modes.
2. Done: establish the Python 3.11 parser-service lock using `pypdfium2==5.12.0`, verify a non-editable wheel, and run parser fixtures plus the full parser suite.
3. Run one new original advertisement through the browser pilot and record parser, retrieval, judgment, and viewer artifacts separately.  This is the acceptance test for the switched profile, not a substitute for it.
4. Add physical page width/height and a measured contrast result with method/provenance.  Missing measurements must remain `UNDETERMINED`/human review.
5. Before a production replacement decision, run coordinate and P1/P3 contract regressions with approved target-environment wheels and document the adapter/visibility contract in an ADR.

## Decision boundary

Changing the authoritative parser contract and the operational execution profile affects the parser/RAG boundary.  The adapter shape and the physical-visibility measurement contract need an ADR decision before the new parser replaces the current one.
