# ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책

## 상태

Accepted

## 배경

ADR-0008은 핵심 도메인, Parser/OCR 어댑터, AI 결과 정규화, API 계약을 테스트 필수 범위로 정했다. ADR-0044는 AI/OCR/RAG 실제 엔진 검증을 Mock/Fixture 기반 PR 테스트와 분리하기로 했다. ADR-0034, ADR-0062, ADR-0063은 각각 문서 정합성 검사, OpenAPI 검증, Docker Compose config 검증을 CI에 연결해야 한다고 정의한다.

PoC 개발을 시작하면 PR마다 어떤 검증을 merge 차단 Gate로 둘지, 어떤 검증을 정기/수동 평가로 둘지 명확해야 한다. 실제 OCR/RAG/LLM 검증을 모든 PR에서 실행하면 비용, 시간, 비결정성 때문에 CI가 불안정해질 수 있고, 반대로 문서/API/Compose 검증을 느슨하게 두면 명세 기반 개발 원칙이 약해진다.

## 결정

CI/CD 검증은 **PR 필수 Gate와 정기/수동 평가를 명확히 분리**한다.

| 구분 | 성격 | 실패 처리 | 포함 검증 |
| --- | --- | --- | --- |
| PR 필수 Gate | 빠른 차단 검증 | merge 차단 | 문서 정합성, lint/format, unit, Mock/Fixture 기반 P0, OpenAPI lint, API contract, Compose config |
| main 병합 전 | 강화 차단 검증 | merge 차단 | PR 필수 Gate + 핵심 통합 테스트 |
| 정기/수동 평가 | 품질 관찰 및 회귀 분석 | 리포트 작성, 필요 시 결함 등록 | 실제 OCR/RAG/LLM, 승인 샘플 기반 평가, KPI 측정 |
| release 후보 | 배포 차단 검증 | 배포 차단 | Docker Compose smoke, migration 검증, 대표 E2E |

외부 AI/OCR/RAG 실제 호출은 PR 필수 Gate에서 기본 금지한다. PR에서는 Mock adapter, synthetic fixture, golden output을 사용해 시스템의 저장, 조회, 상태 전이, 오류 처리, 리포트 반영을 검증한다.

## PR 필수 Gate

PR 필수 Gate는 빠르고 재현 가능해야 한다.

| Gate | 기준 |
| --- | --- |
| 문서 정합성 | `scripts/check-doc-consistency.sh` |
| Python lint | `ruff check .` |
| Python format | `ruff format --check .` |
| Unit/Mock 테스트 | `pytest -m "not external_ai and not slow"` |
| API 계약 | OpenAPI parse/schema validation, Spectral lint, API contract test |
| OpenAPI 타입 | 프론트엔드 API 연동 시작 후 `openapi-typescript` generated diff 확인 |
| Compose config | `compose.yml` + `compose.dev.yml`, `compose.yml` + `compose.prod.yml` config 검증 |
| Secret 노출 방지 | secret, token, presigned URL, 고객사 원문이 로그/fixture에 포함되지 않도록 검사 가능한 범위에서 확인 |

초기 PoC에서 프론트엔드, 백엔드, OpenAPI skeleton이 아직 없는 경우 해당 Gate는 파일이 존재하는 시점부터 활성화한다. 단, 활성화 시점 이후에는 실패를 차단 기준으로 본다.

## 테스트 Marker 기준

`pytest` marker는 다음 기준으로 표준화한다.

| Marker | 의미 | PR 필수 Gate |
| --- | --- | --- |
| `unit` | 순수 함수, 도메인 로직, 정규화 로직 | 포함 |
| `contract` | API/OpenAPI/adapter 입출력 계약 | 포함 |
| `integration` | PostgreSQL, Redis, MinIO 등 내부 인프라 연동 | main 병합 전 또는 release 후보 중심 |
| `external_ai` | 실제 OCR/RAG/LLM 또는 외부 AI API 호출 | 제외 |
| `slow` | 실행 시간이 긴 평가/대량 샘플 테스트 | 제외 |
| `e2e` | 대표 사용자 흐름 | release 후보 중심 |

기본 PR 테스트 명령은 다음을 기준으로 한다.

```bash
pytest -m "not external_ai and not slow"
```

실제 엔진 평가는 다음처럼 별도 실행한다.

```bash
pytest -m "external_ai"
pytest -m "slow or e2e"
```

## 정기/수동 평가

정기/수동 평가는 실제 품질을 확인하기 위한 별도 경로다.

