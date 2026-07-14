# ADR-0048: PoC 개인정보 및 민감정보 저장/노출 정책

## 상태

Accepted

## 배경

PoC는 고객사 소규모 담당자가 제한적으로 사용하는 환경이다. 사용자는 email을 로그인 ID로 사용하며, 사용자 이름과 부서명은 화면 표시와 담당자 식별에 필요하다.

이미 ADR-0036은 비밀번호 평문 저장 금지와 JWT/secret 로그 저장 금지를 정했고, ADR-0022는 감사 로그에 파일 원문, 광고 원문, prompt 전문, token, secret, 개인정보 원문을 저장하지 않는다고 정했다. ADR-0044는 fixture에 고객사 자료, 개인정보, API key, prompt 전문, presigned URL 전체값을 저장하지 않는다고 정했고, ADR-0045는 오류 응답에서 민감정보를 노출하지 않는다고 정했다.

다만 DB에 어떤 개인정보를 평문으로 저장할 수 있는지, 어떤 정보는 저장을 금지하거나 마스킹해야 하는지, 컬럼 암호화는 PoC에서 필수인지가 아직 명확하지 않았다.

## 결정

PoC에서는 사용자 email, 이름, 부서, 역할은 업무 식별과 로그인 편의를 위해 DB 평문 저장을 허용한다. 단, 비밀번호, token, API key, secret, presigned URL 전체값은 평문 저장하지 않는다.

| 구분 | 정책 |
| --- | --- |
| 사용자 email | 로그인 ID로 사용하므로 DB 평문 저장 허용 |
| 사용자 이름 | 소규모 사용자 식별과 화면 표시를 위해 DB 평문 저장 허용 |
| 부서/역할 | 권한 판단과 화면 표시를 위해 DB 평문 저장 허용 |
| 비밀번호 | ADR-0058 기준 `password_hash`만 저장, 평문 저장 금지 |
| access/refresh token | DB/로그 평문 저장 금지. ADR-0056 기준 refresh token은 hash만 저장 |
| API key/secret | DB/로그 저장 금지. 환경 변수 또는 secret 저장소 사용 |
| presigned URL 전체값 | DB/로그 저장 금지. 발급 여부, object 식별자, 만료 시각, 용도만 기록 |
| IP/User-Agent | 감사 로그 목적 저장 허용, 화면 노출 제한 |
| 고객사 광고 원문/상품설명서/약관/기준자료 원문 | 업무 데이터로 저장 가능하되 로그, 오류 응답, fixture, 외부 AI 입력 정책을 별도로 제한 |

컬럼 암호화, KMS/Vault, field-level encryption은 PoC 필수 범위에서 제외한다. 본사업 전환, 고객사 보안 요구, 사용자 수 확대, 운영 데이터 입력이 확정되면 별도 ADR 또는 운영 정책으로 재검토한다.

## 저장 및 노출 기준

| 위치 | 기준 |
| --- | --- |
| PostgreSQL | email/name/department/role 평문 저장 허용, password는 hash만 저장. 로그인 실패/잠금 메타데이터 저장 허용 |
| 감사 로그 | 사용자 ID, 역할, 부서, IP/User-Agent 등 추적 메타데이터 중심 저장. 원문/secret/token 저장 금지 |
| 애플리케이션 로그 | email/name은 원칙적으로 출력하지 않고 user_id, request_id, trace_id 중심 기록 |
| API 오류 응답 | ADR-0045 기준 민감정보와 내부 상세 노출 금지 |
| 테스트 fixture | ADR-0044 기준 개인정보, secret, 고객사 원문 저장 금지. 필요한 경우 synthetic 값 사용 |
| 외부 AI 입력 | ADR-0002 기준 고객사 승인 샘플 범위만 입력 가능. 개인정보/비밀값 포함 자료는 추가 확인 |
| 관리자 화면 | 권한이 있는 관리자에게 필요한 범위의 email/name 표시 가능 |

## 마스킹 기준

PoC 내부 업무 화면에서는 권한이 있는 사용자에게 email과 이름을 표시할 수 있다. 다만 로그, 오류 응답, 외부 공유 산출물, 테스트 fixture에서는 다음 기준을 적용한다.

