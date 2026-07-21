# 화면-API 매핑표

# 화면-API 매핑표

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.40 |
| 기준일 | 2026-07-21 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| v1.40 | 2026-07-21 | S-007 HWP/HWPX는 document-processor text/layout 좌표가 결합된 Annotation만 private SVG 원본 위 BOX로 표시하고, offset만 있는 항목은 원본 위치 미확정으로 처리하도록 정정 (API 계약 변경 없음) |
| v1.39 | 2026-07-21 | 4단계 `/reviews/{reviewId}/support` 탭의 사용자 노출 명칭을 `검토 및 리포트`로 통일 (API 계약 변경 없음) |
| v1.38 | 2026-07-21 | S-010을 4단계 결과 확인의 `/reviews/{reviewId}/results/qa` 탭으로 분리하고, 기존 요약·광고물 조회값을 Q&A 요청 범위에 자동 적용하도록 화면 매핑을 정정 (API 계약 변경 없음) |
| v1.37 | 2026-07-21 | S-006/S-008을 원본 좌측·검토 정보 우측의 넓은 작업공간으로 재배치하고 좌측 탐색 접기·반복 안내 제거를 반영 (API 계약 변경 없음) |
| v1.36 | 2026-07-20 | S-005 상태 조회의 `jobStatus`·`failedReasonCode`·`reviewStatus`로 기술 일시 오류 재시도와 OCR 판독 불가·일반 확인 필요 안내를 구분하도록 반영 (API 계약 변경 없음) |
| v1.35 | 2026-07-20 | S-003·S-014·검증 화면의 상품군 공통 코드에 대출을 추가하고, API enum과 화면 선택값을 동기화 |
| v1.34 | 2026-07-20 | 로그인 공개 화면은 API 계약 변경 없이 헤더 제외 뷰포트에 맞춘 중앙 레이아웃으로 불필요한 세로 스크롤을 제거하도록 정정 |
| v1.33 | 2026-07-20 | S-003의 취소·광고물 등록 액션을 별도 sticky 컨테이너 없이 폼 최하단의 일반 액션 행으로 배치하도록 화면 반영을 정정 (API 계약 변경 없음) |
| --- | --- | --- |
| v1.32 | 2026-07-20 | S-009는 `includeSuggestion=true` 검토 완료 시 위험 Rule 결과·연결 근거에서 생성된 추천을 표시하고, LLM 문장 보강 실패 시에도 기본 추천을 유지하도록 worker 생성 경계를 반영 |
| v1.31 | 2026-07-20 | S-009 추천 문구 목록이 비어 있을 때 항목별 검토 결과의 수정 권고로 이어지는 빈 상태를 추가 (API 계약 변경 없음) |
| v1.30 | 2026-07-20 | S-007 BOX의 normalized coordinate를 스크롤 뷰포트가 아닌 실제 원본 미디어 기준으로 변환하고, hover·선택 표현이 원문을 가리지 않도록 정정 (API 계약 변경 없음) |
| v1.29 | 2026-07-20 | HWP/HWPX 변환 SVG도 Blob 이미지로 가로폭에 맞춰 렌더링하고, 미리보기 영역의 가로 스크롤을 차단해 세로 스크롤로 원본을 확인하도록 정정 (API 계약 변경 없음) |
| v1.28 | 2026-07-20 | S-005가 GET 검토 상태의 완료 응답을 확인한 뒤 지연된 비완료 응답으로 완료 UI를 되돌리지 않도록 화면 상태 안정화 경계를 반영 (API 계약 변경 없음) |
| v1.27 | 2026-07-20 | S-007이 Annotation의 업무 파일 분류가 아닌 preview 콘텐츠 MIME 타입으로 렌더링 형식을 결정하도록 정정 (API 계약 변경 없음) |
| v1.26 | 2026-07-20 | S-005 중립 단계 카드, 원본 내부 스크롤, S-008 문구 우선 칩·표 상세 및 Annotation 좌표 기반 원본 위치 이동을 반영 (API 계약 변경 없음) |
| v1.25 | 2026-07-20 | S-006 기본정보 표·간결한 원본 병행 패널·중립 최종 판단 안내 표시를 반영 (API 계약 변경 없음) |
| v1.24 | 2026-07-20 | ADR-0078의 test/admin PoC 계정 프로필을 반영 (API 역할 계약 변경 없음) |
| v1.23 | 2026-07-20 | 역할 기반 접근 제한 화면의 중립 테두리 표시를 반영 (API 계약 변경 없음) |
| v1.22 | 2026-07-20 | S-014의 개별 검색 데이터 갱신은 신규·개정 자료 확인 및 단건 색인 실패 복구용이며, 공통 검색 설정 변경은 별도 전체 일괄 갱신 범위임을 화면 안내에 반영 (API 계약 변경 없음) |
| v1.21 | 2026-07-20 | S-014에서 청크 확인, 검색 데이터 갱신, 검토 적용 중지를 사용자용 명칭으로 구분하고 검색 갱신과 적용 중지가 서로 독립된 API 동작임을 명시 (API 계약 변경 없음) |
| v1.20 | 2026-07-20 | API 호출 없이 렌더링 실패를 처리하는 전용 오류 경계 화면의 중립 중앙 안내·뷰포트 높이 경계를 반영 |
| v1.19 | 2026-07-20 | API 계약 변경 없이 접근 거부 상태의 중립 표시, 데스크톱 고정 탐색 및 검증 제외 선택의 화면 안내 경계를 동기화 |
| v1.18 | 2026-07-20 | API 계약은 유지하고 S-012/S-014/S-015/S-016의 화면 기본 출력에서 기술 식별자·해시·원시 enum을 제거하여 일반 업무 용어로 표시하는 경계를 반영 |
| v1.17 | 2026-07-18 | S-014 규정·가이드라인 등록 화면의 적용 범위·문서 정보·검토 본문 흐름과 검색 반영의 사용자용 상태명을 반영 (API 계약 변경 없음) |
| v1.16 | 2026-07-18 | 광고물 상세의 기존 검토 이력 조회·진행/결과 복귀와 핵심 화면 공통 업무 단계·결과 하위 탐색 표시를 반영 |
| v1.15 | 2026-07-18 | 로그인 카드의 정적 NH농협은행 로고를 제거하고 인증 후 공통 헤더에만 유지하도록 화면 표시 경계를 정정 |
| v1.14 | 2026-07-18 | S-004~S-008 원본 자동 미리보기와 Worker 단계별 진행률·화면 이탈 후 서버 작업 지속 경계를 반영 |
| v1.13 | 2026-07-17 | 로그인·공통 헤더의 NH농협은행 로고 표시와 대체 텍스트는 API 호출 없이 정적 자산으로 제공함을 명시 |
| v1.12 | 2026-07-17 | HWP/HWPX private SVG 미리보기 호출, 실패 코드 및 Text IR 병행 표시를 반영 |
| v1.11 | 2026-07-16 | S-004 로컬 오늘 기준일 기본값, S-005 완료 단계 정합성, S-007 HWP/HWPX preview 비호출과 Text IR 안내를 반영 |
| --- | --- | --- |
| v1.10 | 2026-07-16 | 로그인 UI에서 내부 마일스톤 표기를 제거하고 사용자용 제목만 유지하는 화면 반영 기준을 추가 |
| v1.9 | 2026-07-16 | 앱 시작·401 refresh 복구, collection pagination, S-006 광고 상세 병합과 S-013 prefill, 복수 suggestion 판단 호출을 화면 흐름에 동기화 |
| v1.8 | 2026-07-15 | OpenAPI v0.7.0의 정확히 다섯 Validation operation으로 S-015 데이터셋/판단과 S-016 불변 KPI 실행/조회를 연결하고 권한·평가 제외·분모 0 미적용 표시 경계를 동기화 |
| v1.7 | 2026-07-15 | OpenAPI v0.6.0 S-009~S-013 생성 client route, 문구 판단 검증, 비단정 Q&A, 초안 이력, 불변 HWPX/PDF snapshot과 구조 비교 화면 상태 동기화 |
| v1.6 | 2026-07-14 | OpenAPI v0.5.0 S-006~S-008 결과 요약·상세·Annotation 생성 client route와 preview/필터/부분 실패·권한 화면 상태 동기화 |
| v1.5 | 2026-07-14 | OpenAPI v0.4.0 S-004/S-005 요청·진행·retry/stale/final failure·quality warning·재분석·권한/redaction client 흐름 동기화 |
| v1.4 | 2026-07-14 | S-014 내부 기준 등록의 필수 metadata JSON, 상위 필드 정합성 및 `REFERENCE_METADATA_INVALID` 안전 표시 경계 반영 |
| v1.3 | 2026-07-14 | S-014 생성 client 연동, 역할별 route gate, 직접 입력 등록·불변 version·Hybrid 503·Chunk redaction의 화면 상태를 실행 흐름과 동기화 |
| v1.2 | 2026-07-14 | S-014 기준자료 단건/이력/reindex/chunk 계약 확정, 관리자 상태·오류·내부 인덱스 식별자 redaction 경계 반영 |
| v1.1 | 2026-07-14 | M2 로그인·광고물 목록·등록·기본 상세의 실제 API 호출, 상태, 권한 및 계약 생성 타입 사용 기준 반영 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, 화면/API 호출 정합성 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 화면-API 매핑표 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 문서 버전 | v1.7 |
| 작성 목적 | 화면별 호출 API, 호출 시점, 요청값, 응답값, 화면 반영 항목을 정의 |
| 기준 문서 | 화면설계서 v0.1, API 명세서 v0.1 |
| API Base URL | `/api/v1` |

