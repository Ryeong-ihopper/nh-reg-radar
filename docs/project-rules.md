# 프로젝트 규칙

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.36 |
| 기준일 | 2026-07-27 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.36 | 2026-07-27 | ADR-0083 롤아웃 전제 충족에 따라 Notion 자동 동기화 원천을 `main`에서 `dev`로 전환하고(성공 run 조회에 `--event push` 추가) page map baseline을 최신 동기화 commit으로 갱신 |
| v1.35 | 2026-07-27 | §5.4 Notion 게시 대상을 102개(일반 17·ADR 85)로 갱신하고 아키텍처 구성도 모음(`docs/architecture-overview.md`)을 `참고` 보조 문서 게시 목록에 편입 |
| v1.34 | 2026-07-27 | 완료된 프론트엔드 구현 감사 문서를 게시 대상에서 제거하고(101개, 일반 16·ADR 85) 로컬 화면 캡처 검증 절차를 §3.2로 이전 |
| v1.33 | 2026-07-26 | §5.4에 page-map 기반 read-only Notion Docs Preflight 기준을 추가(canonical `--validate-map` 선행, mutation 금지, 전용 read-only 토큰(`NOTION_READONLY_API_TOKEN`)·`notion-readonly` Environment로 자격 경계 제한) |
| v1.32 | 2026-07-24 | §10.4.1 폐쇄망 반입 기준선 참조를 ADR-0083→ADR-0082(main 기준선)+Q77로 정정, production job을 비활성 스켈레톤으로 명확화, 롤백을 성공 보장이 아닌 best-effort 복구 시도로 정확화, production Environment에 required reviewer가 미설정임을 명시 |
| v1.31 | 2026-07-23 | 결정적 CI·Build 워크플로(ci.yml·release-readiness.yml)를 org-ci/org-build 러너로 이전하고 §10.4.1을 이전 완료 기준으로 갱신 |
| v1.30 | 2026-07-23 | §10.4.1에 release별 커밋 SHA 이미지 태그 롤백과 SSH host key 고정(DEPLOY_KNOWN_HOSTS) 기준을 추가 |
| v1.29 | 2026-07-23 | §10.4.1 development 배포를 조직 공유 러너(org-cg-rookies/org-deploy) SSH release 방식으로 개정, CI/Build의 org-ci/org-build 이전 기준과 production job 비활성 보존을 명시 |
| v1.28 | 2026-07-23 | §5.4에 미매핑 문서의 안전한 단건 최초 등록 절차와 자동 동기화 원천 전환 시 함께 변경할 항목을 명시 |
| v1.27 | 2026-07-23 | §5.4 Notion 게시 대상을 현행 문서 수(102개, 일반 17·ADR 85)로 갱신하고 CI·배포 가이드를 일반 문서 게시 목록에 편입 |
| v1.26 | 2026-07-23 | §10.4.1 `workflow_run` development 자동 배포에 push·dev 브랜치·동일 저장소 source 가드 조건을 명시 |
| v1.25 | 2026-07-22 | 공용 개발 VM은 Vite/reload 개발 override가 아닌 production Compose profile로 실행하고 frontend 사설 IP ingress만 선택 허용하는 기준을 추가 |
| v1.24 | 2026-07-22 | Conventional Commit 한글 요약은 종결 어미 없이 변경 행위를 간결하게 표기하도록 정정 |
| v1.23 | 2026-07-22 | PR 제목을 소문자 Conventional type과 콜론·한글 요약으로 통일하고 공용 개발 VM reverse proxy 인입은 frontend만 사설 IP에 선택적으로 바인딩하며 나머지 Compose 포트는 비공개로 유지하는 기준을 추가 |
| v1.22 | 2026-07-22 | ADR-0081에 따라 private Parser/OCR와 외부 AI 활성화 설정을 분리 |
| v1.21 | 2026-07-22 | ADR-0080을 GitHub-hosted CI와 self-hosted 환경별 Compose CD 분리로 갱신 |
| v1.20 | 2026-07-21 | ADR-0080에 따라 self-hosted CI·환경별 Compose CD runner 분리, `dev` 성공 revision 배포와 production 수동 승인·환경 파일 격리 기준을 추가 |
| v1.19 | 2026-07-20 | document-processor를 Python 3.13/OpenJDK 25 private Compose service로 고정하고 HWP/HWPX 광고·기준자료가 공용 hybrid 계약과 구성요소 artifact 경계를 사용하도록 운영 기준을 구체화 |
| v1.18 | 2026-07-20 | ADR-0079에 따라 HWP/HWPX hybrid parser 기준을 추가하고, 신규 ADR·프론트엔드 감사 문서의 Notion 게시 범위와 최초 페이지 생성 절차를 동기화 |
| v1.17 | 2026-07-20 | 개발 Compose 기준자료 초기 적재는 PDF/HWP/HWPX parser service와 단일 writer lock을 사용하고 완료 후 두 검색 인덱스 상태를 확인하는 기준을 추가 |
| v1.16 | 2026-07-16 | Conventional Commit 제목을 type 접두어와 한글 요약으로 통일하는 기준을 추가 |
| v1.15 | 2026-07-16 | ADR-0072 private parser/OCR service 이미지, health와 실제 provider E2E를 별도 수동 증거로 유지하는 기준을 추가 |
| v1.14 | 2026-07-16 | 신규 개발자용 provider-free 로컬 Compose 진입점, migration·dev seed·health 대기 순서, 브라우저 API 주소와 안전한 중지·초기화 기준 반영 |
| v1.13 | 2026-07-16 | ADR-0077에 따라 `main` Markdown 변경의 Notion 단방향 자동 동기화, 기존 page ID 보존, 페이지별 검증·rollback과 fail-closed mapping 기준 반영 |
| v1.12 | 2026-07-16 | `main`/`dev`/`feature/*`/`hotfix/*` 브랜치, PR·보호 브랜치, Conventional Commits, release tag 및 GitOps 승격·롤백 규칙을 기존 중복 없이 통합 |
| v1.11 | 2026-07-16 | Product CI의 Python/OpenAPI 교차 런타임 의존성 설치 순서와 현행 migration 적용 후 DB privilege probe 검증 기준 명시 |
| v1.10 | 2026-07-16 | Notion 수동 게시의 번호형 문서·ADR 계층, secret·checkout credential 격리, 재시도·실패 정리 및 내용 완전성 검증 기준 통합 |
| v1.9 | 2026-07-15 | G009 현재 파일 SHA-256과 provider-free E2E 4/0/0 건수를 릴리스 Gate에서 정확히 검증하는 fail-closed 기준 반영 |
| v1.8 | 2026-07-15 | AC-18 최종 문서·일정 동기화 실행 순서와 provider-free·수동 외부 AI·production recovery 운영 증거 해석 경계 반영 |
| v1.7 | 2026-07-15 | M8 production recovery 공개 명령과 PostgreSQL·MinIO·Qdrant·OpenSearch·Redis outage 검증 및 무잔여 정리 경계를 명시 |
| v1.6 | 2026-07-15 | M8 provider-free 릴리스 Gate와 실제 외부 AI 수동 평가를 분리하고 보안·감사·redaction 증거 형식을 구체화 |
| v1.5 | 2026-07-14 | M4 worker의 PostgreSQL 상태 원천, 환경별 parser-artifacts private bucket, 최소 Redis 전달과 실제 tri-store 검증·정리 기준 반영 |
| v1.4 | 2026-07-14 | M1 제품 CI에 앱 독립 품질, Compose/health, DB bootstrap·최소권한, 자격증명 및 namespace 격리 Gate를 구체화 |
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

