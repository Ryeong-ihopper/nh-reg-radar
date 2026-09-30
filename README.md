# NH Reg Radar

NH농협은행 금융상품 광고의 사전 심의를 보조하는 웹 애플리케이션입니다. 광고에서 추출한 내용과 상품별 심의 기준을 연결하고, 항목별 판정·사유·근거 문구·원문 위치를 함께 제공합니다. 최종 심의는 담당자가 확인합니다.

## 주요 기능

- 예금성·대출성·투자성 상품 광고 등록 및 관리
- PDF·이미지·HWP/HWPX 광고의 본문과 위치 정보 추출
- 상품별 템플릿에 따른 필수 항목·조건·예외 검토
- 규칙 기반 검사와 언어 모델을 활용한 의미 검토
- 원본 광고와 항목별 결과를 함께 확인하는 화면
- 판정별 결과 필터 및 상세 근거 확인

## 처리 흐름

```text
광고 등록 → 원문 추출 → 적용 기준 선정 → 근거 검색 → 항목별 검사 → 결과 확인
```

현재 심의는 선택한 상품의 템플릿 기준을 사용합니다. 추출이나 해석이 불확실한 내용은 확인필요로 남기며, 템플릿의 예시 문구를 광고에 그대로 사용해야 하는 의무로 취급하지 않습니다.

AI 수정 문구 자동 생성·저장과 법령 전체 조문·개정 이력 검색은 아직 연결되지 않았습니다.

## 기술 구성

| 영역 | 구성 |
| --- | --- |
| 프런트엔드 | React, TypeScript, Vite |
| 웹 API·심의 처리 | Python |
| 문서 추출 | 외부 문서 파서 및 OCR 연동 |
| 근거 검색·의미 검토 | 검색 서비스 및 언어 모델 연동 |

## 저장소 구조

| 경로 | 내용 |
| --- | --- |
| `apps/frontend/` | 광고 관리 및 심의 결과 화면 |
| `apps/backend/` | 웹 API와 업무 처리 |
| `packages/` | 공통 모듈 및 서비스 연동 |
| `rag-pipeline/` | 심의 기준 구성, 근거 검색, 판정 및 평가 |
| `scripts/` | 실행·운영·관리 도구 |
| `infra/` | 실행 환경 및 배포 구성 |
| `tests/` | 기능 및 계약 검사 |
| `docs/` | 요구사항, 설계, 운영 문서 |

## 개발 환경 실행

Python 3.11과 Node.js 22를 사용합니다. 프런트엔드 개발 서버는 접근 가능한 API 서버에 연결해야 하며, 실제 심의에는 별도의 파서·OCR·검색·모델 서비스 설정이 필요합니다.

```bash
npm --prefix apps/frontend ci
```

PowerShell:

```powershell
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:5182"
npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

Linux/macOS:

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:5182 npm --prefix apps/frontend run dev -- --mode operational --host 127.0.0.1
```

API 주소는 사용 환경에 맞게 지정합니다. 서버 구성과 실행 절차는 [운영 환경 안내](infra/operational/README.md)를 참고하세요.

## 관련 문서

- [프로젝트 규칙](docs/project-rules.md)
- [기능 명세](docs/functional-specification.md)
- [화면 명세](docs/screen-specification.md)
- [규칙 실행 계약](docs/rule-execution-contract-current.md)
- [현재 개발·운영 상태](docs/handoff-current.md)
