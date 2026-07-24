# CI 및 self-hosted Compose 배포 운영 가이드

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.4 |
| 기준일 | 2026-07-24 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.4 | 2026-07-24 | 조직 공유 러너(org-ci/org-build/org-deploy) 이전과 SSH release 배포 완료를 반영해 전면 개정. 과거 runner-local·`DEPLOY_ENV_FILE` 서술 제거, rollback은 best-effort 자동 복구 시도로 정확화, production job은 비활성 코드 스켈레톤(env 경계 미구현)으로 명시, 폐쇄망 반입 기준선 참조를 ADR-0082+Q77로 정정, 러너/호스트 필수 도구(rsync 등) 반영. 릴리스 게이트·외부 AI 평가 workflow 표시명을 역할 중심(M8 접두어 제거)으로 정리한 것과 정합 |
| v1.3 | 2026-07-23 | 조직 공유 러너(org-ci/org-build/org-deploy) 도입과 SSH release 배포 전환을 반영해 label 표를 갱신하고 후속 전면 개정 범위를 명시 |
| v1.2 | 2026-07-23 | `workflow_run` development 자동 배포에 push·dev 브랜치·동일 저장소 source 가드 조건을 명시 |
| v1.1 | 2026-07-22 | 결정적 CI·문서 동기화·수동 외부 AI 평가를 GitHub-hosted runner로 전환하고 배포 runner만 self-hosted로 유지 |
| v1.0 | 2026-07-21 | Self-hosted CI·Compose CD runner 등록, Environment 설정, 배포·rollback 절차를 최초 작성 |

## 목적

검증된 `dev` revision을 조직 공유 self-hosted 러너에서 **SSH release 방식**으로 개발(development) VM에 배포한다. 이 문서는 러너 label·GitHub 설정·배포 흐름·rollback의 운영 절차를 제공한다. 권위 기준은 [프로젝트 규칙 §10.4.1](project-rules.md)과 워크플로(`.github/workflows/ci.yml`, `.github/workflows/deploy-compose.yml`, `scripts/deploy-ssh.sh`)이며, 이 문서는 그 운영 절차를 정리한다. 비밀값 자체는 GitHub, 문서, 로그에 기록하지 않는다.

## 러너 분리와 label

CI·빌드·배포는 모두 조직 공유 self-hosted 러너에서 실행하고, 인터넷 아웃바운드가 필요한 보조 워크플로만 GitHub-hosted `ubuntu-latest`를 유지한다([ADR-0080](adr/ADR-0080-self-hosted-runner-compose-cd-policy.md)).

| 용도 | 워크플로 | 러너 label | 권한 |
| --- | --- | --- | --- |
| 결정적 CI | `Product CI`(`ci.yml`) 품질·DB 권한 probe | `self-hosted`, `linux`, `x64`, `org-ci`, `large` | checkout·테스트·정적 검증. 운영 `.env`·배포 자격 접근 금지 |
| 이미지 빌드·Compose smoke | `Product CI` compose-and-health, 릴리스 게이트 recovery | `self-hosted`, `linux`, `x64`, `org-build`, `large` | 이미지 build·ephemeral Compose smoke |
| 배포 | `Self-hosted Compose CD`(`deploy-compose.yml`) | `self-hosted`, `linux`, `x64`, `org-cg-rookies`, `org-deploy` | `DEPLOY_SSH_KEY`로 `DEPLOY_HOST`에 SSH 접속, 대상 호스트의 `DEPLOY_PATH`·`env/.env.dev`만 사용 |
| 문서 거버넌스 | `Document Governance` | GitHub-hosted `ubuntu-latest` | 저장소 checkout만 |
| Notion 동기화 | `Notion Docs Sync` | GitHub-hosted `ubuntu-latest` | Notion environment secret만 |
| 수동 외부 AI 평가 | `Manual External AI Evaluation` | GitHub-hosted `ubuntu-latest` | 승인된 external AI environment secret만 |

