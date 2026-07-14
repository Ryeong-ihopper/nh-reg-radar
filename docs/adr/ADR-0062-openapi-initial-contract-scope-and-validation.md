# ADR-0062: OpenAPI 초기 계약 작성 범위 및 검증 단계 정책

## 상태

Accepted

## 배경

ADR-0026에서 API 계약의 원천은 `openapi/openapi.yaml`로 두고, `docs/api-specification.md`는 사람이 읽는 업무 설명과 예시 문서로 유지하기로 결정했다. 그러나 PoC 문서에는 이미 많은 API가 정의되어 있어 전체 API를 한 번에 OpenAPI로 작성하면 초기 작성 부담이 크고, 반대로 OpenAPI 작성을 미루면 프론트엔드/백엔드/테스트의 계약 불일치를 자동으로 잡기 어렵다.

현재 저장소에는 `.spectral.yaml`은 있으나 `openapi/openapi.yaml`은 아직 없다. 따라서 PoC 개발 착수 전에 초기 OpenAPI 작성 범위와 검증 단계를 확정해야 한다.

## 결정

OpenAPI 초기 계약은 **핵심 플로우 API부터 작성하고 점진 확장**한다.

| 항목 | 결정 |
| --- | --- |
| 계약 원천 | ADR-0026 기준 `openapi/openapi.yaml` |
| 초기 작성 방식 | 전체 API 일괄 작성이 아니라 핵심 플로우 API 우선 작성 |
| PoC 초기 필수 검증 | OpenAPI parse/schema validation, Spectral lint |
| 프론트엔드 구현 시작 시 | `openapi-typescript` 타입 생성 및 generated diff 확인 |
| 백엔드 구현 이후 | FastAPI generated `/openapi.json`과 원천 OpenAPI diff |
| API 변경 PR | OpenAPI, Markdown API 명세, 화면-API 매핑표, 테스트케이스 동시 갱신 |

## 초기 OpenAPI 작성 범위

초기 `openapi/openapi.yaml`은 다음 핵심 API부터 작성한다.

| 우선순위 | 영역 | 포함 범위 |
| --- | --- | --- |
| 1 | 공통 | 공통 Header, 인증 방식, 공통 오류 응답, 주요 enum |
| 2 | Auth/Common | 로그인, refresh, logout, me, 공통 코드 |
| 3 | 광고물 등록/파일 | 광고물 등록, 파일 업로드, 파일 메타데이터, 다운로드/미리보기 권한 |
| 4 | AI 검토 | AI 검토 요청, 진행 상태 조회, 재분석 요청 |
| 5 | 검토 결과 | 요약, 상세 항목, Annotation, 근거 매핑 |
| 6 | 기준자료 | 기준자료 목록/상세/등록/버전/검색 핵심 API |
| 7 | 리포트 | 리포트 생성, 상태 조회, 다운로드 |
| 8 | PoC 검증 | 검증 데이터셋, 담당자 판단, KPI 결과 조회 핵심 API |

보조 API는 핵심 플로우 구현 중 실제 화면 또는 백엔드 작업이 시작될 때 OpenAPI에 추가한다. API가 구현되거나 프론트엔드에서 호출되면 OpenAPI 누락 상태로 두지 않는다.

## 검증 단계

CI/CD에서 어떤 검증을 PR Gate로 차단할지는 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)을 따른다.

| 단계 | 시점 | 필수 여부 | 검증 |
| --- | --- | --- | --- |
| 1 | `openapi/openapi.yaml` 초안 작성 시 | 필수 | YAML parse 및 OpenAPI schema validation |
| 2 | 모든 API 계약 변경 PR | 필수 | Spectral lint |
| 3 | 프론트엔드 API 연동 시작 시 | 필수 | `openapi-typescript` 타입 생성 및 diff 확인 |
| 4 | 백엔드 endpoint 구현 후 | 필수 | API contract test |
| 5 | FastAPI 앱 실행 가능 후 | 필수 | generated `/openapi.json`과 원천 OpenAPI diff |
| 6 | 외부 AI/OCR/RAG 연동 API | PR 필수는 Mock/Fixture, 실제 엔진 검증은 정기/수동 평가 | ADR-0044 기준 |

