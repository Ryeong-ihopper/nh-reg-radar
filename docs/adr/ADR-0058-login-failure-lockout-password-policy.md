# ADR-0058: 로그인 실패 제한, 계정 잠금 및 비밀번호 정책

## 상태

Accepted

## 배경

ADR-0036에서 PoC 인증은 자체 로그인 + JWT Bearer Token으로 결정했다. ADR-0056과 ADR-0057은 토큰 수명, refresh token cookie, 브라우저 보안 기준을 정했다. 그러나 자체 로그인에서 비밀번호 최소 정책, 로그인 실패 제한, 계정 잠금, rate limit, 로그인 실패 감사 로그 기준은 아직 명확하지 않다.

PoC는 고객사 소규모 담당자가 제한적으로 사용하는 환경이므로 본사업 수준의 MFA나 강한 계정 잠금 정책을 모두 적용할 필요는 없다. 다만 무차별 로그인 시도와 특정 계정 대상 반복 시도에 대한 최소 방어선은 필요하다.

## 결정

PoC 자체 로그인은 비밀번호 최소 정책, 계정별 실패 횟수 제한, 짧은 계정 잠금, IP 단위 rate limit을 함께 적용한다.

| 항목 | 결정 |
| --- | --- |
| 비밀번호 저장 | ADR-0048 기준 `password_hash`만 저장 |
| 비밀번호 최소 길이 | 10자 이상 |
| 비밀번호 금지 기준 | email, 사용자 이름, 사용자 ID와 동일하거나 포함된 값 금지 |
| 비밀번호 복잡도 | PoC에서는 과도한 문자 조합 강제보다 길이와 사용자 정보 포함 금지를 우선 |
| 로그인 실패 제한 | 계정별 연속 5회 실패 시 15분 잠금 |
| 잠금 해제 | 15분 경과 후 자동 해제. 시스템 관리자의 수동 초기화는 후속 구현 가능 |
| 성공 로그인 | 실패 횟수 초기화, `last_login_at` 갱신 |
| 실패 응답 | 계정 존재 여부를 숨기는 일반 `401 UNAUTHORIZED` 응답 |
| 잠금 중 응답 | 공개 로그인 API에서는 일반 `401 UNAUTHORIZED` 응답으로 통일 |
| IP rate limit | 로그인 API 기준 1분 10회, 10분 50회 관찰 기준으로 적용 |
| MFA | PoC 필수 범위에서 제외. 본사업 전환 시 재검토 |
| 감사 로그 | 로그인 성공, 실패, 잠금 발생, 잠금 중 시도, rate limit 차단 기록 |

로그인 실패 응답 메시지는 `이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다.`처럼 계정 존재 여부, 비활성 여부, 잠금 여부를 직접 노출하지 않는 문구로 통일한다. 내부 감사 로그에는 `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `USER_INACTIVE`, `RATE_LIMITED` 같은 사유 코드를 기록할 수 있다.

## DB 관리 기준

`users`에는 최소 다음 필드를 둔다.

| 필드 | 설명 |
| --- | --- |
| `password_hash` | 비밀번호 hash |
| `failed_login_count` | 연속 로그인 실패 횟수 |
| `last_failed_login_at` | 마지막 로그인 실패 시각 |
| `locked_until` | 잠금 만료 시각 |
| `password_changed_at` | 비밀번호 변경 시각 |

IP 단위 rate limit은 Redis 또는 애플리케이션 rate limiter로 관리한다. PoC에서는 rate limit 카운터를 장기 업무 데이터로 저장하지 않는다. 단, rate limit 차단 이벤트는 감사 로그에 남긴다.

## 대안

| 대안 | 판단 |
| --- | --- |
| 비밀번호 hash만 저장, 실패 제한 없음 | 구현은 가장 단순하지만 무차별 로그인 시도 방어가 약하다. |
| 비밀번호 정책 + IP 단위 rate limit만 적용 | 구현 부담은 낮지만 특정 계정 대상 반복 시도 방어가 약하다. |
| 비밀번호 정책 + 계정별 실패 횟수 제한 + 짧은 잠금 + IP rate limit | 보안과 PoC 구현 부담의 균형이 좋아 채택한다. |
| 강한 비밀번호 정책 + 장시간 잠금 + 관리자 해제 + MFA 검토 | 본사업급 정책에 가깝고 PoC 초기에는 과하다. |

## 결정 근거

- 자체 로그인을 쓰는 이상 최소한의 무차별 대입 방어가 필요하다.
- 계정별 실패 제한은 특정 사용자 계정 대상 반복 시도를 줄인다.
- IP rate limit은 대량 로그인 시도를 줄이지만, 프록시/공유망 환경을 고려해 과도하게 낮게 잡지 않는다.
- 공개 로그인 응답에서 계정 존재 여부를 숨기면 사용자 enumeration 위험을 낮출 수 있다.
- MFA는 보안성은 높지만 고객사 계정 체계와 SSO 전환 가능성을 고려하면 PoC 필수 범위에서는 제외하는 편이 실용적이다.

## 영향

- DB 명세의 `users`에 실패 횟수, 잠금, 비밀번호 변경 시각 필드가 필요하다.
- 로그인 API는 실패 횟수 증가, 잠금 처리, 성공 시 초기화, rate limit 처리를 공통 인증 로직에서 수행해야 한다.
- API 오류 응답은 계정 존재 여부와 잠금 여부를 직접 노출하지 않아야 한다.
- 감사 로그는 로그인 실패 사유를 내부 코드로 남기되 비밀번호와 token 원문을 저장하지 않는다.
- 테스트케이스는 비밀번호 정책, 5회 실패 잠금, 잠금 중 일반 응답, 성공 시 실패 카운트 초기화, IP rate limit을 검증한다.

## 후속 조치

- 본사업 전환 또는 고객사 보안 정책 확정 시 비밀번호 만료, 재사용 금지, 관리자 잠금 해제, MFA, SSO 연동 정책을 재검토한다.
- 운영 관찰 후 rate limit 값이 과도하거나 부족하면 보안 설정 변경 기록으로 조정한다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/test-cases.md`
- `docs/adr/ADR-0022-audit-log-scope.md`
- `docs/adr/ADR-0036-jwt-auth-sso-ready-authorization.md`
- `docs/adr/ADR-0048-poc-personal-sensitive-data-policy.md`
- `docs/adr/ADR-0056-jwt-session-token-lifetime-policy.md`
- `docs/adr/ADR-0057-browser-security-cors-csrf-headers.md`