---

# 1. 작성 기준

## 1.1 매핑 기준

본 문서는 화면별로 다음 기준에 따라 API를 매핑한다.

| 구분 | 설명 |
| --- | --- |
| 화면 ID | 화면설계서의 화면 ID |
| 화면명 | 사용자에게 표시되는 화면명 |
| 호출 시점 | 화면 진입, 조회 버튼 클릭, 저장 버튼 클릭, 행 선택 등 |
| API | 호출할 API Endpoint |
| Method | HTTP Method |
| 주요 요청값 | Path Variable, Query Parameter, Request Body, Form Data |
| 주요 응답값 | 화면에 표시하거나 후속 처리에 사용하는 값 |
| 화면 반영 | 응답 데이터를 화면 어디에 표시하는지 |
| 비고 | 추가 개발 필요 API, 권한, 예외 사항 |

---

## 1.2 공통 호출 API

여러 화면에서 공통으로 사용할 가능성이 높은 API는 다음과 같다.

| 구분 | API | Method | 설명 | 비고 |
| --- | --- | --- | --- | --- |
| 로그인 | `/auth/login` | POST | access token과 사용자 context 수신 | `credentials: include`, `refreshToken` httpOnly cookie는 브라우저가 관리. UI는 `로그인`만 표시하며 내부 마일스톤 명칭과 NH농협은행 로고를 노출하지 않는다. 로고는 인증 후 공통 헤더에서 API 없이 정적 자산과 대체 텍스트로 제공한다. |
| 로그아웃 | `/auth/logout` | POST | refresh session revoke와 cookie 삭제 | 화면은 성공/실패와 무관하게 메모리 access token 제거 |
| 사용자 정보 | `/users/me` | GET | 로그인 사용자 정보 조회 | API 명세서 정의됨 |
| 공통 코드 | `/codes/product-groups` | GET | 상품군 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/advertisement-types` | GET | 광고유형 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/review-types` | GET | 검토유형 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/risk-levels` | GET | 위험도 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/review-statuses` | GET | 검토 상태 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 파일 미리보기 descriptor | `/files/{fileId}/preview` | GET | 권한 검증 후 backend 상대 미리보기 경로와 페이지 메타데이터 조회 | API 명세서 정의됨 |
| 파일 미리보기 content | `/files/{fileId}/preview/content` | GET | `pageNo`의 렌더링 이미지를 Bearer 인증 backend proxy로 조회 | API 명세서 정의됨 |
| 파일 다운로드 | `/files/{fileId}/download` | GET | 첨부파일을 Bearer 인증 backend proxy로 다운로드 | API 명세서 정의됨 |

---

# 2. 화면별 API 매핑 요약

| 화면 ID | 화면명 | 주요 API |
| --- | --- | --- |
| S-001 | 메인 대시보드 | 대시보드 요약 조회, 최근 광고물 조회 |
| S-002 | 광고물 목록 | 광고물 목록 조회 |
| S-003 | 광고물 등록 | 광고물 등록, 광고물 수정 |
| S-004 | AI 검토 요청 | 광고물 상세 조회, AI 검토 요청 |
| S-005 | 검토 진행 상태 | AI 검토 진행 상태 조회, 재분석 요청 |
| S-006 | 검토 결과 요약 | 검토 요약 조회, 상세 항목 조회 |
| S-007 | 광고 화면 검토 UI | 파일 미리보기, Annotation 조회, 검토 항목 상세 조회 |
| S-008 | 상세 검토 결과 | 검토 항목 목록 조회, 검토 항목 상세 조회 |
| S-009 | 문구 추천 | 문구 추천 조회, 채택 여부 저장 |
| S-010 | 광고 규정 Q&A | 질의응답 요청, Q&A 이력 조회 |
| S-011 | 심의 의견 초안 | 초안 생성, 초안 수정 |
| S-012 | 검토 리포트 | 리포트 생성, 리포트 조회, 다운로드 |
| S-013 | 수정 전후 비교 | 수정본 등록, 비교 요청, 비교 결과 조회 |
| S-014 | 기준자료 관리 | 기준자료 목록 조회, 등록, 수정, 비활성화 |
| S-015 | 검토 품질 관리 | 검증 데이터 조회, 등록, 담당자 판단 등록 |
| S-016 | 검증 결과 평가 | 성능 평가 실행, 평가 결과 조회 |
| S-017 | 사용자/권한 관리 | 사용자 목록 조회, 권한 변경, 감사 로그 조회 |

---

# 3. 상세 화면-API 매핑

---

## S-001 메인 대시보드

### 3.1 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-001 |
| 화면명 | 메인 대시보드 |
| 화면 목적 | 광고물 검토 현황, 최근 광고물, 주요 리스크 현황을 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자, 관리자 |

---

### 3.2 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 대시보드 요약 조회 | `/dashboard/summary` | GET | `fromDate`, `toDate`, `departmentId` | 전체 광고물 수, 검토 대기, 분석 중, 검토 완료, 확인 필요 건수 | 검토 현황 요약 영역 |
| 화면 진입 | 위험도 현황 조회 | `/dashboard/risk-summary` | GET | `fromDate`, `toDate`, `departmentId` | 위험도 높음/중간/낮음/확인 필요 건수 | 주요 리스크 현황 영역 |
| 화면 진입 | 최근 광고물 조회 | `/advertisements` | GET | `page=1`, `size=5`, `sort=createdAt,desc` | 최근 광고물 목록 | 최근 등록 광고물 영역 |
| 광고물 등록 클릭 | 화면 이동 | - | - | - | - | S-003 이동 |
| 광고물 목록 클릭 | 화면 이동 | - | - | - | - | S-002 이동 |

### 3.3 추가 필요 API

