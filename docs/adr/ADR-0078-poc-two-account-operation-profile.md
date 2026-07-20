# ADR-0078: PoC 2계정 운영 프로필 정책

| 항목 | 내용 |
| --- | --- |
| 상태 | Accepted |
| 날짜 | 2026-07-20 |
| 관련 문서 | README, API 명세서, 화면설계서, 테스트케이스 |
| 관련 ADR | ADR-0036, ADR-0055, ADR-0058 |

## 배경

PoC에서는 역할별로 여러 로그인 계정을 유지하면 데모와 수동 검증의 준비 비용이 커지고, 어떤 계정으로 기준자료를 등록해야 하는지 혼동하기 쉽다. 반면 역할 모델 자체를 관리자와 일반 사용자 두 종류로 축소하면 ADR-0055의 API 인가·부서 scope 경계와 향후 본사업 역할 분리 검증이 약해진다.

따라서 PoC에서 실제로 로그인하는 개발 seed 계정 수를 두 개로 제한하되, 역할 모델과 인가 정책은 그대로 유지할 운영 프로필이 필요하다.

## 결정

PoC 개발 환경의 활성 synthetic 로그인 계정은 다음 두 개만 운영한다.

| 계정 | 운영 목적 | 부여 역할 |
| --- | --- | --- |
| `test@ihopper.co.kr` | 광고 등록·AI 검토·결과 확인과 기준자료 등록·개정·검색 갱신을 포함한 업무 흐름 검증 | `PRODUCT_DEPARTMENT_USER`, `COMPLIANCE_REVIEWER`, `STANDARD_MANAGER` |
| `admin@ihopper.co.kr` | 사용자·권한·감사·시스템 운영 확인 | `SYSTEM_ADMIN` |

`test@ihopper.co.kr`는 기준자료 등록과 변경을 수행할 수 있어야 하므로 `STANDARD_MANAGER`를 추가한다. `admin@ihopper.co.kr`는 기준자료 관리자 전용 계정이 아니라 `SYSTEM_ADMIN`으로 운영한다.

기존 권한 역할과 API 인가 규칙은 변경하지 않는다. 역할별 최소 권한·거부·부서 scope 검증은 자동 테스트의 fixture와 테스트용 actor로 계속 검증한다. 기존 준법감시 synthetic 계정은 활성 로그인 계정으로 운영하지 않는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| A. 역할별 synthetic 계정을 계속 각각 운영 | 최소 권한 수동 점검에는 편하지만 PoC 데모·온보딩에서 계정 선택 혼동과 관리 비용이 커 제외 |
| B. 두 로그인 계정만 운영하고 test 계정에 업무·기준관리 역할을 합성 | PoC 흐름을 단순화하면서 역할 모델과 자동 인가 검증을 유지할 수 있어 채택 |
| C. 권한 모델도 일반 사용자·관리자 두 역할로 축소 | ADR-0055 인가 경계와 본사업 전환 준비를 훼손하므로 제외 |
| D. admin 계정에 모든 데모 업무를 집중 | 시스템 관리 계정의 일상 사용을 정상화해 최소 권한 원칙과 맞지 않아 제외 |

## 영향

- 개발 seed는 활성 로그인 계정을 `test@ihopper.co.kr`, `admin@ihopper.co.kr`으로 제한한다.
- README와 로컬 개발 완료 안내는 두 계정의 용도와 역할을 동일하게 안내한다.
- `test` 계정은 기준자료 관리 화면에 접근할 수 있다.
- `admin` 계정은 시스템 관리 역할을 검증하는 데 사용한다.
- API 권한 enum, ADR-0055의 역할별 인가, 역할별 자동 테스트 fixture는 유지한다.

## 후속 조치

- dev seed의 역할 매핑과 기존 준법감시 개발 계정의 활성 상태를 정리한다.
- README와 `scripts/local-dev.sh`의 계정 안내를 두 계정 프로필과 일치시킨다.
- seed 계약 테스트에 두 활성 계정과 역할 매핑을 고정한다.
- 본사업 전환 전 실제 조직·SSO 기준의 최소 권한 계정과 역할 분리를 다시 검토한다.

## 관련 문서

- `README.md`
- `apps/backend/seeds/dev.sql`
- `scripts/local-dev.sh`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0055-api-authorization-scope-policy.md`
- `docs/test-cases.md`