실제 로그인 흐름의 화면 상태를 확인할 때는 `apps/frontend`의 Playwright 기반 `npm run visual:local`을 사용한다. 계정은 저장소에 기록하지 않고 `LOCAL_UI_EMAIL`, `LOCAL_UI_PASSWORD` 환경변수로만 주입하며, 캡처 산출물은 `/tmp/nh-ad-compliance-visual`에 저장하고 Git으로 추적하지 않는다. 기준 디자인 이미지가 확정되기 전까지는 화면기획서의 구조·레이블·권한 메뉴와 렌더링 품질 확인까지를 범위로 한다.

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

`error`는 commit 또는 CI 실패 기준이다. `warning`은 자동 차단하지 않지만, 변경자는 관련 문서를 수정하지 않은 이유가 타당한지 확인해야 한다. 로컬 hook은 우회할 수 있으므로 동일 검사를 PR 및 `main`/`dev` 대상 CI에 연결한다.

`skills/`만 사람이 수정하며 `.agents/skills`, `.claude/skills`는 온보딩 스크립트가 생성하는 Git 제외 산출물이다. copy fallback을 사용하는 환경에서 원본과 adapter가 달라지면 로컬 Git hook이 실패하므로 setup 스크립트를 다시 실행해야 한다.

저장소 밖의 내용을 Skill 원본이나 adapter 경로로 우회하지 않도록 `skills/` 내부 심볼릭 링크와 특수 파일, `.agents`/`.claude` adapter root 심볼릭 링크를 허용하지 않는다. 설치·검증 스크립트는 실제 경로가 저장소 내부인지 확인하고 후보 copy의 content/mode hash를 검증한 뒤에만 adapter를 변경한다.

## 5.4 Notion 문서 단방향 동기화

Git 문서의 Notion 공유본 운영은 [ADR-0077: Git-Notion 단방향 문서 자동 동기화 정책](adr/ADR-0077-git-notion-one-way-document-sync-policy.md)을 따른다.

