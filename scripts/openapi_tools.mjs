import { readFile } from 'node:fs/promises';

import SwaggerParser from '@apidevtools/swagger-parser';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import YAML from 'yaml';

export const HTTP_METHODS = new Set([
  'get',
  'put',
  'post',
  'delete',
  'options',
  'head',
  'patch',
  'trace',
]);

export async function loadOpenApi(filePath) {
  const source = await readFile(filePath, 'utf8');
  const document = YAML.parseDocument(source, { uniqueKeys: true });
  if (document.errors.length > 0) {
    throw new Error(document.errors.map((error) => error.message).join('\n'));
  }
  return document.toJS();
}

export function collectOperationIds(document) {
  const seen = new Map();
  for (const [path, pathItem] of Object.entries(document.paths ?? {})) {
    for (const [method, operation] of Object.entries(pathItem ?? {})) {
      if (!HTTP_METHODS.has(method.toLowerCase())) continue;
      const operationId = operation?.operationId;
      if (typeof operationId !== 'string' || operationId.length === 0) {
        throw new Error(`Missing operationId for ${method.toUpperCase()} ${path}`);
      }
      if (seen.has(operationId)) {
        throw new Error(
          `Duplicate operationId ${operationId}: ${seen.get(operationId)} and ${method.toUpperCase()} ${path}`,
        );
      }
      seen.set(operationId, `${method.toUpperCase()} ${path}`);
    }
  }
  return seen;
}

export function validateSchemaExamples(document) {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  for (const [name, schema] of Object.entries(document.components?.schemas ?? {})) {
    if (!Object.hasOwn(schema, 'example')) continue;
    const valid = ajv.validate(schema, schema.example);
    if (!valid) {
      throw new Error(`Invalid example for ${name}: ${ajv.errorsText(ajv.errors)}`);
    }
  }
}

export async function validateOpenApi(filePath) {
  const sourceDocument = await loadOpenApi(filePath);
  collectOperationIds(sourceDocument);
  validateSchemaExamples(sourceDocument);
  await SwaggerParser.validate(filePath);
  return sourceDocument;
}
