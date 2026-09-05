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

### 4. 결과 계약을 검사한다

```powershell
python tools/validate_operational_contracts.py result `
  --path C:\work\run-001\04_operational_results.json
```

### 5. 오프라인 회귀 검사를 실행한다

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

정본 CLI는 다음 세 개다.

- `tools/prepare_operational_inputs.py`
- `tools/run_operational_e2e.py`
- `tools/validate_operational_contracts.py`

## 평가 경계

답지가 없어도 입력 준비, 검색·판정 실행, 계약 검증, 누수 검사, 지연시간 측정은 할 수
있다. 검색 Recall과 위반·충족·누락 정확도는 규제목록 v2 해시와 결합된 사람 확정
gold가 있어야 계산한다. 피드백을 보고 코드를 바꾼 데이터는 dev/regression이며 최종
성능은 별도의 미관찰 holdout에서만 보고한다.