| 항목 | 테스트 기준 |
| --- | --- |
| 자동 실행 | `dev`에 게시 대상 Markdown 변경이 push되면 `.github/workflows/notion-docs-publish-test.yml` 실행 |
| 수동 실행 | 초기 전환·장애 복구 시 `workflow_dispatch`를 확인 문자열 `SYNC_DEV_DOCS`와 기준 commit으로 실행 |
| 사전 진단 | 페이지 손상(접근 불가·휴지통·부모 불일치·ID 불일치·`truncated`·알 수 없는 block) 진단은 read-only `.github/workflows/notion-docs-preflight.yml`(`scripts/notion-docs-preflight.sh`)로 수행한다. 대상은 page-map의 source path로 지정하고, Notion 호출 전 `--validate-map`으로 게시 계약을 검증하며, create/update/unlock/trash 없이 GET만 사용하고 허용 메타 필드만 산출한다(본문·제목·댓글·토큰 미출력). 자격은 **쓰기 토큰으로 fallback하지 않는 전용 read-only integration token(`NOTION_READONLY_API_TOKEN`)**만 사용하고 `notion-readonly` Environment(배포 브랜치 `dev` 제한)로 범위를 제한한다 |
| 게시 도구 | 공식 Notion CLI를 사용하는 `scripts/publish-notion-docs-test.sh` |
| 게시 대상 | Git이 추적하는 `docs/*.md`, `docs/**/*.md` Markdown 102개. 일반 문서 17개와 ADR 문서 85개 |
| 제외 대상 | `docs/`의 HWP/HWPX, PDF, PNG, YAML 등 비 Markdown 파일과 Git 비추적 파일 |
| 매핑 | `governance/notion-page-map.json`의 source path-page ID를 사용하고 누락·중복·계층 불일치는 fail-closed |
| 프로젝트 규칙 | `프로젝트 규칙`을 번호 없이 `개발 문서` 최상단에 게시하고, 다음 문서군과 구분선으로 분리 |
| 일반 문서 | README 문서 참조 순서에 따라 프로젝트 규칙을 제외한 기준 문서 14개를 `01`~`14` 번호 제목으로 게시하고, CI·배포 가이드와 아키텍처 구성도 모음은 `참고` 보조 문서로 게시 |
| ADR 문서 | 마지막 `15. ADR` 페이지 아래에 `docs/adr/` 문서 85개 게시 |
| 본문 | Git Markdown 본문만 게시하며 배포 안내, 원본 경로, commit, 동기화 시각과 별도 문서 목록을 Notion 본문에 추가하지 않음 |
| 내부 링크 | 상대 Markdown 링크를 같은 commit의 GitHub 원문 절대 링크로 변환 |
| 변경 선택 | `dev`의 마지막 성공 push 동기화 commit(없으면 page map baseline) 또는 수동 기준 commit부터 현재 commit까지 변경된 Markdown을 갱신하여 이전 실패분도 다음 실행에 포함 |
| 추적 정보 | 기준/대상 commit, Git 원본 경로, 원본 SHA-256, Notion page ID/URL과 action은 GitHub Actions 결과 artifact에만 기록 |
| 잠금 | 대상 문서만 갱신 직전에 잠금 해제하고 페이지별 검증 완료 즉시 다시 잠금 |
| 내용 검증 | 제목, 본문 대표 구문, `truncated=false`, 알 수 없는 block 없음 확인 |
| 장애 처리 | 갱신 전 Markdown·제목 snapshot을 확보하고 실패 시 해당 페이지를 복구·재잠금한 뒤 workflow 실패; 멱등 재실행으로 수렴 |
| 신규·삭제·이름 변경 | mapping 변경과 수동 검토 없이 자동 생성·삭제하지 않음 |
| Secret 범위 | `NOTION_API_TOKEN`은 설정 검증, 연결 확인, 게시 단계에만 주입하고 외부 CLI 설치 단계와 job 공통 환경에는 노출하지 않으며, checkout credential도 설치 단계 전에 저장소에 유지하지 않음 |
| 변경 요청 | Notion 댓글로 의견을 수집하되 공식 변경은 Git branch/PR에서 수행 |

GitHub Actions의 `NOTION_API_TOKEN` secret과 `NOTION_PARENT_PAGE_ID`, `NOTION_WORKSPACE_ID` variable을 사용하며 token 값은 로그나 산출물에 기록하지 않는다. Notion은 공유본이므로 직접 본문 편집은 다음 동기화에서 Git 원본으로 대체될 수 있다. 신규·삭제·이름 변경은 page map과 공유 URL 영향이 있으므로 자동 추론하지 않고 별도 검토한다. 현재 private repository 플랜에서는 branch protection을 사용할 수 없어 Notion workflow는 merge 전 차단 Gate가 아니라 `dev` 반영 후 운영 동기화 및 실패 알림 계층으로 사용한다.

신규 Markdown을 Notion에 최초 반영할 때는 게시 manifest와 예상 개수를 갱신하고 page map에 `page_id: null`로 검토된 항목을 추가한다. 해당 branch에서 `workflow_dispatch`를 `SYNC_DEV_DOCS`, 기준 commit, `allow_create=true`로 실행한 후 artifact의 생성 page ID를 page map에 기록한다. page ID가 Git에 확정된 다음부터는 일반 `dev` push가 기존 페이지를 자동 갱신한다.

미매핑 문서가 여러 개일 때의 안전한 최초 등록 절차는 다음을 따른다.

