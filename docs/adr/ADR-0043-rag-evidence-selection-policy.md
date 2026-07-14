# ADR-0043: RAG 검색 결과 선정 및 근거 표시 정책

## 상태

Accepted

## 배경

ADR-0011은 RAG 근거 검색 전략으로 Hybrid Search를 채택했고, ADR-0012는 기준자료 Chunking과 기본 Top-3 근거 표시 원칙을 정의했다. 그러나 실제 검토 결과에 어떤 근거를 몇 개까지 연결할지, LLM/Rule 입력에는 몇 개의 근거를 사용할지, 관련도 점수가 낮거나 근거가 부족할 때 어떤 상태로 처리할지는 별도로 확정되지 않았다.

RAG 검색 결과 선정 기준이 모호하면 같은 광고 문구에 대해 화면, API, 리포트, KPI 평가에서 서로 다른 근거가 표시될 수 있다. 또한 Qdrant와 OpenSearch는 점수 체계가 다르기 때문에 PoC 초기부터 단일 절대 점수 임계값만으로 근거를 자르는 방식은 위험하다.

## 결정

RAG 검색 결과 선정 정책은 Top-K, 품질 기준, 근거 표시 개수, 근거 부족 처리 기준을 함께 관리한다.

| 항목 | 결정 |
| --- | --- |
| 기본 검색 방식 | ADR-0011 기준 Hybrid Search |
| 내부 후보 수집 | keyword/vector 결과를 병합해 후보 Top 20 수집 |
| LLM/Rule 입력 근거 | 재랭킹 후 상위 5개까지 사용 |
| 검토 항목 저장 근거 | 검토 항목별 최대 5개까지 `review_item_evidences`에 저장 |
| 화면 표시 근거 | 검토 항목별 최대 3개 표시 |
| 리포트 표시 근거 | 검토 항목별 핵심 근거 1~3개 표시 |
| 근거 부족 처리 | 관련 근거가 부족하면 `CHECK_REQUIRED` 또는 기준자료 부족 상태로 표시 |
| 검색 인프라 장애 | ADR-0061 기준 RAG 검토 실패로 처리하고 fallback 판단 금지 |
| 재현성 | 사용된 `evidence_id`, `evidence_chunk_id`, `standard_version_id`, `rank_no`, `relevance_score`, `match_source` 저장 |

## 선정 흐름

```text
query / review target
  -> metadata filter
  -> OpenSearch keyword search
  -> Qdrant vector search
  -> candidate merge
  -> duplicate chunk/evidence 제거
  -> metadata/rule match 기반 rerank
  -> internal Top 20 후보 보존
  -> Top 5를 판단 입력으로 사용
  -> Top 1~3을 화면/리포트 핵심 근거로 표시
```

## 품질 기준

PoC 초기에는 Qdrant와 OpenSearch의 원점수 절대값만으로 근거 사용 여부를 결정하지 않는다. 다음 요소를 조합해 근거 품질을 판단한다.

| 기준 | 설명 |
| --- | --- |
| Rank | 병합/재랭킹 결과 순위 |
| Metadata match | 상품군, 광고유형, 기준 유형, 적용일 일치 여부 |
| Rule match | 금지어, 필수 문구, 조문번호, 기준 유형의 직접 일치 여부 |
| Source priority | 법령/내규/상품자료/심의사례 등 근거 유형의 우선순위 |
| Structure confidence | ADR-0012의 구조 인식 신뢰도 |
| Relevance score | keyword/vector/combined score의 정규화 결과 |

절대 점수 임계값은 PoC 평가셋 결과가 쌓인 뒤 조정한다. 초기 구현에서는 아래 기준을 사용한다.