| API | 사유 |
| --- | --- |
| `/dashboard/summary` | 현재 API 명세서에 없음. 대시보드용 집계 API 필요 |
| `/dashboard/risk-summary` | 위험도 집계 전용 API 필요 |

---

## S-002 광고물 목록

### 3.4 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-002 |
| 화면명 | 광고물 목록 |
| 화면 목적 | 등록된 광고물과 AI 검토 상태 조회 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.5 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 목록 기본 조회 | `/advertisements` | GET | `page`, `size` | 광고물 목록, 페이지 정보 | 목록 영역 |
| 조회 버튼 클릭 | 조건 검색 | `/advertisements` | GET | `keyword`, `productGroup`, `advertisementType`, `reviewStatus`, `riskLevel`, `fromDate`, `toDate`, `page`, `size` | 조건에 맞는 광고물 목록 | 목록 영역 |
| 목록 행 클릭 | 광고물 상세 이동 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 광고물 상세정보 | S-006 또는 상세 화면 이동 전 데이터 |
| AI 검토 요청 클릭 | 검토 요청 화면 이동 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 광고물 기본정보, 파일정보 | S-004 이동 |
| 리포트 보기 클릭 | 리포트 상세 조회 | `/reports/{reportId}` | GET | `reportId` | 리포트 메타데이터, 다운로드 URL | S-012 이동 |

M2 1차 화면은 OpenAPI v0.2.0 `AdvertisementPage`에 잠긴 광고물 ID·광고명·상품군·광고유형·담당부서·등록자·등록일시·검토 상태만 표시한다. 종합 위험도와 리포트 action은 해당 후속 capability 계약이 잠기기 전에는 요청하거나 임시 필드로 합성하지 않는다. 목록 loading/empty/error와 역할 거부를 각각 표시하며, 오류는 code 매핑 문구와 `traceId`만 노출한다.

### 3.5.1 M2 기본 상세 상태

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 목록 ID 클릭 | M2 광고물 기본 상세 | `/advertisements/{advertisementId}` | GET | `advertisementId` | `AdvertisementDetail`, 안전한 `AdvertisementFile` 메타데이터 | `/advertisements/{advertisementId}` 기본정보·파일 목록 |
| 광고물 상세 진입 | 기존 검토 이력 조회 | `/advertisements/{advertisementId}/reviews` | GET | `advertisementId` | `ReviewHistory[]`: 회차, 검토 상태, 위험도, 요청·완료일 | 최근 검토를 우선 표시하고 진행 중이면 S-005, 완료·확인 필요이면 S-006 복귀 링크 제공 |
| 단건 권한 거부 | 부서 scope 거부 | `/advertisements/{advertisementId}` | GET | 타 부서 `advertisementId` | 403 `ErrorResponse` | 전용 권한 안내. raw message, object key, presigned URL 미표시 |
| 파일 미리보기 클릭 | 미리보기 descriptor 조회 | `/files/{fileId}/preview` | GET | `fileId`, `pageNo=1` | `FilePreview`, backend 상대 `previewPath` | 안전한 content 경로 검증 후 다음 호출 |
| descriptor 검증 후 | 렌더링 이미지 조회 | `/files/{fileId}/preview/content` | GET | `fileId`, `pageNo` | `image/png`/`image/jpeg`/`application/pdf` 또는 HWP/HWPX 변환 `image/svg+xml` binary | object URL로 화면 미리보기. HWP/HWPX SVG는 이미지처럼 가로폭에 맞춰 렌더링하고 가로 스크롤 없이 세로 스크롤로 확인한다. Bearer 인증 유지 |
| 파일 다운로드 클릭 | 원본 파일 proxy 다운로드 | `/files/{fileId}/download` | GET | `fileId` | binary, `Content-Disposition` | 파일명으로 저장. Bearer 인증 유지 |
| 파일 권한 거부 | 부서 scope 거부 | 위 파일 API | GET | 타 부서 `fileId` | 403 `ErrorResponse` | 미리보기/다운로드 전용 권한 안내. raw message, bucket, object key 미표시 |

---

## S-003 광고물 등록

### 3.6 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-003 |
| 화면명 | 광고물 등록 |
| 화면 목적 | AI 검토 대상 광고물과 관련 파일 등록 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.7 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 상품군 코드 조회 | `/codes/product-groups` | GET | 없음 | 상품군 코드 목록 | 상품군 선택값 |
| 화면 진입 | 광고유형 코드 조회 | `/codes/advertisement-types` | GET | 없음 | 광고유형 코드 목록 | 광고유형 선택값 |
| 저장 버튼 클릭 | 광고물 등록 | `/advertisements` | POST | `multipart/form-data`: 광고명, 상품군, 광고유형, 광고채널, 담당부서, 광고파일, 상품설명서, 약관, 추가 첨부파일(최대 10개) | `advertisementId`, `reviewStatus`, 파일 정보 | 저장 완료 메시지, S-002 또는 S-004 이동 |
| AI 검토 요청 클릭 | 광고물 등록 후 검토 요청 화면 이동 | `/advertisements` → `/advertisements/{advertisementId}` | POST → GET | 등록 Form Data | 광고물 ID, 상세정보 | S-004 이동 |
| 수정 모드 저장 | 광고물 기본정보 수정 | `/advertisements/{advertisementId}` | PATCH | 광고명, 상품군, 광고유형, 메모 | 수정일시 | 수정 완료 메시지 |

M2 1차 등록은 OpenAPI v0.2.0 생성 타입을 client 경계에서 사용한다. 공통 코드 loading/error, 필수값, 광고 파일·상품설명서·약관·추가 첨부파일 각각의 허용 확장자·50 MiB 선검증과 추가 첨부파일 최대 10개 제한, 역할별 등록 action을 처리한다. `multipart/form-data`의 `Content-Type` boundary는 브라우저가 설정한다. 성공 시 응답 `advertisementId`의 기본 상세로 이동하며, 서버 오류의 raw `message`/`details`에 포함될 수 있는 내부 경로나 민감 원문은 화면에 직접 표시하지 않는다.

---

## S-004 AI 검토 요청

### 3.8 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-004 |
| 화면명 | AI 검토 요청 |
| 화면 목적 | 광고물에 적용할 검토 항목 선택 및 AI 분석 요청 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.9 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회·원본 자동 미리보기 | `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `advertisementId`, `fileId`, `pageNo` | 광고명, 상품군, 광고유형, 파일 목록·private preview | 입력 영역과 원본 병행 패널 |
| 화면 진입 | 검토유형 코드 조회 | `/codes/review-types` | GET | 없음 | 검토유형 코드 목록 | 검토 항목 선택 영역 |
| 분석 요청 클릭 | AI 검토 요청 | `/advertisements/{advertisementId}/reviews` | POST | `CreateReviewRequest`: `standardEffectiveDate`(사용자 로컬 오늘 날짜 기본값, 변경 가능), `reviewTypes`, `includeSuggestion`, `includeOpinionDraft`, `requestMemo` | `ReviewAccepted`: `reviewId`, `jobId`, `reviewStatus`, `standardVersionIds`, `requestedAt` | 응답 `reviewId`로 S-005 이동 |
| 이전 클릭 | 화면 이동 | - | - | - | - | S-002 이동 |

---

## S-005 검토 진행 상태

### 3.10 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-005 |
| 화면명 | 검토 진행 상태 |
| 화면 목적 | AI 분석 진행 상태 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.11 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입/비 terminal 자동 갱신 | 검토 진행 상태·원본 병행 표시 | `/reviews/{reviewId}/status` → `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `reviewId`, `advertisementId`, `fileId`, `pageNo` | `ReviewProgress`: `currentStep`, `progressRate`, `steps`, `jobStatus`, `failedReasonCode`, `reviewStatus` 및 파일 preview | Worker가 영속한 단계별 진행률과 원본을 함께 표시한다. `RETRY_PENDING`은 기술 일시 오류의 자동 재시도, `OCR_UNREADABLE`은 원본 품질 확인, 그 외 `CHECK_REQUIRED`은 검토 근거·조건 확인으로 구분해 안내한다. 화면 이탈은 서버 작업을 중단하지 않고 재진입 시 최신 상태를 조회한다. `COMPLETED` Job은 모든 정의된 step을 완료로 표시 |
| 새로고침 클릭 | 상태 갱신 | `/reviews/{reviewId}/status` | GET | `reviewId` | 최신 `ReviewProgress` | 진행률 및 단계 갱신. terminal 상태에서는 자동 갱신 중지 |
| 결과 보기 클릭 | 검토 결과 요약 이동 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 검토 요약 | S-006 이동 |
| `isRetryable=true` 실패/stale에서 재분석 클릭 | AI 재분석 요청 | `/reviews/{reviewId}/rerun` | POST | `RerunReviewRequest`: `reason`, `reviewTypes` | `RerunReviewAccepted`: `newReviewId`, `previousReviewId`, `jobId`, `reviewStatus` | 이력을 덮어쓰지 않고 `newReviewId`의 S-005 표시 |
| 타 부서·권한 부족 | 상태/재분석 거부 | 위 API | GET/POST | Bearer 인증, `reviewId` | 403 일반화 응답 | 전용 권한 없음 상태. raw artifact/object key/presigned URL 미표시 |

