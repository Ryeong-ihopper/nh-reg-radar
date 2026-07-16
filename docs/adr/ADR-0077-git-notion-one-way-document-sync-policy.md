# ADR-0077: Git-Notion 단방향 문서 자동 동기화 정책

## 상태

Accepted

## 배경

Git `docs/`는 개발 명세의 Source of Truth이고 Notion은 읽기·공유 인터페이스다. 기존 게시 도구는 비어 있는 `개발 문서` 페이지에 전체 문서를 한 번 생성하는 수동 테스트만 지원하므로, Git 문서를 수정해도 기존 Notion 게시본은 자동으로 갱신되지 않는다. 이 상태에서는 공유본이 Git 원본보다 뒤처질 수 있고 사용자가 수동 게시 여부를 별도로 기억해야 한다.

기존 Notion 페이지에는 댓글과 공유 URL이 연결될 수 있으므로 매번 페이지를 삭제·재생성해서는 안 된다. 또한 Notion 장애나 부분 실패가 Git 병합을 되돌리거나 이미 검증된 다른 페이지를 손상시키지 않도록 단방향·멱등·실패 안전 경계를 명확히 해야 한다.

## 결정

Git `main`의 Markdown 문서를 Notion `개발 문서` 페이지에 단방향으로 자동 동기화한다.

| 항목 | 결정 |
| --- | --- |
| 원천 | Git `main`의 `docs/*.md`, `docs/**/*.md` |
| 대상 | 기존 Notion `개발 문서` 계층의 대응 페이지 |
| 자동 실행 | `main`에 게시 대상 Markdown 변경이 push된 뒤 GitHub Actions 실행 |
| 수동 실행 | 초기 전환, 장애 복구, 기준 commit 재동기화에 한해 확인 문자열이 필요한 `workflow_dispatch` 허용 |
| 페이지 식별 | Git에서 관리하는 `governance/notion-page-map.json`의 source path-page ID 매핑을 우선 사용 |
| 갱신 방식 | 공식 Notion CLI의 Markdown page update로 기존 page ID와 댓글·공유 URL을 유지하며 본문 교체 |
| 변경 범위 | `main`의 마지막 성공 동기화 commit(없으면 page map baseline)과 현재 commit 또는 수동 기준 commit 사이에서 변경된 현재 Markdown만 갱신 |
| 잠금 | 갱신 직전에 대상 문서만 잠금 해제하고 검증 완료 즉시 다시 잠금 |
| 검증 | 제목, 대표 본문, 전체 Markdown 비절단, unknown block 0개, 잠금 복구를 페이지별 확인 |
| 실패 처리 | 본문·제목을 갱신 전 snapshot으로 복구하고 workflow를 실패 처리; 완료된 다른 페이지는 유지하며 재실행으로 수렴 |
| 신규·삭제·이름 변경 | 신규 page ID 등록과 삭제/이름 변경은 mapping 변경을 포함해 별도 검토한다. 매핑 누락이나 중복은 자동 생성·삭제하지 않고 fail-closed 한다. |
| Secret | `NOTION_API_TOKEN`은 연결·동기화 단계에만 주입하고 source, log, artifact에 기록하지 않음 |
| 결과 증거 | 기준/대상 commit, source SHA-256, page ID/URL, action과 검증 결과를 보존 기간이 제한된 artifact로 기록 |

Notion 본문에는 source path, commit, 동기화 시각 같은 게시 메타데이터를 삽입하지 않는다. 변경 요청은 Notion 댓글로 받을 수 있지만 공식 수정은 Git branch/PR에서 수행하며, 다음 `main` 동기화가 Notion 본문을 Git 원본으로 되돌릴 수 있다.

현재 GitHub 플랜에서는 private repository branch protection과 ruleset을 사용할 수 없으므로 Notion 동기화 성공을 merge 전 강제 Gate로 만들 수 없다. 자동 동기화 실패는 `main` post-merge 운영 실패로 명시하고 Actions 알림과 수동 재실행으로 복구한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 수동 전체 게시만 유지 | 구현은 단순하지만 게시 누락과 공유본 drift가 반복되어 제외 |
| B. 변경된 기존 페이지를 단방향 자동 갱신 | Git 원천, 기존 URL·댓글 보존, 제한된 API 호출을 함께 만족하여 채택 |
| C. 매번 전체 페이지 삭제·재생성 | 구조는 단순하지만 URL·댓글이 사라지고 부분 실패 영향이 커 제외 |
| D. Git-Notion 양방향 동기화 | 충돌 해결과 권한·감사 원천이 불명확해 제외 |
| E. Notion을 명세 원천으로 전환 | ADR-0004의 Git Source of Truth 결정과 충돌해 제외 |

## 결정 근거

- 공식 Notion CLI는 기존 페이지의 Markdown 본문 갱신을 지원하므로 page ID를 유지할 수 있다.
- 마지막 성공 동기화 commit부터 Git diff로 변경 문서만 선택하면 실패 후 다음 실행에서 누락분까지 다시 선택하면서 Notion API 호출량과 영향 범위를 줄일 수 있다.
- source path-page ID 매핑을 Git에서 리뷰하면 제목 변경에 의존한 오매핑을 방지할 수 있다.
- 페이지별 snapshot 복구와 멱등 재실행은 부분 실패 후 운영자가 전체 계층을 재생성하지 않도록 한다.
- Git 원본과 Notion 공유본의 책임을 분리하면 Notion 직접 편집이 구현 계약을 변경하는 것을 막을 수 있다.

## 영향

- `main`의 게시 대상 Markdown 변경은 Notion 동기화 workflow를 자동 실행한다.
- Notion 장애는 제품 CI 성공을 취소하지 않지만 공유본 최신성 장애로 기록된다.
- 문서 신규·삭제·이름 변경 시 page map 변경과 수동 검토가 추가로 필요하다.
- 기존 Notion 페이지 URL과 댓글은 본문 갱신 후에도 유지된다.
- 저장소에 page ID가 기록되지만 인증 token이나 workspace secret은 포함하지 않는다.

## 후속 조치

- 기존 수동 게시 artifact로 page map을 초기화하고 현재 `main` 변경분을 한 번 수동 동기화한다.
- 자동 workflow에 push path filter, 최소 권한, concurrency 직렬화를 적용한다.
- update·검증·rollback·재실행과 매핑 누락을 mock Notion 회귀 테스트로 고정한다.
- 동기화 실패 알림과 운영 복구 시간을 관찰하고 필요하면 별도 알림 채널을 추가한다.
- 신규/삭제/이름 변경 빈도가 증가하면 page map 자동 갱신 PR과 archive 승인 절차를 별도 ADR로 검토한다.

## 관련 문서

- `README.md`
- `docs/project-rules.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0004-git-notion-wiki-roles.md`
- `governance/notion-page-map.json`
- `.github/workflows/notion-docs-publish-test.yml`
- `scripts/publish-notion-docs-test.sh`
