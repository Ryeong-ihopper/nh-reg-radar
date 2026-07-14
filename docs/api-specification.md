# API 명세서

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-07-13 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, API/DB/화면/테스트 정합성 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | API 명세서 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 대상 시스템 | 멀티모달 RAG 기반 금융상품 광고심의 적정성 검토 AI 에이전트 PoC |
| 문서 버전 | v1.0 |
| 작성 목적 | 프론트엔드, 백엔드, AI 분석 모듈, DB 간 연동 기준 정의 |
| API 유형 | REST API |
| 데이터 형식 | JSON, Multipart Form Data |
| 인증 방식 | PoC 자체 JWT Bearer Token. 본사업 SSO 전환 가능 구조 |
| Base URL | `/api/v1` |

---

# 1. API 설계 원칙

## 1.1 기본 원칙

| 원칙 | 내용 |
| --- | --- |
| REST 기반 | 리소스 중심 URI를 사용한다. |
| JSON 표준 | 일반 요청/응답은 JSON을 사용한다. |
| 파일 업로드 | 광고물, 상품설명서, 약관, 기준자료 원문은 `multipart/form-data`를 사용한다. |
| 비동기 분석 | OCR, RAG, 멀티모달 분석 등 시간이 소요되는 작업은 Job 기반 비동기 처리한다. |
| 근거 기반 응답 | AI 검토 결과는 가능한 경우 근거 문서 ID와 함께 반환한다. |
| 이력 보존 | 광고물 등록, 분석 요청, 검토 결과, 문구 추천, 리포트 생성 이력을 저장한다. |
| 최종 판단 제한 | AI 검토 결과는 준법심의 지원용이며 최종 승인 판단으로 사용하지 않는다. |

---

## 1.2 주요 API 그룹

| 그룹 | 설명 |
| --- | --- |
| Auth API | PoC 로그인, 로그아웃, token 발급 |
| Common API | 공통 코드, 사용자 정보, 파일 미리보기 |
| Advertisement API | 광고물 등록, 조회, 수정, 수정본 등록 |
| Review API | AI 검토 요청, 진행 상태 조회, 재분석 |
| Review Result API | 검토 결과 요약, 상세 결과, 화면 Annotation 조회 |
| Evidence API | 법령, 내부기준, 심의사례 등 근거 검색 및 상세 조회 |
| Suggestion API | 보완 문구 추천 및 담당자 채택 여부 저장 |
| Q&A API | 광고 규정 질의응답 |
| Opinion Draft API | 심의 의견 초안 생성 및 수정 |
| Report API | 검토 리포트 생성, 조회, 다운로드 |
| Standard API | 광고심의 기준자료 등록, 수정, 비활성화 |
| Validation API | PoC 검증 데이터셋 및 성능 평가 |
| Admin API | 사용자, 권한, 감사 로그 관리 |

---

# 2. 공통 규격

## 2.1 공통 Header

| Header | 필수 | 설명 |
| --- | --- | --- |
| Authorization | Y | `Bearer {accessToken}`. 단, `/auth/login`은 제외 |
| Content-Type | Y | `application/json` 또는 `multipart/form-data` |
| Accept | Y | `application/json` |
| X-Request-Id | N | 요청 추적 ID |

인증/인가는 [ADR-0036: PoC 자체 JWT 인증 및 SSO 전환 가능 인가 구조](adr/ADR-0036-jwt-auth-sso-ready-authorization.md), [ADR-0056: JWT 세션 및 토큰 수명 정책](adr/ADR-0056-jwt-session-token-lifetime-policy.md), [ADR-0057: 브라우저 보안 정책, CORS/CSRF 및 보안 헤더 기준](adr/ADR-0057-browser-security-cors-csrf-headers.md), [ADR-0058: 로그인 실패 제한, 계정 잠금 및 비밀번호 정책](adr/ADR-0058-login-failure-lockout-password-policy.md)을 따른다. PoC는 자체 로그인으로 발급한 JWT를 사용하고, API 내부 권한 검증은 인증 제공자와 분리된 user context를 기준으로 수행한다.

## 2.1.1 인증/인가 기준

| 항목 | 기준 |
| --- | --- |
| 인증 방식 | PoC 자체 로그인 + JWT Bearer Token |
| 전환 구조 | 본사업 SSO/OIDC/SAML 연동 가능 AuthProvider 경계 |
| 사용자 기준 | `users`, `departments`, `roles`, `user_roles` |
| 인가 기준 | ADR-0055 기준 role + department scope |
| 토큰 수명 | ADR-0056 기준 access token 30분, refresh token 7일 |
| 감사 로그 연계 | `user_id`, `department_id`, 대표 `role`, `trace_id` 기록 |

Token에는 `sub`, `user_id`, `department_id`, `roles`, `iat`, `exp`, `jti`, `token_version`을 포함한다. access token, refresh token, 비밀번호, 인증 secret은 로그와 감사 로그에 저장하지 않는다.

### 2.1.2 공통 인가 처리

API 인가 범위는 ADR-0055를 따른다.

| API 유형 | 처리 기준 |
| --- | --- |
| 목록 조회 | 권한 범위 밖 데이터는 response에서 제외 |
| 단건 조회 | 권한 없으면 `403 FORBIDDEN` |
| 파일 미리보기/다운로드/presigned URL 발급 | 권한 없으면 `403 FORBIDDEN`, 거부 감사 로그 기록 |
| 등록/수정/삭제/상태 변경 | 권한 없으면 `403 FORBIDDEN` |
| 관리자 API | `SYSTEM_ADMIN`만 허용 |
| 기준자료 변경 API | `STANDARD_MANAGER` 또는 `SYSTEM_ADMIN`만 허용 |

| 역할 | 기본 scope |
| --- | --- |
| `PRODUCT_DEPARTMENT_USER` | 본인 또는 소속 부서 광고물과 관련 파일/리포트 |
| `COMPLIANCE_REVIEWER` | PoC 전체 검토 대상 광고물. 본사업 전환 시 배정 범위 재검토 |
| `STANDARD_MANAGER` | 기준자료 관리. 광고 원본 다운로드 기본 불가 |
| `SYSTEM_ADMIN` | 사용자/권한/감사 로그/시스템 설정. 원본 파일 접근은 장애 대응 사유 기록 필요 |

### 2.1.3 세션 및 토큰 처리

| 항목 | 기준 |
| --- | --- |
| Access token | JWT, 30분 만료, `Authorization: Bearer {accessToken}`로 전달 |
| Refresh token | 7일 만료 opaque token, httpOnly secure sameSite cookie 전달 우선 |
| Refresh token 저장 | DB에는 원문 저장 금지, `refresh_tokens.token_hash`만 저장 |
| Refresh token rotation | `/auth/refresh` 성공 시 기존 token revoke 후 새 token 발급 |
| 로그아웃 | 현재 refresh token revoke 및 cookie 삭제 |
| 사용자 비활성화 | 해당 사용자의 모든 refresh token revoke |
| 권한 변경 | 해당 사용자의 모든 refresh token revoke 및 `auth_token_version` 증가 |
| Access token 무효화 | JWT `token_version`과 DB `users.auth_token_version`이 다르면 `401 UNAUTHORIZED` |

### 2.1.4 브라우저 보안 처리

브라우저 보안 정책은 ADR-0057을 따른다.

| 항목 | 기준 |
| --- | --- |
| CORS | 환경별 allowlist origin만 허용 |
| Wildcard origin | `Access-Control-Allow-Origin: *` 금지 |
| Credentials | refresh token cookie가 필요한 인증 API에만 허용 |
| CSRF 방어 대상 | `/auth/refresh`, `/auth/logout` 등 cookie 기반 인증 API |
| CSRF 방어 방식 | `Origin` 또는 `Referer`가 allowlist에 없으면 `403 FORBIDDEN` |
| 일반 업무 API | `Authorization: Bearer {accessToken}` 기반. CSRF token 필수 대상에서 제외 |
| Cookie 속성 | `HttpOnly`, `Secure`, `SameSite=Lax` 우선. local HTTP만 `Secure=false` 예외 |
| 보안 헤더 | `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` 또는 CSP, 기본 CSP, HTTPS 환경 HSTS |
| 민감 응답 cache | 인증/민감 응답은 `Cache-Control: no-store` 또는 동등 기준 적용 |

### 2.1.5 로그인 보호 및 비밀번호 정책

로그인 실패 제한, 계정 잠금, 비밀번호 정책은 ADR-0058을 따른다.

| 항목 | 기준 |
| --- | --- |
| 비밀번호 저장 | `password_hash`만 저장 |
| 비밀번호 최소 기준 | 10자 이상, email/userName/userId 포함 금지 |
| 로그인 실패 제한 | 계정별 연속 5회 실패 시 15분 잠금 |
| 잠금 해제 | 15분 경과 후 자동 해제 |
| 성공 로그인 | 실패 횟수 초기화, `last_login_at` 갱신 |
| 실패/잠금 응답 | 계정 존재 여부를 숨기는 일반 `401 UNAUTHORIZED` 응답 |
| Rate limit | 로그인 API 기준 IP 단위 1분 10회, 10분 50회 관찰 기준 |
| 감사 로그 | 로그인 성공, 실패, 잠금 발생, 잠금 중 시도, rate limit 차단 기록 |
| MFA | PoC 필수 범위 제외, 본사업 전환 시 재검토 |

---

## 2.2 성공 응답 원칙

성공 응답은 공통 Wrapper로 감싸지 않고 HTTP status code와 리소스별 response schema를 그대로 사용한다. 성공 여부는 `success: true` 필드가 아니라 HTTP status code로 판단한다.

| 상황 | 응답 기준 |
| --- | --- |
| 단건 조회 | 리소스 객체를 그대로 반환 |
| 목록 조회 | 목록과 pagination metadata를 포함한 리소스별 schema 반환 |
| 생성 | `201 Created`와 생성된 리소스 또는 생성 식별자 반환 |
| 수정 | 수정된 리소스 또는 처리 결과 객체 반환 |
| 삭제 | 반환할 본문이 없으면 `204 No Content` 사용 |
| 비동기 요청 | 생성된 job 또는 review request 식별자와 상태 반환 |

개별 API의 성공 응답 예시는 업무 필드 이해를 돕기 위한 설명용이다. 최종 API 계약은 `openapi/openapi.yaml`의 리소스별 response schema를 기준으로 확정한다.

---

## 2.3 공통 오류 응답

오류 응답은 모든 API에서 공통 schema를 사용한다.

