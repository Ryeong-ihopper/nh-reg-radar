# ADR-0076: AI 도구 Lifecycle Hook 적용 범위 및 문서 거버넌스 강제 계층

## 상태

Accepted

## 배경

프로젝트는 `AGENTS.md`, `CLAUDE.md`와 프로젝트 Skills로 사람과 AI의 작업 절차를 안내하고, Git pre-commit/pre-push hook과 CI로 문서 정합성을 검사한다. Claude Code와 Codex의 도구별 lifecycle hook을 추가하면 파일 편집이나 AI 작업 종료 직후 더 빠르게 오류를 발견할 수 있지만, 도구마다 지원 이벤트와 설정 형식이 달라 같은 정책을 중복 구현하고 유지해야 한다.

문서 거버넌스의 최종 통과 기준은 개발자가 사용하는 AI 도구나 IDE와 무관해야 한다. PoC 단계에서는 빠른 피드백보다 모든 개발 경로에 동일한 기준을 적용하고, 우회 가능한 로컬 검사와 중앙 병합 검사의 책임을 분명히 하는 것이 우선이다.

## 결정

PoC에서는 Claude Code와 Codex의 도구별 lifecycle hook을 프로젝트 필수 설치 또는 강제 계층으로 사용하지 않는다. 문서 거버넌스는 다음 세 계층으로 운영한다.

| 계층 | 구성 | 책임 |
| --- | --- | --- |
| 작업 지침·예방 | `AGENTS.md`, `CLAUDE.md`, `skills/*/SKILL.md` | 변경 전 source of truth와 동기화 대상을 확인하고 누락을 예방 |
| 로컬 차단 | `.githooks/pre-commit`, `.githooks/pre-push` | commit과 push 전에 문서 정합성, 변경 영향, 테스트를 검사 |
| 중앙 강제 | GitHub Actions CI와 브랜치 보호 규칙 | 로컬 hook 우회 여부와 관계없이 PR 병합 및 기준 브랜치 반영 전에 동일한 필수 검사를 수행 |

세부 적용 규칙은 다음과 같다.

1. `scripts/setup-dev-tools.sh`는 프로젝트 Skills adapter와 Git hook을 설치하지만 Claude/Codex lifecycle 설정은 생성하거나 변경하지 않는다.
2. 문서 정합성의 공식 강제 기준은 저장소에서 버전 관리되는 검사 스크립트, Git hook과 CI workflow이다.
3. 도구별 lifecycle hook 결과만으로 commit, push 또는 merge 가능 여부를 판단하지 않는다.
4. 개발자가 개인 환경에서 lifecycle hook을 보조적으로 사용할 수는 있지만, 해당 설정은 프로젝트 필수 구성이나 source of truth가 아니다.
5. 로컬 Git hook은 우회할 수 있으므로 CI 검사를 PR과 기준 브랜치의 필수 Gate로 유지한다.
6. lifecycle hook이 필요해지더라도 Git hook과 CI의 공통 검사 명령을 호출해야 하며, 도구별로 별도 정책 로직을 복제하지 않는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 작업 지침 + Git hook + CI | 도구와 IDE에 무관한 공통 기준을 유지하고 중복 구현이 없어 채택 |
| B. A안 + Claude Code lifecycle hook | Claude 사용자는 빠르게 피드백을 받지만 Codex와 실행 시점이 달라 제외 |
| C. A안 + Claude/Codex lifecycle hook 각각 구현 | 피드백은 가장 빠르지만 도구별 설정과 이벤트 차이를 이중 관리해야 하므로 제외 |
| D. 도구별 plugin으로 검사와 Skills 통합 배포 | 설치 경험은 좋지만 PoC 범위를 넘는 패키징·배포·호환성 비용으로 보류 |

## 결정 근거

- Git hook과 CI는 AI 도구, 에디터, 수동 개발 여부에 관계없이 같은 저장소 검사를 실행할 수 있다.
- lifecycle hook은 실행 시점이 빠르지만 개발자가 사용하는 도구에 따라 검사 여부가 달라질 수 있어 최종 강제 계층으로 부적합하다.
- 검사 정책을 Git으로 관리되는 공통 스크립트에 집중하면 규칙 변경 시 도구별 설정 drift를 방지할 수 있다.
- PoC에서는 도구별 통합 유지보수보다 명세와 코드의 일관된 병합 기준이 중요하다.

## 영향

- 신규 개발자 온보딩 시 Claude/Codex lifecycle 설정을 별도로 설치하거나 병합할 필요가 없다.
- AI 편집 직후가 아니라 commit 또는 push 시점에 일부 오류가 발견될 수 있다.
- 모든 개발자는 사용 도구와 관계없이 동일한 Git hook과 CI 결과를 기준으로 작업한다.
- CI가 일시적으로 실행되지 않거나 필수 Gate로 연결되지 않은 상태에서는 로컬 hook 우회가 가능하므로, 저장소 운영자는 브랜치 보호 상태를 유지해야 한다.
- 개인 lifecycle hook은 편의 기능으로 사용할 수 있지만 팀 공통 검사 결과를 대체하지 않는다.

## 후속 조치

- 문서 누락이 commit 이전 단계에서 반복되는지 운영 중 관찰한다.
- 팀 표준 AI 도구가 확정되고 안정적인 lifecycle API가 제공되면 도구별 hook 도입 여부를 새 ADR 후보로 재검토한다.
- lifecycle hook을 도입할 경우 기존 `scripts/check-doc-consistency.sh`, `scripts/doc_guard.py` 등 공통 명령을 호출하는 얇은 adapter로 제한한다.
- CI workflow와 브랜치 보호의 필수 검사 연결 상태를 저장소 운영 점검 항목으로 관리한다.

## 관련 문서

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/project-rules.md`
- `governance/README.md`
- `docs/adr/ADR-0034-codex-claude-skills-standardization.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
- `docs/adr/ADR-0075-project-scoped-skills-distribution.md`
