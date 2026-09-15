# NH 광고심의 RAG 정본 코드

이 문서는 GitHub에 올릴 운영형 코드 경로만 설명한다. 데이터, 답지, 연구원 피드백,
실행 산출물은 저장소에 포함하지 않는다.

## 정본 흐름

2026-09-15 판정 출력: `rag/judgment/output_contract.py`가 요청별 JSON Schema를 생성해 빈 결과/필드 누락/없는 별칭을 제한한다. 조건·의무의 의미와 근거 접지는 기존 검증기가 계속 검사한다. 기본 `NH_JUDGE_RESPONSE_FORMAT=json_schema`이며 Spark 실측 완료, H200 서버는 지원 확인이 필요하다. 미지원 서버에서만 명시적 `json_object` 설정을 사용할 수 있고 자동 강등하지 않는다. 모드·계약 코드 해시가 다르면 기존 체크포인트를 재사용하지 않는다. 이 변경은 운영 서버를 재시작하거나 기존 판정을 교체하지 않는다.

2026-09-15 판독 품질 통제: `rag/judgment/reading_quality.py`는 불확실한 원문에 의존한 확정을 사람 검토로 전환하고 원응답을 감사 기록으로 보존한다. `needs_review`·부분 읽기는 전체 스캔 상태에 반영하며, 확실한 독립 근거의 판정은 유지한다. 관찰된 원문 관계만 각주 문맥 확장에 사용하고 범위 밖/추정 관계는 보류한다. 실제 파서의 관계·스타일 생성 및 새 KL HRC 전체 연결 완료를 의미하지 않는다.

- 최종 결과는 `scripts/operational_locations.py`에서 광고/상품별 요청과 연결해 웹·JSON에 동일하게 투영한다.
  `LINE`은 확정 원문 줄, `REGION`은 정확 줄 미확정인 원본 영역이다. 원문 유사도로 다른 자산을 연결하지 않는다.
  JSON 다운로드 v2에는 화면 행, 추가 검토 후보, 보류 사유, 원본 판정·감사 기록을 보존한다.
- 실제 모델 호출 계측은 `rag/judgment/runtime_metrics.py`에서 실패·재시도·분할 조상 호출까지 집계한다.
  최종 응답 행 수와 실제 API 호출 수, 병렬 누적시간과 경과시간은 서로 다르다.

- 검색 목록과 판정 정의는 동일한 `include_layout=True` 범위로 로드하고 ID 집합을 대조한다.
  fine 질의 외에 700자 이내 동일 출처 부모의 전체 문맥 질의를 추가한다. 원본 질의/근거는 보존한다.
- BM25/정확 벡터는 카테고리별 k를 보장하고, 동일 본문/벡터 요청의 중복 전송만 제거한다.
  재정렬 pool과 최종 후보 예산은 카테고리별 최소 배분 후 순위로 재배분한다. 예산 탈락은 미해당이 아니다.

- 운영 v2 검색 범위는 예금·대출·전체 적용항목이며 시인성도 포함한다(현행 v2 124개).
  투자성 전용132개는 현재 상품 범위 밖이다. 검색 후보와 실제 관측 준비 여부는 분리한다.
  `load_scope()` 기본104개는 과거 비교용이며 운영은 `include_layout=True`를 지정한다.
- 규칙 인덱스는 문서/벡터 해시별 이름을 사용하며 기존 실행 인덱스를 덮어쓰지 않는다.
  작은 규칙 집합의 벡터 검색은 정확 코사인이고, BM25와 같은 필터를 적용한다.
  `timed_out`/shard 실패는 빈 검색 결과가 아니라 처리 실패로 기록한다.

- 운영 임베딩 경계는 BGE 서비스의 실제 1024차원/1024 최대 길이를 확인하고, 벡터의
  차원·유한수·정규화를 검증한다. 캐시 v2는 원문/행순서·벡터 해시 검증과 원자 저장을 사용한다.
  동일 텍스트 계산만 중복 제거하며 원래 청크/규칙 ID·순서는 보존한다.
  `tools/audit_embedding_inputs.py`로 독립 검사 가능. 검색 정확도 검증을 대체하지 않는다.

2026-09-14 연결 점검 기준:

- 상세 상품군의 HWPX 템플릿 전수검사 → 명시 매핑 v2 → 전체 v2 조건부 보완검색.
  템플릿은 독립 판단 출처이며 매핑 누락 때문에 제외하지 않는다.
- 광고 근거 선택은 직접 키워드·BGE 상위 근거를 함께 보존하고 나머지는 순위 융합한다.
  템플릿 예시는 검색 보조에 포함하되 예시 문구 일치를 의무로 만들지 않는다.
- 검색 문서는 원본 `line_ref → text`를 `line_texts`로 보존한다. 모델 호출에서 짧은 줄 별칭과
  정확한 원문을 함께 전달하고, 표시용 bbox와 원본 ID는 별칭 역매핑으로 연결한다.
  합쳐진 문장을 임의로 줄 수에 맞춰 나누거나 bbox를 추측하지 않는다.
- `SOURCE_SCOPED` 조건은 원문을 보존한 모델 적용성 검사이지 결정적 조건 게이트가 아니다.
  조건 배열이 존재한다는 이유만으로 적용성 정확성이 검증됐다고 보고하지 않는다.
- 파서 자체의 `확정`·수치 confidence는 접수 확정 권한이 아니다. 사용자/승인 manifest의
  값만 확정 라우팅에 사용하고 파서 결과는 inferred로 유지한다.
- `text_selection`은 P3의 읽기 선택 상태·재확인 표시·신뢰도·사유를 보존한다. 해당 근거에
  대한 불확실성이며 광고 전체의 법적 판단을 일괄 변경하지 않는다. `span_status`가
  영역 수준이면 정확한 줄 정렬로 간주하지 않는다. 현재 구분은 모델 입력에 전달한다.
- 저장·검색용 메타데이터와 모델 전송 표현을 구분한다. 광고 임베딩은 `text_search` 본문만
  사용한다. 모델 전송의 `lines`는 줄 별칭→원문, `line_bboxes`는 별칭→좌표 사전이며,
  `text_selection_ref`는 요청 내부 `reading_contexts`를 참조한다. 공유 대상은 동일한 읽기
  상태 값뿐이며, 파일·상품·청크·줄 소유권을 합치거나 읽기 불확실성을 생략하지 않는다.
  원문 저장 JSON과 출력 응답 계약은 바꾸지 않는다. `tools/audit_prompt_payload.py`는 저장된
  요청의 복원·참조 일치와 전송 문자 수를 검사한다(토큰 수·정확도 측정이 아님).
- 줄 정렬은 유일한 정확 일치만 채택한다. 반복 문구나 복수 줄 조합이 같은 선택 원문을
  구성하면 최초 일치 위치로 확정하지 않는다. 이 경우 영역 출처와 불확실성을 유지한다.
- 응답 `call_history`는 재시도·분할 이전 실패의 오류/usage/시간/실패 모델 응답도 보존한다.
  분할 조상은 첫 하위 응답에 한 번만 붙이므로 전체 rows의 이력을 모아 시도량을 계산한다.
  `physical_results`는 최종 응답 묶음 수다. 실제 기록된 판정 시도는 `recorded_judge_attempts`이며
  구 체크포인트에는 이력이 없을 수 있으므로 `call_audit_complete`를 함께 확인한다.
- fine 근거의 `parent_evidence_id`로 시인성 관측을 연결하고 선택된 원문 줄의 스타일만
  전달한다. 모델에서도 원문 줄과 같은 L 별칭을 사용하며 영역 측정은 청크 측정으로 바꾸지 않는다.
- `--context-char-budget`(기본 2400)은 seed 외 같은 원본 영역의 문맥을 추가하는 본문 예산이다.
  광고·상품·파일·페이지 경계를 넘지 않고, 예산 초과 그룹은 통째로 보류·감사한다.
  discovery의 `evidence_context`는 추가/보류 ID를 기록한다. 관계 의미가 전수 확인됐다는
  뜻이 아니며 cross-region 각주 관계는 별도 파서 계약/소비 구현이 필요하다.
- `schemas/proposals/parser-handoff-vnext.schema.json`은 파서 담당자 협의용이다.
  현재 P1/P3 어댑터가 이 버전을 자동 수용하지 않는다. 문서 예시와 함께 Node 계약 검사로 검증한다.