1. 모든 `workflow_dispatch`는 등록 전용 branch(예: `chore/notion-page-registration`) ref에서 실행하고, `allow_create=true`와 함께 `sync_paths`에 **정확히 한 경로**만 지정한다. 스크립트는 빈·다중·기매핑 경로를 쓰기·생성 호출 전에 거부한다.
2. 단건 성공 후 artifact의 생성 page ID를 **같은 branch의 page map에 commit·push**한 뒤 다음 문서를 실행한다.
3. 실패한 run이라도 artifact가 있으면 재실행하지 말고 artifact의 ID를 먼저 page map에 반영한다(생성 후 마무리 실패 대비).
4. artifact가 없는 취소·runner 중단은 Notion에서 실제 생성 여부를 대조한 뒤에만 재실행한다.
5. 다음 dispatch는 반드시 직전 page map commit을 포함한 동일 branch ref를 사용한다.
6. 미매핑 문서를 모두 등록하고 page map의 `null`이 0개임을 확인한 뒤 PR로 `dev`에 병합한다.
7. 자동 동기화 원천은 ADR-0083 롤아웃 전제를 충족한 뒤 `dev`로 전환했다(2026-07-27). workflow의 `push.branches`와 성공 run 조회(`gh run list --branch`)를 함께 `dev`로 변경하고, 성공 run 조회에는 `--event push`를 지정해 수동 단건 `workflow_dispatch`가 전체 동기화 기준점으로 오인되지 않게 한다.

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

Parser/OCR 기본 엔진 라우팅은 [ADR-0079: HWP/HWPX 이중 원천 Hybrid Parser 구성 정책](adr/ADR-0079-hwp-hwpx-hybrid-parser-composition.md)을 따른다. PDF와 복합 PDF/표/다단 문서는 `opendataloader-pdf`, 이미지와 스캔 PDF는 `PaddleOCR`을 사용한다. HWP/HWPX는 `rhwp` 기준 텍스트와 `document-processor` 구조를 `HwpHybridParserAdapter`에서 정렬·병합한다. 모든 엔진은 Adapter 뒤에 두며 업무 로직에서 엔진 SDK나 raw output을 직접 호출하지 않는다.

Parser/OCR 품질 미달 시 재처리와 보조 엔진 사용은 [ADR-0073: Parser/OCR 품질 미달 시 재처리 및 보조 엔진 사용 정책](adr/ADR-0073-parser-ocr-quality-rerun-policy.md)을 따른다. 기술 실패는 ADR-0059 기준 retry하고, confidence/구조 인식 품질 미달은 조건 기반 보조 엔진 재처리 후보로 처리한다. 최종 채택된 `NormalizedDocument` v1만 ReviewPipeline 입력으로 사용한다.

Parser/OCR raw artifact 저장, 보존, 접근 권한은 [ADR-0067: Parser/OCR Raw Artifact 저장 위치, 보존 기간 및 접근 정책](adr/ADR-0067-parser-ocr-raw-artifact-storage-retention-policy.md)을 따른다. raw artifact는 Object Storage `parser-artifacts` bucket에 저장하고 DB에는 metadata와 참조 ID만 저장한다. 일반 사용자 API는 raw artifact 원문이나 다운로드 URL을 노출하지 않는다.

`parser-artifacts` bucket은 `AD_ORIGINALS_BUCKET`과 분리된 환경별 private namespace로 bootstrap하고 backend/worker runtime identity에 필요한 object 작업만 허용한다. 실제 PostgreSQL+Redis+MinIO 통합 검증은 synthetic fixture와 고유 Compose project를 사용하고 완료 후 컨테이너, network, volume, 임시 env를 모두 제거한다.

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

공용 개발 VM의 HTTPS reverse proxy는 frontend 포트 하나만 대상으로 한다. 장기 실행은 `compose.yml`과 `compose.prod.yml`로 구성하며, Vite/reload를 포함하는 `compose.dev.yml`은 개발자 로컬 작업에만 사용한다. reverse proxy가 VM 사설망에서 접속해야 할 때만 환경 파일의 `FRONTEND_BIND_ADDRESS`를 VM 사설 IP로 설정한다. backend·worker·DB·검색·parser/OCR 포트는 이 설정으로 노출하지 않는다.

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

M4 Redis delivery queue/dead-letter 이름은 `REDIS_QUEUE_PREFIX` 아래에서 환경별로 분리한다. delivery payload는 frozen `ReviewQueueMessageV1` 식별자만 포함하며 원문, 정규화 본문, raw provider output, bucket/object key를 포함하지 않는다.

Compose backend와 worker는 반드시 동일한 `REDIS_URL` 및 review queue 이름을 설정한다. backend가 host 기본값으로 fallback하면 요청은 영속화되어도 worker로 전달되지 않으므로, Compose bootstrap 회귀는 backend Redis URL/queue 주입을 정적으로 검증하고 실제 provider E2E는 완료 상태까지 확인한다.

ADR-0079의 `opendataloader-pdf`/`PaddleOCR`/`rhwp`/`document-processor`는 private Compose service로 관리하고 worker는 service-specific adapter를 통해 `NormalizedDocument` v1만 수용한다. `document-processor`는 worker의 Python 3.12 의존성과 분리한 Python 3.13/OpenJDK 25 이미지로 운영하고 승인된 Git commit을 고정한다. PDF/복합 PDF와 이미지·스캔 PDF는 해당 service로 라우팅하며, HWP/HWPX 광고와 기준자료는 rhwp 텍스트와 document-processor 구조를 병합한 공용 `hwp-hybrid` 산출물을 사용한다. 구성요소 artifact는 미선택 상태로, 병합본 하나만 선택 상태로 보존한다. 이 engine service는 운영 Compose 네트워크 내부에만 두고, local dev의 loopback port는 디버깅 목적 외 사용하지 않는다. 엔진 container build, healthcheck, 파일 유형별 실제 E2E가 통과하기 전에는 구현 성공으로 표시하지 않는다.

