# 개발 일정 및 Notion 칸반 보드 구성안

# 개발 일정 및 Notion 칸반 보드 구성안

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-07-13 |

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과를 반영한 Sprint/칸반 구성 기준 정리 |

---

## 1. 일정 수립 기준

| 항목 | 내용 |
| --- | --- |
| 개발 기간 | 2026-07-06 ~ 2026-10-31 |
| 실질 개발 마감 | 2026-10-30 |
| 기준일 | 2026-10-31 |
| 개발 방식 | 명세 기반 개발 + AI 활용 풀스택 개발 |
| 관리 방식 | Notion Kanban Board |
| 일정 단위 | 1~2주 단위 Sprint |
| 주요 목표 | 10월 말까지 PoC 시연 가능한 통합본 구축 |
| 최종 산출물 | 광고심의 AI Agent PoC, 기준 DB, 검토 UI, 리포트, 검증 데이터셋, PoC 검증 결과 초안 |

---

# 2. 전체 개발 로드맵

## 2.1 월별 목표

| 월 | 목표 | 주요 산출물 |
| --- | --- | --- |
| 7월 | 착수, 명세 확정, 개발환경 구성, 기본 골격 구현 | 요구사항/기능/API/DB/테스트 명세, Repository, Docker, 기본 API Skeleton |
| 8월 | 핵심 백엔드, 기준 DB, OCR/RAG 기반 분석 파이프라인 구현 | 광고물 등록, 기준자료 관리, OCR 결과 저장, RAG 검색, 검토 Job |
| 9월 | 검토 결과, 화면 표시, 문구 추천, 리포트, 프론트 연동 | 검토 결과 UI, Annotation, 문구 추천, Q&A, 리포트, 수정 전후 비교 |
| 10월 | 통합 안정화, PoC 검증, 성능평가, 시연본 구축 | 통합 PoC, 검증 데이터셋, KPI 평가, 사용자 피드백 반영, 최종 시연본 |

---

## 2.2 Sprint 구성

| Sprint | 기간 | 목표 |
| --- | --- | --- |
| Sprint 0 | 2026-07-06 ~ 2026-07-10 | 착수, 문서 확정, ADR 1차 결정 |
| Sprint 1 | 2026-07-13 ~ 2026-07-24 | 개발환경, Repository, CI/CD, DB 초기 설계 |
| Sprint 2 | 2026-07-27 ~ 2026-08-07 | 광고물 관리, 파일 업로드, 기준자료 관리 |
| Sprint 3 | 2026-08-10 ~ 2026-08-21 | OCR/VLM, 레이아웃 분석, 분석 Job 파이프라인 |
| Sprint 4 | 2026-08-24 ~ 2026-09-04 | RAG 검색, Rule Engine, 검토 결과 생성 |
| Sprint 5 | 2026-09-07 ~ 2026-09-18 | 프론트 1차 구현, 검토 결과 화면, Annotation UI |
| Sprint 6 | 2026-09-21 ~ 2026-10-02 | 문구 추천, Q&A, 심의 의견 초안, 리포트 |
| Sprint 7 | 2026-10-05 ~ 2026-10-16 | 수정 전후 비교, PoC 검증 데이터셋, KPI 평가 |
| Sprint 8 | 2026-10-19 ~ 2026-10-30 | 통합 테스트, 사용자 피드백 반영, 최종 시연본 |
| 마감 | 2026-10-31 | PoC 개발 마감 기준일 |

---

# 3. Notion 칸반 보드 권장 속성

Notion Database는 아래 속성으로 구성하는 것을 권장한다.

| 속성명 | 타입 | 설명 |
| --- | --- | --- |
| Task ID | Text | 작업 ID |
| Task | Title | 작업명 |
| Epic | Select | 상위 업무 영역 |
| Status | Select | Backlog, Ready, In Progress, Review, Done, Blocked |
| Sprint | Select | Sprint 0 ~ Sprint 8 |
| Priority | Select | P0, P1, P2 |
| Owner Role | Select | PM, Backend, Frontend, AI, Data, DevOps, QA, Designer |
| Start Date | Date | 시작일 |
| Due Date | Date | 완료 목표일 |
| Dependency | Relation/Text | 선행 작업 |
| Deliverable | Text | 산출물 |
| Acceptance Criteria | Text | 완료 기준 |
| ADR Required | Checkbox | ADR 필요 여부 |
| Related Doc | Multi-select | 요구사항, 기능명세, API명세, DB명세, 테스트케이스 등 |
| Notes | Text | 특이사항 |

---

# 4. Kanban Status 정의

| Status | 의미 |
| --- | --- |
| Backlog | 아직 착수하지 않은 작업 |
| Ready | 착수 가능 상태 |
| In Progress | 진행 중 |
| Review | 코드 리뷰, 문서 리뷰, QA 검증 대기 |
| Done | 완료 |
| Blocked | 외부 의존성 또는 의사결정 지연으로 중단 |

