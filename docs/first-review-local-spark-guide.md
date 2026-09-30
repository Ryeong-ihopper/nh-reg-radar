# 처음 실행하는 NH 광고심의 — 로컬 PC와 Spark

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.6 |
| 기준일 | 2026-09-30 |
| 대상 | 코드를 받아 광고 1건을 처음 실행할 사용자와 실행을 도울 Claude |
| 환경 | Windows PowerShell, 심의 앱 Python 3.11, Node.js 22, 별도 Spark 서비스 |
| 목표 | 실제 광고 등록 → 파싱 → 규칙 검색 → 판정 → 결과 JSON 다운로드 |
| 검증 범위 | 현재 로컬 코드·설정·CLI와 대조한 안내. 새 PC에서의 설치/E2E 성공은 아직 검증하지 않음 |

## 파서: 저장소의 parser-pipeline 사용

파서는 심의 앱 저장소의 `parser-pipeline/`(nh-parser-fin subtree)에 포함된다. 별도 파서 checkout이나 패치 전달본은 필요 없다. 파서 개발 정본은 nh-parser-fin 저장소이며 이 폴더는 `git subtree pull --prefix=parser-pipeline --squash`로 갱신한다.

사용자가 고른 상세 상품군(예: 대출성상품-상품명 노출)은 심의 intake와 판정에 사용된다. 현재 파서는 템플릿을 자체 판정해 P1/P3에 기록하며, 사용자 선택 템플릿을 파서에 전달하는 기능은 후속 작업이다. 파서의 템플릿 판정을 사용자 선택값으로 간주하지 않는다.

브라우저에서는 이전처럼 상세 상품군을 선택하면 된다. 원문이 깨졌거나 선택 문장/라벨의 근거 범위를 확정할 수 없는 부분과 시인성은 사람 확인 대상으로 남는다. 과거 자동분류 결과를 재사용하지 않으므로 첫 재분석은 원문을 다시 파싱할 수 있다.

## 1. 먼저 알아둘 것

**바꿔야 하는 것은 주로 설정 파일의 데이터·파서 경로와 서비스 주소다. 코드 안의 경로를 찾아 일괄 치환하지 않는다.**

이 프로그램은 다음 순서로 실행된다.

```text
내 PC: 광고 업로드
  → 별도 파서 프로그램: 광고에서 글자·표·위치를 읽음
      → OCR 서비스와 이미지 판독 모델 호출
  → 검색: 규제목록·일반 템플릿에서 확인할 규칙과 광고 근거를 찾음
      → Elasticsearch와 BGE 서비스 호출
  → 판정: Gemma에 규칙·광고 근거를 전달
  → 내 PC: 결과 화면·JSON 다운로드
```

- Spark 접속 권한과 모델 파일만으로는 전 과정이 준비된 것이 아니다. 아래 서비스가 **실행되어 HTTP 요청을 받을 수 있어야** 한다.
- 로컬 서버는 `http://127.0.0.1:5180`에서 사용한다. 이 경로는 로컬 PoC 실행이며 제품용 Docker/PostgreSQL/Redis 전체 배포가 아니다.
- Claude가 직접 실행하려면 프로젝트 파일과 터미널에 접근할 수 있어야 한다. 일반 채팅에서 문서만 읽는 경우에는 사용자가 안내받은 명령을 실행한다.
- 이번 목적은 첫 광고 1건 실행이다. 기존 개발 진단17쌍·8쌍, 성능 실험, 파인튜닝을 실행할 필요 없다.

## 2. 전달자에게 받아야 할 준비물

### 2.1 코드와 파일

**준비물 요약:** 내 PC에는 심의 앱 코드, 별도 파서 프로그램과 실행 환경, 규제목록 XLSX, 일반 템플릿 HWPX, 심의할 광고 원본, 본인 SSH 개인키가 필요하다(SSH 방식 기준). 모델 서비스가 Spark에서 이미 실행 중이면 모델 가중치 파일을 내 PC로 받을 필요는 없다.

**설정값 요약:** SSH 계정/주소/포트와 서비스 연결 주소, 배정된 Elasticsearch 인덱스 접두사, 실제 판정 모델 ID 및 파서용 이미지 판독 모델 ID를 담당자에게 받는다. 이것들은 별도 데이터 파일이 아니라 로컬 설정에 넣을 값이다. `NH_RAG_API_TOKEN`은 이 가이드의 5180 방식에는 필수가 아니며 자세한 구분은 6.4절을 따른다.

| 준비물 | 확인할 내용 |
| --- | --- |
| 심의 앱 코드 | 이 문서와 아래 실행 파일이 포함된 동일한 전달본/commit |
| 파서 코드 | 심의 앱 저장소의 `parser-pipeline/`. HWP/HWPX 광고 파싱에만 사내 `document-processor`가 추가로 필요 |
| 규제목록 | `NH_광고심의_에이전트_규제목록_v2.xlsx` 원본 |
| 일반 템플릿 | 전달자가 지정한 일반 광고 템플릿 HWPX 원본. 심의사례 답지 HWPX로 대체하지 않음 |
| 테스트 광고 | 본인이 실행할 PDF 또는 PNG/JPG 1건과 정확한 상세 상품군 |
| Spark 접속 정보 | VPN 필요 여부, SSH 접속 대상, 개인 SSH 키 경로, 확인할 서버 지문 |
| 실행 서비스 정보 | 아래 표의 주소·포트·정확한 모델 ID·사용 가능한 검색 인덱스 접두사 |

**전달본 확인:** 초기 개발본에는 Git에 포함되지 않은 실행 파일이 있었다. 이번 전달에서는 가이드와 실제 실행 코드를 함께 확인해야 한다. 아래 대표 파일 목록과 전달자가 알려준 commit/브랜치를 대조한다. 오래된 기본 브랜치를 받았다면 전달자가 지정한 최신 작업 브랜치를 받는다. 실행자가 빠진 파일을 Claude에게 새로 구현시키지 않는다.

`scripts/serve-operational-review.py`, `scripts/operational_web_bridge.py`, `rag-pipeline/config/runtime.dgx.example.json`, `apps/frontend/.env.operational` 4개는 커밋 `e91bcf3`에 포함됐다. `feat/regulation-collection-viewer` 브랜치에서 이 커밋을 포함한 최신 전달본을 받는다. 기본 브랜치나 오래된 checkout에는 없을 수 있으므로 아래 파일 목록을 확인한다.

