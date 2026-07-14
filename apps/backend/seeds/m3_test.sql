BEGIN;

INSERT INTO rag.standards (
  standard_id, title, evidence_type, product_group, advertisement_type,
  rule_type, importance, effective_date, expired_date, metadata_json,
  current_version, is_active, created_by
) VALUES (
  'STD-SYNTH-0001', 'Synthetic advertising standard', 'INTERNAL_STANDARD',
  'SAVINGS', 'MOBILE_BANNER', 'REQUIRED', 'HIGH', DATE '2026-01-01', NULL,
  '{"owningDepartment":"Synthetic Compliance","documentName":"Synthetic standard","sectionPath":"1","version":"1.0","applicableProductGroups":["SAVINGS"]}'::jsonb,
  '1.0', true, 'USR-SYNTH-COMPLIANCE'
)
ON CONFLICT (standard_id) DO UPDATE SET
  title = EXCLUDED.title,
  metadata_json = EXCLUDED.metadata_json,
  current_version = EXCLUDED.current_version,
  is_active = EXCLUDED.is_active,
  updated_at = now(),
  updated_by = EXCLUDED.created_by;

INSERT INTO rag.standard_versions (
  standard_version_id, standard_id, version, title, content, change_reason,
  effective_date, expired_date, metadata_json, created_by
) VALUES (
  'STDVER-SYNTH-0001', 'STD-SYNTH-0001', '1.0',
  'Synthetic advertising standard',
  'Synthetic current rule text with a required notice.',
  'Synthetic deterministic M3 fixture', DATE '2026-01-01', NULL,
  '{"inputBoundary":"DIRECT_TEXT_ONLY"}'::jsonb,
  'USR-SYNTH-COMPLIANCE'
)
ON CONFLICT (standard_id, version) DO UPDATE SET
  title = EXCLUDED.title,
  content = EXCLUDED.content,
  metadata_json = EXCLUDED.metadata_json;

INSERT INTO rag.evidences (
  evidence_id, standard_id, standard_version_id, evidence_type, title,
  article_no, content, content_summary, product_group, advertisement_type,
  rule_type, importance, effective_date, expired_date, metadata_json, is_active
) VALUES (
  'EVD-SYNTH-0001', 'STD-SYNTH-0001', 'STDVER-SYNTH-0001',
  'INTERNAL_STANDARD', 'Synthetic advertising standard', '1',
  'Synthetic current rule text with a required notice.',
  'Synthetic required notice.', 'SAVINGS', 'MOBILE_BANNER', 'REQUIRED',
  'HIGH', DATE '2026-01-01', NULL, '{"fixtureVersion":1}'::jsonb, true
)
ON CONFLICT (standard_id, standard_version_id) DO UPDATE SET
  content = EXCLUDED.content,
  content_summary = EXCLUDED.content_summary,
  is_active = EXCLUDED.is_active;

INSERT INTO rag.evidence_chunks (
  evidence_chunk_id, evidence_id, standard_id, standard_version_id, chunk_no,
  chunk_text, token_count, section_path, article_no, source_span,
  structure_confidence, parser_rule_version, chunking_policy_version,
  qdrant_collection, qdrant_point_id, qdrant_index_status,
  opensearch_index, opensearch_doc_id, opensearch_index_status,
  embedding_model, search_schema_version, opensearch_analyzer_version,
  synonym_version, metadata
) VALUES (
  'ECH-SYNTH-0001', 'EVD-SYNTH-0001', 'STD-SYNTH-0001',
  'STDVER-SYNTH-0001', 1,
  'Synthetic current rule text with a required notice.', 8, '1', '1',
  '{"start":0,"end":51}'::jsonb, 1.0000, 'direct-text-v1',
  'reference-chunking-v1', 'evidence_chunks',
  'test:STDVER-SYNTH-0001:ECH-SYNTH-0001:fixed-vector-v1:reference-chunking-v1',
  'PENDING', 'evidence_chunks',
  'test:STDVER-SYNTH-0001:ECH-SYNTH-0001:fixed-vector-v1:reference-chunking-v1',
  'PENDING', 'fixed-vector-v1', 'search-schema-v1', 'ko-analyzer-v1',
  'synonyms-v1', '{"fixtureVersion":1,"vector":[0.1,0.2,0.3]}'::jsonb
)
ON CONFLICT (standard_version_id, chunk_no) DO UPDATE SET
  chunk_text = EXCLUDED.chunk_text,
  qdrant_point_id = EXCLUDED.qdrant_point_id,
  opensearch_doc_id = EXCLUDED.opensearch_doc_id,
  metadata = EXCLUDED.metadata;

COMMIT;
