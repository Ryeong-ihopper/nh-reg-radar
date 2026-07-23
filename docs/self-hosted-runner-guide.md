# GitHub-hosted CI 및 Self-hosted Compose 배포 운영 가이드

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.3 |
| 기준일 | 2026-07-23 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.3 | 2026-07-23 | 조직 공유 러너(org-ci/org-build/org-deploy) 도입과 SSH release 배포 전환을 반영해 label 표를 갱신하고 후속 전면 개정 범위를 명시 |
| v1.2 | 2026-07-23 | `workflow_run` development 자동 배포에 push·dev 브랜치·동일 저장소 source 가드 조건을 명시 |
| v1.1 | 2026-07-22 | 결정적 CI·문서 동기화·수동 외부 AI 평가를 GitHub-hosted runner로 전환하고 배포 runner만 self-hosted로 유지 |
| v1.0 | 2026-07-21 | Self-hosted CI·Compose CD runner 등록, Environment 설정, 배포·rollback 절차를 최초 작성 |

## 목적

검증된 `dev` revision을 조직 공유 self-hosted runner에서 **SSH release 방식**으로 development VM에 배포한다. 이 문서는 runner label·GitHub 설정·배포 흐름의 운영 절차를 제공한다. 비밀값 자체는 GitHub, 문서, 로그에 기록하지 않는다.

> 개정 예정: 인프라팀의 조직 공유 러너(`org-ci`/`org-build`/`org-deploy`) 도입과 SSH release 배포로 전환되어(project-rules §10.4.1, `deploy-compose.yml`, `scripts/deploy-ssh.sh` 기준) 아래 일부 절 중 runner-local·`DEPLOY_ENV_FILE` 서술은 후속 전면 개정에서 정리한다. 현행 유효 기준은 §10.4.1과 워크플로다.

## Runner 분리와 label

| 용도 | 필수 label | 권한 |
| --- | --- | --- |
| 결정적 CI | `org-ci`, `large` (전환 전 GitHub-hosted `ubuntu-latest`) | checkout, Docker build/ephemeral Compose smoke. 운영 `.env` 접근 금지 |
| Build | `org-build`, `large` | 이미지 build·push |
| 문서 동기화 | GitHub-hosted `ubuntu-latest` | Notion environment secret만 접근 |
| 실제 외부 AI 평가 | GitHub-hosted `ubuntu-latest` | 승인된 external AI environment secret만 접근 |
| 개발/운영 배포 | `self-hosted`, `linux`, `x64`, `org-cg-rookies`, `org-deploy` | `DEPLOY_SSH_KEY`로 `DEPLOY_HOST`에 SSH 접속, 대상 호스트의 `DEPLOY_PATH`·`env/.env.dev`만 사용 (운영 job은 비활성 보존) |

GitHub-hosted CI는 deployment runner의 OS 계정·Docker daemon·환경 파일에 접근하지 않는다.

## Host 사전 조건

Self-hosted deployment runner OS 계정에는 GitHub Actions runner, `git`, `bash`, `timeout`, Docker Engine 및 Docker Compose v2가 필요하다. Docker socket 접근은 해당 runner 계정에만 부여하고, root shell·광범위 sudo 권한은 부여하지 않는다. GitHub-hosted runner에는 별도 사내 runner 설치나 Docker 권한 부여가 필요 없다.

```bash
git --version
docker version
docker compose version
psql --version
```

GitHub repository Settings > Actions > Runners에서 deployment runner를 등록하고 해당 label을 추가한다. CI의 `actions/setup-*` 단계와 GitHub-hosted image가 Python, Node, uv, Docker/Compose를 제공한다.

## GitHub Environment 설정

1. Settings > Environments에서 `development`, `production`을 만든다.
2. `production`에는 required reviewer를 설정한다. `development`에는 필요 시 팀 승인 규칙을 적용한다.
3. 각 environment variable에 해당 runner에서만 유효한 절대 경로를 저장한다.

```text
DEPLOY_ENV_FILE=/srv/nh-ad-compliance/env/.env.dev
# production runner:
DEPLOY_ENV_FILE=/srv/nh-ad-compliance/env/.env.prod
```

경로는 예시일 뿐이며, `.env` 파일에는 OpenAI key, DB credential 등 비밀값을 저장할 수 있다. 해당 파일은 runner-local 권한 `0600`으로 보호하고 repository checkout 바깥에 둔다.

## 배포 흐름

1. `feature/*` PR을 `dev`에 병합한다.
2. `Product CI`와 문서 거버넌스가 GitHub-hosted runner에서 통과한다.
3. `Self-hosted Compose CD`가 Product CI의 성공한 head SHA를 checkout하여 development Compose를 배포한다.
4. production은 Actions에서 `Self-hosted Compose CD`를 수동 실행하고 target `production`, 검증된 commit SHA, 확인 문자열 `DEPLOY_PRODUCTION`을 입력한다. GitHub Environment 승인을 받은 뒤에만 실행된다.
5. rollback은 이전에 검증된 commit SHA를 같은 production workflow에 입력해 재배포한다.

배포 workflow는 `docker compose -p nh-ad-dev` 또는 `nh-ad-prod` namespace와 `compose.yml` + `compose.prod.yml` runtime 조합으로 실행한다. development도 장기 실행 VM에서는 source mount·Vite hot reload를 쓰는 `compose.dev.yml`을 사용하지 않는다. 환경 파일의 DB, object storage, Qdrant, OpenSearch namespace는 ADR-0063 기준으로 분리되어야 한다.

`workflow_run` 기반 development 자동 배포는 신뢰되지 않은 코드가 self-hosted runner에서 실행되지 않도록 다음 조건을 모두 만족할 때만 발동한다. 이 가드는 GitHub의 secure-use 권고에 따른다.

- `workflow_run.conclusion == 'success'`
- `workflow_run.event == 'push'` (PR 트리거 실행은 배포하지 않음)
- `workflow_run.head_branch == 'dev'`
- `workflow_run.head_repository.full_name == github.repository` (fork 실행 배제)

## 점검 및 장애 대응

runner에서 다음 명령으로 배포 전 사전 조건을 확인한다.

```bash
DEPLOY_ENV_FILE=/srv/nh-ad-compliance/env/.env.dev \
  scripts/ci/verify_self_hosted_runner.sh --deployment
```

workflow 실패 시 Actions log에는 service 이름과 health 상태만 확인하고, `.env` 내용이나 container environment를 출력하지 않는다. 원인 분석이 필요하면 해당 환경의 제한된 운영 계정으로 Compose logs를 확인한다. 자동 rollback은 하지 않으며, 검증된 이전 revision을 재배포한다.
