# ADR-0036: PoC 자체 JWT 인증 및 SSO 전환 가능 인가 구조

## 상태

Accepted

## 배경

API 명세서는 Bearer Token 기반 인증을 가정하고 있고, 기능명세서와 테스트케이스에는 상품부서 담당자, 준법감시 담당자, 기준 관리자, 시스템 관리자 기준의 권한 매트릭스가 정의되어 있다.

파일 접근, 기준자료 변경, 감사 로그, 사용자/권한 관리, PoC 검증 데이터는 모두 인증된 사용자와 역할·부서 기반 인가에 의존한다. PoC 단계에서 고객사 SSO 연계를 전제로 하면 계정, 네트워크, 보안 정책 협의 지연으로 개발이 막힐 수 있다. 반대로 고정 테스트 계정만 사용하면 권한과 감사 로그 검증 신뢰도가 낮다.

## 결정

PoC 단계는 **자체 로그인 + JWT Bearer Token**을 사용한다. 단, 본사업 전환 시 고객사 SSO/OIDC/SAML 연동으로 교체할 수 있도록 인증 제공자 경계를 둔다.

| 항목 | 결정 |
| --- | --- |
| PoC 인증 방식 | 자체 로그인 + JWT Bearer Token |
| 본사업 전환 | SSO/OIDC/SAML 연동 가능 구조 |
| 사용자 원천 | PoC는 DB `users`, `departments`, `roles`, `user_roles` |
| 권한 검증 | ADR-0055 기준 role + department scope 기반 |
| API 인증 Header | `Authorization: Bearer {accessToken}` |
| Refresh Token | ADR-0056 기준 DB hash 저장 refresh token 사용 |
| 감사 로그 | `user_id`, `department_id`, 대표 `role`, `trace_id` 기록 |

인증 구현은 `AuthProvider` 또는 동등한 인증 어댑터 경계를 둔다. API service layer는 JWT 발급 방식이나 SSO 구현체에 직접 의존하지 않고, 인증된 사용자 컨텍스트와 권한 검증 결과만 사용한다.

## 인가 기준

기본 인가 모델은 다음 조합으로 판단한다.

| 기준 | 내용 |
| --- | --- |
| Role | `PRODUCT_DEPARTMENT_USER`, `COMPLIANCE_REVIEWER`, `STANDARD_MANAGER`, `SYSTEM_ADMIN` |
| Department scope | 사용자의 소속 부서 및 광고물 담당 부서 |
| Resource ownership | 광고물 등록자, 담당 부서, 검토 배정 정보 |
| Action | 조회, 등록, 수정, 분석 요청, 다운로드, 기준자료 변경, 관리자 기능 |
| Environment | `dev`, `prod(main)` 환경별 데이터/secret 분리 |

PoC 기본 정책은 다음과 같다.

| 역할 | 기본 범위 |
| --- | --- |
| 상품부서 담당자 | 본인 또는 소속 부서 광고물 등록, 분석 요청, 결과 조회 |
| 준법감시 담당자 | 검토 대상 광고물 전체 또는 배정 범위 조회, 심의 의견/리포트 생성 |
| 기준 관리자 | 기준자료 등록, 수정, 비활성화, 기준자료 조회 |
| 시스템 관리자 | 사용자, 권한, 감사 로그, 시스템 설정 관리 |

파일 미리보기와 다운로드는 ADR-0021 및 ADR-0055에 따라 backend 권한 검증을 통과한 뒤에만 허용한다.

## 토큰 기준

| 항목 | 기준 |
| --- | --- |
| Access Token | 짧은 만료시간의 JWT |
| Access Token 만료 | ADR-0056 기준 기본 30분 |
| Refresh Token 만료 | ADR-0056 기준 기본 7일 |
| Token claims | `sub`, `user_id`, `department_id`, `roles`, `iat`, `exp`, `jti`, `token_version` |
| Refresh Token 저장 | 원문 저장 금지. DB에는 hash만 저장 |
| Token 폐기 | 로그아웃, 사용자 비활성화, 권한 변경 시 refresh token revoke |
| Secret 관리 | 환경변수 또는 secret manager. Git 커밋 금지 |
| 로그 저장 금지 | access token, refresh token, 비밀번호, 인증 secret |
| 비밀번호 저장 | ADR-0048 기준 단방향 password hash 사용. 평문 저장 금지 |
| 로그인 보호 | ADR-0058 기준 실패 제한, 짧은 잠금, IP rate limit 적용 |

