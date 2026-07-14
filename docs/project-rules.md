# 프로젝트 규칙

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.5 |
| 기준일 | 2026-07-14 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.5 | 2026-07-14 | Notion 단방향 게시 테스트를 기존 `개발 문서` 페이지의 번호형 일반 문서와 하단 `ADR` 계층 구조로 변경하고 본문 배포 안내 및 중복 목록 제거 |
| v1.4 | 2026-07-14 | Git `docs/` Markdown의 Notion 단방향 게시 가능성 검증을 위한 수동 테스트 절차 추가. 운영 자동화 정책은 ADR 확정 전 미적용 |
| v1.3 | 2026-07-14 | ADR-0076에 따라 AI 도구 지침, Git hook, CI의 문서 거버넌스 책임을 분리하고 도구별 lifecycle hook을 PoC 필수 범위에서 제외 |
| v1.2 | 2026-07-14 | ADR-0075에 따라 Claude/Codex Skills를 사용자 홈이 아닌 프로젝트 로컬 adapter로 설치하도록 변경 |
| v1.1 | 2026-07-13 | 영문 파일명, 문서 거버넌스 정책/템플릿, 변경 영향 검사, pre-commit/pre-push 및 CI 검증 기준 추가 |
| v1.0 | 2026-07-13 | ADR-0001/0004/0031/0034 기준 명세 기반 개발, AI 활용, 문서 source of truth 원칙 정리 |

## 1. 문서 목적

본 문서는 프로젝트 수행 시 팀 내 개발 방식, 문서 관리 원칙, AI 활용 기준, 저장소 구성, 테스트 및 배포 방침을 공유하기 위한 기준 문서이다.

본 방침의 목적은 다음과 같다.

- 명세 기반으로 개발 범위와 구현 기준을 명확히 한다.
- AI를 활용하여 개발 생산성을 높이되, 결과물의 품질과 검증 책임은 개발자가 가진다.
- 개발 문서, 코드, 의사결정 기록을 추적 가능한 형태로 관리한다.
- 테스트, 린트, 컨테이너, CI/CD 기준을 표준화하여 일관된 개발 환경을 유지한다.

---

# 2. 개발 기본 원칙

## 2.1 명세 기반 개발

본 프로젝트는 **명세 기반 개발**을 원칙으로 한다.

개발자는 구현에 착수하기 전 다음 문서를 기준으로 기능 범위와 완료 기준을 확인해야 한다.

- 요구사항 정의서
- 기능명세서
- 화면설계서
- API 명세서
- 화면-API 매핑표
- DB 설계서
- 테스트 시나리오

기능 구현은 “요구사항 → 기능명세 → API/DB 설계 → 테스트 케이스 → 구현” 순서로 진행한다.

명세에 없는 기능을 임의로 구현하지 않으며, 요구사항 변경이 발생할 경우 관련 문서를 먼저 갱신한 후 개발에 반영한다.

---

## 2.2 AI 활용 개발

본 프로젝트는 AI를 적극 활용하여 풀스택 개발 생산성을 높인다.

AI는 다음 작업에 활용할 수 있다.

- 요구사항 정리
- 기능명세 초안 작성
- API 명세 초안 작성
- 테스트 케이스 작성
- 백엔드 코드 초안 작성
- 프론트엔드 화면 초안 구현
- 리팩토링 제안
- 코드 리뷰 보조
- 문서화 보조
- 오류 원인 분석

다만 AI가 생성한 산출물은 최종 결과물이 아니며, 반드시 담당 개발자가 검토하고 수정해야 한다. 세부 기준은 [ADR-0031: AI 활용 개발 및 검증 책임](adr/ADR-0031-ai-assisted-development-responsibility.md)을 따른다.

---

## 2.3 AI 활용 시 책임 원칙

AI 활용 시 다음 원칙을 따른다.

| 원칙 | 내용 |
| --- | --- |
| 개발자 책임 | AI가 생성한 코드와 문서의 최종 책임은 담당 개발자에게 있다. |
| 명세 우선 | AI 결과보다 요구사항, 기능명세, API 명세, DB 설계를 우선한다. |
| 테스트 필수 | AI가 생성한 코드도 반드시 테스트 케이스를 작성하고 검증한다. |
| 보안 주의 | 고객사 자료, 계정 정보, API Key, 개인정보는 외부 AI 도구에 입력하지 않는다. |
| 검증 후 반영 | AI가 제안한 코드, 쿼리, 설정은 로컬 테스트 후 반영한다. |

다음 영역은 AI 산출물을 그대로 반영하지 않고 담당 개발자 리뷰를 필수로 한다.

| 영역 | 검증 대상 |
| --- | --- |
| 인증/권한 | 권한 우회, 타 부서 데이터 접근, 관리자 기능 보호 |
| 감사 로그 | 기록 범위, 민감정보 저장 여부, 추적 ID |
| 파일 접근 | 다운로드 권한, presigned URL, object key 노출 |
| DB migration | Alembic revision, schema, FK, unique constraint, seed 분리 여부 |
| KPI/평가 산식 | 분모/분자, 제외 기준, 오답 처리 |
| 위험도 산정 | rule priority, HIGH/MEDIUM/LOW 판단 기준 |
| 외부 AI 입력 | 고객사 승인 샘플 범위, 개인정보/비밀값 포함 여부 |
| prompt/config | 출력 schema, fallback, safety rule, version 기록 |

