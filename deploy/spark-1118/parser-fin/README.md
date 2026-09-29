# nh-parser-fin deployment overlay

Current upstream baseline: `9733d9fd49c3c16850da6844f38fa18a36296b6a` (2026-09-28).
Contracts: P1 `nh-ad-parse-evidence-v4`, P3 `nh-ad-region-review-input-v9`.
The previous deployed baseline was `402ab4b` (P1 v3/P3 v6).

Before packaging, apply `0001-product-scoped-template-resolution.patch` to a clean checkout.
The patch fixes the upstream regression reproduced by
`tests/test_products.py::test_visible_product_name_corrects_a_false_not_shown_judgment`:
a multi-product filename must not inject another product's subtype into per-product template
resolution. The rule is product-scoped and contains no advertisement ID, answer, or case-specific
runtime literal.

After applying it, run the upstream Python 3.13 test suite. The deployment source is acceptable only
when all 103 current upstream tests pass.

Use the explicit operational `parser_contract_profile=region-v9` and pin
`parser_revision` to the full commit SHA. Run `run.py --compact-output`; the
removed `--with-vlm` option must not be sent. HWP/HWPX uses the upstream
structure/render route with the existing private document-processor and local
Chromium. Display the emitted page images with the same canvas instead of an
independently converted preview. See `docs/parser-schema-current-2026-09-28.md`.

The final main refresh changes only README.md from fdfc09f. All parser code
hashes match that tested commit; the 103-test and actual-HWP records retain
their original execution revision. The final runtime pins 9733d9f.
