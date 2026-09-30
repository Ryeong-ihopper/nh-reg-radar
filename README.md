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
| 광고 등록 | [`AdvertisementCreatePage.tsx`](apps/frontend/src/pages/AdvertisementCreatePage.tsx) |
| 결과 화면 | [`OperationalReviewReportPage.tsx`](apps/frontend/src/pages/OperationalReviewReportPage.tsx) |
| 결과 상세·원문 | [`OperationalReviewDetail.tsx`](apps/frontend/src/components/OperationalReviewDetail.tsx), [`OperationalOriginalPanel.tsx`](apps/frontend/src/components/OperationalOriginalPanel.tsx) |
| 결과 데이터 해석 | [`operationalResultModel.ts`](apps/frontend/src/components/operationalResultModel.ts) |
| 화면 API 계약 | [`operational.ts`](apps/frontend/src/api/operational.ts), [`openapi.yaml`](openapi/openapi.yaml) |
| 상품 조합 | [`product-contexts-v1.json`](rag-pipeline/config/product-contexts-v1.json), [`product_context.py`](rag-pipeline/rag/judgment/product_context.py) |
| 운영 연결·이미지 범위 | [`operational_web_bridge.py`](scripts/operational_web_bridge.py), [`runtime-files.json`](infra/operational/runtime-files.json) |

프런트엔드는 React·TypeScript·Vite, 웹 API와 판정기는 Python을 사용합니다. 별도 private 파서, 검색·모델 서비스, 비공개 운영 설정은 이 저장소에 포함되지 않습니다. 생성기·평가기·회귀 테스트·이행 코드는 저장소에 보존하고 최종 운영 이미지의 실행 파일 목록과 구분합니다.

## 개발·검사

Python 3.11과 Node.js 22를 사용합니다. 프런트엔드 의존성을 설치한 뒤 운영 모드의 화면 코드를 로컬 API에 연결할 수 있습니다.

```bash
npm --prefix apps/frontend ci
VITE_API_PROXY_TARGET=http://127.0.0.1:5182 npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

PowerShell에서는 `VITE_API_PROXY_TARGET`을 환경변수로 설정한 뒤 `npm` 명령을 실행합니다. 실제 심의에는 승인된 원문·파서·검색·모델 연결이 별도로 필요합니다.

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