---

# 3. 프론트엔드 개발 방침

프론트엔드는 1차적으로 기능 구현을 우선한다.

초기 화면은 개발자가 초기 화면설계 계획안과 화면-API 매핑표를 기준으로 구현하며, 이후 디자이너의 개선안 또는 디자인 시안을 반영하여 UI/UX를 고도화한다. 핵심/보조 화면의 1차 구현 기준은 [ADR-0032: 프론트엔드 1차 구현 및 디자인 개선 방식](adr/ADR-0032-frontend-first-implementation-policy.md)을 따른다.

## 3.1 프론트엔드 개발 순서

1. 초기 화면설계 계획안 기준 기본 화면 구현
2. API 연동
3. ADR-0045 기준 Validation 및 오류 메시지 처리
4. 테스트 케이스 작성
5. 디자이너 개선안 반영
6. UI/UX 보완
7. 최종 QA

## 3.2 초기 구현 기준

초기 프론트엔드는 다음 사항을 충족해야 한다.

- 화면 진입 가능
- 필수 입력값 처리
- API 요청/응답 연동
- 목록/상세/등록/수정 기본 동작
- ADR-0045 기준 오류 메시지 표시
- 권한별 화면 노출 기준 반영
- 테스트 가능한 상태 제공

디자인 완성도보다 **기능 완결성, API 연동, 테스트 가능성**을 우선한다.

## 3.3 핵심/보조 화면 구현 기준

| 구분 | 1차 구현 기준 |
| --- | --- |
| 핵심 화면 | API 연동 또는 계약 기반 mock, loading/empty/error 상태, 권한 처리, 주요 validation, 업무 action, 수동 검증 가능 상태를 포함 |
| 보조 화면 | 화면 진입, 기본 조회, 기본 상태 표시, 핵심 화면 연결 중심으로 구현 |

핵심 화면은 광고물 등록, AI 검토 요청/진행, 검토 결과, 광고 화면 Annotation, 기준자료 관리, 리포트, PoC 검증/성능 평가 흐름이다. 보조 화면은 대시보드, 광고물 목록, 문구 추천, Q&A, 심의 의견 초안, 수정 전후 비교, 사용자/권한 관리처럼 핵심 검증 흐름을 보조하는 화면이다.

## 3.4 프론트엔드 기술 스택

프론트엔드 기본 스택은 [ADR-0030: 프론트엔드 스택 선택](adr/ADR-0030-frontend-stack.md)을 따른다.

| 영역 | 기준 |
| --- | --- |
| Framework | React |
| Build tool | Vite |
| Language | TypeScript |
| Routing | React Router |
| API 상태 관리 | TanStack Query |
| Table | TanStack Table |
| Form | React Hook Form |
| Validation | Zod |
| API type generation | `openapi-typescript` |
| UI component base | shadcn/ui 또는 Radix 기반 컴포넌트 |

OpenAPI 계약 변경 시 프론트엔드 생성 타입도 함께 갱신한다. OpenAPI 초기 작성 범위와 검증 단계는 [ADR-0062: OpenAPI 초기 계약 작성 범위 및 검증 단계 정책](adr/ADR-0062-openapi-initial-contract-scope-and-validation.md)을 따른다. 초기에는 핵심 플로우 API부터 `openapi/openapi.yaml`에 작성하고, 프론트엔드 API 연동 시작 시 `openapi-typescript` 타입 생성 diff를 확인한다. Annotation 관련 화면은 [ADR-0015: 광고 화면 좌표 체계](adr/ADR-0015-ad-coordinate-system.md)와 [ADR-0066: Coordinate 필드 영속화 및 API 응답 구조 정합화 정책](adr/ADR-0066-coordinate-persistence-and-api-response-policy.md)을 기준으로 구현한다.

핵심 화면의 상세 레이아웃, 컬럼, 필터, 팝업, 권한별 action 노출, 반응형 fallback 기준은 [ADR-0060: PoC 핵심 화면 UI 상세화 및 반응형 범위 정책](adr/ADR-0060-poc-core-screen-ui-detail-policy.md)을 따른다. PoC는 PC/노트북 업무 사용을 우선하고, tablet/mobile은 조회와 상태 확인이 깨지지 않는 수준으로 구현한다.

---

# 4. Git Repository 구성

## 4.1 코드베이스

코드베이스는 **모노 리포지토리(Monorepo)** 구성을 원칙으로 한다.

**예시 구조**는 다음과 같다. (예시이며, 자유롭게 구성 가능)

```
project-root/
├─ apps/
│  ├─ backend/
│  ├─ frontend/
│  └─ worker/
│
├─ packages/
│  ├─ common/
│  ├─ schemas/
│  └─ clients/
│
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  └─ deploy/
│
├─ docs/
│  ├─ requirements/
│  ├─ specifications/
│  ├─ api/
│  ├─ architecture/
│  ├─ adr/
│  └─ meetings/
│
├─ tests/
│
├─ README.md
└─ pyproject.toml
```