---

# 5. Epic 구성

| Epic | 설명 |
| --- | --- |
| E01. Project Setup | 프로젝트 착수, 저장소, 개발환경, CI/CD |
| E02. Specification & ADR | 명세서, ADR, 개발 방법론, 의사결정 기록 |
| E03. Data & DB | DB 설계, 마이그레이션, 기준자료 구조 |
| E04. Advertisement Management | 광고물 등록, 파일 업로드, 수정본 관리 |
| E05. AI Review Pipeline | OCR/VLM, 레이아웃 분석, AI Job, Rule/RAG/LLM 검토 |
| E06. RAG & Search | Qdrant, OpenSearch, Hybrid Search, 기준자료 Chunking |
| E07. Review Result & Annotation | 검토 결과, 근거 매핑, 화면 Annotation |
| E08. Frontend | 프론트엔드 1차 구현 및 API 연동 |
| E09. Compliance Support | 문구 추천, Q&A, 심의 의견 초안, 리포트 |
| E10. Validation & Evaluation | 검증 데이터셋, KPI 평가, PoC 결과 |
| E11. QA & Stabilization | 테스트, 결함 수정, 통합 안정화 |
| E12. Demo & Handover | 최종 시연본, 사용자 가이드, 산출물 정리 |

---

# 6. Notion 칸반 보드 항목

아래 표를 Notion Database에 그대로 옮기면 칸반 보드로 구성할 수 있다.

---

## Sprint 0. 착수 및 1차 의사결정

### 2026-07-06 ~ 2026-07-10

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0001 | 프로젝트 착수 회의 및 범위 재확인 | E02. Specification & ADR | Ready | Sprint 0 | P0 | PM | 2026-07-06 | 2026-07-06 | - | 착수 회의록 | PoC 범위, 일정, 역할이 합의됨 | N |
| T-0002 | 요구사항 정의서 v1.0 정리 | E02. Specification & ADR | Ready | Sprint 0 | P0 | PM | 2026-07-06 | 2026-07-07 | T-0001 | 요구사항 정의서 | 핵심 요구사항과 제외 범위가 정리됨 | N |
| T-0003 | 기능명세서 v1.0 정리 | E02. Specification & ADR | Ready | Sprint 0 | P0 | PM | 2026-07-07 | 2026-07-08 | T-0002 | 기능명세서 | 기능 ID, 입력, 출력, 예외, 완료조건 정리 | N |
| T-0004 | API 명세서 v1.0 정리 | E02. Specification & ADR | Ready | Sprint 0 | P0 | Backend | 2026-07-08 | 2026-07-09 | T-0003 | API 명세서 | 주요 API Endpoint, 요청/응답 정의 완료 | N |
| T-0005 | DB 명세서 v1.0 정리 | E03. Data & DB | Ready | Sprint 0 | P0 | Backend | 2026-07-08 | 2026-07-09 | T-0004 | DB 명세서 | 주요 테이블, PK/FK, 인덱스 후보 정의 | N |
| T-0006 | 테스트케이스 v1.0 정리 | E11. QA & Stabilization | Ready | Sprint 0 | P0 | QA | 2026-07-09 | 2026-07-10 | T-0004, T-0005 | 테스트케이스 | P0/P1 테스트 항목 정의 완료 | N |
| T-0007 | ADR Backlog 작성 | E02. Specification & ADR | Ready | Sprint 0 | P0 | PM | 2026-07-09 | 2026-07-10 | T-0001 | ADR Backlog | 개발 착수 전 의사결정 목록 정리 | N |
| T-0008 | 고객사 자료 반출 및 AI 입력 제한 ADR 작성 | E02. Specification & ADR | Ready | Sprint 0 | P0 | PM | 2026-07-10 | 2026-07-10 | T-0007 | ADR-0001 | 고객사 자료 처리 기준이 합의됨 | Y |

---

## Sprint 1. 개발환경 및 Repository 구성