| 평가 | 기준 |
| --- | --- |
| OCR/Parser | 승인 샘플 또는 synthetic 샘플로 추출 품질, 텍스트 블록, offset, 좌표 매핑 확인 |
| RAG | Qdrant/OpenSearch 실제 엔진으로 Top-K 근거 적중, 근거 부족, 검색 장애 처리 확인 |
| LLM | 샘플 데이터셋으로 판정 구조, 위험도, 근거 연결, 추천 문구 품질 확인 |
| KPI | ADR-0023, ADR-0024 기준 분모/분자와 제외 기준 확인 |
| 회귀 승격 | 실제 엔진 평가에서 반복 발견된 구조적 회귀는 Mock/Fixture 회귀 테스트로 승격 |

정기/수동 평가 실패는 즉시 모든 PR을 차단하지 않는다. 다만 PoC 시연, release 후보, 고객사 검증 전에 해결 여부를 판단하고 결함 또는 개선 과제로 기록한다.

## Release 후보 Gate

release 후보는 `prod(main)` 시연 환경에 반영하기 전 다음을 확인한다.

| Gate | 기준 |
| --- | --- |
| Compose smoke | ADR-0063 기준 `compose.yml` + `compose.prod.yml` 조합 기동 |
| Backend health | health check API 정상 |
| Frontend smoke | 핵심 화면 접근 가능 |
| Migration | upgrade 적용 가능, 필요 시 백업 선행 |
| 대표 E2E | 광고물 등록 -> AI 검토 요청 -> 결과 조회 -> 담당자 판단 -> 리포트 생성 |
| 감사 로그 | 주요 변경/분석/다운로드/리포트 생성 로그 기록 |

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 최소 CI만 적용 | 빠르지만 문서/API/Compose drift와 계약 불일치를 놓치기 쉬워 기각 |
| B. PR 필수 Gate와 정기/수동 평가 분리 | PoC 속도와 품질 검증의 균형이 좋아 채택 |
| C. 실제 OCR/RAG/LLM까지 PR 필수 실행 | 현실 검증은 강하지만 느리고 불안정하며 비용 부담이 커 기각 |
| D. CI는 느슨하게 두고 배포 전 수동 검증 중심 | 초기 편의는 있으나 회귀 발견이 늦고 명세 기반 개발과 맞지 않아 기각 |

## 결정 근거

- PR Gate는 빠르고 결정적이어야 개발 속도를 유지할 수 있다.
- 실제 AI/OCR/RAG 평가는 품질 검증에 필요하지만 비용, 시간, 비결정성 때문에 PR 차단 기준으로는 부적합하다.
- 문서 정합성, OpenAPI, Compose config는 명세 기반 개발과 온프렘 이전 가능성을 지키기 위한 기본 Gate다.
- 실제 엔진 평가에서 발견한 구조적 회귀를 Mock/Fixture로 승격하면 품질 학습이 자동화 테스트로 축적된다.
- release 후보는 고객사 시연과 PoC 검증 기준 환경에 반영되므로 smoke/E2E/migration 검증을 차단 기준으로 둔다.

## 영향

- CI workflow는 빠른 PR Gate와 느린 정기/수동 평가 workflow를 분리한다.
- 테스트 코드에는 `unit`, `contract`, `integration`, `external_ai`, `slow`, `e2e` marker를 사용한다.
- 실제 AI/OCR/RAG 호출이 필요한 테스트는 PR 필수 Gate에서 제외한다.
- 문서 변경 PR은 `scripts/check-doc-consistency.sh`를 통과해야 한다.
- OpenAPI와 Compose 파일이 추가된 이후에는 해당 config/lint 검증이 PR Gate에 포함된다.

## 후속 조치

- `.github/workflows/ci.yml`에 PR 필수 Gate를 작성한다.
- 정기/수동 평가 workflow를 별도 파일로 분리한다.
- `pytest.ini` 또는 `pyproject.toml`에 marker 정의를 추가한다.
- OpenAPI skeleton 작성 후 Spectral lint와 타입 생성 diff를 연결한다.
- Compose 파일 작성 후 dev/prod config 검증을 CI에 연결한다.

## 관련 문서

- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/api-contract-sync-policy.md`
- `docs/adr/ADR-0008-tdd-and-test-scope.md`
- `docs/adr/ADR-0034-codex-claude-skills-standardization.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0062-openapi-initial-contract-scope-and-validation.md`
- `docs/adr/ADR-0063-compose-base-dev-prod-override-policy.md`
