# 테스트케이스

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.5 |
| 기준일 | 2026-07-15 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.5 | 2026-07-15 | Notion 게시 계층을 최상단 `프로젝트 규칙`, 번호형 일반 문서 `01`~`14`, 최하단 `15. ADR` 구조로 변경한 검증 기준 추가 |
| v1.4 | 2026-07-14 | Notion CLI 런타임 설치 단계의 GitHub checkout credential 비노출 검증 추가 |
| v1.3 | 2026-07-14 | Notion 게시 CI secret 단계 제한, 일시 장애 재시도, 실패 실행 생성물 정리 및 페이지별 Mock 본문 검증 케이스 추가 |
| v1.2 | 2026-07-14 | Notion 게시 테스트를 번호형 일반 문서 15개와 하단 ADR 계층 78개 구조로 변경하고 본문 배포 안내 및 중복 목록 미생성 검증 추가 |
| v1.1 | 2026-07-14 | Git `docs/` Markdown 93개 Notion 수동 게시 테스트의 대상 선별, 원본 commit 추적, 잠금 및 내용 완전성 검증 케이스 추가 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, API/DB/Parser/OCR/RAG/평가 snapshot 테스트 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 테스트케이스 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 대상 시스템 | 멀티모달 RAG 기반 금융상품 광고심의 적정성 검토 AI 에이전트 PoC |
| 문서 버전 | v1.5 |
| 작성 목적 | API, DB, 화면, AI 분석 기능의 정상·예외·권한·이력 검증 기준 정의 |
| 기준 문서 | API 명세서 v0.2, DB 명세서 v0.1 |
| 테스트 범위 | PoC 기능 기준 |

---

# 1. 테스트 범위

## 1.1 테스트 대상

| 구분 | 테스트 대상 |
| --- | --- |
| 광고물 관리 | 광고물 목록 조회, 등록, 상세 조회, 수정, 수정본 등록 |
| AI 검토 | AI 검토 요청, 진행 상태 조회, 재분석 |
| OCR/레이아웃 | 텍스트 추출, 좌표 저장, 레이아웃 블록 생성 |
| 검토 결과 | 요약 조회, 상세 결과 조회, 위험도, 판정 결과 |
| 근거 검색 | Evidence 검색, 근거 상세 조회, 검토 항목-근거 매핑 |
| Annotation | 광고 화면 문제 영역 표시 |
| 문구 추천 | 대체 문구 조회, 채택/미채택/수정 후 사용 저장 |
| Q&A | 광고 규정 질의응답, 근거 기반 답변 |
| 심의 의견 | 심의 의견 초안 생성, 조회, 수정 |
| 리포트 | 리포트 생성, 조회, 다운로드 |
| 수정 비교 | 수정본 등록, 수정 전후 비교 |
| 기준자료 | 기준자료 등록, 수정, 비활성화, 변경 이력 |
| PoC 검증 | 검증 데이터셋 등록, 담당자 판단 등록, 성능평가 |
| 운영/권한 | 사용자, 권한, 감사 로그 |
| 비기능 | 권한, 오류 처리, 이력 저장, 감사 추적성 |

---

## 1.2 테스트 제외 범위

| 제외 항목 | 사유 |
| --- | --- |
| 최종 광고 승인 자동화 | PoC 범위 외 |
| 운영계 심의결재 시스템 연동 | 향후 본사업 범위 |
| 전체 상품군 완전 검증 | PoC는 예금성 상품 중심 |
| 실제 법률 판단의 완전 자동화 | AI는 준법심의 지원 도구 |
| 디자인 픽셀 단위 UI 검증 | 화면기획/디자인 확정 후 수행 |

---

# 2. 테스트 기준

## 2.1 테스트 우선순위

| 우선순위 | 설명 |
| --- | --- |
| P0 | 핵심 기능. 실패 시 PoC 진행 불가 |
| P1 | 주요 기능. 실패 시 업무 검증에 영향 |
| P2 | 보조 기능. 실패 시 우회 가능 |
| P3 | 편의 기능 또는 후순위 개선 대상 |

---

## 2.2 테스트 결과 상태

| 상태 | 설명 |
| --- | --- |
| Pass | 기대 결과와 일치 |
| Fail | 기대 결과와 불일치 |
| Blocked | 선행 기능 또는 환경 문제로 테스트 불가 |
| N/A | 현재 범위에서 해당 없음 |
| Retest | 결함 수정 후 재검증 필요 |

---

## 2.3 공통 테스트 데이터

| 데이터 | 예시 |
| --- | --- |
| 상품군 | SAVINGS |
| 광고유형 | MOBILE_BANNER |
| 광고명 | NH 적금 이벤트 모바일 배너 |
| 광고 파일 | banner_sample.png |
| 상품설명서 | product_description.pdf |
| 약관 | terms.pdf |
| 위험 표현 예시 | 국내 최고 수준의 혜택 |
| 대체 문구 예시 | 조건 충족 시 우대 혜택을 제공받을 수 있습니다. |
| 기준자료 예시 | 금융상품 광고심의 내부 기준 |
| 사용자 권한 | PRODUCT_DEPARTMENT_USER, COMPLIANCE_REVIEWER, STANDARD_MANAGER, SYSTEM_ADMIN |

---

## 2.4 Mock 및 Fixture 테스트 기준

AI/OCR/RAG 관련 테스트는 [ADR-0044](adr/ADR-0044-ai-mock-fixture-test-policy.md) 기준으로 Mock/Fixture 기반 자동 테스트와 실제 엔진 기반 정기/수동 평가를 분리한다.

| 테스트 구분 | 기준 |
| --- | --- |
| PR 필수 테스트 | AI/OCR/RAG/LLM 외부 호출은 Mock 또는 Fixture로 대체 |
| Mock OCR | 텍스트 블록, 좌표, confidence를 고정 fixture로 반환 |
| Mock RAG | evidenceId, evidenceChunkId, rankNo, relevanceScore, matchSource를 고정 fixture로 반환 |
| Mock LLM | resultStatus, riskLevel, reason, recommendation을 고정 fixture로 반환 |
| 통합 테스트 | PostgreSQL, Redis, Object Storage 등 내부 인프라는 실제 컨테이너 사용 가능 |
| 실제 엔진 테스트 | OCR 판독 품질, RAG 검색 품질, LLM 판단 품질은 정기/수동 평가로 검증 |
| Fixture 관리 | synthetic fixture와 고객사 승인 샘플 fixture를 분리 |

Mock 테스트는 AI 판단 품질 자체가 아니라, AI 결과 수신 이후의 저장, 상태 전이, API 응답, 화면 표시, 리포트 반영을 검증한다.

---

# 3. 공통/인증 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-COM-001 | 로그인 성공 | ACTIVE 사용자 존재 | `/auth/login` 호출 | accessToken, 사용자 ID, 부서, 권한 목록 반환 | POST `/auth/login` | P0 |
| TC-COM-002 | 로그인 사용자 정보 조회 | 유효한 Token 보유 | `/users/me` 호출 | 사용자 ID, 부서, 권한 목록 반환 | GET `/users/me` | P0 |
| TC-COM-003 | 인증 Token 없음 | Token 미전달 | 보호 API 호출 | 401 UNAUTHORIZED 반환 | 공통 | P0 |
| TC-COM-004 | 권한 없는 API 접근 | 상품부서 권한으로 관리자 API 호출 | `/admin/users` 호출 | 403 FORBIDDEN 반환 | GET `/admin/users` | P0 |
| TC-COM-005 | 만료 Token 접근 | 만료된 JWT 보유 | 보호 API 호출 | 401 UNAUTHORIZED 반환 | 공통 | P0 |
| TC-COM-006 | 비활성 사용자 접근 | INACTIVE 사용자 Token 보유 | 보호 API 호출 | 401 UNAUTHORIZED 또는 403 FORBIDDEN 반환 | 공통 | P0 |
| TC-COM-007 | 상품군 공통 코드 조회 | 공통코드 등록됨 | `/codes/product-groups` 호출 | 상품군 코드 목록 반환 | GET `/codes/{codeGroup}` | P1 |
| TC-COM-008 | 광고유형 공통 코드 조회 | 공통코드 등록됨 | `/codes/advertisement-types` 호출 | 광고유형 코드 목록 반환 | GET `/codes/{codeGroup}` | P1 |
| TC-COM-009 | 오류 응답 표준 메시지 | 오류 발생 조건 준비 | 오류 API 호출 | ADR-0045 기준 code, message, traceId 반환 및 민감정보 미노출 | 공통 | P0 |
| TC-COM-010 | Refresh token 갱신 | 유효한 refresh token cookie 보유 | `/auth/refresh` 호출 | 새 accessToken 반환, refresh token rotation | POST `/auth/refresh` | P0 |
| TC-COM-011 | 로그아웃 후 refresh 실패 | 로그아웃 수행 | `/auth/refresh` 재호출 | 401 UNAUTHORIZED 반환 | POST `/auth/logout`, POST `/auth/refresh` | P0 |
| TC-COM-012 | 권한 변경 후 기존 token 거부 | 사용자 권한 변경됨 | 기존 access token으로 보호 API 호출 | token_version 불일치로 401 UNAUTHORIZED 반환 | 공통 | P0 |
| TC-COM-013 | Refresh token 평문 저장 금지 | 로그인 성공 | DB와 로그 확인 | refresh token 원문 미저장, token_hash만 저장 | `refresh_tokens`, 로그 | P0 |
| TC-COM-014 | Refresh Origin 검증 | 미허용 Origin에서 refresh 요청 | `/auth/refresh` 호출 | 403 FORBIDDEN 반환 | POST `/auth/refresh` | P0 |
| TC-COM-015 | Logout Origin 검증 | 미허용 Origin에서 logout 요청 | `/auth/logout` 호출 | 403 FORBIDDEN 반환 | POST `/auth/logout` | P0 |
| TC-COM-016 | 비밀번호 정책 검증 | 사용자 생성 또는 비밀번호 변경 | 10자 미만 또는 email 포함 비밀번호 입력 | 400 BAD_REQUEST 반환 | 사용자 등록/수정 | P0 |
| TC-COM-017 | 로그인 실패 계정 잠금 | ACTIVE 사용자 존재 | 잘못된 비밀번호로 5회 로그인 | failed_login_count 증가, locked_until 설정 | POST `/auth/login`, `users` | P0 |
| TC-COM-018 | 잠금 중 로그인 응답 일반화 | locked_until 미래 시각 | 올바른 비밀번호로 로그인 | 계정 존재/잠금 사유 노출 없이 401 반환 | POST `/auth/login` | P0 |
| TC-COM-019 | 로그인 성공 시 실패 카운트 초기화 | failed_login_count > 0 | 올바른 비밀번호로 로그인 | failed_login_count=0, last_login_at 갱신 | POST `/auth/login`, `users` | P0 |
| TC-COM-020 | 로그인 Rate limit | 동일 IP에서 반복 로그인 | 제한 초과 호출 | 429 RATE_LIMITED 반환 및 감사 로그 기록 | POST `/auth/login` | P0 |

