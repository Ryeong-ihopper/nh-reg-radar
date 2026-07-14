# ADR-0007: Docker Compose 기반 빌드 및 배포 방식

## 상태

Accepted

## 배경

PoC 개발은 빠른 구성과 재현 가능한 실행 환경이 필요하다. 동시에 개발 완료 후 온프렘 환경으로 이전될 가능성이 있으므로, 특정 클라우드 관리형 서비스나 Kubernetes 전제 구조에 강하게 묶이지 않아야 한다.

현재 프로젝트 규칙 문서는 백엔드, 프론트엔드, AI 워커, DB, 검색 엔진, 벡터 DB를 가능한 한 컨테이너로 분리하도록 정의하고 있다. 의사결정 후보 목록에서도 Docker 컨테이너 분리 기준, Self-hosted Runner, 환경 분리 정책을 우선 ADR 대상으로 보고 있다.

## 결정

PoC의 기본 빌드 및 배포 방식은 Docker Compose 기반으로 한다.

서비스는 다음 단위로 분리한다.

| 서비스 | 역할 |
| --- | --- |
| `frontend` | 웹 UI |
| `backend` | API 서버 |
| `worker` | OCR, 문서 파싱, RAG, AI 분석 비동기 작업 |
| `postgres` | 관계형 DB |
| `qdrant` | 벡터 검색 |
| `opensearch` | 키워드 검색 |
| `redis` | AI 분석 Redis Queue 및 Cache |
| `nginx` | Reverse Proxy. 필요 시 사용 |

환경 파일과 Compose 파일은 다음 기준으로 분리한다.

| 파일 | 목적 |
| --- | --- |
| `.env.example` | 공통 환경 변수 샘플 |
| `.env.dev.example` | dev 환경 변수 샘플 |
| `.env.prod.example` | prod(main) 환경 변수 샘플 |
| `.env.dev` | dev 실제 비밀값. Git에 커밋하지 않음 |
| `.env.prod` | prod(main) 실제 비밀값. Git에 커밋하지 않음 |
| `compose.yml` | 공통 서비스 정의 |
| `compose.dev.yml` | dev 환경 override |
| `compose.prod.yml` | prod(main) 환경 override |

Compose 파일의 세부 책임과 실행 명령은 [ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책](ADR-0063-compose-base-dev-prod-override-policy.md)을 따른다. 초기 배포는 개발 VM 또는 온프렘 후보 서버에서 `docker compose pull`, `docker compose up -d`, `docker compose logs`로 운영 가능한 형태를 목표로 한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 단일 컨테이너 | 초기 실행은 단순하지만 서비스별 의존성, 장애 격리, 리소스 조정이 어렵다. |
| Docker Compose 기반 서비스 분리 | PoC 속도와 온프렘 이전 가능성의 균형이 좋다. |
| Kubernetes 전제 구성 | 운영 확장성은 좋지만 PoC 초기 복잡도와 인프라 부담이 크다. |
| 수동 배포 | 재현성이 낮고 장애 분석과 이전 작업에 불리하다. |

## 결정 근거

- 개발 환경과 온프렘 환경의 실행 방식을 최대한 비슷하게 유지할 수 있다.
- DB, 검색 엔진, 벡터 DB, AI 워커를 독립적으로 교체하거나 리소스를 조정하기 쉽다.
- PoC 단계에서 Kubernetes 운영 부담을 피하면서도 향후 마이그레이션 가능한 서비스 경계를 유지할 수 있다.
- Self-hosted Runner나 수동 배포 스크립트와도 쉽게 연결할 수 있다.

## 영향

- 모든 서비스는 컨테이너 실행을 전제로 설정과 볼륨 경로를 관리해야 한다.
- 로컬 개발 편의성과 온프렘 배포 설정이 섞이지 않도록 Compose override 정책이 필요하다.
- GPU가 필요한 OCR/VLM 도구는 `worker` 또는 별도 `ocr-worker` 서비스로 분리될 수 있다.
- AI 분석 worker는 ADR-0035에 따라 Redis Queue와 PostgreSQL Job 상태 테이블을 함께 사용한다.
- 운영 환경의 비밀값은 `.env` 파일 커밋이 아니라 서버 내 주입 또는 Runner secret으로 관리해야 한다.
- dev/prod(main) Compose 조합은 ADR-0063 기준으로 `docker compose ... config` 검증을 통과해야 한다.

## 후속 조치

- `compose.yml` 초안을 작성한다.
- 서비스별 healthcheck와 의존성 순서를 정의한다.
- 개발 VM용 `.env.dev.example`과 `compose.dev.yml`을 작성한다.
- prod(main)용 `.env.prod.example`과 `compose.prod.yml`을 작성한다.
- Self-hosted Runner 사용 여부와 배포 권한은 별도 ADR에서 확정한다.

## 관련 문서

- `docs/project-rules.md`
- `docs/adr-candidates.md`
- `docs/adr/ADR-0035-redis-queue-postgresql-job-state.md`
- `docs/adr/ADR-0063-compose-base-dev-prod-override-policy.md`
