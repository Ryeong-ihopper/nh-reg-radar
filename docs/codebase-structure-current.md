# 코드베이스 현행 구조와 검토 순서

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.0 |
| 기준일 | 2026-09-10 |
| 목적 | 실제 운영 경로와 구형·평가·제품 코드를 구분하고 기능별 코드 검토 순서를 고정 |

## 1. 정본 저장소 경계

현재 작업 정본은 `nh-ad-compliance/`다. 한 단계 위 `cg_법령api/`도 별도 Git 저장소이며,
그 아래의 `rag/`, `schemas/`, `tools/`, `output/_rag/`는 이전 RAG 개발·평가 계열이다.
현재 `nh-ad-compliance/rag-pipeline/`은 바깥 `rag/`를 import하지 않는다.

| 위치 | 현재 역할 | 처리 원칙 |
| --- | --- | --- |
| `nh-ad-compliance/rag-pipeline/` | 템플릿 중심 DGX 운영형 RAG 정본 | 코드 검토·개선 대상 |
| `nh-ad-compliance/apps/` | 제품 Backend·Frontend·Worker·Parser 서비스 | 제품 흐름 검토 대상 |
| `cg_법령api/rag/` | 구형 실험, Colab, 답지·평가 생성 코드 혼합 | 운영 import 금지, 별도 legacy 보존 |
| `cg_법령api/schemas/` | 구형 운영 계약 사본 | 사용 금지. 현행과 해시가 모두 다름 |
| `cg_법령api/rag/schemas/대출성.json` | 구형 단일 상품군 모델 출력 형식 | 현행 JSON Schema가 아니므로 사용 금지 |
| `cg_법령api/output/_rag/` | 과거 평가·검수 산출물 | 코드가 아니며 운영 입력 금지 |

`rag-pipeline/`과 제품 Worker는 아직 같은 실행기가 아니다. 현행 제품 Worker는
PostgreSQL·Redis·Qdrant 기반 제품 경로이고, 템플릿 중심 RAG는 독립 CLI/API다.
로컬 화면에서는 `scripts/operational_web_bridge.py`가 둘을 연결한다. 제품 Worker로 정식
통합하기 전에는 어느 한쪽을 다른 쪽의 최신 구현으로 간주하지 않는다.

## 2. 실제 처리 흐름과 우선 검토 코드

### 2.1 광고 접수·작업 관리

- 제품 API·도메인: `apps/backend/src/nh_ad_backend/api.py`, `domain.py`, `services.py`
- 광고·심의 작업: `apps/backend/src/nh_ad_backend/reviews.py`, `reviews_api.py`
- 파일 저장: `apps/backend/src/nh_ad_backend/storage.py`, `s3_storage.py`
- 작업 실행 기반: `apps/worker/src/nh_ad_worker/jobs.py`, `queue.py`, `runtime.py`

### 2.2 광고 파싱·OCR·시인성 관측

- 파서 서비스 조립: `apps/parser-services/service.py`
- 엔진별 어댑터: `opendataloader_app.py`, `paddleocr_app.py`, `rhwp_app.py`,
  `document_processor_app.py`
- 공통 파서 계약: `packages/parser-contracts/src/nh_ad_parser_contracts/`
- 제품 Worker 호출부: `apps/worker/src/nh_ad_worker/parser_services.py`
- P1/P3 운영 입력 결합: `rag-pipeline/rag/parsing/prepare_inputs.py`

파서는 텍스트·표·bbox·스타일·시인성 관측까지 책임진다. RAG의 `prepare_inputs.py`는
파서가 만든 P1/P3를 결합하고 검증할 뿐 OCR을 다시 수행하지 않는다.

### 2.3 템플릿 원문 적재와 라우팅

- HWPX 구조 파싱·독립 `TPL-` 카탈로그: `rag-pipeline/rag/templates/catalog.py`
- 적재 CLI: `rag-pipeline/tools/ingest_template_hwpx.py`
- 상세 상품군·입력 정책: `rag-pipeline/rag/judgment/policy.py`