---

# 4. 광고물 관리 테스트케이스

## 4.1 광고물 등록

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-ADV-001 | 광고물 정상 등록 | 유효한 광고 파일 준비 | 필수값과 파일을 포함하여 광고물 등록 API 호출 | 광고물 ID 생성, 상태 `UPLOADED` 저장 | `advertisements`, `advertisement_files` | P0 |
| TC-ADV-002 | 광고명 누락 | 광고명 미입력 | 광고물 등록 API 호출 | 400 BAD_REQUEST, 필수값 오류 반환 | - | P0 |
| TC-ADV-003 | 상품군 누락 | 상품군 미입력 | 광고물 등록 API 호출 | 400 BAD_REQUEST 반환 | - | P0 |
| TC-ADV-004 | 광고유형 누락 | 광고유형 미입력 | 광고물 등록 API 호출 | 400 BAD_REQUEST 반환 | - | P0 |
| TC-ADV-005 | 광고 파일 누락 | 파일 미첨부 | 광고물 등록 API 호출 | 400 BAD_REQUEST 반환 | - | P0 |
| TC-ADV-006 | 지원하지 않는 파일 형식 | `.exe` 또는 허용되지 않은 확장자 준비 | 광고물 등록 API 호출 | `FILE_NOT_SUPPORTED` 반환 | - | P0 |
| TC-ADV-007 | 손상 파일 업로드 | 손상된 PDF 준비 | 광고물 등록 API 호출 | `FILE_READ_FAILED` 반환 | - | P1 |
| TC-ADV-008 | 파일 크기 초과 | 50MB 초과 파일 준비 | 광고물 등록 API 호출 | `FILE_SIZE_EXCEEDED` 반환 | - | P0 |
| TC-ADV-009 | HWP/HWPX 광고물 등록 | hwp 또는 hwpx 광고 파일 준비 | 광고물 등록 API 호출 | 광고물 ID 생성, 분석 가능 여부 저장 | `advertisement_files` | P0 |
| TC-ADV-010 | 상품설명서/약관 포함 등록 | 광고 파일, 상품설명서, 약관 준비 | 광고물 등록 API 호출 | 파일 3건 저장, 파일 유형 구분 | `advertisement_files` | P1 |

## 4.2 광고물 조회/수정

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-ADV-011 | 광고물 목록 조회 | 광고물 등록됨 | `/advertisements` 호출 | 목록 및 페이징 정보 반환 | GET `/advertisements` | P0 |
| TC-ADV-012 | 광고명 조건 검색 | 광고물 등록됨 | keyword 조건으로 목록 조회 | 조건에 맞는 광고물만 반환 | GET `/advertisements` | P1 |
| TC-ADV-013 | 상품군/광고유형 필터 | 복수 광고물 등록됨 | `productGroup`, `advertisementType` 조건 조회 | 조건 일치 목록 반환 | GET `/advertisements` | P1 |
| TC-ADV-014 | 광고물 상세 조회 | 광고물 ID 존재 | 상세 조회 API 호출 | 광고 기본정보, 파일 목록 반환 | GET `/advertisements/{id}` | P0 |
| TC-ADV-015 | 존재하지 않는 광고물 조회 | 잘못된 광고물 ID 사용 | 상세 조회 API 호출 | 404 NOT_FOUND 반환 | GET `/advertisements/{id}` | P1 |
| TC-ADV-016 | 광고물 기본정보 수정 | 광고물 ID 존재 | 광고명/메모 수정 API 호출 | 수정 성공, updated_at 갱신 | PATCH `/advertisements/{id}` | P1 |
| TC-ADV-017 | 수정본 등록 | 기존 광고물 존재 | 수정본 파일 업로드 | revision 생성, 상태 `REVISED` | `advertisement_revisions` | P1 |

---

# 5. AI 검토 요청/진행 상태 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-REV-001 | AI 검토 정상 요청 | 광고물 상태 `UPLOADED` | 검토 요청 API 호출 | reviewId, jobId 생성, 상태 `ANALYSIS_REQUESTED` | `reviews`, `review_jobs`, `review_steps` | P0 |
| TC-REV-002 | 검토 항목 미지정 | 광고물 등록됨 | reviewTypes 없이 검토 요청 | 기본 검토 항목 적용 또는 오류 정책에 따라 처리 | `reviews` | P1 |
| TC-REV-003 | 이미 분석 중인 광고물 재요청 | 기존 상태 `ANALYZING` | 검토 요청 API 재호출 | `REVIEW_ALREADY_RUNNING` 반환 | `reviews` | P0 |
| TC-REV-004 | 존재하지 않는 광고물 검토 요청 | 잘못된 광고물 ID | 검토 요청 API 호출 | 404 NOT_FOUND 반환 | - | P0 |
| TC-REV-005 | 검토 진행 상태 조회 | reviewId 존재 | 상태 조회 API 호출 | currentStep, progressRate, steps 반환 | `review_jobs`, `review_steps` | P0 |
| TC-REV-006 | 검토 완료 상태 조회 | 분석 완료됨 | 상태 조회 API 호출 | 상태 `REVIEW_COMPLETED`, progressRate 100 반환 | `reviews` | P0 |
| TC-REV-007 | 검토 실패 상태 조회 | 분석 실패 발생 | 상태 조회 API 호출 | 상태 `REVIEW_FAILED`, failedReason 반환 | `reviews`, `review_jobs` | P1 |
| TC-REV-008 | AI 재분석 요청 | 기존 reviewId 존재 | rerun API 호출 | newReviewId 생성, 이전 review 유지 | `reviews`, `review_jobs` | P1 |
| TC-REV-009 | 일시 오류 자동 재시도 | 외부 AI timeout fixture 준비 | AI 검토 실행 | jobStatus `RETRY_PENDING`, retryCount 증가, nextRetryAt 저장 | `review_jobs`, `review_steps` | P0 |
| TC-REV-010 | Retry backoff 적용 | retryCount 0~2 상태 준비 | retry scheduling 실행 | nextRetryAt이 1분, 3분, 10분 기준으로 계산 | `review_jobs` | P1 |
| TC-REV-011 | Retry 제외 오류 처리 | 파일 손상 또는 기준자료 미제공 fixture 준비 | AI 검토 실행 | 자동 retry 없이 failedReasonCode와 isRetryable=false 저장 | `review_jobs` | P0 |
| TC-REV-012 | Worker heartbeat 장애 복구 | RUNNING job의 heartbeat 만료 | stale detector 실행 | jobStatus `STALE` 기록 후 retry 가능 시 `RETRY_PENDING` 전환 | `review_jobs`, `audit_logs` | P1 |
| TC-REV-013 | 재시도 한도 초과 최종 실패 | retryCount가 maxRetries에 도달 | 추가 실패 발생 | jobStatus `FAILED_FINAL`, dead_lettered_at, failedReasonCode 저장 | `review_jobs`, `audit_logs` | P0 |
| TC-REV-014 | 상태 조회 retry 필드 반환 | `RETRY_PENDING` job 존재 | 상태 조회 API 호출 | retryCount, maxRetries, nextRetryAt, isRetryable, failedReasonCode 반환 | `review_jobs`, `review_steps` | P0 |

---