| 상황 | 처리 |
| --- | --- |
| 상위 근거가 metadata 또는 rule match를 포함 | 근거 후보로 사용 |
| 상위 근거가 의미적으로 유사하지만 metadata 불일치 | 낮은 우선순위로 사용하거나 담당자 확인 필요 표시 |
| 관련 근거가 1~2개만 충분 | 확보된 근거만 표시하고 근거 부족 여부를 남김 |
| 관련 근거가 없거나 모두 품질 미달 | `CHECK_REQUIRED` 또는 `REFERENCE_INSUFFICIENT`로 처리 |
| 기준자료 자체가 미제공 | `STANDARD_MISSING` 또는 기준자료 부족 상태로 처리 |
| Qdrant 또는 OpenSearch 장애 | `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED`로 처리하고 ADR-0059 기준 retry |

## 표시 기준

| 표시 위치 | 기준 |
| --- | --- |
| 상세 검토 결과 API | 검토 항목별 최대 3개 근거를 rank 순으로 반환 |
| 검토 결과 화면 | 핵심 근거 1~3개 표시, 전체 근거는 상세 또는 확장 영역에서 조회 |
| 리포트 | 핵심 근거 1~3개 표시. 근거 부족 시 “기준자료 확인 필요” 문구 포함 |
| PoC KPI 평가 | 근거 매칭 적정성은 표시된 핵심 근거와 저장된 매핑 근거를 기준으로 평가 |

## 대안

| 대안 | 판단 |
| --- | --- |
| Top-K만 고정 | 구현은 단순하지만 근거 품질 통제가 약하다. |
| Top-K와 최소 관련도 점수만 사용 | 기본 통제는 가능하지만 검색 엔진별 점수 차이 때문에 오판 가능성이 있다. |
| Top-K, 품질 기준, 표시 개수, 근거 부족 처리를 함께 정의 | 화면/API/리포트/KPI 정합성을 확보하면서 PoC 구현 부담을 관리할 수 있다. |
| AI가 모든 검색 결과를 재랭킹해 최종 선택 | 품질은 좋아질 수 있으나 비용, 재현성, 온프렘 전환 부담이 크다. |
| 제한 없이 반환하고 화면에서 필터 | 구현은 쉽지만 결과 일관성과 재현성이 낮다. |

## 결정 근거

- 금융광고 심의는 근거의 정확성과 재현성이 중요하다.
- Hybrid Search 점수는 검색 엔진별로 스케일이 달라 단일 절대값 임계치만으로 판단하기 어렵다.
- 검토 화면과 리포트에는 과도한 근거를 모두 표시하기보다 핵심 근거를 제한해 보여주는 편이 업무에 적합하다.
- 저장 근거와 표시 근거를 분리하면 감사 추적성과 사용자 가독성을 동시에 확보할 수 있다.
- 근거 부족 상태를 명시해야 AI가 불충분한 근거로 확정 판단하는 위험을 줄일 수 있다.

## 영향

- `review_item_evidences`에는 근거 ID, Chunk ID, 기준자료 버전, 순위, 관련도, 검색 출처를 저장한다.
- 상세 검토 결과 API와 근거 검색 API는 rank와 score를 함께 반환한다.
- 화면과 리포트는 검토 항목별 핵심 근거를 최대 3개까지 표시한다.
- 관련 근거가 부족한 검토 항목은 `CHECK_REQUIRED` 또는 기준자료 부족 상태로 분류한다.
- 검색 인프라 장애는 관련 근거 부족이 아니라 기술 장애로 분류하며 ADR-0061 기준 RAG 검토 실패로 처리한다.
- PoC 평가에서 근거 매칭 적정성은 표시 근거와 저장 근거를 함께 기준으로 삼는다.

## 후속 조치

- 검색 품질 평가셋이 확보되면 관련도 정규화 산식과 임계값을 조정한다.
- Qdrant/OpenSearch 장애 시 keyword-only 또는 vector-only fallback은 ADR-0061 기준 사용하지 않는다.
- 화면 설계 시 근거 3개 초과 항목을 확장 표시할지 여부를 UI 상세 설계에서 결정한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/poc-kpi-formulas.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0012-reference-chunking-policy.md`
- `docs/adr/ADR-0061-rag-search-infra-failure-policy.md`
