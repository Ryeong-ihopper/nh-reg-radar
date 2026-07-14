# ADR-0009: 벡터 DB로 Qdrant 채택

## 상태

Accepted

## 배경

금융상품 광고심의 기준, 심의사례, 상품설명서, 약관은 의미 기반 검색이 필요하다. 사용자가 입력한 광고 문구나 AI가 탐지한 위험 표현은 정확히 같은 키워드가 없어도 관련 기준을 찾아야 한다.

DB 명세서와 프로젝트 규칙 문서는 벡터 DB 후보로 Qdrant를 전제하고 있다.

## 결정

벡터 DB로 Qdrant를 채택한다.

Qdrant는 다음 데이터를 담당한다.

| 데이터 | 역할 |
| --- | --- |
| 기준자료 chunk embedding | 의미 기반 근거 검색 |
| 심의사례 embedding | 유사 사례 검색 |
| 상품설명서/약관 chunk embedding | 광고 문구와 상품 조건 의미 비교 |

PostgreSQL은 chunk 메타데이터와 원천 근거 식별자를 저장하고, Qdrant는 벡터 검색 색인을 담당한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| Qdrant | 경량 구성, Python 연동, Docker Compose 운영에 적합하다. |
| pgvector | 운영 단순성은 좋지만 벡터 검색을 PostgreSQL에 집중시켜 역할 분리가 약해진다. |
| Milvus | 대규모 벡터 검색에는 강하지만 PoC 초기 운영 부담이 크다. |
| OpenSearch Vector | 검색 엔진 수를 줄일 수 있으나 키워드/벡터 역할 분리와 튜닝이 복잡해질 수 있다. |

## 결정 근거

- PoC에서 빠르게 구성하고 교체 가능하게 운영하기 쉽다.
- OpenSearch와 역할을 나누면 Hybrid Search 설계가 명확해진다.
- Docker Compose 기반 온프렘 이전 가능성과 맞다.
- 기준자료, 심의사례, 상품설명서 chunk 단위 검색에 적합하다.

## 영향

- embedding 모델과 Qdrant collection schema를 별도 관리해야 한다.
- PostgreSQL의 `evidence_chunks`와 Qdrant point ID 정합성을 유지해야 한다.
- 운영 리소스가 부족한 환경에서는 pgvector 축소안을 재검토할 수 있다.

## 후속 조치

- Qdrant collection payload 스키마는 ADR-0071을 따르고, idempotent upsert/delete 기준은 ADR-0070을 따른다.
- embedding 모델 버전과 chunking 정책을 ADR-0070 및 DB/API 명세에 기록한다.
- 벡터 검색 실패 시 OpenSearch keyword-only fallback은 ADR-0061 기준 사용하지 않고 RAG 검색 인프라 장애로 처리한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
- `docs/adr/ADR-0070-search-index-idempotent-sync-policy.md`
- `docs/adr/ADR-0071-search-index-schema-analyzer-payload-policy.md`
