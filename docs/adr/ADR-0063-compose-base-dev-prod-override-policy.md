# ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책

## 상태

Accepted

## 배경

ADR-0007에서 PoC의 기본 빌드 및 배포 방식은 Docker Compose 기반으로 결정했고, ADR-0020에서 PoC 환경은 `dev`와 `prod(main)` 두 개로 분리하기로 결정했다. 또한 ADR-0033은 로컬 개발과 공용 개발 VM을 병행한다고 정의한다.

그러나 실제 Compose 파일을 하나로 둘지, 환경별로 완전히 분리할지, 공통 파일과 override 파일로 나눌지는 아직 확정되지 않았다. 이 기준이 없으면 개발자 온보딩, 공용 개발 VM 배포, `prod(main)` 시연 환경, 온프렘 이전 후보 환경의 실행 방식이 서로 달라질 수 있다.

## 결정

Docker Compose 구성은 **공통 `compose.yml` + 환경별 `compose.dev.yml`, `compose.prod.yml` override 파일**로 관리한다.

| 항목 | 결정 |
| --- | --- |
| 공통 파일 | `compose.yml` |
| dev override | `compose.dev.yml` |
| prod(main) override | `compose.prod.yml` |
| 환경 변수 샘플 | `.env.example`, `.env.dev.example`, `.env.prod.example` |
| 실제 환경 변수 | `.env.dev`, `.env.prod` 등 실제 비밀값 파일은 Git 커밋 금지 |
| dev 실행 | `docker compose -f compose.yml -f compose.dev.yml --env-file .env.dev up -d` |
| prod(main) 실행 | `docker compose -f compose.yml -f compose.prod.yml --env-file .env.prod up -d` |
| 설정 검증 | dev/prod 조합 각각 `docker compose ... config`로 검증 |

## 파일별 책임

| 파일 | 책임 |
| --- | --- |
| `compose.yml` | 서비스 이름, 네트워크, 기본 의존성, 공통 healthcheck, 공통 volume 선언 |
| `compose.dev.yml` | 개발 편의 설정, 소스 볼륨 마운트, hot reload, 개발 포트 노출, mock/fixture 사용, dev seed 실행 |
| `compose.prod.yml` | `prod(main)` 실행 설정, 빌드된 이미지 또는 release tag, restart policy, 영속 volume, 리소스 제한, 외부 노출 최소화 |
| `.env.example` | 모든 환경에서 필요한 변수 이름과 설명 |
| `.env.dev.example` | dev 기본값, 샘플/fixture 경로, dev 리소스 이름 |
| `.env.prod.example` | `prod(main)` 기본값, 승인 샘플/검증셋 기준 리소스 이름 |

`compose.yml`은 환경별 값을 직접 포함하지 않는다. DB 이름, bucket, Qdrant collection, OpenSearch index, Redis prefix, CORS origin, 외부 AI/OCR/RAG endpoint, secret은 env 파일 또는 배포 환경의 secret 주입으로 관리한다.

## 서비스 구성 기준

공통 Compose의 기본 서비스 단위는 다음과 같다.

| 서비스 | 기준 |
| --- | --- |
| `frontend` | React/Vite 웹 UI |
| `backend` | FastAPI API 서버 |
| `worker` | OCR, parser, RAG, LLM 비동기 작업 |
| `postgres` | PostgreSQL |
| `redis` | Queue 및 cache |
| `minio` | S3 호환 object storage |
| `qdrant` | 벡터 검색 |
| `opensearch` | 키워드/정확 검색 |
| `nginx` | Reverse proxy. 필요 시 사용 |

OCR 또는 문서 파서가 별도 런타임, GPU, 라이선스, 리소스 제약을 요구하는 경우 `worker` 내부 adapter로 시작하되, 필요 시 `ocr-worker` 또는 `parser-worker` 서비스로 분리할 수 있다. 이 경우에도 업무 로직은 ADR-0014의 parser/OCR adapter 경계를 통해 호출한다.

## 환경별 차이

| 항목 | `compose.dev.yml` | `compose.prod.yml` |
| --- | --- | --- |
| 코드 반영 | source mount, hot reload 허용 | 빌드된 image 또는 release tag 사용 |
| seed | 공통 seed + dev seed 허용 | 공통 seed만 기본. 검증 데이터 import는 별도 승인 절차 |
| mock/fixture | ADR-0044 기준 mock/fixture 활성화 가능 | 기본 비활성. 필요한 경우 명시 설정 |
| 포트 노출 | 개발 편의를 위해 제한적 직접 노출 허용 | reverse proxy 중심, 내부 서비스 직접 노출 최소화 |
| volume | 개발 초기화 편의 허용 | 영속 volume 및 백업 대상 명확화 |
| restart | 선택 | `unless-stopped` 등 재시작 정책 적용 |
| resource limit | 관찰 기준으로 적용 가능 | OpenSearch, Qdrant, worker 중심으로 적용 |
| project name | `nh-ad-dev` | `nh-ad-prod` |

