# ADR-0023: PoC KPI 산식 확정

## 상태

Accepted

## 배경

PoC 성능 평가는 필수 문구 검토 정확도, 위험 표현 검토 정확도, 근거 매칭 적정성, 담당자 판단 일치율을 기준으로 한다. 기존 기능명세서와 API 명세서에는 KPI 항목과 목표치는 정의되어 있으나, 평가 단위, 분자/분모, 부분 정답 처리 기준이 명확하지 않으면 같은 결과를 두고도 산출값이 달라질 수 있다.

따라서 PoC 검증 데이터셋 구축 전에 KPI 산식을 항목 단위로 확정하고, 제외 기준과 부분 점수 기준을 구현과 검수의 공통 기준으로 남긴다.

## 결정

PoC KPI는 항목 단위 평가를 기본으로 산출한다.

광고물 단위 통과율이나 종합 평균 점수는 보조 지표로만 사용할 수 있으며, PoC 목표 달성 여부는 다음 네 개 KPI별 목표 달성 여부를 각각 판단한다.

| KPI 코드 | 지표 | 목표 |
| --- | --- | --- |
| `REQUIRED_PHRASE_ACCURACY` | 필수 문구 검토 정확도 | 80% 이상 |
| `MISLEADING_EXPRESSION_ACCURACY` | 위험 표현 검토 정확도 | 75% 이상 |
| `EVIDENCE_PRECISION` | 근거 매칭 적정성 | 85% 이상 |
| `HUMAN_AGREEMENT_RATE` | 담당자 판단 일치율 | 75% 이상 |

산식은 다음 원칙을 따른다.

1. 분모는 평가 대상 항목 중 제외 처리되지 않은 항목 수 또는 평가 대상 근거 수로 한다.
2. 분자는 정답지 또는 담당자 판단 기준과 일치한 항목의 점수 합계로 한다.
3. 부분 정답은 `1.0`, `0.5`, `0` 점수로 처리한다.
4. 평가 제외 항목은 분모와 분자에서 모두 제외하고, 제외 건수와 제외 사유를 별도로 보고한다.
5. 전체 평균 하나로 PoC 통과 여부를 판단하지 않고 KPI별 달성 여부를 따로 표시한다.

상세 산식과 부분 점수 기준은 `docs/poc-kpi-formulas.md`를 기준으로 한다.

## KPI별 산식

| KPI 코드 | 분자 | 분모 | 산식 |
| --- | --- | --- | --- |
| `REQUIRED_PHRASE_ACCURACY` | 필수 문구 항목별 match score 합계 | 평가 대상 필수 문구 항목 수 | `sum(match_score) / denominator * 100` |
| `MISLEADING_EXPRESSION_ACCURACY` | 위험 표현 항목별 match score 합계 | 평가 대상 위험 표현 항목 수 | `sum(match_score) / denominator * 100` |
| `EVIDENCE_PRECISION` | 관련성이 인정된 근거별 match score 합계 | AI가 제시한 평가 대상 근거 수 | `sum(match_score) / denominator * 100` |
| `HUMAN_AGREEMENT_RATE` | 담당자 판단과 일치한 주요 리스크 항목별 match score 합계 | 평가 대상 주요 리스크 항목 수 | `sum(match_score) / denominator * 100` |

분모가 0인 KPI는 점수를 0으로 강제하지 않는다. 해당 KPI는 `NOT_APPLICABLE`로 표시하고 목표 달성 여부 계산에서 제외한다.

## 부분 정답 처리

부분 정답은 다음 점수로 처리한다.

| 점수 | 의미 | 예시 |
| --- | --- | --- |
| `1.0` | 정답 또는 담당자 판단과 일치 | 누락 필수 문구를 정확히 탐지, 위험 표현 상태와 위험도가 일치, 정확한 근거를 제시 |
| `0.5` | 핵심 취지는 맞으나 세부가 불완전 | 수정 필요 판단은 맞지만 위험도 1단계 차이, 근거 문서는 맞지만 조항/문단 위치가 부정확 |
| `0` | 불일치 또는 평가 불가 | false positive, false negative, 무관한 근거 제시, 담당자 판단과 반대 결론 |