모노 리포지토리 구성의 목적은 백엔드, 프론트엔드, AI 워커, 공통 스키마, 인프라 설정을 하나의 저장소에서 일관되게 관리하는 것이다.

---

## 4.2 개발 문서 및 Wiki

프로젝트 Wiki는 단순 문서 보관소가 아니라, **고객사 요구사항·회의록·아키텍처 의사결정 기록(ADR) 등을 추적 가능한 형태로 정리하는 작업 지식층**으로 운영한다.

Wiki 또는 `docs/`에는 다음 문서를 관리한다.

| 구분 | 관리 문서 |
| --- | --- |
| 명세 문서 | 요구사항 정의서, 기능명세서, 화면설계서, API 명세서, 화면-API 매핑표 |
| 의사결정 문서 | ADR, 기술 선택 사유, 아키텍처 변경 이력 |
| 회의 문서 | 회의록, 고객사 요청사항, 결정사항, 후속 조치 |
| 변경 관리 | 고객사 요구사항 변경, 범위 변경, 일정 영향 |
| 개발 규칙 | 코딩 컨벤션, 브랜치 전략, 커밋 메시지, PR 규칙 |
| 공통 스킬 | Claude/Codex Skills, 프롬프트, 반복 작업 자동화 기준 |

---

# 5. 문서 관리 원칙

## 5.1 문서 저장소

문서는 다음 기준으로 관리한다.

문서 충돌 방지와 반복 작업 표준화 및 프로젝트 범위 배포 기준은 [ADR-0075: 프로젝트 범위 Skills 배포 및 온보딩 설치 정책](adr/ADR-0075-project-scoped-skills-distribution.md)을 따른다.

| 도구 | 역할 |
| --- | --- |
| Git | 원천 저장소. 모든 공식 문서와 변경 이력을 관리한다. |
| Notion | 읽기 및 공유 인터페이스. 고객사 또는 내부 공유용으로 활용한다. |
| Claude/Codex Skills | 실행 표준화 계층. 반복 작업, 문서 생성, 코드 생성, 테스트 자동화를 표준화한다. |

---

## 5.2 문서 관리 기준

- 공식 원본은 Git에 저장한다.
- Notion은 공유와 열람 편의를 위한 인터페이스로 사용한다.
- Notion에만 존재하는 중요 결정사항이 없도록 한다.
- 회의에서 결정된 사항은 반드시 Wiki 또는 `docs/meetings`에 기록한다.
- 아키텍처, 기술 선택, 주요 정책 변경은 ADR로 남긴다.
- 요구사항 변경은 관련 명세서와 화면/API/DB 문서에 함께 반영한다.
- 활성 Markdown 문서 파일명은 영문 kebab-case를 사용하고 문서 표시 제목은 업무 독자를 위해 한글로 작성할 수 있다.

---

## 5.3 Skills 및 문서 정합성 Hook

반복되는 AI 활용 개발 작업은 Claude/Codex Skills로 표준화한다. Skills 배포는 [ADR-0075: 프로젝트 범위 Skills 배포 및 온보딩 설치 정책](adr/ADR-0075-project-scoped-skills-distribution.md), 문서 거버넌스 강제 계층은 [ADR-0076: AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층](adr/ADR-0076-ai-tool-lifecycle-hook-enforcement-policy.md)을 따른다.

| 항목 | 기준 |
| --- | --- |
| Skills 원본 | `skills/*/SKILL.md` |
| Codex adapter | `.agents/skills/<skill-name>` |
| Claude Code adapter | `.claude/skills/<skill-name>` |
| Adapter 방식 | 프로젝트 내부 상대 심볼릭 링크 우선, 불가 시 copy + source hash 검증 |
| 초기 설치 | `scripts/setup-dev-tools.sh` |
| 정책 설정 | `governance/document-policy.json` |
| 문서 템플릿 | `governance/templates/` |
| 링크/예시 검사 | `scripts/check-doc-consistency.sh` |
| 정책/변경 영향 검사 | `scripts/doc_guard.py` |
| Git hook | `.githooks/pre-commit`, `.githooks/pre-push` |
| CI 검증 | `.github/workflows/document-governance.yml` |
| Hook 연결 방식 | `git config core.hooksPath .githooks` |
| AI 도구 lifecycle hook | PoC 필수 설치에서 제외. 개인 보조 설정만 허용 |

신규 개발자는 저장소 clone 후 다음 명령을 실행한다.

```bash
scripts/setup-dev-tools.sh
```

해당 스크립트는 다음 작업을 수행한다.

- Claude/Codex Skills adapter를 프로젝트 로컬 `.agents/skills`, `.claude/skills`에 설치한다.
- 사용자 홈의 Codex/Claude Skills 디렉터리는 변경하지 않는다.
- Claude/Codex lifecycle hook 설정은 생성하거나 변경하지 않는다.
- Git pre-commit/pre-push hook을 활성화한다.
- 거버넌스 단위 테스트와 전체 문서 정합성 검사를 실행한다.

