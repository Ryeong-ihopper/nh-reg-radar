"""Synthetic source-only bridge/structure regressions; no model or answer data."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'rag-pipeline'), str(ROOT / 'rag-pipeline/tools')]
from operational_web_bridge import ExecutionBridge  # noqa: E402 - local package roots are established above
from rag.parsing.prepare_inputs import search_docs  # noqa: E402 - local package roots are established above
from rag.parsing.source_structure import compact_source_structure  # noqa: E402 - local package roots are established above
from rag.retrieval.context import expand_source_context  # noqa: E402 - local package roots are established above
from run_operational_e2e import evidence_documents  # noqa: E402 - local package roots are established above
from run_gemma_exhaustive_dgx import _compact_model_request  # noqa: E402 - local package roots are established above


def document():
    regions = []
    for index, text in enumerate(['기본 금리', '우대 조건', '적용 각주'], 1):
        ref = f'p1/r{index}/L00'
        regions.append(dict(evidence_id=f'D#p1:r{index}', region_id=f'r{index}', final_text=text,
            line_refs=[ref], lines=[dict(line_ref=ref, text=text, bbox=None, labels=[], style=None,
                text_source='ocr', confidence=1.)], bbox=None, text_source='ocr',
            labels=[], assignment_status='unassigned', table=None))
    return dict(contract=dict(version='nh-ad-review-integrated-input-v1', sources=dict(
        p1_contract='nh-ad-review-evidence-v6', p3_contract='nh-ad-review-region-input-v1',
        p1_sha256='a'*64, p3_sha256='b'*64)),
        document=dict(ad_id='D', source_file='synthetic.pdf', routing_metadata={}),
        pages=[dict(page_no=1, regions=regions, unassigned_lines=[])],
        quality=dict(line_count=3, region_count=3, empty_region_count=0, line_partition_exact=True))


def relation(a, b, **extra):
    return dict(type='footnote_for', status='observed', from_line_ids=[f'p1/r{a}/L00'],
                to_line_ids=[f'p1/r{b}/L00'], **extra)


class SourceStructureTests(unittest.TestCase):
    def merge(self, *documents):
        return ExecutionBridge.merge_asset_documents(None,
            SimpleNamespace(advertisement_id='AD', advertisement_name='synthetic'),
            [(SimpleNamespace(file_id=f'F{i}', original_file_name=f'{i}.pdf'), doc)
             for i, doc in enumerate(documents)])

    def test_root_page_relations_survive_and_expand(self):
        doc = document()
        doc['relations'] = [relation(1, 2)]
        doc['pages'][0]['relations'] = [relation(2, 3)]
        original = copy.deepcopy(doc)
        merged = self.merge(doc)
        rows = search_docs(merged)[1]
        selected, audit = expand_source_context([rows[0]['doc_id']], rows)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(audit['relation_added_ids']), 2)
        self.assertEqual(doc, original)

    def test_identical_parser_ids_in_two_files_do_not_cross_link(self):
        doc = document()
        doc['relations'] = [relation(1, 2)]
        merged = self.merge(doc, doc)
        rows = search_docs(merged)[1]
        selected, _ = expand_source_context([rows[0]['doc_id']], rows)
        self.assertEqual(len(selected), 2)
        self.assertTrue(all('#asset:F0:' in value for value in selected))
        self.assertEqual(merged['pages'][1]['source_page_no'], 1)
        self.assertEqual(merged['pages'][1]['page_no'], 2)

    def test_dangling_relation_is_audited_not_invented(self):
        doc = document()
        doc['relations'] = [relation(1, 99)]
        rows = search_docs(self.merge(doc))[1]
        selected, audit = expand_source_context([rows[0]['doc_id']], rows)
        self.assertEqual(len(selected), 1)
        self.assertEqual(audit['deferred_groups'][0]['reason'], 'relation_target_missing_or_outside_scope')

    def test_explicit_observed_cell_footnote_recovers_without_root_relation(self):
        for status in ('observed', 'inferred', 'unknown'):
            with self.subTest(status=status):
                doc = document()
                doc['pages'][0]['regions'][0]['table'] = {'status': status, 'cells': [
                    dict(cell_id='c1', row=0, col=0, line_ids=['p1/r1/L00'], footnote_line_ids=['p1/r3/L00'])]}
                rows = search_docs(self.merge(doc))[1]
                selected, audit = expand_source_context([rows[0]['doc_id']], rows)
                self.assertEqual(len(selected), 2 if status == 'observed' else 1)
                if status != 'observed':
                    self.assertEqual(audit['deferred_groups'][0]['reason'], 'unverified_source_relation')

    def test_table_ids_and_exact_lines_survive_to_model(self):
        doc = document()
        doc['pages'][0]['regions'][0]['table'] = {'cells': [dict(cell_id='c1', row=0, col=0,
            row_span=1, col_span=2, text='uncited OCR alternative', line_ids=['p1/r1/L00'],
            footnote_line_ids=['p1/r3/L00'])]}
        doc['relations'] = [relation(1, 3)]
        rows = search_docs(self.merge(doc))[1]
        docs = evidence_documents(rows)
        request = dict(requested_item_ids=[], messages=[{'content': ''}, {'content': json.dumps(
            dict(documents=docs, rules=[], evidence_scope={}))}])
        messages, aliases = _compact_model_request(request)
        wire = json.loads(messages[1]['content'])
        source = wire['documents'][0]
        self.assertEqual(source['table']['cells'][0]['col_span'], 2)
        self.assertEqual(source['table']['cells'][0]['line_ids'], source['line_refs'])
        self.assertEqual(source['source_relations'][0]['to_line_ids'], wire['documents'][2]['line_refs'])
        self.assertEqual(source['asset_ref'], wire['documents'][2]['asset_ref'])
        self.assertNotIn('uncited OCR alternative', messages[1]['content'])

    def test_unanchored_table_is_preserved_for_audit_not_citable(self):
        table = {'cells': [{'text': 'unverified', 'row': 0, 'col': 0}]}
        result = compact_source_structure({'table': table}, {})
        self.assertNotIn('table', result)
        self.assertEqual(result['structure_unavailable_count'], 1)

    def test_exported_schemas_declare_structure_and_asset_type(self):
        doc = document()
        doc['relations'] = [relation(1, 2)]
        merged = self.merge(doc)
        schema = json.loads((ROOT / 'rag-pipeline/schemas/nh-ad-review-integrated-input-v1.schema.json').read_text(encoding='utf-8'))
        self.assertFalse(set(merged) - set(schema['properties']))
        for page in merged['pages']:
            self.assertFalse(set(page) - set(schema['$defs']['page']['properties']))
        rows = search_docs(merged)[1]
        search_schema = json.loads((ROOT / 'rag-pipeline/schemas/ad-evidence-search-v1.schema.json').read_text(encoding='utf-8'))
        for row in rows:
            self.assertFalse(set(row) - set(search_schema['properties']))
        self.assertEqual(search_schema['properties']['asset_id']['type'], ['string', 'null'])

    def test_unverified_or_outside_window_relation_is_not_projected(self):
        for change in [{'status': 'inferred'}, {'to_line_ids': ['missing']}]:
            source = relation(1, 2)
            source.update(change)
            result = compact_source_structure({'source_relations': [source]},
                {'p1/r1/L00': 'L1', 'p1/r2/L00': 'L2'})
            self.assertNotIn('source_relations', result)
            self.assertEqual(result['structure_unavailable_count'], 1)


if __name__ == '__main__':
    unittest.main()
