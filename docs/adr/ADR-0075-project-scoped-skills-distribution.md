# ADR-0075: 프로젝트 범위 Skills 배포 및 온보딩 설치 정책

## 상태

Accepted

## 배경

ADR-0034는 `skills/*/SKILL.md`를 Git 원본으로 관리하고, 온보딩 스크립트가 사용자 홈의 Codex/Claude Skills 디렉터리에 저장소 Skill 심볼릭 링크를 설치하도록 결정했다. 이 방식은 설치가 단순하지만, 프로젝트 전용 Skill이 저장소 밖의 세션에도 노출되고 다른 저장소의 동명 Skill과 충돌할 수 있다. 또한 개발자가 여러 프로젝트에 참여하면 사용자 홈의 링크와 원본 저장소 수명주기를 별도로 관리해야 한다.

Codex와 Claude Code는 각각 저장소 범위의 `.agents/skills`, `.claude/skills`를 탐색할 수 있다. 프로젝트 문서와 개발 규칙은 Git 저장소를 source of truth로 사용하므로, Skills도 사용자 전역이 아니라 해당 저장소 범위에서만 활성화하는 편이 문서 거버넌스 원칙과 맞는다.

## 결정

프로젝트 Skills는 `skills/`를 사람이 수정하는 유일한 원본으로 유지하고, 온보딩 시 프로젝트 로컬 탐색 경로에 adapter를 생성한다. 사용자 홈 Skills 디렉터리에는 설치하지 않는다.

| 항목 | 결정 |
| --- | --- |
| Skills 단일 원본 | `skills/*/SKILL.md` |
| Codex adapter | `.agents/skills/<skill-name>` |
| Claude Code adapter | `.claude/skills/<skill-name>` |
| 설치 명령 | `scripts/setup-dev-tools.sh` |
| 기본 adapter 방식 | 원본을 가리키는 프로젝트 내부 상대 심볼릭 링크 |
| 심볼릭 링크 불가 환경 | 원본 복사본과 source hash를 저장하는 copy fallback |
| 생성물 관리 | `.agents/skills/`, `.claude/skills/`는 Git에서 제외 |
| 정합성 검사 | 로컬 Git hook에서 adapter 누락, 잘못된 링크, copy hash drift를 차단 |
| 경로 안전성 | 저장소 밖을 가리키는 source/adapter 심볼릭 링크를 거부하고 adapter 실경로를 확인 |
| 사용자 홈 설치 | 중단. 기존 사용자 홈 링크의 자동 삭제는 하지 않음 |

## 설치 및 검증 규칙

1. `scripts/setup-dev-tools.sh`는 저장소 루트의 모든 유효한 `skills/*/SKILL.md`를 탐색한다.
2. adapter는 프로젝트 내부 상대 심볼릭 링크로 설치하여 저장소가 이동해도 같은 디렉터리 구조 안에서 유효하도록 한다.
3. 심볼릭 링크를 생성할 수 없거나 copy 모드를 명시한 환경에서는 Skill 디렉터리를 복사하고 원본 content hash를 기록한다.
4. `skills/` 자체, 개별 Skill 디렉터리와 그 내부에는 심볼릭 링크나 FIFO/socket/device 같은 특수 파일을 허용하지 않는다. 디렉터리와 일반 파일만 canonical source 및 copy hash 입력으로 사용한다.
5. `.agents`, `.claude`와 각 `skills` adapter root가 심볼릭 링크이면 설치·검증을 거부하고, 실제 경로가 저장소 내부의 기대 경로와 같은지 확인한 뒤에만 생성·삭제한다.
6. 설치 스크립트는 자신이 생성한 adapter만 갱신한다. 관리 표식이 없는 기존 파일이나 디렉터리와 충돌하면 덮어쓰지 않고 실패한다.
7. 갱신할 adapter 후보의 source identity와 content/mode hash를 검증한 뒤 같은 adapter root 안에서 교체한다. 후보 생성이나 활성화에 실패하면 기존 adapter를 보존하거나 복원한다.
8. pre-commit과 pre-push는 프로젝트 로컬 adapter를 검증한다. symlink는 원본 경로를, copy fallback은 원본과 기록된 content/mode hash를 비교한다.
9. Skill이 추가·삭제되거나 원본이 변경되면 설치 스크립트를 다시 실행해 두 도구의 adapter를 동기화한다.
10. CI는 Git에서 제외된 로컬 adapter 존재를 요구하지 않는다. 원본 Skills와 설치·검증 로직의 자동 테스트만 수행한다.
11. ADR-0034의 Skills 표준화, Git 원본 관리, Git hook 설치, 개발자 최종 책임 원칙은 유지하고 사용자 홈 설치 결정만 본 ADR로 대체한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 사용자 홈 심볼릭 링크 유지 | 설치는 단순하지만 프로젝트 밖 노출, 저장소 간 이름 충돌, 사용자 홈 정리 부담이 있어 제외 |
| B. 단일 원본과 프로젝트 로컬 adapter 사용 | 프로젝트 격리와 단일 원본을 함께 만족하므로 채택 |
| C. 두 프로젝트 경로에 완전한 복사본을 Git으로 관리 | clone 즉시 탐색되지만 중복 원본과 drift 위험이 있어 제외 |
| D. Codex/Claude plugin 또는 registry로 배포 | 배포 통제와 확장성은 좋지만 PoC 단계의 패키징·호환성 비용이 커서 보류 |

## 결정 근거

- 프로젝트 전용 규칙은 해당 저장소 안에서만 활성화하는 것이 최소 범위 원칙에 맞다.
- `skills/` 단일 원본을 유지하면 Codex와 Claude Code용 문서가 서로 달라지는 문제를 방지할 수 있다.
- 프로젝트 로컬 adapter는 여러 저장소의 동명 Skill 충돌과 사용자 홈 오염을 제거한다.
- 상대 심볼릭 링크는 중복 없이 즉시 원본 변경을 반영하고, copy/hash fallback은 심볼릭 링크 제약이 있는 환경을 지원한다.
- 로컬 hook 검증은 copy fallback의 drift와 잘못된 adapter를 commit 전에 발견한다.

## 영향

- 신규 개발자는 저장소 clone 후 `scripts/setup-dev-tools.sh`를 실행한다.
- Codex는 `.agents/skills`, Claude Code는 `.claude/skills`에서 이 저장소의 Skills를 탐색한다.
- 기존 사용자 홈의 `nh-ad-compliance-*` 링크는 새 설치 과정에서 사용되지 않는다. 사용자가 다른 작업에 쓰고 있을 수 있으므로 자동 삭제하지 않는다.
- adapter 생성물은 Git diff와 PR에 포함하지 않고, 원본 `skills/`와 설치·검증 코드만 리뷰한다.
- 심볼릭 링크가 불가능한 환경에서는 Skill 변경 후 setup 재실행이 필요하며, 실행하지 않으면 Git hook이 drift를 보고한다.

## 후속 조치

- 팀의 Windows 및 제한된 파일시스템 사용 여부가 확정되면 copy fallback 사용 빈도와 지원 절차를 점검한다.
- Codex/Claude의 프로젝트 Skills 탐색 규격이 변경되면 adapter 경로와 설치 스크립트를 함께 갱신한다.
- 조직 공통 Skills 배포가 필요해지면 프로젝트 범위 정책과 분리하여 plugin 또는 registry 도입을 별도 ADR로 검토한다.

## 관련 문서

- `README.md`
- `docs/project-rules.md`
- `docs/adr/ADR-0031-ai-assisted-development-responsibility.md`
- `docs/adr/ADR-0034-codex-claude-skills-standardization.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
