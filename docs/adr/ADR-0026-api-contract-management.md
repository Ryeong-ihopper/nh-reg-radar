# ADR-0026: API 명세 관리 및 동기화 강제 방식

## 상태

Accepted

## 배경

본 프로젝트는 명세 기반 개발을 채택했고, 프론트엔드, 백엔드, AI Worker, 테스트케이스가 API 계약을 공유해야 한다. 현재 `docs/api-specification.md`는 사람이 읽기 좋은 Markdown 문서로 정리되어 있으나, API path, method, request/response schema, enum, status code 같은 계약 요소를 자동 검증하기에는 부족하다.

FastAPI는 구현 코드에서 OpenAPI 문서를 생성할 수 있지만, 코드 생성 문서를 원천으로만 삼으면 구현 전에 프론트엔드와 백엔드가 계약을 합의하기 어렵다. 따라서 Git에서 관리되는 OpenAPI YAML을 API 계약의 원천으로 두고, Markdown 문서는 업무 설명과 예시 문서로 유지한다.

## 결정

API 계약의 원천은 Git의 `openapi/openapi.yaml`로 둔다. `docs/api-specification.md`는 사람이 읽는 업무 설명, 예시, 권한, 화면 연계 문서로 유지한다.

API 계약 변경은 다음 파일을 같은 PR에서 함께 갱신해야 한다.

| 구분 | 파일 | 역할 |
| --- | --- | --- |
| 계약 원천 | `openapi/openapi.yaml` | path, method, schema, enum, status code, required field |
| 설명 문서 | `docs/api-specification.md` | API 목적, 업무 흐름, 예시, 권한, 화면/기능 연결 |
| 화면 연계 | `docs/screen-api-mapping.md` | 화면별 호출 API와 응답 반영 위치 |
| 검증 기준 | `docs/test-cases.md` | API 계약 테스트와 주요 정상/예외 케이스 |

충돌 시 우선순위는 `openapi/openapi.yaml > API contract test > docs/api-specification.md`로 둔다.

## 동기화 강제 방식

문서 동기화는 다음 세 가지 방식으로 강제한다.

| 방식 | 강제 내용 |
| --- | --- |
| PR 체크리스트 | API 변경 여부와 관련 문서/테스트 갱신 여부를 리뷰 전에 확인 |
| CI lint | OpenAPI YAML 문법과 스타일을 Spectral로 검사 |
| 구현 검증 | FastAPI가 생성한 `/openapi.json`과 `openapi/openapi.yaml`의 path/method/schema 차이를 비교 |

PoC 초기에는 `openapi/openapi.yaml` 작성과 Spectral lint를 우선 적용한다. 초기 작성 범위와 단계별 검증 기준은 [ADR-0062: OpenAPI 초기 계약 작성 범위 및 검증 단계 정책](ADR-0062-openapi-initial-contract-scope-and-validation.md)을 따른다. CI/CD Gate 적용 범위는 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)을 따르며, FastAPI 구현 이후에는 `/openapi.json` export와 계약 diff 검증을 CI에 추가한다.

## PR 필수 규칙

다음 변경은 `openapi/openapi.yaml` 수정 없이는 병합할 수 없다.

- API path 추가, 변경, 삭제
- HTTP method 변경
- request/response field 추가, 삭제, 타입 변경
- required 여부 변경
- enum 값 추가, 삭제, 이름 변경
- status code 추가, 삭제, 의미 변경
- 인증/권한 요구사항 변경

다음 변경은 Markdown만 수정할 수 있다.

- API 목적 설명 보강
- 업무 흐름 설명 보강
- 예시 문구 개선
- 화면 설명 또는 운영 주석 보강

## CI 검증 기준

CI는 단계적으로 다음 검증을 수행한다.

| 단계 | 검증 | 실패 조건 |
| --- | --- | --- |
| 1 | OpenAPI YAML parse/schema validation | YAML 오류 또는 OpenAPI 스키마 오류 |
| 2 | Spectral lint | 필수 규칙 위반 |
| 3 | API contract test | 구현 응답이 계약과 불일치 |
| 4 | FastAPI generated OpenAPI diff | `/openapi.json`과 `openapi/openapi.yaml`의 계약 차이 |
| 5 | TypeScript type/client generation diff | 생성 타입 변경이 PR에 반영되지 않음 |

## 대안

| 대안 | 판단 |
| --- | --- |
| Markdown API 명세서만 원천으로 유지 | 현재 문서와 이어가기 쉽지만 자동 검증과 타입 생성이 약하다. |
| FastAPI 코드 생성 OpenAPI만 원천으로 사용 | 구현과 문서 불일치는 줄지만 구현 전 계약 합의가 어렵다. |
| OpenAPI YAML만 원천으로 사용 | 자동화는 좋지만 업무 설명, 권한, 화면 흐름을 읽기 어렵다. |
| OpenAPI YAML 계약 원천 + Markdown 설명 + CI 검증 | 명세 기반 개발과 자동 검증의 균형이 좋다. |

## 결정 근거

- API 계약은 사람이 읽는 설명보다 기계 검증 가능한 형식으로 관리해야 한다.
- Markdown 문서는 업무 맥락과 예시를 설명하는 데 유리하므로 유지 가치가 있다.
- PR 체크리스트만으로는 누락을 막기 어렵기 때문에 CI 검증이 필요하다.
- OpenAPI 기반 TypeScript 타입 또는 client를 생성하면 프론트엔드와 백엔드 계약 불일치를 줄일 수 있다.
- FastAPI의 생성 OpenAPI와 원천 OpenAPI를 비교하면 구현 drift를 발견할 수 있다.

## 영향

- `openapi/openapi.yaml`을 새로 작성해야 한다.
- API 변경 PR에는 OpenAPI, Markdown 명세, 테스트케이스 변경이 함께 포함되어야 한다.
- CI에 Spectral lint와 API contract test를 추가해야 한다.
- FastAPI 구현 이후 `/openapi.json` export 및 diff 검증 스크립트를 추가해야 한다.
- 프론트엔드 타입 생성은 ADR-0030에 따라 `openapi-typescript`를 기준으로 구성한다.

## 후속 조치

- `docs/api-contract-sync-policy.md`를 API 변경 절차 기준으로 유지한다.
- `.github/pull_request_template.md`의 API 변경 체크리스트를 PR 리뷰 기준으로 사용한다.
- `.spectral.yaml`을 OpenAPI lint 기본 설정으로 사용한다.
- ADR-0062 기준 핵심 플로우 API부터 `openapi/openapi.yaml` 초안을 작성한다.
- FastAPI 구현 후 generated OpenAPI diff 스크립트와 CI workflow를 추가한다.

## 관련 문서

- `docs/api-contract-sync-policy.md`
- `docs/api-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0001-spec-driven-development.md`
- `docs/adr/ADR-0005-fastapi-backend-framework.md`
- `docs/adr/ADR-0062-openapi-initial-contract-scope-and-validation.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