```json
{
  "code": "FILE_NOT_SUPPORTED",
  "message": "지원하지 않는 파일 형식입니다.",
  "details": [
    {
      "field": "advertisementFile",
      "reason": "jpg, jpeg, png, pdf, hwp, hwpx 파일만 업로드할 수 있습니다."
    }
  ],
  "traceId": "req-20260707-000001",
  "timestamp": "2026-07-07T10:30:00+09:00"
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| code | Y | 업무 또는 시스템 오류 코드 |
| message | Y | ADR-0045 기준 사용자에게 노출 가능한 기본 오류 메시지 |
| details | N | 필드 단위 오류, 원인, 추가 컨텍스트 |
| traceId | Y | 요청 추적 ID. `X-Request-Id`가 있으면 동일 값 사용 |
| timestamp | Y | 오류 발생 시각 |

---

## 2.4 공통 오류 코드

| 코드 | HTTP Status | 설명 | 기본 사용자 메시지 |
| --- | --- | --- | --- |
| BAD_REQUEST | 400 | 잘못된 요청 | 요청값을 확인해 주세요. |
| UNAUTHORIZED | 401 | 인증 실패 | 로그인이 필요합니다. |
| FORBIDDEN | 403 | 권한 없음 | 접근 권한이 없습니다. |
| NOT_FOUND | 404 | 리소스 없음 | 요청한 대상을 찾을 수 없습니다. |
| CONFLICT | 409 | 중복 요청 또는 상태 충돌 | 현재 상태에서는 요청을 처리할 수 없습니다. |
| RATE_LIMITED | 429 | 요청 횟수 초과 | 잠시 후 다시 시도해 주세요. |
| FILE_NOT_SUPPORTED | 400 | 지원하지 않는 파일 형식 | 지원하지 않는 파일 형식입니다. |
| FILE_READ_FAILED | 400 | 파일 판독 실패 | 파일을 읽지 못했습니다. 파일을 다시 확인해 주세요. |
| OCR_FAILED | 422 | OCR/VLM 판독 실패 | 문구를 판독하지 못했습니다. 원본 파일을 확인해 주세요. |
| STANDARD_NOT_FOUND | 422 | 기준자료 부족 | 관련 기준자료를 찾을 수 없습니다. |
| PRODUCT_INFO_MISSING | 422 | 상품설명서 또는 약관 부족 | 상품설명서 또는 약관이 없어 검토가 제한됩니다. |
| RAG_SEARCH_UNAVAILABLE | 503 | RAG 검색 인프라 일시 장애 | RAG 근거 검색을 수행하지 못했습니다. 잠시 후 다시 시도해 주세요. |
| RAG_SEARCH_FAILED | 500 | RAG 검색 처리 실패 | RAG 근거 검색 중 오류가 발생했습니다. 관리자 확인이 필요합니다. |
| REVIEW_ALREADY_RUNNING | 409 | 이미 분석 중인 광고물 | 이미 분석이 진행 중입니다. 진행 상태를 확인해 주세요. |
| AI_JOB_TIMEOUT | 500 | AI 분석 Job timeout | AI 검토 시간이 초과되었습니다. 진행 상태를 확인해 주세요. |
| AI_JOB_RETRY_EXHAUSTED | 500 | AI 분석 Job 재시도 한도 초과 | AI 검토를 완료하지 못했습니다. 재분석 가능 여부를 확인해 주세요. |
| AI_JOB_STALE | 500 | Worker heartbeat 장애 | AI 검토 작업 상태를 복구 중입니다. 잠시 후 다시 확인해 주세요. |
| REVIEW_FAILED | 500 | AI 검토 실패 | AI 검토 중 오류가 발생했습니다. 재분석을 요청해 주세요. |
| FILE_SIZE_EXCEEDED | 400 | 파일 크기 제한 초과 | 파일 용량이 50MB를 초과했습니다. |
| UNSUPPORTED_REPORT_FORMAT | 400 | 지원하지 않는 리포트 출력 형식 | 지원하지 않는 리포트 형식입니다. |
| INTERNAL_ERROR | 500 | 서버 내부 오류 | 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. |

---

## 2.5 ID 노출 규칙

API에 노출되는 주요 엔티티 ID는 Prefix 문자열을 사용한다. DB 내부 PK/FK는 UUID를 사용하며, API path parameter와 response의 `advertisementId`, `reviewId`, `reviewItemId`, `fileId` 등은 외부 노출 ID로 해석한다.

| 구분 | 예시 | 설명 |
| --- | --- | --- |
| 광고물 ID | `ADV-20260707-0001` | 광고물 외부 노출 ID |
| 검토 ID | `REV-20260707-0001` | AI 검토 요청/결과 외부 노출 ID |
| 검토 항목 ID | `ITEM-0001` | 검토 항목 외부 노출 ID. scope는 OpenAPI에서 확정 |
| 파일 ID | `FILE-0001` | 파일 조회/미리보기용 외부 노출 ID |
| 기준자료 ID | `STD-20260707-0001` | 기준자료 외부 노출 ID |
| 리포트 ID | `RPT-20260707-0001` | 리포트 외부 노출 ID |

ID 생성 및 저장 기준은 [ADR-0028: ID 생성 규칙](adr/ADR-0028-id-generation-policy.md)을 따른다.

---

# 3. 공통 Enum 정의

## 3.1 상품군

| 값 | 설명 |
| --- | --- |
| DEPOSIT | 예금 |
| SAVINGS | 적금 |
| DEMAND_DEPOSIT | 입출금 |
| EVENT_FINANCIAL_PRODUCT | 이벤트성 금융상품 |
| LOAN | 대출. 향후 확장 |
| CARD | 카드. 향후 확장 |
| INVESTMENT | 투자성 상품. 향후 확장 |

---

## 3.2 광고 유형

| 값 | 설명 |
| --- | --- |
| LEAFLET | 상품 안내장 |
| BRANCH_MEMO | 영업점 배포용 메모 |
| CUSTOMER_NOTICE | 고객 안내문 |
| MOBILE_BANNER | 모바일 배너 |
| INTERNET_BANKING_BANNER | 인터넷뱅킹 배너 |
| EVENT_PAGE | 이벤트 페이지 |
| APP_PUSH | 앱 Push |
| SMS | SMS |
| ALIMTALK | 알림톡 |
| HTML_CAPTURE | HTML 캡처 |

---

## 3.3 검토 상태

| 값 | 설명 |
| --- | --- |
| DRAFT | 임시저장 |
| UPLOADED | 업로드 완료 |
| ANALYSIS_REQUESTED | 분석 요청 |
| EXTRACTING | 텍스트 추출 중 |
| ANALYZING | AI 검토 중 |
| REVIEW_COMPLETED | 검토 완료 |
| REVIEW_FAILED | 검토 실패 |
| REVISED | 수정본 등록 |
| COMPARED | 수정 전후 비교 완료 |
| REPORT_CREATED | 리포트 생성 완료 |

---

## 3.4 검토 유형

| 값 | 설명 |
| --- | --- |
| REQUIRED_PHRASE | 필수 문구 검토 |
| INTEREST_RATE | 금리·수익률·조건 표시 검토 |
| MISLEADING_EXPRESSION | 과장·오인 표현 검토 |
| PRODUCT_CONSISTENCY | 상품설명서·약관 정합성 검토 |
| VISIBILITY | 위치·크기·강조·시인성 검토 |
| EVIDENCE_MATCHING | 근거 매칭 검토 |
| OCR_QUALITY | OCR 판독 품질 검토 |

---

## 3.5 판정 결과

| 값 | 설명 |
| --- | --- |
| APPROPRIATE | 적정 |
| NEEDS_REVISION | 수정 필요 |
| NEEDS_CONFIRMATION | 확인 필요 |
| NOT_APPLICABLE | 해당 없음 |
| REVIEW_EXCLUDED | 평가 제외 |

---

## 3.6 위험도

| 값 | 설명 |
| --- | --- |
| HIGH | 높음 |
| MEDIUM | 중간 |
| LOW | 낮음 |
| CHECK_REQUIRED | 확인 필요 |

## 3.7 신뢰도 상태

신뢰도 임계값은 ADR-0053 기준 YAML 설정으로 관리한다.

| 구분 | 값 | 설명 |
| --- | --- | --- |
| OCR text | READABLE | `confidenceScore >= 0.80` |
| OCR text | LOW_CONFIDENCE | `0.50 <= confidenceScore < 0.80` |
| OCR text | UNREADABLE | `confidenceScore < 0.50` |
| Parser structure | STRUCTURED | `confidenceScore >= 0.75` |
| Parser structure | PARTIALLY_STRUCTURED | `0.50 <= confidenceScore < 0.75` |
| Parser structure | UNSTRUCTURED | `confidenceScore < 0.50` |
| Annotation location | LOCATED | `locationConfidence >= 0.80` |
| Annotation location | LOW_CONFIDENCE / PARTIALLY_LOCATED | `0.50 <= locationConfidence < 0.80` |
| Annotation location | NOT_LOCATED | `locationConfidence < 0.50` 또는 위치 정보 없음 |

---

# 4. Auth/Common API

## 4.1 로그인

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/auth/login` |
| 설명 | PoC 자체 로그인으로 JWT access token을 발급하고 refresh token cookie를 설정한다. 로그인 실패 제한, 계정 잠금, rate limit은 ADR-0058 기준으로 처리한다. |

### Request

```json
{
  "email": "user@example.com",
  "password": "password"
}
```

### Response

```json
{
  "accessToken": "eyJhbGciOi...",
  "tokenType": "Bearer",
  "expiresIn": 1800,
  "user": {
    "userId": "user001",
    "userName": "홍길동",
    "departmentId": "DPT-001",
    "departmentName": "상품부",
    "roles": [
      "PRODUCT_DEPARTMENT_USER"
    ]
  }
}
```

성공 시 서버는 ADR-0056 기준 refresh token을 httpOnly cookie로 설정한다. 응답 본문과 로그에는 refresh token 원문을 포함하지 않는다.

로그인 실패, 비활성 사용자, 잠금 중인 사용자에 대한 응답은 계정 존재 여부를 숨기기 위해 일반 `401 UNAUTHORIZED`와 사용자 메시지 `이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다.`로 통일한다. IP rate limit 초과는 `429 RATE_LIMITED`로 응답한다.

---

## 4.2 로그아웃

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/auth/logout` |
| 설명 | 현재 refresh token을 revoke하고 refresh token cookie를 삭제한다. ADR-0057 기준 Origin 또는 Referer allowlist 검증을 적용한다. |

---

## 4.3 토큰 갱신

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/auth/refresh` |
| 설명 | 유효한 refresh token cookie로 새 access token을 발급한다. 성공 시 refresh token을 rotation한다. ADR-0057 기준 Origin 또는 Referer allowlist 검증을 적용한다. |

### Response

```json
{
  "accessToken": "eyJhbGciOi...",
  "tokenType": "Bearer",
  "expiresIn": 1800
}
```

---

## 4.4 로그인 사용자 정보 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/users/me` |
| 설명 | 현재 로그인한 사용자 정보를 조회한다. |

### Response

```json
{
  "userId": "user001",
  "userName": "홍길동",
  "departmentId": "DPT-001",
  "departmentName": "상품부",
  "roles": [
    "PRODUCT_DEPARTMENT_USER"
  ]
}
```

