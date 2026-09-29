# NH Reg Radar

NH농협은행 금융상품 광고의 사전 심의를 보조하는 규칙·근거 기반 검토 프로젝트입니다.
광고 이미지·PDF·HWP/HWPX에서 읽은 내용과 선택한 상품의 심의 기준을 연결하고,
항목별 적정·부적정·확인필요 결과를 원문 인용과 위치와 함께 보여줍니다.
최종 심의는 담당자의 검토를 거칩니다.

이 저장소는 기존 NH 제품 개발 기반에 정본 규칙 실행, 운영 웹 연결, 원문 근거 표시,
규칙 구조화와 독립 평가 기능을 확장한 작업 저장소입니다.
현재 업로드 대상은 **[Ryeong-ihopper/nh-reg-radar](https://github.com/Ryeong-ihopper/nh-reg-radar)**입니다.
현재 작업 브랜치는 `feat/regulation-collection-viewer`이며 운영 적용과 저장소의 변경 상태는
[인수인계](docs/handoff-current.md)에서 구별해 확인합니다.

## 주요 기능

- 광고 등록, 상품·매체 선택, 심의 진행 및 저장된 결과 조회
- 예금성·대출성·투자성 기준과 퇴직연금 공통·복수 운용상품 기준 연결
- 원문 조건·예외·원자 검사·AND/OR를 보존하는 정본 실행
- 검사별 광고 근거 검색, Rule·LLM·사람 담당 분리와 코드의 최종 종합
- 항목별 결과 표, 선택 상세, 원문 인용과 실제 좌표 표시
- HWP 심의 이미지와 격리된 HTML 본문 읽기
- 파일·페이지별 추출 상태와 판독 불확실성 안내
- 현재 템플릿에 연결된 법령·규정 근거 검색
- 수정 초안 편집, 예시 가져오기와 복사

AI 수정 초안 자동 생성·채택 결과 DB 저장, 법령 전체 조문 검색·개정 이력,
사용자 수정·재추출 작업대, 실제 심의필 승인·발급 조회는 아직 연결되지 않았습니다.

## 현재 실행 범위

| 구분 | 범위 |
| --- | --- |
| 정본 실행계획 | 템플릿239 + 보완32 = 271계획 |
| 운영 심의 | `template-only`, 템플릿239·보완0 |
| 구조화 작업대장 | 템플릿239 + 보완32 + 추가34 = 305행 |
| 검토 대기 | 보완32·추가34는 자동 활성화하지 않음 |
| 물리 줄 검사 | 실제 줄 미인증33원자는 사람 검토 유지 |

계획이나 테스트의 존재는 각 규정의 의미 검토 완료나 실제 광고 판정 정확도 인증이 아닙니다.
미확정 해석·외부자료 부족·판독 불확실성은 확인필요로 남깁니다.

## 심의 흐름

```mermaid
flowchart LR
    A[광고와 상품 입력] --> B[파서 P1·P3]
    B --> C[광고 근거와 판독 상태]
    A --> D[선택 템플릿 정본 전개]
    C --> E[원자별 근거 확보]
    D --> E
    E --> F[Rule·LLM·사람 검사]
    F --> G[계약 검증과 논리 종합]
    G --> H[결과·인용·추적 저장]
    H --> I[결과와 원문 확인]
```

선택 템플릿의 필수 항목은 검색에서 발견되는지와 무관하게 전개합니다.
검색은 검사에 필요한 광고 증거를 찾는 과정이며 검색 실패를 문구 누락으로 판단하지 않습니다.
LLM의 관찰을 원자별로 검증하고, 코드는 원문의 조건·예외와 결합식에 따라 전체 결과를 계산합니다.
현재 운영 검색은 검사별 라벨·어휘 기준을 사용하며 임베딩 보조는 항목별 유용성 검증과 구별합니다.

실행 코드는 [규칙 실행 계약](docs/rule-execution-contract-current.md)과
[상품·근거 정책](docs/adr/ADR-0087-product-composition-and-evidence-policy.md)을 따릅니다.

## 기술 구성

| 영역 | 구성 |
| --- | --- |
| 웹 화면 | React19, TypeScript, Vite |
| 웹/API·운영 연결 | FastAPI, Python3.11 |
| 심의·검증 | 정본 계획, 조건 계약, 근거 검증, 공통 실행기 |
| 검색·모델 서비스 | Elasticsearch, BGE-M3, OpenAI 호환 Gemma 연결 |
| 문서 파서 | 별도 private `nh-parser-fin`, Python3.13 |
| HWP 지원 | private 문서 처리기, Java, LibreOffice/H2Orestart |
| 배포 | 운영 Dockerfile·Compose, 외부 상태·원문·비공개 설정 마운트 |

현재 운영 웹은 기존 제품 API에 파일 기반 운영 상태·작업·결과 연결을 제공합니다.
PostgreSQL·Redis·MinIO·Qdrant·OpenSearch 기반의 기존 제품 구성과 worker·DB 이행 코드도
저장소에 보존하지만, 그 전체 구성이 현재 운영 심의의 실행 경로라는 뜻은 아닙니다.

## 저장소 구성

```text
apps/frontend/             등록·진행·결과·원문·기준표 화면
apps/backend/              제품 API·인증·업무 계약·DB 이행
apps/worker/               기존 제품 worker
packages/                  AI provider·파서 공용 계약
rag-pipeline/rag/          근거 처리·조건·검색·판정·검증
rag-pipeline/config/       정본 계획·정책·migration·작업대장
rag-pipeline/tools/        운영 실행·복구·생성·독립 평가·CI
scripts/                   웹 연결·원문 표시·포장·문서 검사
infra/operational/         운영 이미지·Compose·실행 파일 목록
tests/                     운영 연결·포장·문서 거버넌스 회귀
docs/                      현행 명세·결정·ADR·인수인계
openapi/                   API 계약과 생성 타입의 원천
```

## 개발 준비

웹·RAG 개발은 Python3.11, Node.js22와 프로젝트 의존성을 사용합니다.
실제 심의에는 별도 승인 원문·private 파서·비공개 서비스 설정과 모델/OCR/검색 연결이 필요합니다.
파서의 Python3.13 환경은 애플리케이션 환경과 분리합니다.

```bash
git clone --branch feat/regulation-collection-viewer https://github.com/Ryeong-ihopper/nh-reg-radar.git
cd nh-reg-radar
uv sync --all-packages --dev
uv pip install -r rag-pipeline/requirements-rag-dev.txt
npm --prefix apps/frontend ci
```

명령 실행 전 프로젝트 환경을 활성화합니다. Linux/macOS는 `source .venv/bin/activate`,
Windows PowerShell은 `.venv/Scripts/Activate.ps1`을 사용합니다.
의존성 설치와 로컬 Git hook 설정은 [개발 도구 설치](scripts/setup-dev-tools.sh)를 참고합니다.

운영 API에 연결하는 프런트엔드 개발 예시입니다. 주소는 실행 중인 로컬 API에 맞춥니다.

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:5182 npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

PowerShell에서는 `$env:VITE_API_PROXY_TARGET='http://127.0.0.1:5182'`를 설정한 뒤 npm 명령을 실행합니다.
실제 심의 서버 설정·파서·원문 연결은 [운영 구성](infra/operational/README.md)을 따릅니다.

## 검사

작은 수정은 영향받은 테스트·타입·lint·화면 확인부터 수행합니다.
공통 판정·파서·출처 계약 변경, 광범위한 삭제와 운영 배포에서는 관련 전체 검사를 수행합니다.
검사 범위와 결과는 실제 변경 및 완료 여부에 따라 기록합니다.

```bash
# 개별 수정: 관련 테스트 파일을 지정
python -m pytest tests/test_operational_locations.py -q

# RAG 공통 변경: 결정적 회귀·누수 방지·계약 검사
python rag-pipeline/tools/run_rag_ci.py
python -m ruff check rag-pipeline

# 화면 변경: 필요한 범위로 실행
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run test -- src/operational-product-context.test.tsx

# 배포용 화면 산출물
npm --prefix apps/frontend run build:operational
```

문서·명세 변경의 기본 검사는 다음과 같습니다.

```bash
scripts/check-doc-consistency.sh
python -m scripts.doc_guard validate --scope working
```

전체 거버넌스는 Linux에서 `python -m unittest discover -s tests/governance -v`로 실행합니다.
Windows에서는 실행 중인 Linux Docker 엔진을 이용하는 `python scripts/run_governance_tests.py`를 사용합니다.
CI는 저장소의 검사 스크립트와 테스트를 실행하므로 필요한 검사 코드는 브랜치에도 보존합니다.

## 운영 이미지와 코드 수명주기

최종 애플리케이션 파일은 [runtime-files.json](infra/operational/runtime-files.json)의 명시 목록을 사용합니다.
현재 실행 목록은 Python106·config/schema19의125파일입니다. 현재 프런트엔드 산출물과
출처 manifest를 함께 포함하며 requirements는 의존성 설치 후 최종 이미지에서 제거합니다.

정본 생성·독립 평가·현재 회귀 테스트·CI·DB 이행은 저장소에 남기고 운영 이미지에서는 제외합니다.
정본 생성의 세 구조 입력은 `rag-pipeline/config/canonical-source/`에서 관리하며,
개인 임시 폴더 없이 현재 정책을 적용해 정본 전체를 재현하는지 CI에서 검사합니다.
공유 요청 생성·운영 복구·HWP 도구와 정본 config/schema는 실행에 필요한 범위로 포함합니다.
새 설계가 대체 경로의 호출·이행·회귀 검증을 통과하면 옛 활성 코드·전용 테스트·중복 문서를 제거합니다.
원문 계보·Accepted ADR·동결 결과와 필요한 호환/이행은 보존합니다.

배포는 실행 중인 작업 확인, 상태 사본과 ID·결과 SHA 대조 후 웹만 갱신합니다.
조회 화면을 바꾸면서 과거 판단을 다시 계산하거나 현재 자료를 과거 결과에 소급 연결하지 않습니다.
구체적인 적용 이미지와 검증 이력은 [인수인계](docs/handoff-current.md)를 확인합니다.

## 판정·데이터 원칙

- 원문·출처·판본·조건·예외·원자 의무와 AND/OR를 보존합니다.
- 예시 표현·숫자는 완전일치 의무나 광고 증거로 사용하지 않습니다.
- 실제 광고의 줄·문자·bbox·출처를 유지하고 확인되지 않은 시각 속성은 사람에게 보냅니다.
- 추출 완료는 정확도 보장이 아니며 confidence를 신뢰도 백분율로 표시하지 않습니다.
- 금융 해석 미확정과 불충분한 근거는 확인필요로 유지합니다.
- gold는 예측 해시를 동결한 뒤 별도 평가에서만 사용합니다. 사례별 하드코딩을 금지합니다.
- 비공개 설정·자격증명·운영 상태·실행 결과·private 파서와 개인 임시 산출물은 새 커밋에 넣지 않습니다.

## 관련 문서

| 문서 | 내용 |
| --- | --- |
| [기능명세](docs/functional-specification.md) | 현재 기능·입출력과 미연동 경계 |
| [화면명세](docs/screen-specification.md) | 화면·표시·원문 연결 |
| [API명세](docs/api-specification.md) | API 계약 |
| [규칙 실행 계약](docs/rule-execution-contract-current.md) | 정본 실행·논리·근거·역할 |
| [확정 결정](docs/decisions.md) | 승인된 해석과 적용 범위 |
| [평가셋 경계](docs/evaluation-splits-current.md) | 개발/회귀·holdout·gold 분리 |
| [테스트케이스](docs/test-cases.md) | 검증 항목과 완료 경계 |
| [ADR 목록](docs/adr/README.md) | 승인된 구조·운영 결정 |

루트 README는 현재 브랜치의 프로젝트 소개입니다. 이 파일을 포함한 PR을 다른 브랜치에
병합하면 병합 대상의 같은 `README.md`에도 변경이 반영됩니다. 양쪽 변경이 겹치면
내용을 합치거나 충돌을 해결해야 하며, Git이 자동으로 별도 개인 폴더에 보관하지는 않습니다.