Compose 파일 변경 시 다음 조합의 설정 검증을 수행한다.

```bash
docker compose -f compose.yml -f compose.dev.yml --env-file .env.dev.example config
docker compose -f compose.yml -f compose.prod.yml --env-file .env.prod.example config
```

dev 환경은 source mount, hot reload, mock/fixture, dev seed를 허용한다. `prod(main)` 환경은 빌드된 image 또는 release tag, restart policy, 영속 volume, healthcheck, smoke test를 기준으로 하며 실제 비밀값 파일은 Git에 커밋하지 않는다.

신규 개발자의 표준 로컬 실행 진입점은 `scripts/local-dev.sh up`이다. 이 명령은 `.env.dev`의 격리된 Compose project에서 PostgreSQL bootstrap 완료 후 migration identity로 Alembic `head`를 적용하고, app identity로 공통·synthetic dev seed를 적용한 다음 전체 서비스 health/readiness 완료까지 기다린다. 브라우저가 사용하는 `VITE_API_BASE_URL`은 `CORS_ALLOWED_ORIGINS` 및 공개 backend port와 일치해야 한다.

`scripts/local-dev.sh down`은 volume을 보존하고, `scripts/local-dev.sh reset`은 해당 Compose project의 local volume을 삭제한 뒤 빈 DB부터 다시 구성한다. dev 예제 credential은 개인 로컬 전용이며 공유 VM·stage·prod에서 재사용하지 않는다. 기본 로컬 경로는 provider-free이며 외부 LLM/OCR/RAG credential을 요구하거나 실제 엔진 성공을 주장하지 않는다.

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

M1 플랫폼 변경은 다음 CI 경계를 추가로 적용한다.

| Gate | 실행 범위 | 자격증명 기준 |
| --- | --- | --- |
| 앱 독립 품질 | backend/worker Python lint·typecheck·test와 frontend clean install·lint·typecheck·test·build | bootstrap/admin 자격증명 주입 금지 |
| Compose/namespace | dev/prod config, env example secret 검사, namespace 정적 비교, dev health smoke | example 값만 사용하고 실제 secret 저장 금지 |
| DB bootstrap/권한 probe | 일회성 bootstrap 재실행, migration upgrade, seed 분리, 금지 권한 probe | 전용 Job에만 수명이 제한된 bootstrap credential 주입 후 폐기 |

일반 제품 테스트 Job은 bootstrap/admin credential을 상속하지 않는다. Alembic은 migration identity만 사용하고 runtime app/worker는 migration DSN을 받지 않는다. 상세 자동 검증 항목은 `TC-NFR-INFRA-001`~`TC-NFR-INFRA-005`를 따른다.

Python의 runtime/static OpenAPI parity 테스트는 저장소의 Node 기반 OpenAPI loader를 호출하므로, 앱 독립 품질 Job은 root `npm ci --ignore-scripts`를 Python 결정적 테스트보다 먼저 완료해야 한다. DB bootstrap/권한 probe는 전체 migration 적용 후 빈 업무 스키마를 기대하지 않으며, 현행 Alembic revision과 app/rag/validation/audit의 대표 relation 존재를 확인한 뒤 역할별 금지 권한을 검증한다.

### 10.1.1 M8 릴리스 자동화와 실제 엔진 평가 경계

M8 릴리스 후보 검증은 [ADR-0044](adr/ADR-0044-ai-mock-fixture-test-policy.md)와 [ADR-0064](adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md)에 따라 다음 두 workflow를 분리한다.

| Workflow | 실행 경계 | 자격증명·증거 기준 |
| --- | --- | --- |
| `.github/workflows/release-readiness.yml` | PR/push 및 명시적 수동 실행의 provider-free Gate | 외부 provider secret과 live inference를 사용하지 않는다. G009 manifest의 OpenAPI·generated client·migration·artifact SHA-256을 현재 파일과 대조하고, provider-free E2E JUnit 결과가 `4 passed/0 failed/0 skipped`와 정확히 일치해야 한다. 이어서 고정 fixture 기반 E2E/release test, lint/type/OpenAPI/frontend/docs/governance를 검증한다. recovery smoke는 수동 입력으로만 실행하되 `NH_RUN_G011_DOCKER_REGRESSION=1` 반복 bootstrap 회귀를 먼저 통과해야 한다. |
| `.github/workflows/external-ai-evaluation.yml` | 승인 환경의 `workflow_dispatch` 수동 평가 | `external_ai` marker만 실행한다. provider/engine/model, 비밀값이 아닌 config SHA-256, 승인 dataset snapshot ID, revision/time/pass-fail-skip count만 `external-ai-evidence.json`에 기록한다. API key, 고객 원문, raw pytest log는 artifact에 포함하지 않는다. |

수동 실제 엔진 평가는 릴리스 판단을 보조하는 별도 증거이며 provider-free Gate를 대체하거나 약화하지 않는다. 수동 workflow가 실행되지 않았거나 실패해도 이를 provider-free 성공으로 오인하지 않고 별도 잔여 위험 또는 결함으로 기록한다.

### 10.1.3 OpenAI live 개발·배포 secret 경계