문서·거버넌스 변경이 포함된 commit에서는 pre-commit hook이 거버넌스 단위 테스트, Markdown 내부 링크, API 명세 JSON 예시, 가능한 경우 OpenAPI lint, staged 변경 영향 규칙을 검사한다. Push 전에는 upstream 대비 push 대상 commit 범위의 변경 영향과 저장소 전체 정적 정합성을 다시 검사한다. CI는 같은 검사와 거버넌스 Python의 Ruff·basedpyright 검사를 실행한다.

`AGENTS.md`, `CLAUDE.md`, Skills는 변경 전 누락을 예방하는 작업 지침 계층이다. Git pre-commit/pre-push는 로컬 차단 계층이며, CI와 브랜치 보호 규칙은 로컬 hook 우회 여부와 관계없이 적용하는 중앙 강제 계층이다. Claude/Codex lifecycle hook은 PoC의 필수 구성이나 merge 판정 근거로 사용하지 않는다.

개발자는 변경 전후 다음 명령으로 영향 범위와 결과를 확인한다.

```bash
python3 -m scripts.doc_guard impact --scope working
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
```

`error`는 commit 또는 CI 실패 기준이다. `warning`은 자동 차단하지 않지만, 변경자는 관련 문서를 수정하지 않은 이유가 타당한지 확인해야 한다. 로컬 hook은 우회할 수 있으므로 동일 검사를 PR 및 `main`/`develop` push CI에 연결한다.

`skills/`만 사람이 수정하며 `.agents/skills`, `.claude/skills`는 온보딩 스크립트가 생성하는 Git 제외 산출물이다. copy fallback을 사용하는 환경에서 원본과 adapter가 달라지면 로컬 Git hook이 실패하므로 setup 스크립트를 다시 실행해야 한다.

저장소 밖의 내용을 Skill 원본이나 adapter 경로로 우회하지 않도록 `skills/` 내부 심볼릭 링크와 특수 파일, `.agents`/`.claude` adapter root 심볼릭 링크를 허용하지 않는다. 설치·검증 스크립트는 실제 경로가 저장소 내부인지 확인하고 후보 copy의 content/mode hash를 검증한 뒤에만 adapter를 변경한다.

## 5.4 Notion 문서 게시 수동 테스트

Git 문서를 Notion에 단방향으로 게시하는 운영 정책을 ADR로 확정하기 전에 다음 수동 테스트로 기술적 가능성과 제약을 검증한다.

| 항목 | 테스트 기준 |
| --- | --- |
| 실행 방식 | `.github/workflows/notion-docs-publish-test.yml`의 `workflow_dispatch`를 확인 문자열 `PUBLISH_DEV_DOCS`와 함께 수동 실행 |
| 게시 도구 | 공식 Notion CLI를 사용하는 `scripts/publish-notion-docs-test.sh` |
| 게시 대상 | Git이 추적하는 `docs/*.md`, `docs/**/*.md` Markdown 93개. 개수는 2026-07-14 테스트 기준 |
| 제외 대상 | `docs/`의 HWP/HWPX, PDF, PNG, YAML 등 비 Markdown 파일과 Git 비추적 파일 |
| 실행 전제 | 지정한 Notion 부모 페이지의 제목이 `개발 문서`이고 활성 하위 block이 없는 경우에만 실행 |
| 일반 문서 | README 문서 참조 순서에 따라 15개 문서를 `01`~`15` 번호 제목으로 `개발 문서` 바로 아래에 게시 |
| ADR 문서 | 일반 문서 다음에 구분선을 추가하고 마지막 `16. ADR` 페이지 아래에 `docs/adr/` 문서 78개 게시 |
| 본문 | Git Markdown 본문만 게시하며 배포 안내, 원본 경로, commit, 동기화 시각과 별도 문서 목록을 Notion 본문에 추가하지 않음 |
| 내부 링크 | 상대 Markdown 링크를 같은 commit의 GitHub 원문 절대 링크로 변환 |
| 추적 정보 | 게시 대상 commit, Git 원본 경로, 원본 SHA-256, Notion page ID/URL은 GitHub Actions 결과 artifact에만 기록 |
| 잠금 | 게시 완료 후 문서 93개, `16. ADR`, `개발 문서` 페이지를 잠금 처리하고 API로 재검증 |
| 내용 검증 | 제목, 본문 대표 구문, `truncated=false`, 알 수 없는 block 없음 확인 |
| 변경 요청 | Notion 댓글로 의견을 수집하되 공식 변경은 Git branch/PR에서 수행 |

테스트 전 기존 테스트 산출물은 확인 후 삭제하고 비어 있는 `개발 문서` 페이지에 게시한다. GitHub Actions의 `NOTION_API_TOKEN` secret과 `NOTION_PARENT_PAGE_ID`, `NOTION_WORKSPACE_ID` variable을 사용하며 token 값은 로그나 산출물에 기록하지 않는다. 이 절차는 게시 자동화의 운영 주기, 기존 페이지 증분 갱신 방식, Git 삭제·이름 변경 전파, 부분 실패 복구, 잠금 이탈 감지를 결정하지 않는다. 테스트 결과를 검토한 뒤 별도 ADR에서 운영 정책을 확정한다.