---

## 4.5 공통 코드 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/codes/{codeGroup}` |
| 설명 | 상품군, 광고유형, 검토유형, 위험도 등 공통 코드를 조회한다. |

### Path Variable

| 이름 | 설명 |
| --- | --- |
| codeGroup | `product-groups`, `advertisement-types`, `review-types`, `risk-levels`, `review-statuses` |

### Response

```json
[
  {
    "code": "SAVINGS",
    "name": "적금",
    "sortOrder": 2,
    "enabled": true
  }
]
```

---

## 4.6 파일 미리보기 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/files/{fileId}/preview` |
| 설명 | 광고 파일의 미리보기 URL 또는 렌더링 이미지를 조회한다. |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| pageNo | N | 페이지 번호 |

### Response

```json
{
  "fileId": "FILE-0001",
  "pageNo": 1,
  "totalPages": 1,
  "previewUrl": "/api/v1/files/FILE-0001/preview/pages/1",
  "width": 1080,
  "height": 1920
}
```

---

# 5. Advertisement API

## 5.1 광고물 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/advertisements` |
| 설명 | 등록된 광고물 목록을 조회한다. |
| 권한 | 상품부서 담당자, 준법감시 담당자, 시스템 관리자 |

권한 범위 밖 광고물은 ADR-0055 기준 목록 응답에서 제외한다.

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| keyword | N | 광고명 검색어 |
| productGroup | N | 상품군 |
| advertisementType | N | 광고유형 |
| reviewStatus | N | 검토 상태 |
| riskLevel | N | 종합 위험도 |
| fromDate | N | 등록 시작일 |
| toDate | N | 등록 종료일 |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

### Response

```json
{
  "contents": [
    {
      "advertisementId": "ADV-20260702-0001",
      "advertisementName": "NH 적금 이벤트 모바일 배너",
      "productGroup": "SAVINGS",
      "advertisementType": "MOBILE_BANNER",
      "registeredBy": "user001",
      "registeredAt": "2026-07-02T10:00:00+09:00",
      "reviewStatus": "REVIEW_COMPLETED",
      "overallRiskLevel": "MEDIUM",
      "latestReviewId": "REV-20260702-0001",
      "reportCreated": true
    }
  ],
  "page": 1,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1
}
```

---

## 5.2 광고물 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/advertisements` |
| Content-Type | `multipart/form-data` |
| 설명 | AI 검토 대상 광고물과 관련 첨부파일을 등록한다. |
| 권한 | 상품부서 담당자, 준법감시 담당자 |

### Form Data

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| advertisementName | Y | 광고명 |
| productGroup | Y | 상품군 |
| advertisementType | Y | 광고유형 |
| channelType | N | 광고채널 |
| departmentId | Y | 담당부서 ID |
| memo | N | 검토 요청 메모 |
| advertisementFile | Y | 광고 파일. 허용 확장자: jpg, jpeg, png, pdf, hwp, hwpx. 최대 50MB |
| productDescriptionFile | N | 상품설명서. 허용 확장자와 용량은 ADR-0037 기준 |
| termsFile | N | 약관. 허용 확장자와 용량은 ADR-0037 기준 |
| additionalFiles | N | 기타 첨부파일. 허용 확장자와 용량은 ADR-0037 기준 |

### Response

```json
{
  "advertisementId": "ADV-20260702-0001",
  "advertisementName": "NH 적금 이벤트 모바일 배너",
  "reviewStatus": "UPLOADED",
  "files": [
    {
      "fileId": "FILE-0001",
      "fileType": "ADVERTISEMENT",
      "fileName": "banner_sample.png",
      "mimeType": "image/png",
      "fileSize": 204800
    }
  ],
  "createdAt": "2026-07-02T10:00:00+09:00"
}
```

---

## 5.3 광고물 상세 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/advertisements/{advertisementId}` |
| 설명 | 광고물 기본정보, 파일정보, 최근 검토 상태를 조회한다. |

### Response

```json
{
  "advertisementId": "ADV-20260702-0001",
  "advertisementName": "NH 적금 이벤트 모바일 배너",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "channelType": "MOBILE_APP",
  "departmentId": "DPT-001",
  "registeredBy": "user001",
  "reviewStatus": "REVIEW_COMPLETED",
  "overallRiskLevel": "MEDIUM",
  "files": [
    {
      "fileId": "FILE-0001",
      "fileType": "ADVERTISEMENT",
      "fileName": "banner_sample.png"
    },
    {
      "fileId": "FILE-0002",
      "fileType": "PRODUCT_DESCRIPTION",
      "fileName": "product_description.pdf"
    }
  ],
  "latestReviewId": "REV-20260702-0001",
  "createdAt": "2026-07-02T10:00:00+09:00"
}
```

---

## 5.4 광고물 기본정보 수정

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/advertisements/{advertisementId}` |
| 설명 | 광고명, 상품군, 광고유형, 메모 등 기본정보를 수정한다. |

### Request

```
{
  "advertisementName": "NH 적금 이벤트 모바일 배너 수정",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "memo": "7월 이벤트 광고 초안"
}
```

### Response

```json
{
  "advertisementId": "ADV-20260702-0001",
  "updatedAt": "2026-07-02T10:20:00+09:00"
}
```

---

## 5.5 수정본 광고물 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/advertisements/{advertisementId}/revisions` |
| Content-Type | `multipart/form-data` |
| 설명 | 기존 광고물에 대한 수정본을 등록한다. |

### Form Data

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| revisionMemo | N | 수정 사유 |
| revisedAdvertisementFile | Y | 수정 광고 파일 |

### Response

```json
{
  "advertisementId": "ADV-20260702-0001",
  "revisionId": "REVISION-0001",
  "reviewStatus": "REVISED"
}
```

---

# 6. Review API

## 6.1 AI 검토 요청

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/advertisements/{advertisementId}/reviews` |
| 설명 | 등록된 광고물에 대해 AI 검토를 요청한다. |
| 처리 방식 | PostgreSQL Job 상태 생성 후 Redis Queue enqueue |

비동기 분석은 [ADR-0035: Redis Queue 및 PostgreSQL Job 상태 테이블 병행](adr/ADR-0035-redis-queue-postgresql-job-state.md)과 [ADR-0059: AI 분석 Job Timeout, Retry, Dead-letter 및 Worker 장애 복구 정책](adr/ADR-0059-ai-job-timeout-retry-deadletter-policy.md)을 따른다. API 서버는 `reviews`, `review_jobs`, `review_steps`를 생성하고 Redis Queue에 `job_id`를 enqueue한다. 진행 상태 조회 API는 Redis가 아니라 PostgreSQL의 `review_jobs`, `review_steps`를 조회한다.

동일 광고물에 `PENDING`, `RUNNING`, `RETRY_PENDING`, `STALE` 상태의 미완료 job이 있으면 중복 분석 요청으로 보고 `REVIEW_ALREADY_RUNNING`을 반환한다.

### Request

```json
{
  "standardEffectiveDate": "2026-07-02",
  "reviewTypes": [
    "REQUIRED_PHRASE",
    "INTEREST_RATE",
    "MISLEADING_EXPRESSION",
    "PRODUCT_CONSISTENCY",
    "VISIBILITY"
  ],
  "includeSuggestion": true,
  "includeOpinionDraft": false,
  "requestMemo": "모바일 배너 광고 사전 점검 요청"
}
```

`standardEffectiveDate`는 ADR-0040 기준 검토에 적용할 기준자료 기준일이다. 미지정 시 시스템이 기본 기준일을 산정해 review에 저장한다. API 서버는 해당 기준일에 유효한 `standard_version_id` 세트를 선택해 review에 고정한다.

### Response

```json
{
  "reviewId": "REV-20260702-0001",
  "advertisementId": "ADV-20260702-0001",
  "reviewStatus": "ANALYSIS_REQUESTED",
  "jobId": "JOB-20260702-0001",
  "standardEffectiveDate": "2026-07-02",
  "standardVersionIds": [
    "STDVER-0001"
  ],
  "requestedAt": "2026-07-02T10:30:00+09:00"
}
```

---

## 6.2 AI 검토 진행 상태 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/status` |
| 설명 | AI 검토 진행 상태를 조회한다. |

### Response

```json
{
  "reviewId": "REV-20260702-0001",
  "advertisementId": "ADV-20260702-0001",
  "reviewStatus": "ANALYZING",
  "jobId": "JOB-20260702-0001",
  "jobStatus": "RUNNING",
  "currentStep": "RAG_ENGINE_REVIEW",
  "progressRate": 65,
  "retryCount": 1,
  "maxRetries": 3,
  "nextRetryAt": null,
  "isRetryable": true,
  "failedReasonCode": null,
  "failedReason": null,
  "timeoutAt": "2026-07-02T11:00:00+09:00",
  "steps": [
    {
      "stepCode": "FILE_PREPROCESSING",
      "stepName": "파일 전처리",
      "status": "COMPLETED",
      "timeoutAt": "2026-07-02T10:33:00+09:00",
      "failedReasonCode": null
    },
    {
      "stepCode": "OCR_EXTRACTION",
      "stepName": "OCR/VLM 텍스트 추출",
      "status": "COMPLETED",
      "timeoutAt": "2026-07-02T10:40:00+09:00",
      "failedReasonCode": null
    },
    {
      "stepCode": "RAG_ENGINE_REVIEW",
      "stepName": "RAG 기반 근거 검색 및 검토",
      "status": "RUNNING",
      "timeoutAt": "2026-07-02T10:40:00+09:00",
      "failedReasonCode": null
    }
  ],
  "updatedAt": "2026-07-02T10:35:00+09:00"
}
```

`jobStatus`는 `PENDING`, `RUNNING`, `RETRY_PENDING`, `STALE`, `COMPLETED`, `FAILED`, `FAILED_FINAL`, `CANCELED` 중 하나로 반환한다. `RETRY_PENDING`인 경우 `nextRetryAt`을 함께 제공한다. `FAILED_FINAL`인 경우 `failedReasonCode`, `failedReason`, `isRetryable`을 제공하고, 화면은 `isRetryable=true`일 때만 재분석 요청 버튼을 표시한다.

Qdrant 또는 OpenSearch 장애로 RAG 검색을 정상 수행하지 못한 경우 ADR-0061 기준 keyword-only/vector-only fallback을 사용하지 않는다. 상태 조회는 `failedReasonCode`에 `RAG_SEARCH_UNAVAILABLE` 또는 `RAG_SEARCH_FAILED`를 반환하고, Job은 ADR-0059 기준 retry 또는 최종 실패 상태로 전환한다. 검색은 정상 수행됐지만 관련 근거가 부족한 경우에만 `CHECK_REQUIRED`, `REFERENCE_INSUFFICIENT`, `STANDARD_NOT_FOUND` 계열로 처리한다.

