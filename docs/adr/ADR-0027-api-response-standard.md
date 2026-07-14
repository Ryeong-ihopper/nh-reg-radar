# ADR-0027: API 응답 표준

## 상태

Accepted

## 배경

본 프로젝트는 `openapi/openapi.yaml`을 API 계약의 원천으로 사용한다. 따라서 API 응답 구조는 OpenAPI schema, FastAPI response model, 프론트엔드 타입 생성, API contract test에 직접 영향을 준다.

초기 API 명세서에는 `success`, `code`, `message`, `data`, `timestamp`를 포함하는 공통 Wrapper 형식이 제안되어 있었다. 그러나 모든 성공 응답을 Wrapper로 감싸면 리소스 schema가 한 단계 깊어지고, OpenAPI 기반 타입 생성 시 실제 업무 객체보다 Wrapper 타입이 전면에 드러난다. 반면 오류 응답은 프론트엔드 표시, 감사 로그, 장애 추적, 테스트 검증을 위해 표준화가 필요하다.

## 결정

성공 응답은 공통 Wrapper로 감싸지 않고 HTTP status code와 리소스별 response schema를 그대로 사용한다. 오류 응답만 공통 형식으로 표준화한다.

### 성공 응답 원칙

| 상황 | 응답 기준 |
| --- | --- |
| 단건 조회 | 리소스 객체를 그대로 반환 |
| 목록 조회 | 목록과 pagination metadata를 포함한 리소스별 schema 반환 |
| 생성 | `201 Created`와 생성된 리소스 또는 생성 식별자 반환 |
| 수정 | 수정된 리소스 또는 처리 결과 객체 반환 |
| 삭제 | 반환할 본문이 없으면 `204 No Content` 사용 |
| 비동기 요청 | 생성된 job 또는 review request 식별자와 상태 반환 |

성공 여부는 `success: true` 필드가 아니라 HTTP status code로 판단한다.

### 오류 응답 원칙

오류 응답은 모든 API에서 다음 구조를 사용한다.

```json
{
  "code": "FILE_NOT_SUPPORTED",
  "message": "지원하지 않는 파일 형식입니다.",
  "details": [
    {
      "field": "advertisementFile",
      "reason": "jpg, jpeg, png, pdf, hwp, hwpx 파일만 업로드할 수 있습니다."
    }
  ],
  "traceId": "req-20260707-000001",
  "timestamp": "2026-07-07T10:30:00+09:00"
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `code` | Y | 업무 또는 시스템 오류 코드 |
| `message` | Y | ADR-0045 기준 사용자에게 노출 가능한 기본 오류 메시지 |
| `details` | N | 필드 단위 오류, 원인, 추가 컨텍스트 |
| `traceId` | Y | 요청 추적 ID. `X-Request-Id`가 있으면 동일 값 사용 |
| `timestamp` | Y | 오류 발생 시각 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 모든 응답에 공통 Wrapper 사용 | 프론트엔드 처리 일관성은 높지만 REST 리소스 schema가 불필요하게 깊어지고 OpenAPI 타입 생성 결과가 장황해진다. |
| 성공 응답은 REST 기본, 오류 응답만 표준화 | 리소스 schema를 명확히 유지하면서 오류 처리 일관성을 확보할 수 있다. |
| API별 자율 | 초기 개발 속도는 빠르지만 프론트엔드 오류 처리, 테스트케이스, 운영 추적 기준이 흔들릴 가능성이 크다. |

## 결정 근거

- 성공 응답은 OpenAPI schema와 프론트엔드 타입 생성에서 리소스 구조가 직접 드러나는 것이 유리하다.
- 오류 응답은 화면 표시, API contract test, 감사 로그, 장애 추적에서 공통 처리가 필요하다.
- HTTP status code가 성공/실패 판단의 기본 수단이므로 `success` 필드를 중복으로 유지할 필요가 낮다.
- FastAPI의 response model을 리소스별로 정의하면 API 문서와 타입 생성 결과가 단순해진다.

## 영향

- `docs/api-specification.md`의 공통 성공 응답 규격은 제거하고 성공 응답 원칙으로 대체한다.
- Markdown API 명세서의 성공 응답 예시는 리소스별 schema 형태로 관리한다.
- 오류 응답 schema는 `openapi/openapi.yaml`의 공통 component로 정의한다.
- 프론트엔드는 HTTP status code와 오류 응답의 `code`, `message`, `details`, `traceId`를 기준으로 처리하되, 사용자 표시 문구는 ADR-0045 기준을 따른다.
- API contract test는 성공 응답에 `success: true` Wrapper를 요구하지 않는다.

## 후속 조치

- `openapi/openapi.yaml` 작성 시 `ErrorResponse` component를 공통 schema로 정의한다.
- `openapi/openapi.yaml` 작성 시 Markdown API 명세서의 성공 응답 예시와 리소스별 schema를 대조한다.
- 프론트엔드 API client 또는 fetch wrapper는 오류 응답만 공통 파싱하도록 구현한다.
- 테스트케이스의 오류 응답 기대값은 `code`, `message`, `details`, `traceId` 및 ADR-0045의 사용자 메시지 매핑 기준으로 정리한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/api-contract-sync-policy.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0026-api-contract-management.md`
- `docs/adr/ADR-0045-user-error-message-policy.md`