# 6. OCR/레이아웃 분석 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-OCR-001 | 이미지 광고 텍스트 추출 | 텍스트 포함 이미지 등록 | AI 검토 실행 | 주요 문구가 `ocr_text_blocks`에 저장 | `ocr_text_blocks` | P0 |
| TC-OCR-002 | PDF 광고 텍스트 추출 | PDF 광고 등록 | AI 검토 실행 | 페이지별 텍스트 블록 저장 | `ocr_text_blocks` | P0 |
| TC-OCR-003 | OCR 좌표 저장 | 이미지 광고 등록 | AI 검토 실행 | ADR-0066 기준 source/원본/정규화 좌표와 coordinate confidence 저장 | `ocr_text_blocks` | P0 |
| TC-OCR-004 | OCR 신뢰도 저장 | OCR 실행 | 결과 확인 | confidence_score 저장 | `ocr_text_blocks` | P1 |
| TC-OCR-005 | 저해상도 이미지 처리 | 흐릿한 이미지 등록 | AI 검토 실행 | 판독 신뢰도 낮음 또는 확인 필요 처리 | `ocr_text_blocks`, `review_items` | P1 |
| TC-OCR-006 | 텍스트 없는 이미지 처리 | 텍스트 없는 이미지 등록 | AI 검토 실행 | OCR 결과 없음, 확인 필요 또는 해당 없음 처리 | `reviews` | P2 |
| TC-OCR-007 | HWP/HWPX Text IR 생성 | HWP/HWPX 광고 파일 등록 | AI 검토 실행 | `textPath`, raw/normalized text, raw/normalized offset 저장 | `ocr_text_blocks` | P0 |
| TC-OCR-008 | Text IR parser 버전 저장 | parser 실행 | 결과 확인 | parserName, parserVersion, parserRuleVersion, irVersion 저장 | `ocr_text_blocks` | P1 |
| TC-OCR-009 | OCR 신뢰도 임계값 적용 | confidence 0.80, 0.79, 0.49 fixture 준비 | AI 검토 실행 | READABLE, LOW_CONFIDENCE, UNREADABLE 상태 분리 | `ocr_text_blocks` | P0 |
| TC-OCR-010 | OCR 판독 불가 평가 제외 후보 | 판정 대상 문구 confidence 0.49 | 평가 실행 | `OCR_UNREADABLE` 제외 후보 기록 | `review_items`, `evaluations` | P1 |
| TC-OCR-011 | NormalizedDocument v1 contract | Parser/OCR fixture 준비 | adapter contract test 실행 | `documentId`, `sourceFileId`, `parserName`, `parserVersion`, `pages`, `textBlocks`, `layoutBlocks`, `confidence`, `warnings`, `irVersion` 반환 | `ocr_text_blocks`, `layout_blocks` | P0 |
| TC-OCR-012 | raw output 직접 의존 방지 | raw artifact fixture 준비 | ReviewPipeline 실행 | ReviewPipeline은 raw output 구조가 아니라 `NormalizedDocument` 필드만 사용 | parser artifact, `review_steps` | P1 |
| TC-OCR-013 | Coordinate 정규화 값 검증 | sourceWidth/sourceHeight와 원본 좌표 fixture 준비 | adapter contract test 실행 | normalizedX/Y/Width/Height가 ADR-0015 계산식과 일치 | `ocr_text_blocks`, `layout_blocks` | P0 |
| TC-OCR-014 | raw artifact metadata 저장 | Parser/OCR raw output fixture 준비 | adapter 실행 후 저장 결과 확인 | Object Storage `parser-artifacts`에 저장되고 DB에는 `raw_artifact_id`, bucket, object_key, checksum, parser/version, retention metadata만 저장 | `parser_artifacts` | P0 |
| TC-OCR-015 | raw artifact 일반 사용자 접근 차단 | 일반 사용자 계정과 raw artifact 참조 준비 | raw artifact 조회 또는 다운로드 시도 | 일반 사용자에게 원문 JSON, presigned URL, object key 전체값이 노출되지 않음 | `parser_artifacts`, `audit_logs` | P0 |
| TC-OCR-016 | ParserRouter 파일 유형별 엔진 선택 | pdf, 복합 pdf, 스캔 pdf, hwp, hwpx, png fixture 준비 | ParserRouter 실행 | PDF/복합 PDF는 `opendataloader-pdf`, HWP/HWPX는 `rhwp`, 이미지/스캔 PDF는 `PaddleOCR` Adapter 선택 | `review_steps`, parser adapter logs | P0 |
| TC-OCR-017 | HWP/HWPX rhwp Text IR contract | HWP/HWPX fixture 준비 | `HwpHwpxParserAdapter` contract test 실행 | `rhwp` 산출물이 `NormalizedDocument` v1 `textBlocks`, `textPath`, raw/normalized offset으로 변환됨 | `ocr_text_blocks` | P0 |
| TC-OCR-018 | 복합 PDF opendataloader 우선 처리 | 표/다단 PDF fixture 준비 | `PdfParserAdapter` 실행 | `opendataloader-pdf`를 1차 엔진으로 사용하고 `layoutBlocks`, `tables`, coordinates를 반환 | `layout_blocks`, `ocr_text_blocks` | P1 |
| TC-OCR-019 | 엔진 교체 시 업무 로직 비의존 | 동일 문서의 대체 엔진 NormalizedDocument fixture 준비 | ReviewPipeline 실행 | 엔진 raw output 변경 없이 `NormalizedDocument` fixture만으로 후속 검토가 동작 | `review_steps`, `review_items` | P1 |
| TC-OCR-020 | Parser/OCR 기술 실패 retry | Parser/OCR timeout fixture 준비 | AI 검토 실행 | ADR-0059 기준 retry되고 품질 재처리로 오분류되지 않음 | `review_steps`, `review_jobs` | P0 |
| TC-OCR-021 | 품질 미달 보조 엔진 재처리 | 구조 confidence `< 0.50` PDF fixture 준비 | Parser/OCR 실행 | ADR-0073 기준 보조 엔진 재처리 시도와 rerunReasonCode 기록 | `parser_artifacts`, `review_steps` | P1 |
| TC-OCR-022 | 최종 채택 산출물만 후속 전달 | 1차/보조 엔진 NormalizedDocument fixture 준비 | ReviewPipeline 실행 | `isSelectedOutput=true` 산출물만 `ocr_text_blocks`, `layout_blocks`, 후속 검토에 반영 | `parser_artifacts`, `ocr_text_blocks`, `layout_blocks` | P0 |
| TC-OCR-023 | OCR 판독 불가 자동 retry 제외 | 판정 대상 문구 confidence `< 0.50` fixture 준비 | AI 검토 실행 | 자동 retry 없이 `OCR_UNREADABLE` 확인 필요/평가 제외 후보 기록 | `review_items`, `evaluations` | P1 |
| TC-OCR-024 | VLM OCR 보조 재처리 제한 | 외부 AI 입력 불가 파일과 이미지 OCR 누락 fixture 준비 | 보조 재처리 판단 | VLM OCR을 실행하지 않고 확인 필요로 처리 | `review_steps`, `audit_logs` | P1 |
| TC-LAY-001 | 제목/본문/유의사항 영역 분리 | 레이아웃 있는 광고 등록 | AI 검토 실행 | `layout_blocks`에 TITLE, BODY, NOTICE 저장 | `layout_blocks` | P1 |
| TC-LAY-002 | 버튼/배너 영역 인식 | 모바일 배너 등록 | AI 검토 실행 | BUTTON, BANNER 영역 저장 | `layout_blocks` | P2 |
| TC-LAY-003 | 레이아웃 신뢰도 저장 | 레이아웃 분석 실행 | 결과 확인 | confidence_score 저장 | `layout_blocks` | P2 |
| TC-LAY-004 | 구조 인식 신뢰도 임계값 적용 | structure confidence 0.75, 0.74, 0.49 fixture 준비 | 레이아웃 분석 실행 | STRUCTURED, PARTIALLY_STRUCTURED, UNSTRUCTURED 상태 분리 | `layout_blocks` | P1 |

---

# 7. 검토 결과 테스트케이스

## 7.1 검토 결과 요약

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-RES-001 | 검토 결과 요약 조회 | 검토 완료 | `/reviews/{id}/summary` 호출 | 종합 위험도, 문제 건수, 주요 리스크 반환 | GET `/reviews/{id}/summary` | P0 |
| TC-RES-002 | 문제 없는 광고물 요약 | 적정 광고물 분석 완료 | 요약 조회 | overallRiskLevel LOW 또는 적정 상태 반환 | GET `/reviews/{id}/summary` | P1 |
| TC-RES-003 | 위험도 높은 광고물 요약 | 위험 표현 포함 광고 분석 완료 | 요약 조회 | topRisks에 위험 항목 포함 | GET `/reviews/{id}/summary` | P0 |
| TC-RES-004 | 존재하지 않는 reviewId | 잘못된 reviewId | 요약 조회 | 404 NOT_FOUND 반환 | GET `/reviews/{id}/summary` | P1 |
| TC-RES-005 | 검토 기준자료 버전 스냅샷 조회 | 검토 완료 | 요약 조회 | standardEffectiveDate와 standardVersionIds 반환 | GET `/reviews/{id}/summary` | P1 |

## 7.2 상세 검토 결과

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-ITEM-001 | 상세 검토 결과 목록 조회 | 검토 완료 | `/reviews/{id}/items` 호출 | review_items 목록 반환 | `review_items` | P0 |
| TC-ITEM-002 | 검토유형 필터 | 여러 검토유형 존재 | `reviewType=REQUIRED_PHRASE` 조회 | 필수 문구 검토 항목만 반환 | `review_items` | P1 |
| TC-ITEM-003 | 위험도 필터 | 위험도별 결과 존재 | `riskLevel=HIGH` 조회 | HIGH 항목만 반환 | `review_items` | P1 |
| TC-ITEM-004 | 판정 결과 필터 | 판정 결과 존재 | `resultStatus=NEEDS_REVISION` 조회 | 수정 필요 항목만 반환 | `review_items` | P1 |
| TC-ITEM-005 | 상세 검토 결과 단건 조회 | reviewItemId 존재 | 단건 조회 API 호출 | 판단 사유, 근거, 추천 문구, 좌표 반환 | `review_items` | P0 |
| TC-ITEM-006 | 근거 없는 검토 항목 | 기준자료 부족 상황 | 상세 조회 | 기준자료 확인 필요 표시 | `review_items` | P1 |
| TC-ITEM-007 | 위험도 산정 근거 응답 | 위험 표현 분석 완료 | 상세 조회 API 호출 | `riskPolicyVersion`, `riskReasonCodes`, `riskRationale.scoreDetail` 반환 | `review_items` | P0 |
| TC-ITEM-008 | 위험도 사유 코드 저장 | Rule/RAG/LLM fixture 준비 | AI 검토 실행 | `risk_reason_codes`와 `risk_score_detail.final.decisionRule` 저장 | `review_items` | P0 |

---

