# ADR-0019: Self-hosted Runner 배포 방식

## 상태

Accepted

## 배경

PoC는 Docker Compose 기반으로 실행되며, 개발 VM 또는 온프렘 서버에 배포될 가능성이 있다. 배포 대상이 내부망 또는 제한된 네트워크에 위치하면 GitHub-hosted Runner가 직접 접근하기 어렵거나 보안 정책상 허용되지 않을 수 있다.

GitHub Actions self-hosted runner는 사용자가 관리하는 서버에서 GitHub Actions job을 실행할 수 있게 해준다. 내부망 접근, Docker Compose 실행, 사내 패키지/스토리지 접근에는 유리하지만, runner 머신의 네트워크 접근권과 비밀값이 workflow 실행 권한과 연결되므로 보안 경계가 필요하다.

## 결정

배포는 Self-hosted Runner 기반으로 수행한다.

Pull Request 검증은 GitHub-hosted Runner 또는 Self-hosted Runner를 사용할 수 있지만, 개발 VM, 시연 환경, 온프렘 후보 환경에 실제 배포하는 job은 Self-hosted Runner에서만 실행한다.

| 항목 | 결정 |
| --- | --- |
| 배포 runner | Self-hosted Runner |
| runner 범위 | repository 전용 runner 우선 |
| runner 위치 | 개발 VM 또는 배포 대상 네트워크에 접근 가능한 별도 VM |
| 배포 방식 | ADR-0063 기준 `compose.yml` + `compose.prod.yml` 조합으로 Docker Compose pull/build/up |
| workflow trigger | `main` 병합, tag, 수동 `workflow_dispatch` |
| 환경 승인 | GitHub Environment protection rule 사용 |
| 비밀값 | GitHub Environment secrets 또는 runner 서버 secret으로 최소 주입 |
| runner label | `self-hosted`, `nh-ad-compliance`, `deploy`, 환경별 label |

초기 PoC에서는 개발 VM에 runner를 설치하거나, 개발 VM과 같은 네트워크에 있는 별도 runner VM을 사용한다. 본사업 또는 고객사 온프렘 이전 시에는 고객사 보안 정책에 따라 runner 위치와 네트워크 접근 방식을 재검토한다.

## 배포 흐름

```text
push or manual dispatch
  -> lint/type/unit/API contract tests
  -> build container images
  -> push or load images
  -> self-hosted runner deploy job
  -> docker compose pull/build
  -> docker compose up -d
  -> smoke test
  -> deployment result notification
```

배포 job은 다음 조건을 만족해야 한다.

| 조건 | 기준 |
| --- | --- |
| PR 검증 통과 | lint, type check, unit/API contract test 통과 |
| 배포 환경 승인 | protected environment 승인 필요 |
| 배포 대상 제한 | runner label과 environment로 제한 |
| secret 최소화 | 배포에 필요한 값만 주입 |
| 로그 관리 | secret, 고객사 자료, 원본 파일 내용 출력 금지 |
| 실패 처리 | 이전 컨테이너 유지 또는 rollback 절차 문서화 |

## Runner 운영 기준

| 항목 | 기준 |
| --- | --- |
| runner 등록 단위 | repository 전용 runner를 기본으로 한다. |
| runner group | 조직 runner 사용 시 repository 접근 범위를 제한한다. |
| 실행 계정 | root 직접 실행을 피하고 전용 시스템 계정을 사용한다. |
| Docker 권한 | 필요한 최소 범위로 부여한다. |
| 동시 실행 | PoC는 배포 runner 동시 실행 1개를 기본으로 한다. |
| 네트워크 | GitHub와 outbound HTTPS 통신, 배포 대상 서버 접근만 허용한다. |
| 업데이트 | runner application과 OS 보안 패치를 정기 적용한다. |
| 모니터링 | runner online/offline 상태와 배포 실패를 확인한다. |

Self-hosted Runner는 job 실행 후 깨끗한 VM을 자동 제공하는 방식이 아니다. 따라서 불특정 repository나 외부 기여자의 workflow가 배포 runner에서 실행되지 않도록 runner scope, label, environment approval을 제한한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| GitHub-hosted Runner로 배포 | 관리 부담은 낮지만 내부망/온프렘 접근과 고객사 네트워크 정책 대응이 어렵다. |
| Self-hosted Runner로 배포 | 내부망 접근과 Docker Compose 배포에 적합하지만 runner 보안 운영 책임이 생긴다. |
| 수동 배포 | 초기에는 가능하지만 재현성, 감사 추적, 배포 실수 방지 측면에서 불리하다. |
| 외부 CD 도구 도입 | 기능은 강하지만 PoC 초기 운영 복잡도가 크다. |

## 결정 근거

- 개발 VM 또는 온프렘 후보 서버에 접근해야 할 가능성이 높다.
- Docker Compose 기반 배포 결정과 잘 맞는다.
- 배포 이력, 승인, 로그를 GitHub Actions에 남길 수 있다.
- 수동 배포보다 재현성과 인수인계 가능성이 높다.
- repository 전용 runner와 environment approval을 사용하면 보안 범위를 줄일 수 있다.

## 영향

- Runner 설치, 서비스 등록, 네트워크 접근, secret 주입 절차가 필요하다.
- GitHub Actions workflow에 build job과 deploy job을 분리해야 한다.
- 배포 환경별 label과 environment secret 관리가 필요하다.
- Runner 장애 시 수동 배포 절차 또는 대체 runner가 필요하다.
- 배포 runner는 내부망 접근 권한을 가지므로 운영 보안 점검 대상이 된다.

## 후속 조치

- `.github/workflows/`에 CI workflow와 deploy workflow를 분리해 작성한다.
- `dev`, `stage`, `demo` 등 environment와 protection rule을 정의한다.
- runner label 규칙을 문서화한다.
- 배포용 `.env.prod.example`과 ADR-0063 기준 `compose.prod.yml` 사용 방식을 정리한다.
- runner 설치 및 장애 대응 절차를 운영 가이드에 추가한다.
- 수동 긴급 배포 절차를 fallback으로 문서화한다.

## 관련 문서

- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0008-tdd-and-test-scope.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0063-compose-base-dev-prod-override-policy.md`
- `docs/project-rules.md`
- `docs/adr-candidates.md`

## 참고 자료

- [GitHub Docs: Self-hosted runners](https://docs.github.com/actions/hosting-your-own-runners)
- [GitHub Docs: Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [GitHub Docs: Security hardening for GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