CI·빌드 러너는 배포 러너의 OS 계정·SSH 키·대상 호스트 환경 파일에 접근하지 않는다.

## GitHub 설정

### Environment

1. Settings > Environments에서 `development`, `production`을 만든다.
2. **현재 두 environment 모두 protection rule(required reviewer 등)이 설정돼 있지 않다.** production 승인 통제가 필요하면 지원 플랜·정책 확정 후 required reviewer를 활성화한다. 그전까지 production job은 아래 [§production](#production-현재-비활성) 조건과 미설정 `DEPLOY_PATH` 실패로만 제한된다.

### Variables / Secrets

배포 대상·경로·계정은 **variable**로, 자격·호스트 키는 **secret**으로 주입한다(값은 문서에 남기지 않는다).

| 키 | 종류 | 용도 |
| --- | --- | --- |
| `DEPLOY_HOST` | variable | 대상 VM 호스트명/주소 |
| `DEPLOY_USER` | variable | 대상 VM SSH 계정 |
| `DEPLOY_PORT` | variable | SSH 포트(미설정 시 22) |
| `DEPLOY_PATH` | variable | 대상 VM 배포 루트(절대 경로). 초기 placeholder `change`는 실제 경로로 교체해야 실행됨 |
| `DEPLOY_SSH_KEY` | secret | 배포용 SSH private key(ssh-agent에 로드) |
| `DEPLOY_KNOWN_HOSTS` | secret | 대상 호스트 공개키 고정값. 미설정 시 `ssh-keyscan` TOFU로 경고와 함께 대체 |
| `MATTERMOST_WEBHOOK_URL` | secret | 배포 성공/실패 알림 webhook(미설정 시 알림 skip) |

## 대상 호스트 준비

배포 대상 VM에는 Docker Engine·Docker Compose v2·`rsync`가 있어야 하며, 배포 계정에만 Docker socket 접근을 부여한다(root shell·광범위 sudo 금지). 배포 러너에는 `git`·`bash`·`ssh-agent`/`ssh`·`rsync`가 필요하고, Mattermost 알림을 쓰면 `jq`·`curl`도 필요하다. `DEPLOY_PATH` 아래 배포 레이아웃은 다음과 같다.

```text
$DEPLOY_PATH/app                 -> releases/<sha>   (현재 release symlink)
$DEPLOY_PATH/releases/<sha>/     (release별 소스 체크아웃; .release_tag 보관)
$DEPLOY_PATH/env/.env.dev        (공유 환경 파일, 0600, 체크아웃 바깥)
```

- `env/.env.dev`에는 OpenAI key, DB credential 등 비밀값이 들어갈 수 있으므로 권한 `0600`으로 보호하고 release 체크아웃 바깥에 둔다.
- 이 파일이 없으면 배포는 사전 조건 검사에서 실패한다.

## development 배포 흐름

1. `feature/*`/`docs/*` PR을 `dev`에 병합한다.
2. `Product CI`가 org 러너에서 통과한다.
3. `Self-hosted Compose CD`가 Product CI의 성공한 head SHA를 checkout하고, `org-deploy` 러너에서 `scripts/deploy-ssh.sh`를 실행한다.
   - `DEPLOY_PATH/releases/<sha>`로 소스를 `rsync`한다.
   - 이미지는 **커밋 SHA 태그(`RELEASE_TAG=<sha>`, `IMAGE_PREFIX=nh-ad-compliance`)** 로 빌드해 release마다 불변 이미지를 남긴다.
   - `docker compose -p nh-ad-dev -f compose.yml -f compose.prod.yml --env-file $DEPLOY_PATH/env/.env.dev up -d --remove-orphans --wait`로 health가 통과할 때까지 기동한다(기본 `--wait-timeout 600`).
   - health 통과 후에만 `app` 심볼릭 링크를 새 release로 **원자적 교체**한다.
   - 오래된 release는 최신 `KEEP_RELEASES`(기본 5)개만 남기고 해당 SHA 이미지와 함께 정리한다.
4. 결과를 `MATTERMOST_WEBHOOK_URL`로 알린다.

공용 개발 VM은 production runtime profile(`compose.prod.yml`: Nginx 정적 번들 + production image)로 실행하며, source mount·Vite hot reload 전용 `compose.dev.yml`은 로컬 개발에만 사용한다. 환경 파일의 DB·object storage·Qdrant·OpenSearch namespace는 [ADR-0063](adr/ADR-0063-compose-base-dev-prod-override-policy.md) 기준으로 분리한다.

### `workflow_run` 자동 배포 가드

신뢰되지 않은 코드가 배포 러너에서 실행되지 않도록, 자동 배포는 다음 조건을 **모두** 만족할 때만 발동한다(GitHub secure-use 권고).

- `workflow_run.conclusion == 'success'`
- `workflow_run.event == 'push'` (PR 트리거 실행은 배포하지 않음)
- `workflow_run.head_branch == 'dev'`
- `workflow_run.head_repository.full_name == github.repository` (fork 실행 배제)

수동 배포가 필요하면 Actions에서 `Self-hosted Compose CD`를 `workflow_dispatch`로 실행하고 `environment=development`, 배포할 commit SHA를 입력한다.

## rollback

- **자동(best-effort):** 새 release가 health를 통과하지 못하면 심볼릭 링크를 교체하지 않고, 이전 release가 기록한 이미지 태그(`<release>/.release_tag`, 없으면 legacy `dev`)로 서비스 복구를 **시도**한 뒤 workflow를 실패 처리한다. 복구 단계는 실패를 무시(`|| true`)하므로 복구 성공을 보장하지 않는다 — 복구 자체가 실패하면 대상 호스트에서 수동 확인이 필요하다.
- **수동:** 이전에 검증된 commit SHA를 `workflow_dispatch`로 다시 배포하면 해당 SHA의 불변 이미지로 되돌아간다.

## production (현재 비활성)

production은 NH 내부 폐쇄망 **수동 반입** 대상이며 자동 배포하지 않는다(`main` 릴리스 기준선은 [ADR-0082](adr/ADR-0082-development-default-branch-dev.md), 폐쇄망 반입 릴리스 전략은 Q77 결정 대기 — [decision-questions](adr/decision-questions.md), [프로젝트 규칙 §10.4.1](project-rules.md)). 워크플로의 production job은 **아직 production-ready 구현이 아닌 비활성 코드 스켈레톤**이다 — `scripts/deploy-ssh.sh`는 항상 대상 호스트의 `env/.env.dev`를 사용하고 production job은 `COMPOSE_PROJECT=nh-ad-prod`만 바꿀 뿐 production 전용 env 경계를 선택하지 못한다. 따라서 **현재 실행·활성화를 금지**하며, 별도 production 배포 계약과 env 경계를 구현한 뒤에만 사용한다(형식적 실행 조건: `workflow_dispatch` + `environment=production` + 확인 문자열 `DEPLOY_PRODUCTION`, production variable 실제 값 설정). 오프라인 번들·SBOM·SHA-256 checksum 등 폐쇄망 반입 artifact 파이프라인은 Q77 확정 이후 구현한다.

## 점검 및 장애 대응

- 배포 사전 조건(Docker·Docker Compose·공유 env 파일 존재)은 `scripts/deploy-ssh.sh`가 대상 호스트에서 자동 확인하며, 누락 시 배포를 중단한다.
- workflow 실패 시 Actions log에는 service 이름과 health 상태만 노출하고 `.env` 내용이나 container environment는 출력하지 않는다.
- 원인 분석이 필요하면 대상 호스트의 제한된 운영 계정으로 `docker compose -p nh-ad-dev ... logs`를 확인한다.

## 참고

- 권위 기준: [프로젝트 규칙 §10.4.1](project-rules.md), [ADR-0080](adr/ADR-0080-self-hosted-runner-compose-cd-policy.md)
- 워크플로/스크립트: `.github/workflows/deploy-compose.yml`, `scripts/deploy-ssh.sh`