# 8. 필수 문구/금리/위험 표현 검토 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 검증 기준 | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-RULE-001 | 필수 문구 포함 광고 검토 | 필수 문구 포함 광고 준비 | AI 검토 실행 | 해당 항목 `APPROPRIATE` | review_items | P0 |
| TC-RULE-002 | 필수 문구 누락 검토 | 세전/연 기준 누락 광고 준비 | AI 검토 실행 | `NEEDS_REVISION` 또는 `NEEDS_CONFIRMATION` | review_items | P0 |
| TC-RULE-003 | 심의필 번호 누락 검토 | 심의필 번호 없는 광고 준비 | AI 검토 실행 | 심의필 누락 항목 생성 | review_items | P1 |
| TC-RULE-004 | 금리 수치 일치 검토 | 상품설명서와 광고 금리 일치 | AI 검토 실행 | 금리 항목 `APPROPRIATE` | review_items | P0 |
| TC-RULE-005 | 금리 수치 불일치 검토 | 상품설명서 금리와 광고 금리 불일치 | AI 검토 실행 | 불일치 의심 항목 생성 | review_items | P0 |
| TC-RULE-006 | 우대조건 누락 검토 | 우대금리 조건 생략 광고 준비 | AI 검토 실행 | 조건 누락 위험 항목 생성 | review_items | P0 |
| TC-RAG-001 | 과장 표현 탐지 | “국내 최고 수준의 혜택” 포함 | AI 검토 실행 | 위험 표현 항목 생성, 위험도 HIGH | review_items | P0 |
| TC-RAG-002 | 확정 표현 탐지 | “확정 수익”, “무조건” 포함 | AI 검토 실행 | 위험 표현 항목 생성 | review_items | P0 |
| TC-RAG-003 | 문맥상 확인 필요 처리 | 판단 근거 부족 표현 포함 | AI 검토 실행 | `NEEDS_CONFIRMATION` 처리 | review_items | P1 |
| TC-RAG-004 | 상품설명서 정합성 검토 | 상품설명서 첨부 | AI 검토 실행 | 광고 문구와 기준 문서 비교 결과 생성 | review_items | P1 |
| TC-RAG-005 | 상품설명서 미첨부 정합성 검토 | 상품설명서 없음 | AI 검토 실행 | `PRODUCT_INFO_MISSING` 또는 확인 필요 처리 | review_items | P1 |

---

# 9. 근거 검색/근거 매핑 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/검색 | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-EVD-001 | 근거 검색 정상 | 기준자료 등록됨 | `/evidences/search` 호출 | 관련 근거 목록 반환 | `evidences`, `evidence_chunks` | P0 |
| TC-EVD-002 | 키워드 검색 | OpenSearch 인덱스 존재 | keyword 검색 | 정확한 키워드 포함 근거 반환 | OpenSearch | P1 |
| TC-EVD-003 | 벡터 검색 | Qdrant point 존재 | searchMode=VECTOR 검색 | 의미상 유사 근거 반환 | Qdrant | P1 |
| TC-EVD-004 | Hybrid 검색 | Qdrant/OpenSearch 준비 | searchMode=HYBRID 검색 | 관련도 높은 근거 반환 | Qdrant, OpenSearch | P1 |
| TC-EVD-005 | 근거 상세 조회 | evidenceId 존재 | 상세 조회 API 호출 | 기준명, 조항번호, 내용 반환 | `evidences` | P0 |
| TC-EVD-006 | 존재하지 않는 근거 조회 | 잘못된 evidenceId | 상세 조회 API 호출 | 404 NOT_FOUND 반환 | - | P1 |
| TC-EVD-007 | 검토 항목-근거 매핑 저장 | AI 검토 완료 | DB 매핑 확인 | `review_item_evidences`에 근거 연결 | `review_item_evidences` | P0 |
| TC-EVD-008 | 근거 관련도 점수 저장 | 근거 검색 완료 | DB 확인 | relevance_score, rank_no 저장 | `review_item_evidences` | P1 |
| TC-EVD-009 | RAG 근거 표시 개수 제한 | 관련 근거 4개 이상 존재 | 상세 검토 결과 조회 | 검토 항목별 화면 표시 근거는 ADR-0043 기준 최대 3개 반환 | `review_item_evidences` | P1 |
| TC-EVD-010 | 근거 부족 처리 | 관련도 높은 기준자료 없음 | AI 검토 실행 | `CHECK_REQUIRED` 또는 기준자료 부족 상태로 처리 | `review_items`, `review_item_evidences` | P1 |
| TC-EVD-011 | 근거 재현성 저장 | Hybrid Search 결과 존재 | AI 검토 실행 후 DB 확인 | evidenceId, evidenceChunkId, standardVersionId, rankNo, relevanceScore, matchSource 저장 | `review_item_evidences` | P1 |
| TC-EVD-012 | Qdrant 장애 시 RAG 검토 실패 | Qdrant 연결 실패, OpenSearch 정상 | AI 검토 실행 | keyword-only fallback 없이 `RAG_SEARCH_UNAVAILABLE`, retry 대상 처리 | `review_jobs`, `review_steps` | P0 |
| TC-EVD-013 | OpenSearch 장애 시 RAG 검토 실패 | OpenSearch 연결 실패, Qdrant 정상 | AI 검토 실행 | vector-only fallback 없이 `RAG_SEARCH_UNAVAILABLE`, retry 대상 처리 | `review_jobs`, `review_steps` | P0 |
| TC-EVD-014 | 검색 인프라 장애와 근거 부족 구분 | 검색 장애 fixture와 검색 정상/근거 없음 fixture 준비 | AI 검토 실행 | 장애는 `RAG_SEARCH_FAILED` 또는 `RAG_SEARCH_UNAVAILABLE`, 근거 없음은 `CHECK_REQUIRED`로 분리 | `review_jobs`, `review_items` | P0 |

---

# 10. Annotation/화면 표시 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-ANN-001 | Annotation 목록 조회 | 검토 결과에 표시 위치 존재 | `/reviews/{id}/annotations` 호출 | 표시 모드, 위치 상태, 좌표/텍스트 위치가 함께 반환 | `annotations` | P0 |
| TC-ANN-002 | 페이지별 Annotation 조회 | 다중 페이지 광고 | pageNo 조건 조회 | 해당 페이지 Annotation만 반환 | `annotations` | P1 |
| TC-ANN-003 | 검토유형별 Annotation 필터 | 다양한 검토유형 존재 | reviewType 조건 조회 | 해당 유형 영역만 반환 | `annotations` | P1 |
| TC-ANN-004 | 위험도별 Annotation 필터 | 위험도별 영역 존재 | riskLevel 조건 조회 | 해당 위험도 영역만 반환 | `annotations` | P1 |
| TC-ANN-005 | Annotation 단건 상세 연결 | reviewItemId 존재 | Annotation 또는 목록 항목 클릭 후 상세 조회 | 검토 항목 상세 결과 반환 | `review_items` | P0 |
| TC-ANN-006 | 좌표 없는 검토 항목 처리 | OCR 좌표 없음 | Annotation 조회 | `LIST_ONLY` 또는 `UNAVAILABLE` 상태로 목록과 상세 패널에 표시 | `review_items`, `annotations` | P1 |
| TC-ANN-007 | HWP/HWPX 텍스트 하이라이트 | HWP/HWPX 문서에서 문구 위치 특정 | Annotation 조회 | `TEXT_HIGHLIGHT`, textBlockId, normalized offset, matchedText 반환 | `annotations` | P1 |
| TC-ANN-008 | 일부 위치 특정 처리 | 일부 문구만 매칭 | Annotation 조회 | `PARTIALLY_LOCATED` 상태와 특정된 문구만 반환 | `annotations` | P1 |
| TC-ANN-009 | 문서 단위 이슈 표시 | 위치 없는 문서 전체 이슈 존재 | Annotation 조회 | `DOCUMENT_LEVEL_ISSUE` 상태로 목록/상세 표시 | `review_items`, `annotations` | P1 |
| TC-ANN-010 | Annotation 위치 신뢰도 임계값 적용 | location confidence 0.80, 0.79, 0.49 fixture 준비 | Annotation 조회 | LOCATED, LOW_CONFIDENCE/PARTIALLY_LOCATED, NOT_LOCATED 상태 분리 | `annotations` | P1 |
| TC-ANN-011 | Annotation Coordinate object 응답 | BOX Annotation 존재 | `/reviews/{id}/annotations` 호출 | `coordinate` object에 source/원본/정규화 좌표, rotation, coordinateConfidence 반환 | `/reviews/{id}/annotations` | P0 |
| TC-FILE-001 | 파일 미리보기 조회 | fileId 존재 | `/files/{id}/preview` 호출 | previewUrl, width, height 반환 | `advertisement_files` | P0 |
| TC-FILE-002 | 존재하지 않는 파일 미리보기 | 잘못된 fileId | preview API 호출 | 404 NOT_FOUND 반환 | - | P1 |

---

# 11. 문구 추천 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-SUG-001 | 문구 추천 목록 조회 | 위험 표현 검토 완료 | `/reviews/{id}/suggestions` 호출 | 원문, 추천문구, 추천사유 반환 | `suggestions` | P0 |
| TC-SUG-002 | 위험 표현에 추천 문구 생성 | “국내 최고 수준” 포함 광고 분석 | 추천 목록 조회 | 완화 표현 추천 생성 | `suggestions` | P0 |
| TC-SUG-003 | 추천 문구 채택 저장 | suggestionId 존재 | decisionStatus=ACCEPTED 저장 | 채택 상태 저장 | `suggestion_decisions` | P0 |
| TC-SUG-004 | 추천 문구 미채택 저장 | suggestionId 존재 | decisionStatus=REJECTED 저장 | 미채택 상태 저장 | `suggestion_decisions` | P1 |
| TC-SUG-005 | 수정 후 사용 저장 | 담당자 수정 문구 입력 | decisionStatus=MODIFIED_AND_USED 저장 | finalText 저장 | `suggestion_decisions` | P0 |
| TC-SUG-006 | 존재하지 않는 suggestionId 저장 | 잘못된 ID 사용 | 판단 저장 API 호출 | 404 NOT_FOUND 반환 | - | P1 |
| TC-SUG-007 | 권한 없는 사용자 저장 | 조회 권한만 있는 사용자 | 판단 저장 API 호출 | 403 FORBIDDEN 반환 | - | P1 |
| TC-SUG-008 | 수정 후 사용 finalText 누락 | suggestionId 존재 | decisionStatus=MODIFIED_AND_USED, finalText 없이 호출 | 400 BAD_REQUEST 반환 | - | P1 |

