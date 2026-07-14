# ADR-0056: JWT 세션 및 토큰 수명 정책

## 상태

Accepted

## 배경

ADR-0036은 PoC 인증 방식을 자체 로그인 + JWT Bearer Token으로 정했고, ADR-0055는 API 인가 범위를 role + department scope 기준으로 정했다. 실제 구현에서는 access token 만료 시간, refresh token 사용 여부, 로그아웃 처리, 사용자 비활성화와 권한 변경 시 기존 토큰 처리 기준이 필요하다.

Access token만 사용하면 구현은 단순하지만 사용자 경험과 강제 로그아웃 제어가 약하다. Redis blacklist를 사용하면 즉시 폐기가 쉽지만 PoC 초기에는 운영 복잡도가 커진다. 따라서 PoC 규모와 보안 통제의 균형을 맞춘 세션 정책이 필요하다.

## 결정

PoC 인증 세션은 짧은 access token과 DB 저장 refresh token을 함께 사용한다.

| 항목 | 결정 |
| --- | --- |
| Access token | JWT, 기본 만료 30분 |
| Refresh token | 난수 기반 opaque token, 기본 만료 7일 |
| Refresh token 저장 | 평문 저장 금지. `refresh_tokens.token_hash`에 hash만 저장 |
| Refresh token 전달 | ADR-0057 기준 httpOnly, secure, sameSite cookie 우선. 로컬 개발은 secure 예외 가능 |
| 로그인 | access token 발급, refresh token 생성 및 hash 저장 |
| 토큰 갱신 | 유효한 refresh token으로 새 access token 발급 |
| 로그아웃 | 현재 refresh token을 revoke 처리 |
| 사용자 비활성화 | 해당 사용자의 모든 refresh token revoke |
| 권한 변경 | 해당 사용자의 모든 refresh token revoke 및 `users.auth_token_version` 증가 |
| Access token 강제 무효화 | JWT의 `token_version`과 `users.auth_token_version`이 다르면 401 처리 |
| 감사 로그 | 로그인, 로그아웃, refresh, token revoke, 권한 변경, 사용자 비활성화 기록 |

Access token에는 `sub`, `user_id`, `department_id`, `roles`, `iat`, `exp`, `jti`, `token_version`을 포함한다. 단, API 인가의 최종 기준은 ADR-0055에 따른 서버 측 사용자/권한 컨텍스트이며, token claim은 요청 사용자 식별과 빠른 검증을 위한 보조 정보로 사용한다.

## Refresh Token 관리

`refresh_tokens` 테이블은 최소 다음 정보를 가진다.

| 필드 | 설명 |
| --- | --- |
| `refresh_token_id` | refresh token 식별자 |
| `user_id` | 사용자 ID |
| `token_hash` | refresh token hash |
| `issued_at` | 발급 시각 |
| `expires_at` | 만료 시각 |
| `revoked_at` | 폐기 시각 |
| `revoked_reason` | `LOGOUT`, `ROLE_CHANGED`, `USER_DISABLED`, `ROTATED`, `EXPIRED`, `ADMIN_REVOKED` |
| `created_ip` | 발급 IP |
| `user_agent` | 발급 User Agent |

Refresh token은 rotation을 기본으로 한다. `/auth/refresh` 호출이 성공하면 기존 refresh token을 `ROTATED`로 revoke하고 새 refresh token을 발급한다. 재사용이 감지된 revoked refresh token은 인증 실패로 처리하고, 해당 사용자의 refresh token 전체 revoke 여부를 운영 정책으로 확장할 수 있다.

## 대안

| 대안 | 판단 |
| --- | --- |
| Access token만 사용 | 구현은 가장 단순하지만 로그아웃, 사용자 비활성화, 권한 변경 반영이 약하다. |
| Access token + DB 저장 refresh token | PoC 구현 부담과 보안 통제의 균형이 좋다. |
| Access token + Redis blacklist | 즉시 폐기 제어는 좋지만 Redis 의존과 운영 복잡도가 증가한다. |
| SSO 전환 전제 최소 세션 정책 | 빠르지만 PoC 자체 인증의 감사와 보안 검증이 약하다. |

## 결정 근거

- PoC 사용자는 소규모지만, 권한 변경과 사용자 비활성화가 실제 관리자 기능으로 존재한다.
- Refresh token을 hash로 저장하면 로그아웃과 강제 폐기가 가능하면서도 평문 token 저장 금지 원칙을 지킬 수 있다.
- Access token을 30분으로 짧게 유지하고 `auth_token_version`을 대조하면 stale access token의 위험을 낮출 수 있다.
- Redis blacklist는 본사업 또는 더 강한 즉시 폐기 요구가 생기면 추가 검토할 수 있다.
- httpOnly cookie를 우선 사용하면 브라우저 저장소에 refresh token을 노출하지 않을 수 있다.
- Cookie 기반 refresh/logout API의 Origin 검증과 CORS 기준은 ADR-0057을 따른다.

## 영향

- DB 명세에 `refresh_tokens` 테이블과 `users.auth_token_version` 컬럼이 필요하다.
- API 명세에 `/auth/refresh`와 refresh token cookie 처리 기준을 추가한다.
- 로그아웃, 사용자 비활성화, 권한 변경 API는 refresh token revoke를 함께 수행해야 한다.
- `/auth/refresh`, `/auth/logout`은 ADR-0057 기준 Origin 또는 Referer allowlist 검증을 수행해야 한다.
- 감사 로그는 token 원문이 아니라 token 식별자, 사용자, 결과, 사유 중심으로 기록한다.
- 테스트케이스는 access token 만료, refresh 성공, 로그아웃 후 refresh 실패, 권한 변경 후 기존 token 거부, token 원문 로그 미저장을 검증한다.

## 후속 조치

- 본사업 SSO 전환 시 refresh token 정책을 고객사 IdP session 정책과 정합시킨다.
- 모바일 또는 외부 클라이언트가 추가되면 cookie 대신 Authorization 기반 refresh 전달 방식을 재검토한다.
- Redis blacklist 또는 session store는 즉시 폐기 요구가 강화될 때 별도 ADR로 검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0048-poc-personal-sensitive-data-policy.md`
- `docs/adr/ADR-0055-api-authorization-scope-policy.md`
- `docs/adr/ADR-0057-browser-security-cors-csrf-headers.md`
