# ADR-0035: Redis Queue 및 PostgreSQL Job 상태 테이블 병행

## 상태

Accepted

## 배경

AI 검토 요청은 OCR, 문서 파싱, 레이아웃 분석, RAG 검색, Rule Engine, LLM 판단, 문구 추천, 리포트 준비 등 여러 장시간 작업을 포함한다. API 서버가 이 작업을 직접 처리하면 요청 응답 시간이 길어지고, 분석 실패·재시도·진행률 조회·worker 장애 복구를 안정적으로 다루기 어렵다.

기존 API/DB 명세에는 `review_jobs`, `review_steps`, `jobId`, 진행 상태 조회 API가 정의되어 있다. 다만 실제 작업을 어떤 큐로 worker에 전달하고, 어떤 저장소를 상태 조회의 원천으로 삼을지 확정이 필요하다.

## 결정

AI 분석 작업은 **Redis Queue와 PostgreSQL Job 상태 테이블을 병행**한다.

| 항목 | 결정 |
| --- | --- |
| 작업 전달 | Redis Queue |
| 상태 원천 | PostgreSQL `review_jobs`, `review_steps` |
| API 서버 역할 | `reviews`, `review_jobs`, `review_steps` 생성 후 Redis Queue에 enqueue |
| Worker 역할 | Redis Queue에서 job 수신, 단계별 처리, PostgreSQL 상태 갱신 |
| 진행 상태 조회 | API는 PostgreSQL을 조회해 응답 |
| 재시도 이력 | PostgreSQL에 `retry_count`, 실패 사유, 다음 재시도 기준 기록. 세부 정책은 ADR-0059 적용 |
| 감사 로그 | 분석 요청, 재분석, job 재시도는 ADR-0022 기준으로 기록 |

Redis는 실행 대기열과 worker 분산 처리에 사용하고, 장기 보존이 필요한 상태와 이력은 PostgreSQL에 저장한다. 프론트엔드와 외부 API는 Redis를 직접 조회하지 않는다.

## 처리 흐름

1. 사용자가 `POST /advertisements/{advertisementId}/reviews`를 호출한다.
2. API 서버는 트랜잭션 안에서 `reviews`, `review_jobs`, 초기 `review_steps`를 생성한다.
3. API 서버는 생성된 `job_id`를 Redis Queue에 enqueue한다.
4. Worker는 Redis Queue에서 job을 가져와 `review_jobs.job_status`를 `RUNNING`으로 변경한다.
5. Worker는 단계별로 `review_steps.step_status`, `review_jobs.current_step`, `review_jobs.progress_rate`를 갱신한다.
6. 성공 시 `review_jobs.job_status`를 `COMPLETED`, `reviews.review_status`를 `REVIEW_COMPLETED`로 갱신한다.
7. 실패 시 ADR-0059 기준으로 retry 가능 여부를 판정한다. 재시도 가능하면 `RETRY_PENDING`과 다음 재시도 시각을 기록한 뒤 `PENDING`으로 재등록하고, 재시도 불가 또는 한도 초과이면 `FAILED_FINAL`과 실패 사유를 기록한다.
8. 화면의 `GET /reviews/{reviewId}/status`는 PostgreSQL 상태를 조회한다.

## 상태 기준

| 상태 | 의미 |
| --- | --- |
| `PENDING` | Job 생성 후 실행 대기 |
| `RUNNING` | Worker가 처리 중 |
| `RETRY_PENDING` | Retry backoff 대기 중 |
| `STALE` | Worker heartbeat 기준 초과로 장애 복구 대상 |
| `COMPLETED` | 모든 단계 완료 |
| `FAILED` | 일반 실패. 구현 호환성을 위해 둘 수 있으나 API/화면은 가능한 경우 `FAILED_FINAL`로 구분 |
| `FAILED_FINAL` | 재시도 한도 초과 또는 복구 불가 오류 |
| `CANCELED` | 사용자의 취소 또는 운영자 조치로 중단. PoC 필수 기능은 아님 |