private Parser/OCR는 `NH_PARSER_SERVICES_ENABLED=true`로 별도 활성화하며 external AI가 없어도 PDF·이미지·HWP/HWPX 정규화와 결정적 Rule 검토를 수행할 수 있다. 실제 OpenAI 기반 광고 결과 확인은 `feature/*` 또는 로컬 dev 환경의 명시적 opt-in으로만 수행한다. `.env.dev`에는 `NH_EXTERNAL_AI_ENABLED=true`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`, 선택적으로 generation/embedding별 base URL·key·timeout·dimension을 설정할 수 있으나 `.env.dev`와 실 key는 Git에 커밋하지 않는다. 개발 Compose는 해당 key를 worker, embedding을 수행하는 backend, 명시적으로 실행한 one-shot 기준자료 적재 command에만 전달한다. PDF/HWP/HWPX 규정 적재는 읽기 전용 `/reference-documents`의 ADR-0002 승인 샘플에 한정한다.

임베딩 endpoint는 OpenAI-compatible `/v1/embeddings` 계약을 사용한다. 폐쇄망 vLLM 전환은 `EMBEDDING_BASE_URL`, `OPENAI_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, 필요 시 `EMBEDDING_API_KEY`와 `EMBEDDING_ALLOW_INSECURE_HTTP=true`를 명시하여 수행한다. model·dimension·endpoint를 바꾸면 기존 vector collection을 재사용하지 않고 새 `QDRANT_COLLECTION`과 전체 기준자료 재색인을 사용한다. OpenSearch와 Qdrant 중 하나라도 사용할 수 없으면 DB scan/단일 backend 성공으로 우회하지 않는다.

배포/수동 GitHub Actions 평가는 repository 또는 environment secret `OPENAI_API_KEY`만 사용하며, PR CI·artifact·로그·Notion 동기화에는 key, 광고 원문, provider raw response를 포함하지 않는다. `NH_EXTERNAL_AI_ENABLED=false` 또는 key 누락은 외부 AI/RAG 결과의 fallback 성공이 아니라 fail-closed 구성 경계이며, private parser/OCR 활성화와는 독립적이다. 새로운 고객/운영/민감 자료를 provider에 보내기 전에는 ADR-0002의 별도 승인 기록이 필요하다.

M8 production recovery rehearsal의 공개 실행 경계는 `bash scripts/release-smoke.sh --env-file .env.prod.example --fresh-project --with-restart-and-outages`이며, 자동 회귀는 `NH_RUN_M8_RELEASE_DOCKER=1 uv run pytest tests/release/test_release_recovery_contract.py -q -rs`로 opt-in 한다. 이 Gate는 G011 fresh/repeat-volume, 0001→0007→0008 migration, backup 이후 downgrade와 PostgreSQL payload/revision 복구, MinIO checksum 복구, Qdrant snapshot download→waited delete→node-global copy→async restore의 green collection·point payload 확인, OpenSearch 재색인, Redis backup 제외와 503 `not_ready`→recovery, object/search outage, PostgreSQL restart를 모두 통과해야 한다. 성공과 실패 모두 production/G011 project의 container·volume·network와 임시 backup directory가 0개로 정리되어야 한다.

### 10.1.2 AC-18 최종 문서·일정 동기화 운영 경계

최종 문서 동기화는 구현 증거를 먼저 명세와 운영 문서에 반영한 뒤 일정/Kanban을 마지막에 갱신한다. 검증 순서는 다음과 같다.

```bash
python3 -m scripts.doc_guard impact --scope working
scripts/check-doc-consistency.sh
python3 -m scripts.doc_guard validate --scope working
python3 -m unittest discover -s tests/governance -v
```

| 판정 대상 | 운영 기준 |
| --- | --- |
| 실제 구현 경로 | backend/worker runtime, frontend client/generated OpenAPI, migration과 workflow의 저장소 경로를 문서 예시와 일치시킴 |
| `Done` 전환 | executable test, goal/fixture trace, runtime/client 또는 운영 rehearsal 증거가 있는 task에만 적용 |
| Provider-free | 외부 API key와 live inference 없이 재현되는 기본 merge/release Gate |
| Credentialed `external_ai` | 승인된 수동 평가 lane이며 provider-free 성공을 대체하지 않음 |
| Production/customer 수용 | 배포, 고객 피드백, 실제 데이터 품질, 전체 P0/P1/Critical 집계는 별도 증거 없이는 완료로 전환하지 않음 |

AC-18 완료 보고는 문서·링크·거버넌스 0 error와 실제 일정 잔여 dependency를 함께 기록한다. OpenAPI Spectral warning처럼 비차단 잔여가 있으면 error 0과 분리해 공개하며 0건으로 과장하지 않는다.

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

## 10.4 GitOps 배포

Git은 코드와 배포 구성의 단일 진실원천이다. 운영 변경은 PR을 통해서만 수행하며 클러스터에 `kubectl apply` 등으로 직접 반영하지 않는다. 긴급 수동 조치가 불가피하면 즉시 Git 변경으로 역반영하고 접근·승인 기록을 남긴다.

