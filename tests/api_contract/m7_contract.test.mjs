import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { collectOperationIds, loadOpenApi } from '../../scripts/openapi_tools.mjs';

const root = new URL('../../', import.meta.url);
const contractPath = new URL('openapi/openapi.yaml', root).pathname;
const manifestPath = new URL('governance/goal-manifests/G008-m7-kpi.json', root).pathname;
const fixturePath = new URL('tests/fixtures/m7/validation-kpi-v1.json', root).pathname;

const validationOperations = new Set([
  'listValidationDatasets',
  'createValidationDataset',
  'createValidationJudgments',
  'createValidationEvaluation',
  'getValidationEvaluation',
]);

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

test('G008 M7 manifest freezes contract, generated client, migration, and synthetic fixture hashes', async () => {
  const document = await loadOpenApi(contractPath);
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  assert.equal(document.info.version, '0.8.0');
  assert.equal(manifest.openapi.version, '0.7.0');
  assert.match(manifest.openapi.source_sha256, /^[a-f0-9]{64}$/);
  assert.match(manifest.generated_client.sha256, /^[a-f0-9]{64}$/);
  assert.equal(createHash('sha256').update(await readFile(new URL(manifest.migration.path, root))).digest('hex'), manifest.migration.sha256);
  assert.equal(manifest.migration.revision, '0007_m7_validation_kpi');
  assert.equal(manifest.migration.down_revision, '0006_m6_support_outputs');
  assert.deepEqual(new Set(manifest.openapi.operation_ids), validationOperations);
  for (const fixture of manifest.fixtures) {
    assert.equal(createHash('sha256').update(await readFile(new URL(fixture.path, root))).digest('hex'), fixture.sha256);
    assert.equal(fixture.kind, 'synthetic');
    assert.equal(fixture.contains_customer_data, false);
  }
});

test('TC-VAL-001..005: exactly five validation operations and versioned dataset contracts are frozen', async () => {
  const document = await loadOpenApi(contractPath);
  const operations = collectOperationIds(document);
  assert.deepEqual(
    new Set([...operations.keys()].filter((operationId) => validationOperations.has(operationId))),
    validationOperations,
  );
  assert.equal(document.paths['/validation/datasets'].get.operationId, 'listValidationDatasets');
  assert.equal(document.paths['/validation/datasets'].post.operationId, 'createValidationDataset');
  assert.equal(document.paths['/validation/datasets/{datasetId}/judgments'].post.operationId, 'createValidationJudgments');
  assert.deepEqual(document.components.schemas.ExcludeReasonCode.enum, [
    'OCR_UNREADABLE',
    'PRODUCT_CONDITION_AMBIGUOUS',
    'REFERENCE_NOT_PROVIDED',
    'SOURCE_FILE_CORRUPTED',
    'LABEL_UNCLEAR',
    'DUPLICATE_SAMPLE',
    'OUT_OF_SCOPE',
  ]);
  assert.ok(document.components.schemas.ValidationDataset.required.includes('datasetVersion'));
  assert.ok(document.components.schemas.ValidationJudgment.required.includes('judgmentVersion'));
});

test('TC-EVAL-001..011: deterministic four-metric, exclusion, partial, error, and zero-denominator rules are locked', async () => {
  const document = await loadOpenApi(contractPath);
  const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));
  assert.equal(document.paths['/validation/evaluations'].post.operationId, 'createValidationEvaluation');
  assert.equal(document.paths['/validation/evaluations/{evaluationId}'].get.operationId, 'getValidationEvaluation');
  assert.deepEqual(document.components.schemas.ValidationMetricCode.enum, [
    'REQUIRED_PHRASE_ACCURACY',
    'MISLEADING_EXPRESSION_ACCURACY',
    'EVIDENCE_PRECISION',
    'HUMAN_AGREEMENT_RATE',
  ]);
  assert.equal(fixture.networkAllowed, false);
  assert.equal(fixture.provider, null);
  assert.deepEqual(fixture.matchScores, [1, 0.5, 0]);
  assert.deepEqual(fixture.targets, {
    REQUIRED_PHRASE_ACCURACY: 80,
    MISLEADING_EXPRESSION_ACCURACY: 75,
    EVIDENCE_PRECISION: 85,
    HUMAN_AGREEMENT_RATE: 75,
  });
  assert.ok(fixture.cases.some((item) => item.aiError === true && item.matchScore === 0 && item.excluded === false));
  assert.ok(fixture.cases.some((item) => item.exclusionCandidate === true && item.exclusionApproved === false && item.excluded === false));
  assert.ok(fixture.expectedMetrics.some((metric) => metric.notApplicable === true && metric.score === null && metric.achieved === false));
});

test('TC-EVAL-012..015: canonical immutable snapshot and selected review provenance are frozen', async () => {
  const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));
  const snapshotHash = `sha256:${createHash('sha256').update(canonicalJson(fixture.canonicalSnapshotInput)).digest('hex')}`;
  assert.equal(snapshotHash, fixture.expectedSnapshotSha256);
  assert.equal(fixture.canonicalSnapshotInput.policy.reviewSelectionPolicy, 'LATEST_COMPLETED');
  assert.equal(fixture.canonicalSnapshotInput.aiResults[0].reviewId, 'REV-M7-0002');
  assert.equal(fixture.immutability.existingEvaluationRemainsUnchanged, true);
  assert.equal(fixture.immutability.changedJudgmentCreatesNewEvaluation, true);
  assert.notEqual(fixture.immutability.originalEvaluationId, fixture.immutability.nextEvaluationId);
  assert.notEqual(fixture.immutability.originalSnapshotSha256, fixture.immutability.nextSnapshotSha256);
});