---

# 12. 광고 규정 Q&A 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-QA-001 | 광고 규정 질문 정상 | 기준자료 등록됨 | Q&A 요청 API 호출 | 답변 요약, 상세 설명, 근거 반환 | `qa_sessions`, `qa_messages` | P1 |
| TC-QA-002 | 상품군 포함 질문 | productGroup 전달 | Q&A 요청 | 상품군 기준으로 근거 검색 | `qa_messages`, `qa_message_evidences` | P1 |
| TC-QA-003 | 근거 부족 질문 | 관련 기준자료 없음 | Q&A 요청 | 단정 답변 없이 확인 필요 표시 | `qa_messages` | P1 |
| TC-QA-004 | Q&A 근거 매핑 저장 | Q&A 답변 생성 | DB 확인 | `qa_message_evidences` 저장 | `qa_message_evidences` | P1 |
| TC-QA-005 | Q&A 이력 조회 | 질문 이력 존재 | `/qa/questions` 호출 | 질문/답변 이력 반환 | `qa_messages` | P2 |
| TC-QA-006 | 빈 질문 요청 | question 공백 | Q&A 요청 | 400 BAD_REQUEST 반환 | - | P1 |

---

# 13. 심의 의견 초안 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-OPN-001 | 심의 의견 초안 생성 | 검토 결과 존재 | 초안 생성 API 호출 | draftId, draftContent 반환 | `opinion_drafts` | P1 |
| TC-OPN-002 | 선택 항목 기반 초안 생성 | reviewItemId 목록 존재 | 일부 항목 선택 후 초안 생성 | 선택 항목만 포함된 초안 생성 | `opinion_drafts` | P1 |
| TC-OPN-003 | 초안 조회 | 초안 생성됨 | 초안 목록 조회 | 생성된 초안 목록 반환 | `opinion_drafts` | P2 |
| TC-OPN-004 | 담당자 수정본 저장 | draftId 존재 | finalContent 저장 | final_content 저장, updated_at 갱신 | `opinion_drafts` | P1 |
| TC-OPN-005 | 준법감시 권한 없는 사용자 생성 | 상품부서 사용자 | 초안 생성 API 호출 | 403 FORBIDDEN 반환 | - | P1 |
| TC-OPN-006 | 검토 결과 없는 초안 생성 | reviewItem 없음 | 초안 생성 API 호출 | 400 또는 404 반환 | - | P2 |

---

# 14. 리포트 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-RPT-001 | HWPX 리포트 정상 생성 | 검토 완료 | format 미지정 또는 HWPX로 리포트 생성 API 호출 | reportId 생성, 상태 CREATED, HWPX 파일 생성 | `reports` | P0 |
| TC-RPT-002 | Annotation 포함 리포트 생성 | Annotation 존재 | includeAnnotations=true 생성 | 리포트에 화면 표시 정보 포함 | `reports`, `annotations` | P1 |
| TC-RPT-003 | 문구 추천 포함 리포트 생성 | suggestion 존재 | includeSuggestions=true 생성 | 추천 문구 포함 | `reports`, `suggestions` | P1 |
| TC-RPT-004 | 근거 상세 포함 리포트 생성 | evidence 매핑 존재 | includeEvidenceDetails=true 생성 | 근거 상세 포함 | `review_item_evidences` | P1 |
| TC-RPT-005 | 리포트 상세 조회 | reportId 존재 | `/reports/{id}` 호출 | 리포트 메타, downloadUrl 반환 | `reports` | P0 |
| TC-RPT-006 | HWPX 리포트 다운로드 | HWPX reportId 존재 | download API 호출 | HWPX 파일 다운로드 성공 | `reports`, `advertisement_files` | P0 |
| TC-RPT-007 | 검토 미완료 상태에서 리포트 생성 | reviewStatus ANALYZING | 리포트 생성 API 호출 | 409 CONFLICT 또는 생성 제한 | `reviews` | P1 |
| TC-RPT-008 | 존재하지 않는 리포트 다운로드 | 잘못된 reportId | 다운로드 API 호출 | 404 NOT_FOUND 반환 | - | P1 |
| TC-RPT-009 | PDF 리포트 생성 및 다운로드 | 검토 완료 | format=PDF로 리포트 생성 후 다운로드 | PDF 파일 다운로드 성공 | `reports`, `advertisement_files` | P0 |
| TC-RPT-010 | 미지원 리포트 형식 요청 | 검토 완료 | format=DOCX 또는 XLSX로 리포트 생성 API 호출 | `UNSUPPORTED_REPORT_FORMAT` 반환 | `reports` | P1 |
| TC-RPT-011 | 리포트 스냅샷 저장 | 검토 완료 | 리포트 생성 API 호출 | report_payload, snapshot_hash, snapshot_version 저장 | `reports` | P0 |
| TC-RPT-012 | PDF 변환본 snapshot 정합성 | HWPX 리포트 생성 가능 | format=PDF 생성 | PDF report가 HWPX sourceReportId와 동일 snapshot_hash 참조 | `reports` | P0 |
| TC-RPT-013 | PDF 변환 실패 분리 기록 | converter 실패 fixture | format=PDF 생성 | HWPX report는 CREATED, PDF report는 FAILED와 failureReason 저장 | `reports` | P1 |

---

# 15. 수정 전후 비교 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-CMP-001 | 수정본 정상 등록 | 원본 광고물 존재 | 수정본 업로드 API 호출 | revisionId 생성 | `advertisement_revisions` | P1 |
| TC-CMP-002 | 수정 전후 비교 실행 | 원본 review, revision 존재 | 비교 요청 API 호출 | comparisonId 생성, 비교 결과 요약 반환 | `comparisons` | P1 |
| TC-CMP-003 | 해결된 지적사항 판정 | 수정본에서 문제 문구 개선 | 비교 실행 | resolutionStatus RESOLVED | `comparison_items` | P1 |
| TC-CMP-004 | 미해결 지적사항 판정 | 수정본에도 문제 문구 존재 | 비교 실행 | resolutionStatus UNRESOLVED | `comparison_items` | P1 |
| TC-CMP-005 | 신규 리스크 판정 | 수정본에 새로운 위험 표현 추가 | 비교 실행 | NEW_ISSUE 생성 | `comparison_items` | P2 |
| TC-CMP-006 | 비교 결과 조회 | comparisonId 존재 | 비교 결과 조회 API 호출 | summary 및 items 반환 | `comparisons`, `comparison_items` | P1 |
| TC-CMP-007 | 잘못된 revisionId 비교 | 잘못된 ID 사용 | 비교 요청 API 호출 | 404 NOT_FOUND 반환 | - | P1 |

---