```text
파서 P1 nh-ad-review-evidence-v6
파서 P3 nh-ad-review-region-input-v1
        │
        ▼
nh-ad-review-integrated-input-v1
        │
        ├─ coarse: 원본 region 전문
        └─ fine: 불릿·길이 기반 검색용 뷰
                │
                ▼
Elasticsearch BM25 + BGE-M3 → RRF 규칙 발견
                │
                ▼
규제목록 v2 입력요건 게이트 → 적용성·판정 동시 검사
                │
                ▼
적용 규칙 + 광고 근거 → Gemma 구조화 판정
                │
                ▼
operational-e2e-result-v1
```

2026-09-09 사용자 결정으로 일반 템플릿 HWPX가 주 심의 기준이며 규제목록 v2는 세부
규칙·법령 근거를 보완한다. `--template-hwpx`를 지정하면 원문 구분·필수여부·기재요령을
독립 `TPL-` 항목으로 적재하고, 확인된 상세 상품군에 해당하는 항목을 전개한다.
v2 item ID 매핑은 전제조건이 아니다. 설정이 없는 기존 실행은 v2 T행 경로를 유지한다.
광고 ID별 답, 사례별 예외, 연구원 O/X는 운영 코드가 읽지 않는다.

### 템플릿 원문 적재와 검증

```powershell
python tools/ingest_template_hwpx.py --source C:\data\general-template.hwpx --output-dir C:\work\template-v1
```

`source.json`은 모든 section XML과 header의 스타일 정의, 표·고유 물리 셀·병합 범위,
중복 문단, run 스타일 참조, 이미지 참조를 보존한다. `catalog.json`은 원문 셀을 참조하는
`review-template-catalog-v1` 항목이며, `validation.json`은 구조 검증 보고서다.
중첩 표는 부모 셀에 연결하고 독립 규칙으로 중복 전개하지 않는다. 필수여부 헤더 누락,
알 수 없는 기호, 의미 열 사이 병합, 이미지·중첩표는 구조 검토 사유로 남긴다.
구조 검토 항목은 자동 판정에서 보류하며 원본 참조를 유지한다.

운영 실행에는 `--template-hwpx C:\data\general-template.hwpx`를 추가한다. API 환경변수는
`NH_TEMPLATE_HWPX_PATH`다. 실행기는 적재한 원본·카탈로그를 보존하고, 모델 요청에 해당
행의 `template_basis`를 포함하며, source SHA를 판정 전에 고정한다. 소배치 복구 결과에도
같은 기준 참조를 보존한다. 템플릿 원문 변경 시 항목 ID도 달라져 구버전 답지·캐시와 혼용하지 않는다.
원문 파싱은 로컬 XML 적재이며 광고 OCR/VLM 서비스와 별개다. 실제 시각 검수는 별도로 필요하다.

## 실행 순서

### 1. 파서 P1/P3를 통합하고 검색 문서를 만든다

```powershell
python tools/prepare_operational_inputs.py `
  --batch-root C:\data\parser-output `
  --out C:\work\prepared
```

출력은 `integrated/*.json`, `evidence_coarse.jsonl`, `evidence_fine.jsonl`,
`manifest.json`이다. 입력 전문은 `integrated`가 정본이고 coarse/fine은 언제든 다시
만들 수 있는 검색용 투영본이다.

### 2. 계약을 검사한다

```powershell
python tools/validate_operational_contracts.py prepared `
  --inputs-dir C:\work\prepared\integrated `
  --coarse C:\work\prepared\evidence_coarse.jsonl `
  --fine C:\work\prepared\evidence_fine.jsonl
```

### 3. 운영형 검색·판정을 실행한다

```powershell
python tools/run_operational_e2e.py `
  --inputs-dir C:\work\prepared\integrated `
  --coarse C:\work\prepared\evidence_coarse.jsonl `
  --fine C:\work\prepared\evidence_fine.jsonl `
  --regulation C:\data\NH_광고심의_에이전트_규제목록_v2.xlsx `
  --output-dir C:\work\run-001 `
  --es-index nh-rules-v2-operational-core `
  --execute-judgment
```

