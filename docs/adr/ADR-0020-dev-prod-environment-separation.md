# ADR-0020: PoC dev/prod(main) 환경 분리 정책

## 상태

Accepted

## 배경

PoC 단계에서는 인프라 리소스와 운영 부담을 줄이기 위해 많은 환경을 둘 수 없다. 다만 기준자료, 광고 원본, 검증 데이터셋, AI 검토 결과, 리포트가 섞이면 시연 결과와 개발 테스트 결과를 신뢰하기 어렵다.

사용자 결정에 따라 PoC 환경은 `dev`와 `prod(main)` 두 개로 운영한다. 여기서 `prod(main)`은 상용 운영 환경이 아니라 PoC 시연과 검증 기준이 되는 안정 환경을 의미한다.

## 결정

PoC 환경은 `dev`와 `prod(main)` 두 개로 분리한다.

| 환경 | 목적 | 배포 기준 | 데이터 성격 |
| --- | --- | --- | --- |
| `dev` | 개발, 통합 테스트, 파서/OCR/RAG 실험 | 수동 workflow 또는 개발 브랜치 배포 | 개발용 샘플, 테스트 데이터, 재처리 허용 데이터 |
| `prod(main)` | PoC 시연, 고객사 검증, 기준 결과 보존 | `main` 병합, release tag, 승인된 수동 배포 | 고객사 제공 승인 샘플, 검증 데이터셋, 시연 결과 |

`prod(main)`은 실제 고객 운영 트래픽을 처리하는 운영 환경으로 해석하지 않는다. 본사업 전환 시에는 `stage`, `prod` 또는 고객사 운영 정책에 맞는 환경 구성을 별도 ADR로 재검토한다.

## 브랜치 및 배포 기준

| 소스 | 처리 |
| --- | --- |
| feature branch PR | 테스트만 수행, 자동 배포 없음 |
| 수동 `workflow_dispatch` | 선택한 브랜치를 `dev`에 배포 가능 |
| `main` merge | `prod(main)` 배포 후보 |
| release tag | `prod(main)` 배포 기준으로 사용 가능 |
| hotfix | PR 검증 후 `main` 병합 |

`prod(main)` 배포는 Self-hosted Runner와 GitHub Environment protection rule을 사용해 승인 절차를 둔다. `dev` 배포는 개발 편의를 위해 수동 실행을 허용하되, secret과 데이터는 `prod(main)`과 분리한다.

## 리소스 분리 기준

두 환경은 같은 물리 VM 또는 같은 Docker Compose 기반으로 시작할 수 있지만, 논리 리소스는 분리한다.

| 리소스 | `dev` | `prod(main)` |
| --- | --- | --- |
| PostgreSQL DB | `nh_ad_dev` | `nh_ad_prod` |
| MinIO bucket prefix | `dev-*` | `prod-*` |
| 광고 원본 bucket | `dev-ad-originals` | `prod-ad-originals` |
| 기준자료 bucket | `dev-reference-documents` | `prod-reference-documents` |
| 리포트 bucket | `dev-reports` | `prod-reports` |
| Qdrant collection | `dev_reference_chunks` | `prod_reference_chunks` |
| OpenSearch index | `dev_reference_docs` | `prod_reference_docs` |
| Redis key prefix | `dev:` | `prod:` |
| GitHub Environment | `dev` | `prod` |

개발 편의를 위해 단일 PostgreSQL 인스턴스, 단일 MinIO 인스턴스를 공유할 수는 있다. 단, DB 이름, bucket, collection, index, secret은 반드시 분리한다.

## 설정 파일 기준

Compose 파일의 세부 구조는 [ADR-0063: Docker Compose 공통 파일 및 dev/prod Override 구성 정책](ADR-0063-compose-base-dev-prod-override-policy.md)을 따른다.