# 16. 기준자료 관리 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-STD-001 | 기준자료 정상 등록 | 기준 관리자 권한 | 기준자료 등록 API 호출 | standardId, evidenceId 생성 | `standards`, `standard_versions`, `evidences` | P0 |
| TC-STD-002 | 기준자료 필수값 누락 | title 또는 content 누락 | 기준자료 등록 API 호출 | 400 BAD_REQUEST 반환 | - | P0 |
| TC-STD-003 | 기준자료 목록 조회 | 기준자료 등록됨 | `/standards` 호출 | 기준자료 목록 반환 | `standards` | P1 |
| TC-STD-004 | 기준자료 조건 검색 | 기준자료 다수 등록 | evidenceType, productGroup 조건 조회 | 조건 일치 목록 반환 | `standards` | P1 |
| TC-STD-005 | 기준자료 상세 조회 | evidenceId 존재 | `/evidences/{id}` 호출 | 근거 상세 반환 | `evidences` | P0 |
| TC-STD-006 | 기준자료 수정 | standardId 존재 | 수정 API 호출 | 기존 version 보존, 새 standardVersionId 생성 | `standard_versions` | P1 |
| TC-STD-007 | 기준자료 비활성화 | standardId 존재 | 비활성화 API 호출 | is_active=false | `standards` | P1 |
| TC-STD-008 | 기준자료 변경 이력 조회 | 수정 이력 존재 | histories API 호출 | 변경 이력 목록 반환 | `standard_versions` | P1 |
| TC-STD-009 | 권한 없는 기준자료 등록 | 상품부서 사용자 | 기준자료 등록 API 호출 | 403 FORBIDDEN 반환 | - | P0 |
| TC-STD-010 | 기준자료 Chunk 생성 | 기준자료 등록 완료 | RAG 인덱싱 수행 | evidence_chunks 생성, Qdrant/OpenSearch ID 저장 | `evidence_chunks` | P1 |
| TC-STD-011 | 기준자료 재색인 요청 | 기준 관리자 권한과 standardVersionId 존재 | 재색인 API 호출 | `standard_reindex_jobs`에 QUEUED Job 생성 | `standard_reindex_jobs` | P0 |
| TC-STD-012 | 재색인 상태 조회 | 재색인 Job 존재 | 상태 조회 API 호출 | jobStatus, reindexScope, indexedChunkCount, 실패 사유 반환 | `standard_reindex_jobs` | P0 |
| TC-STD-013 | 임베딩 모델 변경 재색인 | 기존 Chunk와 새 embeddingModel 지정 | `VECTOR_ONLY` 또는 `INDEX_ONLY` 재색인 실행 | Chunk는 유지되고 Qdrant point와 embeddingModel metadata 갱신 | `evidence_chunks`, `standard_reindex_jobs` | P1 |
| TC-STD-014 | 관리자 Chunk 조회 | 기준 관리자 권한과 evidenceId 존재 | Chunk 목록/상세 조회 API 호출 | chunkText, sectionPath, parserRuleVersion, qdrantPointId 반환 | `evidence_chunks` | P1 |
| TC-STD-015 | 일반 사용자 Chunk 조회 차단 | 상품부서 사용자 | Chunk 조회 API 호출 | 403 FORBIDDEN 반환 | `audit_logs` | P0 |
| TC-STD-016 | 재색인 중복 실행 idempotency | 동일 standardVersionId와 동일 embeddingModel 준비 | 같은 재색인 Job 또는 요청을 2회 실행 | 동일 deterministic ID에 upsert되고 중복 Qdrant point/OpenSearch doc가 생성되지 않음 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-017 | 부분 실패 상태 기록 | Qdrant 성공, OpenSearch 실패 fixture 준비 | 재색인 실행 | Qdrant status ACTIVE, OpenSearch status FAILED, Job 실패 사유 기록 | `evidence_chunks`, `standard_reindex_jobs` | P0 |
| TC-STD-018 | 기준자료 비활성화 검색 제외 | 활성 기준자료 색인 완료 | 비활성화 후 검색 실행 | 관련 chunk index status EXCLUDED 또는 검색 filter로 제외 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-019 | stale index cleanup | EXCLUDED 상태 chunk 존재 | cleanup Job 실행 | Qdrant/OpenSearch 물리 삭제 후 status DELETED 기록 | `evidence_chunks` | P2 |
| TC-STD-020 | 검색 인덱스 표준 필드 색인 | 기준자료 Chunk 생성 완료 | Qdrant payload와 OpenSearch document 확인 | ADR-0071 표준 metadata와 searchSchemaVersion 저장 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-021 | OpenSearch synonym 검색 | synonymVersion이 적용된 기준자료 색인 | 동의어 표현으로 기준자료 검색 | 동의어가 적용되어 관련 chunk가 검색됨 | OpenSearch | P1 |
| TC-STD-022 | OpenSearch highlight 반환 | chunkText/title match가 있는 검색어 준비 | Chunk 상세 또는 검색 결과 조회 | `chunkText`, `title` highlight 또는 snippet 반환 | OpenSearch, API | P1 |
| TC-STD-023 | analyzer/synonym 변경 재색인 | opensearchAnalyzerVersion 또는 synonymVersion 변경 | `KEYWORD_ONLY` 또는 `INDEX_ONLY` 재색인 실행 | OpenSearch document version 갱신, 검색 결과 정상 반환 | `standard_reindex_jobs`, OpenSearch | P1 |

---

# 17. PoC 검증/성능평가 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-VAL-001 | 검증 데이터셋 등록 | 검증 샘플 파일 준비 | 데이터셋 등록 API 호출 | datasetId 생성 | `validation_datasets` | P0 |
| TC-VAL-002 | 검증 데이터셋 목록 조회 | 데이터셋 존재 | `/validation/datasets` 호출 | 데이터셋 목록 반환 | `validation_datasets` | P1 |
| TC-VAL-003 | 담당자 판단 결과 등록 | datasetId 존재 | judgments 등록 API 호출 | judgment 저장 | `validation_judgments` | P0 |
| TC-VAL-004 | 평가 제외 처리 | datasetId 존재 | excluded=true, excludeReasonCode 저장 | is_excluded=true, exclude_reason_code 저장 | `validation_datasets` | P1 |
| TC-VAL-005 | 정답지 수정 version 증가 | datasetId와 judgmentId 존재 | labelJson 또는 judgment 수정 | datasetVersion 또는 judgmentVersion 증가 | `validation_datasets`, `validation_judgments` | P1 |
| TC-EVAL-001 | 성능평가 정상 실행 | 데이터셋, 판단 결과, AI 결과 존재 | 평가 실행 API 호출 | evaluationId 생성, KPI별 score/numerator/denominator 반환 | `evaluations`, `evaluation_metrics` | P0 |
| TC-EVAL-002 | 필수 문구 정확도 산출 | 필수 문구 정답 데이터 존재 | 평가 실행 | REQUIRED_PHRASE_ACCURACY의 분자/분모/점수 산출 | `evaluation_metrics` | P0 |
| TC-EVAL-003 | 위험 표현 정확도 산출 | 위험 표현 정답 데이터 존재 | 평가 실행 | MISLEADING_EXPRESSION_ACCURACY의 분자/분모/점수 산출 | `evaluation_metrics` | P0 |
| TC-EVAL-004 | 근거 매칭 적정성 산출 | 근거 정답/평가 데이터 존재 | 평가 실행 | EVIDENCE_PRECISION의 분자/분모/점수 산출 | `evaluation_metrics` | P1 |
| TC-EVAL-005 | 담당자 판단 일치율 산출 | 담당자 판단 데이터 존재 | 평가 실행 | HUMAN_AGREEMENT_RATE의 분자/분모/점수 산출 | `evaluation_metrics` | P1 |
| TC-EVAL-006 | 평가 대상 없음 | datasetIds 비어 있음 | 평가 실행 API 호출 | 400 BAD_REQUEST 반환 | - | P1 |
| TC-EVAL-007 | 평가 제외 샘플 제외 | 제외 샘플 존재 | excludeInvalidSamples=true 평가 | 제외 샘플은 분모에서 제외되고 excludedCount 증가 | `evaluations`, `evaluation_metrics` | P1 |
| TC-EVAL-008 | 부분 정답 점수 반영 | 부분 정답 항목 존재 | 평가 실행 | match score 0.5가 numerator와 partialCount에 반영 | `evaluation_metrics` | P1 |
| TC-EVAL-009 | KPI 미적용 처리 | 특정 KPI 분모가 0 | 평가 실행 | notApplicable=true, 목표 달성 계산 제외 | `evaluation_metrics` | P1 |
| TC-EVAL-010 | 제외 사유별 집계 | OCR 판독 불가, 상품조건 불명확 제외 샘플 존재 | 평가 실행 | exclusionSummary와 exclusion_summary_json에 사유별 건수 반영 | `evaluations`, `evaluation_metrics` | P1 |
| TC-EVAL-011 | AI 오답 제외 금지 | AI가 위험 표현을 놓친 샘플 존재 | 평가 실행 | 평가 제외가 아니라 오답으로 numerator에 0 반영 | `evaluation_metrics` | P0 |
| TC-EVAL-012 | 평가 실행 Snapshot 생성 | 데이터셋, 판단 결과, AI 결과 존재 | 평가 실행 | dataset/judgment/exclusion/AI/version/policy snapshot과 snapshotHash 저장 | `evaluations` | P0 |
| TC-EVAL-013 | 정답지 수정 후 기존 평가 불변 | 평가 완료 후 정답지 수정 | 기존 evaluation 조회 | 기존 평가는 수정 전 snapshot 기준 score와 hash 유지 | `evaluations`, `evaluation_metrics` | P0 |
| TC-EVAL-014 | 정답지 수정 후 신규 평가 생성 | 정답지 version 증가 상태 | 새 평가 실행 | 신규 evaluationId와 신규 snapshotHash 생성, 변경된 정답지 기준 KPI 산출 | `evaluations`, `evaluation_metrics` | P1 |
| TC-EVAL-015 | AI 재분석 결과 평가 분리 | 기존 review 평가 후 새 review 생성 | 새 평가 실행 | reviewSelectionPolicy에 따라 선택된 reviewId가 AI result snapshot에 기록 | `evaluations` | P1 |

---

# 18. 사용자/권한/감사 로그 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-ADM-001 | 사용자 목록 조회 | 시스템 관리자 권한 | `/admin/users` 호출 | 사용자 목록 반환 | `users` | P1 |
| TC-ADM-002 | 사용자 등록 | 시스템 관리자 권한 | 사용자 등록 API 호출 | user_id 생성 | `users`, `user_roles` | P1 |
| TC-ADM-003 | 사용자 권한 변경 | 사용자 존재 | roles 변경 API 호출 | 권한 매핑 갱신, refresh token revoke, auth_token_version 증가 | `users`, `user_roles`, `refresh_tokens` | P1 |
| TC-ADM-004 | 사용자 비활성화 | 사용자 존재 | 비활성화 API 호출 | user_status INACTIVE, refresh token 전체 revoke | `users`, `refresh_tokens` | P1 |
| TC-AUD-001 | 광고물 등록 감사 로그 | 광고물 등록 수행 | audit_logs 확인 | action_type 기록 | `audit_logs` | P1 |
| TC-AUD-002 | AI 검토 요청 감사 로그 | 검토 요청 수행 | audit_logs 확인 | 분석 요청 로그 저장 | `audit_logs` | P1 |
| TC-AUD-003 | 기준자료 수정 감사 로그 | 기준자료 수정 수행 | audit_logs 확인 | before_json, after_json 저장 | `audit_logs` | P1 |
| TC-AUD-004 | 리포트 다운로드 감사 로그 | 리포트 다운로드 수행 | audit_logs 확인 | 다운로드 로그 저장 | `audit_logs` | P2 |
| TC-AUD-005 | 감사 로그 조건 조회 | 로그 존재 | `/admin/audit-logs` 조건 조회 | 조건 일치 로그 반환 | `audit_logs` | P1 |
| TC-AUD-006 | 권한 거부 감사 로그 | 권한 없는 다운로드 시도 | audit_logs 확인 | result=DENIED, reason_code 기록 | `audit_logs` | P1 |
| TC-AUD-007 | 세션 토큰 감사 로그 | 로그인, refresh, 로그아웃 수행 | audit_logs 확인 | token 원문 없이 action_type과 결과 기록 | `audit_logs`, `refresh_tokens` | P1 |
| TC-AUD-008 | 로그인 실패/잠금 감사 로그 | 로그인 실패와 잠금 발생 | audit_logs 확인 | reason_code에 실패/잠금/rate limit 사유 기록, 비밀번호 원문 미저장 | `audit_logs`, `users` | P1 |
| TC-AUD-009 | AI Job retry/최종 실패 감사 로그 | retry 및 최종 실패 발생 | audit_logs 확인 | job 재시도, stale 복구, dead-letter 전환 로그 저장 | `audit_logs`, `review_jobs` | P1 |