템플릿 항목은 v2 item ID가 없어도 독립적으로 판정된다. v2와의 결합은 법령 근거와
세부 조건을 보강하기 위한 선택적 연결이지 모델 투입의 전제조건이 아니다.

### 2.4 규제목록 v2 적재

- 원본 행 적재·정규화: `rag-pipeline/rag/build_items.py`
- 실행용 규칙 카탈로그: `rag-pipeline/tools/regulation_v2_catalog.py`
- silver 요청 생성: `rag-pipeline/tools/build_silver_requests.py`

이 경로는 템플릿 밖 쟁점, 조건, 입력요건과 법령 근거를 보완한다. 심의사례 정답을
규칙으로 읽지 않는다.

### 2.5 청킹

- 광고 coarse/fine 투영: `rag-pipeline/rag/parsing/prepare_inputs.py`
- 실행 중 규칙별 근거 창 구성: `rag-pipeline/tools/run_operational_e2e.py`

현재 청킹은 별도 패키지로 분리되지 않고 입력 준비와 실행기에 섞여 있다. 물리적 폴더
정리 때 `chunking/`으로 가장 먼저 분리할 대상이다.

### 2.6 임베딩·인덱싱

- BGE-M3 서비스 클라이언트: `rag-pipeline/tools/dgx_bge_client.py`
- 광고 evidence 벡터 생성·캐시: `rag-pipeline/tools/build_ad_evidence_vectors.py`
- Elasticsearch 시험 구성: `rag-pipeline/rag/es/`
- 제품의 별도 임베딩 추상화: `packages/ai-providers/src/nh_ad_ai_providers/embeddings.py`

`packages/ai-providers`는 제품 공통 추상화이고, `dgx_bge_client.py`는 현행 DGX RAG
실행기다. 이름이 비슷하지만 현재 자동 결합돼 있지 않다.

### 2.7 검색·리랭킹

- BM25+BGE-M3 RRF와 리랭킹: `rag-pipeline/tools/hybrid_rule_retrieval.py`
- 운영 실행의 후보 구성: `rag-pipeline/tools/run_operational_e2e.py`
- 제품 Worker의 별도 검색 경로: `apps/worker/src/nh_ad_worker/evidence_search.py`,
  `qdrant_evidence_search.py`

바깥 저장소의 `rag/runtime_search.py`, `query_llm.py`, `item_run.py`는 현행
`rag-pipeline`에서 import하지 않는다. 따라서 지금 운영 코드를 확인할 때는 제외한다.

### 2.8 적용성·판정

- 적용성 공통 로직: `rag-pipeline/rag/judgment/applicability.py`
- 판정 정책·입력 게이트: `rag-pipeline/rag/judgment/policy.py`
- v2 보완 판정 가이드: `rag-pipeline/rag/judgment/decision_guides.py`
- Gemma 호출·출력 계약 복구: `rag-pipeline/tools/run_gemma_exhaustive_dgx.py`
- 모델 HTTP 클라이언트: `rag-pipeline/tools/dgx_openai_client.py`
- 공통 결과 입출력: `rag-pipeline/tools/model_result_io.py`

### 2.9 전체 실행·복구·API

- 운영형 전체 조정: `rag-pipeline/tools/run_operational_e2e.py`
- 정상 결과 보존·실패쌍 복구: `rag-pipeline/tools/recover_operational_judgments.py`
- 입력·결과 계약 검증: `rag-pipeline/tools/validate_operational_contracts.py`
- 비동기 서비스: `rag-pipeline/rag/api/service.py`
- API 진입점: `rag-pipeline/tools/serve_operational_api.py`
- 로컬 제품 화면 연결: `scripts/operational_web_bridge.py`, `serve-operational-review.py`

### 2.10 법령·협회 규정 수집

- 수집 기능 전체: `apps/backend/src/nh_ad_backend/regulation_collection/`
- 법령 수집: `law_scraper.py`
- 금융투자협회 수집: `kofia_scraper.py`
- 변경 비교·검토본: `diff_report.py`, `build_diff_view.py`, `build_review.py`
- 안전장치·해시·DB: `collect_safety.py`, `content_hash.py`, `db.py`