### 2026-07-13 ~ 2026-07-24

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0101 | Monorepo Repository 생성 | E01. Project Setup | Backlog | Sprint 1 | P0 | DevOps | 2026-07-13 | 2026-07-14 | T-0008 | Git Repository | apps, packages, infra, docs 구조 생성 | Y |
| T-0102 | Git 문서 구조 및 Wiki 초기 구성 | E02. Specification & ADR | Backlog | Sprint 1 | P0 | PM | 2026-07-13 | 2026-07-15 | T-0101 | docs 구조 | 명세서, ADR, 회의록 저장 위치 확정 | Y |
| T-0103 | Backend 프로젝트 Skeleton 생성 | E01. Project Setup | Backlog | Sprint 1 | P0 | Backend | 2026-07-14 | 2026-07-16 | T-0101 | Backend Skeleton | 기본 앱 실행, health check API 동작 | Y |
| T-0104 | Frontend 프로젝트 Skeleton 생성 | E08. Frontend | Backlog | Sprint 1 | P1 | Frontend | 2026-07-14 | 2026-07-16 | T-0101 | Frontend Skeleton | 기본 라우팅 및 레이아웃 실행 | Y |
| T-0105 | Python 패키지 관리 uv 적용 | E01. Project Setup | Backlog | Sprint 1 | P1 | Backend | 2026-07-15 | 2026-07-16 | T-0103 | pyproject.toml | uv add 기반 의존성 관리 가능 | Y |
| T-0106 | Docker Compose 초기 구성 | E01. Project Setup | Backlog | Sprint 1 | P0 | DevOps | 2026-07-16 | 2026-07-19 | T-0103, T-0104 | compose.yml, compose.dev.yml, compose.prod.yml | ADR-0063 기준 dev/prod compose config 검증 및 backend, frontend, postgres 컨테이너 실행 | Y |
| T-0107 | PostgreSQL 초기 스키마 구성 | E03. Data & DB | Backlog | Sprint 1 | P0 | Backend | 2026-07-17 | 2026-07-21 | T-0005, T-0106 | DB migration | users, advertisements 등 핵심 테이블 생성 | Y |
| T-0108 | Ruff, Pytest, 기본 CI 구성 | E11. QA & Stabilization | Backlog | Sprint 1 | P0 | DevOps | 2026-07-20 | 2026-07-22 | T-0103 | CI Pipeline | ADR-0064 기준 PR 필수 Gate, Mock/Fixture 기반 테스트, 문서/OpenAPI/Compose config 검증 | Y |
| T-0109 | Self-hosted Runner 구성 검토 | E01. Project Setup | Backlog | Sprint 1 | P1 | DevOps | 2026-07-21 | 2026-07-24 | T-0108 | Runner 구성안 | 배포 대상 서버 접근 가능성 확인 | Y |
| T-0110 | 개발 VM 신청 및 접근 환경 구성 | E01. Project Setup | Backlog | Sprint 1 | P0 | DevOps | 2026-07-13 | 2026-07-19 | - | 개발 VM | ADR-0033 기준 사양 신청, SSH 접속, Docker Compose 전체 스택 기동 확인 | Y |

---

## Sprint 2. 광고물 관리 및 기준자료 관리

### 2026-07-27 ~ 2026-08-07

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0201 | 광고물 등록 API 구현 | E04. Advertisement Management | Backlog | Sprint 2 | P0 | Backend | 2026-07-27 | 2026-07-29 | T-0107 | POST /advertisements | 파일 포함 광고물 등록 가능 | N |
| T-0202 | 광고물 목록/상세 API 구현 | E04. Advertisement Management | Backlog | Sprint 2 | P0 | Backend | 2026-07-29 | 2026-07-31 | T-0201 | GET /advertisements | 검색, 필터, 상세 조회 가능 | N |
| T-0203 | 파일 저장소 정책 확정 및 구현 | E04. Advertisement Management | Backlog | Sprint 2 | P0 | Backend, DevOps | 2026-07-27 | 2026-08-01 | T-0106 | 파일 저장 모듈 | 파일 저장, 메타데이터 저장, 다운로드 가능 | Y |
| T-0204 | 파일 미리보기 API 1차 구현 | E04. Advertisement Management | Backlog | Sprint 2 | P1 | Backend | 2026-07-31 | 2026-08-04 | T-0203 | GET /files/{fileId}/preview | 이미지/PDF 미리보기 URL 반환 | N |
| T-0205 | 기준자료 등록 API 구현 | E06. RAG & Search | Backlog | Sprint 2 | P0 | Backend | 2026-07-30 | 2026-08-04 | T-0107 | POST /standards | 법령/내부기준 등록 가능 | N |
| T-0206 | 기준자료 목록/상세/수정 API 구현 | E06. RAG & Search | Backlog | Sprint 2 | P0 | Backend | 2026-08-04 | 2026-08-07 | T-0205 | Standard API | 조회, 수정, 비활성화 가능 | N |
| T-0207 | 공통 코드 API 구현 | E01. Project Setup | Backlog | Sprint 2 | P1 | Backend | 2026-08-01 | 2026-08-04 | T-0107 | GET /codes/{codeGroup} | 상품군, 광고유형, 상태 코드 조회 가능 | N |
| T-0208 | 광고물 등록 화면 1차 구현 | E08. Frontend | Backlog | Sprint 2 | P1 | Frontend | 2026-08-03 | 2026-08-07 | T-0201, T-0207 | S-003 | 광고물 등록 화면에서 API 연동 가능 | N |
| T-0209 | 광고물 목록 화면 1차 구현 | E08. Frontend | Backlog | Sprint 2 | P1 | Frontend | 2026-08-03 | 2026-08-07 | T-0202 | S-002 | 광고물 목록 검색/조회 가능 | N |
| T-0210 | 광고물 관리 API 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 2 | P0 | QA, Backend | 2026-08-04 | 2026-08-07 | T-0201, T-0202 | pytest | 광고물 등록/조회 테스트 통과 | N |

