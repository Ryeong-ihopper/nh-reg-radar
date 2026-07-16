# nh-ad-compliance

## 프로젝트 개요

NH 농협은행 금융상품 광고물의 사전 검토 업무를 보조하기 위한 AI 기반 광고심의 적정성 검토 에이전트 프로젝트입니다. 광고 이미지, 문서, 문구를 입력받아 금융광고 규정 준수 여부를 검토하고, 위반 가능성이 있는 표현과 필수 문구 누락 여부를 근거와 함께 확인하는 것을 목표로 합니다.

이 저장소의 `docs/` 경로에는 요구사항, 기능, 화면, API, DB, 테스트, 프로젝트 규칙 문서가 정리되어 있습니다. 사람과 AI 모두 작업을 시작하기 전에 아래 문서 역할을 먼저 확인하고, 변경하려는 내용과 가장 가까운 문서를 기준 문서로 삼아야 합니다.

개발 관련 명세 문서는 Git으로 관리되는 `docs/`를 Source of Truth로 사용합니다. Notion은 칸반, 일정, 회의록과 읽기용 공유본으로 사용하며, 구현 중 명세가 바뀌면 같은 작업 단위에서 `docs/` 문서를 함께 갱신합니다. `main`의 게시 대상 Markdown 변경은 ADR-0077에 따라 기존 Notion page ID를 유지하는 단방향 자동 동기화로 공유본에 반영합니다.

## 현재 구현 및 운영 상태 (2026-07-15)

M0~M8의 provider-free thin slice는 저장소의 실제 backend/worker/frontend 경로와 결정적 fixture를 기준으로 구현·검증되었습니다. 실행 진입점은 `apps/backend/src/nh_ad_backend/main.py`, `apps/worker/src/nh_ad_worker/main.py`, `apps/frontend/src/App.tsx`이며, API 호출은 `apps/frontend/src/api/client.ts`와 생성 계약 `apps/frontend/src/api/generated/openapi.ts`를 사용합니다. 원천 API 계약은 OpenAPI `0.8.0`입니다.

| 구분 | 현재 기준 |
| --- | --- |
| Provider-free 자동 Gate | `.github/workflows/release-readiness.yml`, `governance/goal-manifests/G009-m8-release.json`, 고정 fixture 기반 E2E/release 회귀 |
| 실제 외부 AI 수동 평가 | `.github/workflows/external-ai-evaluation.yml`의 승인된 `workflow_dispatch`; credential과 `external_ai` marker가 필요한 별도 lane |
| Production recovery | `bash scripts/release-smoke.sh --env-file .env.prod.example --fresh-project --with-restart-and-outages`; G011 반복 bootstrap을 먼저 검증 |
| 문서·일정 동기화 | [기능명세서](docs/functional-specification.md), [테스트케이스](docs/test-cases.md), [프로젝트 규칙](docs/project-rules.md), [개발 일정 및 Kanban](docs/development-schedule-and-notion-kanban.md) |

Provider-free 성공은 실제 OCR/RAG/LLM provider 품질, 고객사 검증, 시연 환경 배포, P0/P1 전체 합계 또는 Critical 결함 0건을 대신 증명하지 않습니다. 해당 항목은 별도 증거가 생길 때까지 일정/Kanban에서 `Backlog` 또는 `Blocked`로 유지합니다.

## 로컬 개발 환경 빠른 시작

처음 저장소를 받은 개발자는 아래 순서대로 실행하면 provider-free 전체 스택을 로컬에 띄울 수 있습니다. 이 경로는 Docker Compose로 frontend, backend, worker, PostgreSQL, Redis, MinIO, Qdrant, OpenSearch를 실행하고 DB migration과 synthetic dev seed까지 적용합니다. 실제 LLM/OCR/RAG API key는 필요하지 않습니다.

### 1. 사전 요구사항

| 도구 | 용도 | 확인 명령 |
| --- | --- | --- |
| Git | 저장소 clone 및 협업 | `git --version` |
| Python 3.12 | 온보딩·거버넌스 스크립트 | `python3 --version` |
| Docker Engine + Compose v2 | 전체 로컬 스택 | `docker version`, `docker compose version` |
| `uv` | Python 의존성·품질 검사. 서비스 기동 자체에는 선택 | `uv --version` |
| Node.js 22 + npm | OpenAPI·frontend 품질 검사. 서비스 기동 자체에는 선택 | `node --version`, `npm --version` |