| 파일 | 용도 | Git 커밋 |
| --- | --- | --- |
| `.env.example` | 공통 환경 변수 샘플 | 가능 |
| `.env.dev.example` | dev 환경 샘플 | 가능 |
| `.env.prod.example` | prod(main) 환경 샘플 | 가능 |
| `.env.dev` | dev 실제 비밀값 | 금지 |
| `.env.prod` | prod(main) 실제 비밀값 | 금지 |
| `compose.yml` | 공통 서비스 정의 | 가능 |
| `compose.dev.yml` | dev 환경 override | 가능 |
| `compose.prod.yml` | prod(main) 환경 override | 가능 |

실제 비밀값은 GitHub Environment secrets, runner 서버 secret, 또는 서버의 안전한 환경변수 주입 방식으로 관리한다.

## 데이터 사용 기준

| 구분 | `dev` | `prod(main)` |
| --- | --- | --- |
| 샘플 광고물 | 개발용 복사본, 테스트용 변형 허용 | 고객사 승인 샘플 또는 검증셋 |
| 기준자료 | 실험용 재색인 허용 | 검증 기준 버전 고정 |
| OCR/RAG 결과 | 삭제 및 재생성 가능 | PoC 검증 결과 보존 |
| 외부 AI 입력 | 승인된 샘플 범위 내 개발 사용 | 고객사 승인 샘플/검증셋만 사용 |
| 평가 결과 | 개발 참고용 | PoC KPI 산정 기준 |

`prod(main)` 데이터는 개발 실험을 위해 임의 수정하지 않는다. 재색인, 재분석, 기준자료 변경이 필요한 경우 변경 사유와 대상 버전을 기록한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 단일 dev 환경 | 가장 단순하지만 개발 실험과 PoC 검증 결과가 섞일 위험이 크다. |
| `dev` + `prod(main)` | PoC 리소스 부담을 줄이면서 시연/검증 기준 환경을 보호할 수 있다. |
| `dev` + `stage` + `prod` | 운영 전환에는 적합하지만 PoC 단계에서는 인프라와 관리 부담이 크다. |
| 환경 없이 branch만 구분 | 데이터와 secret이 섞여 검증 신뢰성이 낮다. |

## 결정 근거

- 사용자의 PoC 운영 계획과 맞다.
- 환경 수를 최소화하면서도 개발 실험과 PoC 검증 결과를 분리할 수 있다.
- Docker Compose와 Self-hosted Runner 기반 배포 구조와 정합하다.
- 고객사 제공 샘플과 검증 데이터셋을 안정적으로 보존할 수 있다.
- 본사업 전환 시 stage/prod 분리를 별도 결정으로 확장할 수 있다.

## 영향

- Compose 파일과 환경 변수 샘플을 `dev`, `prod(main)` 기준으로 나누어야 한다.
- DB, bucket, collection, index, secret 이름 규칙이 필요하다.
- `prod(main)` 배포에는 승인 절차와 smoke test가 필요하다.
- 테스트 데이터와 PoC 검증 데이터셋을 혼용하지 않도록 운영 규칙이 필요하다.
- 문서에서는 `prod(main)`이 상용 운영 환경이 아니라 PoC 기준 환경임을 명확히 해야 한다.

## 후속 조치

- `.env.dev.example`, `.env.prod.example`을 작성한다.
- `compose.yml`, `compose.dev.yml`, `compose.prod.yml` 초안을 작성한다.
- dev/prod(main) Compose 조합을 `docker compose ... config`로 검증한다.
- GitHub Environment `dev`, `prod`를 생성하고 secret을 분리한다.
- DB, bucket, collection, index 네이밍 규칙을 초기 스키마/인프라 설정에 반영한다.
- PoC 검증 데이터셋을 `prod(main)` 기준 데이터로 분리 관리한다.

## 관련 문서

- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0019-self-hosted-runner-deployment.md`
- `docs/adr/ADR-0017-s3-compatible-object-storage.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
- `docs/adr/ADR-0063-compose-base-dev-prod-override-policy.md`
- `docs/project-rules.md`
- `docs/adr-candidates.md`