---

## Sprint 3. OCR/VLM 및 분석 Job 파이프라인

### 2026-08-10 ~ 2026-08-21

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0301 | AI 검토 요청 API 구현 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | Backend | 2026-08-10 | 2026-08-12 | T-0201 | POST /advertisements/{advertisementId}/reviews | reviewId, jobId 생성 및 Redis Queue enqueue 가능 | N |
| T-0302 | Review Job/Step 상태 관리 구현 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | Backend | 2026-08-10 | 2026-08-14 | T-0301 | review_jobs | PostgreSQL 기준 Job 상태와 단계별 진행률 저장 | N |
| T-0303 | AI Worker 컨테이너 구성 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | AI, DevOps | 2026-08-12 | 2026-08-16 | T-0106, T-0301 | worker container | Redis Queue에서 비동기 분석 작업 실행 가능 | Y |
| T-0304 | OCR/VLM 추출 방식 ADR 확정 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | AI | 2026-08-10 | 2026-08-12 | T-0007 | ADR | OCR/VLM 선택 및 fallback 정책 확정 | Y |
| T-0305 | OCR 텍스트 추출 모듈 1차 구현 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | AI | 2026-08-13 | 2026-08-19 | T-0304 | OCR Module | 텍스트, confidence, 좌표 저장 | N |
| T-0306 | 레이아웃 분석 모듈 1차 구현 | E05. AI Review Pipeline | Backlog | Sprint 3 | P1 | AI | 2026-08-17 | 2026-08-21 | T-0305 | layout_blocks | 제목/본문/유의사항 영역 구분 | N |
| T-0307 | 검토 진행 상태 API 구현 | E05. AI Review Pipeline | Backlog | Sprint 3 | P0 | Backend | 2026-08-14 | 2026-08-18 | T-0302 | GET /reviews/{id}/status | 진행률 및 단계 조회 가능 | N |
| T-0308 | AI 검토 요청 화면 구현 | E08. Frontend | Backlog | Sprint 3 | P1 | Frontend | 2026-08-17 | 2026-08-21 | T-0301, T-0307 | S-004, S-005 | 분석 요청 및 진행상태 확인 가능 | N |
| T-0309 | OCR/Job API 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 3 | P0 | QA, AI | 2026-08-19 | 2026-08-21 | T-0305, T-0307 | pytest | Mock OCR fixture 기반 OCR 저장, Job 상태 테스트 통과 | N |

---

## Sprint 4. RAG 검색 및 검토 결과 생성

### 2026-08-24 ~ 2026-09-04

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0401 | Qdrant 컨테이너 및 Collection 구성 | E06. RAG & Search | Backlog | Sprint 4 | P0 | AI, DevOps | 2026-08-24 | 2026-08-26 | T-0106 | Qdrant | evidence_chunks collection 생성 | Y |
| T-0402 | OpenSearch 컨테이너 및 Index 구성 | E06. RAG & Search | Backlog | Sprint 4 | P0 | Backend, DevOps | 2026-08-24 | 2026-08-26 | T-0106 | OpenSearch | standards/evidence index 생성 | Y |
| T-0403 | 기준자료 Chunking 정책 확정 | E06. RAG & Search | Backlog | Sprint 4 | P0 | AI, Backend | 2026-08-24 | 2026-08-27 | T-0205 | ADR | chunk 크기, overlap, metadata 확정 | Y |
| T-0404 | 기준자료 Chunk 생성 및 인덱싱 구현 | E06. RAG & Search | Backlog | Sprint 4 | P0 | AI | 2026-08-27 | 2026-09-01 | T-0401, T-0402, T-0403 | Indexer | Qdrant/OpenSearch 동시 색인 가능 | N |
| T-0405 | Evidence 검색 API 구현 | E06. RAG & Search | Backlog | Sprint 4 | P0 | Backend, AI | 2026-08-29 | 2026-09-03 | T-0404 | GET /evidences/search | keyword/vector/hybrid 검색 가능 | Y |
| T-0406 | Rule Engine 1차 구현 | E05. AI Review Pipeline | Backlog | Sprint 4 | P0 | Backend, AI | 2026-08-26 | 2026-09-02 | T-0305 | Rule Engine | 필수문구, 금리, 금지어 규칙 검토 가능 | Y |
| T-0407 | RAG 기반 위험 표현 검토 구현 | E05. AI Review Pipeline | Backlog | Sprint 4 | P0 | AI | 2026-08-29 | 2026-09-04 | T-0405 | RAG Review | 위험 표현 판단 및 근거 매핑 가능 | Y |
| T-0408 | 검토 결과 저장 구조 구현 | E07. Review Result & Annotation | Backlog | Sprint 4 | P0 | Backend | 2026-09-01 | 2026-09-04 | T-0406, T-0407 | review_items | 판정 결과, 위험도, 근거 매핑 저장 | N |
| T-0409 | RAG/Rule 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 4 | P0 | QA, AI | 2026-09-02 | 2026-09-04 | T-0406, T-0407 | pytest | Mock RAG/LLM fixture 기반 필수 문구/위험 표현 테스트 통과 | N |

