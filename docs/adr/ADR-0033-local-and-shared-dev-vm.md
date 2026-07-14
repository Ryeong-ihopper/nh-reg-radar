# ADR-0033: 로컬 개발 및 공용 개발 VM 병행

## 상태

Accepted

## 배경

PoC 개발은 Docker Compose 기반으로 진행하며, 백엔드, 프론트엔드, AI 워커, PostgreSQL, MinIO, Qdrant, OpenSearch, Redis 등 여러 구성요소가 함께 동작해야 한다.

모든 개발자가 동일한 전체 스택을 항상 로컬에서 실행하면 개발 장비 요구사항이 커지고, 반대로 공용 VM만 사용하면 단위 개발과 빠른 테스트 속도가 떨어진다. 또한 개발 VM은 여의도 서버에서 인프라 담당자에게 신청하여 사용할 예정이므로, 표준 사양과 운영 기준을 사전에 정해야 한다.

## 결정

개발 환경은 **로컬 개발 환경과 프로젝트 공용 개발 VM을 병행**한다.

| 구분 | 용도 |
| --- | --- |
| 로컬 개발 환경 | 단위 개발, 빠른 테스트, lint/type check, 프론트엔드 개발 서버, 백엔드 단독 실행, 부분 Docker Compose 실행 |
| 프로젝트 공용 개발 VM | Docker Compose 전체 스택 통합 실행, API 계약 검증, 프론트-백엔드-워커 통합 검증, Self-hosted Runner 배포 대상 후보 |

공용 개발 VM은 PoC의 `dev` 환경으로 사용한다. `prod(main)` 기준 환경과 물리 VM을 공유할 수는 있으나, ADR-0020에 따라 DB, object storage bucket, Qdrant collection, OpenSearch index, secret, compose project name은 논리적으로 분리해야 한다.

## 공용 개발 VM 기준

| 항목 | 기준 |
| --- | --- |
| 최소 사양 | 8 vCPU, 32GB RAM, 300GB SSD |
| 권장 사양 | 16 vCPU, 64GB RAM, 500GB SSD |
| OS | Linux 계열 서버 OS |
| 필수 도구 | Docker Engine, Docker Compose plugin, Git |
| 접근 방식 | SSH key 기반 접근, 프로젝트 개발자 중심으로 권한 제한 |
| Docker 권한 | 필요 인원에게만 부여하고, 가능한 경우 root 직접 사용을 피한다 |
| 외부 노출 포트 | 필요한 포트만 허용하고, 서비스별 내부 포트는 reverse proxy 또는 내부 네트워크로 제한 |
| 데이터 | 제공받은 샘플 데이터와 개발용 데이터만 사용한다 |
| 영속 볼륨 | PostgreSQL, MinIO, Qdrant, OpenSearch는 Docker volume 또는 지정 경로에 저장한다 |
| 리소스 제어 | OpenSearch, Qdrant, worker에는 compose resource limit과 healthcheck를 우선 적용한다 |

OpenSearch까지 포함한 전체 스택을 안정적으로 실행하려면 권장 사양을 우선 신청한다. 최소 사양만 확보된 경우에는 OpenSearch 또는 worker 동시 실행 수를 줄이는 임시 운영을 허용한다.

## Docker Compose 실행 범위

Compose 파일 구조와 실행 명령은 [ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책](ADR-0063-compose-base-dev-prod-override-policy.md)을 따른다.

공용 개발 VM의 기본 compose 대상은 다음과 같다.

| 서비스 | 역할 |
| --- | --- |
| frontend | React/Vite 프론트엔드 |
| backend | FastAPI API 서버 |
| worker | OCR, parser, RAG, LLM 비동기 작업 |
| postgres | 업무 데이터 및 메타데이터 |
| minio | S3 호환 파일 저장소 |
| qdrant | 벡터 검색 |
| opensearch | 키워드/정확 검색 |
| redis | Queue 또는 cache |
| nginx | Reverse proxy. 필요 시 사용 |

로컬 환경은 모든 서비스를 항상 실행할 필요가 없다. 개발자는 작업 대상에 따라 `backend + postgres`, `frontend`, `worker + redis`, `qdrant/opensearch` 등 부분 스택을 실행할 수 있다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 개인별 VM | 환경 격리는 좋지만 리소스와 운영 부담이 크다. PoC 단계에서는 과하다. |
| 프로젝트 공용 VM만 사용 | 통합 검증은 쉽지만 단위 개발 속도가 떨어지고 공용 환경 충돌이 잦아질 수 있다. |
| 서비스별 VM | 운영 구조와 유사하지만 PoC 개발 환경으로는 복잡도가 높다. |
| 로컬 개발 + 프로젝트 공용 개발 VM 병행 | 빠른 개발과 통합 검증을 함께 만족한다. Docker Compose 기반 배포 전략과도 정합성이 높다. |

## 결정 근거

- 로컬 개발은 테스트와 피드백 속도가 빠르다.
- 공용 개발 VM은 여러 서비스가 결합된 문제를 조기에 발견할 수 있다.
- Docker Compose 기반 배포 방식과 온프렘 이전 가능성을 함께 검증할 수 있다.
- 개발 VM 지연 시에도 로컬 Docker Compose 부분 스택으로 개발을 계속할 수 있다.
- 공용 VM을 하나의 dev 통합 환경으로 두면 Self-hosted Runner 배포 검증 대상도 명확해진다.

## 영향

- Sprint 1에서 개발 VM 신청 시 권장 사양과 Docker Compose 전체 스택 실행 기준을 포함한다.
- 로컬 개발 환경은 전체 스택 필수 실행을 전제하지 않는다.
- 공용 개발 VM의 데이터는 개발/샘플 데이터로 제한한다.
- `dev`와 `prod(main)`은 물리 서버 공유 여부와 관계없이 논리 리소스를 분리한다.
- OpenSearch, Qdrant, worker는 VM 리소스 사용량을 관찰하며 compose 설정을 조정한다.

## 후속 조치

- `compose.yml`과 `compose.dev.yml`에 로컬 부분 실행과 dev 전체 실행 기준을 반영한다.
- `.env.example`, `.env.dev.example`, `.env.prod.example`을 분리한다.
- 공용 개발 VM 접속, 배포, smoke test 절차를 운영 가이드 또는 README에 추가한다.
- Self-hosted Runner를 개발 VM에 둘지 별도 VM에 둘지는 ADR-0019 기준으로 구현 시점에 최종 배치한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/development-schedule-and-notion-kanban.md`
- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0019-self-hosted-runner-deployment.md`
- `docs/adr/ADR-0020-dev-prod-environment-separation.md`
- `docs/adr/ADR-0029-postgresql-schema-separation.md`
- `docs/adr/ADR-0063-compose-base-dev-prod-override-policy.md`
