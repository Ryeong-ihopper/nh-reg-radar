# nh-parser-fin deployment overlay

Upstream baseline: `402ab4b`.

Before packaging, apply `0001-product-scoped-template-resolution.patch` to a clean checkout.
The patch fixes the upstream regression reproduced by
`tests/test_products.py::test_visible_product_name_corrects_a_false_not_shown_judgment`:
a multi-product filename must not inject another product's subtype into per-product template
resolution. The rule is product-scoped and contains no advertisement ID, answer, or case-specific
runtime literal.

After applying it, run the upstream Python 3.13 test suite. The deployment source is acceptable only
when all 72 tests pass.
