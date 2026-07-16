# 테스트케이스

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.37 |
| 기준일 | 2026-07-16 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.37 | 2026-07-16 | HWP/HWPX 파일 상세에서 브라우저 preview 호출을 차단하고 다운로드·Text IR 안내를 표시하는 회귀 기준을 추가 |
| v1.36 | 2026-07-16 | 권한 검증된 PDF 원본 preview proxy와 frontend PDF object 표시 회귀 기준을 추가 |
| v1.35 | 2026-07-16 | `opendataloader-pdf`·`paddleocr`·`rhwp` 실제 service adapter의 provider E2E와 rhwp Text IR offset 저장 증거 기준을 보강 |
| v1.34 | 2026-07-16 | ADR-0072 실제 Compose engine service와 PDF·이미지·HWP credentialed E2E 검증 기준을 반영 |
| v1.33 | 2026-07-16 | paid provider PDF E2E의 Redis delivery·provider 정규화·DB 근거 source/score 계약과 ADR-0072 실제 엔진 미구현 범위를 명시 |
| v1.32 | 2026-07-16 | OpenAI-compatible embedding의 Qdrant 적재·hybrid 근거 조회 및 model/endpoint 교체 재색인 검증을 추가 |
| v1.31 | 2026-07-16 | 신규 개발자 로컬 Compose 진입점의 설정 검증, migration·seed·health 순서, frontend API 주소, 재실행·중지·volume 초기화 검증 기준 추가 |
| v1.30 | 2026-07-16 | Git `main` Markdown 변경의 Notion 자동 증분 갱신, page ID 보존, mapping fail-closed, 페이지별 rollback·재실행·secret 격리 검증 기준 추가 |
| v1.29 | 2026-07-16 | 팀 Git 브랜치·PR·Conventional Commits·release/hotfix 역반영과 GitOps immutable 승격·rollback 정책의 수동 검증 기준 추가 |
| v1.28 | 2026-07-16 | Product CI가 Python OpenAPI parity 테스트 전에 pinned Node 도구를 설치하고, DB privilege probe가 빈 DB 대신 현행 0009 revision·대표 업무 relation을 검증하도록 회귀 기준 수정 |
| v1.27 | 2026-07-16 | Notion 수동 게시의 93개 Markdown 선별, 번호형 계층, secret 격리, 재시도·실패 정리와 페이지별 내용 검증 회귀 기준 통합 |
| v1.27 | 2026-07-16 | 승인 샘플 PDF/이미지의 OpenAI opt-in 추출·구조화 결과와 규정 PDF 적재/OpenSearch 근거 조회 수동 검증을 추가 |
| v1.26 | 2026-07-16 | 운영 교차검증에서 발견된 enum/read-path 500, refresh replay·bootstrap, worker lease·poison replay, targetIndexes, OCR DB 정합성과 frontend 흐름 회귀 Gate 추가 |
| v1.25 | 2026-07-15 | production recovery의 과거 실제 Docker 수동 증거와 현재 provider-free fake-Docker 회귀 증거를 분리하고 현재 HEAD 운영 복구 주장은 실제 Docker opt-in 재실행 후에만 가능하도록 정정 |
| v1.24 | 2026-07-15 | G010 Ruff canonical formatting 반영 후 G009 executable·manifest SHA-256 동기화 |
| v1.23 | 2026-07-15 | G009 선언 SHA-256 현재 파일 대조와 provider-free E2E 정확한 4/0/0 건수 fail-closed 회귀 기준 반영 |
| v1.22 | 2026-07-15 | 중복 M2 Gate 제거, Spectral 0 error와 warning 잔여를 정확히 구분하고 AC-18 최종 문서·일정 거버넌스 검증 기준 반영 |
| v1.21 | 2026-07-15 | M8 production recovery 공개·opt-in 명령의 6/6 terminal PASS와 multi-store 복구·outage·무잔여 정리 증거 반영 |
| v1.20 | 2026-07-15 | M8 provider-free 릴리스 workflow와 sanitized `external_ai` 수동 workflow 분리, backend/worker 보안·감사·readiness·recovery redaction Gate 반영 |
| v1.19 | 2026-07-15 | M8 실제 PostgreSQL restart/concurrency, 수정본→비교→재검토 frontend, worker lease reconciliation과 G011 반복 bootstrap 증거 반영 |
| v1.18 | 2026-07-15 | G008 M7 provider-free backend KPI/API/PostgreSQL runtime과 전체 backend 회귀 실행 증거를 기존 S-015/S-016 frontend 증거와 통합 반영 |
| v1.17 | 2026-07-15 | M7 S-015/S-016 생성 client 화면의 데이터셋/판단 등록, stored KPI·평가 제외·분모 0 미적용, loading/empty/error/권한 회귀 실행 증거 반영 |
| v1.16 | 2026-07-14 | G008 M7 정확히 5개 Validation operation, 0007 실제 PostgreSQL clean/M6 upgrade, synthetic KPI fixture/hash 및 TC-VAL/EVAL 개별 trace Gate 반영 |
| v1.15 | 2026-07-14 | G007 M6 contract/0006 migration synthetic fixture trace gate와 TC-SUG/QA/OPN/RPT/CMP 및 history 불변조건 검증 반영 |
| v1.14 | 2026-07-14 | G006 M5 backend/worker Rule→RAG→structured 실행·영속화·조회·실패 보존 회귀 증거 반영 |
| v1.13 | 2026-07-14 | M5 S-006~S-008 결과/Annotation 생성 client component 및 광고물→분석 완료→결과→Annotation 결정적 통합 실행 Gate 반영 |
| v1.12 | 2026-07-14 | G006 M5 OpenAPI/0005 migration/Rule·검색·structured output·Annotation synthetic fixture trace Gate 반영 |
| v1.11 | 2026-07-14 | M4 품질 재처리의 보조 adapter 실행·결정적 후보 선택·전체 시도 추적·선택 산출물 단일 영속화 회귀 검증 보강 |
| v1.10 | 2026-07-14 | M4 queue의 exact 6-field/version 계약과 교차 Job idempotency key 실행 전 거부 회귀 검증 보강 |
| v1.9 | 2026-07-14 | M4 backend/worker Review API·idempotency·1/3/10 retry·dead-letter·stale recovery·selected output와 실제 PostgreSQL+Redis+MinIO artifact lifecycle 실행 증거 반영 |
| v1.8 | 2026-07-14 | M4 생성 client 기반 S-004/S-005 요청·진행·retry/stale/final failure·OCR 확인 필요·재분석·권한·raw 비노출 frontend 실행 증거 반영 |
| v1.7 | 2026-07-14 | G005 M4 TC-REV-001~014/TC-OCR-001~024 trace manifest, OpenAPI/0004 migration/NormalizedDocument·raw artifact synthetic fixture entry Gate 반영 |
| v1.6 | 2026-07-14 | S-014 내부 기준 등록 필수 metadata의 정확한 multipart JSON과 `REFERENCE_METADATA_INVALID` 일반화 표시 통합 검증 반영 |
| v1.5 | 2026-07-14 | S-014 생성 client와 관리자 route gate, CRUD/불변 version/이력/reindex/Chunk/Hybrid Search의 loading·empty·error·redaction component/integration 검증 반영 |
| v1.4 | 2026-07-14 | G004-m3 실제 TC ID trace, Standards/Evidence/Reindex/Search 계약·migration·고정 score/vector fixture와 명시적 부분 장애 Gate 반영 |
| v1.3 | 2026-07-14 | M2 capability-local OpenAPI/migration/seed/fixture trace Gate, queryless preview descriptor와 scope·redaction negative contract 검증 반영 |
| v1.2 | 2026-07-14 | M1 앱 독립 검증, Compose smoke, DB bootstrap/Alembic 경계, 최소권한 및 dev/prod namespace 격리 CI 항목 반영 |
| v1.1 | 2026-07-14 | M0 OpenAPI core skeleton, lockfile 기반 lint, 참조/example/operationId 계약 검증 항목 반영 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, API/DB/Parser/OCR/RAG/평가 snapshot 테스트 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 테스트케이스 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 대상 시스템 | 멀티모달 RAG 기반 금융상품 광고심의 적정성 검토 AI 에이전트 PoC |
| 문서 버전 | v1.29 |
| 작성 목적 | API, DB, 화면, AI 분석 기능의 정상·예외·권한·이력 검증 기준 정의 |
| 기준 문서 | API 명세서 v1.2, DB 명세서 v1.2 |
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
| 비기능 | 권한, 오류 처리, 이력 저장, 감사 추적성, M1 플랫폼 및 CI |

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
| TC-ADV-001 | 광고물 정상 등록 | 유효한 광고 파일과 실제 PostgreSQL/MinIO 준비 | 필수값과 파일을 포함하여 광고물 등록 API 호출 | 광고물 ID와 상태 `UPLOADED` 저장, private bucket object 및 `storage_provider`/`bucket`/`object_key`/`checksum_sha256` 메타데이터 생성 | `advertisements`, `advertisement_files`, MinIO | P0 |
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
| TC-OCR-020 | Parser/OCR 기술 실패 retry | 품질 재처리 후보 PDF의 1차 Parser timeout fixture와 구성된 보조 adapter 준비 | AI 검토 실행 | 보조 adapter를 실행하지 않고 ADR-0059 기준 1/3/10 retry·dead-letter 경계로 전파되며 품질 재처리로 오분류되지 않음 | `review_steps`, `review_jobs` | P0 |
| TC-OCR-021 | 품질 미달 보조 엔진 재처리 | 복합 PDF, 1차 confidence `0.49`, `TABLE_EXTRACTION_MISSING`, 구성된 `mineru` fixture 준비 | Parser/OCR 실행 | 1차와 보조 adapter를 각 1회 실행하고 두 시도의 engine, 순번, primary 여부, `rerunReasonCode`, confidence, raw artifact, 선택 여부를 기록 | `parser_artifacts`, `review_steps` | P1 |
| TC-OCR-022 | 최종 채택 산출물만 후속 전달 | confidence·필수 필드·Text IR/Coordinate·warning·판정 문구 판독성이 다른 1차/보조 NormalizedDocument fixture 준비 | ReviewPipeline 실행 | ADR-0073 순서와 앞선 시도 우선 tie-break로 후보를 결정하고 정확히 하나의 `isSelectedOutput=true` 산출물만 `ocr_text_blocks`, `layout_blocks`, 후속 검토에 반영 | `parser_artifacts`, `ocr_text_blocks`, `layout_blocks` | P0 |
| TC-OCR-023 | OCR 판독 불가 자동 retry 제외 | 판정 대상 문구 confidence `< 0.50` fixture 준비 | AI 검토 실행 | 자동 retry 없이 `OCR_UNREADABLE` 확인 필요/평가 제외 후보 기록 | `review_items`, `evaluations` | P1 |
| TC-OCR-024 | VLM OCR 보조 재처리 제한 | 외부 AI 입력 불가 파일과 이미지 OCR 누락 fixture 준비 | 보조 재처리 판단 | VLM OCR을 실행하지 않고 확인 필요로 처리 | `review_steps`, `audit_logs` | P1 |
| TC-LIVE-001 | 승인 샘플 규정 PDF 적재 | dev Compose, `NH_EXTERNAL_AI_ENABLED=true`, 유효한 `OPENAI_API_KEY`, ADR-0002 승인 문서 | `scripts/ingest-reference-regulations.sh` 실행 | 각 PDF가 표준/version/evidence/chunk로 생성 또는 재사용되고 Qdrant/OpenSearch 재색인이 완료된다. key/원문은 출력되지 않는다. | standards/evidence/search index | P0/manual |
| TC-LIVE-002 | 승인 샘플 PDF/PNG 광고 실제 검토 | TC-LIVE-001 완료, product 계정으로 광고 업로드·검토 요청 | supplied sample PDF 또는 PNG를 업로드하고 완료 상태까지 조회 | 선택 산출물, 결과 item, 구조화 LLM score와 OpenSearch 근거 상태가 저장·조회된다. Rule 판정은 provider 출력으로 덮어쓰지 않는다. | review/jobs/results | P0/manual |
| TC-LIVE-003 | live provider fail-closed | `NH_EXTERNAL_AI_ENABLED=true` 이고 key 없음, 또는 HWP/HWPX 업로드 | worker 검토 실행 | `OPENAI_API_KEY_NOT_CONFIGURED` 또는 비지원 adapter 오류로 최종 실패하고 성공 결과·DB fallback 검색이 생성되지 않는다. | review/jobs/audit | P0 |
| TC-LIVE-004 | 실제 hybrid 근거 조회 | TC-LIVE-001 완료, `OPENAI_EMBEDDING_MODEL`과 1536 차원 Qdrant collection 설정 | 샘플 광고를 검토 요청 | 규정 chunk가 실제 vector로 Qdrant에 저장되고, OpenSearch 및 Qdrant가 모두 결과를 반환한 경우에만 `HYBRID` 근거가 결과 item에 연결된다. | Qdrant/OpenSearch/review items | P0/manual |
| TC-LIVE-005 | embedding endpoint/model 교체 | 새 OpenAI-compatible endpoint/model/dimension 및 새 Qdrant collection 설정 | 기존 collection을 재사용하지 않고 기준자료 재적재/재색인 | 새 vector dimension과 model metadata로만 검색하며, dimension 불일치/endpoint 오류는 `SEARCH_UNAVAILABLE` 또는 적재 실패로 종료된다. | Qdrant/reindex jobs | P1/manual |
| TC-LIVE-006 | 승인 PDF paid provider 종단간 검토 | TC-LIVE-001 완료, 동일 Redis URL/queue를 사용하는 backend·worker Compose, 유효한 opt-in key | 승인 PDF를 업로드하고 검토 요청 후 job 종료까지 조회 | `OCR_EXTRACTION`→근거 검색→결과 저장이 완료되고 review는 `CHECK_REQUIRED` 또는 정책상 최종 상태, job은 `COMPLETED`가 된다. OCR ID는 review별로 유일하고 근거 score는 0~1, source는 `KEYWORD`/`VECTOR`/`HYBRID`/`RULE_METADATA` 중 하나다. key/raw provider 응답은 노출되지 않는다. | review/jobs/ocr/results | P0/manual |
| TC-LIVE-007 | ADR-0072 실제 엔진 E2E | `opendataloader-pdf`, `PaddleOCR`, `rhwp` private Compose service 및 유효한 opt-in key | 일반 PDF, 스캔 PDF/PNG, HWP/HWPX 승인 샘플을 각각 업로드·검토 요청하고 완료 상태까지 조회 | 각 job의 선택 parser가 `opendataloader-pdf`, `paddleocr`, `rhwp`이며 service health·`NormalizedDocument` contract·최종 결과 저장이 확인된다. OpenAI는 구조화 판단에만 사용한다. | parser services/review/jobs/results | P0/manual |
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
| TC-FILE-001 | 파일 미리보기 조회 | PNG/JPEG/PDF/HWP fileId 존재 | 상세의 미리보기 선택 | 권한 검증된 backend proxy가 이미지 또는 `application/pdf` 원본 bytes를 반환하고, PDF는 browser object로 표시한다. HWP/HWPX는 미리보기 요청을 보내지 않고 다운로드·Text IR 안내를 표시한다. | `advertisement_files` | P0 |
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
| TC-RPT-014 | 프로세스 재시작 후 불변 다운로드 | HWPX/PDF report 생성 후 repository와 app 재생성 | report 조회·download 재호출 | bytes가 저장 canonical payload에서 동일 복원되고 snapshot_hash/sourceReportId 불변 | `reports` | P0 |

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
| TC-CMP-008 | 다른 광고물 revision 거부 | 광고물 A와 B의 revision 존재 | A 비교에 B revision 사용 | 404 NOT_FOUND, 비교 row 미생성 | `advertisement_revisions`, `comparisons` | P0 |
| TC-CMP-009 | 동시 revision 번호 직렬화 | 같은 광고물에 동시 업로드 | 2개 revision 병렬 생성 | row lock으로 중복 없이 연속 revision_no 저장 | `advertisement_revisions` | P0 |
| TC-CMP-010 | 생성 client 수정 비교 흐름 | 기준 review와 수정 파일 존재 | 화면에서 등록·비교·재검토 제출 | 서버 반환 revisionId만 comparison에 전달하고 새 reviewId 표시 | OpenAPI/generated client | P0 |
| TC-CMP-011 | 수정본 권한·감사 연속성 | 부서 scope/역할 fixture | 등록·비교·download와 scope 밖 접근 | 허용 호출은 actor/trace 감사, scope 밖 호출은 403 | `audit_logs` | P0 |