애플리케이션 저장소는 소스·테스트·Dockerfile·CI를, 별도 GitOps 저장소는 Kubernetes manifest·Helm values·Kustomize overlay를 관리하는 구성을 권장한다. GitOps 환경은 장기 브랜치보다 `overlays/dev`, `overlays/stg`, `overlays/prod` 디렉터리로 분리한다.

| 단계 | 기준 |
| --- | --- |
| 개발 | `feature/*`가 `dev`에 병합되면 CI가 immutable SHA image를 빌드하고 GitOps `dev` overlay 변경 PR을 생성 |
| 운영 | `dev`→`main` 릴리즈 PR과 `vMAJOR.MINOR.PATCH` tag 이후 같은 image tag를 `stg`→`prod`로 승격하며 재빌드하지 않음 |
| 롤백 | 이전 Git commit을 revert하거나 이전 immutable tag로 되돌리는 GitOps PR 사용 |
| Drift | Argo CD/Flux 차이 감지 시 수동 변경 여부를 확인하고 실제 환경을 Git 기준으로 원복하거나 승인된 Git 변경으로 수렴 |

Self-hosted Runner는 내부망 image build·registry push·GitOps PR 생성에 사용할 수 있지만 운영 manifest를 우회해 직접 배포하지 않는다. 운영에서는 `latest` tag를 금지하고 release tag 또는 commit SHA만 사용한다.

### 10.4.1 Self-hosted Compose CD

PoC Compose 환경은 ADR-0080의 배포 경계를 사용한다. development 배포는 조직 공유 self-hosted runner(`self-hosted`, `linux`, `x64`, `org-cg-rookies`, `org-deploy`)에서 **SSH release 방식**으로 실행한다. 결정적 CI는 `org-ci`, 이미지 빌드·Compose smoke는 `org-build`(둘 다 `large`) 조직 공유 러너에서 실행한다(비용·인프라 관리 주체 고려). 인터넷 아웃바운드가 필요한 보조 워크플로(문서 동기화·수동 외부 AI 평가·Notion 동기화)는 org 러너 아웃바운드 접근을 확인한 뒤 개별 이전하며, 그 전까지 GitHub-hosted `ubuntu-latest`를 유지한다.

development 배포 흐름은 다음과 같다. 러너가 검증된 revision을 checkout하고, GitHub Environment(`development`)의 `DEPLOY_SSH_KEY`로 `DEPLOY_HOST`에 SSH 접속해 `DEPLOY_PATH/releases/<sha>`에 소스를 동기화한다. 대상 호스트에서 `compose.yml` + `compose.prod.yml`(runtime)과 대상 호스트의 공유 `env/.env.dev`로 배포하되, 이미지는 **커밋 SHA 태그(`RELEASE_TAG=<sha>`)** 로 빌드해 release마다 불변 이미지를 남긴다. health가 통과한 뒤에만 `app` 심볼릭 링크를 새 release로 원자적으로 교체한다. 실패 시 심볼릭 링크를 교체하지 않고 이전 release에 기록된 이미지 태그(`.release_tag`, 없으면 legacy `dev`)로 서비스 복구를 **시도**한 뒤(복구 단계는 실패를 무시하므로 성공을 보장하지 않으며, 복구 자체가 실패하면 대상 호스트에서 수동 확인이 필요하다) workflow를 실패 처리하며, 결과는 `MATTERMOST_WEBHOOK_URL`로 알린다. SSH host key는 `DEPLOY_KNOWN_HOSTS`로 고정하고(미설정 시 `ssh-keyscan` TOFU로 경고와 함께 대체), source mount·hot reload 전용 `compose.dev.yml`은 로컬 개발에만 사용한다.

`dev` push에서 Product CI가 성공한 정확한 head SHA만 development에 자동 반영한다. 이 `workflow_run` 자동 배포는 신뢰되지 않은 코드가 실행되지 않도록 `workflow_run.event == 'push'`, `head_branch == 'dev'`, `head_repository.full_name == github.repository` 조건을 모두 만족할 때만 발동한다(fork·PR 트리거 배포 배제). 배포 대상·경로·계정은 `development` Environment variable `DEPLOY_HOST`/`DEPLOY_PATH`/`DEPLOY_PORT`/`DEPLOY_USER`로 주입하고, `.env.dev`는 러너 checkout 밖 대상 호스트의 권한 제한 경로(`0600`)에 둔다.

production은 현재 NH 내부 폐쇄망 수동 반입을 사용하며 자동 배포하지 않는다(`main` 릴리스 기준선은 ADR-0082, 폐쇄망 반입 릴리스 전략은 Q77 결정 대기). workflow의 production job은 아직 production-ready 구현이 아닌 **비활성 코드 스켈레톤**으로 보존하며(`scripts/deploy-ssh.sh`가 항상 `env/.env.dev`를 사용해 production 전용 env 경계가 없음), `workflow_dispatch` + `environment=production` 선택 + `DEPLOY_PRODUCTION` 확인 문자열을 요구하고 production variable이 실제 값으로 설정되기 전에는 실행하지 않는다. 다만 현재 production Environment에는 required reviewer 등 protection rule이 설정돼 있지 않으므로, 승인 통제가 필요하면 별도 정책으로 활성화한다. 상세 등록·복구 절차는 `docs/self-hosted-runner-guide.md`를 따른다.

---

# 11. 브랜치 및 PR 운영