부분 정답 인정 여부는 평가 결과의 `partial_count`와 `detail_json.partial_reason`으로 남겨야 한다. 부분 정답을 인정하기 어려운 항목은 `0` 또는 평가 제외 후보로 분류한다.

## 평가 제외 처리

평가 제외 기준은 `docs/adr/ADR-0024-evaluation-exclusion-policy.md`를 따른다. 제외 처리된 항목은 KPI 분자와 분모에서 모두 제외한다.

평가 실행 결과에는 최소 다음 값을 함께 표시한다.

| 항목 | 설명 |
| --- | --- |
| `score` | KPI 점수 |
| `numerator` | match score 합계 |
| `denominator` | 평가 대상 항목 수 또는 근거 수 |
| `excludedCount` | 평가 제외 건수 |
| `partialCount` | 부분 정답 건수 |
| `notApplicable` | 분모 0으로 KPI 미적용 여부 |
| `targetScore` | 목표 점수 |
| `achieved` | 목표 달성 여부 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 항목 단위 평가 | 세부 오류 유형과 개선 대상을 추적하기 쉽고 현재 API/테스트 명세와 정합성이 높다. |
| 광고물 단위 평가 | 고객 설명은 쉽지만 광고물 하나의 복합 항목을 통과/실패로 단순화해 KPI 왜곡 가능성이 있다. |
| 리스크 단위 평가 | 위험도 중심 분석에는 유리하지만 필수 문구, 근거 매칭, 담당자 판단 일치율을 한 기준으로 묶기 어렵다. |

## 결정 근거

- 광고심의 검토 결과는 광고물 하나에 여러 필수 문구, 위험 표현, 근거가 연결된다.
- 항목 단위 평가는 오류 위치와 개선 대상을 명확히 보여준다.
- 기존 API 명세의 metric code와 테스트케이스가 항목별 KPI 산출을 전제로 한다.
- 부분 정답 기준을 점수화하면 담당자 판단의 실무적 수용 가능성을 반영할 수 있다.
- 평가 제외 항목을 분모에서 분리해야 OCR 불가, 기준자료 미제공 같은 외부 요인이 KPI를 왜곡하지 않는다.

## 영향

- 평가 데이터셋은 광고물 단위가 아니라 평가 항목 단위 정답지를 포함해야 한다.
- `evaluation_metrics`에는 점수뿐 아니라 분자, 분모, 제외 건수, 부분 정답 건수를 저장해야 한다.
- 평가 API 응답은 `score`, `numerator`, `denominator`, `excludedCount`, `partialCount`, `notApplicable`, `targetScore`, `achieved`를 포함한다.
- 테스트케이스는 KPI별 분자/분모와 부분 점수 산출을 검증해야 한다.
- PoC 결과보고서는 KPI별 목표 달성 여부와 주요 오류 유형을 함께 제시해야 한다.

## 후속 조치

- `docs/poc-kpi-formulas.md`를 구현 기준으로 유지한다.
- 평가 제외 기준은 ADR-0024 기준과 정합성을 유지한다.
- 검증 데이터셋/정답지의 공식 원천과 평가 실행 snapshot 고정은 ADR-0074 기준과 정합성을 유지한다.
- API 명세의 평가 응답은 산출 근거 필드를 포함하도록 유지한다.
- DB 명세의 `evaluation_metrics` 테이블은 산출 근거 필드를 포함하도록 유지한다.
- 테스트케이스는 부분 정답과 `NOT_APPLICABLE` 케이스를 포함하도록 유지한다.

## 관련 문서

- `docs/poc-kpi-formulas.md`
- `docs/functional-specification.md`
- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0024-evaluation-exclusion-policy.md`
- `docs/adr/ADR-0074-validation-dataset-golden-label-snapshot-policy.md`
