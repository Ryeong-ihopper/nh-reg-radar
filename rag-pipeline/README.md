# NH 광고심의 RAG 정본

파서 결과를 광고 근거 청크로 변환하고, 규제목록 v2에서 적용 규칙을 검색한 뒤
Gemma 구조화 판정을 수행하는 독립 실행 코드입니다.

전체 입력 계약, 실행 순서, 데이터·평가 경계는
[RAG_PIPELINE.md](RAG_PIPELINE.md)를 참조하십시오.

## 빠른 확인

```bash
python tools/run_rag_ci.py
python tools/prepare_operational_inputs.py --help
python tools/run_operational_e2e.py --help
python tools/serve_operational_api.py --help
python tools/manage_blind_evaluation.py --help
```

운영 서비스는 파서 이후의 `nh-ad-review-integrated-input-v1` 한 건과 수요사 또는
접수 시스템이 확인한 상품군을 받아 비동기 작업으로 처리한다. `POST /v1/reviews`는
즉시 작업 ID를 반환하고 상태·결과는 별도 조회한다. 모델 confidence는 자동 승인에
사용하지 않으며 위반·판단불가는 항상 연구원 검토 대상으로 남는다.

## 포함 범위

- 파서 P1/P3 동일성 검증과 통합 입력 생성
- coarse/fine 광고 근거 청킹
- 규제목록 v2 C/D/T 후보 검색
- Elasticsearch BM25와 BGE-M3 벡터 검색의 RRF 결합
- Gemma 구조화 판정과 결과 계약 검증
- 운영 코드와 답지·연구원 피드백의 누수 방지 검사
- 예측 봉인·블라인드 사람 검수·오류유형 평가

원본 광고, 규제목록 파일, 답지, 연구원 검수표와 실행 결과는 저장소에 포함하지 않습니다.

## 저장된 실행 결과를 기존 웹에서 확인

저장소 루트의 `scripts/serve-operational-review.py`는 `apps/frontend` 빌드와
기존 백엔드 조회 API에 실제 운영형 판정 결과를 연결하는 로컬 읽기 전용 도구입니다.
백엔드 의존성 외에 `pypdfium2`, `Pillow`가 필요합니다. 입력 경로는 모두 명시합니다.

아래 `/private/...`는 예시 자리표시자이므로 실제 파일 경로로 바꿔야 한다. Windows
PowerShell에서는 bash의 `\` 줄 연결을 사용하지 않고 다음처럼 백틱을 사용한다.

```powershell
.\.venv\Scripts\python.exe scripts\serve-operational-review.py `
  --result C:\work\run\04_operational_results.json `
  --requests C:\work\run\02_judgment_requests.jsonl `
  --integrated C:\work\input\advertisement.json `
  --original C:\work\original\advertisement.pdf `
  --static-dir apps\frontend\dist `
  --state-dir C:\work\viewer `
  --port 5180
```

Linux/Jupyter terminal에서는 저장소 전용 Python 환경과 Linux 파일 경로를 사용한다.
원격 Jupyter라면 `localhost:5180`을 사용자 PC에서 직접 여는 대신 Jupyter server proxy의
`/proxy/5180/` 경로를 사용한다.

`viewer-session.json`의 일회용 `open_url`로 접속하면 기존 인증 절차의 세션을
발급받아 결과 화면으로 이동합니다. 이 파일에는 로컬 접속 정보가 있으므로 Git에
추가하지 않습니다. 서버는 loopback에만 바인딩하며 신규 심의 등 변경 요청은 차단합니다.
서버 재시작 시 원본 결과에서 조회 모델을 다시 구성합니다.

화면의 3종 판정 계약에 맞춰 위반은 수정 필요, 판단불가는 확인 필요로 표시합니다.
충족·미해당은 적정 그룹으로 분류하되 제목과 사유에 원판정을 보존합니다.
규칙 직접 연결에는 `RULE_METADATA`를 사용하며 검색 점수 미제공을 명시합니다.
광고유형 `NOTICE`는 화면 호환값으로만 사용하며 판정 입력에는 반영하지 않습니다.
PDF는 200 DPI로 렌더링하고 입력의 실제 line_ref 좌표로 위치를 표시합니다.
이 연결은 신규 업로드→검색→판정의 운영 웹 통합이나 판정 정확성 검증을 뜻하지 않습니다.