---

## S-006 검토 결과 요약

### 3.12 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-006 |
| 화면명 | 검토 결과 요약 |
| 화면 목적 | AI 검토 결과의 종합 위험도와 주요 리스크 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.13 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회·원본 자동 미리보기 | `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `advertisementId`, `fileId`, `pageNo` | 광고 기본정보, 파일정보·private preview | 데스크톱 좌측의 넓은 원본 패널과 우측 광고 기본정보 표. 구현 방식 설명은 표시하지 않음 |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 종합 위험도, 문제 건수, 검토유형별 요약, 주요 리스크 | 검토 요약 영역 |
| 주요 리스크 클릭 | 검토 항목 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 판단 사유, 근거, 추천 문구, ADR-0066 기준 Coordinate | 상세 팝업 또는 S-008 이동 |
| 광고 화면 보기 클릭 | Annotation 조회 | `/reviews/{reviewId}/annotations` | GET | `reviewId`, `pageNo` | Annotation 표시 모드, 위치 상태, Coordinate/텍스트 위치 | S-007 이동 |
| 상세 결과 보기 클릭 | 상세 목록 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 상세 검토 항목 목록 | S-008 이동 |
| 문구 추천 보기 클릭 | 문구 추천 조회 | `/reviews/{reviewId}/suggestions` | GET | `reviewId` | 추천 문구 목록 | S-009 이동 |
| 리포트 생성 클릭 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST | 리포트 옵션 | `reportId`, `reportStatus` | S-012 이동 |

---

## S-007 광고 화면 검토 UI

### 3.14 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-007 |
| 화면명 | 광고 화면 검토 UI |
| 화면 목적 | 광고 원본 위에 문제 영역, 위험도, 근거를 시각적으로 표시 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.15 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 파일 ID, 광고 기본정보 | 상단 정보 영역 |
| 화면 진입 | 광고 파일 미리보기 | `/files/{fileId}/preview` | GET | `fileId`, `pageNo` | 렌더링 이미지 또는 preview URL | 이미지/PDF/HWP/HWPX 모두 광고 원본 미리보기 영역에 호출. HWP/HWPX는 private 변환 SVG를 반환 |
| 화면 진입 | Annotation 조회 | `/reviews/{reviewId}/annotations` | GET | `reviewId`, `pageNo`, `reviewType` | 표시 모드, 위치 상태, Coordinate/텍스트 위치, 위험도, 검토유형 | 파일 형식별 Annotation 표시. HWP/HWPX는 구조 좌표가 있는 항목만 SVG 원본 위 BOX로 표시하며, offset만 있는 항목은 원본 위치 미확정 목록으로 표시 |
| Annotation 또는 목록 항목 클릭 | 검토 항목 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 원문, 문제유형, 판단사유, 근거, 추천문구 | 선택 항목 상세 패널 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 기준명, 조항, 내용, 적용일 | 근거 상세 팝업 |
| 필터 선택 | Annotation 필터링 | `/reviews/{reviewId}/annotations` | GET | `reviewType`, `riskLevel`, `pageNo` | 필터링된 Annotation 목록 | 화면 표시 갱신 |

### 3.16 추가 필요 API

| API | 사유 |
| --- | --- |
| `/files/{fileId}/preview` | 광고 원본 이미지/PDF 렌더링 표시 필요 |
| `/files/{fileId}/pages` | 다중 페이지 광고물의 페이지 수 조회 필요 시 추가 |

---

## S-008 상세 검토 결과

### 3.17 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-008 |
| 화면명 | 상세 검토 결과 |
| 화면 목적 | 항목별 검토 결과, 판단 사유, 근거, 추천 문구 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.18 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 상세 검토 결과 목록 조회 | `/reviews/{reviewId}/items` | GET | `reviewType`, `riskLevel`, `resultStatus`, `page`, `size` | 검토 항목 목록 | 목록 영역 |
| 조회/필터 클릭 | 상세 결과 조건 조회 | `/reviews/{reviewId}/items` | GET | 필터 조건 | 필터링된 검토 항목 목록 | 목록 영역 갱신 |
| 행 클릭 | 검토 항목 상세 조회·원본 위치 이동 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 상세 판단 사유, ADR-0043 기준 핵심 근거 최대 3개, 추천 문구, Coordinate | 문구 우선 상세 패널을 표로 표시하고 Coordinate가 있으면 같은 화면의 원본 미리보기를 해당 위치로 스크롤 |
| 광고 화면에서 보기 클릭 | Annotation 위치 이동 | `/reviews/{reviewId}/annotations` | GET | `reviewItemId` 또는 `pageNo` | 표시 모드, 위치 상태, Coordinate/텍스트 위치 | S-007 이동 후 Coordinate가 있으면 원본 캔버스를 해당 위치로 스크롤 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 근거 상세정보 | 근거 팝업 |

### 3.18.1 M5 생성 client 실행 매핑

| 화면/route | 생성 operation | 실행 상태 및 화면 반영 |
| --- | --- | --- |
| S-006 `/reviews/{reviewId}/results` | `getReviewSummary` | 종합 위험도·집계·주요 리스크를 표시하고 `EvidenceStatus`의 검색 장애와 업무적 근거 부족을 서로 다른 안내로 표시한다. |
| S-008 `/reviews/{reviewId}/results/items` | `listReviewItems`, `getReviewItem` | `reviewType`, `riskLevel`, `resultStatus` query를 생성 타입으로 전달한다. 문구를 우선 표시하고 검토 유형·판정·위험도는 칩으로 보조하며, 상세의 판단 방식·수정 권고·근거 상태는 표로 표시한다. Coordinate가 있으면 원본 미리보기의 해당 위치로 이동한다. |
| S-007 `/reviews/{reviewId}/results/annotations` | `listReviewAnnotations` | `pageNo`, `reviewType`, `riskLevel` query와 BOX/TEXT_HIGHLIGHT/LIST_ONLY/UNAVAILABLE 표시 모드를 소비하며, 위치 신뢰도 확인 목록을 유지한다. |
| S-007 원본 미리보기 | `getFilePreview` 후 `/files/{fileId}/preview/content` | Bearer 인증으로 descriptor의 동일 origin content만 Blob URL로 표시한다. Annotation의 `fileType`은 업무상 분류이므로 렌더링 형식 판정에 사용하지 않고 preview 콘텐츠 MIME 타입을 사용한다. 이미지와 HWP/HWPX 변환 SVG는 가로폭에 맞춰 표시한다. 이미지/PDF BOX는 정규화 좌표를 실제 렌더링 원본 미디어의 폭·높이로 변환하며, HWP/HWPX는 private 변환 SVG와 offset 하이라이트를 함께 사용한다. |
| 공통 | 위 네 M5 operation | loading/empty/error/403을 전용 상태로 표시하고 서버 원문, raw artifact/object key/presigned URL은 렌더링하지 않는다. |

---

## S-009 문구 추천

### 3.19 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-009 |
| 화면명 | 문구 추천 |
| 화면 목적 | 위험 표현에 대한 대체 문구와 담당자 채택 여부 관리 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.20 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 문구 추천 목록 조회 | `/reviews/{reviewId}/suggestions` | GET | `reviewId` | 원문, 추천 문구, 추천 사유, 근거 ID, 채택 상태 | `includeSuggestion=true`인 검토는 완료 worker가 위험 Rule 결과와 연결 근거로 생성한 추천을 표시한다. LLM 문장 보강은 선택적이며 실패 시 Rule 기본 추천을 유지한다. 빈 배열이면 빈 상태와 S-008 이동을 표시 |
| 추천 항목 클릭 | 관련 검토 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewItemId` | 판단 사유, 위험도, 근거 | 문제 분석 영역 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 근거 상세정보 | 근거 팝업 |
| 채택/미채택/수정 후 저장 클릭 | 문구 추천 판단 저장 | `/suggestions/{suggestionId}/decision` | PATCH | `decisionStatus`, `finalText`, `comment`. `MODIFIED_AND_USED`는 `finalText` 필수 | 저장 결과, 수정일시, 최종 사용 문구 | 채택 상태 갱신 |