`prod(main)`은 상용 운영 환경이 아니라 PoC 시연과 검증 기준 환경이다. 다만 온프렘 이전 가능성을 검증해야 하므로 실행 방식은 개발 편의보다 재현성, secret 분리, 영속 volume, healthcheck, smoke test를 우선한다.

## 검증 기준

Compose 파일 변경 PR은 [ADR-0064: CI/CD 검증 Gate 및 테스트 실행 분리 정책](ADR-0064-ci-cd-quality-gate-test-split-policy.md)에 따라 최소한 다음 검증을 수행한다.

```bash
docker compose -f compose.yml -f compose.dev.yml --env-file .env.dev.example config
docker compose -f compose.yml -f compose.prod.yml --env-file .env.prod.example config
```

공용 개발 VM 또는 배포 후보 환경에서는 다음을 추가로 확인한다.

| 검증 | 기준 |
| --- | --- |
| dev 전체 스택 기동 | 주요 서비스 container가 healthy 또는 running 상태 |
| prod(main) smoke test | backend health check, frontend 접근, DB 연결, Redis 연결 |
| 검색 인프라 상태 | Qdrant/OpenSearch health check |
| 파일 저장소 상태 | MinIO bucket 접근 가능 |
| 데이터 분리 | ADR-0020 기준 DB, bucket, collection, index, Redis prefix 분리 |

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 단일 `compose.yml`과 `.env`만 사용 | 초기에는 단순하지만 dev/prod 차이가 커질수록 조건과 주석이 늘어나고 실수 위험이 커져 기각 |
| B. 공통 `compose.yml` + `compose.dev.yml`, `compose.prod.yml` override | 공통 서비스 정의를 재사용하면서 환경별 차이를 명확히 분리할 수 있어 채택 |
| C. `compose.dev.yml`, `compose.prod.yml` 완전 분리 | 환경별 명확성은 높지만 서비스 정의 중복과 정합성 유지 부담이 커져 기각 |
| D. 단일 파일 profile 기반 분기 | 파일 수는 줄지만 설정을 읽을 때 환경별 차이가 묻히고 배포 명령이 복잡해질 수 있어 기각 |
| E. Helm/Kubernetes 기준 | 본사업 확장성은 좋지만 PoC 초기와 온프렘 후보 검증에는 과해 기각 |

## 결정 근거

- ADR-0007의 Docker Compose 기반 배포와 ADR-0020의 `dev`/`prod(main)` 분리 정책을 동시에 만족한다.
- 공통 서비스 정의를 하나로 유지하므로 backend, worker, storage, search 서비스 정합성을 유지하기 쉽다.
- dev 편의 설정과 `prod(main)` 재현성 설정을 분리해 개발자 온보딩과 시연 환경 안정성을 함께 확보할 수 있다.
- 온프렘 이전 시에도 `compose.prod.yml`을 기준으로 포트, volume, 네트워크, 리소스 제한만 조정하면 된다.
- CI 또는 hook에서 `docker compose config`를 실행해 파일 조합 오류를 조기에 발견할 수 있다.

## 영향

- `compose.override.yml` 또는 `compose.onprem.yml`을 기본 구조로 두지 않는다.
- Sprint 1의 Docker Compose 초기 구성 산출물은 `compose.yml`, `compose.dev.yml`, `compose.prod.yml`, env example 파일로 본다.
- 온보딩 스크립트와 README의 실행 예시는 dev 조합을 기본으로 작성한다.
- 배포 workflow와 Self-hosted Runner는 `prod(main)` 배포 시 `compose.yml` + `compose.prod.yml` 조합을 사용한다.
- ADR-0064 기준 PR 필수 Gate에는 dev/prod Compose config 검증을 추가한다.

## 후속 조치

- `compose.yml`, `compose.dev.yml`, `compose.prod.yml` 초안을 작성한다.
- `.env.example`, `.env.dev.example`, `.env.prod.example`을 작성한다.
- `scripts/setup-dev-tools.sh` 또는 별도 온보딩 문서에 dev 스택 실행 명령을 추가한다.
- CI에 dev/prod Compose config 검증을 추가한다.
- Self-hosted Runner 배포 workflow에서 `compose.prod.yml` 조합을 사용하도록 한다.

## 관련 문서

- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0019-self-hosted-runner-deployment.md`
- `docs/adr/ADR-0020-dev-prod-environment-separation.md`
- `docs/adr/ADR-0033-local-and-shared-dev-vm.md`
- `docs/adr/ADR-0041-alembic-migration-and-seed-policy.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0064-ci-cd-quality-gate-test-split-policy.md`
- `docs/project-rules.md`
- `docs/development-schedule-and-notion-kanban.md`
