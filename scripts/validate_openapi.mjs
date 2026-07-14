import { resolve } from 'node:path';

import { validateOpenApi } from './openapi_tools.mjs';

const contractPath = resolve(process.argv[2] ?? 'openapi/openapi.yaml');
const document = await validateOpenApi(contractPath);
const operationCount = Object.values(document.paths ?? {}).reduce(
  (count, pathItem) => count + Object.keys(pathItem ?? {}).length,
  0,
);
console.log(`OpenAPI validation passed: ${contractPath} (${operationCount} operations)`);
