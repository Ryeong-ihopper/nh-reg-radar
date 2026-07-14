import assert from 'node:assert/strict';
import test from 'node:test';

import SwaggerParser from '@apidevtools/swagger-parser';

import {
  collectOperationIds,
  loadOpenApi,
  validateOpenApi,
  validateSchemaExamples,
} from '../../scripts/openapi_tools.mjs';

const contractPath = new URL('../../openapi/openapi.yaml', import.meta.url).pathname;

test('TC-NFR-API-001: M5 source document is valid and capability-bounded', async () => {
  const document = await validateOpenApi(contractPath);
  assert.equal(document.openapi, '3.1.0');
  assert.equal(typeof document.info.title, 'string');
  assert.equal(document.info.version, '0.5.0');
  assert.deepEqual(Object.keys(document.paths).sort(), [
    '/admin/audit-logs',
    '/advertisements',
    '/advertisements/{advertisementId}',
    '/advertisements/{advertisementId}/reviews',
    '/auth/login',
    '/auth/logout',
    '/auth/refresh',
    '/codes/{codeGroup}',
    '/evidence-chunks/{evidenceChunkId}',
    '/evidences/search',
    '/evidences/{evidenceId}',
    '/evidences/{evidenceId}/chunks',
    '/files/{fileId}/download',
    '/files/{fileId}/preview',
    '/files/{fileId}/preview/content',
    '/reviews/{reviewId}/annotations',
    '/reviews/{reviewId}/items',
    '/reviews/{reviewId}/items/{reviewItemId}',
    '/reviews/{reviewId}/rerun',
    '/reviews/{reviewId}/status',
    '/reviews/{reviewId}/summary',
    '/standard-reindex-jobs/{jobId}',
    '/standards',
    '/standards/{standardId}',
    '/standards/{standardId}/deactivate',
    '/standards/{standardId}/histories',
    '/standards/{standardId}/versions/{standardVersionId}/reindex',
    '/users/me',
  ]);
  assert.ok(Object.hasOwn(document.components.schemas, 'ErrorResponse'));
});

test('TC-NFR-API-007: every local ref resolves', async () => {
  const dereferenced = await SwaggerParser.dereference(contractPath);
  const responseSchema = dereferenced.components.responses.Unauthorized.content['application/json'].schema;
  assert.equal(responseSchema, dereferenced.components.schemas.ErrorResponse);
});

test('TC-NFR-API-007/TC-COM-009: documented example satisfies ErrorResponse', async () => {
  const document = await loadOpenApi(contractPath);
  assert.doesNotThrow(() => validateSchemaExamples(document));

  const invalid = structuredClone(document);
  delete invalid.components.schemas.ErrorResponse.example.traceId;
  assert.throws(() => validateSchemaExamples(invalid), /Invalid example for ErrorResponse/);
});

test('TC-NFR-API-008: duplicate and missing operationIds are rejected non-vacuously', () => {
  const duplicate = {
    paths: {
      '/a': { get: { operationId: 'readThing' } },
      '/b': { post: { operationId: 'readThing' } },
    },
  };
  assert.throws(() => collectOperationIds(duplicate), /Duplicate operationId/);
  assert.throws(
    () => collectOperationIds({ paths: { '/a': { get: {} } } }),
    /Missing operationId/,
  );
});