다른 PC의 `.venv311`, `node_modules`, 기존 `temp/operational-server`를 통째로 복사하지 않는다. 실행 환경은 새 PC에서 만들고 첫 실행 상태도 별도 폴더에 저장한다.

### 2.2 Spark 담당자에게 확인할 서비스

| 서비스 | 하는 일 | 필요한 확인 |
| --- | --- | --- |
| Gemma 판정 | 규칙과 광고 근거를 보고 판정 | `/v1/chat/completions`, 정확한 모델 ID, JSON Schema 출력 지원 |
| BGE | 검색용 숫자 벡터 생성과 검색 순위 재정렬 | 이 저장소 클라이언트의 `/health`, `/embed`, `/rerank`와 호환 |
| Elasticsearch | 한국어 규칙 검색 | Nori 사용 가능, 버전 호환, 허용된 인덱스 생성/조회/문서 적재 권한 |
| PaddleX OCR | 광고의 글자·표·영역 읽기 | 파서의 `/layout-parsing` 요청과 호환되는 실제 주소 |
| 파서용 Gemma/VLM | 광고 이미지를 보고 판독 보조 | 이미지 입력 지원, 파서가 요구하는 출력 형식, 모델 ID |

판정용 Gemma와 이미지 판독용 모델은 같은 서비스일 수도, 별도 서비스일 수도 있다. 이름이나 포트를 추측해 연결하지 않는다. BGE도 일반적인 `/v1/embeddings` 주소로 대체할 수 없다. 현재 `/embed` 클라이언트는 NumPy 바이너리 응답을 읽는다.

앱의 기본 HTTP 클라이언트가 임의의 API 인증 방식을 자동 지원하는 것은 아니다. 별도 Bearer 인증 등이 필수인 서비스라면 담당자와 지원되는 연결 방식을 확인한다. SSH 터널은 접근 경로이며 HTTP 인증을 대체하는 기능이 아니다.

**공유 Spark 장비나 모델·OCR·검색 서비스를 임의로 재시작하거나 모델을 새로 올리지 않는다.** 서비스가 없으면 담당자에게 준비를 요청한다. 첫 실행에는 기존 서비스 이용이 기본이다.

## 3. 프로젝트 위치와 코드 확인

이하 명령은 **Windows PowerShell**용이다. `C:/work/...`, `REPLACE_...`는 예시이며 본인 경로·담당자가 준 값으로 바꾼다. Windows 경로를 JSON에 적을 때는 `/`를 사용하면 편하다.

PowerShell 창 A를 열고 실제 프로젝트 폴더로 이동한다.

```powershell
$projectRoot = 'C:/work/nh-ad-compliance'
Set-Location -LiteralPath $projectRoot
Get-Location
py -3.11 --version
node --version
npm.cmd --version
git --version
ssh -V
```

프로젝트 루트는 `apps`, `scripts`, `rag-pipeline`, `docs`가 함께 있는 폴더다. 받은 폴더 안에 `nh-ad-compliance`가 한 번 더 있으면 그 안쪽일 수 있다.

Python 3.11 또는 Node.js 22가 없으면 회사에서 허용한 방식으로 설치한 뒤 터미널을 다시 연다. 설치 도중 오류가 나면 이후 명령을 계속 실행하지 않는다.

```powershell
$requiredFiles = @(
  'AGENTS.md',
  'docs/handoff-current.md',
  'docs/decisions.md',
  'docs/evaluation-splits-current.md',
  'scripts/serve-operational-review.py',
  'scripts/operational_web_bridge.py',
  'scripts/operational_locations.py',
  'rag-pipeline/config/runtime.dgx.example.json',
  'rag-pipeline/requirements-rag.txt',
  'rag-pipeline/rag/parsing/prepare_inputs.py',
  'rag-pipeline/rag/judgment/output_contract.py',
  'rag-pipeline/tools/run_operational_e2e.py',
  'apps/frontend/package-lock.json'
)
$missing = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($missing.Count) { $missing; throw '실행 코드가 빠져 있습니다. 전달본을 확인하세요.' }
git rev-parse HEAD
git status --short
```

이 확인은 대표 파일 점검이다. 전체 전달본 일치 여부는 전달자가 알려준 commit/변경 목록으로 확인한다. `git reset`, 변경 파일 삭제, 강제 checkout으로 맞추지 않는다.

Claude는 적용되는 `AGENTS.md`와 필수 문서를 읽는다. 다만 인수인계의 연구·개발 재개 작업을 시작하지 말고 **이 문서의 첫 실행 목적**을 따른다.

## 4. 앱과 파서의 Python 환경 만들기

### 4.1 심의 앱 — 창 A, 프로젝트 루트

```powershell
py -3.11 -m venv .venv311
if ($LASTEXITCODE -ne 0) { throw '앱 가상환경 생성 실패' }
.\.venv311\Scripts\python.exe -m pip install -r rag-pipeline/requirements-rag.txt -e packages/ai-providers -e packages/parser-contracts -e apps/backend
if ($LASTEXITCODE -ne 0) { throw '앱 패키지 설치 실패' }
.\.venv311\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw '앱 패키지 호환성 확인 실패' }
.\.venv311\Scripts\python.exe -c "import sys, fastapi, uvicorn, pypdfium2, PIL, numpy, openpyxl, requests, nh_ad_backend; print(sys.executable); print('APP_IMPORT_OK')"
if ($LASTEXITCODE -ne 0) { throw '앱 모듈 확인 실패' }
.\.venv311\Scripts\python.exe scripts/serve-operational-review.py --help
if ($LASTEXITCODE -ne 0) { throw '앱 실행 진입점 확인 실패' }
```

이미 환경이 있으면 버전·import부터 확인하고 불필요하게 다시 만들지 않는다. 패키지를 인터넷에서 받을 수 없는 PC는 담당자가 제공한 같은 버전의 사내 패키지 저장소/설치 파일을 사용한다. 설치가 안 된다고 고정 버전을 임의로 낮추지 않는다.