### 실제 자동심의 연결 (기본 동작)

기본적으로 저장소의 `temp/operational-config.local.json`을 읽고 기존 광고 등록·검토
요청·진행·결과 화면에서 실제 파서와 정본 검색·판정기를 실행합니다. 다른 설정은
`--execution-config /private/operational-config.json`으로 지정합니다. 저장 결과만 확인할
때에만 `--read-only`를 명시합니다.
프런트엔드는 `VITE_OPERATIONAL_REVIEW=true`로 빌드합니다. 이 옵션을 끈 일반 제품
빌드 및 production PostgreSQL/Redis worker에는 영향을 주지 않습니다.

설정 파일 필수 항목은 `regulation_path`, `es_url`, `es_index`, `model`,
`parser_revision`입니다. 선택 항목은 `dgx_host`, `dgx_key`, `parser_env`이며 실제
주소·경로·인증은 비공개 설정으로만 주입합니다.
파서는 저장소의 `parser-pipeline/`(nh-parser-fin subtree)만 사용합니다. `parser_runner`는
`nh_parser_fin`, `parser_contract_profile`은 `region-v11`만 허용하며 `run.py --compact-output`의
`final/*.p1.json`·`*.p3.json`(P1 v6/P3 v11)을 정본 P1/P3 계약으로 변환합니다.
`parser_revision`에는 `parser-pipeline` squash 커밋의 `git-subtree-split` 40자리 값을 넣습니다.
`parser_root`·`parser_cwd`를 생략하면 `parser-pipeline/`을, `parser_python`을 생략하면 그
폴더의 `.venv`를 사용합니다. 이전 계약(v3/v6, v4/v9, v5/v10)의 저장 결과는 읽기만 지원합니다.
웹 Python에는 backend 의존성과 `pypdfium2`, `Pillow`, `numpy`, `openpyxl`, `requests`가,
파서 Python에는 `parser-pipeline`의 별도 의존성(`pypdfium2==5.12.0`)과 GPU 서비스 설정이 필요합니다.

Python 기준은 3.11이다. 운영 의존성은 `requirements-rag.txt`, 테스트·Ruff까지 포함한
개발 의존성은 `requirements-rag-dev.txt`로 설치한다. 중간 보고는
`config/runtime.dgx.example.json`, 최종 DAP 반입은 `config/runtime.h200.example.json`을
복사해 실제 비공개 경로·주소를 채운다. 두 프로필 모두 동일 파이프라인을 실행하며
`model_env`의 `NH_GPU_*` 주소만 달라진다.

PaddleOCR는 Python 3.11을 사용하지만 NumPy 1.26 계열 의존성 때문에 DAP/RAG 환경과
분리된 서비스로 실행한다. `pytest`와 Ruff는 개발 검증 전용이며 고객사 운영 커널에는
필수가 아니다. 현행 파이프라인은 LangGraph를 import하지 않으므로 제공 버전과 무관하게
운영 필수 목록에 추가하지 않는다.

한 광고 원본만 처리하고, 사용자가 고른 상품군/템플릿만 provided로 전달합니다.
현재 미연결인 추가 첨부 대조·추천·의견 초안·과거 규정 버전·부분범위 요청은 거절합니다.
파싱부터 새로 실행하며 광고 답지나 이전 판정 결과를 실행 입력으로 사용하지 않습니다.
원본과 작업 상태·원출력은 `state-dir/execution`에 보존합니다. 서버 재시작 중단은
실패/재분석 가능으로 복원하며, 실행 중에만 Windows 절전 진입을 억제합니다.

검증: `python -m unittest discover -s tests -p test_operational_web_bridge.py -v`
(저장소 루트). 실환경 검사는 `scripts/check-operational-execution.mjs`로 수행하며
명시한 광고에 실제 GPU 판정을 시작하므로 비용과 시간이 발생합니다.