실행 전 `.env.example`을 참고해 환경변수를 설정한다. 내부 IP, 계정, SSH 키 경로는
코드나 커밋에 넣지 않는다.

## 운영 API

운영에서는 긴 CLI가 끝날 때까지 HTTP 연결을 유지하지 않는다. 요청은 영속 작업으로
저장하고 즉시 `202 + job_id`를 반환한다.

```powershell
python tools/serve_operational_api.py --host 0.0.0.0 --port 8088
```

```http
POST /v1/reviews
X-API-Key: <NH_RAG_API_TOKEN>
Content-Type: application/json

{
  "schema_version": "operational-review-request-v1",
  "client_request_id": "external-request-001",
  "document": { "contract": { "version": "nh-ad-review-integrated-input-v1" } },
  "routing_overrides": { "product_group": "예금성" },
  "execute_model": true
}
```

- `GET /v1/reviews/{job_id}`: 진행 상태
- `GET /v1/reviews/{job_id}/result`: 완료 결과
- `POST /v1/reviews/{job_id}/retry`: 중단·실패 작업 재시도
- `GET /health`: 프로세스와 v2 파일 준비 상태

서버 재시작 중이던 작업은 `INTERRUPTED`로 복구되며 명시적 재시도가 가능하다. 모델
출력 일부가 계약을 위반하면 정상 쌍을 보존하고 누락 쌍만 1회 소배치 재호출한다.
같은 `client_request_id`와 동일 입력을 다시 보내면 기존 job을 반환하고, 다른 입력으로
키를 재사용하면 거부한다. 작업 timeout은 기본 30분이며 전체 시도는 최대 3회다.

### 운영 후보·판정 게이트

- 실행 시작 시 규제목록 v2 전체 행과 활성 템플릿 규칙을
  `rule-applicability-contract-v2`로 컴파일한다. 현재 상품 범위 밖 규칙도 원본 ID 중복,
  범위 문구 누락 여부를 전수 감사하되 모델에는 현재 광고에 해당하는 후보만 전달한다.
- 판정은 `SCOPE → A1..An 적용조건 → U1..Un 검토조건 → O1..On 의무` 순서를 강제한다.
  v2 비고의 범위 제한을 SCOPE에 보존하고, 기준 원문 O1과 승인 가이드의 명시 requirements를 각각 검사한다.
  O ID 누락·중복·임의 병합을 거부한다. 원문 복합문장은 SOURCE_TEXT_ONLY로 표시하며 의미 원자화 완료로 취급하지 않는다.
  구버전 저장 결과는 읽을 수 있지만 새 계약 검증을 받은 것으로 승격하지 않는다.
  대상자·상품·상황·매체·절차 한정은 점검문구와 판정기준 원문 전체로 확인하며,
  조건 ID의 누락·순서 변경 또는 조건 불충족 상태의 의무 판정은 출력 계약 오류다.
- 범위 또는 적용조건이 불충족이면 `NOT_APPLICABLE`과 빈 `requirement_checks`를
  출력한다. 적용되지 않은 규칙에 O1 의무 점검을 억지로 생성하지 않는다.
- 조건의 참·거짓을 `단`, 키워드 또는 광고 파일명만으로 확정하지 않는다. 구조화된 원문·승인
  가이드와 같은 광고 문맥의 근거를 사용하고 확인할 수 없으면 의무를 판정하지 않고
  `UNDETERMINED`로 보낸다.
- `product_group`은 `confirmed|verified|provided` 상태만 하드 필터로 사용한다. 없으면
  모델을 호출하지 않고 입력 보완으로 종료한다.
- T 규칙은 확인된 `template_id` 또는 `product_subtype`과 정확히 일치하는 섹션만
  판정하고 나머지는 `deferred_template_rule_ids`에 남긴다.
- 표시의무·양식은 확인 상품군의 v2 규칙을 전개하고 금지는 하이브리드 검색한다.
  운영 기본 경로에서는 규제목록 v2의 입력요건으로 검사 가능한 후보를 가른 뒤 Gemma가
  적용성과 판정을 한 번에 수행한다. 별도 Gemma 1차 적용성 검사는 정확도 비교를 위한
  `--enable-applicability-screen` 실험 옵션이며, 켜도 그 결과만으로 후보를 제거하지 않는다.