---

## 6.3 광고물별 검토 이력 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/advertisements/{advertisementId}/reviews` |
| 설명 | 특정 광고물의 AI 검토 이력을 조회한다. |

### Response

```json
[
  {
    "reviewId": "REV-20260702-0001",
    "reviewRound": 1,
    "reviewStatus": "REVIEW_COMPLETED",
    "overallRiskLevel": "MEDIUM",
    "requestedAt": "2026-07-02T10:30:00+09:00",
    "completedAt": "2026-07-02T10:40:00+09:00"
  }
]
```

---

## 6.4 AI 재분석 요청

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/reviews/{reviewId}/rerun` |
| 설명 | 기존 검토 결과를 기준으로 재분석을 요청한다. |

### Request

```
{
  "reason": "수정본 등록 후 재검토",
  "reviewTypes": [
    "REQUIRED_PHRASE",
    "MISLEADING_EXPRESSION",
    "VISIBILITY"
  ]
}
```

### Response

```json
{
  "newReviewId": "REV-20260702-0002",
  "previousReviewId": "REV-20260702-0001",
  "reviewStatus": "ANALYSIS_REQUESTED"
}
```

---

# 7. Review Result API

## 7.1 검토 결과 요약 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/summary` |
| 설명 | AI 검토 결과 요약 정보를 조회한다. |

### Response

```json
{
  "reviewId": "REV-20260702-0001",
  "advertisementId": "ADV-20260702-0001",
  "standardEffectiveDate": "2026-07-02",
  "standardVersionIds": [
    "STDVER-0001"
  ],
  "overallRiskLevel": "MEDIUM",
  "totalItemCount": 12,
  "needsRevisionCount": 4,
  "needsConfirmationCount": 2,
  "reviewTypeSummary": [
    {
      "reviewType": "REQUIRED_PHRASE",
      "totalCount": 4,
      "needsRevisionCount": 1,
      "needsConfirmationCount": 0
    },
    {
      "reviewType": "MISLEADING_EXPRESSION",
      "totalCount": 3,
      "needsRevisionCount": 2,
      "needsConfirmationCount": 1
    }
  ],
  "topRisks": [
    {
      "reviewItemId": "ITEM-0001",
      "riskLevel": "HIGH",
      "riskPolicyVersion": "risk-policy-v1",
      "riskReasonCodes": [
        "PROHIBITED_EXPRESSION",
        "HIGH_RAG_RELEVANCE"
      ],
      "targetText": "국내 최고 수준의 혜택",
      "reason": "확정적·과장 표현으로 소비자 오인 가능성이 있습니다."
    }
  ],
  "completedAt": "2026-07-02T10:40:00+09:00"
}
```

---

## 7.2 상세 검토 결과 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/items` |
| 설명 | AI 검토 항목별 상세 결과를 조회한다. |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| reviewType | N | 검토 유형 |
| riskLevel | N | 위험도 |
| resultStatus | N | 판정 결과 |
| evidenceRequired | N | 근거 필요 여부 |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

### Response

```json
{
  "contents": [
    {
      "reviewItemId": "ITEM-0001",
      "reviewType": "MISLEADING_EXPRESSION",
      "targetText": "국내 최고 수준의 혜택",
      "resultStatus": "NEEDS_REVISION",
      "riskLevel": "HIGH",
      "riskPolicyVersion": "risk-policy-v1",
      "riskReasonCodes": [
        "PROHIBITED_EXPRESSION",
        "HIGH_RAG_RELEVANCE"
      ],
      "reason": "객관적 근거 없이 최고 수준이라는 표현을 사용하여 과장 표현으로 해석될 수 있습니다.",
      "evidenceCount": 2,
      "suggestionCount": 1,
      "pageNo": 1,
      "hasAnnotation": true
    }
  ],
  "page": 1,
  "size": 20,
  "totalElements": 1
}
```

---

## 7.3 상세 검토 결과 단건 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/items/{reviewItemId}` |
| 설명 | 특정 검토 항목의 판단 사유, 근거, 추천 문구, 화면 좌표를 조회한다. |

### Response

```json
{
  "reviewItemId": "ITEM-0001",
  "reviewType": "MISLEADING_EXPRESSION",
  "targetText": "국내 최고 수준의 혜택",
  "resultStatus": "NEEDS_REVISION",
  "riskLevel": "HIGH",
  "riskPolicyVersion": "risk-policy-v1",
  "riskReasonCodes": [
    "PROHIBITED_EXPRESSION",
    "HIGH_RAG_RELEVANCE",
    "LLM_MISLEADING_CONTEXT"
  ],
  "riskRationale": {
    "riskLevel": "HIGH",
    "policyVersion": "risk-policy-v1",
    "reasonCodes": [
      "PROHIBITED_EXPRESSION",
      "HIGH_RAG_RELEVANCE",
      "LLM_MISLEADING_CONTEXT"
    ],
    "scoreDetail": {
      "rule": {
        "matched": true,
        "ruleIds": [
          "RULE-MISLEADING-001"
        ],
        "severity": "HIGH"
      },
      "rag": {
        "topRelevanceScore": 0.91,
        "evidenceCount": 2,
        "evidenceSufficient": true
      },
      "llm": {
        "decision": "RISKY",
        "confidence": 0.86
      },
      "parser": {
        "confidenceStatus": "READABLE"
      },
      "final": {
        "riskLevel": "HIGH",
        "decisionRule": "RULE_HIGH_OVERRIDES_LLM"
      }
    }
  },
  "reason": "객관적 근거 없이 최고 수준이라는 표현을 사용하여 소비자 오인 가능성이 있습니다.",
  "evidences": [
    {
      "evidenceId": "EVD-0001",
      "evidenceChunkId": "ECH-0001",
      "evidenceType": "INTERNAL_STANDARD",
      "title": "금융상품 광고심의 내부 기준",
      "articleNo": "3.2.1",
      "matchedText": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
      "rankNo": 1,
      "relevanceScore": 0.91,
      "matchSource": "HYBRID"
    }
  ],
  "suggestions": [
    {
      "suggestionId": "SUG-0001",
      "suggestedText": "조건 충족 시 우대 혜택을 제공받을 수 있습니다.",
      "suggestionReason": "확정적 표현을 조건부 표현으로 완화"
    }
  ],
  "annotation": {
    "pageNo": 1,
    "x": 120,
    "y": 240,
    "width": 320,
    "height": 48
  }
}
```

---

## 7.4 광고 화면 Annotation 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/annotations` |
| 설명 | 광고 화면 내 문제 영역 Annotation 표시 정보를 조회한다. |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| pageNo | N | 페이지 번호 |
| reviewType | N | 검토 유형 |
| riskLevel | N | 위험도 |

### Response

```json
{
  "reviewId": "REV-20260702-0001",
  "fileId": "FILE-0001",
  "fileType": "PDF",
  "pageNo": 1,
  "annotations": [
    {
      "annotationId": "ANN-0001",
      "reviewItemId": "ITEM-0001",
      "reviewType": "MISLEADING_EXPRESSION",
      "riskLevel": "HIGH",
      "targetText": "국내 최고 수준의 혜택",
      "annotationDisplayMode": "BOX",
      "annotationStatus": "LOCATED",
      "locationConfidence": 0.94,
      "confidencePolicyVersion": "confidence-thresholds-v1",
      "displayReason": "MATCHED_BOX",
      "pageNo": 1,
      "x": 120,
      "y": 240,
      "width": 320,
      "height": 48,
      "textBlockId": null,
      "textPath": null,
      "rawStartOffset": null,
      "rawEndOffset": null,
      "normalizedStartOffset": null,
      "normalizedEndOffset": null,
      "matchedText": null
    },
    {
      "annotationId": "ANN-0002",
      "reviewItemId": "ITEM-0002",
      "reviewType": "REQUIRED_PHRASE",
      "riskLevel": "CHECK_REQUIRED",
      "targetText": "중도해지 유의사항",
      "annotationDisplayMode": "TEXT_HIGHLIGHT",
      "annotationStatus": "PARTIALLY_LOCATED",
      "locationConfidence": 0.72,
      "confidencePolicyVersion": "confidence-thresholds-v1",
      "displayReason": "PARTIAL_TEXT_MATCH",
      "pageNo": null,
      "x": null,
      "y": null,
      "width": null,
      "height": null,
      "textBlockId": "OCR-0007",
      "textPath": "body/section[1]/paragraph[4]",
      "rawStartOffset": 348,
      "rawEndOffset": 365,
      "normalizedStartOffset": 342,
      "normalizedEndOffset": 359,
      "matchedText": "중도해지"
    }
  ]
}
```

---

# 8. Evidence API

## 8.1 근거 검색

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/evidences/search` |
| 설명 | 법령, 내부기준, 상품 기준, 심의사례 등 기준자료를 검색한다. |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| keyword | Y | 검색어 |
| evidenceType | N | 근거 유형 |
| productGroup | N | 상품군 |
| advertisementType | N | 광고유형 |
| ruleType | N | 필수/금지/권고/참고 |
| effectiveDate | N | 적용 기준일. 미지정 시 현재 유효한 기준일을 사용 |
| searchMode | N | `KEYWORD`, `VECTOR`, `HYBRID` |
| limit | N | 반환 개수. 기본 20, 최대 20 |

### Response

```json
[
  {
    "evidenceId": "EVD-0001",
    "evidenceChunkId": "ECH-0001",
    "evidenceType": "INTERNAL_STANDARD",
    "title": "금융상품 광고심의 내부 기준",
    "articleNo": "3.2.1",
    "ruleType": "PROHIBITED",
    "productGroup": "SAVINGS",
    "advertisementType": "MOBILE_BANNER",
    "contentSummary": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
    "effectiveDate": "2026-01-01",
    "standardVersionId": "STDVER-0001",
    "version": "1.0",
    "rankNo": 1,
    "relevanceScore": 0.91,
    "matchSource": "HYBRID"
  }
]
```

---

## 8.2 근거 상세 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/evidences/{evidenceId}` |
| 설명 | 특정 기준자료의 상세 내용을 조회한다. |

### Response

```json
{
  "evidenceId": "EVD-0001",
  "evidenceType": "INTERNAL_STANDARD",
  "title": "금융상품 광고심의 내부 기준",
  "articleNo": "3.2.1",
  "content": "객관적 근거 없는 최고, 유일, 보장 등 표현은 소비자 오인 가능성이 있으므로 사용에 유의한다.",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "ruleType": "PROHIBITED",
  "importance": "HIGH",
  "effectiveDate": "2026-01-01",
  "standardVersionId": "STDVER-0001",
  "version": "1.0",
  "sourceFileId": "FILE-EVD-0001"
}
```

---