---

## S-010 광고 규정 Q&A

### 3.21 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-010 |
| 화면명 | 광고 규정 Q&A |
| 화면 목적 | 광고 규정 관련 질문에 대한 RAG 기반 답변 제공 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.22 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 현재 검토 요약·광고물 조회 | `/reviews/{reviewId}/summary` → `/advertisements/{advertisementId}` | GET | `reviewId`, `advertisementId` | 기준 적용일, 상품군, 광고유형 | 별도 탭의 질문 범위로 자동 적용하고 현재 검토 기준으로 표시 |
| 질문하기 클릭 | 광고 규정 질의응답 요청 | `/qa/questions` | POST | `question`, `productGroup`, `advertisementType`, `standardEffectiveDate` | 답변 요약, 상세 설명, 근거, 추천 문구, 담당자 검토 필요 여부 | 답변 영역 |
| 결과 요약/검토 및 리포트 탭 이동 | 화면 전환 | - | - | `reviewId` | - | Q&A 요청·응답은 화면 상태로 유지하고 결과 확인의 공통 탭 간에 이동 |

---

## S-011 심의 의견 초안

### 3.24 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-011 |
| 화면명 | 심의 의견 초안 |
| 화면 목적 | AI 검토 결과 기반 심의 의견 초안 생성 및 수정 |
| 주요 사용자 | 준법감시 담당자 |

---

### 3.25 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 주요 리스크, 문제 건수 | 광고 기본정보/요약 영역 |
| 화면 진입 | 상세 검토 항목 조회 | `/reviews/{reviewId}/items` | GET | `reviewId`, `riskLevel`, `resultStatus` | 검토 항목 목록 | 초안 포함 항목 선택 |
| 초안 생성 클릭 | 심의 의견 초안 생성 | `/reviews/{reviewId}/opinion-drafts` | POST | `includeReviewItemIds`, `templateType`, `additionalInstruction` | `draftId`, `draftContent`, 포함 항목 | AI 생성 초안 영역 |
| 저장 클릭 | 심의 의견 초안 수정 | `/opinion-drafts/{draftId}` | PATCH | `finalContent` | 수정 결과, 수정일시 | 담당자 수정 영역 저장 |
| 기존 초안 조회 | 초안 목록 조회 | `/reviews/{reviewId}/opinion-drafts` | GET | `reviewId` | 초안 목록 또는 최신 초안 | 초안 목록 영역 |

### 3.26 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /opinion-drafts/{draftId}` | 초안 단건 상세 조회 필요 |

---

## S-012 검토 리포트

### 3.27 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-012 |
| 화면명 | 검토 리포트 |
| 화면 목적 | 광고물별 검토 결과 리포트 생성, 미리보기, 다운로드 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.28 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 검토 요약 | 리포트 미리보기 기본 정보 |
| 화면 진입 | 상세 항목 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 상세 검토 항목 목록, ADR-0043 기준 핵심 근거 1~3개 | 리포트 상세 항목 |
| 리포트 생성 클릭 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST | `reportType`, `format=HWPX/PDF`, `includeAnnotations`, `includeSuggestions`, `includeOpinionDraft`, `includeEvidenceDetails` | `reportId`, `reportStatus` | 생성 완료 메시지 |
| 미리보기 클릭 | 리포트 상세 조회 | `/reports/{reportId}` | GET | `reportId` | 리포트 메타데이터, 다운로드 URL | 미리보기 영역 |
| 다운로드 클릭 | 리포트 다운로드 | `/reports/{reportId}/download` | GET | `reportId` | Binary File | 파일 다운로드 |
| 인쇄 클릭 | 프론트 처리 | - | - | - | - | 브라우저 인쇄 또는 파일 인쇄 |

---

## S-013 수정 전후 비교

### 3.29 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-013 |
| 화면명 | 수정 전후 비교 |
| 화면 목적 | 최초 광고안과 수정 광고안의 차이 및 지적사항 해결 여부 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.30 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 기존 광고물 상세 조회 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 원본 광고물 정보, 파일정보 | 원본 정보 영역 |
| 화면 진입 | 기존 검토 결과 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 기존 지적사항 목록 | 수정 전 영역 |
| 수정본 업로드 클릭 | 수정본 등록 | `/advertisements/{advertisementId}/revisions` | POST | `multipart/form-data`: `revisionMemo`, `revisedAdvertisementFile` | `revisionId`, `reviewStatus` | 수정본 등록 완료 |
| 비교 실행 클릭 | 수정 전후 비교 요청 | `/advertisements/{advertisementId}/comparisons` | POST | `baseReviewId`, `revisionId`, `compareTypes` | `comparisonId`, 해결/미해결/신규 건수 | 비교 결과 요약 |
| 비교 결과 조회 | 비교 상세 조회 | `/comparisons/{comparisonId}` | GET | `comparisonId` | 변경 문구, 해결 여부, 신규 리스크 | 비교 상세 영역 |
| 재분석 요청 클릭 | AI 재분석 요청 | `/reviews/{reviewId}/rerun` | POST | `reason`, `reviewTypes` | `newReviewId` | S-005 이동 |

### 3.30.1 M6 생성 client 실행 매핑