---

# 16. 기준자료 관리 테스트케이스

| TC ID | 테스트 항목 | 사전조건 | 테스트 절차 | 기대 결과 | 관련 DB/API | 우선순위 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-STD-001 | 기준자료 정상 등록 | 기준 관리자 권한과 유효한 내부 기준 metadata | `owningDepartment`, `documentName`, `sectionPath`, `effectiveDate`, `version`, `productGroup`를 포함한 multipart 등록 API 호출 | 정확한 metadata JSON이 전달되고 standardId, evidenceId 생성 | `standards`, `standard_versions`, `evidences` | P0 |
| TC-STD-002 | 기준자료 필수값 누락 | title/content 또는 내부 기준 필수 metadata 누락 | 기준자료 등록 API 호출 | 일반 필수값은 400 BAD_REQUEST, 유형별 metadata는 400 `REFERENCE_METADATA_INVALID` 반환 | - | P0 |
| TC-STD-003 | 기준자료 목록 조회 | 기준자료 등록됨 | `/standards` 호출 | 기준자료 목록 반환 | `standards` | P1 |
| TC-STD-004 | 기준자료 조건 검색 | 기준자료 다수 등록 | evidenceType, productGroup 조건 조회 | 조건 일치 목록 반환 | `standards` | P1 |
| TC-STD-005 | 기준자료 상세 조회 | evidenceId 존재 | `/evidences/{id}` 호출 | 근거 상세 반환 | `evidences` | P0 |
| TC-STD-006 | 기준자료 수정 | standardId 존재 | 수정 API 호출 | 기존 version 보존, 새 standardVersionId 생성 | `standard_versions` | P1 |
| TC-STD-007 | 기준자료 비활성화 | standardId 존재 | 비활성화 API 호출 | is_active=false | `standards` | P1 |
| TC-STD-008 | 기준자료 변경 이력 조회 | 수정 이력 존재 | histories API 호출 | 변경 이력 목록 반환 | `standard_versions` | P1 |
| TC-STD-009 | 권한 없는 기준자료 등록 | 상품부서 사용자 | 기준자료 등록 API 호출 | 403 FORBIDDEN 반환 | - | P0 |
| TC-STD-010 | 기준자료 Chunk 생성 | 직접 입력 기준자료 등록 완료 | 고정 Chunk/score/vector fixture로 RAG 인덱싱 수행 | `evidence_chunks` 생성, 동일 입력은 deterministic Qdrant/OpenSearch ID로 upsert | `evidence_chunks` | P1 |
| TC-STD-011 | 기준자료 재색인 요청 | 기준 관리자 권한과 standardVersionId 존재 | 재색인 API 호출 | `standard_reindex_jobs`에 QUEUED Job 생성 | `standard_reindex_jobs` | P0 |
| TC-STD-012 | 재색인 상태 조회 | 재색인 Job 존재 | 상태 조회 API 호출 | jobStatus, reindexScope, indexedChunkCount, 실패 사유 반환 | `standard_reindex_jobs` | P0 |
| TC-STD-013 | 임베딩 모델 변경 재색인 | 기존 Chunk와 새 embeddingModel 지정 | `VECTOR_ONLY` 또는 `INDEX_ONLY` 재색인 실행 | Chunk는 유지되고 Qdrant point와 embeddingModel metadata 갱신 | `evidence_chunks`, `standard_reindex_jobs` | P1 |
| TC-STD-014 | 관리자 Chunk 조회 | 기준 관리자 권한과 evidenceId 존재 | Chunk 목록/상세 조회 API 호출 | chunkText, sectionPath, parserRuleVersion, 검색 version/status를 반환하고 내부 index/point/doc ID는 숨김 | `evidence_chunks` | P1 |
| TC-STD-015 | 일반 사용자 Chunk 조회 차단 | 상품부서 사용자 | Chunk 조회 API 호출 | 403 FORBIDDEN 반환 | `audit_logs` | P0 |
| TC-STD-016 | 재색인 중복 실행 idempotency | 동일 standardVersionId와 동일 embeddingModel 준비 | 같은 재색인 Job 또는 요청을 2회 실행 | 동일 deterministic ID에 upsert되고 중복 Qdrant point/OpenSearch doc가 생성되지 않음 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-017 | 부분 실패 상태 기록 | Qdrant 성공, OpenSearch 실패 fixture 준비 | 재색인 실행 | Qdrant status ACTIVE, OpenSearch status FAILED, Job 실패 사유 기록 | `evidence_chunks`, `standard_reindex_jobs` | P0 |
| TC-STD-018 | 기준자료 비활성화 검색 제외 | 활성 기준자료 색인 완료 | 비활성화 후 검색 실행 | 관련 chunk index status EXCLUDED 또는 검색 filter로 제외 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-019 | stale index cleanup | EXCLUDED 상태 chunk 존재 | cleanup Job 실행 | Qdrant/OpenSearch 물리 삭제 후 status DELETED 기록 | `evidence_chunks` | P2 |
| TC-STD-020 | 검색 인덱스 표준 필드 색인 | 기준자료 Chunk 생성 완료 | Qdrant payload와 OpenSearch document 확인 | ADR-0071 표준 metadata와 searchSchemaVersion 저장 | `evidence_chunks`, Qdrant, OpenSearch | P0 |
| TC-STD-021 | OpenSearch synonym 검색 | synonymVersion이 적용된 기준자료 색인 | 동의어 표현으로 기준자료 검색 | 동의어가 적용되어 관련 chunk가 검색됨 | OpenSearch | P1 |
| TC-STD-022 | OpenSearch highlight 반환 | chunkText/title match가 있는 검색어 준비 | Chunk 상세 또는 검색 결과 조회 | `chunkText`, `title` highlight 또는 snippet 반환 | OpenSearch, API | P1 |
| TC-STD-023 | analyzer/synonym 변경 재색인 | opensearchAnalyzerVersion 또는 synonymVersion 변경 | `KEYWORD_ONLY` 또는 `INDEX_ONLY` 재색인 실행 | OpenSearch document version 갱신, 검색 결과 정상 반환 | `standard_reindex_jobs`, OpenSearch | P1 |