## 8.3 기준자료 재색인 요청

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/standards/{standardId}/versions/{standardVersionId}/reindex` |
| 설명 | 기준자료 특정 버전을 기준으로 Chunk 또는 검색 인덱스를 재생성한다. |
| 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |

### Request

```json
{
  "reindexScope": "INDEX_ONLY",
  "reason": "embedding model changed",
  "parserRuleVersion": "reference-parser-rules-v1",
  "chunkingPolicyVersion": "reference-chunking-v1",
  "embeddingModel": "text-embedding-3-large",
  "searchSchemaVersion": "search-schema-v1",
  "opensearchAnalyzerVersion": "ko-analyzer-v1",
  "synonymVersion": "synonyms-v1",
  "targetIndexes": [
    "QDRANT",
    "OPENSEARCH"
  ]
}
```

`reindexScope`는 `INDEX_ONLY`, `CHUNK_AND_INDEX`, `KEYWORD_ONLY`, `VECTOR_ONLY` 중 하나를 사용한다. `searchSchemaVersion`, `opensearchAnalyzerVersion`, `synonymVersion`은 ADR-0071 기준 검색 인덱스 schema/analyzer/synonym 변경 추적에 사용한다. `prod(main)`에서는 `reason`이 필수다.

### Response

```json
{
  "jobId": "SRJ-0001",
  "standardId": "STD-0001",
  "standardVersionId": "STDVER-0001",
  "reindexScope": "INDEX_ONLY",
  "jobStatus": "QUEUED",
  "requestedAt": "2026-07-12T09:00:00Z"
}
```

---

## 8.4 기준자료 재색인 상태 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/standard-reindex-jobs/{jobId}` |
| 설명 | 기준자료 재색인 Job 상태와 대상 인덱스 처리 결과를 조회한다. |
| 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |

### Response

```json
{
  "jobId": "SRJ-0001",
  "standardId": "STD-0001",
  "standardVersionId": "STDVER-0001",
  "reindexScope": "INDEX_ONLY",
  "jobStatus": "SUCCEEDED",
  "targetIndexes": [
    "QDRANT",
    "OPENSEARCH"
  ],
  "parserRuleVersion": "reference-parser-rules-v1",
  "chunkingPolicyVersion": "reference-chunking-v1",
  "embeddingModel": "text-embedding-3-large",
  "searchSchemaVersion": "search-schema-v1",
  "opensearchAnalyzerVersion": "ko-analyzer-v1",
  "synonymVersion": "synonyms-v1",
  "createdChunkCount": 0,
  "indexedChunkCount": 128,
  "qdrantStatus": "ACTIVE",
  "opensearchStatus": "ACTIVE",
  "failedReasonCode": null,
  "failedReasonMessage": null,
  "requestedBy": "user001",
  "requestedAt": "2026-07-12T09:00:00Z",
  "startedAt": "2026-07-12T09:00:10Z",
  "completedAt": "2026-07-12T09:02:30Z"
}
```

---

## 8.5 근거 Chunk 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/evidences/{evidenceId}/chunks` |
| 설명 | 특정 근거의 Chunk 목록을 조회한다. 관리자/운영 검증용 API이며 일반 사용자 화면에는 직접 노출하지 않는다. |
| 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

### Response

```json
{
  "contents": [
    {
      "evidenceChunkId": "ECH-0001",
      "evidenceId": "EVD-0001",
      "standardId": "STD-0001",
      "standardVersionId": "STDVER-0001",
      "chunkNo": 1,
      "chunkText": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
      "tokenCount": 42,
      "sectionPath": "3/2/1",
      "articleNo": "3.2.1",
      "pageNo": 4,
      "structureConfidence": 0.92,
      "parserRuleVersion": "reference-parser-rules-v1",
      "chunkingPolicyVersion": "reference-chunking-v1",
      "embeddingModel": "text-embedding-3-large",
      "searchSchemaVersion": "search-schema-v1",
      "opensearchAnalyzerVersion": "ko-analyzer-v1",
      "synonymVersion": "synonyms-v1",
      "qdrantIndexStatus": "ACTIVE",
      "opensearchIndexStatus": "ACTIVE"
    }
  ],
  "page": 1,
  "size": 20,
  "totalElements": 1
}
```

---

## 8.6 근거 Chunk 상세 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/evidence-chunks/{evidenceChunkId}` |
| 설명 | RAG 품질 검증과 장애 분석을 위해 Chunk 상세와 검색 인덱스 연결 정보를 조회한다. |
| 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` |

### Response

```json
{
  "evidenceChunkId": "ECH-0001",
  "evidenceId": "EVD-0001",
  "standardId": "STD-0001",
  "standardVersionId": "STDVER-0001",
  "chunkNo": 1,
  "chunkText": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
  "tokenCount": 42,
  "sectionPath": "3/2/1",
  "articleNo": "3.2.1",
  "pageNo": 4,
  "sourceSpan": {
    "start": 120,
    "end": 178
  },
  "structureConfidence": 0.92,
  "parserRuleVersion": "reference-parser-rules-v1",
  "chunkingPolicyVersion": "reference-chunking-v1",
  "embeddingModel": "text-embedding-3-large",
  "searchSchemaVersion": "search-schema-v1",
  "opensearchAnalyzerVersion": "ko-analyzer-v1",
  "synonymVersion": "synonyms-v1",
  "deterministicIndexId": "prod:STDVER-0001:ECH-0001:text-embedding-3-large:reference-chunking-v1",
  "opensearchHighlights": {
    "title": [
      "금융상품 <em>광고심의</em> 내부 기준"
    ],
    "chunkText": [
      "객관적 근거 없는 <em>최고</em>, 유일, 보장 등 표현 사용 주의"
    ]
  },
  "qdrantIndexStatus": "ACTIVE",
  "qdrantIndexedAt": "2026-07-12T09:02:10Z",
  "qdrantIndexErrorCode": null,
  "qdrantCollection": "evidence_chunks",
  "qdrantPointId": "qdrant-point-0001",
  "opensearchIndexStatus": "ACTIVE",
  "opensearchIndexedAt": "2026-07-12T09:02:20Z",
  "opensearchIndexErrorCode": null,
  "opensearchIndex": "evidence_chunks_index",
  "opensearchDocId": "os-doc-0001"
}
```

---

# 9. Suggestion API

## 9.1 문구 추천 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/suggestions` |
| 설명 | AI가 생성한 보완 문구 및 대체 문구 목록을 조회한다. |

### Response

```json
[
  {
    "suggestionId": "SUG-0001",
    "reviewItemId": "ITEM-0001",
    "originalText": "국내 최고 수준의 혜택",
    "suggestedText": "조건 충족 시 우대 혜택을 제공받을 수 있습니다.",
    "suggestionReason": "확정적·과장 표현을 조건부 표현으로 완화",
    "evidenceIds": [
      "EVD-0001"
    ],
    "decisionStatus": "PENDING"
  }
]
```

---

## 9.2 문구 추천 채택 여부 저장

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/suggestions/{suggestionId}/decision` |
| 설명 | 담당자의 추천 문구 채택, 미채택, 수정 후 사용 여부를 저장한다. |

### Request

```json
{
  "decisionStatus": "MODIFIED_AND_USED",
  "finalText": "이벤트 조건 충족 시 우대 혜택을 제공받을 수 있습니다.",
  "comment": "조건 문구를 추가하여 사용"
}
```

`decisionStatus`는 ADR-0039 기준 `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED`만 허용한다. `MODIFIED_AND_USED`일 때 `finalText`는 필수이며, `ACCEPTED`에서 `finalText`가 없으면 기존 `suggestedText`를 최종 사용 문구로 간주한다. 판단 저장 시 `suggestion_decisions`에는 이력을 추가하고, `suggestions.decision_status`에는 최신 상태를 반영한다.

### Response

```json
{
  "suggestionId": "SUG-0001",
  "decisionStatus": "MODIFIED_AND_USED",
  "finalText": "이벤트 조건 충족 시 우대 혜택을 제공받을 수 있습니다.",
  "updatedAt": "2026-07-02T11:00:00+09:00"
}
```

---

# 10. Q&A API

## 10.1 광고 규정 질의응답 요청

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/qa/questions` |
| 설명 | 광고 규정 관련 질문을 입력하면 RAG 기반 답변을 생성한다. |

### Request

```json
{
  "question": "적금 모바일 배너에서 '국내 최고 수준의 혜택'이라는 표현을 사용할 수 있나요?",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "standardEffectiveDate": "2026-07-02"
}
```

`standardEffectiveDate`는 ADR-0040 기준 Q&A 답변에 사용할 기준자료 기준일이다.

### Response

```json
{
  "qaId": "QA-0001",
  "answerSummary": "객관적 근거 없이 '국내 최고 수준' 표현을 사용하는 것은 과장 표현으로 해석될 수 있어 주의가 필요합니다.",
  "answerDetail": "해당 표현을 사용하려면 객관적 비교 근거가 필요하며, 근거가 부족한 경우 조건부 표현 또는 구체적 혜택 설명으로 완화하는 것이 적절합니다.",
  "evidences": [
    {
      "evidenceId": "EVD-0001",
      "standardVersionId": "STDVER-0001",
      "title": "금융상품 광고심의 내부 기준",
      "articleNo": "3.2.1",
      "matchedText": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의"
    }
  ],
  "suggestedPhrases": [
    "조건 충족 시 우대 혜택을 제공받을 수 있습니다."
  ],
  "needsHumanReview": true
}
```

---

## 10.2 Q&A 이력 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/qa/questions` |
| 설명 | 광고 규정 Q&A 이력을 조회한다. |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| keyword | N | 질문 검색어 |
| productGroup | N | 상품군 |
| fromDate | N | 시작일 |
| toDate | N | 종료일 |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

---

# 11. Opinion Draft API

## 11.1 심의 의견 초안 생성

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/reviews/{reviewId}/opinion-drafts` |
| 설명 | AI 검토 결과를 기반으로 심의 의견 초안을 생성한다. |
| 권한 | 준법감시 담당자 |

### Request

```
{
  "includeReviewItemIds": [
    "ITEM-0001",
    "ITEM-0002"
  ],
  "templateType": "DEFAULT_COMPLIANCE_REVIEW",
  "additionalInstruction": "상품부서 보완 요청용으로 작성"
}
```

### Response

```json
{
  "draftId": "DRAFT-0001",
  "reviewId": "REV-20260702-0001",
  "draftContent": "해당 광고안은 일부 표현에 대해 소비자 오인 가능성이 있어 보완이 필요합니다. 특히 '국내 최고 수준의 혜택' 표현은 객관적 근거가 확인되지 않을 경우 과장 표현으로 해석될 수 있으므로 조건부 표현으로 수정하는 것이 바람직합니다.",
  "includedReviewItemIds": [
    "ITEM-0001",
    "ITEM-0002"
  ],
  "createdAt": "2026-07-02T11:10:00+09:00"
}
```

---

## 11.2 심의 의견 초안 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reviews/{reviewId}/opinion-drafts` |
| 설명 | 특정 검토 건에 생성된 심의 의견 초안 목록을 조회한다. |

