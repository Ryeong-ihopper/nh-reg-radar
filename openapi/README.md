# OpenAPI contract tooling

`openapi/openapi.yaml` is the source contract. Install exactly the locked Node
dependencies with `npm ci`; do not use transient `npx` downloads.

Run the complete M0 contract gate with:

```bash
npm run openapi:check
```

`npm run openapi:generate` writes a deterministic JSON representation to
`generated/openapi/openapi.json`. The entire `generated/` tree is reproducible
and Git-ignored; committed source files must not depend on an unstated generated
artifact.

After a backend exists, export its OpenAPI JSON to a generated path and compare
contract-bearing paths, methods, operation IDs, parameters, request bodies,
responses/status codes, security declarations, and component schemas:

```bash
python3 scripts/compare_openapi_contract.py \
  openapi/openapi.yaml generated/backend/openapi.json
```
