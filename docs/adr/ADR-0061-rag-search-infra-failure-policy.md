# ADR-0061: RAG 검색 인프라 장애 처리 및 Fallback 금지 정책

## 상태

Accepted

## 배경

ADR-0011은 RAG 근거 검색의 기본 전략으로 Qdrant 벡터 검색과 OpenSearch 키워드 검색을 병행하는 Hybrid Search를 채택했다. ADR-0043은 검색 결과 Top-K, 근거 표시 개수, 근거 부족 처리 기준을 정의했다. 다만 Qdrant 또는 OpenSearch 장애 시 keyword-only/vector-only fallback을 허용할지, 아니면 RAG 검토 실패로 처리할지는 후속 결정으로 남아 있었다.

금융상품 광고심의에서 RAG 근거는 AI 판단의 설명 가능성과 담당자 검토 신뢰도에 직접 영향을 준다. 검색 인프라 장애 상황에서 한쪽 검색 결과만으로 제한 판단을 계속하면, 사용자는 정상 근거 검색 결과로 오해할 수 있고 잘못된 근거 또는 누락된 근거를 기준으로 심의 판단을 검토할 위험이 있다.

## 결정

Qdrant 또는 OpenSearch 검색 인프라 장애는 **degraded fallback 대상이 아니라 복구 대상 장애**로 처리한다.

| 항목 | 결정 |
| --- | --- |
| 정상 검색 | ADR-0011 기준 OpenSearch + Qdrant Hybrid Search |
| Qdrant 장애 | vector-only 누락 상태로 계속하지 않고 RAG 검토 실패 처리 |
| OpenSearch 장애 | keyword-only 누락 상태로 계속하지 않고 RAG 검토 실패 처리 |
| Qdrant/OpenSearch 모두 장애 | RAG 검토 실패 처리 |
| 사용자 안내 | RAG 검토 또는 AI 검토 실패로 안내하고 재분석/복구 필요 상태 표시 |
| Job 처리 | ADR-0059 기준 retry 대상. retry 한도 초과 시 `FAILED_FINAL` |
| 오류 코드 | `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED` |
| 근거 부족과의 구분 | 검색은 정상 수행됐으나 관련 근거가 부족한 경우만 `CHECK_REQUIRED` 또는 기준자료 부족 상태 처리 |

## 장애와 업무적 근거 부족 구분

| 상황 | 처리 |
| --- | --- |
| 검색 인프라 연결 실패 | `RAG_SEARCH_UNAVAILABLE`, retry 대상 |
| 검색 인프라 timeout | `RAG_SEARCH_UNAVAILABLE`, retry 대상 |
| 검색 인덱스 없음 또는 collection 없음 | `RAG_SEARCH_FAILED`, 운영 오류 수정 대상 |
| 검색 응답 schema 오류 | `RAG_SEARCH_FAILED`, 오류 수정 대상 |
| 검색은 정상이나 관련 근거 없음 | `CHECK_REQUIRED` 또는 `REFERENCE_INSUFFICIENT` |
| 기준자료 자체가 미제공 | `STANDARD_NOT_FOUND` 또는 `STANDARD_MISSING` |
| 기준일에 유효한 기준 버전 없음 | `CHECK_REQUIRED` 또는 `STANDARD_NOT_FOUND` |

검색 인프라 장애는 KPI 평가의 “근거 부족” 케이스로 섞지 않는다. 장애로 RAG 검토가 완료되지 않은 항목은 PoC 평가 시 기술 실패 또는 평가 제외 사유로 별도 집계한다.

## 처리 흐름

```text
RAG search step
  -> OpenSearch health/query
  -> Qdrant health/query
  -> 둘 중 하나라도 인프라 장애
  -> review_steps.failed_reason_code = RAG_SEARCH_UNAVAILABLE 또는 RAG_SEARCH_FAILED
  -> review_jobs retry scheduling
  -> retry 성공 시 Hybrid Search 재수행
  -> retry 한도 초과 시 FAILED_FINAL
```

Rule Engine 결과는 내부적으로 저장할 수 있으나, 화면과 리포트에서는 “RAG 검토 실패” 상태를 명확히 표시하고 RAG 근거가 필요한 검토 항목을 정상 완료로 표시하지 않는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 한쪽 검색 실패 시 RAG 검토 실패 | 근거 신뢰도와 장애 복구 책임이 명확해 채택 |
| B. Qdrant 장애 시 OpenSearch keyword-only fallback | 일부 결과는 얻을 수 있으나 사용자가 정상 검색으로 오해할 수 있어 기각 |
| C. OpenSearch 장애 시 Qdrant vector-only fallback | 조문번호, 필수 문구, 금지어 정확 검색 누락 위험이 있어 기각 |
| D. 둘 다 장애 시 Rule-only 결과 제공 | RAG 검토가 필요한 항목까지 완료처럼 보일 수 있어 기본 정책으로는 기각 |
| E. 모든 장애를 `CHECK_REQUIRED`로 표시 | 업무적 근거 부족과 기술 장애가 섞여 장애 복구 우선순위가 흐려져 기각 |

## 결정 근거

- RAG 근거는 금융광고 심의 설명 가능성과 감사 추적의 핵심이다.
- 한쪽 검색엔진만 사용한 결과는 정상 Hybrid Search 결과와 품질 특성이 다르다.
- 검색 장애는 담당자가 확인해야 할 업무적 불확실성이 아니라 운영자가 복구해야 할 기술 장애다.
- ADR-0059의 retry/dead-letter 정책과 연결하면 일시 장애와 최종 실패를 구분할 수 있다.
- 근거 부족과 인프라 장애를 분리해야 PoC KPI와 장애 리포트가 왜곡되지 않는다.

## 영향

- RAG 검색 adapter는 Qdrant와 OpenSearch 장애를 감지해 명시적 오류 코드로 반환해야 한다.
- Worker는 RAG 검색 인프라 장애를 ADR-0059 기준 retry 대상으로 처리한다.
- API 상태 조회는 `failedReasonCode`에 `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED`를 반환한다.
- 화면은 검색 인프라 장애를 “기준자료 확인 필요”가 아니라 “RAG 검토 실패/복구 필요”로 표시한다.
- 테스트 fixture는 근거 부족과 검색 인프라 장애를 별도 케이스로 분리한다.

## 후속 조치

- RAG adapter health check와 query timeout 기준을 구현 설정으로 관리한다.
- Docker Compose healthcheck 또는 worker startup check에 Qdrant/OpenSearch 연결 확인을 포함한다.
- 운영자가 검색 인덱스/collection 상태를 확인할 수 있는 runbook 또는 초기 진단 스크립트를 추가한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0009-qdrant-vector-database.md`
- `docs/adr/ADR-0010-opensearch-keyword-search.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0043-rag-evidence-selection-policy.md`
- `docs/adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md`
