# ADR-0011: Hybrid Search 전략 채택

## 상태

Accepted

## 배경

광고심의 근거 검색은 정확 검색과 의미 검색이 모두 필요하다. 조문번호, 필수 문구, 금지어처럼 정확한 표현을 찾아야 하는 경우가 있고, 광고 문맥과 유사한 기준이나 사례를 찾아야 하는 경우도 있다.

Qdrant는 벡터 검색을, OpenSearch는 키워드 검색을 담당하도록 결정했다.

## 결정

RAG 근거 검색의 기본 전략으로 Hybrid Search를 채택한다.

기본 흐름은 다음과 같다.

```text
query
  -> query normalization
  -> OpenSearch keyword search
  -> Qdrant vector search
  -> result merge/rerank
  -> top evidence selection
  -> review item evidence mapping
```

초기 PoC 기준은 다음과 같다.

| 항목 | 결정 |
| --- | --- |
| 검색 방식 | OpenSearch + Qdrant 병렬 검색 |
| 기본 표시 개수 | ADR-0043 기준 검토 항목별 최대 Top-3 근거 |
| 관련도 미달 | ADR-0043 기준 `CHECK_REQUIRED` 또는 “기준자료 확인 필요”로 표시 |
| 결과 병합 | keyword score, vector score, metadata match를 조합 |
| 메타데이터 필터 | 상품군, 광고유형, 기준 유형, 적용일 |
| 검색 인프라 장애 | ADR-0061 기준 fallback 금지. RAG 검토 실패 및 복구 대상 처리 |

## 대안

| 대안 | 판단 |
| --- | --- |
| Vector only | 문맥 검색은 좋지만 조문번호/필수 문구 정확 검색에 약하다. |
| Keyword only | 정확 검색은 좋지만 표현이 다른 유사 기준 검색에 약하다. |
| Hybrid Search | 구현 복잡도는 증가하지만 심의 근거 검색 품질에 가장 적합하다. |

## 결정 근거

- 금융광고 심의는 근거의 정확성과 설명 가능성이 중요하다.
- 광고 문구는 기준 문서와 표현이 다를 수 있어 의미 검색이 필요하다.
- 조문번호, 금지어, 필수 문구는 키워드 검색이 필요하다.
- Top 근거를 review item과 연결해 감사 추적성을 확보할 수 있다.

## 영향

- 검색 결과 병합과 rerank 로직이 필요하다.
- 검색 품질 평가는 keyword/vector 각각이 아니라 최종 Hybrid 결과 기준으로 수행한다.
- 관련도 기준과 Top-K 정책은 ADR-0043의 RAG 검색 결과 선정 및 근거 표시 정책을 따른다.
- Qdrant 또는 OpenSearch 장애 시 ADR-0061 기준 RAG 검토 실패로 처리하고 retry/복구 대상으로 관리한다.

## 후속 조치

- 검색 결과 병합 점수 산식의 초기 운영 기준은 ADR-0043을 따른다.
- 근거 Top-K와 관련도 threshold 조정은 PoC 평가셋 결과에 따라 후속 보완한다.
- 검색 품질 평가셋을 PoC 검증 데이터셋에 포함한다.
- 장애 시 keyword-only 또는 vector-only fallback은 ADR-0061 기준 사용하지 않는다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0009-qdrant-vector-database.md`
- `docs/adr/ADR-0010-opensearch-keyword-search.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