## 11.1 브랜치 전략

`main`과 `dev`는 보호 브랜치이며 직접 commit·push, force push, branch 삭제를 금지한다. 모든 기능·수정·문서·운영 설정 변경은 작업 브랜치와 PR을 사용한다. 저장소 관리자 긴급 조치는 예외 사유와 후속 PR·리뷰 기록을 남겨야 한다.

| 브랜치 | 용도 |
| --- | --- |
| `main` | 배포 가능한 운영 기준선과 릴리즈 이력 |
| `dev` | 기능 통합·개발 환경 검증 기준선 |
| `feature/*` | `dev`에서 분기하는 신규 기능·개선·일반 수정 |
| `hotfix/*` | `main`에서 분기하는 운영 장애·치명적 결함 긴급 수정 |
| `docs/*` | 문서 전용 변경에 선택적으로 사용 |

## 11.2 병합 흐름

| 변경 유형 | PR 흐름 | 병합 방식 |
| --- | --- | --- |
| 기능·일반 수정 | `feature/*` → `dev` | Squash merge 권장 |
| 문서 | `docs/*` → `dev` | Squash merge 권장 |
| 운영 릴리즈 | `dev` → `main` | Merge commit |
| 긴급 수정 | `hotfix/*` → `main`, 이후 `main` → `dev` 역반영 | Merge commit |

CI 실패 상태에서는 병합하지 않는다. `hotfix/*`를 `main`에만 반영하고 `dev` 역반영을 누락해서는 안 된다.

## 11.3 브랜치 및 커밋 명명

브랜치는 `<type>/<short-description>` 또는 `<type>/<issue-number>-<short-description>` 형식으로 작성하며 소문자와 하이픈을 사용한다. `feature/test`, `feature/tmp`처럼 목적이 불명확한 이름은 금지한다.

커밋 제목은 Conventional Commits 형식을 사용한다.

```text
<type>: <한글 요약>
```

허용 type은 `feat`, `fix`, `hotfix`, `refactor`, `docs`, `test`, `chore`, `ci`이다. 제목의 요약은 한글로 작성하며 scope는 사용하지 않는다. 요약은 `한다`·`됩니다` 같은 종결 어미를 쓰지 않고 변경 행위를 간결한 명사형 또는 동사 어간으로 끝낸다. 예: `fix: 개발 도메인 Vite 접근 허용`. 한 커밋에는 하나의 논리적 변경만 담고 `WIP`, `final`, `test` 같은 의미 없는 제목은 사용하지 않는다. 예: `fix: 갱신 토큰 재사용 방지`, `ci: 현행 마이그레이션 head 검증`.

## 11.4 PR 및 리뷰 기준

PR은 가능한 한 한 가지 목적과 300~500줄 이내의 리뷰 가능한 크기로 유지하며 리팩터링과 기능 추가를 분리한다. PR 본문에는 다음 항목을 포함한다.

PR 제목은 다음 형식을 사용한다. type은 소문자로 작성하고 scope·대괄호 접두어를 사용하지 않는다.

```text
<type>: <한글 요약>
```

허용 type은 커밋과 동일하게 `feat`, `fix`, `hotfix`, `refactor`, `docs`, `test`, `chore`, `ci`이다. 예: `feat: 광고 규정 Q&A 추가`, `fix: 한글 문서 미리보기 오류 수정`, `docs: 개발 환경 실행 절차 보강`.

- 변경 목적과 관련 요구사항·이슈
- 변경 내용 요약
- API·DB·배포·운영 영향 범위
- 테스트 방법과 결과
- 운영 변경 시 배포·롤백 방법

최소 1명 승인을 필수로 하고 2명을 권장한다. DB·인프라·운영 영향 변경은 담당자 추가 승인을 받는다. `main`과 `dev`에는 PR, 필수 CI, 승인, force push·삭제 금지 보호 정책을 적용한다.

## 11.5 릴리즈 및 Hotfix

운영 릴리즈는 `main`에 `vMAJOR.MINOR.PATCH` tag와 릴리즈 노트를 남긴다. 호환성 파괴는 MAJOR, 기능 추가는 MINOR, 버그 수정은 PATCH를 증가시킨다. 운영 image는 release tag와 commit SHA를 함께 추적하고 immutable하게 사용한다.

Hotfix는 `main`에서 `hotfix/<issue>`를 분기해 긴급 리뷰·CI 후 `main`에 병합한다. 배포 이후 `main`→`dev` 역반영과 GitOps `prod` overlay 변경을 확인한다.

## 11.6 PR 체크리스트

PR 작성자는 다음 항목을 확인한다.

```text
[ ] 관련 요구사항 또는 이슈가 연결되어 있다.
[ ] 기능명세 또는 API 명세 변경이 필요한 경우 문서를 수정했다.
[ ] 테스트 케이스를 추가했다.
[ ] lint, format, typecheck, 테스트를 통과했다.
[ ] Docker 실행에 문제가 없다.
[ ] 민감정보가 코드에 포함되지 않았다.
[ ] 배포 영향과 롤백 방법을 확인했다.
[ ] hotfix라면 dev 역반영 계획이 있다.
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
10. 운영 배포와 롤백은 immutable image와 GitOps PR을 통해 수행한다.

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