- 규칙별 BGE-M3 근거를 제공하되 짧은 광고(기본 12,000자 이하)는 coarse 전문도
  함께 제공한다. 부분 파싱이나 축소 창은 광고 전체 부재의 증명이 아니므로
  `MISSING` 확정을 금지한다.
- 텍스트로 전부 검사 가능한 규칙은 `TEXT`, 추가 자료 요건이 함께 있는 규칙은
  `PARTIAL`, 현 입력으로 검사할 부분이 없는 규칙은 `EXTERNAL`로 나눈다.
  `PARTIAL`은 텍스트 요건만 검사하고 전체 충족 확정을 금지한다. `EXTERNAL`은 보류한다.
- `광고물(원본형식)`이라는 열 값만 보고 일괄 보류하지 않는다. 파서가 정확한 줄 분할과
  스타일을 보존했다면 줄바꿈·구분기호 같은 텍스트 형식 규칙은 검사한다. 반대로 bbox,
  글자 크기, 색상, 위치가 필요한 레이아웃 규칙은 해당 관측값이 없으면 보류한다.
- 광고 전문 검사가 완료된 표시의무 규칙에서 적용성이 확인되고 필수 구성요소가
  `MISSING`이면 전체 결과를 `UNDETERMINED`로 후퇴시킬 수 없다. 출력 계약 위반으로
  거부하고 해당 소배치 또는 규칙만 재처리한다.
- 모델 호출 계약은 긴 `ad_id`/`item_id`/evidence ID/line ref를 반복 생성하지
  않고 `R1`/`E1`/`L1` 별칭을 쓴다. 실행기가 검증 후 정본 ID로 복원하므로
  최종 저장·화면 계약은 기존 ID를 유지한다.
- 각 `requirement_check` 결과에는 `finding_basis=OBSERVED|ABSENCE|UNKNOWN`을
  기록한다. `VIOLATED`는 직접 관찰 근거, `MISSING`은 전체 검사가 완료된
  부재, `UNDETERMINED`는 입력 부족이어야 한다. 이 구분으로 부재 판정을
  `VIOLATED`로 바꾸어 검증을 우회하는 것을 감사한다.
- 본판정에서 미해당으로 확인한 항목은 운영 목록에서 제외하고 `excluded_candidates`에
  원출력을 보존한다. 실험용 1차 결과는 이 결정을 대체하지 않는다. 요청/응답 수는
  이 감사 기록을 포함하므로 화면 항목 수와 다를 수 있다.
- 답지 생성의 미해당 표본과 운영 검사는 분리한다. 위 제외 판단은 모델의 추론이므로
  별도 적용성 검수 없이는 정확한 필터라고 보증하지 않는다.
- 금지 규칙은 광고 fine 청크에서 v2 규칙을 BM25+BGE-M3로 검색하고 RRF로 결합한 뒤,
  DGX의 `bge-reranker-v2-m3`로 후보 순서만 재정렬한다. 리랭커 점수 임계치로 후보를
  삭제하지 않으며 후보 상한과 검색·재정렬 흔적을 결과에 남긴다.
- 심의필 자리표시, 불릿 종류, 날짜 표현은 광고 전체 텍스트에서 기계 관측값으로
  제공해 형식 차이만으로 위반을 만드는 것을 차단한다.
- 접수자가 확인한 `review_stage`, `association_pre_review`,
  `external_evidence_available`은 출처와 상태를 붙여 적용조건에 사용한다. 사전심의에서는
  최종 심의필 번호가 아직 발급되지 않은 것으로 보며 `0000-0000` 등 자리표시 형식도
  심의필 번호 형식이 존재하는 것으로 본다.
- A4 이상 여부·8pt·대비 등 시인성 수치 계산은 파서/OCR 단계의 책임이다. RAG는
  `regions[].visibility`와 페이지 물리 크기를 재계산하지 않고 그대로 판정 근거로
  전달한다. 파서 관측값이 없으면 텍스트나 파일명으로 추정하지 않는다.
- 모델 confidence는 보정된 확률이 아니다. 모든 `VIOLATION`과 `UNDETERMINED`는
  자동 확정하지 않고 연구원 검토 대상으로 보낸다.

