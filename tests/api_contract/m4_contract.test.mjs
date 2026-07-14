import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('governance/goal-manifests/G005-m4-parser-ocr-job.json', root).pathname;

test('G005-m4 manifest freezes the Review Job Parser boundary', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const operations = collectOperationIds(document);

  assert.equal(manifest.goal_id, 'G005-m4-parser-ocr-job');
  assert.equal(manifest.openapi.version, '0.4.0');
  assert.equal(document.info.version, '0.8.0');
  for (const operationId of manifest.openapi.operation_ids) {
    assert.ok(operations.has(operationId), `missing operationId ${operationId}`);
  }
  for (const schema of manifest.openapi.schemas) {
    assert.ok(Object.hasOwn(document.components.schemas, schema), `missing schema ${schema}`);
  }
});

test('TC-REV-001..014: Review Job contract locks idempotent retry progress and rerun fields', async () => {
  const document = await loadOpenApi(contractPath);
  for (const [path, method, operationId] of [
    ['/advertisements/{advertisementId}/reviews', 'post', 'requestAdvertisementReview'],
    ['/advertisements/{advertisementId}/reviews', 'get', 'listAdvertisementReviews'],
    ['/reviews/{reviewId}/status', 'get', 'getReviewStatus'],
    ['/reviews/{reviewId}/rerun', 'post', 'rerunReview'],
  ]) {
    const operation = document.paths[path]?.[method];
    assert.equal(operation?.operationId, operationId);
    assert.ok(operation.responses['401']);
    assert.ok(operation.responses['403']);
  }
  const progress = document.components.schemas.ReviewProgress;
  for (const field of [
    'jobStatus', 'currentStep', 'progressRate', 'retryCount', 'maxRetries',
    'nextRetryAt', 'isRetryable', 'failedReasonCode', 'failedReason', 'timeoutAt', 'steps',
  ]) {
    assert.ok(Object.hasOwn(progress.properties, field), `ReviewProgress lacks ${field}`);
  }
  assert.deepEqual(document.components.schemas.ReviewJobStatus.enum, [
    'PENDING', 'RUNNING', 'RETRY_PENDING', 'STALE', 'COMPLETED',
    'FAILED', 'FAILED_FINAL', 'CANCELED',
  ]);
  assert.equal(progress.properties.maxRetries.const, 3);
  assert.ok(document.paths['/advertisements/{advertisementId}/reviews'].post.responses['409']);
  assert.ok(document.paths['/reviews/{reviewId}/rerun'].post.responses['409']);
});

test('TC-OCR-001..024: NormalizedDocument and minimal queue payload are provider-independent', async () => {
  const document = await loadOpenApi(contractPath);
  const normalized = document.components.schemas.NormalizedDocument;
  for (const field of [
    'documentId', 'sourceFileId', 'reviewId', 'sourceFileType', 'parserName',
    'parserVersion', 'parserRuleVersion', 'irVersion', 'pages', 'textBlocks',
    'layoutBlocks', 'tables', 'warnings', 'confidence', 'rawArtifactRef', 'createdAt',
  ]) {
    assert.ok(normalized.required.includes(field), `NormalizedDocument must require ${field}`);
  }
  assert.equal(normalized.properties.irVersion.pattern, '^normalized-document-v1$');
  const queue = document.components.schemas.ReviewQueueMessageV1;
  assert.equal(queue.additionalProperties, false);
  assert.equal(queue.properties.messageVersion.const, 'review-job-v1');
  for (const forbidden of ['body', 'raw', 'text', 'objectKey', 'presignedUrl']) {
    assert.ok(!Object.hasOwn(queue.properties, forbidden), `queue leaks ${forbidden}`);
  }
});

test('M4 synthetic parser fixtures are versioned customer-free and hash locked', async () => {
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  for (const fixture of manifest.fixtures) {
    const bytes = await readFile(new URL(fixture.path, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), fixture.sha256);
    assert.equal(fixture.kind, 'synthetic');
    assert.equal(fixture.contains_customer_data, false);
  }
});
