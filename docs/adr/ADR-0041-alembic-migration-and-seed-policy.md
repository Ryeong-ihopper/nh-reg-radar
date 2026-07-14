# ADR-0041: Alembic 기반 DB 마이그레이션 및 Seed 분리 정책

## 상태

Accepted

## 배경

본 프로젝트는 FastAPI/Python 백엔드와 PostgreSQL을 사용하며, DB schema는 `app`, `rag`, `validation`, `audit`로 분리한다. DB 명세서에는 초기 migration이 schema 생성 후 테이블을 생성해야 한다고 정의되어 있으나, migration 도구, version table 위치, seed data 관리 방식, rollback 기준은 아직 명확하지 않았다.

DB 구조 변경과 초기 데이터 주입을 같은 migration에 섞으면 환경별 데이터 차이를 통제하기 어렵다. 특히 dev 환경에는 샘플 사용자와 샘플 기준자료가 필요하지만, prod(main)에는 불필요하거나 위험할 수 있다.

## 결정

DB migration 도구는 Alembic을 사용한다. Migration은 Git으로 관리하고, schema/table/index/FK/constraint 같은 DB 구조 변경만 담당한다. Seed data는 migration에 섞지 않고 별도 script 또는 fixture로 관리한다.

| 항목 | 결정 |
| --- | --- |
| Migration 도구 | Alembic |
| Migration 위치 | `apps/backend/migrations` |
| Version table | `app.alembic_version` |
| Schema 생성 | 초기 migration에서 `app`, `rag`, `validation`, `audit` 생성 |
| Migration 관리 | Git으로 migration 파일 추적 |
| Seed 관리 | `apps/backend/seeds`와 `scripts/seed-*.sh`로 분리 |
| Rollback | PoC에서는 best-effort downgrade, 운영 반영 전 백업 우선 |
| CI 검증 | migration 적용 검증 수행 |

## Migration과 Seed의 책임 경계

| 구분 | 관리 방식 |
| --- | --- |
| schema, table, column | Alembic migration |
| index, FK, unique constraint | Alembic migration |
| enum/check constraint, status code constraint | Alembic migration |
| 공통 코드, 역할 코드 | seed script, idempotent upsert |
| dev 샘플 사용자/부서 | dev 전용 seed |
| 고객사 승인 샘플 데이터 | 별도 import 또는 dev/prod(main) 정책에 따른 seed |
| 테스트 fixture | 테스트 코드 또는 fixture 파일 |
| 운영 데이터 | migration/seed로 임의 주입 금지 |

Seed script는 여러 번 실행해도 같은 결과가 되도록 idempotent upsert 방식으로 작성한다. 운영 환경에 seed를 적용해야 하는 경우에는 공통 코드, 기본 역할처럼 시스템 동작에 필요한 최소 master data만 대상으로 한다.

## 샘플 구조

```text
apps/backend/migrations/
  env.py
  script.py.mako
  versions/
    0001_create_schemas.py
    0002_create_users_and_auth.py
    0003_create_advertisements.py

apps/backend/seeds/
  common_codes.yaml
  roles.yaml
  dev_users.yaml
  sample_standards.yaml

scripts/
  seed-common-data.sh
  seed-dev-data.sh
```

기본 적용 순서는 다음과 같다.

```bash
alembic upgrade head
scripts/seed-common-data.sh
scripts/seed-dev-data.sh
```

`seed-dev-data.sh`는 dev 환경 전용이다. prod(main)에 적용하려면 명시적인 환경 변수 또는 별도 승인 절차를 요구해야 한다.

## 처리 기준

| 상황 | 처리 |
| --- | --- |
| 신규 테이블/컬럼 추가 | Alembic revision 생성 |
| schema 추가 또는 schema별 table 생성 | Alembic revision에 명시 |
| 공통 코드 추가 | seed 파일과 seed script 갱신 |
| dev 테스트 사용자 추가 | dev seed 갱신 |
| 고객사 샘플 기준자료 import | 승인된 샘플 범위 내에서 별도 import script 사용 |
| migration 실패 | 원인 수정 후 재적용. prod(main) 반영 전에는 백업 우선 |
| downgrade 필요 | PoC에서는 가능한 범위에서 제공하되 데이터 손실 가능 시 백업/restore 우선 |

## 대안

| 대안 | 판단 |
| --- | --- |
| SQL 파일 직접 관리 | 단순하지만 변경 순서, revision, rollback 추적이 약하다. |
| ORM 자동 생성/자동 migration 중심 | 초기 속도는 빠르지만 의도치 않은 schema 변경 위험이 크다. |
| Prisma/Flyway/Liquibase 사용 | 기능은 충분하지만 현재 Python/FastAPI 스택에서는 Alembic이 더 자연스럽다. |
| PoC는 수동 SQL, 본사업 때 migration 도입 | PoC 중 schema 변경 이력이 사라질 수 있어 개발자 공유 source of truth와 맞지 않는다. |

## 결정 근거

- FastAPI/Python 백엔드와 SQLAlchemy 계열 구현에 Alembic이 가장 표준적이다.
- ADR-0029의 schema 분리 정책을 migration으로 재현해야 한다.
- 개발자 온보딩 시 `alembic upgrade head`로 동일 schema를 만들 수 있어야 한다.
- seed data는 환경별로 다르므로 migration과 분리해야 한다.
- 공통 코드와 역할 코드는 반복 실행 가능한 seed로 관리해야 개발/테스트 환경 초기화가 안정적이다.

## 영향

- DB schema 변경 PR에는 Alembic migration을 포함해야 한다.
- Migration에는 dev 샘플 데이터나 고객사 샘플 데이터를 넣지 않는다.
- CI 또는 문서 정합성 검증에 migration 적용 검증을 추가할 수 있다.
- `common_codes`, `roles`, dev 사용자, 샘플 기준자료는 seed script로 관리한다.
- DB 명세의 migration 기준과 후속 상세화 항목을 본 ADR 기준으로 갱신한다.

## 후속 조치

- 백엔드 scaffold 작성 시 `apps/backend/migrations`와 `apps/backend/seeds` 구조를 생성한다.
- `scripts/seed-common-data.sh`, `scripts/seed-dev-data.sh`를 온보딩 스크립트와 연결한다.
- DB 계정 분리 정책은 ADR-0046을 따르고, 백업 및 복구 정책은 ADR-0047을 따른다. 본사업 전환 시 schema별 세부 권한, 장기 backup/restore, 장기 보관 정책을 별도 ADR 또는 운영 정책으로 보완한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/project-rules.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0046-postgresql-db-account-separation.md`
- `docs/adr/ADR-0047-poc-backup-and-restore-policy.md`
- `docs/adr/ADR-0006-postgresql-primary-database.md`
- `docs/adr/ADR-0029-postgresql-schema-separation.md`
- `docs/adr/ADR-0034-codex-claude-skills-standardization.md`