---

## Sprint 5. 검토 결과 화면 및 Annotation UI

### 2026-09-07 ~ 2026-09-18

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0501 | 검토 결과 요약 API 구현 | E07. Review Result & Annotation | Backlog | Sprint 5 | P0 | Backend | 2026-09-07 | 2026-09-09 | T-0408 | GET /reviews/{id}/summary | 종합 위험도, 주요 리스크 조회 가능 | N |
| T-0502 | 상세 검토 결과 API 구현 | E07. Review Result & Annotation | Backlog | Sprint 5 | P0 | Backend | 2026-09-07 | 2026-09-10 | T-0408 | GET /reviews/{id}/items | 필터/페이징 조회 가능 | N |
| T-0503 | Annotation 좌표 정책 확정 | E07. Review Result & Annotation | Backlog | Sprint 5 | P0 | Frontend, AI | 2026-09-07 | 2026-09-09 | T-0305 | ADR | ADR-0015/0066 기준 원본/정규화 좌표와 API Coordinate 구조 확정 | Y |
| T-0504 | Annotation 생성 로직 구현 | E07. Review Result & Annotation | Backlog | Sprint 5 | P0 | Backend, AI | 2026-09-09 | 2026-09-15 | T-0503 | annotations | 문제 영역 좌표 저장 가능 | N |
| T-0505 | Annotation 조회 API 구현 | E07. Review Result & Annotation | Backlog | Sprint 5 | P0 | Backend | 2026-09-12 | 2026-09-16 | T-0504 | GET /reviews/{reviewId}/annotations | 페이지/유형/위험도 필터 가능 | N |
| T-0506 | 검토 결과 요약 화면 구현 | E08. Frontend | Backlog | Sprint 5 | P0 | Frontend | 2026-09-10 | 2026-09-17 | T-0501 | S-006 | 종합 위험도와 주요 리스크 표시 | N |
| T-0507 | 상세 검토 결과 화면 구현 | E08. Frontend | Backlog | Sprint 5 | P0 | Frontend | 2026-09-11 | 2026-09-18 | T-0502 | S-008 | 검토 항목 필터/상세 확인 가능 | N |
| T-0508 | 광고 화면 검토 UI 1차 구현 | E08. Frontend | Backlog | Sprint 5 | P0 | Frontend | 2026-09-12 | 2026-09-18 | T-0505, T-0204 | S-007 | 파일 미리보기 위 Annotation 표시 | N |
| T-0509 | 검토 결과/Annotation 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 5 | P0 | QA | 2026-09-16 | 2026-09-18 | T-0501~T-0508 | 테스트 결과 | 요약/상세/Annotation 테스트 통과 | N |

---

## Sprint 6. 문구 추천, Q&A, 의견 초안, 리포트

