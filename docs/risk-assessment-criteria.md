# 위험도 산정 기준표

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-07-13 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-07-13 | ADR-0018/0068 기준 위험도 산정 원칙, 판정 상태, 테스트 기준 정리 |

## 1. 문서 목적

본 문서는 광고심의 AI 검토 결과의 항목별 위험도와 종합 위험도를 산정하기 위한 기준표이다.

위험도 산정은 다음 원칙을 따른다.

- 정형 Rule 위반은 LLM 판단보다 우선한다.
- RAG 근거가 부족하면 확정 판단을 하지 않고 `CHECK_REQUIRED`로 처리한다.
- OCR/Parser 신뢰도가 ADR-0053 기준 확인 필요 구간이면 담당자 확인이 필요한 상태로 처리한다.
- LLM은 위험도를 단독 확정하지 않고 문맥 판단, 설명, 보완 문구 추천을 제공한다.
- 최종 심의 판단은 준법감시 담당자가 수행한다.

## 2. 위험도 코드

| 위험도 | 의미 | 기본 판정 상태 |
| --- | --- | --- |
| `HIGH` | 즉시 수정 또는 담당자 확인이 필요한 중대 리스크 | `NEEDS_REVISION` |
| `MEDIUM` | 수정 권고 또는 추가 확인이 필요한 리스크 | `NEEDS_REVISION` 또는 `NEEDS_CONFIRMATION` |
| `LOW` | 경미한 표현 개선 또는 참고 수준 | `APPROPRIATE` 또는 참고 권고 |
| `CHECK_REQUIRED` | 자동 판단을 확정할 수 없음 | `NEEDS_CONFIRMATION` |

`CHECK_REQUIRED`는 낮은 위험도가 아니다. 근거 부족, 원문 신뢰도 부족, 판단 충돌처럼 담당자 확인이 필요한 상태를 의미한다.

## 3. 입력별 우선순위

| 우선순위 | 입력 | 처리 기준 |
| --- | --- | --- |
| 1 | Rule 명시 위반 | 즉시 `HIGH` 후보 |
| 2 | OCR/Parser 신뢰도 부족 | `CHECK_REQUIRED` 후보 |
| 3 | RAG 근거 관련도 부족 | `CHECK_REQUIRED` 후보 |
| 4 | Rule/LLM 판단 충돌 | `CHECK_REQUIRED` 후보 |
| 5 | RAG 근거 충분 + LLM 문맥 판단 | `HIGH`, `MEDIUM`, `LOW` 산정 |
| 6 | 담당자 최종 판정 | AI 위험도와 별도 표시 |

## 4. 항목별 위험도 기준

| 조건 | 위험도 | 판정 상태 | 예시 |
| --- | --- | --- | --- |
| 필수 고지 문구 누락 | `HIGH` | `NEEDS_REVISION` | 세전/연 기준, 투자위험 고지 누락 |
| 금리, 수익률, 수수료 등 핵심 정보 오류 | `HIGH` | `NEEDS_REVISION` | 실제 상품설명서와 다른 금리 표기 |
| 심의필 번호 누락 또는 형식 오류 | `HIGH` | `NEEDS_REVISION` | 필수 심의필 표시 누락 |
| 법령, 내규, 상품 기준과 명시적으로 충돌 | `HIGH` | `NEEDS_REVISION` | 금지 표현 또는 필수 제한 조건 위반 |
| RAG 근거 관련도 높고 LLM이 중대 오인 가능성 판단 | `HIGH` | `NEEDS_REVISION` | 원금 보장처럼 오인 가능한 표현 |
| RAG 근거 관련도 높고 LLM이 수정 필요 판단 | `MEDIUM` | `NEEDS_REVISION` | 혜택 조건이 일부 누락되어 오인 가능 |
| 표현은 대체로 맞지만 명확화가 필요한 경우 | `MEDIUM` | `NEEDS_CONFIRMATION` | 조건 문구가 모호하거나 위치가 불명확 |
| 내부 권장 문구와 일부 차이가 있으나 위반은 불명확 | `LOW` | `APPROPRIATE` 또는 참고 권고 | 문체, 순서, 표현 명확화 수준 |
| Rule 위반 없음, 근거 충분, LLM도 적정 판단 | `LOW` | `APPROPRIATE` | 주요 기준 충족 |
| RAG 근거가 없거나 관련도 기준 미달 | `CHECK_REQUIRED` | `NEEDS_CONFIRMATION` | 기준자료 확인 필요 |
| OCR/Parser 신뢰도가 ADR-0053 기준 확인 필요 구간 | `CHECK_REQUIRED` | `NEEDS_CONFIRMATION` | 흐린 이미지, 깨진 PDF, 구조 인식 부분 실패 |
| OCR/Parser confidence `< 0.50`으로 판정 대상 문구 식별 불가 | 평가 제외 후보 | `REVIEW_EXCLUDED` 후보 | OCR_UNREADABLE |
| Rule은 적정이나 LLM이 위험 판단 | `CHECK_REQUIRED` | `NEEDS_CONFIRMATION` | 정형 기준과 문맥 판단 충돌 |
| Rule은 위반이나 LLM이 적정 판단 | `HIGH` | `NEEDS_REVISION` | 정형 Rule 위반 우선 |
| LLM 단독 판단이며 근거 연결 없음 | `CHECK_REQUIRED` | `NEEDS_CONFIRMATION` | 근거 없는 위험 주장 |

