# ADR-0018: 위험도 산정 기준

## 상태

Accepted

## 배경

검토 결과 화면, Annotation, 리포트, 대시보드는 항목별 위험도와 종합 위험도를 기준으로 검토 우선순위를 제공한다. API와 DB 명세에는 이미 `HIGH`, `MEDIUM`, `LOW`, `CHECK_REQUIRED` 위험도 코드가 정의되어 있으나, 어떤 조건에서 각 위험도를 부여할지는 별도 기준이 필요하다.

위험도를 LLM 판단에만 맡기면 같은 사안에 대한 결과가 흔들릴 수 있고, 고객사나 담당자가 “왜 이 항목이 HIGH인가”를 확인하기 어렵다. 따라서 정형 Rule 결과, RAG 근거 관련도, LLM 문맥 판단, OCR/Parser 신뢰도를 조합하되, 최종 기준표를 문서화해 구현과 테스트의 기준으로 사용한다.

## 결정

위험도 산정은 Rule 우선, RAG/LLM 보조, 불확실성은 `CHECK_REQUIRED` 원칙으로 수행한다.

| 입력 | 역할 |
| --- | --- |
| Rule 결과 | 필수 문구, 금리/수익률 표기, 심의필 번호, 금지어 등 명확한 위반 여부 판정 |
| RAG 근거 관련도 | 판단에 사용할 기준자료가 충분하고 관련성이 높은지 확인 |
| LLM 판단 | 과장·오인 가능성, 문맥상 불일치, 판단 사유, 보완 문구 제안 |
| OCR/Parser 신뢰도 | ADR-0053 기준 원문 추출과 좌표가 판단에 사용할 만큼 신뢰 가능한지 확인 |
| 담당자 판정 | 최종 심의 판단 확정 |

상세 기준은 `docs/risk-assessment-criteria.md`를 기준으로 한다.

## 위험도 의미

| 위험도 | 의미 | 기본 처리 |
| --- | --- | --- |
| `HIGH` | 즉시 수정 또는 담당자 확인이 필요한 중대 리스크 | `NEEDS_REVISION` 우선 |
| `MEDIUM` | 수정 권고 또는 추가 확인이 필요한 리스크 | `NEEDS_REVISION` 또는 `NEEDS_CONFIRMATION` |
| `LOW` | 경미한 표현 개선 또는 참고 수준 | `APPROPRIATE` 또는 참고 권고 |
| `CHECK_REQUIRED` | 자동 판단을 확정할 수 없음 | `NEEDS_CONFIRMATION` |

`CHECK_REQUIRED`는 낮은 위험도가 아니라 자동 판단 불확실성을 의미한다. 근거 부족, OCR 신뢰도 부족, Rule/LLM 충돌, 기준자료 관련도 부족은 억지로 `HIGH`, `MEDIUM`, `LOW`로 환산하지 않는다.

## 산정 원칙

| 조건 | 위험도 |
| --- | --- |
| Rule이 명시 위반으로 판정 | `HIGH` |
| 필수 고지 누락, 금리/수익률 핵심 정보 오류, 심의필 번호 오류 | `HIGH` |
| RAG 근거 관련도 높고 LLM도 위험 판단 | `HIGH` 또는 `MEDIUM` |
| RAG 근거는 있으나 LLM 판단이 “오인 가능성” 수준 | `MEDIUM` |
| Rule 위반 없음, RAG 근거 충분, LLM도 적정 판단 | `LOW` |
| RAG 근거 부족 | `CHECK_REQUIRED` |
| OCR/Parser 신뢰도 ADR-0053 확인 필요 구간 | `CHECK_REQUIRED` |
| OCR/Parser confidence `< 0.50`으로 판정 대상 문구 식별 불가 | 평가 제외 후보 |
| Rule과 LLM 판단 충돌 | `CHECK_REQUIRED` |
| LLM 단독 판단이며 근거 연결 없음 | `CHECK_REQUIRED` |