---

# 6. 개발 방식

## 6.0 인증/인가 구현 기준

인증/인가는 [ADR-0036: PoC 자체 JWT 인증 및 SSO 전환 가능 인가 구조](adr/ADR-0036-jwt-auth-sso-ready-authorization.md), [ADR-0055: API 인가 범위 및 부서 Scope 판정 기준](adr/ADR-0055-api-authorization-scope-policy.md), [ADR-0056: JWT 세션 및 토큰 수명 정책](adr/ADR-0056-jwt-session-token-lifetime-policy.md), [ADR-0057: 브라우저 보안 정책, CORS/CSRF 및 보안 헤더 기준](adr/ADR-0057-browser-security-cors-csrf-headers.md), [ADR-0058: 로그인 실패 제한, 계정 잠금 및 비밀번호 정책](adr/ADR-0058-login-failure-lockout-password-policy.md)을 따른다.

PoC는 자체 로그인과 JWT Bearer Token을 사용한다. 본사업 전환 시 SSO/OIDC/SAML 연동이 가능하도록 인증 제공자 경계를 두고, 업무 API는 인증 구현체가 아니라 공통 user context와 authorization service를 사용한다.

권한 검증은 role + department scope 기준으로 수행하며, 권한 우회, 타 부서 데이터 접근, 관리자 기능 보호는 고위험 영역으로 리뷰한다. 브라우저 보안은 환경별 CORS allowlist, refresh/logout Origin 검증, refresh token cookie 보안 속성, 기본 보안 헤더를 공통 미들웨어 또는 reverse proxy에서 적용한다. 자체 로그인은 비밀번호 최소 정책, 실패 5회 15분 잠금, IP rate limit, 일반화된 인증 실패 메시지를 공통 인증 로직에서 처리한다.

## 6.0.1 AI Worker Job 설정 기준

AI 분석 Job의 timeout, retry, dead-letter, worker heartbeat 장애 복구는 [ADR-0059: AI 분석 Job Timeout, Retry, Dead-letter 및 Worker 장애 복구 정책](adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md)을 따른다.

전체 Job timeout, 단계별 timeout, retry backoff, retry 대상 오류 코드는 코드에 하드코딩하지 않고 YAML 등 외부 설정으로 관리한다. 기본값은 전체 Job timeout 30분, 최대 retry 3회, backoff 1분/3분/10분이다.

Queue/Worker 구현은 Redis Queue 라이브러리 내부 상태에만 의존하지 않고 `review_jobs`, `review_steps`를 상태 원천으로 갱신해야 한다. Redis 메시지에는 `job_id`, `review_id`, `job_type` 등 최소 식별자만 포함하고 광고 원문, OCR 결과, 기준자료 본문, 고객사 민감정보는 포함하지 않는다.

RAG 검색 adapter는 [ADR-0061: RAG 검색 인프라 장애 처리 및 Fallback 금지 정책](adr/ADR-0061-rag-search-infra-failure-policy.md)을 따른다. Qdrant 또는 OpenSearch 장애 시 keyword-only/vector-only fallback으로 계속 판단하지 않고, `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED`를 반환해 Job retry와 장애 복구 흐름으로 넘긴다.

Parser/OCR adapter는 [ADR-0065: NormalizedDocument 공통 출력 스키마 및 Parser/OCR Adapter 계약 정책](adr/ADR-0065-normalized-document-schema-and-adapter-contract.md)을 따른다. ReviewPipeline, RAG, Annotation, 리포트 로직은 parser별 raw output이 아니라 `NormalizedDocument` v1 필드에만 의존해야 한다.

Parser/OCR 기본 엔진 라우팅은 [ADR-0072: Parser/OCR 기본 엔진 선택 및 파일 유형별 라우팅 정책](adr/ADR-0072-parser-ocr-engine-routing-policy.md)을 따른다. PDF와 복합 PDF/표/다단 문서는 `opendataloader-pdf`, HWP/HWPX는 `rhwp`, 이미지와 스캔 PDF는 `PaddleOCR`을 1차 엔진으로 사용한다. 모든 엔진은 Adapter 뒤에 두며 업무 로직에서 엔진 SDK나 raw output을 직접 호출하지 않는다.

Parser/OCR 품질 미달 시 재처리와 보조 엔진 사용은 [ADR-0073: Parser/OCR 품질 미달 시 재처리 및 보조 엔진 사용 정책](adr/ADR-0073-parser-ocr-quality-rerun-policy.md)을 따른다. 기술 실패는 ADR-0059 기준 retry하고, confidence/구조 인식 품질 미달은 조건 기반 보조 엔진 재처리 후보로 처리한다. 최종 채택된 `NormalizedDocument` v1만 ReviewPipeline 입력으로 사용한다.

Parser/OCR raw artifact 저장, 보존, 접근 권한은 [ADR-0067: Parser/OCR Raw Artifact 저장 위치, 보존 기간 및 접근 정책](adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md)을 따른다. raw artifact는 Object Storage `parser-artifacts` bucket에 저장하고 DB에는 metadata와 참조 ID만 저장한다. 일반 사용자 API는 raw artifact 원문이나 다운로드 URL을 노출하지 않는다.