| 화면/route | 생성 operation | 실행 상태 및 화면 반영 |
| --- | --- | --- |
| S-009 `/reviews/{reviewId}/support` | `listReviewSuggestions`, `recordSuggestionDecision` | 추천 문구를 조회하고 `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED`를 저장한다. `MODIFIED_AND_USED`는 요청 전 `finalText`를 필수 검증하며 저장 후 목록을 다시 조회한다. |
| S-010 `/reviews/{reviewId}/results/qa` | `getReviewSummary`, `getAdvertisement`, `askComplianceQuestion` | 현재 검토의 상품군·광고유형·기준 적용일을 질문 범위에 자동 적용한다. 질문 결과의 답변 요약·상세·고정 근거·참고 문구를 표시하며, 근거가 없고 `needsHumanReview=true`이면 확정 답변 대신 담당자 확인 안내와 빈 근거 상태를 표시한다. |
| S-011 `/reviews/{reviewId}/support` | `listOpinionDrafts`, `createOpinionDraft`, `updateOpinionDraft` | 최신 초안을 조회하고 없으면 생성한다. 원본 `draftContent`를 유지한 채 담당자 `finalContent`를 저장하고 다시 조회한다. |
| S-012 `/reviews/{reviewId}/support` | `createReviewReport`, `getReviewReport`, `downloadReviewReport` | HWPX/PDF 리포트의 생성 형식·준비 상태와 다운로드를 표시한다. 응답의 식별자·해시는 클라이언트 동작에만 사용하고 기본 화면에는 표시하지 않는다. 다운로드는 Bearer 권한을 확인하며 변환 실패는 원본 HWPX와 분리한다. |
| S-013 `/advertisements/{advertisementId}/comparisons` | `createAdvertisementComparison`, `getAdvertisementComparison` | 기존 검토에서 진입해 수정본을 비교하고 해결·미해결·신규 확인 건수와 항목을 표시한다. 비교 API의 식별자는 요청에만 사용하며 기본 화면에는 노출하지 않는다. |
| 공통 | 위 M6 operation | loading/error/403을 공통 상태로 표시하고 지원 산출물은 자동 확정하지 않는다. 화면은 내부 snapshot 원문, 감사 메타데이터, 저장소 경로를 노출하지 않는다. |

---

## S-014 기준자료 관리

### 3.31 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-014 |
| 화면명 | 검토 기준자료 관리 |
| 화면 목적 | 규정·가이드라인·내부 기준 등록 및 광고 검토 근거 관리 |
| 주요 사용자 | 기준 관리자, 시스템 관리자 |

---

### 3.32 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 기준자료 목록 조회 | `/standards` | GET | `page`, `size`, `activeOnly` | 기준자료 목록 | 목록 영역 |
| 조회 클릭 | 기준자료 조건 검색 | `/standards` | GET | `keyword`, `evidenceType`, `productGroup`, `advertisementType`, `ruleType`, `activeOnly` | 조건에 맞는 기준자료 목록 | 목록 영역 |
| 기준자료 등록 클릭 | 규정·가이드라인·내부 기준 등록 | `/standards` | POST | `multipart/form-data`: 기준명, `INTERNAL_STANDARD`, 상품군, 광고유형, 기준성격, 중요도, 적용일, 직접 입력 내용, 선택 원문 파일 및 `metadata` JSON(`owningDepartment`, `documentName`, `sectionPath`, `effectiveDate`, `version`, `productGroup`, `inputBoundary`) | `standardId`, `evidenceId`, `version` | 등록 완료 후 목록 갱신. `metadata.productGroup`/`effectiveDate`는 상위 multipart 필드와 같은 값 유지 |
| 행 클릭 | 기준자료 단건 조회 | `/standards/{standardId}` | GET | `standardId` | master와 현재 불변 version 상세 | 상세 영역 |
| 수정 클릭 | 기준자료 수정 | `/standards/{standardId}` | PATCH | 기준명, 내용, 적용일, 변경 사유 | 수정 결과 | 상세 영역 갱신 |
| 검토 적용 중지 클릭 | 기준자료 검토 적용 중지 | `/standards/{standardId}/deactivate` | PATCH | `reason` | 미적용 상태 | 기준자료와 이력은 유지하고 광고 검토·근거 검색 대상에서 제외 |
| 이력 보기 클릭 | 기준자료 변경 이력 조회 | `/standards/{standardId}/histories` | GET | `standardId` | 불변 version 변경 이력 목록 | 이력 패널 |
| 검색 데이터 갱신 클릭 | 선택한 기준자료 버전의 검색 데이터 갱신 요청 | `/standards/{standardId}/versions/{standardVersionId}/reindex` | POST | `reindexScope`, `reason`, model/version 정보 | `jobId`, `jobStatus` | 신규·개정 자료 확인 또는 단건 색인 실패 복구에 사용. 공통 모델·스키마 변경은 전체 일괄 갱신 범위 |
| 검색 데이터 갱신 상태 확인 | 기준자료 검색 데이터 갱신 상태 조회 | `/standard-reindex-jobs/{jobId}` | GET | `jobId` | 상태, 처리 건수, 실패 사유 | 상태 배지/오류 표시 |
| 청크 확인 클릭 | 기준자료 청크 목록 조회 | `/evidences/{evidenceId}/chunks` | GET | `evidenceId`, `page`, `size` | 내부 index/point/doc ID가 제거된 청크 내용·version·상태 | 관리자 보조 화면 |

### 3.33 확정 계약 경계

| API | 확정 기준 |
| --- | --- |
| `/standards/{standardId}/histories` | 불변 version 이력 조회 계약으로 사용 |
| `/standards/{standardId}` | master와 현재 version 단건 조회 계약으로 사용 |

### 3.34 화면 상태 및 권한 매핑