Review Orchestrator는 개별 엔진 결과를 모아 위험도를 산정한다. LLM은 위험도를 단독 확정하지 않고, 문맥 판단과 설명, 보완 문구 추천을 제공한다.

## 종합 위험도 산정

광고물 전체의 종합 위험도는 항목별 위험도를 보수적으로 집계한다.

| 항목별 결과 | 종합 위험도 |
| --- | --- |
| `HIGH`가 1건 이상 | `HIGH` |
| `HIGH` 없음, `CHECK_REQUIRED`가 1건 이상 | `CHECK_REQUIRED` |
| `HIGH`/`CHECK_REQUIRED` 없음, `MEDIUM`이 1건 이상 | `MEDIUM` |
| `LOW` 또는 적정 항목만 존재 | `LOW` |

단, 준법감시 담당자의 최종 판정이 있는 경우 화면과 리포트에서는 AI 종합 위험도와 담당자 최종 판정을 구분해 표시한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| Rule 기반 점수만 사용 | 재현성은 높지만 문맥상 과장·오인 표현을 포착하기 어렵다. |
| LLM 판단만 사용 | 구현은 빠르지만 일관성, 설명 가능성, 테스트 가능성이 낮다. |
| Rule + RAG + LLM 조합 | 구현은 복잡하지만 금융광고 심의의 정형/문맥 판단을 균형 있게 처리한다. |
| 위험도 없이 담당자 확인만 표시 | 보수적이지만 검토 우선순위를 제공하지 못한다. |

## 결정 근거

- 금융광고 심의는 중대 위반 가능성을 우선적으로 드러내야 한다.
- Rule 위반처럼 명확한 조건은 LLM 판단보다 우선해야 한다.
- 근거가 부족한 상태에서 확정 위험도를 부여하면 설명 가능성과 신뢰도가 떨어진다.
- 기준표를 문서화하면 구현, 테스트, 고객사 협의, 향후 기준 변경을 같은 기준으로 진행할 수 있다.
- 위험도 산정 기준은 AI 모델 교체와 독립적으로 유지되어야 한다.

## 영향

- `Review Orchestrator`에 위험도 산정 규칙이 필요하다.
- `review_items`에는 위험도 산정에 사용한 rule result, evidence relevance, llm decision, confidence 정보를 추적할 수 있어야 한다.
- API 응답에는 위험도와 함께 주요 산정 사유를 표시해야 한다.
- 테스트케이스에는 기준표의 대표 조건을 fixture로 포함해야 한다.
- 위험도 기준 변경은 ADR 후속 기록 또는 기준표 문서 변경 이력으로 남긴다.

## 후속 조치

- `docs/risk-assessment-criteria.md`를 구현과 테스트의 기준 문서로 사용한다.
- 기능명세서의 위험도 기준 설명을 본 ADR 기준으로 갱신한다.
- API/DB 명세의 위험도 산정 근거 필드는 ADR-0068 기준 `risk_policy_version`, `risk_reason_codes`, `risk_score_detail`, `riskRationale`로 관리한다.
- 테스트케이스에 Rule 위반, RAG 근거 부족, OCR 신뢰도 부족, Rule/LLM 충돌 케이스를 추가한다.
- 화면과 리포트에서 `CHECK_REQUIRED`를 낮은 위험도가 아니라 담당자 확인 필요 상태로 표시한다.
- OCR/Parser/Annotation 신뢰도 임계값과 상태 매핑은 ADR-0053을 따른다.

## 관련 문서

- `docs/risk-assessment-criteria.md`
- `docs/adr/ADR-0053-confidence-threshold-policy.md`
- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0013-rule-rag-llm-responsibility.md`
- `docs/adr/ADR-0011-hybrid-search-strategy.md`
- `docs/adr/ADR-0068-risk-rationale-persistence-and-api-response-policy.md`
