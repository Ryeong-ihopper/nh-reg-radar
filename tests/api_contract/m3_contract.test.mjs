import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('tests/fixtures/m3/trace-manifest.json', root).pathname;

test('G004-m3 manifest freezes the Standards/Evidence/Reindex/Search boundary', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const operations = collectOperationIds(document);

  assert.equal(manifest.goalId, 'G004-m3');
  assert.equal(document.info.version, manifest.openapi.version);
  for (const operationId of manifest.openapi.operationIds) {
    assert.ok(operations.has(operationId), `missing operationId ${operationId}`);
  }
  for (const schema of manifest.openapi.schemas) {
    assert.ok(Object.hasOwn(document.components.schemas, schema), `missing schema ${schema}`);
  }
});

test('TC-STD-001..015: standards lifecycle and admin boundaries are explicit', async () => {
  const document = await loadOpenApi(contractPath);
  for (const [path, method] of [
    ['/standards', 'get'],
    ['/standards', 'post'],
    ['/standards/{standardId}', 'get'],
    ['/standards/{standardId}', 'patch'],
    ['/standards/{standardId}/deactivate', 'patch'],
    ['/standards/{standardId}/histories', 'get'],
    ['/standards/{standardId}/versions/{standardVersionId}/reindex', 'post'],
    ['/standard-reindex-jobs/{jobId}', 'get'],
    ['/evidences/{evidenceId}/chunks', 'get'],
    ['/evidence-chunks/{evidenceChunkId}', 'get'],
  ]) {
    const operation = document.paths[path]?.[method];
    assert.ok(operation, `missing ${method.toUpperCase()} ${path}`);
    assert.ok(Object.hasOwn(operation.responses, '401'));
    assert.ok(Object.hasOwn(operation.responses, '403'));
  }

  assert.equal(
    document.paths['/standards'].post.requestBody.content['multipart/form-data'].schema.$ref,
    '#/components/schemas/CreateStandardRequest',
  );
  assert.equal(
    document.components.schemas.CreateStandardRequest.properties.content.minLength,
    1,
  );
  assert.equal(
    document.components.schemas.StandardHistoryPage.properties.contents.items.$ref,
    '#/components/schemas/StandardDetail',
  );
});

test('TC-EVD-001..006: deterministic search contract locks modes, limits, version, and rank', async () => {
  const document = await loadOpenApi(contractPath);
  const search = document.paths['/evidences/search'].get;
  const parameters = new Map(
    search.parameters.map((parameter) => [
      parameter.name ?? parameter.$ref.split('/').at(-1),
      parameter,
    ]),
  );

  assert.equal(parameters.get('keyword').required, true);
  assert.equal(parameters.get('limit').schema.default, 20);
  assert.equal(parameters.get('limit').schema.maximum, 20);
  assert.equal(parameters.get('searchMode').schema.$ref, '#/components/schemas/SearchMode');

  const result = document.components.schemas.EvidenceSearchResult;
  for (const field of [
    'evidenceId',
    'evidenceChunkId',
    'standardVersionId',
    'rankNo',
    'relevanceScore',
    'matchSource',
  ]) {
    assert.ok(result.required.includes(field), `EvidenceSearchResult must require ${field}`);
  }
});

test('TC-EVD-012..014/TC-STD-017: partial infrastructure failures are explicit, never fallback', async () => {
  const document = await loadOpenApi(contractPath);
  for (const [path, method] of [
    ['/evidences/search', 'get'],
    ['/standards/{standardId}/versions/{standardVersionId}/reindex', 'post'],
    ['/standard-reindex-jobs/{jobId}', 'get'],
  ]) {
    const response = document.paths[path][method].responses['503'];
    assert.ok(response, `${method.toUpperCase()} ${path} lacks explicit 503`);
    assert.equal(response.$ref, '#/components/responses/SearchUnavailable');
  }
  const unavailable = document.components.responses.SearchUnavailable;
  assert.match(unavailable.description, /no keyword-only or vector-only fallback/i);

  const job = document.components.schemas.StandardReindexJob;
  for (const field of ['qdrantStatus', 'opensearchStatus', 'failedReasonCode']) {
    assert.ok(Object.hasOwn(job.properties, field), `job lacks ${field}`);
  }
});

test('M3 fixture is synthetic, fixed, provider-free, tie-break deterministic, and hash locked', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const fixtureMeta = manifest.fixtures[0];
  const bytes = await readFile(new URL(fixtureMeta.path, root));
  const fixture = JSON.parse(bytes);

  assert.equal(createHash('sha256').update(bytes).digest('hex'), fixtureMeta.sha256);
  assert.equal(fixture.kind, 'synthetic');
  assert.equal(fixture.containsCustomerData, false);
  assert.equal(fixture.inputBoundary, 'DIRECT_TEXT_ONLY');
  assert.equal(fixture.embeddingProvider, null);
  assert.deepEqual(fixture.rankingPolicy.tieBreak, [
    'combinedScore DESC',
    'evidenceChunkId ASC',
  ]);
  assert.deepEqual(fixture.expected.top3, fixture.expected.top5.slice(0, 3));
  assert.deepEqual(fixture.expected.top5, fixture.expected.top20.slice(0, 5));
  assert.equal(fixture.infrastructureFailure.allowFallback, false);

  const testCases = await readFile(new URL('docs/test-cases.md', root), 'utf8');
  for (const id of manifest.testCaseIds) {
    assert.match(testCases, new RegExp(`\\| ${id} \\|`), `${id} is not a real TC ID`);
  }
});