| 항목 | 마스킹/대체 기준 |
| --- | --- |
| email | `user@example.com` 같은 synthetic 값 또는 일부 마스킹 |
| 이름 | synthetic 이름 또는 역할명 중심 표기 |
| IP 주소 | 필요 시 일부 마스킹 또는 내부 로그에만 보관 |
| object key | 외부 응답/오류 메시지에는 노출하지 않음 |
| presigned URL | 전체값 저장/출력 금지 |

## 금지 기준

다음 정보는 DB, 로그, 오류 응답, fixture, prompt/config YAML에 평문으로 저장하지 않는다.

| 금지 대상 | 기준 |
| --- | --- |
| 비밀번호 평문 | 항상 금지 |
| access token, refresh token | 평문 저장 금지. refresh token은 hash 저장만 허용 |
| API key, secret, object storage credential | 평문 저장 금지 |
| presigned URL 전체값 | 저장/로그 출력 금지 |
| LLM prompt 전문 | 고객사 자료나 내부 정책 포함 가능성이 있으므로 로그/fixture 저장 금지 |
| 고객사 원문 전문 | 업무 저장소 외 로그/오류/fixture 저장 금지 |

## 대안

| 대안 | 판단 |
| --- | --- |
| PoC에서는 별도 정책 없이 평문 저장 | 구현은 빠르지만 노출 금지 경계가 모호하다. |
| email/name 평문 저장 허용 + secret/token/로그/fixture 제한 | PoC 규모와 보안 요구의 균형이 좋다. |
| email/name까지 암호화 또는 hash 저장 | 보안은 강화되지만 로그인, 검색, 화면 표시 구현이 복잡해진다. |
| 모든 개인정보/민감정보 컬럼 암호화 + KMS/Vault | 본사업급 기준이며 PoC에는 과하다. |
| 본사업 전환 시 결정 | 초기 구현은 쉽지만 고객사 보안 검토 대응이 늦어진다. |

## 결정 근거

- PoC 사용자는 고객사 소규모 담당자로 제한되며 email은 로그인 ID로 사용된다.
- email과 이름은 사용자 식별, 권한 확인, 화면 표시, 감사 추적에 필요하다.
- 비밀번호, token, secret, presigned URL은 유출 시 직접적인 보안 사고로 이어지므로 저장 금지선이 필요하다.
- 컬럼 암호화는 키 관리, 검색, 운영 복잡도를 만들기 때문에 PoC 필수 범위에서는 제외한다.
- 로그, 오류 응답, fixture, 외부 AI 입력 경계를 분리하면 평문 저장 허용 범위를 제한적으로 관리할 수 있다.

## 영향

- `users.email`, `users.user_name`은 평문 컬럼으로 유지한다.
- 비밀번호는 `password_hash`만 저장하며 평문 비밀번호 컬럼은 만들지 않는다.
- 로그인 실패 횟수, 잠금 만료 시각, 비밀번호 변경 시각은 ADR-0058 기준 보안 메타데이터로 저장한다.
- API, application log, audit log, fixture 작성 시 민감정보 저장 금지 기준을 적용해야 한다.
- 관리자 화면과 사용자 관리 화면은 권한이 있는 사용자에게만 email/name을 표시한다.
- 본사업 전환 시 컬럼 암호화, KMS/Vault, 개인정보 보관 기간, 접근 이력 확대를 재검토해야 한다.

## 후속 조치

- DB 명세서의 개인정보 암호화 후속 항목을 본 ADR 기준으로 갱신한다.
- 테스트케이스에 token/secret/presigned URL/고객사 원문이 로그와 오류 응답에 노출되지 않는 검증을 유지한다.
- 본사업 전환 시 개인정보 영향평가 또는 고객사 보안 검토 결과에 따라 컬럼 암호화 여부를 재검토한다.

## 관련 문서

- `docs/database-specification.md`
- `docs/api-specification.md`
- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/adr/ADR-0002-customer-sample-data-ai-input-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0044-ai-mock-fixture-test-policy.md`
- `docs/adr/ADR-0045-user-error-message-policy.md`
- `docs/adr/ADR-0056-jwt-session-token-lifetime-policy.md`
- `docs/adr/ADR-0058-login-failure-lockout-password-policy.md`