## 16.1 S-014 프론트엔드 통합 검증 기준

S-014 component/integration 테스트는 기존 `TC-STD-001`~`TC-STD-018`과 `TC-EVD-001`~`TC-EVD-014`의 화면 경계를 다음과 같이 함께 검증한다. 새 요구사항 ID나 TC ID를 만들지 않고 기존 계약 TC의 사용자 흐름 증거로 연결한다.

| 연결 TC | 화면 검증 |
| --- | --- |
| TC-STD-001/002/003/004 | 생성된 OpenAPI 타입으로 목록 loading/empty와 filter를 검증하고, 내부 기준 필수 metadata 여섯 필드와 `inputBoundary`가 multipart JSON 및 상위 상품군·적용일과 정확히 일치하는 성공 payload, 400 `REFERENCE_METADATA_INVALID` 일반화 문구·traceId·원문 message 미노출을 검증 |
| TC-STD-005/006/008 | 단건 상세 후 변경 사유가 있는 새 불변 version 저장, version 이력 표시 검증 |
| TC-STD-007/018 | 비활성화 사유 PATCH와 soft-deactivate 상태 표시 검증 |
| TC-STD-009/015 | `STANDARD_MANAGER`, `SYSTEM_ADMIN` 외 role은 route에서 API 호출 전에 차단되고 Chunk action이 노출되지 않음을 검증 |
| TC-STD-011/012/014/017 | 재색인 요청의 고정 version/양쪽 target과 Job 상태, redacted Chunk 내용·양쪽 index 상태, 내부 point/doc 식별자 미노출 검증 |
| TC-EVD-001/004/012/013/014 | deterministic rank/score/matchSource 표시, 503 일반화 문구와 traceId, server message 및 내부 검색 식별자 미노출, fallback 금지 검증 |

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