## 5. 종합 위험도 기준

| 항목별 결과 | 종합 위험도 |
| --- | --- |
| `HIGH`가 1건 이상 | `HIGH` |
| `HIGH` 없음, `CHECK_REQUIRED`가 1건 이상 | `CHECK_REQUIRED` |
| `HIGH`/`CHECK_REQUIRED` 없음, `MEDIUM`이 1건 이상 | `MEDIUM` |
| `LOW` 또는 적정 항목만 존재 | `LOW` |

종합 위험도는 AI 검토 우선순위 표시용이다. 담당자 최종 판정은 별도 필드로 관리한다.

## 6. 화면 및 리포트 표시 기준

| 표시 항목 | 표시 기준 |
| --- | --- |
| 위험도 | `HIGH`, `MEDIUM`, `LOW`, `CHECK_REQUIRED` |
| 판정 상태 | `APPROPRIATE`, `NEEDS_REVISION`, `NEEDS_CONFIRMATION` |
| 산정 사유 | 적용된 Rule, RAG 근거, LLM 판단 요약 |
| 근거 | 관련 기준자료, 조문, 상품설명서 위치, 심의사례 |
| 확인 필요 사유 | 근거 부족, OCR 신뢰도 부족, 판단 충돌 등 |
| 책임 제한 문구 | AI 검토 결과는 심의 지원 정보이며 최종 판단은 담당자가 수행 |

## 7. 테스트 기준

다음 케이스는 자동 테스트 또는 평가셋에 포함한다.

| 테스트 케이스 | 기대 결과 |
| --- | --- |
| 필수 고지 문구 누락 | `HIGH`, `NEEDS_REVISION` |
| 상품설명서와 금리 불일치 | `HIGH`, `NEEDS_REVISION` |
| 과장 표현과 관련 근거 존재 | `HIGH` 또는 `MEDIUM` |
| 근거 관련도 기준 미달 | `CHECK_REQUIRED`, `NEEDS_CONFIRMATION` |
| OCR/Parser 신뢰도 확인 필요 | ADR-0053 기준 `CHECK_REQUIRED`, `NEEDS_CONFIRMATION` |
| Rule/LLM 판단 충돌 | `CHECK_REQUIRED` 또는 Rule 위반 우선 |
| 적정 광고물 | `LOW`, `APPROPRIATE` |

## 8. 변경 관리

위험도 산정 기준을 변경할 때는 다음을 함께 확인한다.

- 기능명세서의 위험도 설명
- API 명세의 risk level 응답
- DB 명세의 risk level 코드
- ADR-0068 기준 `risk_policy_version`, `risk_reason_codes`, `risk_score_detail`, `riskRationale` 응답
- 테스트케이스의 기대 결과
- 고객사와 합의한 PoC 평가 기준

중대한 산정 원칙 변경은 별도 ADR 또는 기존 ADR의 후속 기록으로 남긴다.
