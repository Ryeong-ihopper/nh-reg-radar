# ADR-0044: AI/OCR/RAG Mock 및 Fixture 테스트 정책

## 상태

Accepted

## 배경

ADR-0008은 핵심 도메인, Parser/OCR 어댑터, AI 결과 정규화, API 계약을 테스트 필수 범위로 정했다. 그러나 실제 OCR, RAG 검색, LLM 판단을 언제 Mock으로 대체하고, 언제 실제 엔진으로 검증할지에 대한 세부 기준은 남아 있었다.

AI/OCR/RAG 통합 테스트를 모든 PR에서 실제 엔진으로 실행하면 비용, 속도, 외부 서비스 상태, 모델 응답 변동 때문에 CI가 불안정해진다. 반대로 Mock 테스트만 사용하면 실제 OCR 판독 품질, RAG 근거 검색 품질, LLM 판단 품질을 놓칠 수 있다.

따라서 PoC 단계에서는 빠른 회귀 검증과 실제 품질 검증을 분리한다.

## 결정

테스트는 계층별로 Mock, Fixture, 실제 엔진 검증을 분리한다.

| 테스트 구분 | 정책 |
| --- | --- |
| PR 필수 테스트 | AI/OCR/RAG/LLM 외부 호출은 Mock 또는 Fixture로 대체 |
| Unit 테스트 | 순수 함수, 도메인 로직, 위험도 산정, 상태 전이 검증 |
| API 계약 테스트 | 고정 요청/응답 Fixture로 OpenAPI 및 API 응답 구조 검증 |
| 통합 테스트 | PostgreSQL, Redis, Object Storage 등 내부 인프라는 가능하면 실제 컨테이너 사용 |
| OCR/문서 파싱 품질 테스트 | 샘플 파일 기반 정기 또는 수동 테스트 |
| RAG 검색 품질 테스트 | Qdrant/OpenSearch 실제 엔진 기반 정기 또는 수동 테스트 |
| LLM 판단 품질 테스트 | 샘플 데이터셋 기반 별도 평가 실행 |
| PoC KPI 평가 | 실제 또는 승인된 샘플 데이터셋으로 별도 실행 |

Mock 테스트는 AI 품질을 검증하는 테스트가 아니다. AI/OCR/RAG가 특정 구조화 결과를 반환했을 때 시스템이 결과를 올바르게 저장, 조회, 표시, 리포트 반영하는지 검증하는 테스트이다. OCR/Parser fixture는 ADR-0065의 `NormalizedDocument` v1 구조를 기준으로 작성한다.

## Mock 대상과 검증 목적

| 대상 | Mock 입력/출력 | 검증 목적 |
| --- | --- | --- |
| OCR/Parser | `NormalizedDocument`, text blocks, layout blocks, coordinates | OCR 결과 저장, 좌표 변환, Annotation 생성 |
| RAG Search | evidence list, chunk id, rank, relevance score, match source | 근거 매핑 저장, 근거 표시 개수 제한, 근거 부족 처리 |
| LLM 판단 | result status, risk level, reason, recommendation | 검토 항목 저장, 위험도 요약, 리포트 반영 |
| Queue/Worker | job id, step status, progress, failure reason, retry count, heartbeat | 비동기 상태 전이, retry backoff, stale worker 복구, 최종 실패 처리 |
| 외부 AI API | 성공/실패/timeout 응답 | 오류 처리, fallback, retry 판정, audit log, 사용자 메시지 |

## Fixture 관리 기준

Fixture는 테스트 재현성을 위해 Git으로 관리한다. 단, 고객사 승인 샘플과 synthetic fixture를 분리한다.

```text
tests/fixtures/
  synthetic/
    advertisements/
    ocr/
    rag/
    llm/
    reports/
  approved-samples/
    README.md
```

| Fixture 유형 | 관리 기준 |
| --- | --- |
| synthetic fixture | 개발자가 만든 비민감 샘플. PR/CI에서 자유롭게 사용 |
| approved sample fixture | 고객사 승인 샘플. ADR-0002의 외부 AI 입력 정책과 저장 정책 준수 |
| golden output | Mock OCR/RAG/LLM의 기대 출력. 변경 시 테스트 기대값과 함께 리뷰 |
| error fixture | OCR 실패, RAG 근거 부족, LLM timeout, 파일 손상, transient timeout, retry exhausted, stale worker 등 예외 시나리오 |
| KPI fixture | PoC KPI 산식 검증용 정답 데이터. 평가 제외 기준과 함께 관리 |

