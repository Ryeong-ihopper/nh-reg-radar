# ADR-0057: 브라우저 보안 정책, CORS/CSRF 및 보안 헤더 기준

## 상태

Accepted

## 배경

ADR-0056에서 refresh token은 httpOnly cookie로 전달하기로 결정했다. Cookie는 브라우저가 자동으로 전송하므로, 허용된 프론트엔드 origin에서만 API를 호출할 수 있게 제한하고 cookie 기반 인증 API에는 CSRF 방어 기준이 필요하다.

일반 업무 API는 `Authorization: Bearer {accessToken}` 헤더를 사용하므로 악성 사이트가 사용자의 access token 값을 읽어 임의로 붙일 수 없다. 반면 `/auth/refresh`, `/auth/logout`처럼 refresh token cookie를 사용하는 API는 브라우저가 cookie를 자동 전송할 수 있어 Origin 검증 또는 CSRF token 검증이 필요하다.

## 결정

PoC 브라우저 보안 정책은 CORS allowlist, refresh token cookie 보안 속성, cookie 기반 인증 API의 Origin 검증, 기본 보안 헤더를 함께 적용한다.

| 항목 | 결정 |
| --- | --- |
| CORS | 환경별 허용 origin allowlist만 허용 |
| Wildcard origin | `Access-Control-Allow-Origin: *` 금지 |
| Credentials | refresh token cookie가 필요한 인증 API에서만 `credentials` 허용 |
| Refresh token cookie | `HttpOnly`, `Secure`, `SameSite=Lax` 우선. 로컬 개발만 `Secure=false` 예외 |
| CSRF 방어 대상 | `/auth/refresh`, `/auth/logout` 등 cookie 기반 인증 API |
| CSRF 방어 방식 | PoC는 `Origin` 또는 `Referer` allowlist 검증 우선 |
| 일반 업무 API | Bearer access token 기반이므로 CSRF token 필수 대상에서 제외 |
| 보안 헤더 | API 또는 reverse proxy에서 최소 보안 헤더 적용 |

허용 origin은 환경 설정으로 관리한다.

| 환경 | 예시 origin |
| --- | --- |
| local | `http://localhost:5173` |
| dev | 개발 VM 또는 dev 도메인 |
| prod(main) | PoC main 배포 도메인 |

요청의 `Origin` 또는 `Referer`가 비어 있거나 allowlist에 없으면 cookie 기반 인증 API는 `403 FORBIDDEN`으로 거부한다. 서버 간 내부 호출, healthcheck, worker 내부 호출은 브라우저 cookie 인증을 사용하지 않는다.

## 보안 헤더 기준

최소 적용 헤더는 다음과 같다.

| 헤더 | 기준 |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-Frame-Options` | `DENY` 또는 CSP `frame-ancestors 'none'` |
| `Content-Security-Policy` | `default-src 'self'`를 기본으로 프론트엔드 자원 정책에 맞게 확장 |
| `Strict-Transport-Security` | HTTPS 환경에서 적용. local HTTP는 제외 |
| `Cache-Control` | 인증/민감 응답은 `no-store` 또는 동등한 캐시 방지 |

파일 미리보기, presigned URL, 리포트 다운로드는 파일 접근 정책과 함께 캐시 및 frame 표시 정책을 별도 응답 헤더로 조정할 수 있다. 단, 민감 파일 원문과 token은 URL, 로그, 오류 응답, referrer로 노출하지 않는다.

## 대안

| 대안 | 판단 |
| --- | --- |
| CORS allowlist만 적용 | 구현은 가장 단순하지만 cookie 기반 refresh에 대한 CSRF 방어가 약하다. |
| CORS allowlist + SameSite cookie만 적용 | PoC에는 빠르지만 환경별 도메인 분리와 예외 처리 기준이 모호하다. |
| CORS allowlist + cookie 보안 속성 + Origin 검증 + 기본 보안 헤더 | 보안과 구현 부담의 균형이 좋아 채택한다. |
| 모든 state-changing API에 CSRF token과 엄격 보안 헤더 전체 적용 | 가장 보수적이지만 PoC 초기 구현 부담이 크다. |

## 결정 근거

- Refresh token cookie는 httpOnly라도 브라우저가 자동 전송하므로 CSRF 방어 기준이 필요하다.
- 일반 업무 API는 Bearer access token을 사용하므로 CSRF token 필수 적용보다 CORS와 인증 헤더 검증이 실용적이다.
- Origin/Referer 검증은 PoC에서 구현 부담이 낮고 cookie 기반 인증 API의 핵심 위험을 줄인다.
- 보안 헤더를 공통 미들웨어 또는 reverse proxy에 적용하면 화면과 API의 기본 브라우저 보안 기준을 일관되게 유지할 수 있다.
- 본사업 전환 시 고객사 도메인, SSO redirect URI, reverse proxy 정책에 맞춰 allowlist와 CSP를 확장할 수 있다.

## 영향

- API 서버 또는 reverse proxy는 환경별 CORS allowlist를 설정해야 한다.
- `/auth/refresh`, `/auth/logout`은 Origin/Referer 검증을 통과해야 한다.
- 프론트엔드는 refresh/logout 요청에 credentials 포함 설정을 사용하되, 일반 업무 API는 Bearer access token을 사용한다.
- 테스트케이스는 허용 origin, 미허용 origin, cookie 속성, 보안 헤더, refresh/logout Origin 검증을 포함해야 한다.
- 개발 환경에서는 local HTTP 편의를 위해 `Secure=false` 예외를 허용하되, dev/prod(main)에서는 HTTPS와 `Secure=true`를 기준으로 한다.

## 후속 조치

- 배포 도메인 확정 시 `CORS_ALLOWED_ORIGINS`와 CSP 세부값을 환경별 설정에 반영한다.
- 본사업 SSO 전환 시 IdP redirect/callback origin과 CORS/CSP allowlist를 재검토한다.
- 외부 임베딩, 파일 미리보기 iframe, 별도 CDN 사용이 생기면 frame/CSP 정책을 별도 검토한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/project-rules.md`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0056-jwt-session-token-lifetime-policy.md`
- `docs/adr/ADR-0048-poc-personal-sensitive-data-policy.md`