이 수집 경로와 광고 판정용 v2 Excel 적재는 현재 별도 기능이다. 수집 결과가 자동으로
v2 판정 규칙을 바꾸지 않는다.

## 3. 그 밖의 기능

| 기능 | 정본 위치 |
| --- | --- |
| 인증·권한 | `apps/backend/src/nh_ad_backend/security.py` |
| 기준자료 등록·검색 | `standards*.py`, `reference_ingestion.py`, `reference_document_parser.py` |
| 미리보기 | `pdf_preview.py`, `hwp_preview.py`, `scripts/local_hwp_preview.py` |
| 결과 표시 변환 | `apps/backend/src/nh_ad_backend/results*.py`, `scripts/serve-operational-review.py` |
| 프론트엔드 | `apps/frontend/src/` |
| API 계약 | `openapi/openapi.yaml` |
| RAG JSON 계약 | `rag-pipeline/schemas/` |
| DB migration | `apps/backend/migrations/` |
| 인프라 | `compose*.yml`, `infra/`, `deploy` 관련 scripts |
| 평가·누수 검사 | `rag-pipeline/tests/`, `validate_gold_v2_binding.py`, `run_rag_ci.py` |
| 문서 거버넌스 | `scripts/doc_governance/`, `governance/` |

## 4. 스키마 소유권

| 스키마 종류 | 단일 정본 위치 |
| --- | --- |
| 외부 HTTP API | `openapi/openapi.yaml` |
| RAG 입출력 JSON | `rag-pipeline/schemas/` |
| 파서 내부 Python 모델 | `packages/parser-contracts/src/nh_ad_parser_contracts/` |
| DB 구조 | `apps/backend/migrations/` |

바깥 `cg_법령api/schemas/`의 동명 4개 파일은 현행 `rag-pipeline/schemas/`와 해시가
모두 다르다. 자동 동기화 대상으로 보지 않고 legacy로 취급한다.

## 5. 목표 폴더 구조

기존 공개 CLI 경로는 얇은 wrapper로 유지하고 내부 구현을 다음처럼 분리한다.

```text
rag-pipeline/
├─ rag/
│  ├─ contracts/       # JSON 계약 검증과 결과 I/O
│  ├─ parsing/         # P1/P3 결합과 검증
│  ├─ templates/       # HWPX 템플릿 카탈로그
│  ├─ regulations/     # v2 적재와 실행 규칙
│  ├─ chunking/        # coarse/fine과 규칙별 근거 창
│  ├─ embeddings/      # BGE-M3 client와 vector cache
│  ├─ retrieval/       # BM25, vector, RRF, reranker
│  ├─ judgment/        # 적용성, 정책, Gemma 계약
│  ├─ orchestration/   # E2E, 복구, freeze
│  └─ api/             # 비동기 job service
├─ tools/              # 사람과 배포가 호출하는 CLI; 내부 구현 이동 후 wrapper만 유지
├─ schemas/            # RAG JSON Schema 단일 정본
├─ tests/              # 위 기능 구조와 동일하게 분리
└─ legacy/             # 실행 import가 금지된 보존 코드
```

한 번에 모든 파일을 이동하지 않는다. 기능 단위로 구현 이동, import 교체, CLI wrapper,
테스트, 문서 갱신을 한 묶음으로 수행한다.

## 6. 정리 순서

1. `runtime-cache/`, `output/`, `temp/` 등 실행 산출물을 Git 대상에서 제외한다.
2. `CANONICAL_FILES.txt`에 빠진 현행 템플릿·판정 가이드·리랭킹 검사를 추가한다.
3. 참조가 없는 구형 템플릿 export 3개는 `legacy/`로 이동한다.
4. `contracts → parsing/templates/regulations → chunking/embeddings/retrieval → judgment → orchestration/api`
   순서로 내부 패키지를 이동한다.
5. 각 단계에서 RAG CI와 누수 검사를 통과시킨다.
6. 마지막에 제품 Worker와 독립 RAG의 통합 방식을 별도 ADR로 확정한다.

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.0 | 2026-09-10 | 중첩 저장소·중복 스키마·제품 Worker와 독립 RAG 경계를 조사하고 기능별 검토 순서와 목표 구조 작성 |
