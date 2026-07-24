# ADR-0080: GitHub-hosted CI 및 Self-hosted Compose CD 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-21 |
| 관련 문서 | 프로젝트 규칙, 테스트케이스, Docker Compose 운영 가이드 |
| 관련 ADR | ADR-0063, ADR-0064, ADR-0077, ADR-0082, ADR-0083 |

> 개정(2026-07-23): 인프라팀의 조직 공유 러너 도입에 따라 development 배포 실행 방식을 **runner-local Docker에서 조직 공유 러너(`org-cg-rookies`, `org-deploy`)의 SSH release 배포로 변경**한다. 러너가 `DEPLOY_HOST`에 SSH 접속해 `DEPLOY_PATH/releases/<sha>`에 배포하고 health 확인 후 `app` 심볼릭 링크를 교체한다. 결정적 CI·Build는 `org-ci`/`org-build`로 이전(비용·인프라 관리)한다. production 자동 배포 job은 비활성 보존하며 실제 운영은 NH 폐쇄망 수동 반입(`main` 릴리스 기준선 ADR-0082, 반입 전략 Q77 결정 대기)을 사용한다. 아래 원문의 runner-local·`DEPLOY_ENV_FILE` 서술은 이 개정으로 대체된다. 현행 기준은 project-rules §10.4.1과 `deploy-compose.yml`/`scripts/deploy-ssh.sh`다.
>
> 개정(2026-07-25): 원문 검증·후속의 `scripts/ci/verify_self_hosted_runner.sh`(runner-local Docker·`DEPLOY_ENV_FILE` 사전점검)는 SSH release 모델과 맞지 않고 어떤 워크플로도 호출하지 않아 제거한다. 배포 사전 조건(Docker·Compose·대상 호스트 공유 env 파일 존재)은 `scripts/deploy-ssh.sh`가 대상 호스트에서 검증한다. 원문의 `nh-ad-deploy-dev`/`nh-ad-deploy-prod` 라벨 서술도 실제 `org-cg-rookies`/`org-deploy` 라벨로 대체된다.

## 배경

이 서비스는 private parser/OCR 이미지와 개발·운영 Compose 환경을 사용한다. CI는 공개 인터넷에서 재현 가능한 provider-free 검증만 수행하므로 GitHub-hosted runner에서 격리 실행할 수 있다. 반면 실제 배포는 내부망 Docker socket과 runner-local 환경 파일 접근이 필요하다. CI와 배포 runner를 같은 권한으로 운영하면 PR 코드가 배포 Docker와 비밀값에 접근할 수 있다.

## 결정

1. 결정적 CI는 GitHub-hosted `ubuntu-latest`에서 실행한다. CI job은 ephemeral Docker Compose를 사용할 수 있지만 운영 환경 파일과 deployment runner label을 보유하지 않는다.
2. Notion 동기화와 credentialed 외부 AI 평가도 GitHub-hosted `ubuntu-latest`에서 실행하며, 각각 필요한 GitHub Environment/repository secret만 job 범위로 주입한다.
3. `dev` push의 Product CI 성공 후에만 `nh-ad-deploy-dev` runner가 development Compose를 배포한다. workflow는 완료된 CI의 정확한 head SHA를 checkout한다.
4. production Compose 배포는 자동 실행하지 않는다. `workflow_dispatch`, GitHub `production` environment 승인, `DEPLOY_PRODUCTION` 확인 문자열, `nh-ad-deploy-prod` 전용 runner가 모두 필요하다.
5. 배포 환경 파일은 runner의 절대 경로에만 보관한다. GitHub Environment variable `DEPLOY_ENV_FILE`에는 경로만 저장하며, `.env.*`, API key, DB credential은 repository, Actions log, artifact에 저장하지 않는다.
6. 배포는 `scripts/deploy-compose.sh`를 통해 `docker compose -p nh-ad-dev|nh-ad-prod -f compose.yml -f compose.prod.yml ... up -d --build --wait`로 실행하고, 필수 서비스 health를 확인한다. development도 hot-reload용 `compose.dev.yml`이 아닌 production-style runtime을 사용하되 dev namespace와 환경 파일을 유지한다. 실패 시 workflow는 중단하며 자동 rollback은 수행하지 않는다. rollback은 이전 검증 commit을 명시해 재배포한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| GitHub-hosted runner만 사용 | 실제 내부망 Compose 배포와 runner-local secret 보관에 맞지 않아 제외 |
| CI와 production 배포를 동일 runner에서 실행 | PR 코드의 Docker/비밀값 접근 범위가 넓어져 제외 |
| main push에서 production 자동 배포 | 승인과 운영 관찰 없이 운영 상태를 변경하므로 제외 |
| GitHub-hosted CI와 환경별 전용 deployment runner | CI 인프라 운영 부담을 없애고, 실제 환경 접근은 배포 runner로 한정해 채택 |

## 영향

- CI는 GitHub-hosted runner에서 즉시 실행되며, deployment runner 등록 전에는 배포 job만 대기한다.
- GitHub repository에는 `development`, `production` environment를 만들고 production required reviewer를 설정해야 한다.
- `dev`가 개발 통합 브랜치이므로 기존 workflow의 잘못된 `develop` push trigger를 `dev`로 정정한다.
- GitOps 전환 후에는 Compose CD를 GitOps manifest PR 생성으로 대체하며, production 배포 승인·immutable revision·rollback 원칙은 유지한다.

## 검증 및 운영

- `scripts/ci/verify_self_hosted_runner.sh`가 Docker Engine, Compose, deployment 환경 파일의 절대 경로·존재 여부를 검증한다.
- `scripts/deploy-compose.sh --environment dev|prod`는 Compose config, `--wait`, frontend/backend/worker와 데이터·검색 서비스 health를 검증한다.
- self-hosted runner 등록과 GitHub Environment/변수 설정은 `docs/self-hosted-runner-guide.md`를 따른다.

## 후속 조치

- GitHub repository에는 `nh-ad-deploy-dev`, `nh-ad-deploy-prod` label의 deployment runner만 등록한다. CI·문서 동기화·수동 외부 AI 평가는 GitHub-hosted runner를 사용한다.
- `development`, `production` GitHub Environment와 production required reviewer를 구성한다.
- 각 deployment runner에 권한 제한된 runner-local 환경 파일을 만들고 `DEPLOY_ENV_FILE` environment variable에 절대 경로만 등록한다.
- 첫 development 배포에서 Compose health와 환경별 namespace 격리를 확인하고, production 배포 전에는 수동 release smoke를 수행한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/test-cases.md`
- `docs/self-hosted-runner-guide.md`
- `.github/workflows/ci.yml`
- `.github/workflows/deploy-compose.yml`