고객사 자료, 개인정보, API key, prompt 전문, presigned URL 전체값은 fixture에 저장하지 않는다.

## CI 및 실행 기준

CI/CD 단계별 Gate와 pytest marker 운영 기준은 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)을 따른다.

| 실행 시점 | 실행 테스트 | 실패 처리 |
| --- | --- | --- |
| Pull Request | lint, type check, unit, API contract, Mock 기반 P0 테스트 | 실패 시 merge 차단 |
| main 병합 전 | PR 필수 테스트 + 핵심 통합 테스트 | 실패 시 merge 차단 |
| 정기 실행 | 실제 OCR/RAG/LLM 연동 테스트, 샘플 데이터셋 평가 | 결과 리포트 및 회귀 분석 |
| 수동 검증 | 고객사 승인 샘플 기반 PoC 시나리오 | 시연/평가 전 확인 |
| 릴리스 후보 | Docker Compose smoke, 대표 E2E, migration 검증 | 배포 전 차단 기준 |

실제 AI/OCR/RAG 평가는 비용과 시간이 크고 결과가 변동될 수 있으므로 PR 필수 검증에는 포함하지 않는다. 단, 실제 엔진 평가에서 구조적 회귀가 반복되면 Mock fixture 또는 deterministic regression case로 승격한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 모든 테스트에서 실제 AI/OCR/RAG 사용 | 현실 검증은 좋지만 CI가 느리고 불안정하다. |
| CI는 전부 Mock, 수동 검증만 실제 엔진 사용 | 빠르지만 실제 품질 회귀를 늦게 발견할 수 있다. |
| 계층별로 Mock/Fixture/실제 엔진 검증 분리 | 개발 속도와 품질 검증의 균형이 가장 좋다. |
| OCR/RAG는 실제, LLM만 Mock | 검색/파싱 품질은 잡지만 PR CI 부담이 커진다. |
| 개발자가 임의 선택 | 테스트 결과의 일관성과 신뢰도가 낮아진다. |

## 결정 근거

- AI와 OCR 결과는 비용, 시간, 비결정성 문제가 있어 PR 필수 검증에 부적합하다.
- API, DB, 화면, 리포트 연결은 Mock 결과만으로도 안정적으로 검증할 수 있다.
- 실제 OCR/RAG/LLM 품질은 PoC KPI와 샘플 데이터셋 평가에서 별도로 검증해야 한다.
- Fixture를 Git에서 관리하면 회귀 테스트와 문서 기반 개발의 재현성이 높아진다.
- 고객사 승인 샘플과 synthetic fixture를 분리해야 보안 정책과 개발 편의성을 함께 만족할 수 있다.

## 영향

- AI/OCR/RAG Adapter는 Mock 구현과 실제 구현을 교체할 수 있는 인터페이스를 가져야 한다.
- PR CI는 Mock 기반 P0 테스트를 빠르게 실행한다.
- 실제 엔진 테스트는 정기/수동 파이프라인 또는 공용 개발 VM에서 실행한다.
- 테스트케이스 문서는 Mock 검증 대상과 실제 엔진 검증 대상을 구분한다.
- Fixture 변경은 테스트 기대값 변경으로 간주해 리뷰 대상에 포함한다.

## 후속 조치

- 백엔드 scaffold 작성 시 `tests/fixtures` 구조와 mock adapter 패턴을 반영한다.
- CI 구성 시 ADR-0064 기준 `pytest -m "not external_ai and not slow"`를 PR 필수 Gate로 사용한다.
- 실제 OCR/RAG/LLM 평가 결과를 PoC 결과보고서 또는 평가 로그로 남긴다.
- 고객사 승인 샘플 fixture의 저장 위치와 접근 권한은 보안 정책에 맞춰 재확인한다.

## 관련 문서

- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/api-contract-sync-policy.md`
- `docs/adr/ADR-0008-tdd-and-test-scope.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
- `docs/adr/ADR-0014-pluggable-document-parser-ocr.md`
- `docs/adr/ADR-0035-redis-queue-postgresql-job-state.md`
- `docs/adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
- `docs/adr/ADR-0065-normalized-document-schema-and-adapter-contract.md`