---

## 11.3 심의 의견 초안 수정

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/opinion-drafts/{draftId}` |
| 설명 | 담당자가 AI 생성 심의 의견 초안을 수정한다. |

### Request

```
{
  "finalContent": "해당 광고안은 일부 표현에 대해 보완이 필요합니다. '국내 최고 수준의 혜택' 문구는 객관적 근거가 확인되지 않을 경우 과장 표현으로 해석될 수 있으므로, '조건 충족 시 우대 혜택 제공' 등으로 수정 요청합니다."
}
```

### Response

```json
{
  "draftId": "DRAFT-0001",
  "updatedAt": "2026-07-02T11:15:00+09:00"
}
```

---

# 12. Report API

## 12.1 검토 리포트 생성

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/reviews/{reviewId}/reports` |
| 설명 | AI 검토 결과 리포트를 생성한다. |

### Request

```
{
  "reportType": "FULL",
  "format": "HWPX",
  "includeAnnotations": true,
  "includeSuggestions": true,
  "includeOpinionDraft": true,
  "includeEvidenceDetails": true
}
```

`format`은 ADR-0038 기준 `HWPX`, `PDF`만 허용한다. 미지정 시 기본값은 `HWPX`이다.
PDF 요청은 ADR-0054 기준 HWPX 기준 산출물을 생성한 뒤 HWPX-to-PDF converter adapter로 변환한다.

### Response

```json
{
  "reportId": "RPT-0001",
  "reviewId": "REV-20260702-0001",
  "sourceReportId": null,
  "reportType": "FULL",
  "format": "HWPX",
  "reportStatus": "CREATED",
  "snapshotHash": "sha256:4c6f1f2d9b3a...",
  "snapshotVersion": "report-snapshot-v1",
  "rendererVersion": "hwpx-renderer-v1",
  "converterVersion": null,
  "createdAt": "2026-07-02T11:20:00+09:00"
}
```

---

## 12.2 검토 리포트 상세 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reports/{reportId}` |
| 설명 | 생성된 리포트의 메타데이터와 포함 항목을 조회한다. |

### Response

```json
{
  "reportId": "RPT-0001",
  "reviewId": "REV-20260702-0001",
  "sourceReportId": null,
  "reportType": "FULL",
  "format": "HWPX",
  "reportStatus": "CREATED",
  "snapshotHash": "sha256:4c6f1f2d9b3a...",
  "snapshotVersion": "report-snapshot-v1",
  "rendererVersion": "hwpx-renderer-v1",
  "converterVersion": null,
  "downloadUrl": "/api/v1/reports/RPT-0001/download",
  "createdBy": "user002",
  "createdAt": "2026-07-02T11:20:00+09:00"
}
```

---

## 12.3 검토 리포트 다운로드

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/reports/{reportId}/download` |
| 설명 | 생성된 HWPX 또는 PDF 리포트 파일을 다운로드한다. |
| Response | Binary File |

---

# 13. Comparison API

## 13.1 수정 전후 비교 요청

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/advertisements/{advertisementId}/comparisons` |
| 설명 | 최초 광고안과 수정 광고안을 비교한다. |

### Request

```
{
  "baseReviewId": "REV-20260702-0001",
  "revisionId": "REVISION-0001",
  "compareTypes": [
    "TEXT",
    "REQUIRED_PHRASE",
    "MISLEADING_EXPRESSION",
    "VISIBILITY"
  ]
}
```

### Response

```json
{
  "comparisonId": "CMP-0001",
  "advertisementId": "ADV-20260702-0001",
  "comparisonStatus": "COMPLETED",
  "resolvedIssueCount": 3,
  "unresolvedIssueCount": 1,
  "newIssueCount": 0
}
```

---

## 13.2 수정 전후 비교 결과 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/comparisons/{comparisonId}` |
| 설명 | 수정 전후 비교 상세 결과를 조회한다. |

### Response

```json
{
  "comparisonId": "CMP-0001",
  "summary": {
    "resolvedIssueCount": 3,
    "unresolvedIssueCount": 1,
    "newIssueCount": 0
  },
  "items": [
    {
      "reviewItemId": "ITEM-0001",
      "originalText": "국내 최고 수준의 혜택",
      "revisedText": "조건 충족 시 우대 혜택 제공",
      "resolutionStatus": "RESOLVED",
      "comment": "확정적 표현이 조건부 표현으로 수정되었습니다."
    }
  ]
}
```

---

# 14. Standard API

## 14.1 기준자료 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/standards` |
| 설명 | 광고심의 기준자료 목록을 조회한다. |
| 권한 | 기준 관리자, 시스템 관리자 |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| keyword | N | 기준명 또는 내용 검색 |
| evidenceType | N | 법령, 내부기준, 상품기준, 심의사례 등 |
| productGroup | N | 상품군 |
| advertisementType | N | 광고유형 |
| ruleType | N | 필수/금지/권고/참고 |
| activeOnly | N | 활성 기준만 조회 |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

---

## 14.2 기준자료 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/standards` |
| Content-Type | `multipart/form-data` |
| 설명 | 법령, 내부 매뉴얼, 필수 문구, 금지어, 심의사례, 문구 템플릿 등을 등록한다. |

### Form Data

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| title | Y | 기준자료명 |
| evidenceType | Y | 기준자료 유형 |
| productGroup | N | 적용 상품군 |
| advertisementType | N | 적용 광고유형 |
| ruleType | Y | 필수/금지/권고/참고 |
| importance | N | 중요도 |
| effectiveDate | N | 적용일 |
| expiredDate | N | 적용 종료일 |
| metadata | N | ADR-0050 기준 자료 유형별 확장 메타데이터 JSON |
| content | Y | 기준 내용 |
| sourceFile | N | 원문 파일 |

`metadata`는 ADR-0050 기준 `evidenceType`별 필수 메타데이터를 포함해야 한다. 예를 들어 법령/감독규정은 기관, 조문번호, 시행일, 개정일, 원문 출처를 포함하고, 심의사례는 사례번호, 판단유형, 지적사항, 조치결과, 판단일을 포함한다.

### Response

```json
{
  "standardId": "STD-0001",
  "evidenceId": "EVD-0001",
  "standardVersionId": "STDVER-0001",
  "version": "1.0",
  "isActive": true
}
```

---

## 14.3 기준자료 수정

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/standards/{standardId}` |
| 설명 | 기준자료 내용을 수정하고 버전을 갱신한다. |

### Request

```json
{
  "title": "금융상품 광고심의 내부 기준",
  "content": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용에 유의한다.",
  "effectiveDate": "2026-07-01",
  "expiredDate": null,
  "metadata": {
    "owningDepartment": "준법감시부",
    "sectionPath": "표현 심의 > 금지 표현"
  },
  "changeReason": "내부 기준 개정 반영"
}
```

기준자료 수정은 ADR-0040 기준 기존 version을 덮어쓰지 않고 새 `standard_versions` row를 생성한다. 응답에는 생성된 `standardVersionId`, `version`, `effectiveDate`를 반환한다.

---

## 14.4 기준자료 비활성화

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/standards/{standardId}/deactivate` |
| 설명 | 기준자료를 삭제하지 않고 비활성화한다. |

### Request

```json
{
  "reason": "개정 기준으로 대체"
}
```

---

## 14.5 기준자료 변경 이력 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/standards/{standardId}/histories` |
| 설명 | 기준자료의 변경 이력을 조회한다. |

---

# 15. Validation API

## 15.1 PoC 검증 데이터셋 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/validation/datasets` |
| 설명 | PoC 검증용 광고물 및 정답 데이터 목록을 조회한다. |

---

## 15.2 PoC 검증 데이터셋 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/validation/datasets` |
| Content-Type | `multipart/form-data` |
| 설명 | 검증용 광고물, 상품 조건, 담당자 판단 기준을 등록한다. |

### Form Data

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| datasetName | Y | 검증 데이터셋명 |
| productGroup | Y | 상품군 |
| advertisementType | Y | 광고유형 |
| advertisementFile | Y | 샘플 광고물 |
| productConditionFile | N | 상품 주요 조건 |
| humanReviewComment | N | 준법 검토 의견 |
| labelJson | N | 정답 데이터 JSON |
| excluded | N | 평가 제외 여부 |
| excludeReasonCode | N | 평가 제외 사유 코드 |
| excludeReasonDetail | N | 평가 제외 상세 사유 |

등록된 검증 데이터셋과 정답지는 ADR-0074 기준 DB를 공식 원천으로 사용한다. 이후 정답지, 상품조건, 평가 제외 사유가 수정되면 데이터셋 version을 증가시키고, 과거 평가 결과는 수정하지 않는다.

### 평가 제외 사유 코드

| 코드 | 설명 |
| --- | --- |
| OCR_UNREADABLE | ADR-0053 기준 OCR/Parser confidence `< 0.50`이고 판정 대상 문구 식별 불가 |
| PRODUCT_CONDITION_AMBIGUOUS | 상품조건 불명확 |
| REFERENCE_NOT_PROVIDED | 기준자료 미제공 |
| SOURCE_FILE_CORRUPTED | 원본 파일 손상 또는 분석 불가 |
| LABEL_UNCLEAR | 정답지 또는 담당자 판단 불명확 |
| DUPLICATE_SAMPLE | 중복 샘플 |
| OUT_OF_SCOPE | PoC 범위 외 샘플 |

---

## 15.3 담당자 판단 결과 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/validation/datasets/{datasetId}/judgments` |
| 설명 | AI 결과와 비교할 담당자 판단 결과를 등록한다. |

### Request

```json
{
  "judgments": [
    {
      "targetText": "국내 최고 수준의 혜택",
      "reviewType": "MISLEADING_EXPRESSION",
      "expectedStatus": "NEEDS_REVISION",
      "riskLevel": "HIGH",
      "comment": "객관적 근거 없는 최고 표현",
      "excluded": false,
      "excludeReasonCode": null,
      "excludeReasonDetail": null
    }
  ]
}
```

담당자 판단 결과는 ADR-0074 기준 공식 정답지의 일부로 관리한다. 판단 결과가 수정되면 judgment version을 증가시키고, 기존 평가 결과는 평가 실행 당시 snapshot 기준으로 유지한다.

---