### 2026-09-21 ~ 2026-10-02

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0601 | 문구 추천 생성 로직 구현 | E09. Compliance Support | Backlog | Sprint 6 | P0 | AI | 2026-09-21 | 2026-09-25 | T-0407 | suggestions | 위험 표현별 대체 문구 생성 | N |
| T-0602 | 문구 추천 API 구현 | E09. Compliance Support | Backlog | Sprint 6 | P0 | Backend | 2026-09-23 | 2026-09-28 | T-0601 | Suggestion API | 추천 조회 및 채택 저장 가능 | N |
| T-0603 | 문구 추천 화면 구현 | E08. Frontend | Backlog | Sprint 6 | P1 | Frontend | 2026-09-25 | 2026-10-01 | T-0602 | S-009 | 추천 문구 확인/채택/수정 가능 | N |
| T-0604 | 광고 규정 Q&A API 구현 | E09. Compliance Support | Backlog | Sprint 6 | P1 | Backend, AI | 2026-09-21 | 2026-09-29 | T-0405 | Q&A API | 질문 입력 시 근거 기반 답변 반환 | N |
| T-0605 | 광고 규정 Q&A 화면 구현 | E08. Frontend | Backlog | Sprint 6 | P2 | Frontend | 2026-09-28 | 2026-10-02 | T-0604 | S-010 | 질문/답변/근거 표시 가능 | N |
| T-0606 | 심의 의견 초안 생성 API 구현 | E09. Compliance Support | Backlog | Sprint 6 | P1 | Backend, AI | 2026-09-23 | 2026-09-30 | T-0502, T-0601 | Opinion Draft API | 검토 항목 기반 초안 생성 가능 | N |
| T-0607 | 리포트 생성 API 구현 | E09. Compliance Support | Backlog | Sprint 6 | P0 | Backend | 2026-09-25 | 2026-10-02 | T-0501, T-0502, T-0602 | Report API | HWPX 우선 및 PDF 리포트 생성 | N |
| T-0608 | 심의 의견/리포트 화면 구현 | E08. Frontend | Backlog | Sprint 6 | P1 | Frontend | 2026-09-29 | 2026-10-02 | T-0606, T-0607 | S-011, S-012 | 초안 조회, 리포트 생성/다운로드 가능 | N |
| T-0609 | 문구 추천/리포트 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 6 | P0 | QA | 2026-09-30 | 2026-10-02 | T-0602, T-0607 | 테스트 결과 | 추천/채택/리포트 테스트 통과 | N |

---

## Sprint 7. 수정 전후 비교 및 PoC 검증 기능

### 2026-10-05 ~ 2026-10-16

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0701 | 수정 전후 비교 API 구현 | E09. Compliance Support | Backlog | Sprint 7 | P1 | Backend, AI | 2026-10-05 | 2026-10-09 | T-0203, T-0502 | Comparison API | 원본/수정본 비교 결과 생성 | N |
| T-0702 | 수정 전후 비교 화면 구현 | E08. Frontend | Backlog | Sprint 7 | P2 | Frontend | 2026-10-08 | 2026-10-14 | T-0701 | S-013 | 해결/미해결/신규 리스크 표시 | N |
| T-0703 | PoC 검증 데이터셋 등록 API 구현 | E10. Validation & Evaluation | Backlog | Sprint 7 | P0 | Backend | 2026-10-05 | 2026-10-08 | T-0201 | Validation Dataset API | 샘플 광고물/정답 데이터 등록 가능 | N |
| T-0704 | 담당자 판단 결과 등록 API 구현 | E10. Validation & Evaluation | Backlog | Sprint 7 | P0 | Backend | 2026-10-08 | 2026-10-10 | T-0703 | Judgment API | 담당자 판단 결과 저장 가능 | N |
| T-0705 | PoC KPI 산식 및 평가 제외 기준 확정 | E10. Validation & Evaluation | Backlog | Sprint 7 | P0 | PM, QA | 2026-10-05 | 2026-10-09 | T-0007 | ADR | KPI 산식, 제외 기준 합의 완료 | Y |
| T-0706 | PoC 성능평가 API 구현 | E10. Validation & Evaluation | Backlog | Sprint 7 | P0 | Backend, QA | 2026-10-12 | 2026-10-16 | T-0704, T-0705 | Evaluation API | KPI별 점수 산출 가능 | N |
| T-0707 | PoC 검증 관리 화면 구현 | E08. Frontend | Backlog | Sprint 7 | P1 | Frontend | 2026-10-12 | 2026-10-16 | T-0703, T-0704 | S-015 | 데이터셋/담당자 판단 등록 가능 | N |
| T-0708 | 성능 평가 화면 구현 | E08. Frontend | Backlog | Sprint 7 | P1 | Frontend | 2026-10-14 | 2026-10-16 | T-0706 | S-016 | KPI 결과 조회 가능 | N |
| T-0709 | 검증/평가 테스트 작성 | E11. QA & Stabilization | Backlog | Sprint 7 | P0 | QA | 2026-10-14 | 2026-10-16 | T-0703~T-0708 | 테스트 결과 | 검증 데이터셋 및 KPI 테스트 통과 | N |

---

## Sprint 8. 통합 안정화 및 최종 시연본

### 2026-10-19 ~ 2026-10-30