## 6.1 TDD 개발 원칙

본 프로젝트는 TDD 또는 테스트 우선 개발을 지향한다.

모든 주요 기능은 구현 시 테스트 케이스를 함께 작성해야 한다.

## 6.2 테스트 작성 기준

다음 항목은 반드시 테스트한다.

- API 정상 요청/응답
- 필수값 누락
- 권한 오류
- 파일 업로드 실패
- OCR/AI 분석 실패
- 기준자료 부족
- 검토 결과 조회
- 문구 추천 저장
- 리포트 생성
- DB 저장 및 조회 로직

## 6.3 테스트 실행 기준

PR 생성 전 개발자는 다음을 확인해야 한다.

```bash
ruff check .
ruff format .
pytest
```

테스트가 실패한 코드는 병합하지 않는다.

---

# 7. 활용 언어 및 패키지 관리

## 7.1 기본 언어

본 프로젝트의 기본 개발 언어는 **Python**으로 한다.

Python은 다음 영역에 활용한다.

- 백엔드 API
- AI Agent
- RAG Engine
- 데이터 전처리
- OCR/VLM 연계
- 평가 스크립트
- 배치/워커
- 테스트 자동화

---

## 7.2 의존성 관리

Python 의존성 관리는 `uv`를 사용한다.

패키지 추가 시 다음 명령을 사용한다.

```bash
uv add package-name
```

개발용 패키지는 다음과 같이 추가한다.

```bash
uv add --dev package-name
```

의존성 추가 후에는 관련 lock file 변경사항을 함께 커밋한다.

---

# 8. 개발 환경 및 인프라

## 8.1 개발 VM

개발 환경은 [ADR-0033: 로컬 개발 및 공용 개발 VM 병행](adr/ADR-0033-local-and-shared-dev-vm.md)을 따른다.

개발자는 로컬 환경에서 단위 개발, 빠른 테스트, lint/type check, 프론트엔드 개발 서버, 백엔드 단독 실행, 부분 Docker Compose 실행을 수행한다.

프로젝트 공용 개발 VM은 여의도 서버에서 할당받아 사용하며, Docker Compose 전체 스택 통합 실행, API 계약 검증, 프론트-백엔드-워커 통합 검증, 배포 검증 대상으로 사용한다.

공용 개발 VM 권장 기준은 다음과 같다.

| 항목 | 기준 |
| --- | --- |
| 최소 사양 | 8 vCPU, 32GB RAM, 300GB SSD |
| 권장 사양 | 16 vCPU, 64GB RAM, 500GB SSD |
| 필수 도구 | Docker Engine, Docker Compose plugin, Git |
| 접근 방식 | SSH key 기반 접근, 프로젝트 개발자 중심 권한 제한 |
| 데이터 기준 | 제공받은 샘플 데이터와 개발용 데이터만 사용 |
| 포트 기준 | 필요한 포트만 허용하고 서비스 내부 포트는 내부 네트워크 또는 reverse proxy로 제한 |

개발 VM이 필요한 경우 인프라 담당자에게 신청한다.

신청 시 다음 정보를 포함한다.

- 프로젝트명
- 사용자명
- 필요 CPU/Memory/Disk. 기본 신청은 권장 사양을 우선 사용
- 사용 목적. Docker Compose 전체 스택 통합 개발 환경
- 필요 포트. SSH, frontend/backend/nginx 등 외부 접근이 필요한 포트만 명시
- 예상 사용 기간
- Docker 사용 여부
- 접근 대상자와 SSH key 등록 대상

공용 개발 VM은 `dev` 환경으로 사용한다. `prod(main)` 기준 환경과 물리 VM을 공유할 수는 있으나, DB, object storage bucket, Qdrant collection, OpenSearch index, secret, compose project name은 환경별로 분리한다.

---

## 8.2 Docker 컨테이너 구성

개발 및 배포 환경은 Docker 컨테이너 기반으로 구성한다.

백엔드, 프론트엔드, AI 워커, DB, 검색 엔진, 벡터 DB는 가능한 한 컨테이너를 분리한다.

Docker Compose 파일 구조와 실행 명령은 [ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책](adr/ADR-0063-compose-base-dev-prod-override-policy.md)을 따른다. 공통 서비스 정의는 `compose.yml`, dev 환경 차이는 `compose.dev.yml`, `prod(main)` 환경 차이는 `compose.prod.yml`에 둔다.

예시 구성은 다음과 같다.

| 컨테이너 | 역할 |
| --- | --- |
| backend | API 서버 |
| frontend | 웹 프론트엔드 |
| worker | OCR, RAG, AI 분석 비동기 작업 |
| postgres | 관계형 DB |
| qdrant | 벡터 DB |
| opensearch | 키워드 검색 |
| redis | AI 분석 Redis Queue 및 Cache |
| nginx | Reverse Proxy. 필요 시 사용 |

AI 분석 비동기 작업은 [ADR-0035: Redis Queue 및 PostgreSQL Job 상태 테이블 병행](adr/ADR-0035-redis-queue-postgresql-job-state.md)을 따른다. Redis는 worker 작업 전달에 사용하고, 진행 상태와 이력의 원천은 PostgreSQL `review_jobs`, `review_steps`로 둔다.

