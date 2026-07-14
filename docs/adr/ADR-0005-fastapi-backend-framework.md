# ADR-0005: Python 백엔드 프레임워크로 FastAPI 채택

## 상태

Accepted

## 배경

본 프로젝트의 백엔드는 광고물 관리, AI 검토 요청, 검토 결과 조회, 기준자료 관리, Q&A, 리포트, PoC 검증 API를 제공해야 한다. API 명세서가 이미 주요 엔드포인트와 요청/응답 구조를 정의하고 있으므로, 구현 프레임워크는 타입 기반 스키마 정의, API 문서화, 비동기 작업 연계에 강해야 한다.

AI 워커, OCR/문서 파서, RAG 검색과도 Python 생태계에서 연동할 가능성이 높다.

## 결정

Python 백엔드 API 프레임워크로 FastAPI를 채택한다.

기본 원칙은 다음과 같다.

| 항목 | 결정 |
| --- | --- |
| API 서버 | FastAPI |
| 데이터 검증/직렬화 | Pydantic 모델 |
| API 문서 | FastAPI가 생성하는 OpenAPI 스키마를 기본으로 사용 |
| 서버 실행 | ASGI 서버 기반 실행 |
| 백그라운드 분석 | API 서버는 요청/조회 책임, 장기 실행 분석은 worker로 분리 |

## 대안

| 대안 | 판단 |
| --- | --- |
| FastAPI | 타입 힌트, Pydantic, OpenAPI 자동 생성, 비동기 작업 연계가 PoC에 적합하다. |
| Django + DRF | 관리자 기능과 ORM 생태계는 강하지만 PoC API 서버로는 무거울 수 있다. |
| Flask | 단순하지만 타입 기반 계약, OpenAPI, 검증 구조를 별도로 설계해야 한다. |

## 결정 근거

- API 명세 기반 개발과 잘 맞는다.
- Pydantic 모델을 통해 요청/응답 DTO를 명확하게 관리할 수 있다.
- OpenAPI 스키마를 자동 생성할 수 있어 프론트엔드, 테스트, 문서와 연동하기 쉽다.
- Python AI/문서 처리 생태계와 같은 언어권에서 통합하기 쉽다.
- 장기 실행 OCR/RAG/LLM 분석은 API 프로세스에 넣지 않고 worker로 분리해 장애 영향과 응답 지연을 줄일 수 있다.

## 영향

- API 요청/응답 모델은 Pydantic 기반으로 정의한다.
- API 명세서와 FastAPI OpenAPI 스키마가 어긋나지 않도록 계약 테스트가 필요하다.
- DB 접근, 인증/인가, 트랜잭션, 에러 응답 포맷은 별도 공통 계층으로 표준화해야 한다.
- 관리자 화면이 필요하더라도 Django Admin에 의존하지 않고 별도 Admin API와 프론트엔드 화면으로 구현한다.

## 후속 조치

- `apps/backend` 초기 구조를 FastAPI 기준으로 구성한다.
- 공통 응답 포맷과 오류 코드를 API 명세서와 맞춘다.
- Pydantic 스키마와 OpenAPI export를 API 계약 검증에 활용한다.
- worker 호출 방식은 [ADR-0035: Redis Queue 및 PostgreSQL Job 상태 테이블 병행](ADR-0035-redis-queue-postgresql-job-state.md)을 따른다.

## 관련 문서

- `docs/api-specification.md`
- `docs/database-specification.md`
- `docs/functional-specification.md`
- `docs/adr/ADR-0003-monorepo-structure.md`
- `docs/adr/ADR-0007-docker-compose-build-deploy.md`