| Task ID | Task | Epic | Status | Sprint | Priority | Owner Role | Start Date | Due Date | Dependency | Deliverable | Acceptance Criteria | ADR Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-0801 | E2E 통합 테스트 수행 | E11. QA & Stabilization | Backlog | Sprint 8 | P0 | QA | 2026-10-19 | 2026-10-21 | 전체 기능 | E2E 테스트 결과 | 광고물 등록→검토→리포트 흐름 Pass | N |
| T-0802 | P0/P1 결함 수정 | E11. QA & Stabilization | Backlog | Sprint 8 | P0 | Backend, Frontend, AI | 2026-10-20 | 2026-10-25 | T-0801 | 결함 수정 내역 | Critical 0건, Major 합의 처리 | N |
| T-0803 | 샘플 광고물 기반 PoC 검증 수행 | E10. Validation & Evaluation | Backlog | Sprint 8 | P0 | QA, PM | 2026-10-21 | 2026-10-25 | T-0706 | 검증 결과 | 샘플별 AI 결과와 담당자 판단 비교 | N |
| T-0804 | 사용자 피드백 수렴 및 반영 | E12. Demo & Handover | Backlog | Sprint 8 | P1 | PM, Frontend, AI | 2026-10-23 | 2026-10-27 | T-0803 | 피드백 반영 내역 | 주요 사용성/설명력 개선 반영 | N |
| T-0805 | 최종 시연 시나리오 작성 | E12. Demo & Handover | Backlog | Sprint 8 | P0 | PM | 2026-10-23 | 2026-10-27 | T-0803 | 시연 시나리오 | 데모 순서와 샘플 데이터 확정 | N |
| T-0806 | 최종 시연본 빌드 및 배포 | E12. Demo & Handover | Backlog | Sprint 8 | P0 | DevOps | 2026-10-26 | 2026-10-28 | T-0802 | PoC Build | 시연 환경에서 전체 기능 동작 | N |
| T-0807 | PoC 결과보고서 초안 작성 | E10. Validation & Evaluation | Backlog | Sprint 8 | P1 | PM, QA | 2026-10-26 | 2026-10-29 | T-0803 | 결과보고서 초안 | KPI, 오류 유형, 개선 과제 포함 | N |
| T-0808 | 운영/개발 가이드 정리 | E12. Demo & Handover | Backlog | Sprint 8 | P1 | Backend, DevOps | 2026-10-27 | 2026-10-30 | T-0806 | README, 운영 가이드 | 실행/배포/테스트 절차 문서화 | N |
| T-0809 | 최종 산출물 정리 및 태깅 | E12. Demo & Handover | Backlog | Sprint 8 | P0 | PM, DevOps | 2026-10-29 | 2026-10-30 | T-0806, T-0807 | release tag | Git tag, 문서, 시연본 정리 완료 | N |

---

# 7. 마일스톤

| 마일스톤 | 목표일 | 완료 기준 |
| --- | --- | --- |
| M1. 착수 및 명세 확정 | 2026-07-10 | 요구사항/기능/API/DB/테스트 명세 초안 완료 |
| M2. 개발환경 구축 완료 | 2026-07-24 | Monorepo, Docker, CI, DB 초기 구성 완료 |
| M3. 광고물/기준자료 관리 완료 | 2026-08-07 | 광고물 등록, 파일 저장, 기준자료 관리 API 동작 |
| M4. OCR/분석 Job 파이프라인 완료 | 2026-08-21 | OCR 결과 저장, 분석 Job 상태 추적 가능 |
| M5. RAG/Rule 기반 검토 결과 생성 | 2026-09-04 | 필수 문구, 위험 표현, 근거 매칭 결과 생성 |
| M6. 검토 결과 UI 및 Annotation 완료 | 2026-09-18 | 화면에서 검토 결과와 문제 영역 확인 가능 |
| M7. 문구 추천/리포트 완료 | 2026-10-02 | 문구 추천, Q&A, 의견 초안, 리포트 생성 가능 |
| M8. PoC 검증 기능 완료 | 2026-10-16 | 검증 데이터셋, 담당자 판단, KPI 평가 가능 |
| M9. 최종 시연본 완료 | 2026-10-30 | 통합 테스트, 결함 수정, 시연 환경 배포 완료 |
| M10. 개발 마감 기준 | 2026-10-31 | PoC 개발 마감 |

---

# 8. Notion Board View 추천

## 8.1 기본 Kanban View

| View명 | Group by | Sort |
| --- | --- | --- |
| Development Board | Status | Priority → Due Date |
| Sprint Board | Sprint | Due Date |
| Epic Board | Epic | Priority → Due Date |
| ADR Board | ADR Required | Due Date |
| QA Board | Priority | Status → Due Date |

---

## 8.2 Status별 초기 배치

| Status | 포함 작업 |
| --- | --- |
| Ready | Sprint 0 작업 |
| Backlog | Sprint 1~8 전체 작업 |
| In Progress | 실제 착수한 작업 |
| Review | PR 리뷰, 문서 리뷰, QA 대기 작업 |
| Done | 완료된 작업 |
| Blocked | 고객사 자료 미제공, ADR 미결정, 인프라 미구성 등으로 중단된 작업 |

---

# 9. 리스크 및 선행 의사결정