---

# 19. 비기능 테스트케이스

## 19.1 권한/보안

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-SEC-001 | 상품부서 사용자의 타 부서 광고물 목록 필터링 | 광고물 목록 조회 | 타 부서 광고물은 목록에서 제외 | P0 |
| TC-NFR-SEC-002 | 기준 관리자 외 기준자료 수정 제한 | 상품부서 권한으로 기준자료 수정 | 403 FORBIDDEN | P0 |
| TC-NFR-SEC-003 | 파일 다운로드 권한 검증 | 권한 없는 파일 다운로드 시도 | 403 FORBIDDEN | P0 |
| TC-NFR-SEC-004 | 민감정보 로그 저장 방지 | API 호출 후 로그 확인 | Token, 파일 원문 등 민감정보 미저장 | P0 |
| TC-NFR-SEC-005 | 상품부서 사용자의 타 부서 광고물 단건 접근 제한 | 타 부서 광고물 상세 조회 | 403 FORBIDDEN | P0 |
| TC-NFR-SEC-006 | 시스템 관리자 원본 파일 접근 사유 기록 | SYSTEM_ADMIN이 원본 파일 접근 | 장애 대응 사유와 감사 로그 기록 | P1 |
| TC-NFR-SEC-007 | Refresh token cookie 보호 속성 | 로그인 수행 | Set-Cookie 확인 | HttpOnly, SameSite, Secure 속성 적용. 로컬 개발은 Secure 예외 가능 | P0 |
| TC-NFR-SEC-008 | CORS allowlist 검증 | 미허용 Origin에서 API 호출 | CORS 차단 또는 403 처리 | P0 |
| TC-NFR-SEC-009 | 보안 헤더 검증 | 주요 화면/API 응답 확인 | nosniff, Referrer-Policy, X-Frame-Options 또는 CSP 적용 | P1 |
| TC-NFR-SEC-010 | 민감 응답 캐시 방지 | 로그인/사용자 정보/refresh 응답 확인 | Cache-Control no-store 또는 동등 기준 적용 | P1 |

## 19.2 성능

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-PERF-001 | 광고물 목록 조회 성능 | 광고물 1,000건, page size 20 기준 목록 조회 | ADR-0042 기준 P95 1.5초 이내 관찰 | P2 |
| TC-NFR-PERF-002 | 검토 결과 상세 조회 성능 | review_items 500건 기준 페이징 조회 | ADR-0042 기준 P95 2초 이내 관찰, 페이징 정상 동작 | P2 |
| TC-NFR-PERF-003 | 근거 검색 응답 성능 | evidence_chunks 다수 등록 후 검색 | ADR-0042 기준 P95 3초 이내 관찰 | P2 |
| TC-NFR-PERF-004 | AI 분석 비동기 처리 | 대용량 광고물 분석 요청 | API는 P95 2초 이내 jobId 반환, 분석은 비동기 진행 | P0 |

## 19.3 이력/추적성

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-HIS-001 | 재분석 이력 보존 | 동일 광고물 재분석 | 기존 review 유지, 신규 review 생성 | P0 |
| TC-NFR-HIS-002 | 기준자료 버전 이력 보존 | 기준자료 수정 | 이전 버전 삭제 없이 보존, 새 standardVersionId 생성 | P0 |
| TC-NFR-HIS-003 | 추천 문구 판단 이력 보존 | 채택 후 수정 후 사용으로 변경 | `suggestion_decisions` 이력 추가, `suggestions.decision_status` 최신 상태 반영 | P1 |
| TC-NFR-HIS-004 | 리포트 생성 이력 보존 | 리포트 여러 번 생성 | report 이력 각각 저장 | P1 |
| TC-NFR-HIS-005 | 과거 검토 기준 버전 유지 | 기준자료 개정 후 과거 review 조회 | 기존 review의 standardVersionIds 변경 없음 | P0 |

## 19.4 API 계약

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-API-001 | OpenAPI 문법 검증 | `openapi/openapi.yaml` parse/schema validation 실행 | OpenAPI 문법 및 schema 오류 없음 | P0 |
| TC-NFR-API-002 | Spectral lint | `npx @stoplight/spectral-cli lint openapi/openapi.yaml` 실행 | ADR-0026/0062 기준 lint 통과 | P0 |
| TC-NFR-API-003 | TypeScript 타입 생성 diff | `openapi-typescript` 생성 후 git diff 확인 | 생성 타입 변경이 PR에 반영됨 | P1 |
| TC-NFR-API-004 | FastAPI generated OpenAPI diff | FastAPI 구현 후 `/openapi.json`과 원천 OpenAPI 비교 | path/method/schema/status code 차이 없음 | P1 |
| TC-NFR-API-005 | 핵심 플로우 API 포함 범위 | OpenAPI path 목록 확인 | Auth, 광고물/파일, AI 검토, 결과/Annotation, 기준자료, 리포트, PoC 검증 핵심 API 포함 | P0 |

## 19.5 화면 UI 및 반응형

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-UI-001 | 핵심 화면 기본 상태 표시 | S-003, S-004, S-005, S-006, S-007, S-008, S-012, S-014, S-015, S-016 진입 | loading, empty, error 상태가 화면별로 표시됨 | P1 |
| TC-NFR-UI-002 | 권한별 action 노출 | 상품부서, 준법감시, 기준 관리자, 시스템 관리자 계정으로 핵심 화면 진입 | 권한 없는 메뉴/action은 숨김 또는 비활성화되고 직접 접근은 403 처리 | P1 |
| TC-NFR-UI-003 | PC 기준 핵심 레이아웃 | 1280px 이상 viewport에서 핵심 화면 확인 | ADR-0060 기준 레이아웃 패턴과 주요 액션 영역이 유지됨 | P1 |
| TC-NFR-UI-004 | Tablet/Mobile fallback | 768px, 375px viewport에서 핵심 화면 확인 | 텍스트 겹침, 버튼 잘림, 필수 상태 확인 불가가 없음 | P2 |
| TC-NFR-UI-005 | Annotation 화면 반응형 제한 안내 | 모바일 viewport에서 S-007 진입 | 정밀 검토는 PC 사용 권장 안내 또는 제한된 fallback 표시 | P2 |

## 19.6 Notion 문서 게시 수동 테스트

이 절의 기대 개수 93개와 제외 개수 33개는 2026-07-14 테스트 대상 commit 기준이다. 운영 자동화 정책과 기존 페이지 갱신 방식은 별도 ADR 확정 전까지 테스트 범위에 포함하지 않는다.

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-DOC-001 | 게시 대상 선별 | 게시 스크립트를 dry-run으로 실행 | Git 추적 Markdown 93개가 선택되고 비 Markdown 33개와 비추적 파일은 제외됨 | P0 |
| TC-NFR-DOC-002 | 대상 페이지 사전조건 | 하위 block이 있거나 제목이 다른 부모 페이지로 게시 실행 | 제목이 `개발 문서`이고 비어 있는 페이지가 아니면 게시 전 실패함 | P0 |
| TC-NFR-DOC-003 | 번호와 ADR 계층 | 게시 후 `개발 문서`와 `15. ADR` 하위 block 조회 | 최상단에 번호 없는 `프로젝트 규칙`이 표시되고 구분선 다음 일반 문서 14개가 `01`~`14` 순서로 표시되며, 두 번째 구분선 다음 마지막 `15. ADR` 아래에 ADR 문서 78개가 표시됨 | P0 |
| TC-NFR-DOC-004 | 문서 본문과 링크 | 게시된 임의 문서의 본문과 링크 확인 | Git 문서 내용만 표시되고 배포 안내·별도 목록이 없으며 상대 Markdown 링크는 대상 commit GitHub 절대 링크로 변환됨 | P0 |
| TC-NFR-DOC-005 | 페이지 잠금 | 게시 완료 후 전체 페이지 API 조회 | 문서 93개, `15. ADR`, `개발 문서`의 `is_locked`가 모두 `true`임 | P0 |
| TC-NFR-DOC-006 | 게시 내용 완전성 | 게시 후 각 문서를 Markdown으로 재조회 | 모든 문서의 번호형 제목과 본문 대표 구문이 일치하고 `truncated=false`, 알 수 없는 block 0건임 | P0 |
| TC-NFR-DOC-007 | Secret 비노출 및 최소 범위 | GitHub Actions 환경 범위, checkout 설정, 로그와 결과 artifact 점검 | `NOTION_API_TOKEN`은 설정 검증·연결 확인·게시 단계에만 주입되고 외부 CLI 설치 단계, 로그, Markdown 페이지, JSON artifact에 노출되지 않으며 checkout credential도 설치 단계에서 사용할 수 없음 | P0 |
| TC-NFR-DOC-008 | 결과 추적 | GitHub Actions 완료 후 summary와 JSON artifact 확인 | 대상 commit, 일반/ADR 게시 수, 원본 경로·SHA-256, page ID/URL, 잠금 상태를 확인할 수 있음 | P1 |
| TC-NFR-DOC-009 | 실패 실행 생성물 정리 | ADR 게시 중 영구 `502`를 Mock으로 발생 | 제한 재시도 후 실패하고 이번 실행이 만든 프로젝트 규칙·일반 문서, `15. ADR` 및 구분선만 제거되며 부모 `개발 문서`는 유지됨 | P0 |
| TC-NFR-DOC-010 | 페이지별 본문 검증 | 서로 다른 Markdown을 게시한 Mock 페이지를 각각 재조회 | 각 페이지 검증은 해당 페이지에 게시한 본문만 사용하며 다른 문서의 대표 구문으로 통과하지 않음 | P1 |