Compose 파일 변경 시 다음 조합의 설정 검증을 수행한다.

```bash
docker compose -f compose.yml -f compose.dev.yml --env-file .env.dev.example config
docker compose -f compose.yml -f compose.prod.yml --env-file .env.prod.example config
```

dev 환경은 source mount, hot reload, mock/fixture, dev seed를 허용한다. `prod(main)` 환경은 빌드된 image 또는 release tag, restart policy, 영속 volume, healthcheck, smoke test를 기준으로 하며 실제 비밀값 파일은 Git에 커밋하지 않는다.

---

# 9. 데이터 저장소 및 검색 구성

## 9.1 DB

관계형 DB는 **PostgreSQL**을 사용한다.

PostgreSQL은 다음 데이터를 관리한다.

- 사용자
- 광고물 메타데이터
- 파일 메타데이터
- AI 검토 요청
- 검토 결과
- 근거 매핑
- 문구 추천
- 리포트 이력
- 기준자료 메타데이터
- PoC 검증 데이터셋
- 평가 결과

---

## 9.2 벡터 DB

벡터 DB는 **Qdrant**를 사용한다.

Qdrant는 다음 용도로 활용한다.

- 법령/규정 임베딩 검색
- 내부 매뉴얼 검색
- 심의사례 유사도 검색
- 상품설명서/약관 문맥 검색
- RAG Engine 근거 검색

---

## 9.3 키워드 검색

키워드 검색은 **OpenSearch**를 사용한다.

OpenSearch는 다음 용도로 활용한다.

- 법령명, 조문번호, 기준명 검색
- 필수 문구 검색
- 금지어/주의어 검색
- 심의사례 키워드 검색
- 광고물 텍스트 검색
- 로그 및 운영 데이터 검색

---

## 9.4 검색 전략

본 프로젝트는 벡터 검색과 키워드 검색을 함께 사용하는 Hybrid Search 구조를 지향한다.

| 검색 방식 | 사용 목적 |
| --- | --- |
| Vector Search | 의미 기반 유사 문서 검색 |
| Keyword Search | 정확한 문구, 조문번호, 금지어 검색 |
| Hybrid Search | RAG 근거 검색 정확도 향상 |

---

# 10. CI/CD 방침

## 10.1 CI 기본 단계

CI/CD 검증 Gate와 테스트 실행 분리는 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md)을 따른다.

PR 또는 main 브랜치 병합 전 다음 검증을 수행한다.

```
1. 의존성 설치
2. ruff format 검사
3. ruff check 실행
4. 테스트 실행
5. 빌드 검증
6. Docker 이미지 빌드 검증
```

PR 필수 Gate에는 문서 정합성, OpenAPI/Spectral/API contract, dev/prod Compose config 검증을 포함한다. 실제 OCR/RAG/LLM 또는 외부 AI API 호출 테스트는 PR 필수 Gate에서 제외하고 정기/수동 평가로 분리한다.

---

## 10.2 Lint 및 Format

Python 코드 품질 검사는 `ruff`를 사용한다.

기본 명령은 다음과 같다.

```bash
ruff check .
ruff format .
```

CI에서는 format 위반, lint 오류, 테스트 실패가 발생하면 병합을 제한한다.

---

## 10.3 테스트

테스트는 `pytest`를 기본으로 한다.

```bash
pytest -m "not external_ai and not slow"
```

테스트는 다음 범위를 포함한다.

- Unit Test
- API Test
- Service Test
- Repository Test
- Integration Test
- AI 결과 검증용 샘플 테스트

AI/OCR/RAG 테스트는 [ADR-0044](adr/ADR-0044-ai-mock-fixture-test-policy.md) 기준으로 실행 계층을 분리한다.

| 실행 시점 | 기준 |
| --- | --- |
| Pull Request | Mock/Fixture 기반 unit, API contract, P0 테스트 실행 |
| main 병합 전 | PR 필수 테스트와 핵심 통합 테스트 실행 |
| 정기/수동 평가 | 실제 OCR/RAG/LLM 연동 테스트와 샘플 데이터셋 평가 실행 |
| 릴리스 후보 | Docker Compose smoke test, 대표 E2E, migration 검증 실행 |

PR 필수 테스트에서 외부 AI/OCR/RAG 호출은 기본적으로 금지하고, Mock adapter 또는 golden fixture를 사용한다. 실제 엔진 검증은 비용, 시간, 비결정성을 고려해 정기/수동 평가로 분리한다.

pytest marker는 ADR-0064 기준으로 `unit`, `contract`, `integration`, `external_ai`, `slow`, `e2e`를 사용한다.

---

## 10.4 배포

배포는 **Self-hosted Runner**를 활용한다.

Self-hosted Runner를 사용하는 이유는 다음과 같다.

- 내부망 또는 사내 인프라 접근 필요
- 개발 VM 및 사내 서버와의 네트워크 연계
- 보안 정책 준수
- 컨테이너 기반 배포 자동화

배포 파이프라인은 다음 흐름을 따른다.