## 17.1 M7 S-015/S-016 프론트엔드 실행 증거

| 검증 묶음 | 실행 증거 |
| --- | --- |
| TC-VAL-001~005 | `apps/frontend/src/m7-validation.test.tsx`에서 frozen 생성 client 기반 multipart 데이터셋 등록, JSON 담당자 판단, version/제외 표시와 empty/error 상태를 검증한다. |
| TC-EVAL-001~010/012~015 | 동일 테스트에서 서버 저장 `score`, 분자/분모, 목표/달성 여부, 불변 snapshot hash, 승인 제외 집계와 `notApplicable=true` 분모 0 표시를 검증하며 브라우저 재계산을 금지한다. |
| 권한 회귀 | 상품부서 역할의 직접 route 접근은 API 호출 전에 차단하고, 준법감시/기준 관리자/시스템 관리자의 실행·조회 action 차이를 검증한다. |
| 실행 명령 | `npm --prefix apps/frontend run openapi:check`, `lint`, `typecheck`, `test`, `build`를 M7 frontend 완료 Gate로 사용한다. |

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
| TC-NFR-SEC-003 | 파일 다운로드 권한 검증 | 실제 private MinIO object에 권한 없는 사용자가 backend proxy 다운로드 시도 | 403 FORBIDDEN, object key/presigned URL 비노출, DENIED 감사 기록 | P0 |
| TC-NFR-SEC-004 | 민감정보 로그 저장 방지 | API 호출 후 로그/감사/오류 응답 확인 | Token/hash, 비밀번호, 파일 원문, bucket/object key 등 민감정보 미노출 | P0 |
| TC-NFR-SEC-005 | 상품부서 사용자의 타 부서 광고물 단건 접근 제한 | 타 부서 광고물 상세 조회 | 403 FORBIDDEN과 traceId 기반 안전 메시지, 광고/파일 원문 미노출 | P0 |
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

G007 M6 entry gate는 위 TC-SUG, TC-QA, TC-OPN, TC-RPT, TC-CMP 및 TC-NFR-HIS-003~004를
`m6_contract.test.mjs`와 `test_m6_database_contract.py`에 고정하고, provider-free synthetic
fixture의 SHA-256을 goal manifest에서 검증한다.

## 19.4 API 계약

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-API-001 | OpenAPI 문법 검증 | `openapi/openapi.yaml` parse/schema validation 실행 | OpenAPI 문법 및 schema 오류 없음 | P0 |
| TC-NFR-API-002 | Spectral lint | lockfile 설치 후 repository의 OpenAPI lint script 실행 | transient `npx` 다운로드 없이 ADR-0026/0062 기준 lint 통과 | P0 |
| TC-NFR-API-003 | TypeScript 타입 생성 diff | `openapi-typescript` 생성 후 git diff 확인 | 생성 타입 변경이 PR에 반영됨 | P1 |
| TC-NFR-API-004 | FastAPI generated OpenAPI diff | FastAPI 구현 후 `/openapi.json`과 원천 OpenAPI 비교 | path/method/schema/status code 차이 없음 | P1 |
| TC-NFR-API-005 | M2 핵심 플로우 API 포함 범위 | OpenAPI path 목록과 FilePreview example/pattern 확인 | Auth/Common, 광고물 등록·목록·상세, authorized 파일 preview/content/download, redacted 감사 조회만 포함하고 previewPath는 queryless content descriptor이며 `pageNo`는 실제 content 요청에만 사용 | P0 |
| TC-NFR-API-006 | M2 capability-local 범위 | OpenAPI metadata, paths, components 확인 | v0.2.0의 12 operation/schema가 trace manifest와 일치하고 Review/Parser/Search/Result/Report 등 M3+ 계약이 없음 | P0 |
| TC-NFR-API-007 | OpenAPI 참조 및 example 검증 | 모든 local `$ref` 해석과 schema example validation 실행 | 끊어진 참조와 schema 불일치 example이 없음 | P0 |
| TC-NFR-API-008 | operationId 유일성 | 모든 path operation의 `operationId` 수집 후 중복 검사 | M2/M3 operation을 보존한 M4 source contract 28개 operation에 누락·중복 `operationId`가 없음 | P0 |

## 19.5 화면 UI 및 반응형

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-UI-001 | 핵심 화면 기본 상태 표시 | 로그인, S-002, S-003 및 후속 핵심 화면 진입 | 로그인 validation과 S-002/S-003 loading, empty, error, required/file validation 상태가 화면별로 표시됨 | P1 |
| TC-NFR-UI-002 | 권한별 action 노출 | 상품부서, 준법감시, 기준 관리자, 시스템 관리자 계정으로 핵심 화면 진입 | STANDARD_MANAGER의 광고 등록/목록 action은 요청 전 거부되고, 타 부서 상세 직접 접근은 403 traceId 기반 안전 메시지를 표시하며 민감 원문을 숨김 | P1 |
| TC-NFR-UI-003 | PC 기준 핵심 레이아웃 | 1280px 이상 viewport에서 핵심 화면 확인 | ADR-0060 기준 레이아웃 패턴과 주요 액션 영역이 유지됨 | P1 |
| TC-NFR-UI-004 | Tablet/Mobile fallback | 768px, 375px viewport에서 핵심 화면 확인 | 텍스트 겹침, 버튼 잘림, 필수 상태 확인 불가가 없음 | P2 |
| TC-NFR-UI-005 | Annotation 화면 반응형 제한 안내 | 모바일 viewport에서 S-007 진입 | 정밀 검토는 PC 사용 권장 안내 또는 제한된 fallback 표시 | P2 |

