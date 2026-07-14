# ADR-0010: 키워드 검색 엔진으로 OpenSearch 채택

## 상태

Accepted

## 배경

광고심의 기준 검색은 의미 기반 검색만으로 충분하지 않다. 법령명, 조문번호, 상품명, 금지어, 필수 문구, 특정 표현은 정확 검색과 필터링이 중요하다.

OpenSearch는 키워드 검색, 필터, 하이라이트, 운영 색인 관리에 적합하며, Qdrant와 함께 Hybrid Search를 구성할 수 있다.

## 결정

키워드 검색 엔진으로 OpenSearch를 채택한다.

OpenSearch는 다음 검색을 담당한다.

| 검색 유형 | 예시 |
| --- | --- |
| 정확 검색 | 조문번호, 기준명, 상품명 |
| 키워드 검색 | 금지어, 필수 문구, 위험 표현 |
| 필터 검색 | 상품군, 광고유형, 기준 유형, 적용일 |
| 하이라이트 | 근거 문장 표시 |

PostgreSQL은 원천 데이터와 메타데이터를 보관하고, OpenSearch는 검색용 색인을 담당한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| OpenSearch | 온프렘 구성 가능, 정확 검색과 필터링에 적합하다. |
| Elasticsearch | 기능은 적합하지만 라이선스와 운영 정책 확인이 필요하다. |
| PostgreSQL Full Text Search | 단순 구성은 가능하지만 조문/문구 검색 품질과 확장성에 한계가 있다. |
| Qdrant만 사용 | 의미 검색은 가능하지만 정확 검색과 필터링 품질이 부족하다. |

## 결정 근거

- 금융광고 심의는 정확한 문구와 조문 근거가 중요하다.
- Qdrant 벡터 검색과 조합하면 의미 검색과 정확 검색을 모두 지원할 수 있다.
- Docker Compose 기반 PoC와 온프렘 이전 가능성이 있다.

## 영향

- PostgreSQL 원천 데이터와 OpenSearch 색인 동기화가 필요하다.
- 색인 schema, analyzer, synonym 정책은 ADR-0071 기준으로 관리해야 한다.
- 개발 VM 리소스가 부족하면 초기에는 PostgreSQL FTS로 축소하는 임시 경로를 검토할 수 있다.
- OpenSearch 장애 시 Qdrant vector-only fallback으로 계속 판단하지 않고 ADR-0061 기준 RAG 검색 인프라 장애로 처리한다.

## 후속 조치

- 기준자료 색인 schema, analyzer, synonym, highlight 기준은 ADR-0071을 따르고, idempotent upsert/delete 기준은 ADR-0070을 따른다.
- 상품군, 광고유형, 기준 유형, 적용일 필터 필드를 표준화한다.
- 검색 결과 하이라이트와 RAG 근거 표시 형식을 화면/API 명세와 맞춘다.

## 관련 문서

- `docs/database-specification.md`
- `docs/api-specification.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
- `docs/adr/ADR-0070-search-index-idempotent-sync-policy.md`
- `docs/adr/ADR-0071-search-index-schema-analyzer-payload-policy.md`