### 다상품 광고와 연관 광고

- 등록 입력은 `operational-ad-intake-v1`을 사용한다. `assets[]`에는 동일 광고를 구성하는
  원본 파일을, `products[]`에는 상품별 상세 상품군과 파일·페이지 범위를,
  `shared_asset_scopes`에는 공통 문구 범위를 기록한다. 모든 자산은 상품 또는 공통 범위에
  배정되어야 하며, 미배정·중복 범위가 있으면 파서 실행 전에 사람 확인으로 중단한다.
- 접수 계약의 `product_classification_code`는 사용자 선택값이다. 내부 `template_id`는
  활성 v2 매핑으로 파생하며 고객 입력으로 받지 않는다.
- 한 광고에 상품이 여러 개 있으면 `document.products[]`에서 상품명, 상품별 라우팅,
  상품 전용 `evidence_ids`를 나누고 공통 문구는 `shared_evidence_ids`에 한 번만 둔다.
  상품마다 `template_id`를 따로 가질 수 있으므로 같은 템플릿이라고 가정하지 않는다.
- 실행기는 공통 증거와 상품 전용 증거를 합쳐 상품별 독립 scope를 만들고 결과를
  `(ad_id, product_id, item_id)`로 구분한다. 공통 문구는 각 상품 scope에서 같은 규칙으로
  검사하되 상품별 템플릿·조건·판정은 섞지 않는다. 모든 영역이 상품 또는 공통으로
  배정되지 않았으면 그때만 입력 보완으로 중단한다.
- 잘린 동일 광고는 하나의 `ad_id` 아래 자산·페이지로 복원한다. 서로 다른 광고를
  랜딩페이지·연속노출 등으로 함께 볼지는 별도 `review_case_id`와 관계 종류가 확정된
  경우에만 연결한다. 앞 광고의 판정을 뒤 광고의 정답으로 복사하지 않는다.

### 여러 광고 실행과 대기열

- `POST /v1/reviews`는 즉시 `job_id`를 반환하므로 사용자는 브라우저를 계속 붙잡지
  않고 다른 업무를 할 수 있다. 로컬 시연 등록 화면은 서로 다른 광고 파일을 최대
  20건 선택해 각각 독립 job으로 등록·요청한다. 같은 광고를 나눈 파일은 이 배치에
  넣지 않고 한 광고의 자산으로 묶어야 한다.
- GPU 동시처리가 검증된 환경에서는 `NH_RAG_QUEUE_WORKERS`를 늘려 광고 작업을
  병렬화할 수 있다. 광고를 한 프롬프트에 섞지 않고 광고별 요청은 독립적으로 유지한다.
  한 작업 내부의 규칙 판정은 `NH_RAG_MODEL_WORKERS`와 규칙 배치 크기로 이미 병렬화한다.
- 병렬 worker 수는 처리시간 측정과 GPU 메모리·오류율 비교 후 정한다. 병렬화는 총
  대기시간을 줄일 수 있지만 광고 한 건의 계산량 자체를 없애지는 않는다.
- 중간 개발·보고의 무거운 실행은 DGX Spark, 최종 DAP 반입은 H200 프로필을 사용한다.
  BGE-M3·리랭커·Gemma는 동일 HTTP 계약과 `NH_GPU_*` 설정을 사용하며 장비별 주소와
  인증만 바꾼다. 로컬 프론트·API는 작업 조정과 화면 표시를 담당하고 GPU 서비스가
  끊겼을 때 CPU 모델로 자동 후퇴하지 않는다.

### 템플릿 판정 가이드

이 절의 기존 `review-decision-guide-v1`은 v2 보완 가이드에만 적용한다. 일반 템플릿
HWPX의 독립 `review-template-catalog-v1`에는 v2 매핑 필수 제한을 적용하지 않는다.
템플릿의 필수 여부와 기재 요령은 내부 심의 기준으로 직접 사용하고, 예시문구는 의미상
예시로 사용한다. 근거 법령이 없는 항목에 조문을 생성하지 않는다. 템플릿 밖 쟁점은
v2 일반 검색을 통해 계속 검사한다.

- 규제목록 v2는 세부 적용조건·법적 근거의 보완 기준이다. 일반 템플릿 HWPX는 독립
  `TPL-` 규칙을 만들며 v2 item ID가 없어도 판정에 들어간다.