## 15.4 PoC 성능 평가 실행

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/validation/evaluations` |
| 설명 | 검증 데이터셋 기준으로 PoC KPI를 산출한다. |

### Request

```json
{
  "datasetIds": [
    "DATASET-0001",
    "DATASET-0002"
  ],
  "metrics": [
    "REQUIRED_PHRASE_ACCURACY",
    "MISLEADING_EXPRESSION_ACCURACY",
    "EVIDENCE_PRECISION",
    "HUMAN_AGREEMENT_RATE"
  ],
  "excludeInvalidSamples": true,
  "reviewSelectionPolicy": "LATEST_COMPLETED"
}
```

### Response

```json
{
  "evaluationId": "EVAL-0001",
  "evaluationStatus": "COMPLETED",
  "snapshotHash": "sha256:7d9f2d0a1a4e...",
  "snapshotCreatedAt": "2026-07-13T10:00:00+09:00",
  "datasetSnapshotCount": 2,
  "exclusionSummary": [
    {
      "excludeReasonCode": "OCR_UNREADABLE",
      "count": 2
    },
    {
      "excludeReasonCode": "PRODUCT_CONDITION_AMBIGUOUS",
      "count": 1
    }
  ],
  "metrics": [
    {
      "metricCode": "REQUIRED_PHRASE_ACCURACY",
      "metricName": "필수 문구 검토 정확도",
      "score": 82.5,
      "numerator": 33.0,
      "denominator": 40,
      "excludedCount": 2,
      "partialCount": 3,
      "notApplicable": false,
      "targetScore": 80.0,
      "achieved": true
    },
    {
      "metricCode": "MISLEADING_EXPRESSION_ACCURACY",
      "metricName": "위험 표현 검토 정확도",
      "score": 76.0,
      "numerator": 19.0,
      "denominator": 25,
      "excludedCount": 1,
      "partialCount": 2,
      "notApplicable": false,
      "targetScore": 75.0,
      "achieved": true
    },
    {
      "metricCode": "EVIDENCE_PRECISION",
      "metricName": "근거 매칭 적정성",
      "score": 86.0,
      "numerator": 43.0,
      "denominator": 50,
      "excludedCount": 0,
      "partialCount": 4,
      "notApplicable": false,
      "targetScore": 85.0,
      "achieved": true
    },
    {
      "metricCode": "HUMAN_AGREEMENT_RATE",
      "metricName": "담당자 판단 일치율",
      "score": 74.0,
      "numerator": 37.0,
      "denominator": 50,
      "excludedCount": 0,
      "partialCount": 5,
      "notApplicable": false,
      "targetScore": 75.0,
      "achieved": false
    }
  ]
}
```

### Metric 산출 필드

| 필드 | 설명 |
| --- | --- |
| score | `numerator / denominator * 100`으로 산출한 KPI 점수 |
| numerator | 항목별 match score 합계 |
| denominator | 평가 대상 항목 수 또는 평가 대상 근거 수 |
| excludedCount | 평가 제외 건수 |
| partialCount | 부분 정답 건수 |
| notApplicable | 분모가 0이라 목표 달성 여부를 계산하지 않는지 여부 |
| targetScore | KPI 목표 점수 |
| achieved | 목표 달성 여부. `notApplicable=true`이면 `false`로 처리 |

`exclusionSummary`는 KPI 분모에서 제외된 샘플 또는 평가 항목의 사유별 건수를 나타낸다. AI 오답은 제외 사유로 집계하지 않는다.

평가 실행 시점에는 ADR-0074 기준으로 데이터셋, 담당자 판단, 제외 사유, 선택된 AI 검토 결과, 기준자료/모델/프롬프트/Parser/OCR/RAG/Search 버전, KPI 정책을 snapshot으로 저장한다. `reviewSelectionPolicy=LATEST_COMPLETED`는 각 데이터셋에 연결된 최신 완료 AI 검토 결과를 평가 대상으로 선택한다. 특정 reviewId 지정 방식이 필요해지면 후속 API 확장에서 `reviewIdsByDataset` 형태로 추가한다.

---

## 15.5 PoC 성능 평가 결과 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/validation/evaluations/{evaluationId}` |
| 설명 | 특정 평가 결과를 조회한다. 현재 정답지가 아니라 평가 실행 당시 snapshot 기준 결과를 반환한다. |

### Response

```json
{
  "evaluationId": "EVAL-0001",
  "evaluationStatus": "COMPLETED",
  "snapshotHash": "sha256:7d9f2d0a1a4e...",
  "snapshotCreatedAt": "2026-07-13T10:00:00+09:00",
  "datasetSnapshotCount": 2,
  "reviewSelectionPolicy": "LATEST_COMPLETED",
  "versionSnapshot": {
    "standardVersionIds": [
      "STDVER-0001"
    ],
    "modelVersion": "gpt-4.1-2026-07",
    "promptVersion": "review-prompt-v3",
    "parserOcrPolicy": "ADR-0072/ADR-0073",
    "ragSearchPolicy": "ADR-0043/ADR-0071"
  },
  "metrics": [
    {
      "metricCode": "REQUIRED_PHRASE_ACCURACY",
      "score": 82.5,
      "numerator": 33.0,
      "denominator": 40,
      "excludedCount": 2,
      "partialCount": 3,
      "notApplicable": false,
      "targetScore": 80.0,
      "achieved": true
    }
  ]
}
```

---

# 16. Admin API

## 16.1 사용자 목록 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/admin/users` |
| 설명 | 시스템 사용자 목록을 조회한다. |
| 권한 | 시스템 관리자 |

---

## 16.2 사용자 등록

| 항목 | 내용 |
| --- | --- |
| Method | POST |
| URI | `/api/v1/admin/users` |
| 설명 | 시스템 사용자를 등록한다. |

### Request

```
{
  "userName": "홍길동",
  "email": "user@example.com",
  "departmentId": "DPT-001",
  "roles": [
    "PRODUCT_DEPARTMENT_USER"
  ]
}
```

---

## 16.3 사용자 권한 변경

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/admin/users/{userId}/roles` |
| 설명 | 사용자 권한을 변경한다. |

### Request

```
{
  "roles": [
    "PRODUCT_DEPARTMENT_USER",
    "COMPLIANCE_REVIEWER"
  ]
}
```

---

## 16.4 사용자 비활성화

| 항목 | 내용 |
| --- | --- |
| Method | PATCH |
| URI | `/api/v1/admin/users/{userId}/deactivate` |
| 설명 | 사용자 계정을 비활성화한다. |

### Request

```
{
  "reason": "부서 이동"
}
```

---

## 16.5 시스템 감사 로그 조회

| 항목 | 내용 |
| --- | --- |
| Method | GET |
| URI | `/api/v1/admin/audit-logs` |
| 설명 | 광고물 등록, 분석 요청, 리포트 생성, 기준자료 변경 등 주요 로그를 조회한다. |
| 권한 | 시스템 관리자 |

### Query Parameters

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| userId | N | 사용자 ID |
| actionType | N | 행위 유형 |
| fromDate | N | 시작일 |
| toDate | N | 종료일 |
| page | N | 페이지 번호 |
| size | N | 페이지 크기 |

---

# 17. 주요 데이터 모델

## 17.1 Advertisement

```
{
  "advertisementId": "ADV-20260702-0001",
  "advertisementName": "NH 적금 이벤트 모바일 배너",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "channelType": "MOBILE_APP",
  "departmentId": "DPT-001",
  "registeredBy": "user001",
  "reviewStatus": "UPLOADED",
  "overallRiskLevel": "MEDIUM",
  "createdAt": "2026-07-02T10:00:00+09:00",
  "updatedAt": "2026-07-02T10:20:00+09:00"
}
```

---

## 17.2 Review

```
{
  "reviewId": "REV-20260702-0001",
  "advertisementId": "ADV-20260702-0001",
  "reviewRound": 1,
  "reviewStatus": "REVIEW_COMPLETED",
  "overallRiskLevel": "MEDIUM",
  "requestedBy": "user001",
  "requestedAt": "2026-07-02T10:30:00+09:00",
  "completedAt": "2026-07-02T10:40:00+09:00"
}
```

---

## 17.3 ReviewItem

```
{
  "reviewItemId": "ITEM-0001",
  "reviewId": "REV-20260702-0001",
  "reviewType": "MISLEADING_EXPRESSION",
  "targetText": "국내 최고 수준의 혜택",
  "resultStatus": "NEEDS_REVISION",
  "riskLevel": "HIGH",
  "riskPolicyVersion": "risk-policy-v1",
  "riskReasonCodes": [
    "PROHIBITED_EXPRESSION",
    "HIGH_RAG_RELEVANCE",
    "LLM_MISLEADING_CONTEXT"
  ],
  "reason": "객관적 근거 없는 최고 표현으로 소비자 오인 가능성이 있습니다.",
  "pageNo": 1,
  "evidenceIds": [
    "EVD-0001"
  ],
  "suggestionIds": [
    "SUG-0001"
  ]
}
```

---

## 17.4 Evidence

```
{
  "evidenceId": "EVD-0001",
  "evidenceType": "INTERNAL_STANDARD",
  "title": "금융상품 광고심의 내부 기준",
  "articleNo": "3.2.1",
  "content": "객관적 근거 없는 최고, 유일, 보장 등 표현 사용 주의",
  "productGroup": "SAVINGS",
  "advertisementType": "MOBILE_BANNER",
  "ruleType": "PROHIBITED",
  "importance": "HIGH",
  "effectiveDate": "2026-01-01",
  "version": "1.0"
}
```

---

## 17.5 Annotation

```json
{
  "annotationId": "ANN-0001",
  "reviewItemId": "ITEM-0001",
  "fileId": "FILE-0001",
  "annotationDisplayMode": "BOX",
  "annotationStatus": "LOCATED",
  "locationConfidence": 0.94,
  "confidencePolicyVersion": "confidence-thresholds-v1",
  "displayReason": "MATCHED_BOX",
  "pageNo": 1,
  "coordinate": {
    "sourceWidth": 1080,
    "sourceHeight": 1920,
    "sourceUnit": "px",
    "x": 120,
    "y": 240,
    "width": 320,
    "height": 48,
    "normalizedX": 0.1111,
    "normalizedY": 0.125,
    "normalizedWidth": 0.2963,
    "normalizedHeight": 0.025,
    "rotation": 0,
    "coordinateConfidence": 0.94
  },
  "textBlockId": null,
  "textPath": null,
  "rawStartOffset": null,
  "rawEndOffset": null,
  "normalizedStartOffset": null,
  "normalizedEndOffset": null,
  "matchedText": null,
  "riskLevel": "HIGH",
  "reviewType": "MISLEADING_EXPRESSION"
}
```

---

## 17.6 Text IR Block

Text IR Block은 ADR-0065의 `NormalizedDocument.textBlocks` 영속화/응답 기준을 따른다. Parser/OCR adapter raw output은 API 계약으로 직접 노출하지 않고, ADR-0067 기준 내부 artifact 참조만 사용한다.

```json
{
  "textBlockId": "OCR-0007",
  "fileId": "FILE-0001",
  "pageNo": null,
  "textPath": "body/section[1]/paragraph[4]",
  "textBlockType": "PARAGRAPH",
  "rawText": "중도해지 시 불이익이 발생할 수 있습니다.",
  "normalizedText": "중도해지 시 불이익이 발생할 수 있습니다.",
  "rawStartOffset": 348,
  "rawEndOffset": 372,
  "normalizedStartOffset": 342,
  "normalizedEndOffset": 366,
  "parserName": "rhwp",
  "parserVersion": "0.1.0",
  "parserRuleVersion": "hwp-text-ir-v1",
  "irVersion": "text-ir-v1",
  "confidenceScore": 0.98,
  "confidenceStatus": "READABLE",
  "confidencePolicyVersion": "confidence-thresholds-v1",
  "coordinate": null
}
```

## 17.7 Coordinate

Coordinate는 ADR-0015, ADR-0065, ADR-0066 기준 원본 좌표와 정규화 좌표를 함께 표현한다. 렌더링 좌표는 API에서 저장하거나 반환하지 않고 프론트엔드가 현재 뷰어 크기와 배율 기준으로 계산한다.

```json
{
  "sourceWidth": 1080,
  "sourceHeight": 1920,
  "sourceUnit": "px",
  "x": 120,
  "y": 240,
  "width": 320,
  "height": 48,
  "normalizedX": 0.1111,
  "normalizedY": 0.125,
  "normalizedWidth": 0.2963,
  "normalizedHeight": 0.025,
  "rotation": 0,
  "coordinateConfidence": 0.94
}
```

## 17.8 NormalizedDocument v1

`NormalizedDocument`는 Parser/OCR adapter의 공통 출력 계약이다. API/OpenAPI schema와 adapter contract test는 ADR-0065 기준 `normalized-document-v1`을 따른다.

```json
{
  "documentId": "NDOC-0001",
  "sourceFileId": "FILE-0001",
  "reviewId": "REV-0001",
  "sourceFileType": "hwpx",
  "parserName": "opendataloader-pdf",
  "parserVersion": "1.0.0",
  "parserRuleVersion": "normalized-document-rules-v1",
  "irVersion": "normalized-document-v1",
  "pages": [],
  "textBlocks": [],
  "layoutBlocks": [],
  "tables": [],
  "warnings": [],
  "confidence": {
    "score": 0.98,
    "status": "READABLE",
    "policyVersion": "confidence-thresholds-v1"
  },
  "rawArtifactRef": "RAWART-0001",
  "createdAt": "2026-07-12T09:00:00Z"
}
```

`rawArtifactRef`는 내부 raw artifact 참조값이며, 일반 사용자에게 다운로드 가능한 URL 또는 Object Storage 전체 경로로 제공하지 않는다.

---

# 18. API 호출 흐름

## 18.1 광고물 등록 및 AI 검토 흐름

```
1. POST /api/v1/advertisements
   → 광고물 등록

