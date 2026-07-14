# ADR-0046: PostgreSQL DB 계정 분리 정책

## 상태

Accepted

## 배경

ADR-0029에서 PostgreSQL schema는 PoC 단계부터 `app`, `rag`, `validation`, `audit`로 분리하기로 결정했다. 그러나 schema 분리와 DB 접속 계정 분리는 별개의 의사결정이다.

초기에는 PoC 구현 속도를 고려해 단일 애플리케이션 계정을 허용하는 방향이 검토되었다. 하지만 본 프로젝트는 광고물 원본, 기준자료, 감사 로그, PoC 평가 데이터를 함께 다루며, 온프렘 환경 이전 가능성도 있다. 따라서 애플리케이션 런타임, DB 구조 변경, 운영 조회, 예외적 관리자 작업을 같은 계정으로 수행하면 사고 범위가 커지고 운영 감사가 어려워질 수 있다.

특히 migration 계정과 admin 계정은 모두 높은 권한처럼 보일 수 있지만 역할이 다르다. Migration 계정은 Git으로 관리되는 Alembic migration을 반복 가능하게 실행하는 자동화 계정이고, admin 계정은 계정/권한 관리, 장애 대응, 복구, 예외적 수동 운영을 담당하는 사람 중심 운영 계정이다.

## 결정

PoC 단계부터 PostgreSQL DB 계정을 다음 4종으로 분리한다.

| 계정 | 용도 | 사용 주체 |
| --- | --- | --- |
| `app` | 애플리케이션 런타임 CRUD | API 서버, Worker |
| `migration` | Alembic migration 실행 및 DB 구조 변경 | 배포/마이그레이션 자동화 |
| `readonly` | 운영 조회, 리포트 검증, 장애 분석용 읽기 | 운영자, 진단 도구 |
| `admin` | 계정/권한 관리, 장애 대응, 복구, 예외적 수동 운영 | 제한된 관리자 |

Schema 구조는 ADR-0029의 `app`, `rag`, `validation`, `audit` 분리를 유지한다. 단, PoC에서는 schema별 세부 권한 분리까지 강제하지 않고, 본사업 전환 또는 고객사 보안 요구 확정 시 schema별 권한, RLS, 컬럼 암호화, 백업/복구 권한을 별도 ADR 또는 운영 정책으로 보완한다.

## 계정별 권한 기준

| 계정 | 허용 권한 | 제한 권한 |
| --- | --- | --- |
| `app` | 서비스에 필요한 `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `CREATE`, `ALTER`, `DROP`, role 관리, extension 설치 |
| `migration` | schema/table/index/constraint 변경, migration version table 갱신, 필요한 data migration | role 관리, 전체 DB 관리, 슈퍼유저성 권한, 임의 운영 조회 계정 사용 |
| `readonly` | 필요한 schema/table에 대한 `SELECT` | `INSERT`, `UPDATE`, `DELETE`, DDL, role 관리 |
| `admin` | role 생성/권한 부여, 긴급 점검, 복구, 예외적 수동 운영 | 애플리케이션 런타임 및 CI/CD 상시 사용 |

`migration` 계정은 자동화된 구조 변경에 필요한 권한만 가진다. `admin` 계정은 migration 계정에 부여하지 않는 role 관리, 권한 부여/회수, 장애 대응, 복구성 작업을 수행할 수 있다.

## 운영 기준

| 항목 | 기준 |
| --- | --- |
| 앱 런타임 | `app` 계정만 사용 |
| Alembic 실행 | `migration` 계정 사용 |
| 운영 조회 | `readonly` 계정 우선 사용 |
| 긴급 운영 | `admin` 계정 사용, 사용 이력 추적 |
| 비밀번호/접속 정보 | Git에 커밋하지 않고 환경 변수 또는 배포 secret으로 관리 |
| Docker Compose | 초기화 스크립트에서 4종 계정을 생성할 수 있게 구성 |
| 본사업 전환 | schema별 권한, RLS, 컬럼 암호화, KMS/Vault 연계 재검토 |

## 대안

| 대안 | 판단 |
| --- | --- |
| 단일 DB 계정 | 구현은 가장 단순하지만 런타임 계정이 DDL과 운영 권한까지 가지게 되어 사고 범위가 크다. |
| `app`/`migration`만 분리 | 구조 변경 권한은 분리되지만 운영 조회와 관리자 작업 추적이 약하다. |
| `app`/`migration`/`readonly`/`admin` 분리 | PoC에서도 감당 가능한 복잡도로 권한 경계와 감사 가능성을 확보한다. |
| schema별 계정까지 즉시 분리 | 보안은 강하지만 PoC 개발과 migration 관리가 복잡해진다. |
| 본사업 전환 시점까지 유보 | 초기는 빠르지만 온프렘 이전 및 보안 검토 시 계정 구조를 다시 설계해야 한다. |

## 결정 근거

- Schema 분리만으로는 런타임, migration, 운영 조회, 관리자 작업의 권한 경계가 충분히 나뉘지 않는다.
- `readonly` 계정을 분리하면 리포트 검증, 장애 분석, 운영 조회 중 실수로 데이터를 변경할 위험을 줄일 수 있다.
- `admin` 계정을 분리하면 role 관리, 복구, 예외적 수동 조치를 애플리케이션/CI 계정과 분리해 감사하기 쉽다.
- `migration` 계정을 분리하면 앱 런타임 계정에 DDL 권한을 주지 않아도 된다.
- Docker Compose 초기화 스크립트로 계정 생성을 자동화하면 개발자 온보딩 부담을 크게 늘리지 않고 권한 경계를 만들 수 있다.

## 영향

- DB 초기화 스크립트는 4종 계정을 생성해야 한다.
- 애플리케이션 설정은 런타임 DSN과 migration DSN을 분리해야 한다.
- CI/CD 또는 배포 절차는 Alembic 실행 시 `migration` 계정을 사용해야 한다.
- 운영 조회 스크립트나 진단 도구는 기본적으로 `readonly` 계정을 사용해야 한다.
- `admin` 계정은 앱 런타임, 테스트, CI/CD에서 사용하지 않는다.

## 후속 조치

- Docker Compose 및 DB init script에 `app`, `migration`, `readonly`, `admin` 계정 생성을 반영한다.
- 백엔드 환경 변수는 런타임 DB URL과 migration DB URL을 분리한다.
- 본사업 전환 시 schema별 권한, RLS, 컬럼 암호화, 백업/복구 권한을 별도 ADR 또는 운영 정책으로 구체화한다.
- 테스트 환경에서 앱 계정으로 DDL이 실행되지 않는지 확인하는 검증을 추가할 수 있다.

## 관련 문서

- `docs/database-specification.md`
- `docs/adr/ADR-0029-postgresql-schema-separation.md`
- `docs/adr/ADR-0041-alembic-migration-and-seed-policy.md`
- `docs/adr/ADR-0020-dev-prod-environment-separation.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