## 19.6 M1 플랫폼 및 CI

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-INFRA-001 | 앱별 독립 품질 Gate | backend와 worker의 lint/typecheck/test를 각각 실행하고 frontend의 clean install/lint/typecheck/test/build를 실행 | 세 앱이 다른 앱의 런타임 기동 없이 독립 통과하고 capability 업무 로직이 포함되지 않음 | P0 |
| TC-NFR-INFRA-002 | dev/prod Compose 및 dev health smoke | env example을 사용해 dev/prod `docker compose config`를 검증하고 dev stack의 앱·PostgreSQL·Redis·MinIO·Qdrant·OpenSearch health를 확인 | 두 config 오류가 없고 dev 필수 서비스가 healthy 또는 readiness 응답 성공 | P0 |
| TC-NFR-INFRA-003 | DB bootstrap, migration 및 seed 경계 | bootstrap 전용 identity로 초기화를 두 번 실행하고 같은 volume의 `db-bootstrap`만 강제 재생성하며 migration/seed를 반복 실행 | active postmaster 검증 후 별도 launch 없이 종료, sentinel/data/PostgreSQL ID/role·DB·public schema ACL 불변, PANIC·invalid checkpoint·interrupted recovery·잔여물 0 | P0 |
| TC-NFR-INFRA-004 | DB 최소권한 및 privileged credential 격리 | migration role 관리, app DDL, readonly write를 실제 DB에서 시도하고 workflow/config/image/artifact에서 bootstrap/admin 자격증명 주입을 검사 | 모든 금지 SQL이 거부되고 privileged 자격증명은 일회성 bootstrap/probe 경계 밖에 존재하지 않으며 runtime DSN과 migration DSN identity가 다름 | P0 |
| TC-NFR-INFRA-005 | dev/prod namespace 격리 | env example과 rendered Compose에서 PostgreSQL DB, MinIO bucket, Qdrant collection, OpenSearch index, Redis queue/cache prefix를 비교하고 교차 환경 접근 probe 실행 | 모든 namespace 값이 환경별로 다르고 dev 자격증명으로 prod namespace 접근이 거부됨 | P0 |
| TC-NFR-INFRA-006 | 신규 개발자 로컬 전체 기동 | `.env.dev.example`을 복사하고 `scripts/local-dev.sh up` 실행 후 migration·공통/dev seed·전체 health와 브라우저 API 주소를 확인하며 `down`/`reset`을 재실행 | 외부 provider credential 없이 두 synthetic 계정 로그인과 frontend/backend/worker 접근이 가능하고, `down`은 volume 보존, `reset`은 해당 Compose project volume만 삭제 후 빈 DB부터 재구성 | P0 |

## 19.7 M2 계약·통합 trace Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Goal trace | `tests/fixtures/m2/trace-manifest.json` | `G003-m2`, OpenAPI 12 operation/schema, `0002_m2_auth_advertisement_audit`, synthetic fixture hash, 실제 `TC-COM-001..020`/`TC-ADV-001..017` 매핑 일치 |
| Contract | `npm run openapi:check` | schema/example, `$ref`, operationId, multipart/status, 403 scope, response redaction 검증과 Spectral 0 error 통과. warning은 비차단 잔여로 출력하며 0건으로 오기하지 않음 |
| DB static | `python3 -m unittest tests.integration.test_m2_database_contract -v` | M2 owner table/column/grant, active refresh revoke index, seed 분리/guard 검증 통과 |
| DB/Object Storage integration | 실제 PostgreSQL/MinIO backend integration test | clean upgrade, duplicate seed, private object 저장/조회, 타 부서 preview/download 403, DB/object rollback 및 secret/object-key 비노출 |
| Browser | frontend test suite | unauth validation, cookie/Bearer 호출, loading/error redaction, login→multipart 등록→목록/상세, 타 부서 상세 403 검증 통과 |

## 19.8 M4 계약·DB·fixture entry Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Goal trace | `governance/goal-manifests/G005-m4-parser-ocr-job.json` | 실제 `TC-REV-001..014`, `TC-OCR-001..024`가 executable node에 매핑되고 OpenAPI/DB/fixture SHA-256이 고정됨 |
| Review/Job contract | `tests/api_contract/m4_contract.test.mjs` | 요청/이력/상태/재분석 operation, PostgreSQL 상태 필드, 최대 retry 3, minimal `ReviewQueueMessageV1` 잠금 |
| Parser contract | `packages/parser-contracts/tests/test_contracts.py` | NormalizedDocument v1 round-trip, 0.80/0.79/0.49 confidence, coordinate/offset, 파일별 routing, VLM 제한 통과 |
| Raw artifact contract | `packages/parser-contracts/tests/test_contracts.py` | checksum 불일치 거부, 일반 사용자 접근 거부, redacted audit, retention hold/승인 삭제 계약 통과 |
| DB static | `tests/integration/test_m4_database_contract.py` | 0004가 0003을 상속하고 6개 owner table, active 중복, retry/heartbeat/dead-letter, selected artifact/coordinate/offset 제약을 포함 |
| Runtime parity | `apps/backend/tests/test_backend_health.py::test_runtime_openapi_semantically_matches_static_contract` | handler 구현 전 projection을 포함한 runtime/static v0.4.0 operation/schema/status 의미 차이 0 |

이 Gate는 external OCR/provider 성공을 주장하지 않는다. 실제 PostgreSQL+Redis+MinIO 상태 전이와 backend/worker 실행, frontend 생성 client/UI는 frozen boundary를 소비하는 후속 M4 delivery lane에서 별도 검증한다.

## 19.9 M4 frontend delivery Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Generated client | `cd apps/frontend && npm run openapi:check` | OpenAPI v0.4.0 `requestAdvertisementReview`, `listAdvertisementReviews`, `getReviewStatus`, `rerunReview`와 Review schema 생성물이 clean diff를 유지 |
| Request/progress UI | `apps/frontend/src/review-flow.test.tsx` | S-004 loading·요청 payload·성공 이동과 S-005 진행률·단계·수동 갱신·완료를 검증 |
| Recovery/failure UI | `apps/frontend/src/review-flow.test.tsx` | `RETRY_PENDING`, `STALE`, `FAILED_FINAL`, `isRetryable` 기반 재분석과 immutable `newReviewId` 이동을 검증 |
| Quality/permission/redaction | `apps/frontend/src/review-flow.test.tsx` | `CHECK_REQUIRED`/`OCR_UNREADABLE` 확인 필요, 타 부서 403, raw artifact/object key/presigned URL 비노출을 검증 |
| Frontend quality | `cd apps/frontend && npm run lint && npm run typecheck && npm test && npm run build` | lint/typecheck/component·API test/build가 모두 통과 |

## 19.10 M4 backend/worker runtime delivery Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Review API/runtime | `apps/backend/tests/test_m4_reviews.py` | frozen 요청/이력/상태/재분석 응답, 부서 scope, 활성 중복 409, immutable round와 식별자-only queue를 검증 |
| Worker state machine | `apps/worker/tests/test_m4_jobs.py` | exact `review-job-v1` 6-field payload, 교차 Job idempotency key 실행 전 거부, duplicate delivery 무시, 합법 claim, 1/3/10분 세 번 retry 후 `FAILED_FINAL`/dead-letter, heartbeat stale recovery를 검증 |
| Parser persistence/security | `apps/worker/tests/test_m4_jobs.py`, parser contract suite | 선택된 `NormalizedDocument`만 영속화하고 저신뢰도 확인 필요, raw/checksum, queue/log redaction을 검증 |
| Actual tri-store | `tests/integration/test_m4_actual_postgres_redis_minio.py` | migration 0004가 적용된 실제 PostgreSQL, Redis 7, MinIO private buckets에서 enqueue→claim→artifact/block 저장→완료, restart recovery, 접근 거부/예외 감사, retention hold/승인 삭제를 synthetic fixture로 검증 |

