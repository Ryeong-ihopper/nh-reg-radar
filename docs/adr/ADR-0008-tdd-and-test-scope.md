# ADR-0008: TDD 및 테스트 적용 범위

## 상태

Accepted

## 배경

본 프로젝트는 광고물 업로드, 문서 파싱/OCR, 기준자료 검색, AI 검토, 담당자 판정, 리포트 생성까지 여러 계층이 연결된다. 특히 파서와 AI 결과는 구현체 교체 가능성을 열어두어야 하므로, 개별 도구의 내부 동작보다 입력/출력 계약과 정규화 결과를 안정적으로 검증하는 테스트가 중요하다.

PoC 일정상 모든 기능을 엄격한 TDD로 개발하기는 어렵지만, 회귀가 발생하면 검토 결과 신뢰도와 문서 정합성에 직접 영향을 주는 영역은 자동 테스트를 완료 조건으로 둔다.

## 결정

핵심 도메인, 문서 Parser/OCR 어댑터, AI 결과 정규화, API 계약은 테스트 필수 범위로 정한다.

| 구분 | 테스트 방침 |
| --- | --- |
| 핵심 도메인 로직 | Rule 판정, 검토 상태 전이, 위험도/판정 통합 로직은 단위 테스트 필수 |
| Parser/OCR 어댑터 | 입력 파일에서 `NormalizedDocument`로 변환되는 계약 테스트 필수 |
| AI 결과 정규화 | LLM/RAG 원본 응답을 내부 스키마로 변환하는 로직은 fixture 기반 테스트 필수 |
| API 계약 | API 명세서와 FastAPI OpenAPI 스키마의 요청/응답 계약 테스트 필수 |
| DB 마이그레이션 | 핵심 테이블과 외래키, 상태값 제약은 마이그레이션 테스트 대상 |
| 프론트엔드 | 주요 화면의 API 연동 경로와 핵심 사용자 흐름 중심 테스트 |
| E2E | 광고물 등록 -> AI 검토 -> 담당자 판정 -> 리포트 생성의 대표 happy path 필수 |

AI 모델의 자연어 답변 자체를 모든 테스트에서 고정하지 않는다. 대신 모델 호출은 mock 또는 fixture로 분리하고, 정규화된 구조, 필수 필드, 근거 연결, 상태 처리 규칙을 검증한다.

## CI 실행 기준

CI/CD 단계별 차단 Gate와 정기/수동 평가 분리는 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)을 따른다.

| 실행 시점 | 필수 검증 |
| --- | --- |
| Pull Request | lint, type check, unit test, API 계약 테스트, 문서/OpenAPI/Compose config 검증 |
| main 병합 전 | PR 필수 검증 + 핵심 통합 테스트 |
| 정기/수동 실행 | 실제 OCR/RAG/LLM 연동 테스트, 샘플 데이터셋 평가 |
| 릴리스 후보 | Docker Compose 기반 smoke test, 대표 E2E, 마이그레이션 검증 |

LLM/OCR 등 비용과 시간이 큰 테스트는 PR 필수 검증에서 제외하고, ADR-0044 기준 Mock/Fixture 기반 테스트와 정기 평가 파이프라인으로 분리한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 전 기능 TDD | 품질은 높지만 PoC 속도와 일정 리스크가 크다. |
| 핵심 계약과 도메인 중심 테스트 | 품질과 개발 속도의 균형이 가장 좋다. |
| API happy path와 수동 검수 중심 | 빠르지만 파서/AI 정규화 회귀를 놓치기 쉽다. |
| PoC 기간 수동 검수만 수행 | 재현성과 변경 추적성이 낮아 명세 기반 개발 방식과 맞지 않는다. |

## 결정 근거

- 광고심의 결과는 설명 가능성과 재현성이 중요하다.
- AI 결과는 비결정적일 수 있으므로 원문 답변보다 구조화·정규화·근거 연결을 검증해야 한다.
- Parser/OCR 도구를 교체 가능하게 유지하려면 공통 출력 계약 테스트가 필요하다.
- API 명세 기반 개발을 유지하려면 OpenAPI와 문서의 계약 불일치를 빠르게 발견해야 한다.
- Docker Compose 기반 배포 전 smoke test를 두면 온프렘 이전 가능성에 대비하기 쉽다.

## 영향

- 구현 시 테스트 fixture와 샘플 데이터를 함께 관리해야 한다.
- Parser/OCR/LLM 어댑터는 테스트 가능한 인터페이스로 분리해야 한다.
- CI는 빠른 PR 검증과 느린 AI 통합 평가를 분리해야 한다.
- 테스트케이스 문서는 자동화 여부와 검증 레벨을 표시할 수 있도록 보완한다.

## 후속 조치

- `docs/test-cases.md`에 테스트 레벨과 자동화 우선순위를 반영한다.
- Parser/OCR 공통 출력 스키마인 `NormalizedDocument`는 ADR-0065 기준 v1 계약으로 정의한다.
- API 명세서와 OpenAPI 스키마 비교 방식을 구현 단계에서 확정한다.
- 샘플 데이터 기반 AI 평가셋과 golden fixture 범위는 ADR-0044 기준으로 정한다.
- PR 필수 검증과 정기 평가 파이프라인은 ADR-0064 기준으로 구분한다.

## 관련 문서

- `docs/test-cases.md`
- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/adr/ADR-0001-spec-driven-development.md`
- `docs/adr/ADR-0005-fastapi-backend-framework.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
