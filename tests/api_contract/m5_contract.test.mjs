import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('governance/goal-manifests/G006-m5-review-results.json', root).pathname;

test('G006-m5 manifest freezes Result Evidence Annotation entry gate', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const operations = collectOperationIds(document);

  assert.equal(manifest.goal_id, 'G006-m5-review-results');
  assert.equal(document.info.version, '0.7.0');
  // M5 is a preserved subset of the additive v0.6 source contract; its
  // historical source digest is retained in the manifest rather than treated
  // as the digest of every future additive release.
  // The generated client expands additively for M6; retain the M5 manifest
  // digest as historical release metadata while asserting the client exists.
  await readFile(new URL(manifest.generated_client.path, root));
  for (const operationId of manifest.openapi.operation_ids) {
    assert.ok(operations.has(operationId), `missing operationId ${operationId}`);
  }
  for (const schema of manifest.openapi.schemas) {
    assert.ok(Object.hasOwn(document.components.schemas, schema), `missing schema ${schema}`);
  }
});

test('TC-RES-001..005/TC-ITEM-001..007: review results require risk rationale and explicit evidence state', async () => {
  const document = await loadOpenApi(contractPath);
  for (const [path, operationId, schema] of [
    ['/reviews/{reviewId}/summary', 'getReviewSummary', 'ReviewSummary'],
    ['/reviews/{reviewId}/items', 'listReviewItems', 'ReviewItemPage'],
    ['/reviews/{reviewId}/items/{reviewItemId}', 'getReviewItem', 'ReviewItemDetail'],
  ]) {
    const operation = document.paths[path]?.get;
    assert.equal(operation?.operationId, operationId);
    assert.equal(operation.responses['200'].content['application/json'].schema.$ref, `#/components/schemas/${schema}`);
    for (const status of ['400', '401', '403', '404']) assert.ok(operation.responses[status]);
  }

  const summary = document.components.schemas.ReviewItemSummary;
  for (const field of [
    'riskLevel', 'riskPolicyVersion', 'riskReasonCodes', 'evidenceStatus',
    'evidenceFailureCode', 'sourceEngine', 'sourceVersion',
  ]) {
    assert.ok(summary.required.includes(field), `ReviewItemSummary must require ${field}`);
  }
  assert.deepEqual(document.components.schemas.RiskLevel.enum, ['HIGH', 'MEDIUM', 'LOW', 'CHECK_REQUIRED']);
  assert.deepEqual(document.components.schemas.EvidenceStatus.enum, [
    'CONNECTED', 'NOT_REQUIRED', 'INSUFFICIENT', 'SEARCH_UNAVAILABLE',
  ]);
  assert.deepEqual(document.components.schemas.RiskScoreDetail.required, [
    'rule', 'rag', 'llm', 'parser', 'final',
  ]);
});

test('TC-RAG-001..005/TC-EVD-007..011/014: staged fixtures preserve Rule results and distinguish RAG failures', async () => {
  const rule = JSON.parse(await readFile(new URL('tests/fixtures/m5/rule-results-v1.json', root), 'utf8'));
  const search = JSON.parse(await readFile(new URL('tests/fixtures/m5/search-evidence-v1.json', root), 'utf8'));
  const structured = JSON.parse(await readFile(new URL('tests/fixtures/m5/structured-output-v1.json', root), 'utf8'));

  assert.equal(rule.items[0].sourceEngine, 'RULE');
  assert.equal(rule.items[0].scoreDetail.llm.status, 'NOT_RUN');
  assert.equal(rule.items[0].evidenceStatus, 'NOT_REQUIRED');

  const insufficient = search.cases.find((item) => item.caseId === 'INSUFFICIENT');
  const unavailable = search.cases.find((item) => item.caseId === 'SEARCH_UNAVAILABLE');
  const failed = search.cases.find((item) => item.caseId === 'SEARCH_FAILED');
  assert.equal(insufficient.status, 'INSUFFICIENT');
  assert.equal(insufficient.failureCode, null);
  assert.equal(unavailable.failureCode, 'RAG_SEARCH_UNAVAILABLE');
  assert.equal(failed.failureCode, 'RAG_SEARCH_FAILED');
  assert.deepEqual(unavailable.preservedRuleItemIds, [rule.items[0].reviewItemId]);

  assert.equal(structured.provider, null);
  assert.equal(structured.model, null);
  assert.equal(structured.networkAllowed, false);
  assert.ok(structured.cases.some((item) => item.status === 'INVALID_SCHEMA'));
});

test('TC-ANN-001..011: Annotation contract covers box highlight and list fallback', async () => {
  const document = await loadOpenApi(contractPath);
  const operation = document.paths['/reviews/{reviewId}/annotations']?.get;
  assert.equal(operation.operationId, 'listReviewAnnotations');
  assert.deepEqual(document.components.schemas.AnnotationDisplayMode.enum, [
    'BOX', 'TEXT_HIGHLIGHT', 'LIST_ONLY', 'UNAVAILABLE',
  ]);

  const annotation = document.components.schemas.Annotation;
  for (const field of [
    'annotationDisplayMode', 'annotationStatus', 'locationConfidence',
    'confidencePolicyVersion', 'coordinate', 'textBlockId',
    'normalizedStartOffset', 'normalizedEndOffset',
  ]) {
    assert.ok(annotation.required.includes(field), `Annotation must require ${field}`);
  }

  const fixture = JSON.parse(await readFile(new URL('tests/fixtures/m5/annotation-display-v1.json', root), 'utf8'));
  assert.deepEqual(fixture.annotations.map((item) => item.annotationDisplayMode), [
    'BOX', 'TEXT_HIGHLIGHT', 'LIST_ONLY',
  ]);
  assert.deepEqual(fixture.annotations.map((item) => item.locationConfidence), [0.8, 0.79, 0.49]);
  assert.equal(fixture.annotations[0].coordinate.normalizedWidth, 0.4);
  assert.equal(fixture.annotations[1].coordinate, null);
  assert.equal(fixture.annotations[2].coordinate, null);
});

test('M5 synthetic fixtures are versioned provider-independent and hash locked', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  for (const fixture of manifest.fixtures) {
    const bytes = await readFile(new URL(fixture.path, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), fixture.sha256);
    assert.equal(fixture.kind, 'synthetic');
    assert.equal(fixture.contains_customer_data, false);
  }
});
