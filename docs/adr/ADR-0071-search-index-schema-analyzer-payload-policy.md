# ADR-0071: 검색 인덱스 스키마, Analyzer/Synonym/Highlight 및 Payload 표준화 정책

## 상태

Accepted

## 배경

ADR-0009는 Qdrant를 벡터 DB로 채택했고, ADR-0010은 OpenSearch를 키워드 검색 엔진으로 채택했다. ADR-0043은 RAG 근거 선정과 표시 기준을 정했고, ADR-0050은 기준자료 공통 메타데이터를 정의했다. ADR-0070은 Qdrant/OpenSearch 인덱스 동기화와 idempotent upsert/delete 기준을 정했다.

그러나 실제 검색 품질과 구현 계약에 필요한 Qdrant payload 필드, OpenSearch document schema, 한국어 analyzer, synonym 사전, highlight 반환 기준은 아직 명확하지 않다. 이 기준이 없으면 동일한 chunk라도 검색 adapter, RAG reranker, 근거 표시 화면, 재색인 Job이 서로 다른 필드를 사용하게 되어 검색 품질과 장애 분석이 흔들릴 수 있다.

따라서 PoC 단계에서 필요한 검색 인덱스 스키마와 버전 관리 기준을 표준화한다.

## 결정

검색 인덱스는 **공통 payload/document 필드 표준화 + OpenSearch 한국어 analyzer/synonym/highlight 적용** 방식으로 구성한다.

| 항목 | 결정 |
| --- | --- |
| Qdrant payload | filter, rerank, 근거 추적에 필요한 공통 metadata를 표준 포함 |
| OpenSearch document | 본문 검색, 정확 검색, metadata filter, highlight를 위한 필드 표준화 |
| Analyzer | 한국어 텍스트 검색에 맞는 analyzer를 사용하되 PoC 초기에는 과도한 튜닝 금지 |
| Synonym | 금융/광고/법령 용어 사전을 Git 관리 설정 파일로 versioning |
| Highlight | OpenSearch 결과에서 `chunk_text`, `title` 중심으로 반환 |
| Version | `search_schema_version`, `opensearch_analyzer_version`, `synonym_version`을 기록 |
| 재색인 | schema/analyzer/synonym 변경 시 ADR-0069 재색인 API로 재색인 |

## 표준 필드

Qdrant payload와 OpenSearch document는 동일한 논리 필드명을 기준으로 매핑한다. API는 camelCase를 사용하고, DB와 검색 인덱스 내부 필드는 snake_case를 사용한다.

| 필드 | Qdrant | OpenSearch | 용도 |
| --- | --- | --- | --- |
| `evidence_chunk_id` | 포함 | keyword | 근거 chunk 식별 |
| `evidence_id` | 포함 | keyword | 근거 원문 연결 |
| `standard_id` | 포함 | keyword | 기준자료 식별 |
| `standard_version_id` | 포함 | keyword | 기준 버전 재현성 |
| `evidence_type` | 포함 | keyword | 법령/내규/매뉴얼/사례 구분 |
| `title` | 포함 | text + keyword | 기준자료 제목 검색과 표시 |
| `chunk_text` | 선택 | text | 본문 키워드 검색과 highlight |
| `article_no` | 포함 | text + keyword | 조문번호/항목번호 검색 |
| `section_path` | 포함 | text + keyword | 구조 인식 경로 |
| `product_group` | 포함 | keyword | 상품군 filter |
| `advertisement_type` | 포함 | keyword | 광고유형 filter |
| `rule_type` | 포함 | keyword | 필수/금지/권고 구분 |
| `importance` | 포함 | keyword | 중요도/rerank |
| `effective_date` | 포함 | date | 기준일 filter |
| `expired_date` | 포함 | date | 기준일 filter |
| `index_status` | 포함 | keyword | `ACTIVE` 검색 제한 |
| `embedding_model` | 포함 | keyword | 벡터 재현성 |
| `chunking_policy_version` | 포함 | keyword | chunk 재현성 |
| `search_schema_version` | 포함 | keyword | 검색 schema 변경 추적 |
| `opensearch_analyzer_version` | 선택 | keyword | analyzer 변경 추적 |
| `synonym_version` | 선택 | keyword | 동의어 사전 변경 추적 |

Qdrant payload에는 vector search filter와 rerank에 필요한 metadata를 우선 포함한다. 긴 본문 `chunk_text`는 운영 저장량과 중복을 고려해 필수 payload로 두지 않지만, 장애 분석 편의를 위해 짧은 preview 또는 checksum을 추가하는 것은 허용한다.

OpenSearch document에는 본문 검색과 highlight를 위해 `chunk_text`를 포함한다. 정확 매칭이 필요한 `article_no`, `title`, `section_path`는 text field와 keyword subfield를 함께 둔다.

## OpenSearch Analyzer와 Synonym

OpenSearch는 한국어 문서 검색을 위해 한국어 analyzer를 사용한다. PoC 초기에는 다음 원칙을 따른다.

| 항목 | 기준 |
| --- | --- |
| 기본 analyzer | 한국어 형태소 또는 한국어 텍스트 처리에 적합한 analyzer 사용 |
| keyword subfield | 조문번호, 코드, enum, ID, 날짜 filter에는 keyword field 사용 |
| synonym 사전 | `config/search/synonyms/*.txt` 또는 동등한 Git 관리 파일로 관리 |
| synonym version | 검색 인덱스 문서와 재색인 Job에 `synonym_version` 기록 |
| 과도한 튜닝 | 평가셋 확보 전 ranking boost, 복잡한 multi-field 튜닝은 최소화 |

