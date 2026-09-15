import { readFile } from 'node:fs/promises';
import test from 'node:test';
import assert from 'node:assert/strict';
import { validateValues } from '../../scripts/validate-rag-artifacts.mjs';

const schema = JSON.parse(await readFile(new URL('../../rag-pipeline/schemas/ad-evidence-search-v1.schema.json', import.meta.url), 'utf8'));
function unassignedDocument() {
  return { schema_version: 'ad-evidence-search-v1', ad_id: 'AD', product_id: 'P',
    source_file: 'sample.png', routing: {}, routing_metadata: {}, page_no: 1,
    region_id: null, labels: [], assignment_status: 'unassigned', doc_id: 'E',
    view_type: 'fine_text', text_canonical: 'source', text_search: 'source',
    line_refs: ['L'], line_texts: { L: 'source' }, line_bboxes: { L: [0, 0, 10, 10] },
    span_status: 'parser_line_exact', text_selection: { needs_review: true, confidence: 0.4 } };
}
test('unassigned evidence and text selection are declared in the schema', () => {
  assert.deepEqual(validateValues(schema, [unassignedDocument()]), []);
});
test('invalid bbox and non-boolean review status are rejected', () => {
  for (const change of [{ line_bboxes: { L: [0, 0] } }, { text_selection: { needs_review: 'false' } }, { invented_field: 1 }]) {
    assert.equal(validateValues(schema, [{ ...unassignedDocument(), ...change }]).length, 1);
  }
});

const proposal = JSON.parse(await readFile(new URL('../../rag-pipeline/schemas/proposals/parser-handoff-vnext.schema.json', import.meta.url), 'utf8'));
const requestDoc = await readFile(new URL('../../docs/parser-schema-change-request-current.md', import.meta.url), 'utf8');
const example = JSON.parse(requestDoc.match(/```json\s*([\s\S]*?)```/)[1]);
test('parser request document includes a schema-valid proposed example', () => {
  assert.deepEqual(validateValues(proposal, [example]), []);
});
test('parser proposal rejects false exact mapping and non-observation output', () => {
  const noSource = structuredClone(example);
  noSource.pages[0].selected_segments[0].source_line_ids = [];
  const legalVerdict = { ...example, verdict: 'COMPLIANT' };
  const failedButComplete = structuredClone(example);
  failedButComplete.pages[0].parse_status = 'failed';
  for (const value of [noSource, legalVerdict, failedButComplete]) assert.equal(validateValues(proposal, [value]).length, 1);
});