## 19.11 M5 계약·DB·fixture entry Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Goal trace | `governance/goal-manifests/G006-m5-review-results.json` | 실제 `TC-RES-001..005`, `TC-ITEM-001..007`, `TC-RAG-001..005`, `TC-EVD-007..011/014`, `TC-ANN-001..011`이 executable node에 매핑되고 OpenAPI/client/fixture SHA-256이 고정됨 |
| Result contract | `tests/api_contract/m5_contract.test.mjs` | summary/items/detail/annotations operation, risk rationale, source engine/version, 명시적 evidence 상태 계약 잠금 |
| Failure semantics | `tests/fixtures/m5/search-evidence-v1.json`, `structured-output-v1.json` | 업무적 근거 부족과 검색 장애, structured schema 오류가 분리되고 Rule item ID 보존 |
| Annotation contract | `tests/fixtures/m5/annotation-display-v1.json` | 0.80 BOX, 0.79 TEXT_HIGHLIGHT, 0.49 LIST_ONLY 세 표시 경로와 Coordinate/offset fallback 잠금 |
| DB static | `tests/integration/test_m5_database_contract.py` | 0005가 0004를 상속하고 3개 owner table, evidence rank/version, 장애 code, BOX/offset 제약 포함 |
| Generated client | `cd apps/frontend && npm run openapi:check` | OpenAPI v0.5.0 네 operation과 M5 schema 생성물이 clean diff 유지 |
| Frontend result/Annotation | `cd apps/frontend && npm test -- --run src/m5-results.test.tsx` | `TC-RES-001/003`, `TC-ITEM-001/003/005/006/007`, `TC-ANN-001/005/006/007/008/010/011`, `TC-NFR-UI-005`를 S-006 집계·부분 실패, S-008 필터/상세, S-007 BOX/offset/list fallback·권한/empty 상태와 광고물 분석 완료→결과→Annotation 이동으로 결정적으로 검증 |
| Runtime parity | `apps/backend/tests/test_backend_health.py::test_runtime_openapi_semantically_matches_static_contract` | 실제 M5 handler와 frozen projection을 포함한 runtime/static operation/schema/status 의미 차이 0 |

이 Gate는 external LLM/provider/network 호출을 금지하고 provider/model을 null로 유지한다. S-006~S-008 화면은 frozen generated client와 local fetch fixture로 실행하며, backend Rule/RAG/structured pipeline은 다음 runtime lane에서 같은 계약을 소비한다.

## 19.12 M5 backend·worker 실행 검증

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Rule/risk property table | `apps/worker/tests/test_m5_results.py` | 최상급/절대 표현, 조건 없는 금리, 정상 문구가 동일 config에서 각각 HIGH/MEDIUM/LOW 구조 결과를 결정적으로 만들고 policy/reason/source version을 항상 포함 |
| RAG evidence/failure | `apps/worker/tests/test_m5_results.py` | 고정 후보 중 0.70 이상 최대 3개를 선정하고 `INSUFFICIENT`, `RAG_SEARCH_UNAVAILABLE`, `RAG_SEARCH_FAILED`가 Rule 판정·위험도를 덮지 않음 |
| Structured fixture | `apps/worker/tests/test_m5_results.py`, `tests/fixtures/m5/structured-output-v1.json` | provider/model null, `networkAllowed=false`인 versioned mock만 사용하고 invalid schema를 명시하면서 Rule/RAG 결과 보존 |
| Worker integration | `apps/worker/tests/test_m5_results.py` | 선택된 parser 산출물 이후 result bundle이 completion 전에 저장되고 확인 필요 상태가 job/review에 전파됨 |
| Result API/scope | `apps/backend/tests/test_m5_result_api.py` | summary/items/detail/annotations 실제 handler가 frozen v0.5 응답, evidence snapshot, BOX 위치와 부서 scope 403을 반환 |
| Regression gates | `uv run pytest apps/backend/tests apps/worker/tests`, `uv run mypy`, `uv run ruff check apps/backend apps/worker` | M0~M4 회귀 없이 backend/worker 전체 test, type, lint 통과 |

## 19.13 M7 계약·DB·fixture entry Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Goal trace | `governance/goal-manifests/G008-m7-kpi.json` | 실제 `TC-VAL-001..005`, `TC-EVAL-001..015`가 각각 executable node에 매핑되고 OpenAPI/client/fixture SHA-256이 고정됨 |
| Validation contract | `tests/api_contract/m7_contract.test.mjs` | OpenAPI v0.7.0에 정확히 5개 Validation operation, versioned dataset/judgment, 4개 KPI/목표/제외/부분점수/미적용 계약 잠금 |
| Deterministic fixture | `tests/fixtures/m7/validation-kpi-v1.json` | customer data/provider/network 없이 1.0/0.5/0, 승인/미승인 제외, AI 오류 0점, 분모 0, canonical snapshot과 신규 평가 hash를 재현 |
| DB history/static | `tests/integration/test_m7_database_contract.py` | 0001~0006 SHA-256 동일, 0007이 0006을 상속하고 validation 4개 테이블과 version/snapshot/KPI 제약만 소유 |
| Actual PostgreSQL | `tests/integration/test_m7_database_contract.py::test_actual_postgres_clean_and_m6_to_m7_upgrades` | 임시 PostgreSQL 16에서 빈 DB 0001→0007과 기존 M6 DB 0006→0007이 실제 Alembic 실행되고 4개 테이블/nullable score/head revision 확인 |
| Generated client | `npm --prefix apps/frontend run openapi:check` | v0.7.0 generated TypeScript client가 source 계약과 clean diff 유지 |
| Runtime parity | `apps/backend/tests/test_backend_health.py::test_runtime_openapi_semantically_matches_static_contract` | frozen M7 fragment를 포함한 runtime/static operation/schema/status 의미 차이 0 |

이 Gate는 provider SDK, 외부 network, credential 및 고객사 원문을 사용하지 않는다. 데이터셋/정답지의 운영 원천은 PostgreSQL이며 Git fixture는 개발·테스트 회귀 입력으로만 사용한다.

## 19.14 M7 backend 실행 검증

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| KPI golden/unit | `apps/backend/tests/test_m7_kpi.py` | 4개 KPI의 정확한 분자/분모, 1/0.5/0, 승인 제외, AI 오답 0, partial count, 분모 0 미적용을 provider 없이 재현 |
| Runtime API/권한 | `apps/backend/tests/test_m7_validation_api.py` | 정확히 5개 route가 dataset/judgment version, role gate, 생성 감사, 불변 evaluation snapshot/hash와 저장 KPI를 반환 |
| PostgreSQL repository | `apps/backend/tests/test_m7_postgres_repository.py` | 실제 PostgreSQL에서 dataset/judgment 저장과 version 증가, evaluation/metric 원자 저장 및 불변 roundtrip 통과 |
| Migration/runtime parity | `tests/integration/test_m7_database_contract.py`, `apps/backend/tests/test_backend_health.py` | clean/M6 upgrade와 runtime/static OpenAPI 의미가 frozen v0.7.0 계약과 일치 |
| Backend regression | `uv run python -m pytest -m "not external_ai and not slow" -q` | provider/network 없이 기존 backend·worker 회귀와 M7 실행 검증이 함께 통과 |
| Static quality | `uv run ruff check .`, `uv run mypy` | lint 오류 0, canonical package type 오류 0 |

