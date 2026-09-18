import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from rag.retrieval.evidence_bundle import supplement_evidence, source_facets  # noqa: E402 - local package roots are established above
from rag.judgment.condition_contracts import compile_condition_contract  # noqa: E402 - local package roots are established above
from rag.parsing.source_structure import table_relations, compact_source_structure  # noqa: E402 - local package roots are established above
from tools import run_operational_e2e as operational  # noqa: E402 - local package roots are established above


def row(key, text, product='P'):
    return dict(doc_id=key, text_canonical=text, ad_id='A', product_id=product)


class EvidenceBundleTests(unittest.TestCase):
    def test_template_field_hint_recovers_readable_line_without_excluding_unlabeled_hits(self):
        rows = [row('readable', '가상저축'), row('uncertain', '흐린 이름'),
                row('dense', '상품 설명 안내'), row('lexical', '상품명 안내')]
        for doc in rows[:2]:
            doc['labels'] = [{'label': '상품명'}]
        rows[1]['text_selection'] = {'needs_review': True}
        vectors = {key: np.array([score, 0.]) for key, score in
                   [('readable', .1), ('uncertain', .8), ('dense', 1.), ('lexical', .4)]}
        args = dict(rule_vector_by_id={'R': np.array([1., 0.])}, ad_fine_rows=rows,
                    fine_vector_by_id=vectors, trigger_ids=[], rule_text='상품명', rule_label='상품명')
        frozen = copy.deepcopy(rows)
        self.assertEqual(operational.top_rule_evidence('R', k=1, **args), ['readable'])
        selected = operational.top_rule_evidence('R', k=3, **args)
        self.assertEqual(set(selected), {'readable', 'dense', 'lexical'})
        self.assertEqual(rows, frozen)
        self.assertEqual(operational.top_rule_evidence('R', k=0, **args), [])
        self.assertEqual(operational.top_rule_evidence('R', k=1, **{**args, 'rule_label': '다른구분'}), ['lexical'])

    def test_table_header_and_note_links_require_observation(self):
        table = {'status': 'observed', 'cells': [
            {'cell_id': 'h', 'line_ids': ['header']},
            {'cell_id': 'c', 'line_ids': ['body'], 'header_cell_ids': ['h'], 'footnote_line_ids': ['note']}]}
        links = table_relations(table)
        self.assertEqual({link['type'] for link in links}, {'header_for', 'footnote_for'})
        aliases = {'header':'L1','body':'L2','note':'L3'}
        wire = compact_source_structure({'table': table, 'source_relations':links}, aliases)
        self.assertEqual(wire['table']['cells'][1]['header_cell_ids'], ['h'])
        self.assertEqual(wire['table']['cells'][1]['footnote_line_ids'], ['L3'])
        table['status'] = 'inferred'
        wire = compact_source_structure({'table':table,'source_relations':table_relations(table)}, aliases)
        self.assertNotIn('source_relations', wire)
        self.assertNotIn('footnote_line_ids', wire['table']['cells'][1])

    def test_two_syllable_term_rescues_dense_miss(self):
        selected = operational.top_rule_evidence('R', rule_vector_by_id={'R': np.array([1., 0.])},
            ad_fine_rows=[row('correct', '금리 안내'), row('other', '상담 안내')],
            fine_vector_by_id={'correct': np.array([0., 1.]), 'other': np.array([1., 0.])},
            trigger_ids=[], k=1, rule_text='금리')
        self.assertEqual(selected, ['correct'])

    def test_facet_recovers_condition_without_losing_trigger(self):
        rows = [row('seed', '금리'), row('condition', '납입 기간'), row('unrelated', '연락처')]
        selected, audit = supplement_evidence(['seed'], rows,
            {'criterion': '금리\n납입 기간'}, char_budget=5)
        self.assertEqual(selected, ['seed', 'condition'])
        self.assertEqual(audit['added_chars'], 5)
        self.assertFalse(audit['semantic_dependencies_complete'])

    def test_budget_boundary_preserves_whole_chunk(self):
        for budget in [0, 4]:
            selected, audit = supplement_evidence(['seed'], [row('seed', '금리'), row('c', '납입 기간')],
                {'criterion': '납입 기간'}, char_budget=budget)
            self.assertEqual(selected, ['seed'])
            self.assertEqual(audit['facets'][0]['status'], 'BUDGET_DEFERRED')

    def test_no_match_does_not_mean_absent_and_other_product_is_excluded(self):
        selected, audit = supplement_evidence(['seed'], [row('seed', '금리'), row('c', '납입 기간', 'OTHER')],
            {'criterion': '납입 기간'}, char_budget=100)
        self.assertEqual(selected, ['seed'])
        self.assertEqual(audit['facets'][0]['status'], 'NO_LEXICAL_MATCH')

    def test_search_sentences_do_not_create_new_obligations(self):
        rule = {'question': '조건 안내', 'criterion': '납입 기간을 표시한다. 단, 해당 없으면 면제한다.'}
        rule['condition_contract'] = compile_condition_contract(rule)
        original = copy.deepcopy(rule)
        facets = source_facets(rule)
        self.assertGreater(len(facets), 1)
        self.assertEqual(len(rule['condition_contract']['obligation_checks']), 1)
        self.assertEqual(rule, original)

    def test_rerank_uses_second_trigger_deduplicates_and_preserves_candidates(self):
        candidates = [{'item_id': 'R', 'rank': 1, 'trigger_evidence': [
            {'trigger': {'doc_id': 'a'}}, {'trigger': {'doc_id': 'b'}}, {'trigger': {'doc_id': 'b'}}]},
            {'item_id': 'S', 'rank': 2, 'trigger_evidence': [{'trigger': {'doc_id': 'a'}}]}]
        rules = {key: {'item_id': key, 'category': 'PROHIBIT', 'title': key} for key in ['R', 'S']}
        with patch.object(operational, 'dgx_rerank', return_value=np.array([.1, .9, .5])) as call:
            result = operational.rerank_prohibition_candidates(candidates, rules=rules,
                fine_documents={'a': row('a', '첫 근거'), 'b': row('b', '둘째 근거')}, rrf_k=60, candidate_pool=80)
        self.assertEqual(len(call.call_args.args[0]), 3)
        self.assertEqual(result[0]['reranker_score'], .9)
        self.assertEqual(result[0]['reranker_evidence_ids'], ['a', 'b'])
        self.assertEqual(len(result), 2)

    def test_rerank_rejects_incomplete_provider_response(self):
        with patch.object(operational, 'dgx_rerank', return_value=np.array([])):
            with self.assertRaises(ValueError):
                operational.rerank_prohibition_candidates(
                    [{'item_id': 'R', 'trigger_evidence': [{'trigger': {'doc_id': 'a'}}]}],
                    rules={'R': {'item_id': 'R', 'category': 'PROHIBIT'}},
                    fine_documents={'a': row('a', '금리')}, rrf_k=60, candidate_pool=80)


if __name__ == '__main__':
    unittest.main()
