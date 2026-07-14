# API 계약 동기화 기준

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-07-13 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-07-13 | ADR-0026/0062/0064 기준 API 계약 동기화 및 검증 기준 정리 |

## 1. 문서 목적

본 문서는 `openapi/openapi.yaml`, `docs/api-specification.md`, `docs/screen-api-mapping.md`, `docs/test-cases.md` 간 동기화 기준을 정의한다.

API 계약 관리 원칙은 `docs/adr/ADR-0026-api-contract-management.md`를 따르고, 초기 OpenAPI 작성 범위와 단계별 검증 기준은 `docs/adr/ADR-0062-openapi-initial-contract-scope-and-validation.md`를 따른다. CI/CD Gate 적용 범위와 PR 차단 기준은 `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`를 따른다.

## 2. 문서별 역할

| 문서 | 역할 | 변경 기준 |
| --- | --- | --- |
| `openapi/openapi.yaml` | API 계약 원천 | API path, method, schema, enum, status code, required field 변경 시 필수 |
| `docs/api-specification.md` | 업무 설명과 예시 | API 목적, 권한, 예시, 업무 흐름 변경 시 필수 |
| `docs/screen-api-mapping.md` | 화면 연계 기준 | 화면 호출 API, 호출 시점, 화면 반영 항목 변경 시 필수 |
| `docs/test-cases.md` | 검증 기준 | API 정상/예외/권한/계약 테스트 변경 시 필수 |

## 3. 변경 유형별 필수 수정

| 변경 유형 | OpenAPI | API 명세서 | 화면-API 매핑표 | 테스트케이스 |
| --- | --- | --- | --- | --- |
| API 신규 추가 | 필수 | 필수 | 화면 사용 시 필수 | 필수 |
| API 삭제 | 필수 | 필수 | 해당 화면 있으면 필수 | 필수 |
| request/response 필드 변경 | 필수 | 예시/설명 있으면 필수 | 화면 표시 항목이면 필수 | 필수 |
| enum 변경 | 필수 | 코드표 있으면 필수 | 화면 옵션이면 필수 | 필수 |
| status code 변경 | 필수 | 오류 설명 있으면 필수 | 화면 오류 처리 영향 시 필수 | 필수 |
| 권한 변경 | 필수 | 필수 | 화면 접근 권한 영향 시 필수 | 권한 테스트 필수 |
| 설명만 보강 | 불필요 | 필수 | 필요 시 | 불필요 |

## 4. PR 체크 기준

API 변경 PR은 다음을 확인해야 한다.

- `openapi/openapi.yaml` 변경 여부를 확인했다.
- `docs/api-specification.md`의 설명과 예시를 확인했다.
- `docs/screen-api-mapping.md`의 화면 영향 범위를 확인했다.
- `docs/test-cases.md`의 계약/권한/예외 테스트를 확인했다.
- OpenAPI lint와 API contract test가 통과했다.
- FastAPI 구현 이후에는 generated `/openapi.json`과 `openapi/openapi.yaml` 차이를 확인했다.

## 5. 초기 OpenAPI 작성 범위

PoC 초기에는 전체 API를 한 번에 작성하지 않고 ADR-0062 기준 핵심 플로우 API부터 `openapi/openapi.yaml`에 작성한다.

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

보조 API는 구현 또는 화면 연동이 시작되는 시점에 OpenAPI에 추가한다. 구현되었거나 프론트엔드에서 호출하는 API를 OpenAPI 누락 상태로 두지 않는다.

## 6. CI 검증 기준

PoC 초기 CI는 ADR-0064 기준 PR 필수 Gate로 다음을 목표로 한다.

```bash
npx @stoplight/spectral-cli lint openapi/openapi.yaml
```

FastAPI 구현 이후에는 다음 검증을 추가한다.

```bash
# 예시: 실제 앱 경로와 실행 방식 확정 후 스크립트화
curl http://localhost:8000/openapi.json -o build/openapi.generated.json
python scripts/compare_openapi_contract.py openapi/openapi.yaml build/openapi.generated.json
pytest tests/api_contract
```

프론트엔드는 ADR-0030에 따라 React + Vite + TypeScript를 사용한다. API 계약 변경 시 `openapi-typescript`로 생성한 TypeScript 타입도 함께 갱신한다.

AI/OCR/RAG가 포함된 API 계약 테스트는 ADR-0044와 ADR-0064 기준으로 외부 엔진을 직접 호출하지 않고 Mock/Fixture 응답을 사용한다. 실제 OCR/RAG/LLM 품질 검증은 API 계약 테스트가 아니라 정기/수동 평가 파이프라인에서 수행한다.

오류 응답 계약 테스트는 ADR-0027의 `ErrorResponse` 구조와 ADR-0045의 오류 코드별 사용자 메시지 매핑을 함께 기준으로 삼는다.

```bash
npx openapi-typescript openapi/openapi.yaml -o frontend/src/generated/api-types.ts
git diff --exit-code frontend/src/generated/api-types.ts
```

## 7. 검증 도입 단계

| 단계 | 시점 | 필수 검증 |
| --- | --- | --- |
| 1 | `openapi/openapi.yaml` 초안 작성 | YAML parse, OpenAPI schema validation |
| 2 | 모든 API 계약 변경 PR | Spectral lint |
| 3 | 프론트엔드 API 연동 시작 | `openapi-typescript` 타입 생성 및 diff 확인 |
| 4 | 백엔드 endpoint 구현 후 | API contract test |
| 5 | FastAPI 앱 실행 가능 후 | generated `/openapi.json`과 원천 OpenAPI diff |

## 8. 충돌 처리

문서 간 내용이 충돌하면 다음 순서로 판단한다.

1. `openapi/openapi.yaml`
2. API contract test
3. `docs/api-specification.md`
4. `docs/screen-api-mapping.md`

단, 업무 의도가 불명확하면 문서를 임의로 맞추지 않고 요구사항 또는 ADR을 먼저 갱신한다.

## 9. 후속 작업

- `openapi/openapi.yaml` 초안 작성
- API contract test 도입
- FastAPI generated OpenAPI diff 스크립트 작성
- 프론트엔드 타입/client 생성 경로 확정