가상환경 활성화 명령은 필요 없다. 이후에도 **반드시 `.venv311/Scripts/python.exe`를 직접 지정**한다. 작업 관리자에 보이는 시스템 Python 경로를 복사해 서버를 시작하면 가상환경의 패키지를 찾지 못할 수 있다.

### 4.2 파서 — parser-pipeline 전용 환경

파서는 저장소의 `parser-pipeline/`이며 Python 3.11 기준이다. 앱과 같은 버전이지만 **파서 폴더의 `uv.lock`으로 만든 별도 `.venv`를 사용한다.** 파서는 PDF 렌더 결과를 고정하려고 `pypdfium2==5.12.0`을 사용하므로 앱 Python에 파서를 함께 설치해 버전을 덮어쓰지 않는다.

```powershell
$parserRoot = Join-Path $projectRoot 'parser-pipeline'
if (-not (Test-Path -LiteralPath (Join-Path $parserRoot 'run.py'))) { throw '파서 실행 파일이 없습니다.' }
uv sync --project $parserRoot
if ($LASTEXITCODE -ne 0) { throw '파서 가상환경 생성 실패' }
$parserPython = Join-Path $parserRoot '.venv/Scripts/python.exe'
& $parserPython (Join-Path $parserRoot 'run.py') --help
if ($LASTEXITCODE -ne 0) { throw '파서 실행 진입점 확인 실패' }
```

심의 앱은 설정에 파서 경로가 없으면 `parser-pipeline/`과 이 `.venv`를 사용한다. PaddleX·이미지 판독 모델 주소는 5절의 `parser_env` 또는 `parser-pipeline/.env`(Git 제외)에 넣는다.

첫 실행 광고는 PDF 또는 PNG/JPG를 사용한다. HWP/HWPX **광고 파싱**에는 별도 사내 문서 처리 패키지가 필요할 수 있다. 일반 템플릿 HWPX를 심의 기준으로 읽는 기능과는 별개다.

## 5. 본인 PC의 설정 파일 만들기

아래 예시는 저장소 파서 `parser-pipeline/` 기준이다. 창 A에서 `temp` 폴더를 만들고, 편집기로 `temp/operational-config.local.json`을 **UTF-8, BOM 없이** 저장한다. 기존 파일이 있으면 먼저 내용을 확인하고 본인의 필요한 값만 수정한다.

```powershell
New-Item -ItemType Directory -Force -Path temp | Out-Null
```

```json
{
  "runtime_profile": "dgx-interim",
  "regulation_path": "C:/work/nh-data/NH_광고심의_에이전트_규제목록_v2.xlsx",
  "template_source_path": "C:/work/nh-data/REPLACE_GENERAL_TEMPLATE.hwpx",
  "template_appropriate_judgment_path": "C:/work/nh-data/1. 대출성상품-상품명 노출.xlsx",
  "es_url": "http://127.0.0.1:19201",
  "es_index": "REPLACE_ASSIGNED_INDEX_PREFIX",
  "model": "REPLACE_JUDGE_MODEL_ID",
  "model_env": {
    "NH_GPU_BGE_ENDPOINT": "http://127.0.0.1:8103",
    "NH_GPU_GEMMA_ENDPOINT": "http://127.0.0.1:8102/v1/chat/completions",
    "NH_GPU_GEMMA_MODEL": "REPLACE_JUDGE_MODEL_ID",
    "NH_JUDGE_RESPONSE_FORMAT": "json_schema"
  },
  "parser_runner": "nh_parser_fin",
  "parser_contract_profile": "region-v10",
  "parser_revision": "REPLACE_PARSER_SUBTREE_SPLIT",
  "parser_env": {
    "PADDLEX_URL": "http://127.0.0.1:18081/layout-parsing",
    "GEMMA_URL": "http://127.0.0.1:18102/v1/chat/completions",
    "GEMMA_MODEL": "REPLACE_VISION_MODEL_ID"
  }
}
```

| 바꿀 항목 | 무엇을 넣는가 |
| --- | --- |
| `regulation_path` | 내 PC에 있는 지정 규제목록의 절대 경로 |
| `template_source_path` | 내 PC에 있는 지정 일반 템플릿의 절대 경로 |
| `template_appropriate_judgment_path` | 선택 사항. TPL 결과 화면에 표시할 일반 업무 가이드 XLSX의 절대 경로. 검색·모델 판정에는 사용하지 않음 |
| `parser_revision` | `git log -1 --format=%B --grep="git-subtree-dir: parser-pipeline"`의 `git-subtree-split` 40자리 값 |
| `parser_root`, `parser_cwd`, `parser_python` | 생략하면 `parser-pipeline/`과 그 `.venv`. 다른 위치의 파서를 쓸 때만 지정 |
| `model`, `NH_GPU_GEMMA_MODEL` | 판정 서비스에서 제공하는 동일한 모델 ID |
| `parser_env.GEMMA_MODEL` | 이미지 판독 서비스의 모델 ID |
| `es_index` | 담당자가 허용한 인덱스 접두사. 소문자 사용 |
| 각 URL | 아래 터널 예시를 그대로 쓰면 로컬 주소 유지. 직접 연결이면 담당자 주소로 교체 |

광고 원본 경로는 이 설정에 넣지 않는다. 웹 화면에서 파일을 선택한다. 정답표·연구원 O/X·과거 판정 결과 경로도 넣지 않는다.

첫 검색은 규칙과 벡터 해시가 붙은 인덱스를 생성하거나 기존 호환 인덱스를 사용한다. `es_index`는 임의의 기존 인덱스를 삭제·교체하라는 뜻이 아니다. **조회 권한만 있으면 최초 실행이 막힐 수 있으므로 생성/적재 권한도 확인한다.**

위 예시는 SSH 터널을 통한 직접 HTTP 연결을 사용하므로 `dgx_host`·`dgx_key`를 JSON에 넣지 않았다. 해당 필드는 별도 SSH fallback을 쓸 때만 필요하다. `REGION_READING_MODE` 등 파서 정책은 전달받은 검증 설정을 따르고 속도를 이유로 임의 변경하지 않는다.

설정 파일 전체나 개인키 내용을 채팅·Git에 붙이지 않는다. Claude는 로컬 파일을 읽되 점검 결과만 요약한다. `temp`는 이 저장소의 Git 제외 경로다.

