# NH Reg Radar

NH농협은행 금융상품 광고의 사전 심의를 보조하는 프로젝트입니다. 광고 원본에서 읽은 내용과 선택한 상품의 템플릿 기준을 연결하고, 항목별 판단·근거 문구·원문 위치를 함께 보여줍니다. 최종 심의는 담당자가 확인합니다.

## 현재 범위

- 예금성·대출성·투자성 광고 등록과 원본 파일 묶음 처리
- 선택한 템플릿의 필수 항목 전개, 조건·예외·원자 의무 검사
- 항목별 근거 검색과 규칙·모델·사람 확인의 역할 분리
- 저장 결과 표, 선택 항목 상세, 원문 위치·추출 상태 표시
- 퇴직연금 일반의 펀드·ETF·ELB 복수 선택, IRP 펀드 노출의 추가 ETF·ELB 선택

운영 판정은 `template-only` 정책으로 템플릿 239항목을 사용합니다. 보완 32항목과 추가 후보 34항목은 작업대장에만 있으며 자동 판정에 추가되지 않습니다. 예시 문구·숫자는 완전일치 기준이 아닙니다. 판독이나 금융 해석이 불확실하면 확인필요로 남깁니다.

AI 수정 문구 자동 생성·채택 결과 저장, 법령 전체 조문·개정 이력 검색, 사용자 수정·재추출 작업대는 아직 연결되지 않았습니다.

## 화면과 데이터 흐름

```text
광고 등록 → 상품·매체·원본 입력 → 파서 P1/P3 → 정본 항목 전개
       → 항목별 광고 근거 확보 → 규칙·모델·사람 검사 → 결과 저장·원문 확인
```

등록 화면에서 고른 분류는 `routing`과 `intake.products[]`에 전달합니다. 퇴직연금 일반은 기본 템플릿에 실제 언급된 펀드·ETF·ELB 템플릿을 더합니다. IRP 펀드상품 노출은 펀드 의무를 이미 포함하므로 ETF·ELB만 추가합니다. IRP 금융투자상품 미노출에는 운용상품을 추가하지 않습니다. 연결되지 않은 운용상품은 임의 템플릿으로 추측하지 않습니다.

파서가 제공한 원문·줄·문자·좌표·출처를 보존합니다. HWP/HWPX의 기본 원문은 심의에 사용한 이미지이며 HTML 본문은 별도의 격리된 읽기 화면입니다. 추출 완료 상태만으로 판독 정확도를 보장하지 않습니다.

## 코드 위치

| 영역 | 주요 파일 |
| --- | --- |
| 광고 목록·검색·선택 | [`AdvertisementListPage.tsx`](apps/frontend/src/pages/AdvertisementListPage.tsx), [`AdvertisementDetailPage.tsx`](apps/frontend/src/pages/AdvertisementDetailPage.tsx) |
| 광고 등록 | [`AdvertisementCreatePage.tsx`](apps/frontend/src/pages/AdvertisementCreatePage.tsx) |
| 결과 화면 | [`OperationalReviewReportPage.tsx`](apps/frontend/src/pages/OperationalReviewReportPage.tsx) |
| 결과 상세·원문 | [`OperationalReviewDetail.tsx`](apps/frontend/src/components/OperationalReviewDetail.tsx), [`OperationalOriginalPanel.tsx`](apps/frontend/src/components/OperationalOriginalPanel.tsx) |
| 결과 데이터 해석 | [`operationalResultModel.ts`](apps/frontend/src/components/operationalResultModel.ts) |
| 화면 API 계약 | [`operational.ts`](apps/frontend/src/api/operational.ts), [`openapi.yaml`](openapi/openapi.yaml) |
| 상품 조합 | [`product-contexts-v1.json`](rag-pipeline/config/product-contexts-v1.json), [`product_context.py`](rag-pipeline/rag/judgment/product_context.py) |
| 운영 연결·이미지 범위 | [`operational_web_bridge.py`](scripts/operational_web_bridge.py), [`runtime-files.json`](infra/operational/runtime-files.json) |
| 파서 계약 변환·근거 위치 | [`parser_contract_adapter.py`](rag-pipeline/rag/parsing/parser_contract_adapter.py), [`prepare_inputs.py`](rag-pipeline/rag/parsing/prepare_inputs.py), [`operational_locations.py`](scripts/operational_locations.py) |

프런트엔드는 React·TypeScript·Vite, 웹 API와 판정기는 Python을 사용합니다. 별도 private 파서, 검색·모델 서비스, 비공개 운영 설정은 이 저장소에 포함되지 않습니다. 생성기·평가기·회귀 테스트·이행 코드는 저장소에 보존하고 최종 운영 이미지의 실행 파일 목록과 구분합니다.

## 광고 목록·렌더링 담당자 안내

