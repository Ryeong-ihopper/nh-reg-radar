# ADR-0039: 문구 추천 검토·채택·수정 정책

## 상태

Accepted

## 배경

AI 검토 결과는 부적정하거나 위험한 광고 표현에 대해 보완 문구를 제안한다. API, DB, 화면, 테스트케이스에는 이미 문구 추천 조회와 담당자 판단 저장 기능이 정의되어 있다.

다만 AI 추천 문구를 최종 문안처럼 사용할지, 담당자 판단을 어떻게 저장할지, 수정 후 사용 문구를 리포트에 어떻게 반영할지에 대한 업무 기준이 명확하지 않으면 화면, API validation, 이력 보존, 리포트 생성 기준이 흔들릴 수 있다.

## 결정

초기 PoC에서는 AI 추천 문구를 담당자 검토 대상 초안으로 제공하고, 담당자가 `채택`, `미채택`, `수정 후 사용` 중 하나로 판단을 저장한다.

| 항목 | 결정 |
| --- | --- |
| AI 추천 문구 성격 | 최종 문안이 아니라 담당자 검토 대상 초안 |
| 기본 상태 | `PENDING` |
| 담당자 판단 상태 | `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED` |
| 판단 이력 | `suggestion_decisions`에 누적 저장 |
| 현재 상태 | `suggestions.decision_status`에 최신 판단 상태 반영 |
| 최종 문구 | `MODIFIED_AND_USED`일 때 `final_text` 필수 |
| 리포트 반영 | AI 추천 문구와 담당자 최종 판단을 구분 표시 |

상품부서 담당자와 준법감시 담당자는 모두 문구 추천 판단을 저장할 수 있다. 단, 최종 심의 판단과 대외적으로 확정된 광고 문안 책임은 준법감시 담당자 또는 고객사 업무 절차의 최종 승인자에게 있음을 화면과 리포트에서 구분한다.

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| 추천 문구 생성 직후 | `decision_status=PENDING` |
| 담당자가 그대로 사용 | `ACCEPTED`, `final_text`는 선택. 미입력 시 `suggested_text`를 최종 사용 문구로 간주 |
| 담당자가 사용하지 않음 | `REJECTED`, `comment` 권장 |
| 담당자가 수정해 사용 | `MODIFIED_AND_USED`, `final_text` 필수 |
| 동일 추천에 재판단 | 새 `suggestion_decisions` row를 추가하고 `suggestions.decision_status`만 최신 상태로 갱신 |
| 권한 없는 사용자 판단 저장 | `FORBIDDEN` |
| 존재하지 않는 추천 ID | `NOT_FOUND` |

추천 문구 복사는 상태 변경으로 보지 않는다. 복사 이벤트를 별도 감사 로그 대상으로 둘지는 PoC 필수 범위에서 제외한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| AI 추천 문구는 참고만 하고 저장하지 않음 | 구현은 단순하지만 피드백, 이력, 리포트 활용이 어렵다. |
| 담당자가 `채택/미채택/수정 후 사용`으로 판단 저장 | 현재 API, DB, 화면과 정합성이 가장 높고 감사 추적이 가능하다. |
| AI 추천 문구를 자동 채택 후보로 반영 | 업무 속도는 빠르지만 AI 문구가 최종안처럼 오해될 위험이 크다. |
| 준법감시 담당자만 채택 가능 | 통제는 강하지만 상품부서 자가수정 흐름이 느려진다. |

## 결정 근거

- 금융상품 광고 문구는 AI 자동 확정 대상이 아니라 담당자 검토와 책임 구분이 필요하다.
- `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED`는 현재 API, DB, 화면, 테스트케이스에 이미 반영된 상태값이다.
- 판단 이력을 누적하면 추천 품질 개선, 담당자 피드백 분석, PoC 결과 설명에 활용할 수 있다.
- 최신 상태와 이력 테이블을 분리하면 목록 조회 성능과 이력 추적성을 동시에 확보할 수 있다.
- 리포트에서 AI 추천과 담당자 최종 문구를 분리하면 AI 지원 정보와 사람의 판단을 명확히 구분할 수 있다.

## 영향

- API는 `decisionStatus` 값을 `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED`로 제한한다.
- `MODIFIED_AND_USED` 요청에는 `finalText`를 필수로 검증한다.
- `ACCEPTED` 요청에서 `finalText`가 없으면 `suggested_text`를 최종 사용 문구로 간주한다.
- DB는 `suggestion_decisions`에 판단 이력을 누적하고, `suggestions.decision_status`에는 최신 상태를 저장한다.
- 화면은 AI 추천 문구와 담당자 최종 문구를 구분 표시해야 한다.
- 리포트는 AI 추천 문구, 담당자 판단 상태, 최종 사용 문구를 구분해 포함한다.

## 후속 조치

- 구현 시 `SuggestionDecisionPolicy` 또는 동등한 validation 모듈을 둔다.
- 담당자 역할별 판단 가능 범위는 ADR-0036의 role + department scope 인가 규칙을 따른다.
- PoC 피드백 분석에서 `REJECTED`, `MODIFIED_AND_USED` 사유를 집계할지 추후 검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/screen-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0038-report-output-format-policy.md`