PoC 기본 재시도 정책은 ADR-0059를 따른다.

| 항목 | 기준 |
| --- | --- |
| 최대 재시도 | 3회 |
| Retry backoff | 1분, 3분, 10분 |
| 재시도 대상 | 일시적 네트워크 오류, 외부 AI/OCR/RAG 일시 장애, worker heartbeat timeout, Object Storage 일시 오류 |
| 재시도 제외 | 파일 손상, 지원하지 않는 파일 형식, OCR 판독 불가, 상품조건 불명확, 필수 기준자료 미제공, 권한 오류, 요청값 검증 오류 |
| Timeout | 전체 Job 30분, 단계별 timeout은 설정값으로 분리 |
| 중복 요청 | 동일 광고물에 `PENDING` 또는 `RUNNING` job이 있으면 `REVIEW_ALREADY_RUNNING` 반환 |

## 대안

| 대안 | 판단 |
| --- | --- |
| PostgreSQL Job 테이블만 사용 | 구조는 단순하지만 worker 분산, 대기열 제어, 재시도 실행을 직접 구현해야 한다. |
| Redis Queue + PostgreSQL Job 상태 테이블 | Queue 처리와 상태 조회 책임이 분리되어 PoC와 확장성의 균형이 좋다. |
| Celery + Redis/RabbitMQ | 검증된 구조지만 PoC 초기에는 의존성과 운영 복잡도가 커질 수 있다. |
| FastAPI BackgroundTask | 구현은 쉽지만 프로세스 장애, 재시도, 진행률 조회, worker 분리에 취약하다. |

## 결정 근거

- API 서버는 빠르게 `reviewId`, `jobId`를 반환해야 한다.
- S-005 검토 진행 상태 화면은 DB에 저장된 안정적인 상태를 조회해야 한다.
- Redis Queue는 Docker Compose 기본 구성과 맞고, worker 수평 확장에도 대응하기 쉽다.
- PostgreSQL 상태 테이블을 원천으로 두면 감사, 이력, 장애 복구, PoC 평가 분석에 활용할 수 있다.
- Celery 도입 여부는 구현 단계에서 Python queue 라이브러리 선택 문제로 남길 수 있지만, 아키텍처 책임 경계는 Redis Queue + PostgreSQL 상태 테이블로 고정한다.

## 영향

- `redis`는 선택 컨테이너가 아니라 AI 분석 파이프라인의 기본 구성요소가 된다.
- `review_jobs`, `review_steps`는 API 진행 상태 조회의 원천이다.
- Worker는 모든 단계 전환과 실패 사유를 PostgreSQL에 기록해야 한다.
- Redis Queue 메시지는 `job_id`와 필요한 최소 식별자만 포함하고, 광고 원본이나 민감 본문은 포함하지 않는다.
- 분석 요청 API는 DB 트랜잭션 성공 후 enqueue 실패 시 job을 `FAILED` 또는 `PENDING` 복구 대상으로 남겨야 한다.
- CI/테스트에서는 Redis를 실제로 띄우는 통합 테스트와 queue adapter mock 기반 단위 테스트를 분리한다.

## 후속 조치

- `review_jobs`에 queue, enqueue, lock/heartbeat, retry 관련 필드를 보강한다.
- `compose.yml`에 Redis healthcheck와 worker 의존성을 정의한다.
- Queue adapter 인터페이스를 두어 구현 라이브러리 교체 가능성을 유지한다.
- Job timeout, retry backoff, dead-letter 처리 세부값은 ADR-0059 기준을 기본값으로 두고 YAML 설정 등 외부 설정으로 관리한다.
- `GET /reviews/{reviewId}/status` 응답에 `jobId`, 실패 사유, 재시도 가능 여부 노출 필요성을 API 상세 설계에서 반영한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/screen-api-mapping.md`
- `docs/project-rules.md`
- `docs/adr/ADR-0005-fastapi-backend-framework.md`
- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0033-local-and-shared-dev-vm.md`
- `docs/adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md`