## 9.1 일정 영향이 큰 리스크

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| 고객사 기준자료 제공 지연 | RAG/Rule 검토 정확도 저하 | 샘플 기준자료로 Mock 개발 후 실제 자료 반영 |
| OCR/VLM 성능 부족 | Annotation 및 문구 검토 품질 저하 | OCR+VLM fallback 구조 검토 |
| Qdrant/OpenSearch 운영 지연 | RAG 검색 개발 지연 | PostgreSQL 기반 임시 검색으로 우회 가능 |
| 화면 디자인 지연 | 프론트 개발 지연 | 기능 우선 화면 구현 후 디자인 개선 |
| KPI 산식 미확정 | PoC 평가 지연 | 10월 9일까지 ADR로 산식 확정 |
| 개발 VM/Runner 지연 | 통합 배포 지연 | 로컬 Docker Compose 부분 스택으로 우선 개발하고, 공용 VM 확보 후 전체 스택 통합 검증 |

---

## 9.2 개발 착수 전 우선 확정해야 할 ADR

| ADR | 확정 목표일 | 이유 |
| --- | --- | --- |
| 고객사 자료 반출 및 AI 입력 제한 | 2026-07-10 | AI 활용 개발 및 자료 처리 기준 필요 |
| Monorepo 구조 채택 | 2026-07-14 | Repository 생성 전 결정 필요 |
| Python 백엔드 프레임워크 선택 | 2026-07-16 | Backend Skeleton 생성 전 결정 필요 |
| PostgreSQL 사용 | 2026-07-18 | DB migration 작성 전 결정 필요 |
| 개발 VM 구성 | 2026-07-19 | Docker Compose 전체 스택 통합 개발 환경 신청 전 결정 필요 |
| 파일 저장소 선택 | 2026-07-31 | 광고물 업로드 구현 전 결정 필요 |
| OCR/VLM 추출 방식 | 2026-08-12 | 분석 파이프라인 구현 전 결정 필요 |
| Qdrant/OpenSearch 사용 | 2026-08-26 | RAG 검색 구현 전 결정 필요 |
| Hybrid Search 전략 | 2026-09-03 | 근거 검색 품질 검증 전 결정 필요 |
| Annotation 좌표 체계 | 2026-09-09 | ADR-0015/0066 기준 결정 완료. 구현 전 DB/API/OpenAPI 반영 필요 |
| KPI 산식 및 평가 제외 기준 | 2026-10-09 | PoC 성능평가 구현 전 결정 필요 |

---

# 10. 10월 말 완료 기준

2026년 10월 31일 기준 완료 상태는 다음을 목표로 한다.

| 영역 | 완료 기준 |
| --- | --- |
| 광고물 관리 | 광고물 등록, 조회, 수정본 등록 가능 |
| 기준자료 관리 | 기준자료 등록, 수정, 검색 가능 |
| OCR/VLM | 광고물 텍스트 추출 및 좌표 저장 가능 |
| RAG 검색 | 기준자료 기반 근거 검색 가능 |
| AI 검토 | 필수 문구, 금리·조건, 위험 표현, 정합성 일부 검토 가능 |
| Annotation | 광고 화면 위 문제 영역 표시 가능 |
| 문구 추천 | 부적정 표현에 대한 대체 문구 제안 가능 |
| Q&A | 광고 규정 질의응답 가능 |
| 리포트 | 검토 결과 리포트 생성 가능 |
| 검증 | 샘플 광고물 기준 AI 결과와 담당자 판단 비교 가능 |
| KPI | 필수 문구 정확도, 위험 표현 정확도, 근거 매칭 적정성, 담당자 판단 일치율 산출 가능 |
| 배포 | 시연 환경에서 PoC 통합본 실행 가능 |
| 문서 | API, DB, 테스트케이스, ADR, 운영 가이드 최신화 |

---

# 11. 결론

본 일정은 2026년 10월 31일까지 PoC 개발본을 완성하기 위한 칸반 기반 실행 계획이다.

핵심 일정 전략은 다음과 같다.

1. 7월에는 문서, 개발환경, Repository, CI/CD, DB Skeleton을 확정한다.
2. 8월에는 광고물 등록, 기준자료 관리, OCR/VLM, 분석 Job, RAG 검색 기반을 구현한다.
3. 9월에는 검토 결과, Annotation UI, 문구 추천, Q&A, 리포트 등 사용자 기능을 구현한다.
4. 10월에는 수정 전후 비교, PoC 검증 데이터셋, KPI 평가, 통합 테스트, 최종 시연본을 완성한다.

Notion에서는 본 문서의 `Task ID` 단위로 카드를 생성하고, `Status`, `Sprint`, `Epic`, `Priority`, `Owner Role`, `Due Date`를 기준으로 보드를 운영하면 된다.
