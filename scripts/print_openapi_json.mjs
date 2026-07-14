import { resolve } from 'node:path';

import { loadOpenApi } from './openapi_tools.mjs';

const sourcePath = resolve(process.argv[2]);
process.stdout.write(JSON.stringify(await loadOpenApi(sourcePath)));