- 심의사례 표는 운영 규칙으로 적재하지 않는다. v2용 별도 업무 가이드를 사용할 때만
  `review-decision-guide-v1`로 정규화해 기존 v2 `item_id`에 붙인다.
- 충족 예시는 완전일치 문구가 아니며 표현 변형을 폭넓게 인정한다. 가이드는 새 규칙을
  만들거나 v2 적용범위를 넓힐 수 없고, 활성 v2 파일 SHA-256과 다르면 실행을 거부한다.

### 불완전 위반 답지의 평가 범위

- 수요사가 위반 항목만 제공한 광고는 `known-positive` 답지다. 제공된 위반의 발견
  Recall은 계산할 수 있지만, 목록에 없는 규칙을 자동으로 충족·미해당·오탐으로 간주해
  전체 정확도나 Precision을 계산하지 않는다.
- 시스템이 다른 위반 후보를 찾으면 오답으로 버리지 않고 `미채점 신규 후보`로 분리해
  사람 판정을 받는다. 전수 답지가 부담되면 여러 검색기의 후보 합집합과 계층별 음성
  표본만 검수하는 pooling 방식으로 충족·미해당·판단불가 라벨을 늘린다.

### 4. 계약 미충족 모델 출력만 소배치 복구한다

모델 호출이 끝났지만 일부 광고-규칙 쌍이 출력 계약을 통과하지 못했다면 전체 광고를
다시 판정하지 않는다. 유효 응답을 보존한 채 누락 쌍만 작은 배치로 만든다.

```powershell
python tools/recover_operational_judgments.py build `
  --requests C:\work\run-001\02_judgment_requests.jsonl `
  --responses C:\work\run-001\03_judgment_responses.json `
  --output C:\work\run-001\05_recovery_requests.jsonl `
  --batch-size 4
```

복구 요청을 `run_gemma_exhaustive_dgx.py`로 실행한 뒤 원 응답과 복구 응답을 함께
최종 결과로 조립한다. 복구 도구는 판정값을 고치지 않으며 계약 유효 응답만 합친다.
이미 실패한 request가 식별된 경우 `--request-id`를 반복 지정해 해당 요청만 재호출하고,
선택 목록은 응답의 `execution.selected_request_ids`에 감사 기록으로 남긴다.

웹 운영 연결에서 같은 광고에 여러 파일을 첨부하면 최초 파서는 파일 묶음을 한 번에 처리한다.
일부 파일의 P1/P3 산출물만 누락되거나 배치가 부분 실패하면, 완성된 자산은 보존하고 누락
파일만 독립 입력으로 한 번 재시도한다. 재시도 뒤에도 남은 실패는 파일명·사유·로그를
`parser-failure.json`에 보존하며 해당 광고의 검색·판정은 시작하지 않는다.

```powershell
python tools/recover_operational_judgments.py finalize `
  --requests C:\work\run-001\02_judgment_requests.jsonl `
  --discovery C:\work\run-001\01_discovery.json `
  --freeze C:\work\run-001\FREEZE_BEFORE_PREDICTION.json `
  --responses C:\work\run-001\03_judgment_responses.json `
  --responses C:\work\run-001\06_recovery_responses.json `
  --output C:\work\run-001\04_operational_results.json
```

### 5. 결과 계약을 검사한다

최종 결과는 모델 값만 나열하지 않는다. 결정적 관측·라우팅·입력능력 가드레일을 통과한
후보마다 템플릿 원문 또는 규제목록 v2의 `rule_basis`와 사용 증거 `decision_trace`를
필수로 저장한다. 템플릿에 조문이 없으면 출처 근거만 기록하고 법령 근거를 만들지 않는다.
최상위 `audit`에는 요청·응답 모델, 검색 방식·인덱스·질의 변형, 규칙 원본 SHA-256,
가드레일·validator 해시를 기록한다.

글자 크기·대비·배치·원본형식이 필요한 규칙은 실제 파서 관측값이 있을 때만 실행하고,
없는 경우 해당 규칙만 사람 검토로 보낸다. AI 실행 완료 뒤의 사람 승인·반려는 판정 JSON을
수정하지 않는 별도 불변 업무 기록이지만 현재 PoC 화면에서는 기본 비노출이다.