2. POST /api/v1/advertisements/{advertisementId}/reviews
   → AI 검토 요청

3. GET /api/v1/reviews/{reviewId}/status
   → 검토 진행 상태 조회

4. GET /api/v1/reviews/{reviewId}/summary
   → 검토 결과 요약 조회

5. GET /api/v1/reviews/{reviewId}/items
   → 상세 검토 결과 조회

6. GET /api/v1/reviews/{reviewId}/annotations
   → 광고 화면 문제 영역 조회

7. GET /api/v1/reviews/{reviewId}/suggestions
   → 문구 추천 조회

8. POST /api/v1/reviews/{reviewId}/reports
   → 검토 리포트 생성
```

---

## 18.2 기준자료 관리 및 RAG 검색 흐름

```
1. POST /api/v1/standards
   → 기준자료 등록

2. GET /api/v1/standards
   → 기준자료 목록 조회

3. GET /api/v1/evidences/search
   → 광고 검토 또는 Q&A에서 근거 검색

4. GET /api/v1/evidences/{evidenceId}
   → 근거 상세 조회
```

---

## 18.3 PoC 검증 흐름

```
1. POST /api/v1/validation/datasets
   → 검증 데이터셋 등록

2. POST /api/v1/validation/datasets/{datasetId}/judgments
   → 담당자 판단 결과 등록

3. POST /api/v1/validation/evaluations
   → KPI 평가 실행

4. GET /api/v1/validation/evaluations/{evaluationId}
   → 평가 결과 조회
```

---

# 19. DB 명세서 연계 대상 테이블

다음 단계의 DB 명세서는 아래 테이블을 중심으로 작성한다.

| API 영역 | 주요 테이블 후보 |
| --- | --- |
| 광고물 관리 | `advertisements`, `advertisement_files`, `advertisement_revisions` |
| AI 검토 | `reviews`, `review_jobs`, `review_steps`, `review_items` |
| 화면 표시 | `annotations`, `ocr_text_blocks`, `layout_blocks` |
| 근거 관리 | `evidences`, `standards`, `standard_versions`, `evidence_chunks` |
| 문구 추천 | `suggestions`, `suggestion_decisions` |
| Q&A | `qa_sessions`, `qa_messages`, `qa_message_evidences` |
| 심의 의견 | `opinion_drafts` |
| 리포트 | `reports` |
| 검증 | `validation_datasets`, `validation_judgments`, `evaluations`, `evaluation_metrics` |
| 운영/권한 | `users`, `departments`, `roles`, `user_roles`, `refresh_tokens`, `audit_logs` |

---

# 20. 테스트케이스 연계 기준

테스트케이스는 API별로 최소 다음 유형을 포함한다.

| 테스트 유형 | 설명 |
| --- | --- |
| 정상 케이스 | 필수 요청값이 모두 유효한 경우 |
| 필수값 누락 | 필수 요청 필드가 누락된 경우 |
| 권한 오류 | 권한 없는 사용자가 API를 호출한 경우 |
| 상태 충돌 | 분석 중인 광고물에 중복 분석 요청한 경우 |
| 파일 오류 | 지원하지 않는 파일 또는 손상 파일 업로드 |
| 기준자료 부족 | 근거 검색 또는 검토 기준이 부족한 경우 |
| AI 분석 실패 | OCR, RAG, 멀티모달 분석 실패 |
| 페이징/필터 | 목록 조회 조건, 페이지, 정렬 검증 |
| 이력 검증 | 분석 재요청, 수정본 등록, 리포트 생성 이력 검증 |
| 감사 로그 | 주요 변경 행위가 로그로 저장되는지 검증 |

---

# 21. 후속 상세화 필요사항

| 항목 | 상세화 필요 내용 |
| --- | --- |
| OpenAPI 계약 관리 | ADR-0026 기준 `openapi/openapi.yaml`을 API 계약 원천으로 관리. ADR-0062 기준 핵심 플로우 API부터 작성하고 Spectral lint, 타입 생성 diff, FastAPI generated OpenAPI diff를 단계적으로 적용 |
| 인증/인가 | ADR-0036 기준 PoC 자체 JWT + 본사업 SSO 전환 가능 구조 적용. API 인가는 ADR-0055 기준 role + department scope로 처리. 세션과 토큰 수명은 ADR-0056 기준 적용 |
| 브라우저 보안 | ADR-0057 기준 CORS allowlist, cookie 기반 인증 API Origin 검증, 기본 보안 헤더 적용 |
| 로그인 보호 | ADR-0058 기준 비밀번호 정책, 실패 5회 15분 잠금, IP rate limit, 일반화된 인증 실패 메시지 적용 |
| 파일 정책 | ADR-0037 기준 `jpg/jpeg/png/pdf/hwp/hwpx`, 파일 1개당 50MB 제한 적용. 바이러스 검사는 PoC 필수 차단 조건에서 제외 |
| AI Job 정책 | ADR-0035 기준 Redis Queue + PostgreSQL Job 상태 테이블 적용. ADR-0059 기준 전체 Job timeout 30분, 단계별 timeout, 최대 retry 3회, backoff 1분/3분/10분, `RETRY_PENDING`/`STALE`/`FAILED_FINAL` 상태 적용 |
| OCR 좌표 체계 | ADR-0015/ADR-0066 기준 원본 좌표와 정규화 좌표를 함께 관리하고 API는 `Coordinate` object로 반환 |
| Parser/OCR 엔진 라우팅 | ADR-0072 기준 PDF/복합 PDF는 `opendataloader-pdf`, HWP/HWPX는 `rhwp`, 이미지/스캔 PDF는 `PaddleOCR` 우선 적용. API 계약은 엔진 raw output이 아니라 `NormalizedDocument` v1 기준 |
| Parser/OCR 품질 재처리 | ADR-0073 기준 기술 retry와 품질 미달 재처리를 분리한다. 보조 엔진 시도는 raw artifact metadata에 기록하고, API의 업무 응답은 최종 채택된 `NormalizedDocument` 기준 결과만 반환 |
| RAG 검색 정책 | ADR-0043 기준 내부 후보 Top 20, 판단 입력 Top 5, 화면 표시 Top 3, 리포트 표시 1~3개 적용. 관련도 부족 시 `CHECK_REQUIRED` 또는 기준자료 부족 상태 처리. 검색 인프라 장애는 ADR-0061 기준 RAG 검토 실패 및 복구 대상으로 처리 |
| 위험도 산정 기준 | HIGH, MEDIUM, LOW, CHECK_REQUIRED 판정 기준 |
| 리포트 파일 형식 | ADR-0038 기준 `HWPX` 우선, `PDF` 지원. `DOCX/XLSX/HWP`는 초기 범위 제외 |
| 기준자료 버전관리 | ADR-0040 기준 불변 version 보존, `standardEffectiveDate` 자동 선택, review 기준 버전 스냅샷 고정 적용 |
| API 보안 | 파일 다운로드 URL 만료, ADR-0055 기준 권한별 데이터 접근 제한, 권한 거부 감사 로그 기록 |
| 오류 메시지 | ADR-0045 기준 공통 오류 코드별 사용자 메시지 매핑과 민감정보 노출 금지 기준 적용 |
| 성능 기준 | ADR-0042 기준 PoC 관찰 목표로 관리. 업로드 접수 P95 5초, 분석 요청 P95 2초, 상태 조회 P95 1초, 표준 샘플 분석 완료 P80 10분/P95 20분 관찰 |

---

# 22. 결론

본 API 명세서는 AI 기반 금융상품 광고심의 적정성 검토 에이전트 PoC의 주요 기능을 API 단위로 정의한 문서이다.

핵심 API 흐름은 다음과 같다.

1. 광고물 등록
2. AI 검토 요청
3. 검토 진행 상태 조회
4. 검토 결과 요약 및 상세 조회
5. 광고 화면 문제 영역 조회
6. 근거 검색 및 상세 조회
7. 문구 추천 및 담당자 채택 여부 저장
8. 심의 의견 초안 생성
9. 검토 리포트 생성
10. PoC 검증 데이터셋 및 성능 평가

문구 추천 판단은 ADR-0039 기준 `PENDING`, `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED` 상태와 판단 이력 누적 정책을 따른다.

본 문서를 기준으로 다음 단계에서는 DB 명세서와 테스트케이스를 작성한다.