| Cleanup/namespace | 고유 Compose project + dev env example | 종료 후 M4 검증 컨테이너/network/volume/임시 env 잔여물이 0이고 parser bucket/queue가 환경 prefix로 격리됨 |

## 19.15 M8 릴리스 후보 통합 검증

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| 실제 PostgreSQL durability | `apps/backend/tests/test_m8_support_postgres.py` | 0001→0008 fresh migration, runtime role 접속, fresh repository/FastAPI app restart, report bytes/hash/source linkage, wrong-ad revision 거부, 동시 revision 번호 직렬화 통과 |
| OpenAPI/generated client | `npm run openapi:check`, `npm --prefix apps/frontend run openapi:check` | v0.8.0 runtime/static 의미 일치, revision multipart operation 1개, 생성 TypeScript diff 0 |
| Frontend E2E component | `apps/frontend/src/m6-support.test.tsx` | upload→returned revisionId→comparison→rerun 세 요청의 순서·payload·화면 ID 표시 통과 |
| Worker lifecycle | `PYTHONPATH=. uv run pytest -q apps/worker/tests` | supervised shutdown/readiness, heartbeat, stale/due retry, publish lease recovery, 미구성 parser 최종 실패 포함 39 passed |
| Worker live reconciliation | `M8_LIVE_DATABASE_URL=... M8_LIVE_REDIS_URL=... PYTHONPATH=. uv run pytest -q tests/integration/test_m8_worker_reconciliation.py -vv` | PostgreSQL 16.9·Redis 7에서 publish 실패 lease 보존/만료 후 6-field 재발행과 STALE recovery 1 passed |
| 반복 Compose bootstrap | `NH_RUN_G011_DOCKER_REGRESSION=1 PYTHONPATH=. uv run pytest tests/integration/test_compose_bootstrap_repeat_up.py -q` | same-volume bootstrap 재생성 3/3, 데이터·ACL·PostgreSQL identity 보존, 금지 recovery log/잔여물 0 |

## 19.16 M8 운영·보안·외부 엔진 분리 Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| Provider-free E2E 4종 | `uv run pytest tests/e2e -q`, `python3 scripts/validate_goal_manifest.py governance/goal-manifests/G009-m8-release.json` | E2E-001~004가 4 passed/0 failed/0 skipped이고 AC16.1~16.4 및 실제 25개 TC node에 연결됨. G009의 OpenAPI·generated client·migration·artifact 선언 SHA-256은 현재 저장소 파일과 일치해야 하며 불일치·누락 시 실패함. manifest SHA-256 `cfb07ea58609abbaa856d32345d69e4154e0c8da5e23e20e4050518496663d09`, executable SHA-256 `30a8c56fb10ac85c82cf5a6a054a1f5113e0df2060f6cd6ce6e9662a77f86923`, fixture SHA-256 `b7467261128143d46328b8f0fe81f783ee7bce78d102d35d2d5002be46e74b3a` |
| Provider-free release workflow | `.github/workflows/release-readiness.yml`, `tests/release/test_m8_release_workflows.py` | PR/push Gate가 secret 또는 실제 provider 호출 없이 G009 provider-free JUnit 결과를 manifest 고정 기대치 `4 passed/0 failed/0 skipped`와 정확히 비교하고, 이어서 E2E/release, lint/type/OpenAPI/frontend/docs/governance를 결정적으로 실행하며 `external_ai`를 제외함 |
| Recovery 선행 안전 Gate | `.github/workflows/release-readiness.yml` | 수동 recovery smoke가 `NH_RUN_G011_DOCKER_REGRESSION=1`인 `test_compose_bootstrap_repeat_up.py`를 먼저 통과한 후에만 `scripts/release-smoke.sh`를 실행함 |
| Production recovery evidence boundary | 현재 provider-free 회귀: `uv run pytest tests/release/test_release_recovery_contract.py -q -rs`; 실제 Docker opt-in 재검증: `NH_RUN_M8_RELEASE_DOCKER=1 uv run pytest tests/release/test_release_recovery_contract.py -q -rs` 또는 `bash scripts/release-smoke.sh --env-file .env.prod.example --fresh-project --with-restart-and-outages` | `6 passed in 666.35s`는 release-smoke 변경 전 과거 실제 Docker 수동 실행 증거이며 현재 HEAD의 운영 복구 성공으로 간주하지 않는다. 현재 HEAD의 기본 실행 증거는 `12 passed, 1 skipped`이며, skip은 실제 Docker opt-in smoke이다. 이 실행은 provider/network 없이 static·fake-Docker로 명령 순서, timeout/status 보존, signal-safe cleanup, dirty-project 거부 및 recovery 계약을 회귀 검증하지만 실제 PostgreSQL·MinIO·Qdrant·OpenSearch·Redis 복구를 증명하지 않는다. 현재 HEAD에서 production recovery 성공을 주장하려면 격리된 환경에서 위 opt-in 실제 Docker 명령을 새로 실행해 multi-store 복구·outage·무잔여 cleanup 결과와 정확한 현재 출력 건수를 다시 기록해야 한다. |

## 19.17 AC-18 최종 문서·일정 거버넌스 Gate

| 검증 범위 | 실행/증거 | 기대 결과 |
| --- | --- | --- |
| 구현 경로 | `README.md`, `docs/functional-specification.md` | backend/worker runtime, frontend client/generated contract, OpenAPI `0.8.0`, migration `0001`~`0009` 경로가 저장소 실제 경로와 일치 |
| Provider 경계 | release/external-AI workflow와 `-m "not external_ai and not slow"` | provider-free 자동 Gate와 credentialed `external_ai` 수동 평가를 분리하고 서로의 성공을 대체하지 않음 |
| 일정/Kanban | `docs/development-schedule-and-notion-kanban.md` | 구현 증거가 있는 task만 `Done`; 실제 provider, 고객 검증·피드백, 배포·tag, 미집계 P0/P1/Critical 기준은 `Backlog`/`Blocked` 유지 |
| 문서 정합성 | `scripts/check-doc-consistency.sh`, `python3 -m scripts.doc_guard validate --scope working`, governance unit test | metadata·변경 이력·링크·traceability 0 error |
| 완료 해석 | AC-18 final governance report | 문서 동기화 완료를 실제 외부 AI 품질이나 최종 사업 수용 완료로 과장하지 않음 |
| 외부 엔진 수동 증거 | `.github/workflows/external-ai-evaluation.yml`, `tests/release/test_m8_release_workflows.py` | `workflow_dispatch`와 승인 environment에서만 `external_ai` marker를 실행하고 provider/engine/model/config SHA-256/dataset ID/revision/time/count만 sanitized JSON으로 보존하며 provider-free Gate와 분리됨 |
| Backend 보안·trace | `tests/release/test_m8_release_operations.py` | `TC-COM-009`, `TC-NFR-SEC-009`, `TC-NFR-SEC-010` 기준 request ID, CSP/HSTS/nosniff/frame 보호, 민감 응답 `no-store`, token 비노출이 재현됨 |
| 감사 redaction | `tests/release/test_m8_release_operations.py` | `TC-AUD-007`, `TC-NFR-SEC-004` 기준 로그인 audit가 actor/action/result/trace만 보존하고 비밀번호/token/email/name/IP 원문을 저장하지 않음 |
| Worker readiness·recovery log | `tests/release/test_m8_release_operations.py` | queue 장애 시 health와 readiness를 분리해 503 `not_ready`를 반환하고 recovery 오류 log는 job/review ID를 구조화 필드로 남기되 token/object key/presigned URL/원문을 포함하지 않음 |