```powershell
python tools/validate_operational_contracts.py result `
  --path C:\work\run-001\04_operational_results.json
```

### 6. 오프라인 회귀 검사를 실행한다

```powershell
python tools/run_rag_ci.py
```

### 7. 예측과 사람 판정을 분리해 평가한다

평가 대상 예측을 먼저 봉인하고, 모델 verdict·reason·confidence·decision trace가 제거된
검수 패킷만 사람에게 전달한다. 두 명 이상이 독립 판정하고 불일치는 최종 조정자가
확정한다. `GOLD_READY`가 되기 전에는 평가를 실행할 수 없다.

```powershell
python tools/manage_blind_evaluation.py freeze `
  --prediction C:\work\run-001\04_operational_results.json `
  --output C:\work\evaluation\prediction-freeze.json `
  --dataset-id HOLDOUT-001 `
  --split BLIND_HOLDOUT `
  --unseen-confirmed-by reviewer-lead `
  --unseen-confirmed-at 2026-09-14T10:00:00+09:00

python tools/manage_blind_evaluation.py packet `
  --prediction C:\work\run-001\04_operational_results.json `
  --freeze C:\work\evaluation\prediction-freeze.json `
  --output C:\work\evaluation\blind-review-packet.json

python tools/manage_blind_evaluation.py seal `
  --packet C:\work\evaluation\blind-review-packet-reviewed.json `
  --output C:\work\evaluation\human-labels.json `
  --minimum-reviewers 2

python tools/manage_blind_evaluation.py evaluate `
  --freeze C:\work\evaluation\prediction-freeze.json `
  --labels C:\work\evaluation\human-labels.json `
  --output C:\work\evaluation\evaluation-result.json
```

기존 19건과 개발 중 반복 확인한 광고는 `DEV_REGRESSION`만 사용한다. 새 미관찰 광고에
확인자·시각 선언이 있을 때만 `BLIND_HOLDOUT`을 허용한다. 출력 계약 실패는
`OUTPUT_CONTRACT_FAILURE`, 과적용·미탐·과신·미해결·판정 반전은 서로 다른 오류유형으로
집계한다.

## 코드 경계

- 운영 구현: `rag/contracts/`, `rag/parsing/`, `rag/templates/`, `rag/judgment/`,
  `rag/api/`, 아래 정본 CLI와 직접 의존 모듈
- 평가: `rag/evaluation/`, `tools/manage_blind_evaluation.py`, `tools/eval_*`,
  `tools/validate_gold_*`; 운영 진입점에서 import 금지
- 답지/검수표 생성: `tools/build_*review*`, `tools/prepare_answer*`; 운영 진입점에서 import 금지
- 과거 코드: `tools/_legacy/`; 신규 운영 코드에서 import 금지

현재 작업 폴더에는 다른 실험 변경도 남아 있으므로 `git add .`을 사용하지 않는다.
정본만 스테이징할 때는 다음 명령을 사용한다.

```powershell
git add --pathspec-from-file=CANONICAL_FILES.txt
git diff --cached --check
```

정본 CLI는 다음 네 개다.

- `tools/prepare_operational_inputs.py`
- `tools/run_operational_e2e.py`
- `tools/recover_operational_judgments.py`
- `tools/validate_operational_contracts.py`

## 평가 경계

로컬 검수 기준 시연은 운영 실행과 별도다. 표시 어댑터만 검수표를 읽고 출처를
표시하며, 원본 Gemma 예측·요청·해시를 덮어쓰지 않는다. 시연의 충족·위반 수를 모델
성능으로 보고하지 않는다. 적용성 응답 계약 통과도 의미 판단의 정확성 보증이 아니다.

답지가 없어도 입력 준비, 검색·판정 실행, 계약 검증, 누수 검사, 지연시간 측정은 할 수
있다. 검색 Recall과 위반·충족·누락 정확도는 규제목록 v2 해시와 결합된 사람 확정
gold가 있어야 계산한다. 피드백을 보고 코드를 바꾼 데이터는 dev/regression이며 최종
성능은 별도의 미관찰 holdout에서만 보고한다.
