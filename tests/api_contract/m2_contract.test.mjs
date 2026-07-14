import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import SwaggerParser from '@apidevtools/swagger-parser';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('tests/fixtures/m2/trace-manifest.json', root).pathname;

test('TC-COM-001..015/TC-ADV-001..017: manifest locks the exact M2 contract', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const operationIds = [...collectOperationIds(document).keys()];

  assert.equal(manifest.goalId, 'G003-m2');
  assert.equal(manifest.openapi.version, document.info.version);
  assert.deepEqual(manifest.openapi.operationIds, operationIds);
  assert.deepEqual(manifest.openapi.schemas, Object.keys(document.components.schemas));

  for (const excluded of manifest.excludedCapabilities) {
    assert.equal(
      JSON.stringify(document).toLowerCase().includes(excluded),
      false,
      `M3+ capability leaked into M2: ${excluded}`,
    );
  }
});

test('TC-COM-003/004/014/015: auth and negative-scope responses are explicit', async () => {
  const document = await loadOpenApi(contractPath);
  assert.deepEqual(document.security, [{ BearerAuth: [] }]);
  assert.deepEqual(document.paths['/auth/login'].post.security, []);

  for (const path of ['/auth/refresh', '/auth/logout']) {
    const operation = document.paths[path].post;
    assert.deepEqual(operation.security, [{ RefreshCookie: [] }]);
    assert.equal(operation.parameters[0].$ref, '#/components/parameters/Origin');
    assert.ok(Object.hasOwn(operation.responses, '403'));
  }

  for (const [path, method] of [
    ['/advertisements/{advertisementId}', 'get'],
    ['/files/{fileId}/preview', 'get'],
    ['/files/{fileId}/preview/content', 'get'],
    ['/files/{fileId}/download', 'get'],
    ['/admin/audit-logs', 'get'],
  ]) {
    assert.ok(Object.hasOwn(document.paths[path][method].responses, '403'), `${path} lacks 403`);
  }
});

test('TC-ADV-001..010: upload contract locks multipart, boundaries, and safe status codes', async () => {
  const document = await loadOpenApi(contractPath);
  const create = document.paths['/advertisements'].post;
  const media = create.requestBody.content['multipart/form-data'];
  assert.equal(media.schema.$ref, '#/components/schemas/CreateAdvertisementRequest');
  assert.deepEqual(Object.keys(create.responses).sort(), [
    '201',
    '400',
    '401',
    '403',
    '409',
    '413',
    '415',
  ]);

  const file = document.components.schemas.AdvertisementFile;
  assert.equal(file.properties.fileSize.maximum, 52_428_800);
  const request = document.components.schemas.CreateAdvertisementRequest;
  assert.match(request.properties.advertisementFile.description, /jpg\/jpeg\/png\/pdf\/hwp\/hwpx/);
});

test('TC-COM-009/013 and file access: response schemas redact storage and audit internals', async () => {
  const document = await loadOpenApi(contractPath);
  const forbiddenResponseFields = new Set([
    'filePath',
    'storedFileName',
    'objectKey',
    'presignedUrl',
    'refreshToken',
    'password',
    'tokenHash',
    'beforeJson',
    'afterJson',
    'metadataJson',
    'ipAddress',
    'userAgent',
  ]);
  for (const schemaName of [
    'AdvertisementFile',
    'AdvertisementSummary',
    'AdvertisementDetail',
    'FilePreview',
    'AuditLogSummary',
  ]) {
    const serialized = JSON.stringify(document.components.schemas[schemaName]);
    for (const field of forbiddenResponseFields) {
      assert.equal(serialized.includes(`\"${field}\"`), false, `${schemaName} exposes ${field}`);
    }
  }

  const previewPathPattern = new RegExp(
    document.components.schemas.FilePreview.properties.previewPath.pattern,
  );
  assert.equal(previewPathPattern.test('/api/v1/files/FILE-0001/preview/content'), true);
  assert.equal(previewPathPattern.test('/api/v1/files/FILE-0001/preview/content?pageNo=1'), false);
  assert.ok(Object.hasOwn(document.paths, '/files/{fileId}/preview/content'));
  const download = document.paths['/files/{fileId}/download'].get.responses['200'];
  assert.equal(download.content['application/octet-stream'].schema.format, 'binary');
});

test('TC-COM-001/TC-ADV-014: real login and detail examples satisfy flattened schemas', async () => {
  const document = await SwaggerParser.dereference(contractPath);
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  for (const [path, method, status] of [
    ['/auth/login', 'post', '200'],
    ['/advertisements/{advertisementId}', 'get', '200'],
  ]) {
    const media = document.paths[path][method].responses[status].content['application/json'];
    assert.equal(
      ajv.validate(media.schema, media.example),
      true,
      `${method.toUpperCase()} ${path}: ${ajv.errorsText(ajv.errors)}`,
    );
  }
});

test('M2 fixture is synthetic, versioned, and hash-locked to real TC IDs', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const testCases = await readFile(new URL('docs/test-cases.md', root), 'utf8');

  assert.equal(new Set(manifest.testCaseIds).size, manifest.testCaseIds.length);
  for (const id of manifest.testCaseIds) {
    assert.match(id, /^TC-(?:COM|ADV)-\d{3}$/);
    assert.match(testCases, new RegExp(`\\| ${id} \\|`), `${id} is not a real test-case ID`);
  }

  for (const fixture of manifest.fixtures) {
    assert.equal(fixture.kind, 'synthetic');
    assert.equal(fixture.containsCustomerData, false);
    assert.ok(Number.isInteger(fixture.version) && fixture.version > 0);
    const bytes = await readFile(new URL(fixture.path, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), fixture.sha256);
  }
});