---

# 20. End-to-End 테스트 시나리오

## E2E-001 광고물 등록부터 리포트 생성까지

| 단계 | 사용자 액션 | 검증 API/DB | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 광고물 등록 | POST `/advertisements` | 광고물 상태 `UPLOADED` |
| 2 | AI 검토 요청 | POST `/advertisements/{id}/reviews` | reviewId, jobId 생성 |
| 3 | 진행 상태 조회 | GET `/reviews/{id}/status` | 단계별 진행 상태 표시 |
| 4 | 검토 완료 확인 | `reviews.review_status` | `REVIEW_COMPLETED` |
| 5 | 결과 요약 조회 | GET `/reviews/{id}/summary` | 종합 위험도 반환 |
| 6 | 상세 결과 조회 | GET `/reviews/{id}/items` | 문제 항목 반환 |
| 7 | Annotation 조회 | GET `/reviews/{id}/annotations` | 표시 모드, 위치 상태, 좌표/텍스트 위치 반환 |
| 8 | 문구 추천 조회 | GET `/reviews/{id}/suggestions` | 대체 문구 반환 |
| 9 | 리포트 생성 | POST `/reviews/{id}/reports` | reportId 생성 |
| 10 | 리포트 다운로드 | GET `/reports/{id}/download` | 파일 다운로드 성공 |

---

## E2E-002 기준자료 등록 후 RAG 근거 매칭

| 단계 | 사용자 액션 | 검증 API/DB | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 기준자료 등록 | POST `/standards` | standardId, evidenceId 생성 |
| 2 | 기준자료 Chunk 생성 | `evidence_chunks` | qdrant_point_id, opensearch_doc_id 저장 |
| 3 | 광고물 검토 요청 | POST `/advertisements/{id}/reviews` | AI 분석 시작 |
| 4 | 위험 표현 검토 | `review_items` | 위험 표현 항목 생성 |
| 5 | 근거 매핑 확인 | `review_item_evidences` | reviewItem과 evidence 연결 |
| 6 | 상세 결과 조회 | GET `/reviews/{id}/items/{itemId}` | 근거 포함 응답 반환 |

---

## E2E-003 수정본 등록 및 재검토

| 단계 | 사용자 액션 | 검증 API/DB | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 최초 광고물 검토 완료 | `reviews` | 기존 review 생성 |
| 2 | 수정본 등록 | POST `/advertisements/{id}/revisions` | revisionId 생성 |
| 3 | 수정 전후 비교 | POST `/advertisements/{id}/comparisons` | comparisonId 생성 |
| 4 | 비교 결과 조회 | GET `/comparisons/{id}` | 해결/미해결/신규 리스크 반환 |
| 5 | 재분석 요청 | POST `/reviews/{id}/rerun` | newReviewId 생성 |
| 6 | 재검토 결과 확인 | GET `/reviews/{newReviewId}/summary` | 수정본 검토 결과 반환 |

---

## E2E-004 PoC 성능평가

| 단계 | 사용자 액션 | 검증 API/DB | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 검증 데이터셋 등록 | POST `/validation/datasets` | datasetId 생성 |
| 2 | 담당자 판단 등록 | POST `/validation/datasets/{id}/judgments` | judgment 저장 |
| 3 | AI 검토 결과 준비 | `review_items` | AI 결과 존재 |
| 4 | 성능평가 실행 | POST `/validation/evaluations` | evaluationId 생성 |
| 5 | 평가 snapshot 확인 | `evaluations` | snapshotHash와 입력/AI 결과 snapshot 저장 |
| 6 | KPI 확인 | `evaluation_metrics` | 정확도, 일치율 산출 |
| 7 | 결과 조회 | GET `/validation/evaluations/{id}` | KPI별 점수와 snapshot metadata 반환 |

---

# 21. 결함 분류 기준

| 결함 등급 | 설명 | 예시 |
| --- | --- | --- |
| Critical | 핵심 업무 불가 | 광고물 등록 불가, AI 검토 요청 불가 |
| Major | 주요 기능 오류 | 검토 결과 누락, 근거 매칭 실패, 리포트 생성 실패 |
| Minor | 부분 오류 | 필터 오류, 일부 메시지 오류 |
| Trivial | 사용성 또는 문구 오류 | 오탈자, 정렬 오류 |

---

# 22. 테스트 완료 기준

본 PoC의 테스트 완료 기준은 다음과 같다.

| 기준 | 완료 조건 |
| --- | --- |
| P0 테스트 | 100% Pass |
| P1 테스트 | 90% 이상 Pass, 미해결 결함은 우회 방안 존재 |
| Critical 결함 | 0건 |
| Major 결함 | 운영 검증 전까지 해결 또는 합의된 보류 |
| E2E 시나리오 | 핵심 4개 흐름 모두 Pass |
| 리포트 | 테스트 결과 요약 및 결함 목록 작성 |
| 감사 로그 | 주요 변경 행위 로그 저장 확인 |

---

# 23. 후속 상세화 필요사항

| 항목 | 상세화 내용 |
| --- | --- |
| 실제 테스트 데이터 | 샘플 광고물, 상품설명서, 약관, 기준자료 확보 |
| 테스트 자동화 | pytest 기반 API 테스트 작성 |
| Mock 정책 | ADR-0044 기준 PR/CI는 Mock/Fixture 기반, 정기/수동 평가는 실제 엔진 기반으로 분리 |
| RAG 검색 정책 | ADR-0043 기준 Top-K, 근거 표시 개수, 근거 부족 처리 기준 적용. 검색 인프라 장애는 ADR-0061 기준 RAG 검토 실패 및 retry 대상으로 검증 |
| 성능 기준 | ADR-0042 기준 PoC 런타임 성능 목표를 관찰 기준으로 적용 |
| 권한 정책 | ADR-0055 기준 role + department scope 적용. 목록 scope filter, 단건/다운로드 403 처리 |
| 세션/토큰 정책 | ADR-0056 기준 access token 만료, refresh token rotation/revoke, token 원문 저장 금지 검증 |
| 브라우저 보안 정책 | ADR-0057 기준 CORS allowlist, refresh/logout Origin 검증, cookie 속성, 보안 헤더 검증 |
| OpenAPI 계약 정책 | ADR-0062 기준 핵심 플로우 API OpenAPI 작성, Spectral lint, 타입 생성 diff, FastAPI generated OpenAPI diff 검증 |
| Docker Compose 정책 | ADR-0063 기준 `compose.yml` + `compose.dev.yml`, `compose.yml` + `compose.prod.yml` 조합 config 검증 |
| CI/CD Gate | ADR-0064 기준 PR 필수 Gate와 정기/수동 실제 엔진 평가 분리. PR은 `pytest -m "not external_ai and not slow"` 기준 |
| Parser/OCR 계약 | ADR-0065 기준 `NormalizedDocument` v1 fixture와 adapter contract test 적용 |
| Parser/OCR 라우팅 | ADR-0072 기준 PDF/복합 PDF `opendataloader-pdf`, HWP/HWPX `rhwp`, 이미지/스캔 PDF `PaddleOCR` 우선 적용 검증 |
| Parser/OCR 품질 재처리 | ADR-0073 기준 기술 retry, 조건 기반 보조 엔진 재처리, 최종 채택 산출물만 후속 전달 검증 |
| PoC 검증 Snapshot | ADR-0074 기준 DB 정답지 version, 평가 실행 snapshot, 기존 evaluation 불변성, snapshotHash 검증 |
| Coordinate 계약 | ADR-0066 기준 DB 명시 컬럼과 API `Coordinate` object 검증 |
| 화면 UI 정책 | ADR-0060 기준 핵심 화면 레이아웃, 권한별 action, 상태 표시, PC 우선 및 mobile fallback 검증 |
| 로그인 보호 정책 | ADR-0058 기준 비밀번호 정책, 실패 5회 잠금, 실패 응답 일반화, IP rate limit 검증 |
| 오류 메시지 | ADR-0045 기준 공통 오류 코드별 사용자 메시지와 민감정보 노출 금지 기준 적용 |
| Seed 정책 | ADR-0041 기준 공통 seed와 dev seed를 migration과 분리 |
| 평가 산식 | KPI별 분자/분모 정의 확정 |
| CI 연계 | ADR-0064 기준 PR 필수 Gate, main 병합 전 핵심 통합 테스트, 정기/수동 실제 엔진 평가, release 후보 smoke/E2E/migration 검증 분리 |

---

# 24. 결론

본 테스트케이스는 AI 기반 금융상품 광고심의 적정성 검토 에이전트 PoC의 핵심 기능을 API, DB, AI 분석, 근거 매칭, 리포트, 검증평가 관점에서 검증하기 위한 기준이다.

핵심 검증 흐름은 다음과 같다.

1. 광고물 등록
2. AI 검토 요청
3. OCR/VLM 텍스트 추출
4. Rule/RAG/Multimodal 검토 결과 생성
5. 근거 매칭
6. ADR-0051 기준 Annotation 표시
7. 문구 추천
8. 심의 의견 초안 및 리포트 생성
9. 수정 전후 비교
10. PoC 성능평가

본 문서를 기준으로 후속 단계에서는 pytest 기반 API 자동화 테스트, 테스트 데이터셋, CI 테스트 파이프라인을 작성한다.