## 6. Spark 연결하기 — PowerShell 창 B

### 6.1 SSH 터널과 리버스 프록시의 차이

**이 가이드의 기본 구성은 내 PC에서 Spark로 여는 SSH 로컬 포트 포워딩(`ssh -L`)이다.** Spark의 SSH에 접속할 수 있고 해당 계정에 포트 포워딩이 허용돼 있으면, 이 연결을 위해 Nginx 같은 HTTP 리버스 프록시를 새로 설치할 필요는 없다.

```text
내 PC 심의 앱 → 내 PC 127.0.0.1:8102 → SSH 암호화 연결 → Spark 판정 서비스
```

| 담당자가 제공한 접속 방식 | 필요한 준비 |
| --- | --- |
| Spark SSH 직접 접속 | 본인 계정·공개키 등록, SSH 포트, 서비스 포트, 포워딩 허용 여부. 아래 `-L` 예시 사용 |
| VPN 내부에서만 접속 | 승인된 VPN 연결 후 SSH 터널 실행 |
| 점프 서버를 거쳐 SSH 접속 | 점프 서버와 Spark 각각의 계정·키·호스트 지문. 담당자 제공 SSH config의 `ProxyJump` 사용. Spark에 개인키를 복사하거나 `ssh -A`를 켤 필요 없음 |
| 회사가 제공하는 HTTPS 리버스 프록시 | 담당자가 제공한 서비스별 전체 URL·경로 변환·인증 방식·인증서 신뢰 설정 사용. 기존 주소와 클라이언트 호환성 확인 |
| Spark에서 외부로 열어 둔 역방향 터널(`ssh -R`) | 담당자가 제공한 중계 서버 접속점 사용. 로컬 사용자가 Spark의 역방향 터널을 새로 만들거나 재시작하지 않음 |

회사 네트워크가 프록시 사용을 요구하면 해당 경로를 따라야 한다. 실제 중계 주소·점프 서버·인증 방식은 현재 문서로 확정할 수 없으므로 담당자에게 받아야 한다. `127.0.0.1:8102`를 인터넷에서 접근 가능한 Spark 주소라고 해석하지 않는다. SSH 서버가 기본 22번 외의 포트를 쓰면 아래 SSH 인자에 `'-p', '담당자가_준_포트'`를 추가한다.

프록시를 사용할 때는 Gemma 판정, BGE, OCR, 이미지 판독, Elasticsearch를 각각 어디로 연결하는지 확인한다. BGE의 NumPy 바이너리 응답·각 API의 요청 경로·이미지 업로드 크기·긴 응답 대기시간을 그대로 지원해야 한다. 현행 클라이언트가 프록시의 Bearer/SSO 인증을 자동 처리한다고 가정하지 않는다. 비밀 토큰을 URL에 넣거나 인증서 검증을 끄지 않는다.