이 Gate의 외부 엔진 workflow는 실제 엔진 성공을 provider-free 완료 조건으로 주장하지 않는다. 수동 실행 결과는 `supplementary_only=true`로 기록하며 secret, 고객 원문, raw test log는 artifact에서 제외한다.

## 19.18 Notion 문서 단방향 동기화 테스트

이 절의 기대 개수 94개와 제외 개수 33개는 ADR-0077 적용 commit 기준이다. Git `main`이 원본이며 기존 Notion page ID와 댓글·공유 URL을 유지하는 증분 갱신을 검증한다.

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-DOC-001 | 게시 대상 선별 | 게시 스크립트를 dry-run으로 실행 | Git 추적 Markdown 94개가 선택되고 일반 15개·ADR 79개로 완전히 분류되며 비 Markdown 33개와 비추적 파일은 제외됨 | P0 |
| TC-NFR-DOC-002 | page map 완전성 | manifest와 `governance/notion-page-map.json`을 비교 | 모든 source path가 중복 없이 하나의 올바른 parent/page ID에 매핑되고 누락·중복은 동기화 전에 실패함 | P0 |
| TC-NFR-DOC-003 | 자동 실행 범위·실패 수렴 | `main`에 Markdown과 비문서 파일을 각각 push하고 중간 동기화 실패 후 다음 문서 변경을 push | 게시 대상 Markdown 변경에만 실행되고 마지막 성공 동기화 commit부터 현재까지를 선택하여 이전 실패 문서도 다음 실행에 다시 포함됨 | P0 |
| TC-NFR-DOC-004 | 기존 페이지 증분 갱신 | 매핑된 문서 하나를 변경하고 동기화 | 기존 page ID·URL을 유지한 채 공식 CLI page update로 본문과 제목이 Git 원본으로 교체됨 | P0 |
| TC-NFR-DOC-005 | 본문과 링크 | 갱신된 문서의 Notion Markdown을 재조회 | Git 문서 내용만 표시되고 게시 메타데이터가 없으며 상대 Markdown 링크는 대상 commit GitHub 절대 링크로 변환됨 | P0 |
| TC-NFR-DOC-006 | 잠금·내용 완전성 | 갱신 완료 페이지를 API로 재조회 | `is_locked=true`, 제목·대표 본문 일치, `truncated=false`, unknown block 0건임 | P0 |
| TC-NFR-DOC-007 | Secret 비노출 및 최소 범위 | GitHub Actions 환경 범위, checkout 설정, log와 artifact 점검 | `NOTION_API_TOKEN`은 연결·동기화 단계에만 주입되고 설치 단계, log, Markdown, JSON artifact에 노출되지 않으며 checkout credential도 유지하지 않음 | P0 |
| TC-NFR-DOC-008 | 결과 추적 | Actions summary와 JSON artifact 확인 | 기준/대상 commit, source path·SHA-256, page ID/URL, action, 검증 결과를 확인할 수 있음 | P1 |
| TC-NFR-DOC-009 | 페이지별 rollback | update 후 검증 단계에 영구 오류를 Mock으로 발생 | 갱신 전 Markdown·제목이 복구되고 페이지가 다시 잠긴 뒤 workflow가 실패함 | P0 |
| TC-NFR-DOC-010 | 멱등 재실행 | 동일 before/after와 문서로 동기화를 두 번 실행 | 동일 page ID만 반복 갱신하고 중복 페이지를 만들지 않으며 최종 본문이 Git 원본과 일치함 | P0 |
| TC-NFR-DOC-011 | mapping fail-closed | source path 누락·중복·잘못된 parent map으로 동기화 | Notion 변경 전에 실패하고 제목 추측으로 임의 페이지를 생성·삭제하지 않음 | P0 |
| TC-NFR-DOC-012 | 수동 복구 실행 | 확인 문자열과 기준 commit을 지정해 `workflow_dispatch` 실행 | 자동 실행과 같은 검증·rollback 경로로 기준 commit 이후 변경 문서만 재동기화함 | P1 |

## 19.19 Git 협업 및 GitOps 정책 수동 테스트

| TC ID | 테스트 항목 | 테스트 절차 | 기대 결과 | 우선순위 |
| --- | --- | --- | --- | --- |
| TC-NFR-GIT-001 | 브랜치 흐름 | 기능·릴리즈·긴급 수정 PR의 base/head 확인 | `feature/*`→`dev`, `dev`→`main`, `hotfix/*`→`main` 흐름이며 hotfix는 `dev` 역반영 PR을 포함 | P0 |
| TC-NFR-GIT-002 | 보호 브랜치 | `main`, `dev`의 repository rule 확인 | direct/force push와 삭제가 금지되고 PR·필수 CI·승인이 요구됨 | P0 |
| TC-NFR-GIT-003 | 커밋·PR 형식 | PR commit과 본문 검토 | Conventional Commits 제목을 사용하고 목적·영향·테스트·배포/롤백 항목이 존재 | P1 |
| TC-NFR-GIT-004 | 릴리즈 추적 | 운영 릴리즈의 tag·image·release note 확인 | `vMAJOR.MINOR.PATCH`와 commit SHA가 immutable image 및 릴리즈 노트에 연결됨 | P0 |
| TC-NFR-GIT-005 | GitOps 승격·롤백 | dev/stg/prod overlay와 배포 이력 비교 | 동일 image tag를 재빌드 없이 승격하고 배포·롤백·drift 해소가 Git PR로 추적됨 | P0 |

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
| 1 | 내부 기준 등록 | POST `/standards` | 필수 metadata JSON과 상위 상품군·적용일이 일치하고 standardId, evidenceId 생성 |
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

## 20.5 운영 교차검증 회귀

| 검증 항목 | 입력/경합 | 기대 결과 |
| --- | --- | --- |
| 광고 상태 읽기 | `ANALYSIS_REQUESTED`, `ANALYZING`, `CHECK_REQUIRED`, `REVIEW_COMPLETED`, `REVIEW_FAILED` 광고 목록·상세 조회 | 응답 enum validation 500 없이 저장 상태 반환 |
| 멀티파트 enum | 미지원 `productGroup` 또는 `advertisementType`로 광고 등록 | 저장 전에 400 거부, 후속 목록 오염 없음 |
| refresh 단일사용 | 회전된 token replay 및 동일 token 동시 rotation | active session family 폐기 또는 한 요청만 성공하며 두 successor가 동시에 활성화되지 않음 |
| frontend 세션 복구 | refresh cookie가 있는 새로고침·보호 경로 진입, access token 401 | 시작 시 세션 복원, 401은 단 한 번 refresh 후 원 요청 재시도 |
| worker lease | stale 회수 뒤 이전 worker의 persist/retry/complete | `RUNNING`과 `locked_by` CAS가 거부하고 새 owner 상태를 변경하지 않음 |
| worker poison/idempotency | claim 이후 예상외 예외, 결과 저장 후 완료 전 재실행 | 최종 실패/dead-letter 또는 동일 checkpoint 재사용으로 무한 stale loop 없음 |
| 재색인 대상 | `targetIndexes` 부분집합 및 scope 불일치 | 요청 target만 실행하고 모순된 조합은 400 거부 |
| OCR DB 계약 | 0008→0009 upgrade 및 fresh head | 좌표 물리명·정밀도와 `idx_ocr_blocks_text_gin` 존재 |
| 화면 완결성 | 복수 추천, S-006, S-013, 2페이지 이상 목록 | 모든 추천 판단 가능, 기본정보·비교 진입·pagination 표시 |

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