동의어는 금융상품, 광고 표현, 법령/감독규정 용어처럼 검색 누락 비용이 큰 표현부터 관리한다. 예를 들어 `금리, 이자율`, `수수료, 비용`, `최고, 최대`, `확정, 보장` 같은 용어군은 synonym 후보가 될 수 있다.

## Highlight 기준

OpenSearch 검색 결과는 `chunk_text`와 `title`에 대한 highlight를 반환할 수 있어야 한다.

| 대상 | 기준 |
| --- | --- |
| `chunk_text` | 근거 문구 강조 표시의 기본 highlight field |
| `title` | 기준자료명 검색 결과 표시용 highlight field |
| `article_no` | 정확 조문번호 검색은 highlight보다 field match 정보로 표시 |
| 미반환 상황 | analyzer 또는 field 설정상 highlight가 없으면 원문 snippet과 matchSource로 보완 |

화면/API는 highlight가 없다는 이유로 근거 자체를 버리지 않는다. 근거 선정은 ADR-0043의 rank, metadata match, rule match, source priority, structure confidence 기준을 따른다.

## Version 관리

검색 인덱스 관련 변경은 다음 version 값을 기록한다.

| Version | 의미 | 변경 시 처리 |
| --- | --- | --- |
| `search_schema_version` | Qdrant payload/OpenSearch document field 계약 | `INDEX_ONLY` 또는 필요 시 `CHUNK_AND_INDEX` |
| `opensearch_analyzer_version` | analyzer/filter/tokenizer 설정 | `KEYWORD_ONLY` 또는 `INDEX_ONLY` |
| `synonym_version` | synonym 사전 버전 | `KEYWORD_ONLY` 또는 `INDEX_ONLY` |
| `embedding_model` | vector embedding 모델 | `VECTOR_ONLY` 또는 `INDEX_ONLY` |
| `chunking_policy_version` | chunk 생성 정책 | `CHUNK_AND_INDEX` |

Version 값은 재색인 요청, 재색인 Job, chunk metadata, 검색 인덱스 payload/document에 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 최소 필드와 기본 analyzer만 사용 | 구현은 단순하지만 한국어/법령/금융 용어 검색 품질이 낮아 기각 |
| B. 공통 payload/document 필드 표준화 + 한국어 analyzer/synonym/highlight 적용 | 검색 품질과 구현 부담의 균형이 좋아 채택 |
| C. 초기부터 도메인 synonym, multi-field, ranking boost를 상세 튜닝 | 검색 품질은 좋지만 PoC 초기 구현 부담이 커 기각 |
| D. analyzer/synonym/highlight를 검색 품질 이슈 발생 후 결정 | 빠르지만 RAG 품질 검증 기준이 흔들려 기각 |
| E. 검색엔진 튜닝을 최소화하고 application rerank에 위임 | OpenSearch 정확 검색/하이라이트 장점을 충분히 활용하지 못해 기각 |

## 결정 근거

- 금융광고 심의는 의미 검색뿐 아니라 정확한 조문번호, 금지어, 필수 문구 검색이 중요하다.
- Qdrant와 OpenSearch가 같은 metadata 기준을 공유해야 Hybrid Search 병합과 rerank가 안정적이다.
- synonym과 analyzer 변경은 검색 결과를 바꾸므로 version과 재색인 이력이 필요하다.
- highlight는 화면의 근거 설명성과 검수 효율을 높인다.
- PoC 초기에는 검색 품질을 검증할 수 있는 표준 계약을 먼저 만들고, 세밀한 ranking 튜닝은 평가셋 축적 후 조정하는 편이 안전하다.

## 영향

- `evidence_chunks`와 `standard_reindex_jobs`에 검색 schema/analyzer/synonym version 필드를 추가한다.
- Qdrant payload와 OpenSearch document 예시에 표준 필드를 반영한다.
- 재색인 API는 `searchSchemaVersion`, `opensearchAnalyzerVersion`, `synonymVersion`을 받을 수 있어야 한다.
- Chunk 조회 API는 검색 schema/analyzer/synonym version과 highlight 설정 추적에 필요한 값을 반환한다.
- 테스트케이스에 표준 필드 색인, synonym 검색, highlight 반환, version 변경 재색인을 추가한다.

## 후속 조치

- `config/search/synonyms/` 경로 또는 동등한 설정 경로를 만들고 synonym 사전을 Git으로 관리한다.
- OpenSearch index template/mapping 생성 스크립트에 analyzer, keyword subfield, highlight 대상 field를 반영한다.
- Qdrant/OpenSearch adapter는 동일한 metadata builder를 사용해 payload/document drift를 줄인다.
- 검색 품질 평가셋이 확보되면 synonym, analyzer, ranking boost를 별도 ADR 또는 설정 변경으로 조정한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0009-qdrant-vector-database.md`
- `docs/adr/ADR-0010-opensearch-keyword-search.md`
- `docs/adr/ADR-0043-rag-evidence-selection-policy.md`
- `docs/adr/ADR-0050-reference-metadata-policy.md`
- `docs/adr/ADR-0069-standard-reindex-and-chunk-query-api-policy.md`
- `docs/adr/ADR-0070-search-index-idempotent-sync-policy.md`