`-L`, `-R`, `ProxyJump`의 의미는 [OpenSSH 설명](https://man.openbsd.org/ssh.1)을 참고한다.

### 6.2 개인키를 공유하지 않고 본인 계정으로 접속

> **실행자 필독: SSH 개인키 파일과 그 내용은 Claude, 채팅, 이메일, Git, 공유 드라이브에 올리지 마세요. 개인키 보호 암호도 전달하지 마세요. 담당자에게 등록할 것은 `.pub` 공개키뿐입니다.** 개인키가 노출됐다면 내용을 다시 보내지 말고 담당자에게 해당 공개키의 접근 권한 폐기와 새 키 등록을 요청하세요.

**사용자마다 자기 PC에서 키 쌍을 만들고, 담당자에게는 `.pub` 공개키만 전달한다.** 기존 개발자의 개인키를 복사해 받는 것을 준비물로 삼지 않는다. 회사가 별도 키/인증서 발급 절차를 운영하면 그 절차를 따른다.

1. 본인이 PowerShell에서 아래 명령을 실행한다. 이미 승인받은 본인 키가 있으면 생성 단계를 건너뛴다.
2. 생성 중 개인키 보호 암호(passphrase)를 직접 입력한다. 암호를 Claude 채팅이나 명령 인자에 쓰지 않는다.
3. `.pub` 파일만 Spark 담당자에게 보내 본인 접속 계정에 등록을 요청한다. Linux Spark에서는 일반적으로 해당 계정의 `~/.ssh/authorized_keys`에 공개키를 등록한다. 개인키는 내 PC에 둔다.
4. 담당자가 알려준 SSH 계정·주소·서버 지문으로 접속을 확인한 뒤 6.3의 서비스 터널을 연다.

```powershell
# 이 블록은 사용자가 자기 터미널에서 직접 실행한다.
$sshDirectory = Join-Path $env:USERPROFILE '.ssh'
$sshKeyPath = Join-Path $sshDirectory 'nh_review_ed25519'
if ((Test-Path -LiteralPath $sshKeyPath) -or (Test-Path -LiteralPath ($sshKeyPath + '.pub'))) {
  throw '같은 이름의 키가 있습니다. 덮어쓰지 말고 기존 키 등록 여부를 확인하세요.'
}
New-Item -ItemType Directory -Force -Path $sshDirectory | Out-Null
ssh-keygen -t ed25519 -f $sshKeyPath -C 'nh-review-user'
if ($LASTEXITCODE -ne 0) { throw 'SSH 키 생성 실패' }
# 담당자에게 전달할 파일은 확장자가 .pub인 공개키뿐이다.
Write-Host ('공개키 파일: ' + $sshKeyPath + '.pub')
```

SSH는 내 PC의 개인키로 인증용 서명을 만들며 개인키 원문을 서버로 전송하지 않는다. `ssh -i 경로`는 SSH 프로그램에 키 파일 위치를 알려주는 것이며, 키 내용을 채팅에 붙이는 것이 아니다. 자세한 절차는 [Microsoft OpenSSH 키 관리](https://learn.microsoft.com/ko-kr/windows-server/administration/openssh/openssh_keymanagement)를 참고한다.

**Claude에게는 개인키 파일 경로 또는 SSH 접속 별칭만 알려준다.** 개인키를 `Get-Content`, `cat`, 로그·스크린샷으로 읽게 하지 않는다. 파일 경로만 알려주는 것은 접근 권한 차단과는 다르다. Claude가 키 파일에 접근하는 것 자체를 막으려면 도구의 파일 접근 권한에서 `.ssh`를 제외하고, 사용자가 창 B에서 SSH 터널을 직접 실행한다. 그러면 심의 앱과 Claude는 이미 열린 로컬 포트만 사용하면 된다. `ssh-agent`를 사용하는 환경에서는 사용자가 직접 키를 등록해 암호 입력을 관리할 수 있지만, 에이전트 사용만으로 Claude의 파일 읽기 권한이 없어지지는 않는다.

처음 실행하는 사람에게는 **본인이 6.3의 터널을 직접 열고, Claude에는 “터널 연결 완료, 설정의 로컬 포트를 사용하세요”라고 알려주는 방식**을 권장한다. 이 방식에서는 Claude에게 키 파일 경로조차 알려줄 필요 없다. 키 보호 암호는 본인 터미널에 직접 입력하고 창 B는 심의가 끝날 때까지 유지한다.

### 6.3 다섯 서비스의 로컬 포트 연결

VPN이 필요하면 먼저 연결한다. 아래는 다섯 서비스를 SSH 터널 하나로 연결하는 예시다. **원격 포트의 0을 모두 담당자가 준 실제 포트로 바꾼 후 실행한다.** 각 서비스가 Spark 자신의 `127.0.0.1`에서 열려 있다는 전제다. 다른 서버에 있다면 담당자가 알려준 전달 대상 호스트를 사용한다.

```powershell
$sparkTarget = 'REPLACE_USER@REPLACE_SPARK_HOST'
$sshKeyPath = 'C:/Users/REPLACE_USER/.ssh/REPLACE_PRIVATE_KEY'
$esRemotePort = 0
$bgeRemotePort = 0
$judgeRemotePort = 0
$ocrRemotePort = 0
$visionRemotePort = 0

if (@($esRemotePort, $bgeRemotePort, $judgeRemotePort, $ocrRemotePort, $visionRemotePort) -contains 0) {
  throw '담당자가 알려준 원격 서비스 포트를 먼저 입력하세요.'
}
if (-not (Test-Path -LiteralPath $sshKeyPath -PathType Leaf)) { throw 'SSH 개인키 경로를 확인하세요.' }

$sshArgs = @(
  '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
  '-i', $sshKeyPath,
  '-L', "127.0.0.1:19201:127.0.0.1:${esRemotePort}",
  '-L', "127.0.0.1:8103:127.0.0.1:${bgeRemotePort}",
  '-L', "127.0.0.1:8102:127.0.0.1:${judgeRemotePort}",
  '-L', "127.0.0.1:18081:127.0.0.1:${ocrRemotePort}",
  '-L', "127.0.0.1:18102:127.0.0.1:${visionRemotePort}",
  $sparkTarget
)
& ssh @sshArgs
```

최초 SSH 접속에서는 담당자가 준 서버 지문과 일치하는지 확인한다. 개인키 암호가 필요하면 본인이 터미널에 입력한다. 보통 연결 후 아무 출력 없이 창이 유지된다. **광고 실행 중 이 창을 닫지 않는다.**

`Address already in use`는 로컬 포트가 사용 중이라는 뜻이다. 기존 터널의 소유자를 확인해 재사용하거나 다른 로컬 포트와 설정 URL을 함께 지정한다. 전체 `ssh` 프로세스를 종료하지 않는다.

기존 `rag-pipeline/tools/start_runtime_tunnels.ps1`도 사용할 수 있지만 그 스크립트는 ES/BGE/판정 세 포트만 연결하며 BGE/판정 원격 포트가 고정되어 있다. **OCR와 이미지 판독 연결까지 자동으로 생기는 것은 아니다.** 위 명령과 중복 실행하지 않는다.

### 6.4 `NH_RAG_API_TOKEN`은 언제 필요한가?

| 항목 | 사용처 |
| --- | --- |
| SSH 개인키 | Spark SSH 접속 인증. 내 PC에서만 사용 |
| `NH_RAG_API_TOKEN` | 별도 `rag-pipeline/tools/serve_operational_api.py` HTTP 서버의 요청 인증. 호출 시 `X-API-Key` 헤더로 전달 |
| Gemma/BGE/OCR/프록시 인증값 | 각 서비스 운영자가 지정한 별도 인증. RAG API 토큰과 자동으로 같아지지 않음 |
| 로컬 웹 로그인 | 이 가이드의 5180 화면 로그인. SSH 인증과 별개 |

**이 문서의 로컬 5180 경로는 RAG 서비스를 같은 프로세스 안에서 사용하므로 `NH_RAG_API_TOKEN`이 필수 준비물이 아니다.** 별도 RAG HTTP 서버를 호출하도록 구성한 경우에만 담당자가 발급한 해당 API 토큰이 필요하다. 5180 설정 파일에 이 이름의 값을 추가한다고 Spark 모델이나 프록시에 인증되는 것이 아니다. 별도 RAG API와 프록시가 서로 다른 인증을 요구하면 각각의 계약을 확인한다.

### 6.5 전달자가 준비할 설정값 — 인덱스 접두사와 모델 ID

10번 Elasticsearch 인덱스 접두사와 11번 Gemma 판정 모델 ID는 개인키 같은 인증 비밀이 아니라 **정확하게 일치해야 하는 연결 설정값**이다. 전달자가 이미 확인한 값을 알고 있으면 실행자에게 직접 전달해도 된다. 모르면 Spark/검색 담당자가 확인해서 제공한다. 계정·인덱스 사용 권한도 실행자에게 배정됐는지 함께 확인한다.

| 전달할 값 | 누가 확인하는가 | 실행자가 넣을 위치 |
| --- | --- | --- |
| 배정된 Elasticsearch 인덱스 접두사 | 검색 관리자. 개발자 개인의 기존 접두사를 그대로 배정했다고 가정하지 않음 | `es_index` |
| 실제 판정 모델 ID | Spark 모델 운영자 또는 해당 서비스의 `/v1/models` 조회 | `model`과 `model_env.NH_GPU_GEMMA_MODEL`에 같은 값 |
| 파서용 이미지 판독 모델 ID | 파서/Spark 담당자 | `parser_env.GEMMA_MODEL` |

**전달 방법:** 인덱스 접두사와 모델 ID 두 값 자체는 인증 비밀이 아니므로 실행자에게 일반 업무 메시지로 알려줘도 된다. 이 두 값 때문에 반드시 비공개 채널을 써야 하는 것은 아니다. 조직의 정보 공개 정책은 별도로 따른다. 전체 설정 파일에는 내부 주소·개인 경로가 함께 있을 수 있어 필요 시 승인된 비공개 채널로 전달하며, 개인키·암호·토큰은 전달용 파일에 넣지 않는다. 실행자는 5절 예시에 확인한 값을 넣어 자기 PC의 `temp/operational-config.local.json`에 저장하고 데이터·파서 경로를 바꾼다. 전체 로컬 설정은 Git에 올리지 않는다. 값 두 개만 보낼 경우에는 다음처럼 항목 이름을 붙이면 된다.

```text
Elasticsearch 인덱스 접두사(es_index): [담당자가 배정한 값]
Gemma 판정 모델 ID(model / NH_GPU_GEMMA_MODEL): [실제 서비스의 모델 ID]
대상 서비스/접속 안내: [비공개 안내 파일 위치]
```

모델 ID는 화면에 보이는 별명이나 모델 폴더 이름을 추측해 넣지 않는다. `/v1/models`는 서비스가 제공하는 경우 모델 ID를 확인하는 용도이며, 인덱스 접두사의 사용 권한을 배정해 주는 기능은 아니다. 프로그램 파일 4개는 확인된 Git 작업 브랜치로 전달하고, 이 설정값·사내 원본 자료·개인키는 코드 전달과 구분한다.

## 7. 경로·서비스 확인 — 다시 창 A

```powershell
Set-Location -LiteralPath $projectRoot
$configPath = Join-Path $projectRoot 'temp/operational-config.local.json'
$cfg = Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath | ConvertFrom-Json
foreach ($field in @('regulation_path', 'template_source_path')) {
  if (-not (Test-Path -LiteralPath $cfg.$field -PathType Leaf)) { throw "파일 경로 오류: $field" }
}
$parserPython = if ($cfg.parser_python) { $cfg.parser_python } else { Join-Path $projectRoot 'parser-pipeline/.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $parserPython -PathType Leaf)) { throw '파서 가상환경이 없습니다. 4.2절을 실행하세요.' }
if ((Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath) -match 'REPLACE_') {
  throw '설정에 아직 예시 값이 남아 있습니다.'
}
if ($cfg.model -ne $cfg.model_env.NH_GPU_GEMMA_MODEL) { throw '판정 모델 ID 두 값을 일치시키세요.' }
if ($cfg.parser_revision -notmatch '^[0-9a-f]{40}$') { throw 'parser_revision에 40자리 커밋을 넣으세요.' }
Write-Host 'LOCAL_PATHS_OK'
```

다음 점검은 광고 원문을 보내지 않는다. 위 터널 예시의 로컬 포트를 사용한다.

```powershell
$es = Invoke-RestMethod -Uri 'http://127.0.0.1:19201/' -TimeoutSec 10
Write-Host ('Elasticsearch 응답 버전: ' + $es.version.number)
$bge = Invoke-RestMethod -Uri 'http://127.0.0.1:8103/health' -TimeoutSec 10
Write-Host 'BGE health 응답 수신'
$judgeModels = Invoke-RestMethod -Uri 'http://127.0.0.1:8102/v1/models' -TimeoutSec 10
if ($cfg.model -notin @($judgeModels.data.id)) { throw '판정 서비스에 설정한 모델 ID가 없습니다.' }
$visionModels = Invoke-RestMethod -Uri 'http://127.0.0.1:18102/v1/models' -TimeoutSec 10
if ($cfg.parser_env.GEMMA_MODEL -notin @($visionModels.data.id)) { throw '이미지 판독 모델 ID가 없습니다.' }
Test-NetConnection -ComputerName 127.0.0.1 -Port 18081 -InformationLevel Quiet
```

직접 서비스 주소나 다른 로컬 포트를 선택했다면 점검 주소도 함께 바꾼다. `/v1/models`를 제공하지 않는 서비스는 담당자에게 확인된 모델 ID/점검 방법을 받는다. 조회 성공은 이미지 입력·구조화 출력·실제 OCR 성공을 보장하지 않는다. 첫 실제 광고에서 파서 출력과 판정 결과까지 확인해야 한다.

## 8. 화면 빌드와 로컬 서버 실행 — 창 A

```powershell
Push-Location apps/frontend
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw '프런트 의존성 설치 실패' }
$env:VITE_OPERATIONAL_REVIEW = 'true'
npm.cmd run build:operational
if ($LASTEXITCODE -ne 0) { throw '운영 화면 빌드 실패' }
Pop-Location

.\.venv311\Scripts\python.exe scripts/serve-operational-review.py --static-dir apps/frontend/dist --state-dir temp/first-review-server --execution-config temp/operational-config.local.json --port 5180
```

`VITE_OPERATIONAL_REVIEW=true`를 **빌드 전에** 지정해야 한다. 이 값이 빠지면 실제 자동심의 화면과 다른 제품 화면이 나올 수 있다.

서버 명령에 `--read-only`, `--result`, `--requests`, `--integrated`, `--original`을 추가하지 않는다. 이 문서는 과거 결과를 보여주는 방식이 아니라 **신규 광고 등록 모드**를 실행한다.

성공하면 `Uvicorn running on http://127.0.0.1:5180` 로그가 나온다. 창 A도 그대로 유지한다. 브라우저에서 `http://127.0.0.1:5180/login`에 접속한다.

- 이 로컬 PoC 코드의 로그인: **아이디 `admin`, 비밀번호 `admin`**.
- 이메일이라고 표시된 입력칸에도 `admin`을 넣는다.
- 이 계정은 로컬 시연용이다. 서버를 외부 인터넷에 공개하지 않는다.
- 접속 정보는 `temp/first-review-server/viewer-session.json`에도 저장된다. 이 파일을 공유하지 않는다.

Claude가 서버를 백그라운드로 시작할 때는 같은 가상환경 Python·작업 폴더·인자를 사용하고, Windows에서는 `Start-Process -WindowStyle Hidden`과 별도 stdout/stderr 로그를 사용한다. 새 프로세스/5180 소유 PID를 기록한다. 시스템 Python을 대신 실행하지 않는다.

## 9. 첫 광고 1건 실행

1. 광고 등록 화면을 연다.
2. 광고 카드는 **하나만** 사용한다.
3. 광고명·상품군·상세 상품군을 정확하게 입력한다. 상세 상품군으로 내부 템플릿이 연결된다.
4. 동일 광고를 구성하는 원본 파일만 함께 선택한다. 서로 다른 광고를 한 카드에 섞지 않는다. 파일당 최대 50MB다.
5. **“광고 1개 등록 후 자동심의”**를 누른다. 등록과 검토 요청이 이어진다.
6. 진행 화면에서 파싱 → 검색·판정 → 결과 저장 상태를 확인한다. 클릭을 반복해 중복 작업을 만들지 않는다.
7. 완료 후 결과 화면에서 충족·위반·판단불가, 해당 규정, 판단 이유, 인용된 광고 원문을 확인한다.
8. **“결과 JSON 다운로드”**로 파일을 저장한다.

처음에는 예금성 또는 대출성의 지원 상세 상품군으로 실행한다. 카드/투자성이나 확인되지 않은 다상품 광고를 임의의 상품군으로 바꿔 넣지 않는다. 상품설명서·약관을 추가 비교자료로 넣는 기능은 이 경로에 연결되지 않았으므로 처음부터 함께 첨부하지 않는다.

파싱과 판정은 수분 이상 걸릴 수 있고, 긴 광고·여러 파일·재시도·공유 GPU 사용량에 따라 더 걸린다. 과거 64규칙 실행의 약10분43초는 파싱을 제외한 기록이다. 일부17쌍49초·8쌍30초는 광고 한 건 전체 처리시간이 아니다. 첫 실행은 검색 인덱스·벡터 준비로 더 걸릴 수 있다.

## 10. 성공 확인과 기록 위치

**로그인 화면이 뜬 것과 심의가 끝난 것은 다르다.** 다음을 모두 확인한다.

- 해당 광고의 작업이 완료 또는 경고 포함 완료 상태이고, 실패 상태가 아니다.
- 새로 올린 광고의 원본이 결과 화면에 표시된다.
- 규정별 판정과 이유가 표시되고 JSON을 다운로드할 수 있다.
- 판단불가·출력 실패·검토 보류가 있으면 해당 건수와 사유를 그대로 남긴다. 모두 충족으로 바꾸지 않는다.
- 처리 완료는 광고 승인 또는 정확도 검증 완료라는 뜻이 아니다. 작은 글자·금리·표·각주는 사람이 원본과 대조한다.

이번 명령의 저장 위치는 다음과 같다.

| 위치 | 내용 |
| --- | --- |
| `temp/first-review-server/execution/web-state.json` | 등록 광고·검토 상태·결과 연결 |
| `temp/first-review-server/execution/runs/` | 검토별 원본·파싱·통합 산출물·로그 |
| `temp/first-review-server/execution/rag-jobs/` | 검색·판정 작업별 상태·산출물 |
| 브라우저 다운로드 폴더 | 사용자가 내려받은 결과 JSON |

하위 폴더 이름과 파일 위치는 검토 ID/작업 ID로 찾아간다. 이전 사람의 PC에 있던 절대 경로, 광고 ID, 개발 진단 결과를 재사용하지 않는다. 위 폴더에는 광고 원문과 결과가 있으므로 Git에 올리지 않는다.

## 11. 자주 막히는 경우

| 증상 | 먼저 확인할 것 |
| --- | --- |
| 실행 파일이 없다 | 현재 실행 코드가 Git에 포함됐는지 전달자에게 확인. Claude에게 대체 서버 생성을 시키지 않음 |
| `ModuleNotFoundError` | 앱과 파서 각각 설정된 가상환경 Python을 쓰는지 확인 |
| Python 3.13이 필요하다는 메시지 | 받은 파서 버전과 실제 `pyproject.toml` 확인. 심의 앱 3.11을 임의 변경하지 않음 |
| 패키지 버전을 찾을 수 없다 | 사내 저장소/패키지 전달본·현재 requirements 버전 확인. 무작정 최신/구버전으로 교체하지 않음 |
| JSON 읽기 오류 | 쉼표·따옴표·UTF-8 BOM·경로의 역슬래시 확인 |
| `Connection refused` 또는 timeout | VPN, SSH 창, 로컬/원격 포트, 담당 서비스 가동 상태 확인 |
| 모델 ID 오류 | 판정 모델과 이미지 판독 모델 각각의 실제 ID 확인 |
| BGE 벡터/응답 형식 오류 | 현재 BGE 전용 API와 연결했는지 확인. 일반 임베딩 API로 대체하지 않음 |
| Elasticsearch Nori/권한 오류 | Nori 설치와 지정 인덱스의 생성·조회·적재 권한을 담당자에게 확인 |
| 업로드 후 P1/P3가 없다고 나온다 | 별도 파서 runner·버전·Python·OCR/VLM 주소와 해당 파서 로그 확인. 웹만 재시작해 해결하려 하지 않음 |
| JSON Schema 미지원 | 담당 모델 서비스의 구조화 출력 호환성 확인. 검증기를 끄거나 빈 응답을 정상 판정으로 만들지 않음 |
| 5180 포트 사용 중 | 실제 소유 프로세스와 작업 상태 확인. 다른 서버를 임의 종료하지 않음 |
| 화면이 예전 모드다 | 운영 옵션을 넣어 빌드했는지, 서버의 static-dir이 그 dist인지 확인 |
| 원문 좌표가 안 나온다 | 실제 파서 좌표가 없는 근거일 수 있음. 좌표를 만들어 붙이지 않음 |

작업이 끝난 것을 확인한 후 서버 창 A에서 `Ctrl+C`, 이어 터널 창 B에서 `Ctrl+C`로 종료한다. 진행·대기 중인 작업이 있으면 끝날 때까지 기다린다. 강제 종료하면 재시작 후 그 작업이 중단/실패 상태가 될 수 있다. 다음 실행에는 같은 `state-dir`로 기존 상태를 보존한다.

## 12. Claude에게 그대로 붙여 넣을 요청

먼저 이 MD를 프로젝트와 함께 Claude에게 제공한다. 아래 빈칸에 **경로와 비밀정보 파일의 위치**를 넣는다. 개인키 원문·비밀번호·토큰은 넣지 않는다.

```text
목표는 이 프로젝트로 실제 광고 1건을 처음 실행하고 결과 JSON을 다운로드하는 것입니다.
첨부한 docs/first-review-local-spark-guide.md 순서대로 진행해 주세요.

내 환경:
- 운영체제: Windows
- 심의 프로젝트 루트: [절대 경로]
- 전달자가 지정한 코드 commit/전달본 버전: [값 또는 확인 필요]
- 규제목록 v2 XLSX: [절대 경로]
- 지정 일반 템플릿 HWPX: [절대 경로]
- 별도 파서 루트/버전: [경로와 버전 또는 확인 필요]
- 테스트할 광고 원본: [파일 경로 목록. 동일 광고 1건]
- 광고의 상품군/상세 상품군: [값 또는 사용자에게 확인]
- Spark 접속·각 서비스 포트·모델 ID를 기록한 비공개 로컬 파일: [경로]
- 접속 방식: [직접 SSH / VPN+SSH / 점프 서버 / 회사 HTTPS 프록시]
- SSH 터널: [사용자가 직접 연결 완료 / 연결 안내 필요]
- 내 SSH 키 파일: [Claude가 직접 접속해야 할 때만 경로. 사용자가 터널을 열면 제공하지 않음]

진행 방법:
1. 적용 AGENTS와 필수 문서를 읽고 실행 코드가 실제로 있는지 확인하세요.
   인수인계의 개발 재개 작업 대신 이 첫 실행 목표를 따르세요.
   누락된 코드/파서/서비스 정보는 한 번에 목록으로 정리해서 질문하세요.
   빠진 실행 코드를 새로 구현하거나 다른 저장소의 구형 코드로 대체하지 마세요.
2. 앱 Python3.11과 별도 파서 환경, 패키지와 프런트 빌드를 확인하세요.
   각 명령의 실패 여부를 확인하고 실패했으면 다음 단계로 넘어가지 마세요.
3. 내 경로로 temp/operational-config.local.json을 만들거나 필요한 값만 수정하세요.
   기존 설정·사용자 코드·상태는 보존하고 비밀값은 채팅/로그에 출력하지 마세요.
4. 지정된 기존 Spark 서비스에 연결하세요. 원격 장비/모델/OCR/ES를
   재시작하거나 새 모델을 설치하지 마세요. 검색에 필요한 지정 인덱스 권한도 확인하세요.
   SSH 키 파일의 내용은 읽거나 출력하지 마세요. 키 암호 입력·공개키 등록은 사용자가 합니다.
   사용자가 직접 연 터널이 있으면 로컬 포트를 사용하세요. 프록시 방식이면 담당자가 준
   주소·인증·경로 호환성을 먼저 확인하세요. 로컬5180에 NH_RAG_API_TOKEN을 필수로 요구하지 마세요.
5. 경로·연결·모델 호환성을 점검한 후 로컬5180을 신규 등록 모드로 시작하세요.
   temp/first-review-server를 사용하고 이전 사람의 상태나 결과를 복사하지 마세요.
   백그라운드 실행은 숨긴 창·로그·PID를 남기고 반드시 가상환경 Python을 쓰세요.
6. 내가 위에서 지정한 광고 1건만 실제 파서·검색·판정에 전달해 주세요.
   위 설정 서비스로 그 광고를 처리하는 것이 이번 요청에 포함됩니다.
   다른 광고/폴더 전체를 보내거나 중복 심의를 시작하지 마세요.
   원본 파일이나 상세 상품군이 미정이면 실행 전에 확인하세요.
7. 브라우저를 직접 조작할 수 있으면 등록부터 JSON 다운로드까지 진행하고,
   조작할 수 없으면 내가 클릭할 화면·버튼을 단계별로 알려 주세요.
8. 완료 상태, 소요시간(파싱 포함 여부), 판정/판단불가/실패 건수,
   다운로드 파일과 로컬 로그 위치를 요약하세요. 실패를 완료라고 하지 마세요.

기존17쌍/8쌍 진단, 성능 튜닝, 파인튜닝, 답지 생성은 실행하지 마세요.
파서/검색/판정 기준을 사례에 맞춰 바꾸지 말고 정답표·연구원 O/X를 런타임에 넣지 마세요.
광고 작업 중에는 서버·터널을 종료하지 마세요.
```

## 관련 문서

- [현재 인수인계](handoff-current.md): 현행 구현과 미완료 범위
- [확정 결정](decisions.md): 규칙 출처·판정·운영 경계
- [평가셋 현황](evaluation-splits-current.md): 개발 자료와 독립 평가 구분
- [파이프라인 검토](pipeline-design-review-current.md): 실제 검증 결과와 한계
- [파서 담당자 전달 자료](parser-agent-handoff.md): 파서 계약 협의용. 첫 실행 설치 안내를 대체하지 않음

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.6 | 2026-09-30 | 별도 파서 전달본·패치 대신 저장소 `parser-pipeline/`과 전용 환경·기본 경로·`parser_revision` 설정으로 전환 |
| v1.5 | 2026-09-15 | 사용자 템플릿 지원 파서 전달·패치 적용·첫 재분석 주의점 추가 |
| v1.4 | 2026-09-15 | 인덱스 접두사·모델 ID는 인증 비밀이 아님을 명확화, 실행 파일 포함 커밋과 수신 브랜치 명시 |
| v1.3 | 2026-09-15 | 개인키 비공개 강조·사용자 직접 터널 연결 절차, 인덱스 접두사/모델 ID의 확인 책임과 비공개 전달 방법 추가 |
| v1.2 | 2026-09-15 | SSH 로컬 터널·프록시·점프/역방향 연결 구분, 본인 공개키 등록과 개인키 비공개 절차, RAG API 토큰 사용처 보완 |
| v1.1 | 2026-09-15 | 실행 코드 동반 전달과 최신 작업 브랜치 확인 절차 반영 |
| v1.0 | 2026-09-15 | Windows 첫 실행, 코드 전달 완전성, 분리 파서 환경, 5서비스 연결, 설정·웹 실행·Claude 지시문 작성 |
