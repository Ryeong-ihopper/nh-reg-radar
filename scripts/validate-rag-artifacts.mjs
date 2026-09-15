// Development-only JSON Schema validation; no Node dependency in the GPU runtime.
// node scripts/validate-rag-artifacts.mjs SCHEMA INPUT.json [INPUT.jsonl ...]
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';

export function validateValues(schema, values) {
  const validate = new Ajv2020({ allErrors: true, strict: false }).compile(schema);
  const failures = [];
  values.forEach((value, index) => {
    if (!validate(value)) failures.push({ index, errors: validate.errors.map(error => ({
      path: error.instancePath, keyword: error.keyword, message: error.message,
    })) });
  });
  return failures;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [schemaFile, ...inputs] = process.argv.slice(2);
  if (!schemaFile || !inputs.length) throw new Error('Usage: SCHEMA INPUT.json [INPUT.jsonl ...]');
  const schema = JSON.parse(await readFile(schemaFile, 'utf8'));
  let failed = false;
  for (const input of inputs) {
    const source = await readFile(input, 'utf8');
    const values = input.endsWith('.jsonl')
      ? source.split(/\r?\n/).filter(line => line.trim()).map(line => JSON.parse(line))
      : [JSON.parse(source)];
    const failures = validateValues(schema, values);
    console.log(JSON.stringify({ input, documents: values.length, failed: failures.length,
      errors: failures.slice(0, 3) }));
    failed ||= failures.length > 0;
  }
  process.exitCode = failed ? 1 : 0;
}
