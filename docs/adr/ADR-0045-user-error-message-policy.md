# ADR-0045: 사용자 오류 메시지 및 오류 코드 표시 정책

## 상태

Accepted

## 배경

ADR-0027은 API 오류 응답을 `code`, `message`, `details`, `traceId`, `timestamp` 형식으로 표준화했다. 그러나 같은 오류 코드가 화면마다 다르게 표시되거나, API 내부 오류 문구가 그대로 사용자에게 노출되면 사용자 경험, 보안, 테스트 기대값이 흔들릴 수 있다.

특히 본 프로젝트는 광고 원본, 상품설명서, 약관, 기준자료 원문, 외부 AI 호출, presigned URL 같은 민감한 데이터를 다룬다. 오류 메시지에 광고 문구 원문, 파일 경로, 내부 stack trace, token, presigned URL 전체값이 포함되면 보안 사고로 이어질 수 있다.

따라서 API 오류 코드와 사용자 표시 메시지의 매핑 기준을 문서화하고, 화면과 테스트는 이 기준을 따른다.

## 결정

공통 오류 코드를 기준으로 사용자 표시 메시지 매핑표를 관리한다. API 오류 응답 구조는 ADR-0027을 유지하며, `message`는 사용자에게 노출 가능한 기본 메시지로 작성한다.

| 항목 | 결정 |
| --- | --- |
| API 오류 구조 | ADR-0027의 `code`, `message`, `details`, `traceId`, `timestamp` 유지 |
| 사용자 표시 기준 | 오류 코드별 기본 사용자 메시지를 표시 |
| 화면별 보완 | 화면 맥락상 필요한 경우 짧은 보완 안내를 추가 |
| 상세 원인 확인 | 사용자에게는 `traceId`를 제공하고 상세 원인은 로그에서 확인 |
| 민감정보 노출 | 파일 원문, 광고 원문, token, presigned URL, stack trace 노출 금지 |
| 테스트 기준 | 오류 코드와 사용자 메시지 매핑을 테스트 기대값으로 사용 |

## 오류 코드별 기본 사용자 메시지

| 오류 코드 | 기본 사용자 메시지 |
| --- | --- |
| `BAD_REQUEST` | 요청값을 확인해 주세요. |
| `UNAUTHORIZED` | 로그인이 필요합니다. |
| `FORBIDDEN` | 접근 권한이 없습니다. |
| `NOT_FOUND` | 요청한 대상을 찾을 수 없습니다. |
| `CONFLICT` | 현재 상태에서는 요청을 처리할 수 없습니다. |
| `FILE_NOT_SUPPORTED` | 지원하지 않는 파일 형식입니다. |
| `FILE_READ_FAILED` | 파일을 읽지 못했습니다. 파일을 다시 확인해 주세요. |
| `FILE_SIZE_EXCEEDED` | 파일 용량이 50MB를 초과했습니다. |
| `OCR_FAILED` | 문구를 판독하지 못했습니다. 원본 파일을 확인해 주세요. |
| `STANDARD_NOT_FOUND` | 관련 기준자료를 찾을 수 없습니다. |
| `PRODUCT_INFO_MISSING` | 상품설명서 또는 약관이 없어 검토가 제한됩니다. |
| `REVIEW_ALREADY_RUNNING` | 이미 분석이 진행 중입니다. 진행 상태를 확인해 주세요. |
| `REVIEW_FAILED` | AI 검토 중 오류가 발생했습니다. 재분석을 요청해 주세요. |
| `UNSUPPORTED_REPORT_FORMAT` | 지원하지 않는 리포트 형식입니다. |
| `INTERNAL_ERROR` | 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. |

## 메시지 작성 기준

| 구분 | 기준 |
| --- | --- |
| 길이 | 한 문장 또는 짧은 두 문장으로 작성 |
| 표현 | 사용자가 다음 행동을 알 수 있게 작성 |
| 책임 표현 | AI 판단 실패와 사용자 입력 오류를 구분 |
| 불확실성 | 기준자료 부족, OCR 실패, 근거 부족은 담당자 확인 필요 흐름으로 안내 |
| 추적 | 반복 오류는 `traceId`와 함께 문의하도록 안내 가능 |
| 화면 보완 | 화면별 버튼 또는 다음 행동은 프론트엔드 문구로 보완 |

## 노출 금지 정보

| 금지 대상 | 예시 |
| --- | --- |
| 내부 stack trace | Python traceback, SQL error 전문 |
| 파일 시스템 경로 | `/app/uploads/...`, 서버 로컬 경로 |
| Object Storage URL | presigned URL 전체값, bucket 내부 경로 |
| 인증 정보 | token, session id, API key, secret |
| 고객사 원문 | 광고 문구 전문, 상품설명서/약관 원문 |
| Prompt 전문 | LLM prompt, system message, 내부 지침 |
| DB 상세 오류 | raw SQL, constraint 내부명만 노출하는 메시지 |

`details`에는 필드명, 안전한 reason code, 허용 확장자, 제한 용량처럼 사용자 조치에 필요한 정보만 포함한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| API 오류 메시지를 그대로 화면에 표시 | 구현은 쉽지만 화면 맥락과 보안 통제가 약하다. |
| 화면별 사용자 메시지를 프론트에서 별도 관리 | UX는 좋지만 API/테스트와 불일치할 수 있다. |
| 공통 오류 코드와 사용자 메시지 매핑표를 문서화 | API, 화면, 테스트 정합성을 유지하기 가장 좋다. |
| 모든 오류를 상세 기술 메시지로 제공 | 디버깅에는 유리하지만 사용자와 고객사에게 부적절하다. |
| PoC에서는 최소 메시지만 사용 | 빠르지만 검수와 시연 품질이 낮아질 수 있다. |

## 결정 근거

- 오류 메시지는 사용자가 다음 행동을 결정하는 데 필요하다.
- 공통 오류 코드와 메시지 매핑이 있어야 화면, API, 테스트 기대값이 일치한다.
- 민감정보가 오류 메시지에 섞이면 감사 로그 정책과 파일 접근 정책을 우회하는 노출이 발생할 수 있다.
- `traceId`를 제공하면 사용자 메시지를 짧게 유지하면서 운영자가 로그에서 상세 원인을 추적할 수 있다.

## 영향

- API 명세의 공통 오류 코드에는 기본 사용자 메시지를 함께 관리한다.
- 프론트엔드는 오류 코드별 기본 메시지를 사용하되 화면별 보완 안내를 추가할 수 있다.
- 테스트케이스는 주요 오류 코드의 `code`, `message`, `traceId`를 검증한다.
- 내부 예외와 외부 AI/OCR/RAG 오류는 사용자 메시지로 변환하는 error mapper를 거친다.
- 로그에는 상세 원인을 남기되 사용자 응답에는 민감정보를 포함하지 않는다.

## 후속 조치

- OpenAPI 작성 시 `ErrorResponse` schema와 오류 코드 enum을 본 ADR 기준으로 정의한다.
- 프론트엔드 공통 error handler에 오류 코드별 메시지 매핑을 반영한다.
- 테스트케이스에 주요 오류 코드별 사용자 메시지 검증을 추가한다.
- 구현 중 신규 오류 코드가 필요하면 API 명세, 화면-API 매핑표, 테스트케이스를 함께 갱신한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/screen-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/adr/ADR-0027-api-response-standard.md`
- `docs/adr/ADR-0021-file-access-download-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
