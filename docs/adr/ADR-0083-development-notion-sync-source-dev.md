# ADR-0083: 개발 기간 Notion 동기화 원천 dev 확장 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-23 |
| 관련 문서 | 프로젝트 규칙, 테스트케이스, notion-page-map |
| 관련 ADR | ADR-0077(개정), ADR-0082 |

## 배경

ADR-0077은 Git `main`의 Markdown을 Notion `개발 문서` 페이지에 단방향 자동 동기화한다. ADR-0082로 개발 기간 기본 브랜치를 `dev`로 전환하면서 `main` push가 드물어졌고, `main` 기준 동기화만 유지하면 개발 명세의 Notion 공유본이 장기간 갱신되지 않는다. 개발 중에도 공유본을 최신으로 유지하려는 요구가 있다.

## 결정

1. 개발 기간 동안 Notion 문서 자동 동기화의 **원천 branch를 `dev`로 확장**한다.
2. ADR-0077의 동기화 메커니즘(공식 Notion CLI, 기존 page ID·댓글·URL 보존, `governance/notion-page-map.json` 매핑, 마지막 성공 동기화 commit 기준 변경분 선택, 페이지별 잠금·검증·snapshot 복구, 매핑 누락·중복 fail-closed, 단방향·멱등)은 **그대로 유지**하고 원천 branch 차원만 개정한다.
3. `dev` merge push에서 게시 대상 Markdown이 변경되면 동기화 workflow가 실행된다.
4. 운영 릴리스 준비 시점에 원천을 `main`으로 복귀할지 여부는 ADR-0082·Q77과 함께 재검토한다.
5. 원천 branch 확장은 아래 롤아웃 전제를 충족한 뒤에만 라이브로 활성화한다. 전제 충족 전에는 기존 `main` 원천 트리거를 유지한다(트리거를 먼저 전환하면 개수·매핑 불일치로 fail-closed 된다).

## 롤아웃 전제

1. 게시 대상 Markdown 개수 정합: `EXPECTED_MARKDOWN_COUNT`와 프로젝트 규칙 §5.4의 개수를 현재 `dev` 기준으로 갱신한다.
2. `dev`에만 존재하고 Notion에 없는 문서는 `governance/notion-page-map.json`에 `page_id: null`로 검토 항목을 추가한다.
3. 해당 branch에서 `NOTION_API_TOKEN` 기반 `workflow_dispatch`(`SYNC_DEV_DOCS`, 기준 commit, `allow_create=true`)로 신규 페이지를 최초 생성하고 artifact의 page ID를 page map에 확정한다. 이 단계는 Notion workspace 접근과 secret이 필요하므로 저장소 자동화가 아닌 운영 담당자가 수행한다.
4. page map이 Git에 확정된 뒤 `.github/workflows/notion-docs-publish-test.yml`의 push 트리거 원천을 `dev`로 전환한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. `main` 원천 유지 + 필요 시 수동 `workflow_dispatch` | 개발 공유본 최신성이 담당자 기억에 의존하여 제외 |
| B. 개발 기간 원천을 `dev`로 확장 | 개발 명세 공유본을 상시 최신으로 유지하여 채택 |
| C. Notion을 릴리스 시점 snapshot으로만 운영 | 공유본 갱신은 단순하나 개발 중 공유 요구를 충족하지 못해 제외 |

## 영향

- 롤아웃 완료 후 `dev` merge마다 게시 대상 Markdown 변경이 Notion 공유본에 반영되어 최신성이 향상된다.
- Notion 갱신 빈도가 증가하므로 실패 알림과 멱등 재실행 운영 부담이 늘 수 있다.
- ADR-0077은 원천 branch 차원에서 본 ADR로 개정된다. 나머지 조항은 유효하다.
- 트리거 전환 전까지 Notion 공유본은 기존 `main` 기준으로 유지된다.

## 검증

- 롤아웃 전제 3의 최초 생성 후 page map의 신규 page ID가 확정되었는지 확인한다.
- 트리거 전환 후 `dev` push에서 변경분만 갱신되고 개수·매핑 검증이 통과하는지 확인한다.
- mock Notion 회귀 테스트는 원천 branch 확장 후에도 update·검증·rollback·재실행·매핑 누락 경계를 유지한다.

## 후속 조치

- 운영 담당자가 Notion workspace에서 신규 문서 페이지를 최초 생성하고 page map을 확정한다(토큰 필요).
- page map 확정 후 workflow push 트리거 원천을 `dev`로 전환하는 별도 변경을 반영한다.
- 릴리스 준비 시 원천 `main` 복귀 여부를 ADR-0082·Q77과 함께 결정한다.

## 관련 문서

- `docs/adr/ADR-0077-git-notion-one-way-document-sync-policy.md`
- `docs/project-rules.md`
- `governance/notion-page-map.json`
- `.github/workflows/notion-docs-publish-test.yml`
- `scripts/publish-notion-docs-test.sh`