```
코드 Push / PR Merge
→ CI 실행
→ Lint 검사
→ Test 실행
→ Docker Build
→ Self-hosted Runner 배포
→ 컨테이너 상태 확인
```

---

# 11. 브랜치 및 PR 운영

## 11.1 브랜치 전략

기본 브랜치 전략은 다음을 따른다.

```
main
develop
feature/*
fix/*
hotfix/*
release/*
```

| 브랜치 | 용도 |
| --- | --- |
| main | 운영 또는 배포 기준 브랜치 |
| develop | 개발 통합 브랜치 |
| feature/* | 기능 개발 브랜치 |
| fix/* | 일반 버그 수정 |
| hotfix/* | 긴급 수정 |
| release/* | 배포 준비 브랜치 |

---

## 11.2 PR 기준

PR 생성 시 다음 항목을 포함해야 한다.

- 작업 개요
- 관련 요구사항 또는 이슈 번호
- 변경 내용
- 테스트 결과
- 영향 범위
- 리뷰 요청 사항

PR은 최소 1명 이상의 리뷰를 받은 후 병합한다.

---

## 11.3 PR 체크리스트

PR 작성자는 다음 항목을 확인한다.

```
[ ] 관련 요구사항 또는 이슈가 연결되어 있다.
[ ] 기능명세 또는 API 명세 변경이 필요한 경우 문서를 수정했다.
[ ] 테스트 케이스를 추가했다.
[ ] ruff check를 통과했다.
[ ] ruff format을 적용했다.
[ ] pytest를 통과했다.
[ ] Docker 실행에 문제가 없다.
[ ] 민감정보가 코드에 포함되지 않았다.
```

---

# 12. ADR 운영

## 12.1 ADR 작성 대상

다음 의사결정은 ADR로 기록한다.

- 주요 아키텍처 변경
- 프레임워크 선택
- DB 선택
- 검색 엔진 선택
- 벡터 DB 선택
- 배포 방식 변경
- 인증/인가 방식 변경
- AI Agent 구조 변경
- RAG 전략 변경
- 외부 서비스 연동 방식 변경

---

## 12.2 ADR 기본 형식

ADR 문서는 `docs/adr/` 경로에 누적 기록한다.

파일명은 `ADR-0000-의사결정-제목.md` 형식을 사용한다.

현재 채택된 ADR 목록은 `docs/adr/README.md`에서 관리한다.

사용자의 판단이 필요한 후보는 `docs/adr/decision-questions.md`에 질문, 선택지, 추천안을 먼저 정리하고 답변을 받은 뒤 ADR로 승격한다.

```
# ADR-0001: Qdrant를 벡터 DB로 사용

## 상태
Accepted

## 배경
광고심의 기준, 심의사례, 상품설명서 검색을 위해 의미 기반 검색이 필요하다.

## 결정
벡터 DB로 Qdrant를 사용한다.

## 대안
- pgvector
- Milvus
- Elasticsearch Vector Search

## 결정 사유
- 경량 구성 가능
- Python 연동 용이
- PoC 환경에서 빠른 구축 가능
- Hybrid Search 구조에서 OpenSearch와 역할 분리가 명확함

## 영향
- 벡터 검색 로직은 Qdrant API에 의존한다.
- 향후 운영 규모 확대 시 성능 검증이 필요하다.
```

---

# 13. 팀 내 최소 준수 규칙

본 프로젝트에서 반드시 지켜야 할 최소 규칙은 다음과 같다.

1. 명세 없이 주요 기능을 구현하지 않는다.
2. 요구사항 변경은 문서에 먼저 반영한다.
3. AI가 작성한 코드는 반드시 개발자가 검토한다.
4. 모든 주요 기능에는 테스트 케이스를 추가한다.
5. PR 전 `ruff check`, `ruff format`, `pytest`를 실행한다.
6. 공식 문서는 Git에 저장한다.
7. Notion은 공유 인터페이스로 활용하되 원천 저장소로 사용하지 않는다.
8. 주요 기술 결정은 ADR로 남긴다.
9. 백엔드, 프론트엔드, AI 워커는 컨테이너를 분리한다.
10. 배포는 Self-hosted Runner 기반 CI/CD를 통해 수행한다.

---

# 14. 결론

본 개발 방침은 프로젝트 수행 과정에서 개발자, 기획자, AI 활용 도구, 문서, 코드, 인프라가 일관된 기준으로 운영되도록 하기 위한 팀 내 표준이다.

핵심 원칙은 다음과 같다.

- 명세 기반으로 개발한다.
- AI를 적극 활용하되 최종 책임은 개발자가 가진다.
- Git을 원천 저장소로 삼고 Notion은 공유 인터페이스로 활용한다.
- Wiki와 ADR을 통해 고객사 요구사항, 회의 결정사항, 기술 의사결정을 추적 가능하게 관리한다.
- TDD와 CI/CD를 통해 코드 품질을 유지한다.
- Docker, PostgreSQL, Qdrant, OpenSearch 기반의 표준 개발 환경을 사용한다.

본 문서는 실제 개발 과정에서 팀 합의에 따라 지속적으로 개정될 수 있다.
