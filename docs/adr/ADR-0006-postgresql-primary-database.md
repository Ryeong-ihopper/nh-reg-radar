# ADR-0006: 기본 관계형 DB로 PostgreSQL 채택

## 상태

Accepted

## 배경

프로젝트는 광고물, 파일, 검토 이력, 검토 결과, 기준자료 메타데이터, 사용자/권한, 감사 로그, PoC 검증 결과를 구조적으로 저장해야 한다. 데이터 간 관계와 이력 추적이 중요하므로 관계형 DB가 필요하다.

DB 명세서는 PostgreSQL을 전제로 테이블, 인덱스, JSONB 후보, 보관 정책을 정의하고 있다.

## 결정

기본 관계형 DB로 PostgreSQL을 채택한다.

PostgreSQL은 다음 데이터를 관리한다.

| 영역 | 예시 |
| --- | --- |
| 광고물 관리 | `advertisements`, `advertisement_files`, `advertisement_revisions` |
| 검토 실행/결과 | `reviews`, `review_jobs`, `review_steps`, `review_items` |
| 기준자료 메타데이터 | `standards`, `standard_versions`, `evidences` |
| 사용자/권한 | `users`, `roles`, `user_roles` |
| 운영/감사 | `audit_logs`, `common_codes` |
| PoC 검증 | `validation_datasets`, `validation_judgments`, `evaluations` |

벡터 검색은 Qdrant, 키워드 검색은 OpenSearch가 담당하고, PostgreSQL은 원천 업무 데이터와 검색 결과의 식별자/메타데이터를 관리한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| PostgreSQL | 관계형 데이터, JSONB, 인덱스, 트랜잭션, PoC 운영 편의성이 적합하다. |
| MySQL/MariaDB | 가능하지만 JSONB/검색 확장성과 기존 DB 명세 방향에서 PostgreSQL보다 이점이 작다. |
| SQLite | 로컬 PoC는 쉽지만 동시성, 운영, 검색 저장소 연계에 부적합하다. |
| MongoDB | 유연한 문서 저장에는 유리하지만 관계/이력/검증 데이터의 정합성 관리에 불리하다. |

## 결정 근거

- 광고물과 검토 결과는 관계와 상태 전이가 명확하다.
- 감사 로그와 이력 보관, 권한 관리에 트랜잭션과 제약조건이 필요하다.
- Docker Compose 기반 PoC와 온프렘 이전 모두에서 운영하기 쉽다.
- Qdrant/OpenSearch와 역할을 분리해 데이터 원천성과 검색 색인을 명확히 할 수 있다.

## 영향

- DB 마이그레이션 체계를 도입해야 한다.
- 검색 색인과 벡터 포인트는 PostgreSQL 원천 데이터와 동기화되어야 한다.
- 대용량 `review_items`, `audit_logs`는 ADR-0049 기준 PoC 초기에는 일반 테이블로 시작하고, 본사업 전환 또는 데이터 증가 기준 충족 시 파티셔닝을 재검토한다.
- JSONB 사용은 편의성보다 조회 패턴과 인덱스 전략을 우선해 제한적으로 사용한다.

## 후속 조치

- `apps/backend`에서 PostgreSQL 연결과 마이그레이션 도구를 구성한다.
- DB 명세서의 테이블을 초기 migration으로 반영한다.
- 검색 색인 동기화 실패 시 재처리 정책을 정의한다.
- 개발/온프렘 환경의 백업·복구 절차를 정리한다.
- 파티셔닝 적용 여부는 ADR-0049 기준으로 관리한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/adr/ADR-0049-poc-table-partitioning-policy.md`
- `docs/api-specification.md`
- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