PoC에서 SSO가 제공되면 자체 로그인 대신 SSO를 붙일 수 있지만, API 내부의 사용자 컨텍스트와 권한 검증 인터페이스는 유지한다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 자체 로그인 + JWT | 구현이 단순하고 로컬/개발 VM에서 독립 실행이 쉽지만 SSO 전환 설계가 필요하다. |
| 사내/고객사 SSO 전제 | 운영 환경과 가장 가깝지만 PoC 초기에 연계 정보와 망 설정 지연 가능성이 크다. |
| 내부망 접근 + 고정 테스트 계정 | 가장 빠르지만 권한/감사 로그 검증 신뢰도가 낮다. |
| PoC 자체 JWT + SSO 전환 가능 구조 | PoC 속도와 본사업 전환 가능성의 균형이 좋다. |

## 결정 근거

- PoC는 로컬 개발과 공용 개발 VM에서 독립 실행 가능해야 한다.
- 권한 매트릭스, 파일 접근, 감사 로그 검증은 실제 사용자/역할/부서 컨텍스트가 있어야 한다.
- 고객사 SSO 연계는 본사업 또는 고객사 보안 정책 확정 후 진행될 가능성이 높다.
- 인증 제공자 경계를 두면 자체 JWT에서 SSO/OIDC/SAML로 전환할 때 업무 API와 권한 로직 변경을 줄일 수 있다.

## 영향

- API 공통 미들웨어는 Bearer Token을 검증하고 user context를 생성한다.
- 권한 검증은 라우터별 ad hoc 조건문이 아니라 ADR-0055 기준 공통 authorization service에서 수행한다.
- `users`, `departments`, `roles`, `user_roles`는 PoC seed 또는 관리자 API로 관리한다.
- 감사 로그에는 수행 당시 사용자, 부서, 대표 역할, trace ID를 기록한다.
- 테스트케이스는 401, 403, 타 부서 접근 제한, 관리자 API 제한을 P0로 유지한다.
- 세션과 토큰 수명, refresh token revoke는 ADR-0056 기준으로 구현한다.
- CORS, CSRF, cookie 보안 속성, 보안 헤더는 ADR-0057 기준으로 구현한다.
- 로그인 실패 제한, 계정 잠금, 비밀번호 정책은 ADR-0058 기준으로 구현한다.
- 본사업 전환 시 SSO 계정 매핑, 부서/역할 동기화, 고객사 IdP 세션 정책 정합은 후속 ADR 또는 운영 정책으로 확정한다.

## 후속 조치

- API 명세서에 자체 JWT + SSO 전환 가능 구조를 반영한다.
- DB 명세서의 `users`에 인증 제공자와 외부 사용자 식별자 필드를 보강한다.
- 기능명세서의 권한 범위 후속 상세화 항목은 ADR-0055 기준으로 정리한다.
- 테스트케이스에 만료 token, 비활성 사용자, 타 부서 접근 제한 케이스를 보강한다.
- 테스트케이스에 refresh token 갱신, 로그아웃 후 refresh 실패, 권한 변경 후 기존 token 거부 케이스를 보강한다.
- 테스트케이스에 로그인 실패 제한, 계정 잠금, rate limit, 비밀번호 정책 검증을 보강한다.
- 사용자 email/name 저장 및 민감정보 노출 제한은 ADR-0048을 따른다.
- 구현 시 `AuthProvider`, `AuthorizationService`, `CurrentUser` 컨텍스트를 공통 계층으로 둔다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0021-file-access-download-policy.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0055-api-authorization-scope-policy.md`
- `docs/adr/ADR-0056-jwt-session-token-lifetime-policy.md`
- `docs/adr/ADR-0057-browser-security-cors-csrf-headers.md`
- `docs/adr/ADR-0058-login-failure-lockout-password-policy.md`
- `docs/adr/ADR-0030-frontend-stack.md`
- `docs/adr/ADR-0048-poc-personal-sensitive-data-policy.md`
