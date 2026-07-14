import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

import { validateOpenApi } from './openapi_tools.mjs';

const sourcePath = resolve(process.argv[2] ?? 'openapi/openapi.yaml');
const outputPath = resolve(process.argv[3] ?? 'generated/openapi/openapi.json');
const document = await validateOpenApi(sourcePath);

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(document, null, 2)}\n`, 'utf8');
console.log(`Generated OpenAPI JSON: ${outputPath}`);
