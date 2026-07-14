import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('governance/goal-manifests/G007-m6-support-outputs.json', root).pathname;

test('G007 M6 manifest freezes the provider-independent support-output contract', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  assert.equal(document.info.version, '0.8.0');
  assert.equal(manifest.openapi.version, '0.6.0');
  assert.equal(manifest.openapi.source_sha256, 'ab0311b4d075d79ee65648e3a35212b0ee6bd0f0e5dfbd1e56a3d7fe61ee29e5');
  assert.equal(manifest.generated_client.sha256, '9077dbaa41ff35703d3089382a5f608bcbf05de0a5aa798a6f17f56d5b5ca1e7');
  const operations = collectOperationIds(document);
  for (const operationId of manifest.openapi.operation_ids) assert.ok(operations.has(operationId), `missing ${operationId}`);
  for (const schema of manifest.openapi.schemas) assert.ok(Object.hasOwn(document.components.schemas, schema), `missing ${schema}`);
  for (const fixture of manifest.fixtures) {
    assert.equal(createHash('sha256').update(await readFile(new URL(fixture.path, root))).digest('hex'), fixture.sha256);
    assert.equal(fixture.kind, 'synthetic');
    assert.equal(fixture.contains_customer_data, false);
  }
});

test('TC-SUG-001..008: suggestions retain append-only human decisions', async () => {
  const document = await loadOpenApi(contractPath);
  assert.equal(document.paths['/reviews/{reviewId}/suggestions'].get.operationId, 'listReviewSuggestions');
  assert.equal(document.paths['/reviews/{reviewId}/suggestions'].get.responses['200'].content['application/json'].schema.type, 'array');
  assert.equal(document.paths['/suggestions/{suggestionId}/decision'].patch.operationId, 'recordSuggestionDecision');
  assert.deepEqual(document.components.schemas.SuggestionDecisionStatus.enum, ['PENDING', 'ACCEPTED', 'REJECTED', 'MODIFIED_AND_USED']);
  assert.deepEqual(document.components.schemas.SuggestionDecisionRequest.properties.decisionStatus.enum, ['ACCEPTED', 'REJECTED', 'MODIFIED_AND_USED']);
});

test('TC-QA-001..006 and TC-OPN-001..006: fixed references and editable draft boundary are explicit', async () => {
  const document = await loadOpenApi(contractPath);
  assert.equal(document.paths['/qa/questions'].post.operationId, 'askComplianceQuestion');
  assert.equal(document.paths['/qa/questions'].get.operationId, 'listComplianceQuestions');
  assert.equal(document.components.schemas.QaAnswer.properties.needsHumanReview.type, 'boolean');
  assert.equal(document.paths['/reviews/{reviewId}/opinion-drafts'].post.operationId, 'createOpinionDraft');
  assert.equal(document.paths['/reviews/{reviewId}/opinion-drafts'].get.responses['200'].content['application/json'].schema.type, 'array');
  assert.ok(document.components.schemas.OpinionDraft.required.includes('draftContent'));
  assert.ok(Object.hasOwn(document.components.schemas.OpinionDraft.properties, 'finalContent'));
});

test('TC-RPT-001..013 and TC-CMP-001..007: snapshots and structural comparison outcomes are frozen', async () => {
  const document = await loadOpenApi(contractPath);
  assert.equal(document.paths['/reviews/{reviewId}/reports'].post.operationId, 'createReviewReport');
  assert.equal(document.paths['/reports/{reportId}/download'].get.operationId, 'downloadReviewReport');
  assert.deepEqual(document.components.schemas.ReportFormat.enum, ['HWPX', 'PDF']);
  assert.deepEqual(document.components.schemas.ResolutionStatus.enum, ['RESOLVED', 'UNRESOLVED', 'NEW_ISSUE', 'CHECK_REQUIRED']);
  const fixture = JSON.parse(await readFile(new URL('tests/fixtures/m6/support-outputs-v1.json', root), 'utf8'));
  assert.equal(fixture.networkAllowed, false);
  assert.equal(fixture.provider, null);
  assert.deepEqual(fixture.comparison.statuses, ['RESOLVED', 'UNRESOLVED', 'NEW_ISSUE']);
});

test('TC-CMP-008..011: a stored multipart revision is registered before comparison', async () => {
  const document = await loadOpenApi(contractPath);
  const operation = document.paths['/advertisements/{advertisementId}/revisions'].post;
  assert.equal(operation.operationId, 'createAdvertisementRevision');
  assert.equal(operation.requestBody.content['multipart/form-data'].schema.$ref, '#/components/schemas/AdvertisementRevisionRequest');
  assert.ok(document.components.schemas.AdvertisementRevisionRequest.required.includes('revisedAdvertisementFile'));
  assert.equal(operation.responses['201'].content['application/json'].schema.$ref, '#/components/schemas/AdvertisementRevision');
});
