# ADR-0059: AI 분석 Job Timeout, Retry, Dead-letter 및 Worker 장애 복구 정책

## 상태

Accepted

## 배경

ADR-0035에서 AI 분석 작업은 Redis Queue와 PostgreSQL Job 상태 테이블을 병행하기로 결정했다. 다만 timeout, retry backoff, dead-letter, worker heartbeat 장애 복구의 세부 기준은 구현 설정으로 남아 있었다.

AI 검토는 OCR/Parser, RAG, Rule Engine, LLM 판단, 결과 통합, 리포트 준비처럼 실패 원인이 다른 단계로 구성된다. 전체 Job 단위로만 실패를 처리하면 일시적 외부 장애와 파일 손상 같은 복구 불가 오류를 구분하기 어렵고, 담당자가 진행 상태 화면에서 재시도 중인지 최종 실패인지 판단하기 어렵다.

## 결정

AI 분석 Job은 **단계별 timeout + 오류 유형별 retry + 지수 backoff + 최종 실패/dead-letter 상태 기록** 방식으로 처리한다.

| 항목 | 결정 |
| --- | --- |
| 전체 Job timeout | 30분 |
| 단계별 timeout | 단계 코드별 설정값으로 관리 |
| 최대 재시도 | 3회 |
| Retry backoff | 1분, 3분, 10분 |
| Retry 상태 | `RETRY_PENDING` |
| Worker heartbeat 장애 | heartbeat 기준 초과 시 `STALE`로 표시 후 retry 가능 여부에 따라 재등록 |
| 최종 실패 | 재시도 한도 초과 또는 복구 불가 오류 시 `FAILED_FINAL` |
| Dead-letter | 별도 Queue 의존보다 PostgreSQL 상태와 감사 로그를 원천으로 기록 |
| Redis 메시지 | `job_id`, `review_id`, `job_type` 등 최소 식별자만 포함 |

단계별 timeout 기본값은 다음 기준으로 시작한다. 실제 값은 YAML 설정 등 외부 설정으로 관리해 구현 중 조정할 수 있게 한다.

| 단계 | 기본 timeout |
| --- | --- |
| 파일 전처리 | 3분 |
| OCR/Parser | 10분 |
| 레이아웃 분석 | 5분 |
| Rule Engine | 3분 |
| RAG Engine | 5분 |
| LLM/Multimodal 판단 | 10분 |
| 결과 통합 | 3분 |
| 리포트 준비 | 5분 |

## Retry 판정 기준

| 구분 | 처리 |
| --- | --- |
| 일시적 네트워크 오류 | retry |
| 외부 AI/OCR/RAG 서비스 일시 장애 또는 timeout | retry |
| Qdrant/OpenSearch 검색 인프라 일시 장애 | retry. ADR-0061 기준 fallback 판단 금지 |
| Worker heartbeat timeout | retry 가능하면 `STALE` 기록 후 재등록 |
| Object Storage 일시 오류 | retry |
| Redis enqueue 일시 실패 | DB 상태를 남기고 retry 대상 처리 |
| 파일 손상 | retry 제외 |
| 지원하지 않는 파일 형식 | retry 제외 |
| OCR 판독 불가 | retry 제외. 검토 결과의 확인 필요/판독 불가 상태로 처리 |
| 상품조건 불명확 | retry 제외. 담당자 확인 필요 상태로 처리 |
| 기준자료 미제공 | retry 제외. 기준자료 부족 상태로 처리 |
| 권한 오류 | retry 제외 |
| 요청값 검증 오류 | retry 제외 |

Retry 제외 오류는 기술 실패가 아니라 업무적으로 확인이 필요한 상태일 수 있다. 따라서 사용자 메시지는 가능한 경우 `OCR_FAILED`, `PRODUCT_INFO_MISSING`, `STANDARD_NOT_FOUND` 등 업무 오류 코드로 구분하고, 무조건 `REVIEW_FAILED`로만 표현하지 않는다.

Parser/OCR 품질 미달로 인한 보조 엔진 재처리는 기술 retry와 구분하며, 세부 기준은 ADR-0073을 따른다.

## 상태 전이

```text
PENDING
  -> RUNNING
  -> COMPLETED
  -> RETRY_PENDING -> PENDING
  -> STALE -> RETRY_PENDING -> PENDING
  -> FAILED_FINAL
  -> CANCELED
```

`FAILED`는 구현 호환성을 위한 일반 실패 상태로 둘 수 있지만, API와 화면에서는 재시도 한도 초과 또는 복구 불가 최종 실패를 `FAILED_FINAL`로 구분한다. 재분석 버튼은 `isRetryable=true`인 실패에만 제공한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 단순 실패, retry 없음 | 구현은 가장 쉽지만 일시 장애에도 사용자가 재분석을 수동 요청해야 한다. |
| B. 전체 Job timeout + 고정 3회 retry | 단순하지만 어떤 단계에서 멈췄는지, retry해도 되는 오류인지 구분하기 어렵다. |
| C. 단계별 timeout + 오류 유형별 retry + 지수 backoff + 최종 실패 상태 | 장애 복구, 사용자 안내, 운영 추적의 균형이 좋다. |
| D. Queue 라이브러리 retry/dead-letter에 위임 | 구현은 빠를 수 있으나 상태 원천이 Redis/Queue 내부로 분산될 수 있다. |

## 결정 근거

- PoC에서도 장시간 AI 작업은 외부 AI, OCR, Object Storage, worker 상태에 영향을 받는다.
- 재시도 가능한 기술 오류와 재시도해도 해결되지 않는 입력/기준자료 문제를 분리해야 담당자 안내가 정확해진다.
- `review_jobs`, `review_steps`를 상태 원천으로 유지하면 Redis Queue 라이브러리를 교체해도 API와 화면 계약이 흔들리지 않는다.
- Dead-letter를 DB 상태와 감사 로그로 남기면 PoC 운영자가 실패 원인을 조회하고 재현하기 쉽다.
- Redis 메시지에 민감 본문을 넣지 않는 ADR-0035 원칙을 유지한다.

## 영향

- `review_jobs`는 `RETRY_PENDING`, `STALE`, `FAILED_FINAL` 상태와 retry/dead-letter 관련 필드를 저장한다.
- `review_steps`는 단계별 timeout과 실패 사유 코드를 저장할 수 있어야 한다.
- 진행 상태 API는 retry 횟수, 다음 retry 예정 시각, 재분석 가능 여부, 실패 사유 코드를 반환한다.
- Worker는 단계 시작/완료/heartbeat/failure/retry scheduling을 PostgreSQL에 기록한다.
- Audit log에는 job retry, stale worker 복구, 최종 실패/dead-letter 전환을 기록한다.

## 후속 조치

- Job 정책은 YAML 설정 등으로 외부화해 `job_timeout`, 단계별 timeout, backoff, retry 대상 오류 코드를 관리한다.
- Queue adapter는 Redis Queue 구현체에 종속되지 않도록 `enqueue`, `ack`, `retry`, `dead_letter` 책임을 인터페이스로 분리한다.
- Mock/fixture 테스트에 timeout, transient failure, retry exhausted, non-retryable failure, stale worker 케이스를 포함한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0035-redis-queue-postgresql-job-state.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0073-parser-ocr-quality-rerun-policy.md`