| 경계 | 화면 처리 |
| --- | --- |
| 생성 타입 | OpenAPI 0.3.0 frozen 문서로 생성한 `StandardPage`, `StandardDetail`, `StandardHistoryPage`, `StandardReindexJob`, `EvidenceChunkPage`, `EvidenceSearchResult`를 client와 화면 경계에 사용 |
| Route 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN`만 `/standards` 접근과 navigation link를 허용하고, 그 외 role은 API 요청 전에 차단 |
| 목록/관리 loading | 목록 조회와 상세·이력·청크 확인·검색 데이터 갱신·등록·수정·검토 적용 중지 action 진행 상태를 분리해 표시 |
| Empty | 목록/이력/Chunk/검색 결과가 0건이면 해당 영역의 빈 상태 표시 |
| 오류/redaction | ADR-0045 일반화 문구와 안전한 traceId만 표시하고 server message 및 index/point/doc ID를 숨김 |
| 등록 metadata 오류 | `REFERENCE_METADATA_INVALID`를 필수 메타데이터 입력 확인 문구로 표시하고 안전한 traceId만 제공하며 backend 원문 message는 숨김 |
| Hybrid 장애 | `/evidences/search` 또는 재색인 503을 정상/빈 결과로 fallback하지 않고 검색 인프라 장애로 표시 |

---

## S-015 PoC 검증 관리

### 3.34 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-015 |
| 화면명 | PoC 검증 관리 |
| 화면 목적 | 검증 데이터셋 및 담당자 판단 결과 관리 |
| 주요 사용자 | 준법감시 담당자, 기준 관리자 |

---

### 3.35 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검증 데이터셋 목록 조회 | `/validation/datasets` | GET | `productGroup`, `advertisementType`, `page`, `size` | 검증 데이터셋 목록 | 목록 영역 |
| 검증 데이터 등록 클릭 | 검증 데이터셋 등록 | `/validation/datasets` | POST | `multipart/form-data`: 데이터셋명, 상품군, 광고유형, 샘플 광고물, 상품조건파일, 담당자 의견, 정답 JSON | `datasetId` | 등록 완료 메시지 |
| 행 클릭 | 검증 데이터셋 상세 조회 | `/validation/datasets/{datasetId}` | GET | `datasetId` | 샘플 광고물, 정답 데이터, AI 결과 | API 추가 필요 |
| 담당자 판단 등록 클릭 | 담당자 판단 결과 등록 | `/validation/datasets/{datasetId}/judgments` | POST | `judgments`, `excluded` | 등록 결과 | 판단 결과 영역 |
| AI 결과 비교 클릭 | 검증 비교 결과 조회 | `/validation/datasets/{datasetId}/comparison` | GET | `datasetId` | AI 판정, 담당자 판단, 일치 여부 | API 추가 필요 |
| 평가 제외 클릭 | 평가 제외 처리 | `/validation/datasets/{datasetId}/exclude` | PATCH | `excluded`, `excludeReason` | 평가 제외 상태 | API 추가 필요 |

M7 실행 화면은 frozen v0.7.0 범위의 `listValidationDatasets`, `createValidationDataset`, `createValidationJudgments` 세 operation만 사용한다. 데이터셋/판단 제외는 각 등록 요청의 `excluded`, `excludeReasonCode`, `excludeReasonDetail`로 처리하며 별도 PATCH 계약은 후속 범위로 유지한다.

| 실행 상태 | 화면 처리 |
| --- | --- |
| loading / empty | 목록 요청 중 loading과 0건 상태를 분리한다. |
| error | ADR-0045 안전 문구와 traceId만 표시한다. |
| permission | 준법감시/기준 관리자만 등록 action을 표시하고 시스템 관리자는 조회 전용, 상품부서 직접 접근은 요청 전에 차단한다. |
| version / exclusion | dataset version과 평가 대상/제외 사유를 목록에 표시한다. |

### 3.36 추가 필요 API

| API | 사유 |
| --- | --- |
| `/validation/datasets/{datasetId}` | 검증 데이터셋 단건 상세 조회 필요 |
| `/validation/datasets/{datasetId}/comparison` | AI 결과와 담당자 판단 비교 조회 필요 |
| `/validation/datasets/{datasetId}/exclude` | 평가 제외 처리 필요 |

---

## S-016 성능 평가

### 3.37 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-016 |
| 화면명 | 성능 평가 |
| 화면 목적 | PoC KPI별 성능 평가 실행 및 결과 확인 |
| 주요 사용자 | 준법감시 담당자, 시스템 관리자 |

---

### 3.38 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 최근 평가 결과 목록 조회 | `/validation/evaluations` | GET | `page`, `size`, `fromDate`, `toDate` | 평가 결과 목록 | API 추가 필요 |
| 평가 실행 클릭 | PoC 성능 평가 실행 | `/validation/evaluations` | POST | `datasetIds`, `metrics`, `excludeInvalidSamples` | `evaluationId`, KPI별 점수, 목표 달성 여부 | 평가 결과 영역 |
| 평가 결과 상세 클릭 | 평가 결과 조회 | `/validation/evaluations/{evaluationId}` | GET | `evaluationId` | KPI 점수, 오류 유형, 개선 필요사항 | 상세 영역 |
| 결과 다운로드 클릭 | 평가 결과 다운로드 | `/validation/evaluations/{evaluationId}/download` | GET | `evaluationId`, `format` | Binary File | API 추가 필요 |
| 결과보고서 반영 클릭 | 결과보고서 반영 | `/validation/evaluations/{evaluationId}/report-reflection` | POST | 반영 항목 | 반영 결과 | API 추가 필요 |

M7 실행 화면은 frozen v0.7.0의 `createValidationEvaluation`, `getValidationEvaluation` 두 operation만 사용한다. 평가 이력 목록·다운로드·결과보고서 반영은 후속 API 범위이며 현재 화면에서 호출하지 않는다.

| 실행 상태 | 화면 처리 |
| --- | --- |
| stored KPI | 서버의 score/분자/분모/목표/달성 여부를 그대로 표시하고 재계산하지 않는다. |
| denominator 0 | `notApplicable=true`를 `미적용`, `분모 0 · 목표 판단 제외`로 표시한다. |
| exclusion | `exclusionSummary`를 승인 제외 사유별 건수로 표시한다. |
| permission | 준법감시/시스템 관리자는 실행·조회, 기준 관리자는 조회 전용, 상품부서는 route 차단한다. |
| error | 평가 대상 없음과 조회 실패를 ADR-0045 안전 오류 상태로 표시한다. |

### 3.39 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /validation/evaluations` | 평가 이력 목록 조회 필요 |
| `GET /validation/evaluations/{evaluationId}/download` | 평가 결과 파일 다운로드 필요 |
| `POST /validation/evaluations/{evaluationId}/report-reflection` | PoC 결과보고서 반영 기능 필요 시 추가 |

---

## S-017 사용자/권한 관리

### 3.40 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-017 |
| 화면명 | 사용자/권한 관리 |
| 화면 목적 | 사용자 계정, 권한, 감사 로그 관리 |
| 주요 사용자 | 시스템 관리자 |

---

### 3.41 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 사용자 목록 조회 | `/admin/users` | GET | `keyword`, `departmentId`, `role`, `status`, `page`, `size` | 사용자 목록 | 목록 영역 |
| 사용자 등록 클릭 | 사용자 등록 | `/admin/users` | POST | 사용자명, 부서, 이메일, 권한 | 사용자 ID | 목록 영역 갱신 |
| 권한 변경 클릭 | 사용자 권한 변경 | `/admin/users/{userId}/roles` | PATCH | `roles` | 변경 결과 | 권한 영역 갱신 |
| 비활성화 클릭 | 사용자 비활성화 | `/admin/users/{userId}/deactivate` | PATCH | `reason` | 비활성화 결과 | 목록 영역 갱신 |
| 로그 조회 클릭 | 시스템 로그 조회 | `/admin/audit-logs` | GET | `userId`, `actionType`, `fromDate`, `toDate` | 감사 로그 목록 | 로그 영역 |

### 3.42 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /admin/users/{userId}` | 사용자 상세 조회 필요 |

---

# 4. 주요 사용자 액션별 API 흐름

## 4.1 광고물 등록 후 AI 검토 요청

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-003 | 광고물 정보 입력 및 파일 업로드 | `/advertisements` | POST |
| 2 | S-004 | 검토 항목 선택 | `/advertisements/{advertisementId}` | GET |
| 3 | S-004 | AI 검토 요청 | `/advertisements/{advertisementId}/reviews` | POST |
| 4 | S-005 | 진행 상태 확인 | `/reviews/{reviewId}/status` | GET |
| 5 | S-006 | 결과 요약 확인 | `/reviews/{reviewId}/summary` | GET |

---

## 4.2 검토 결과 상세 확인

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-006 | 검토 결과 요약 확인 | `/reviews/{reviewId}/summary` | GET |
| 2 | S-008 | 상세 검토 결과 조회 | `/reviews/{reviewId}/items` | GET |
| 3 | S-008 | 검토 항목 상세 확인 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 4 | S-008 | 근거 상세 확인 | `/evidences/{evidenceId}` | GET |

---

## 4.3 광고 화면에서 문제 영역 확인

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-007 | 광고 파일 미리보기 | `/files/{fileId}/preview` | GET |
| 2 | S-007 | 문제 영역 조회 | `/reviews/{reviewId}/annotations` | GET |
| 3 | S-007 | Annotation 또는 목록 항목 클릭 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 4 | S-007 | 근거 상세 확인 | `/evidences/{evidenceId}` | GET |

---

## 4.4 문구 추천 채택

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-009 | 추천 문구 목록 조회 | `/reviews/{reviewId}/suggestions` | GET |
| 2 | S-009 | 추천 문구 선택 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 3 | S-009 | 채택/미채택/수정 후 저장 | `/suggestions/{suggestionId}/decision` | PATCH |

---

## 4.5 리포트 생성 및 다운로드

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-012 | 리포트 생성 옵션 선택 | - | - |
| 2 | S-012 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST |
| 3 | S-012 | 리포트 상세 조회 | `/reports/{reportId}` | GET |
| 4 | S-012 | 리포트 다운로드 | `/reports/{reportId}/download` | GET |

---