## OpenAPI에 우선 포함할 공통 Schema

초기 OpenAPI에는 최소한 다음 공통 schema를 정의한다.

| Schema | 내용 |
| --- | --- |
| `ErrorResponse` | ADR-0027, ADR-0045 기준 오류 응답 구조 |
| `PageResponse` | 목록 API 공통 pagination 구조 |
| `UserContext` | 인증 사용자와 role/department scope |
| `AdvertisementSummary` | 광고물 목록/요약 공통 필드 |
| `ReviewStatusResponse` | `jobStatus`, `retryCount`, `failedReasonCode` 등 ADR-0059/0061 상태 필드 |
| `ReviewItem` | 검토 항목, 위험도, 판정, 근거 연결 |
| `Annotation` | ADR-0051/0052 기준 표시 모드, 위치 상태, 좌표/텍스트 offset |
| `EvidenceSummary` | ADR-0043 기준 근거 ID, rank, score, match source |
| `ReportSummary` | 리포트 생성 상태와 출력 형식 |

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 전체 API를 한 번에 OpenAPI로 작성 | 가장 완전하지만 초기 작성 부담이 크고 실제 구현 전 변경 비용이 큼 |
| B. 핵심 플로우 API부터 작성 후 점진 확장 | PoC 개발 속도와 계약 검증의 균형이 좋아 채택 |
| C. 백엔드 구현 후 FastAPI generated OpenAPI를 원천으로 전환 | 구현과는 잘 맞지만 명세 기반 개발 원칙이 약해져 기각 |
| D. Markdown API 명세를 당분간 원천으로 유지 | 빠르지만 ADR-0026과 충돌하고 자동 검증이 약해 기각 |

## 결정 근거

- PoC 초기에는 핵심 업무 흐름을 빠르게 구현해야 하므로 전체 API 일괄 작성은 부담이 크다.
- 핵심 API만이라도 OpenAPI 계약을 먼저 두면 프론트엔드 타입 생성, mock, API contract test를 시작할 수 있다.
- Markdown API 명세는 업무 설명에 강하지만 path/method/schema/enum/status code 자동 검증에는 한계가 있다.
- FastAPI generated OpenAPI는 구현 drift 검증에는 유용하지만, 구현 전에 계약을 합의하는 원천으로는 부적합하다.
- ADR-0030의 `openapi-typescript`, ADR-0027의 응답 표준, ADR-0045의 오류 메시지 정책과 연결된다.

## 영향

- `openapi/openapi.yaml` 초안은 핵심 플로우 API 중심으로 작성한다.
- API 변경 PR은 ADR-0026 기준 동기화 대상 문서를 함께 갱신해야 한다.
- 프론트엔드 API 타입 생성 파일은 OpenAPI 계약 변경 시 함께 갱신되어야 한다.
- 백엔드 구현 이후에는 generated OpenAPI diff 스크립트가 ADR-0064 기준 CI Gate 또는 수동 검증에 포함된다.
- 보조 API도 구현 또는 화면 연동이 시작되는 시점에는 OpenAPI에 추가해야 한다.

## 후속 조치

- `openapi/openapi.yaml`의 초기 skeleton을 작성한다.
- `.spectral.yaml` 기준 lint 명령을 문서 정합성 검사 또는 CI에 연결한다.
- `openapi-typescript` 생성 경로를 실제 프론트엔드 디렉터리 구조에 맞게 확정한다.
- FastAPI 앱 구현 후 `/openapi.json` export 및 diff 스크립트를 추가한다.
- 핵심 API별 contract test fixture를 ADR-0044 기준으로 작성한다.

## 관련 문서

- `docs/api-contract-sync-policy.md`
- `docs/api-specification.md`
- `docs/screen-api-mapping.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0026-api-contract-management.md`
- `docs/adr/ADR-0027-api-response-standard.md`
- `docs/adr/ADR-0030-frontend-stack.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0045-user-error-message-policy.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