Docker에는 전체 스택을 실행할 수 있는 충분한 메모리와 디스크를 할당해야 합니다. 특히 OpenSearch가 시작되지 않는 Linux 환경은 [문제 해결](#문제-해결)의 `vm.max_map_count` 항목을 확인합니다.

### 2. 저장소 clone과 개발 도구 설정

```bash
git clone https://github.com/bhjeon-cginside/nh-ad-compliance.git
cd nh-ad-compliance
scripts/setup-dev-tools.sh
```

이 스크립트는 프로젝트 Claude/Codex Skills adapter를 저장소 내부의 `.agents/skills`, `.claude/skills`에 설치하고, Git pre-commit/pre-push hook을 활성화하며, 거버넌스 단위 테스트와 문서 정합성 검사를 실행합니다. `skills/`가 사람이 수정하는 유일한 원본이며 사용자 홈에는 설치하지 않습니다. 상세 기준은 [ADR-0075](docs/adr/ADR-0075-project-scoped-skills-distribution.md)를 따릅니다.

### 3. dev 환경 파일 생성

```bash
cp .env.dev.example .env.dev
```

`.env.dev`는 Git에 포함되지 않습니다. 예제의 비밀번호와 secret은 개인 로컬 개발 전용이며 공유 VM이나 운영 환경에서 재사용하지 않습니다. 포트를 변경하면 `FRONTEND_PORT`/`BACKEND_PORT`와 함께 `CORS_ALLOWED_ORIGINS`/`VITE_API_BASE_URL`도 같은 주소로 맞춥니다.

### 4. 전체 스택 초기화 및 실행

```bash
scripts/local-dev.sh up
```

최초 실행은 이미지를 내려받고 빌드하므로 시간이 걸릴 수 있습니다. 스크립트는 다음 순서를 자동으로 수행하며 재실행해도 같은 migration과 seed를 안전하게 적용합니다.

1. Compose 설정과 dev 환경을 검증합니다.
2. PostgreSQL 역할/bootstrap과 database health를 확인합니다.
3. migration identity로 Alembic `head`를 적용합니다.
4. app identity로 공통 코드와 synthetic dev 사용자만 seed합니다.
5. 전체 서비스를 빌드하고 health/readiness 완료까지 기다립니다.

기본 synthetic 로그인 계정은 다음과 같습니다.

| 역할 | 이메일 | 비밀번호 |
| --- | --- | --- |
| 상품부서 사용자 | `product@example.invalid` | `LocalDevPassword!42` |
| 준법감시 사용자 | `compliance@example.invalid` | `LocalDevPassword!42` |

개인 로컬 비밀번호를 바꾸려면 시작 시에만 다음처럼 전달합니다. 평문 비밀번호는 DB에 저장되지 않으며 scrypt hash만 dev seed에 전달됩니다.

```bash
NH_LOCAL_DEV_PASSWORD='다른-로컬-비밀번호-10자-이상' scripts/local-dev.sh up
```

### 5. 접속 및 정상 동작 확인

| 대상 | 기본 주소 |
| --- | --- |
| 웹 화면 | <http://localhost:5173> |
| Backend health | <http://localhost:8000/health> |
| Backend OpenAPI | <http://localhost:8000/openapi.json> |
| Worker readiness | <http://localhost:8001/ready> |
| MinIO console | <http://localhost:9001> |

브라우저는 CORS/refresh-cookie 기준과 일치하도록 `127.0.0.1` 대신 위 `localhost` 주소를 사용합니다. 터미널에서는 다음 명령으로 기본 상태를 확인합니다.

```bash
scripts/local-dev.sh status
curl --fail http://localhost:8000/health
curl --fail http://localhost:8001/ready
```

### 6. 로그, 중지, 완전 초기화

```bash
# 전체 또는 특정 서비스 로그
scripts/local-dev.sh logs
scripts/local-dev.sh logs backend worker

# 컨테이너만 중지하고 로컬 데이터 volume은 보존
scripts/local-dev.sh down

# 컨테이너와 로컬 volume을 삭제한 뒤 빈 DB부터 다시 기동
scripts/local-dev.sh reset
```

`reset`은 해당 `.env.dev`의 `COMPOSE_PROJECT_NAME`에 속한 PostgreSQL, MinIO, Redis, Qdrant, OpenSearch 로컬 데이터를 삭제합니다. 공유 프로젝트 이름을 사용하지 않습니다.

### 문제 해결

- **포트가 이미 사용 중임**: `.env.dev`의 `FRONTEND_PORT`, `BACKEND_PORT` 등 충돌 포트를 변경합니다. frontend/backend 포트를 바꿀 때는 `CORS_ALLOWED_ORIGINS`와 `VITE_API_BASE_URL`도 함께 변경합니다.
- **DB/DSN 일치 오류**: `POSTGRES_DB`를 변경했다면 `NH_DB_RUNTIME_URL`과 `NH_DB_MIGRATION_URL` 마지막 database 이름도 동일하게 변경합니다.
- **OpenSearch가 기동하지 않음**: Linux host에서 `vm.max_map_count`가 낮다면 `sudo sysctl -w vm.max_map_count=262144` 적용 후 다시 실행합니다.
- **서비스가 unhealthy임**: `scripts/local-dev.sh status`와 `scripts/local-dev.sh logs <service>`로 원인을 확인합니다.
- **DB schema 또는 seed를 처음부터 재현해야 함**: `scripts/local-dev.sh reset`을 실행합니다.
- **외부 AI 기능을 기대했으나 동작하지 않음**: 기본 로컬 경로는 고정 fixture와 provider-free adapter만 사용합니다. 실제 외부 엔진 평가는 별도의 승인된 수동 workflow와 credential이 필요합니다.

## 개발 도구 및 문서 거버넌스

PoC의 문서 거버넌스는 AI 도구별 lifecycle hook을 필수 설치하지 않습니다. `AGENTS.md`, `CLAUDE.md`, Skills는 작업 지침으로 사용하고, Git pre-commit/pre-push와 CI를 공통 강제 계층으로 사용합니다. 상세 기준은 [ADR-0076](docs/adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md)을 따릅니다.

개발 중에는 다음 명령으로 변경 영향과 정합성을 직접 확인할 수 있습니다.

```bash
python3 -m scripts.doc_guard impact --scope working
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
```

정책 설정과 문서 템플릿은 [문서 거버넌스 가이드](governance/README.md)를 기준으로 사용합니다.

로컬에서 CI와 가까운 품질 검사를 직접 실행하려면 다음 의존성을 설치한 뒤 검사합니다.

```bash
uv sync --all-packages --dev
npm ci --ignore-scripts
npm --prefix apps/frontend ci

uv run ruff check .
uv run mypy
uv run python -m pytest -m "not external_ai and not slow"
npm run openapi:check
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend run test
npm --prefix apps/frontend run build
```

## 문서 참조 가이드

| 문서 | 주요 내용 | 사람이 볼 때 | AI가 볼 때 |
| --- | --- | --- | --- |
| [요구사항 정의서](docs/requirements-definition.md) | 프로젝트 목적, 적용 범위, 사용자, 업무/기능/데이터/비기능 요구사항, 수용 기준 | 무엇을 만들어야 하는지 확인 | 요구사항 변경, 기능 우선순위 판단, 누락 요구사항 검토의 기준 |
| [기능명세서](docs/functional-specification.md) | 화면별 기능, 입력값, 처리 규칙, 출력값, 예외 처리, 권한, 수용 기준 | 기능 동작 방식을 상세 확인 | 구현 단위, 상태 전이, 예외 처리, 테스트 조건 도출의 기준 |
| [화면설계서](docs/screen-specification.md) | 메뉴 구조, 공통 화면 구성, 화면별 UI 구성, 버튼, 이동 흐름, 팝업, 메시지 | 사용자가 보는 화면과 흐름 확인 | 프론트엔드 화면/컴포넌트/라우팅 구현 기준 |
| [화면-API 매핑표](docs/screen-api-mapping.md) | 화면별 호출 API, 호출 시점, 요청/응답값, 사용자 액션별 API 흐름 | 화면과 백엔드 연결 방식 확인 | 프론트엔드-백엔드 연동, API 호출 누락 검토 기준 |
| [API 명세서](docs/api-specification.md) | API 설계 원칙, 공통 규격, 엔드포인트, 요청/응답 모델, 호출 흐름 | 외부/내부 연동 규격 확인 | 백엔드 라우터, DTO, 클라이언트 타입, API 테스트 작성 기준 |
| [API 계약 동기화 기준](docs/api-contract-sync-policy.md) | OpenAPI, API 명세, 구현, 생성 타입 간 원천과 동기화 절차 | API 계약 변경 순서와 검증 기준 확인 | 계약 변경 시 함께 수정할 파일과 CI Gate 판단 기준 |
| [DB 명세서](docs/database-specification.md) | ERD 개요, 테이블, 인덱스, 보관 정책, Qdrant/OpenSearch 설계 | 저장 데이터와 관계 확인 | 스키마, 마이그레이션, 쿼리, 검색 저장소 구현 기준 |
| [테스트케이스](docs/test-cases.md) | 기능별 정상/예외/권한/비기능/E2E 테스트, 결함 분류, 완료 기준 | 검수 기준과 테스트 범위 확인 | 단위/통합/E2E 테스트 케이스 생성과 회귀 검증 기준 |
| [프로젝트 규칙](docs/project-rules.md) | 개발 방식, AI 활용 기준, 저장소 구성, 문서 관리, TDD, CI/CD, 브랜치/PR, ADR | 팀 개발 규칙과 운영 기준 확인 | 코드 작성 방식, 문서 변경 방식, AI 사용 제한, 품질 기준 준수 |
| [의사결정 필요사항](docs/adr-candidates.md) | ADR 관리 기준, 개발/AI/프론트엔드/백엔드/DB/RAG/인프라/보안 관련 미결정 항목 | 아직 결정되지 않은 항목 확인 | 구현 전 의사결정 필요 여부와 ADR 후보 식별 |
| [개발 일정 및 Notion 칸반 보드 구성안](docs/development-schedule-and-notion-kanban.md) | 개발 로드맵, 스프린트, 칸반 속성, Epic, 마일스톤, 리스크 | 일정과 작업 관리 방식 확인 | 작업 분해, 우선순위, 마일스톤 기반 진행 계획 수립 |
| [참조 레포지토리](docs/reference-repositories.md) | 참고할 외부/내부 레포지토리 목록 | 유사 구현이나 참고 자료 확인 | 구현 패턴, 기술 선택, 샘플 구조 탐색의 출발점 |
| [PoC KPI 산식 기준표](docs/poc-kpi-formulas.md) | KPI 분모·분자, 집계 단위, 반올림 기준 | PoC 평가 결과 산정 방식 확인 | 평가 쿼리와 집계 테스트의 공식 산식 기준 |
| [PoC 평가 제외 기준표](docs/poc-evaluation-exclusion-criteria.md) | OCR 판독 불가 등 평가 제외 사유와 승인 기준 | 평가 제외 여부와 근거 확인 | KPI 분모 제외 로직과 감사 기록 검증 기준 |
| [위험도 산정 기준표](docs/risk-assessment-criteria.md) | 위험도 등급, 점수, 사유 코드와 판정 우선순위 | 검토 결과의 위험도 판단 기준 확인 | Rule/RAG/LLM 결과를 최종 위험도로 변환하는 기준 |

## 작업 목적별 우선 참조 순서

| 작업 | 우선 확인 문서 |
| --- | --- |
| 신규 기능 정의 | 요구사항 정의서 -> 기능명세서 -> 테스트케이스 |
| 화면 구현/수정 | 화면설계서 -> 화면-API 매핑표 -> 기능명세서 |
| API 구현/수정 | API 명세서 -> 화면-API 매핑표 -> DB 명세서 -> 테스트케이스 |
| DB/검색 구조 변경 | DB 명세서 -> API 명세서 -> 의사결정 필요사항 |
| AI 검토 로직/RAG 구현 | 요구사항 정의서 -> 기능명세서 -> DB 명세서 -> 테스트케이스 |
| 테스트 작성/검수 | 테스트케이스 -> 기능명세서 -> API 명세서 |
| 개발 방식/품질 기준 확인 | 프로젝트 규칙 -> 의사결정 필요사항 |
| 일정/작업 분해 | 개발 일정 및 Notion 칸반 보드 구성안 -> 요구사항 정의서 |

활성 Markdown 문서의 파일명은 영문 kebab-case를 사용합니다. 문서 화면에 표시되는 한글 제목과 파일명을 분리하고, 파일 경로를 바꾸면 저장소 전체의 링크와 자동화 설정을 같은 변경에서 갱신합니다.

## 원본 자료

`docs/규정 및 가이드라인/`, `docs/광고예시/`, `docs/계획서/`에는 광고심의 규정, 예시 광고물, 사업 계획 관련 원본 파일이 포함되어 있습니다. 이 자료들은 요구사항과 기능명세를 검증하거나 AI 검토 기준을 보강할 때 참고합니다.