## 4.6 PoC 성능 평가

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-015 | 검증 데이터셋 등록 | `/validation/datasets` | POST |
| 2 | S-015 | 담당자 판단 등록 | `/validation/datasets/{datasetId}/judgments` | POST |
| 3 | S-016 | 성능 평가 실행 | `/validation/evaluations` | POST |
| 4 | S-016 | 평가 결과 조회 | `/validation/evaluations/{evaluationId}` | GET |

---

# 5. API 보완 필요 목록

현재 API 명세서 기준으로 화면 구현 시 추가 정의가 필요한 API는 다음과 같다.

| 구분 | API | 필요 화면 | 필요 사유 | 우선순위 |
| --- | --- | --- | --- | --- |
| 대시보드 | `/dashboard/summary` | S-001 | 검토 현황 집계 | 중요 |
| 대시보드 | `/dashboard/risk-summary` | S-001 | 위험도별 집계 | 중요 |
| 파일 | `/files/{fileId}/download` | S-014, S-017 | 첨부파일 다운로드 | 중요 |
| 의견 초안 | `GET /opinion-drafts/{draftId}` | S-011 | 초안 단건 상세 조회 | 중요 |
| 검증 | `/validation/datasets/{datasetId}` | S-015 | 검증 데이터셋 상세 조회 | 중요 |
| 검증 | `/validation/datasets/{datasetId}/comparison` | S-015 | AI 결과와 담당자 판단 비교 | 중요 |
| 검증 | `/validation/datasets/{datasetId}/exclude` | S-015 | 평가 제외 처리 | 중요 |
| 평가 | `GET /validation/evaluations` | S-016 | 평가 이력 목록 조회 | 중요 |
| 평가 | `/validation/evaluations/{evaluationId}/download` | S-016 | 평가 결과 다운로드 | 선택 |
| 평가 | `POST /validation/evaluations/{evaluationId}/report-reflection` | S-016 | PoC 결과보고서 반영 | 선택 |
| 관리자 | `GET /admin/users/{userId}` | S-017 | 사용자 상세 조회 | 중요 |

---

# 6. 화면별 권한 매핑

| 화면 ID | 화면명 | 상품부서 담당자 | 준법감시 담당자 | 기준 관리자 | 시스템 관리자 |
| --- | --- | --- | --- | --- | --- |
| S-001 | 메인 대시보드 | 조회 | 조회 | 조회 | 조회 |
| S-002 | 광고물 목록 | 조회 | 조회 | 불가 | 조회 |
| S-003 | 광고물 등록 | 등록 | 등록 | 불가 | 등록 |
| S-004 | AI 검토 요청 | 요청 | 요청 | 불가 | 요청 |
| S-005 | 검토 진행 상태 | 조회 | 조회 | 불가 | 조회 |
| S-006 | 검토 결과 요약 | 조회 | 조회 | 불가 | 조회 |
| S-007 | 광고 화면 검토 UI | 조회 | 조회 | 불가 | 조회 |
| S-008 | 상세 검토 결과 | 조회 | 조회 | 불가 | 조회 |
| S-009 | 문구 추천 | 조회/의견 | 조회/의견 | 불가 | 조회 |
| S-010 | 광고 규정 Q&A | 사용 | 사용 | 사용 | 사용 |
| S-011 | 심의 의견 초안 | 제한 | 생성/수정 | 불가 | 조회 |
| S-012 | 검토 리포트 | 생성/조회 | 생성/조회 | 불가 | 생성/조회 |
| S-013 | 수정 전후 비교 | 등록/조회 | 조회 | 불가 | 조회 |
| S-014 | 기준자료 관리 | 불가 | 제한 조회 | 등록/수정 | 등록/수정 |
| S-015 | PoC 검증 관리 | 불가 | 등록/조회 | 등록/조회 | 조회 |
| S-016 | 성능 평가 | 불가 | 실행/조회 | 조회 | 실행/조회 |
| S-017 | 사용자/권한 관리 | 불가 | 불가 | 불가 | 관리 |

---

# 7. 화면별 주요 예외 처리 매핑

| 화면 ID | 주요 예외 | 관련 오류 코드 | 처리 방식 |
| --- | --- | --- | --- |
| S-003 | 지원하지 않는 파일 형식 | `FILE_NOT_SUPPORTED` | ADR-0045 기본 메시지 + 허용 확장자 안내 |
| S-003 | 파일 크기 초과 | `FILE_SIZE_EXCEEDED` | ADR-0045 기본 메시지 + 50MB 이하 파일 업로드 안내 |
| S-003 | 파일 손상 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 재업로드 안내 |
| S-004 | 이미 분석 중 | `REVIEW_ALREADY_RUNNING` | ADR-0045 기본 메시지 + 기존 분석 진행 상태 안내 |
| S-005 | 분석 실패 | `REVIEW_FAILED` | ADR-0045 기본 메시지 + 재분석 버튼 표시 |
| S-006 | 기준자료 부족 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + “기준자료 확인 필요” 표시 |
| S-007 | 파일 미리보기 실패 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 원본 파일 확인 안내 |
| S-007 | OCR 좌표 없음 | `OCR_FAILED` | ADR-0045 기본 메시지 + ADR-0051 기준 `LIST_ONLY` 또는 `UNAVAILABLE` 표시 |
| S-008 | 근거 없음 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + 확인 필요 표시 |
| S-009 | 추천 문구 없음 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + 담당자 직접 검토 안내 |
| S-010 | 질문 범위 불명확 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 상품군/광고유형 선택 안내 |
| S-011 | 검토 결과 없음 | `NOT_FOUND` | ADR-0045 기본 메시지 + 초안 생성 제한 |
| S-012 | 리포트 생성 실패 | `INTERNAL_ERROR` | ADR-0045 기본 메시지 + 재시도 안내 |
| S-013 | 수정본 파일 오류 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 수정본 재업로드 안내 |
| S-014 | 기준자료 중복 | `CONFLICT` | ADR-0045 기본 메시지 + 기존 기준자료 확인 안내 |
| S-015 | 정답 데이터 부족 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 담당자 판단 입력 요청 |
| S-016 | 평가 대상 없음 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 검증 데이터셋 선택 안내 |
| S-017 | 권한 없음 | `FORBIDDEN` | ADR-0045 기본 메시지 + 접근 제한 안내 |

---

# 8. 결론

본 화면-API 매핑표는 화면설계서의 주요 화면과 API 명세서의 엔드포인트를 연결한 개발 연계 문서이다.

핵심 흐름은 다음과 같다.

1. `S-003 광고물 등록`에서 `/advertisements` API 호출
2. `S-004 AI 검토 요청`에서 `/advertisements/{advertisementId}/reviews` API 호출
3. `S-005 검토 진행 상태`에서 `/reviews/{reviewId}/status` API 호출
4. `S-006 검토 결과 요약`에서 `/reviews/{reviewId}/summary` API 호출
5. `S-007 광고 화면 검토 UI`에서 `/reviews/{reviewId}/annotations` 및 `/files/{fileId}/preview` API 호출
6. `S-008 상세 검토 결과`에서 `/reviews/{reviewId}/items` API 호출
7. `S-009 문구 추천`에서 `/reviews/{reviewId}/suggestions` 및 `/suggestions/{suggestionId}/decision` API 호출
8. `S-012 검토 리포트`에서 `/reviews/{reviewId}/reports` 및 `/reports/{reportId}/download` API 호출
9. `S-015~S-016`에서 PoC 검증 데이터셋과 KPI 평가 API 호출

이 문서를 기준으로 후속 단계에서는 **OpenAPI 3.0 명세**, **DB 설계서**, **화면별 Request/Response 상세 정의**, **테스트 케이스**를 작성하면 된다.