운영 모드의 결과 화면은 `OperationalReviewReportPage.tsx`입니다. 일반 모드의 `ReviewResultsPage.tsx`와 진입점이 다르므로 [`App.tsx`](apps/frontend/src/App.tsx)의 라우팅과 `.env.operational`을 먼저 확인하세요. 목록 API는 `api/client.ts`, 운영 심의 API는 `api/operational.ts`, 화면 배치는 `styles.css`에서 관리합니다.

결과 화면은 다음 세 데이터를 연결합니다. 아래 경로의 앞에는 `/api/v1/operational`이 붙습니다.

| 응답 | 화면에서 쓰는 내용 |
| --- | --- |
| `reviews/{reviewId}/workspace` | 항목별 판정·사유·인용문, `evidence_locations`(직접 근거), `review_locations`(사람 확인 대상) |
| `reviews/{reviewId}/parser-layout` | 파일·페이지 연결, 영역·줄·좌표, 페이지별 `canvas_w/h`, `preview_path` |
| `reviews/{reviewId}/parser-page/{pageNo}` | 해당 P1/P3와 원본 해시에 결합된 실제 파서 페이지 이미지 |

`OperationalOriginalPanel`은 이미지를 그리고 좌표를 페이지 캔버스 크기로 나눠 표시합니다. 결과의 페이지 번호와 원본 파일의 페이지 번호는 다를 수 있으므로 `asset_id`·`source_page_no`를 함께 유지해야 합니다. HWP HTML 보기는 별도이며 이미지 좌표를 겹쳐 그리지 않습니다.

`operationalResultModel`은 판정 표시명·위치 선택·위치 없음 안내를 담당하고, `OperationalReviewDetail`은 선택 항목의 사유·인용문·검사 상세를 표시합니다. 좌표가 없다는 이유만으로 문구 누락을 뜻하지 않습니다. 명시적으로 비어 있는 `evidence_locations`를 다른 상품의 같은 문구로 찾아 채우지 않습니다.

외부 파서의 최신 확인 커밋은 [`3d3dacbf`](https://github.com/cg-wnsdud/nh-parser-fin/tree/3d3dacbf95518090c12b10874ba3d758a889f235)입니다. P1 v5·P3 v10은 `region-v10`으로 연결하며, 이전 저장 결과의 v3/v6·v4/v9도 읽습니다. 파서 업데이트 시 비공개 실행 설정의 `parser_contract_profile`과 40자리 `parser_revision`을 실제 설치본에 맞춰 함께 변경해야 합니다. 코드 지원과 운영 설치 상태는 구분하며 최신 적용 여부는 [인수인계](docs/handoff-current.md)를 확인하세요.

최종 `selected_text`는 영역 단위이고 P1 OCR 줄과 다를 수 있습니다. PDF 디지털 교정이나 표 변환 후 문구를 예전 OCR 줄의 정확한 문구·좌표라고 취급하면 안 됩니다. 원본 P1/P3를 보존하고 검증 가능한 줄 또는 실제 영역 수준으로 연결합니다. 자세한 계약은 [파서 연결 명세](docs/parser-schema-current-2026-09-28.md)를 따릅니다.

## 개발·검사

Python 3.11과 Node.js 22를 사용합니다. 프런트엔드 의존성을 설치한 뒤 운영 모드의 화면 코드를 로컬 API에 연결할 수 있습니다.

```bash
npm --prefix apps/frontend ci
VITE_API_PROXY_TARGET=http://127.0.0.1:5182 npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

PowerShell에서는 `VITE_API_PROXY_TARGET`을 환경변수로 설정한 뒤 `npm` 명령을 실행합니다. 실제 심의에는 승인된 원문·파서·검색·모델 연결이 별도로 필요합니다.

```powershell
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:5182"
npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

5182는 접속 가능한 운영 API 또는 로컬 연결이 먼저 있어야 합니다. Vite를 켜는 것만으로 파서·OCR·모델 서버가 시작되지는 않습니다. 서버 구성은 [`infra/operational/README.md`](infra/operational/README.md)를 참고하세요.

변경 범위에 맞는 직접 회귀부터 실행합니다. 공통 판정·출처 계약이나 운영 배포가 바뀌면 관련 전체 검사를 추가합니다.

```bash
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run test -- src/operational-product-context.test.tsx
python rag-pipeline/tools/run_rag_ci.py
python -m scripts.doc_guard validate --scope working
```

Linux 문서·거버넌스 검사는 `scripts/check-doc-consistency.sh`와 `python -m unittest discover -s tests/governance -v`로 수행합니다. Windows에서는 실행 중인 Linux Docker 엔진을 사용하는 `python scripts/run_governance_tests.py`를 사용합니다.

현재 계약과 작업 경계는 [프로젝트 규칙](docs/project-rules.md), [기능 명세](docs/functional-specification.md), [화면 명세](docs/screen-specification.md), [규칙 실행 계약](docs/rule-execution-contract-current.md), [인수인계](docs/handoff-current.md)를 확인하세요. 평가 정답은 예측 해시를 동결한 뒤 별도 절차에서만 사용합니다.
