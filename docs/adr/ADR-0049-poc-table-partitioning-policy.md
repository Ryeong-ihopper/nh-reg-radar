# ADR-0049: PoC 대용량 테이블 파티셔닝 적용 정책

## 상태

Accepted

## 배경

PostgreSQL에는 검토 항목(`review_items`)과 감사 로그(`audit_logs`)처럼 시간이 지날수록 누적되는 테이블이 있다. 본사업에서는 데이터 증가, 보관 기간, 삭제/아카이브 정책에 따라 파티셔닝이 필요할 수 있다.

그러나 PoC 단계에서는 검증 데이터 규모가 제한적이고, ADR-0042에서 성능 목표를 운영 SLA가 아니라 관찰 기준으로 정했다. 초기부터 파티셔닝을 적용하면 Alembic migration, 테스트 DB 초기화, 인덱스 관리, 쿼리 작성, 보관 정책이 복잡해진다.

따라서 PoC에서는 파티셔닝보다 일반 테이블, 적절한 인덱스, 페이징, 기간 조건 조회를 우선 적용한다.

## 결정

PoC에서는 `audit_logs`, `review_items`에 파티셔닝을 적용하지 않는다. 두 테이블은 일반 테이블로 시작하고, 필수 인덱스와 조회 제약을 적용한다.

| 대상 | PoC 결정 |
| --- | --- |
| `audit_logs` | 일반 테이블 사용, 기간 조건과 인덱스 기반 조회 |
| `review_items` | 일반 테이블 사용, `review_id` 중심 조회와 페이징 적용 |
| 파티셔닝 | PoC 초기 미적용 |
| 재검토 시점 | 본사업 전환 또는 데이터 증가 기준 충족 시 |

## 필수 인덱스 기준

| 테이블 | 인덱스 기준 |
| --- | --- |
| `audit_logs` | `created_at`, `user_id`, `action_type`, `target_type + target_id` |
| `review_items` | `review_id`, `review_type`, `result_status`, `risk_level`, `ocr_block_id` |

필요 시 구현 단계에서 복합 인덱스를 추가할 수 있다. 단, 인덱스 추가는 실제 조회 패턴과 실행 계획을 기준으로 한다.

## 조회 기준

| 조회 | 기준 |
| --- | --- |
| 감사 로그 목록 | 기간 조건을 기본 조회 조건으로 둔다. |
| 감사 로그 상세 | `audit_log_id` 또는 `target_type + target_id` 중심으로 조회한다. |
| 검토 항목 목록 | `review_id` 기준으로 조회하고 페이징을 적용한다. |
| 검토 항목 필터 | `review_type`, `result_status`, `risk_level` 필터를 인덱스 기준과 맞춘다. |
| 전체 스캔 | 관리자성 집계나 유지보수 목적 외에는 피한다. |

## 파티셔닝 재검토 기준

다음 조건 중 하나 이상을 충족하면 파티셔닝 또는 보관/아카이브 정책을 재검토한다.

| 조건 | 검토 방향 |
| --- | --- |
| `audit_logs` 100만 건 이상 | 월 단위 range partition 검토 |
| `review_items` 100만 건 이상 | `review` 생성일 또는 `created_at` 기준 partition 검토 |
| 감사 로그 기간 조회 P95가 ADR-0042 관찰 목표를 지속 초과 | 인덱스 개선 또는 partition 검토 |
| 검토 항목 목록/필터 조회 P95가 ADR-0042 관찰 목표를 지속 초과 | 복합 인덱스 또는 partition 검토 |
| 본사업에서 로그 보관/삭제가 월 또는 연 단위로 확정 | `audit_logs` range partition 검토 |
| 고객사 운영 데이터 규모가 PoC 예상치를 크게 초과 | 테이블별 용량 산정 후 partition 검토 |

## 대안

| 대안 | 판단 |
| --- | --- |
| PoC 파티셔닝 미적용, 일반 테이블 + 인덱스 | PoC 규모와 구현 단순성에 가장 적합하다. |
| `audit_logs`만 월 단위 파티셔닝 | 감사 로그 장기 보관에는 유리하지만 PoC 초기 운영 부담이 늘어난다. |
| `audit_logs`, `review_items` 모두 파티셔닝 | 대용량 대응은 좋지만 migration과 테스트가 복잡해진다. |
| 모든 이력성 테이블 파티셔닝 | 본사업급 설계이며 PoC에는 과하다. |
| 성능 문제 발생 시 즉시 결정 | 기준 없이 늦게 바꾸면 migration 변경 비용이 커진다. |

## 결정 근거

- PoC에서는 데이터 규모보다 기능 검증, AI 판단 품질, 담당자 검토 흐름 검증이 우선이다.
- 파티셔닝은 데이터 증가와 보관 정책이 확정된 뒤 적용하는 것이 더 안전하다.
- ADR-0042의 성능 기준은 운영 SLA가 아니라 관찰 목표이므로 초기부터 복잡한 물리 설계를 강제할 필요가 없다.
- 일반 테이블과 적절한 인덱스, 페이징, 기간 조건만으로 PoC 조회 성능을 충분히 관찰할 수 있다.
- 재검토 기준을 수치로 남기면 본사업 전환 시 파티셔닝 도입 여부를 판단하기 쉽다.

## 영향

- 초기 Alembic migration은 partitioned table을 만들지 않는다.
- 테스트 DB 초기화와 fixture 로딩은 일반 테이블 기준으로 작성한다.
- 감사 로그 API는 기간 조건과 페이징을 기본으로 설계한다.
- 검토 항목 API는 `review_id` 기준 조회와 페이징을 적용한다.
- 본사업 전환 또는 데이터 증가 기준 충족 시 파티셔닝 도입 ADR 또는 운영 정책을 별도로 작성한다.

## 후속 조치

- DB 명세서의 파티셔닝 후속 상세화 항목을 본 ADR 기준으로 갱신한다.
- 구현 시 `audit_logs`, `review_items` 조회 API에 페이징과 필터 조건을 적용한다.
- 성능 관찰 결과에서 데이터 증가로 인한 병목이 확인되면 인덱스 개선과 파티셔닝을 함께 검토한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/api-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0006-postgresql-primary-database.md`
- `docs/adr/ADR-0042-poc-runtime-performance-targets.md`
