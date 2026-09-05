# NH 광고심의 RAG 정본 코드

이 문서는 GitHub에 올릴 운영형 코드 경로만 설명한다. 데이터, 답지, 연구원 피드백,
실행 산출물은 저장소에 포함하지 않는다.

## 정본 흐름

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
적용 규칙 전개 + 광고 근거 → Gemma 구조화 판정
                │
                ▼
operational-e2e-result-v1
```

정본 규정 입력은 `NH_광고심의_에이전트_규제목록_v2.xlsx` 하나다. 광고 ID별 답,
사례별 예외, 연구원 O/X는 운영 코드가 읽지 않는다. T행은 v2에 포함된 규칙 후보로
사용하되 파서 추정 템플릿은 배제 필터가 아니라 추적·순위 보조값으로만 사용한다.

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

- `product_group`은 `confirmed|verified|provided` 상태만 하드 필터로 사용한다. 없으면
  모델을 호출하지 않고 입력 보완으로 종료한다.
- T 규칙은 확인된 `template_id` 또는 `product_subtype`과 정확히 일치하는 섹션만
  판정하고 나머지는 `deferred_template_rule_ids`에 남긴다.
- 표시의무·양식은 확인 상품군의 v2 규칙을 전개하되 규칙별 BGE-M3 상위 근거만
  모델에 보낸다. 축소 창은 광고 전체 부재의 증명이 아니므로 `MISSING` 확정을 금지한다.
- 랜딩 캡처·레이아웃·원본형식이 필요한 규칙은 현재 텍스트 모델로 판정하지 않고
  `deferred_input_rules`로 분리한다.
- 금지 규칙은 광고 fine 청크에서 v2 규칙을 BM25+BGE-M3로 검색하고 RRF로 결합한다.
  후보 상한과 검색 흔적을 결과에 남긴다.
- 심의필 자리표시, 불릿 종류, 날짜 표현은 광고 전체 텍스트에서 기계 관측값으로
  제공해 형식 차이만으로 위반을 만드는 것을 차단한다.
- 모델 confidence는 보정된 확률이 아니다. 모든 `VIOLATION`과 `UNDETERMINED`는
  자동 확정하지 않고 연구원 검토 대상으로 보낸다.

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

```powershell
python tools/validate_operational_contracts.py result `
  --path C:\work\run-001\04_operational_results.json
```

### 6. 오프라인 회귀 검사를 실행한다

```powershell
python tools/run_rag_ci.py
```

## 코드 경계

- 운영: `rag/operational/`, 아래 정본 CLI, 그리고 그 직접 의존 모듈
- 평가: `tools/eval_*`, `tools/validate_gold_*`; 운영 진입점에서 import 금지
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

답지가 없어도 입력 준비, 검색·판정 실행, 계약 검증, 누수 검사, 지연시간 측정은 할 수
있다. 검색 Recall과 위반·충족·누락 정확도는 규제목록 v2 해시와 결합된 사람 확정
gold가 있어야 계산한다. 피드백을 보고 코드를 바꾼 데이터는 dev/regression이며 최종
성능은 별도의 미관찰 holdout에서만 보고한다.
