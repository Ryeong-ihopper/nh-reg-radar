# Parser agent handoff

## 복수 표제의 하위 라벨 보존 — 2026-09-16

한 원문 줄에 여러 명시 표제가 있는 경우 첫 표제만 남기던 후처리를 수정한다. `|`·전각 세로줄·세미콜론 구분 필드의 기존 표제 인식 결과를 모아 유효 라벨을 보존하며 P1 줄·좌표·공개 span 형식은 유지한다. 전달 패치와 합성 검사를 함께 적용해야 한다. 현재 이미지 추가 및 단일 영역 호출의 정확도 이점은 충분히 입증되지 않아 운영 호출 방식을 바꾸지 않는다. 하위 라벨링 호출은 계속 OCR 텍스트/좌표와 선택 P3 문맥을 사용한다. 기존 사람 검토 경계와 최종 파서 스키마 의존성은 유지한다.

## 라벨 의미·원문 품질 보완 — 2026-09-16

하위 라벨 모델에 줄별 OCR source/confidence와 기존 저신뢰 판독 기준의 사람 확인 표시를 전달한다. 명확한 디코딩 손상 또는 기존 설정 기준 미만 OCR 줄에는 모델 신뢰도가 높거나 명시 표제가 있어도 라벨을 확정하지 않는다. 원문과 독립적으로 읽을 수 있는 다른 줄의 라벨은 보존한다. 템플릿 기재요령의 240자/2항목 절단을 제거하고 모든 기재요령을 전달한다. P3가 실제 선택한 VLM 판독문은 줄 번호 없는 문맥 보조로 구분하며 P1에 없는 정보를 P1 라벨 근거로 승격하지 않는다. 회사/상품 고유 이름과 메뉴·절차 문단, 실제 조건과 계산기 입력 예시를 구별하도록 공통 안내를 보완한다. 특정 광고 이름·수치·답지 조건을 추가하지 않는다. 저신뢰 기준은 기존 OCR 재판독 설정을 사용하며 높은 OCR 신뢰도가 정확도를 보증하지는 않는다. 당시 재사용 정책은 `user-template-labeling-v3`였으며 현행 정책은 상단을 따른다. 최종 스키마 수령과 별도 광고의 사람 확정 정답에 기반한 독립 평가를 완료한 것으로 취급하지 않는다.



전체 실행의 파일별/병합 입력 비교에서 표 라벨 경계의 자산 접두어 연결 오류를 발견했다. 병합 시 라벨과 원문 참조 모두에 접두어를 붙이지만 청킹은 원문 참조에서만 접두어를 떼어 라벨 경계를 놓쳤다. 전체 참조를 우선하고 접두어 없는 구형 라벨만 현재 영역의 유일한 줄로 연결하도록 수정했다. 다른 자산의 동일 접미사와 모호한 구형 참조는 연결하지 않는다. 기존 통합 입력을 고정한 오프라인 검사에서 coarse31 유지, fine49→56으로 파일별 청킹 합계와 일치했다. RAG279+21 통과. 광고 문구나 정답별 예외는 없다. 이미 진행 중이던49청크 판정은 원래 입력으로 보존하고, 완료 후 검증된 새 P1/P3를 재사용해 수정 청킹의 검색·판정부터 별도 재실행한다. 이는 OCR 재실행이나 판정 응답의 성공할 때까지 재호출이 아니라 일반 연결 결함 수정에 따른 새 입력 검증이다.

## 하위 라벨 연결 후속 — 2026-09-16

모델의 하위 라벨 출력은 시작·끝 범위 대신 오름차순의 중복 없는 `line_ids`를 사용한다. 예를 들어 `[0, 3]`은 두 줄만 선택하며 사이의 1·2번 줄에 라벨을 붙이지 않는다. P1/P3 공개 출력은 기존의 연속 `spans`와 `line_refs`를 유지한다. P1 내보내기도 범위를 보정하지 않으며, 검색 입력은 라벨 참조의 영역 소유권·순서와 선택적으로 제공된 시작/끝 범위의 일치를 다시 확인한다. 잘못된 라벨 범위만 제외하고 원문·유효 라벨을 보존하며 `needs_review`를 켠다. 저장 원본은 덮어쓰지 않는다. 이는 사용자 확정 템플릿과 ADR-0085의 원문 접지 계약을 실행하는 일반 구현 수정이며 새 판정 규정이나 사례별 라벨 사전을 추가하지 않는다. P3의 다른 판독문을 P1 원문으로 승격하지 않으며, 라벨 의미 정확도와 OCR 정확도를 보장하는 변경은 아니다.


## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.6 |
| 기준일 | 2026-09-16 |
| 상태 | 파서 담당 코덱스용 독립 전달 패킷. 요구 의미·수용 기준 협의안이며 배포된 API 계약이 아님 |
| 범위 | 광고 원문 추출·증거 전달·파서 실행 복구. 심의 규칙이나 정답 전달 아님 |

## 사용자 선택 템플릿과 하위 라벨의 책임

2026-09-15 사용자 결정: `[대출성상품-상품명 노출]` 같은 상위 템플릿은 등록자가 선택한 상세 상품군에서 확정한다. 파서가 파일명·규칙 분기·모델로 다시 고르지 않는다. 회사명·상품명·우대금리·부대비용·대출금리 등 선택 템플릿 안의 하위 구분과 원문 줄의 대응이 파서의 라벨링 책임이다.

운영 연결부는 `internal_template_id`를 최초 파싱·파일 병렬 처리·실패 파일 재시도에 동일하게 전달한다. `nh_ad_parser_cli`의 `--template-id`가 필수이며 P1/P3가 해당 ID와 `source=user_provided`를 모두 반환해야 한다. 미입력·지원하지 않는 실행기·다른 템플릿 출력은 자동 분류로 우회하지 않는다. 시각화만 생성하는 보조 경로는 `--parse-only`를 사용한다. `parser-intake.json`의 정책 버전/템플릿이 다른 과거 자동분류 P1/P3는 재실행에서 재사용하지 않는다.

하위 라벨은 P1 원문 줄에 붙인다. 모델 입력에 줄별 bbox를 보존해 표의 표제/값 대응을 확인하게 하며, OCR 순서만으로 떨어진 줄 사이의 다른 항목까지 범위에 넣지 않도록 한다. 좌표로 폰트/색상을 판정하지 않는다. 모델이 반환한 역순·음수·범위 밖 줄 번호를 임의 보정하지 않으며, 신뢰도 미확정/0.7 미만 라벨은 확정 연결에서 제외하고 사람 확인 표시를 보존한다. 0.7 이상이라는 이유로 라벨 의미가 정확하다고 보증하지 않는다. P3 선택 문장이 원문 줄의 유일한 순서 대응으로 확인될 때만 해당 줄의 하위 라벨을 검색 뷰에 전달한다. 확인되지 않은 P3 문장에는 영역 전체의 라벨을 덮어씌우지 않고 원문·선택 문장을 모두 보존하며 사람 확인으로 남긴다.

P3가 원문의 일부 줄만 선택한 경우에도 대응이 입증된 줄의 좌표·문자 범위·표 행을 유지한다. fine 청크는 자기 줄만 참조하고 다른 청크/생략된 줄의 라벨을 가져오지 않는다. 중복 문장, 바뀐 숫자, 줄 일부만 일치한 경우를 정확 대응으로 승격하지 않는다. 색상·폰트·크기·시인성은 기존 사람 검토 범위를 유지한다.

## 현행 시인성·판독 불확실성 처리 범위

2026-09-15 사용자 결정: 현재 파서는 원문 위치를 위한 bbox만 제공하는 범위로 진행한다. 색상·폰트·글자 크기·대비·가독성·시인성·레이아웃 판정은 사람 검토로 넘기며 측정 기능 개발을 선행조건으로 요구하지 않는다. 기존 style 값이나 bbox가 있더라도 자동 시인성 판정을 재활성화하지 않는다. 좌표는 원문 위치 확인용이며 글자 크기나 색상을 추정하는 근거가 아니다.

기존 운영 P1/P3는 원문·줄 참조·bbox·읽기 상태의 검색/인용/좌표 표시/사람 검토를 지원한다. 신규 ETL→KL HRC 출력은 별개이며 HRC 단독으로는 원문 줄·좌표·부분 실패 정보가 부족하다. 원시 Default JSON 또는 허용된 증거 sidecar의 전달과 우리 버전 어댑터가 필요하다. 표·각주 연결이 없거나 복합 의무의 조건/예외가 불명확하면 자동 완전 판정을 보장하지 않고 사람 검토로 남긴다.

이 절은 아래 패킷의 과거 시인성 확장 요구보다 우선한다. 폰트·글자 크기·색상·대비 산출은 이번 인계의 필수 수용 조건이 아니다.


## 0. Agent entrypoint

```yaml
packet_id: nh-parser-evidence-handoff-20260915
audience: parser_repository_coding_agent
language: ko
self_contained: true
reading_order: ["0", "1", "2", "3", "3.1", "4", "5", "6", "7", "8"]
essential_intent:
  - 원문 추출과 증거 전달을 수정하는 요청이지 심의 모델/규칙을 파서 안에 구현하라는 요청이 아님
  - 필드 존재가 아니라 원문 의미와 위치 및 불확실성이 소비 단계까지 보존되는지가 완료 기준
  - 현재 downstream 판정도 미완성임; 모든 오판을 파서 탓으로 돌리거나 파서 완료로 전체 심의 정확도를 보장하지 않음
task:
  objective: 광고 심의 소비자가 원문/위치/읽기 품질을 손실 없이 받도록 추출과 전달 경계를 검증하고 보완
  first_action: 실제 checkout과 배포 commit 확인 후 아래 issue/requirement의 현재 해당 여부 대조
  implement: 자신의 저장소 권한과 확정 계약 안에서 일반 결함 수정 + 양성/음성/경계 테스트; 발견 목록만 작성하고 수정 없이 완료 처리하지 않음
  proposal_only: KL 허용 형식 변경, 신규 외부 전송/저장소, 고객사 배포 변경, 새로운 API 계약
  do_not_infer: 이 문서만으로 고객사 원문 외부 업로드·실행 중 서버 재시작·기존 결과 삭제 권한을 얻었다고 해석하지 않음
evidence_labels:
  SOURCE_AUDIT: 아래 고정 commit의 소스에서 확인
  SYNTHETIC_REPRO: 합성 입력/모의 실행에서 재현; 실제 OCR 성능 측정 아님
  LEGACY_ARTIFACT: 기존 P1/P3 실행 산출물·원본 대조; 새 ETL 실행의 결과 아님
  IMPLEMENTED_LOCAL: 우리 소비 코드 수정 및 로컬 테스트; 배포/실광고 재실행과 구분
  LIVE_SPARK_DIAGNOSTIC: 기존 파싱과 격리 교정 입력으로 실제 검색/판정 실행; 고객사 ETL OCR 실행이나 holdout 평가 아님
  UNVERIFIED: 추가 실행 또는 담당자 확인 필요
compatibility:
  required: 아래 정보의 의미 보존
  not_required: 특정 필드명, P1/P3 신규 생성, 우리 내부 스키마 직접 출력, 의미 라벨러 신규 개발
  migration: 현재 원시 필드 보존 또는 승인된 증거 sidecar + 우리 버전 어댑터 우선; 전면 교체도 합의/회귀 검증 후 가능
```

이 패킷은 작업 요청 데이터다. 수신 저장소의 상위 보안 지침·AGENTS·고객사 계약을 우회하지 않는다. 과거 채팅이나 접근 불가능한 우리 로컬 산출물이 없어도 아래 요구사항으로 작업 가능하다. 파일 경로는 탐색 힌트이며 최신 코드의 위치/상태를 다시 확인한다.

## 1. 목표 시스템과 환경

```text
등록: 광고 ID + 원본 파일들 + 사용자 확정 상세 상품군 + 매체
→ 파일별 파싱: 전체 원문/원본 위치/읽기 상태/표/가능한 스타일
→ 우리 어댑터: 사용자 입력 결합 + 내부 ID + 같은 광고 파일 결합 + 상품/공통 근거 범위
→ 우리 청킹: 조건·수치·제목·각주 문맥 보존
→ 템플릿 항목 전수검사 → 매핑 v2 우선검사 → v2 조건부 보완 검색
→ 조건 먼저 확인 → 의무/근거별 판정 → 읽기 품질/출력 검증 → 사람 검토·bbox·결과 저장
```

- 템플릿: 일반 템플릿 HWPX의 구분·필수 여부·기재요령을 독립 항목으로 사용. v2 매핑 없이도 검사한다. 예시는 의미 참고이며 동일 문구 강제가 아니다.
- 템플릿 필수항목은 검색 hit를 전제로 검사하지 않는다. 검색은 광고→보완 규칙 발견과 규칙→광고 근거 회수의 두 방향이며 별도 평가한다. 검색 결과 없음은 문구 부재 증거가 아니다. 파서도 검색/라벨에 선택되지 않은 원문을 버리지 않는다.
- 규제목록 v2: 세부 조건·법령 근거와 템플릿 밖 금지/오인 등 보완 검색. 파서는 이 규칙을 판정하지 않는다.
- 광고: 판정 대상의 실제 원문이다. 라벨 설명·템플릿 예시·모델 생성 문장은 광고 본문을 대체하지 않는다.
- 심의사례/기존 답지: 개발·평가 자료. 파서 추출/운영 검색/판정에 답을 주입하지 않는다. 특정 광고 문구·이름·규칙 ID 맞춤 예외 금지.
- 우리 개발·시연: DGX Spark. 최종 고객사: H200 + DAP/Jupyter Python 3.11, 고정 패키지 기준. 고객사 ETL은 우리 로컬에서 직접 실행할 수 있다고 가정하지 않는다.
- Spark의 기존 OCR/VLM provider와 고객사 ETL provider는 다르다. 공통 증거 계약/변환 로직은 재사용할 수 있지만 주소 변경만으로 동일 OCR 성능·동일 응답을 얻는 것은 아니다. 고객사 전용 모듈은 provider 경계로 분리한다.

## 2. 서로 다른 두 파서 계열 — 혼동 금지

### NEW_CUSTOM_PARSER

```yaml
repository: https://github.com/cg-wnsdud/nh-custon-parser
audited_ref: main
audited_commit: 23d1dcc25fd4c70f4ad1cc1bc6ba0a3214306a4e
commit_meaning: 2026-09-15 확인한 소스 스냅샷; 수신 시 최신 HEAD 또는 실제 배포본이라는 보장 없음
flow: original -> ETLwithLLM -> Default_JSON -> internal_normalization -> Knowledge_Lake_HRC_JSONL_INFO_ZIP
ocr_implementation: 외부 ETL 서비스; 이 저장소 자체가 OCR 모델을 구현하는 것은 아님
labels: Title/Text/Table/Figure 같은 구조 유형; 광고 심의 의미 라벨과 다름
verified:
  - 저장소 단위/모의 API 테스트 15개 통과
  - 아래 손실·상태·페이지·프로세스 경계의 합성 재현
unverified:
  - 실제 고객사 배포 commit 및 실제 Default JSON
  - PDF/PNG/HWP 등의 OCR 정확도와 작은 글씨/표 누락률
  - KL 등록 후 증거 보존, H200 모델/패키지 조합
```

### LEGACY_P1_P3

- 흐름: 원본 → P1(`nh-ad-parse-evidence-v1`, 원문 후보·줄·좌표 등) → P3(`nh-ad-region-review-input-v1`, 영역별 선택 텍스트/라벨/줄 참조) → **우리 검색 청킹**.
- P1은 원본 파일 그 자체가 아니고 P3도 검색용 청크가 아니다. P1/P3는 기존 파서 계약/산출물 구분이며 새 custom parser에 같은 출력을 요구하지 않는다.
- LEGACY_ARTIFACT 표본: 6쪽·30영역·673줄. 673줄에 bbox/confidence가 있었지만 물리 페이지 크기·값이 채워진 style·채워진 표 구조는 확인되지 않았다. 전체 형식의 지원 여부로 일반화 금지.
- 실제 원본에 있는 문구가 OCR에서 깨지거나 선택 본문에서 빠졌고, 라벨 설명에는 관련 개념이 남아 있었다. 라벨은 별도 추론 결과일 수 있으므로 라벨 존재는 실제 문장의 추출·전달 증명이 아니다.
- 15개 청크는 영역 연결만 입증되고 정확한 줄 대응은 미입증. 문장 수에 맞춰 원문 줄을 임의 분할/배정해 exact로 만들지 않는다.
- 기존 충족33건의 Codex 원본 육안 대조: 동의25/보류8. 수요사 확정 gold가 아니고 보류8 모두 오판 확정이라는 뜻도 아니며 새 ETL 성능 수치도 아니다.

## 3. 우리 쪽에서 고쳤거나 맡는 것 — 파서에 전가하지 않음

```yaml
owner: review_pipeline
implemented_local:
  - needs_review/부분 읽기 보존 및 전체 읽기 READY 판정에 반영
  - 불확실한 근거에 의존한 충족/미기재/적용성 확정의 사람 검토 전환
  - 별도 명확한 근거/독립 위반 유지; 원래 모델 응답과 변경 사유 감사 보존
  - 부모 영역 ID와 작은 청크 ID 차이로 스타일이 빠지던 전달 수정
  - 충족 수치의 원문 줄 대조, 조건 인용의 규칙별 근거 범위 검사
  - 공급된 observed 관계의 검색 문맥 확장; 추정/범위 밖 관계는 별도 보류
  - 명시 의무 O ID별 검사 완전성 및 v2 비고의 적용범위 계약 보존
  - 부분 스캔의 부재/전체 완전성 판단과 명확한 문구 존재 판단을 구분하도록 일반 프롬프트 보완
validation: 최신 로컬 RAG CI 233개 + 함수 검사21개 통과; 앞선 실제64규칙 새 계약 형식검사 통과
limits:
  - 실제64규칙은 SOURCE_TEXT_ONLY; 모든 복합 기준의 의무 원자화 완료 아님
  - 기존 보류8건 실제 재판정/정답 확정 미완료
  - 후속 Spark 진단 검색/판정 실행 있음(3.1절); 운영 서버 재시작/기존 운영 결과 교체 없음
  - 정상 근거에서도 과도한 기권과 빈 객체 출력 오류가 남음; 프롬프트 보완으로 완전히 해결됐다는 주장 금지
  - 관측되지 않은 원문/좌표/표 관계는 후처리로 복원 불가
```

우리 책임: 사용자 확정 상세 상품군/매체·광고/파일/상품 ID 관리, 내부 템플릿 선택, 동일 광고 결합, 청킹/검색/규칙/판정, 화면 좌표 변환. 파서가 호출자의 메타데이터를 받는다면 원값을 그대로 보존하고 추론은 별도 observations에 둔다. 최소한 응답과 업로드 파일을 확실히 대응시키는 키가 필요하다.

### 3.1 최신 분리 시험 — 파서 요청의 근거와 한계

```yaml
evidence_class: LIVE_SPARK_DIAGNOSTIC
date: '2026-09-15'
input_lineage: 기존 P1/P3 기반 동일 광고6파일; 새 고객사 Default/HRC 실행 결과가 아님
arms:
  legacy: 기존 파싱 입력을 현재 청킹/검색/판정 코드로 처리
  corrected: 원본6쪽의 표/조건/각주/표시문구13줄만 시각 대조 교정하고 검색부터 처리
  oracle: 규칙과 원본 대조 근거를 직접 제공해 판정만 처리; 규칙 ID 지정은 이 진단 arm에서만 허용
isolation:
  - 교정 텍스트와 명시적 근거 묶음을 함께 바꿨으므로 OCR만의 인과 효과로 해석하지 않음
  - 전체 광고의 정상 전사본은 아님; 나머지 불확실성/금리 공란/파일 간 수치 차이 유지
  - 모든 요청 complete_ad_scan=false; 가짜 전체 읽기 완료로 정확도를 높이지 않음
  - 운영 원문/기존 판정 해시 불변; 교정본/규칙-근거 지정표는 진단 전용으로 격리
  - 검색에는 목표 규칙/근거 ID를 주지 않고 결과 동결 후 별도 평가
search_observations:
  - 두 입력 모두 템플릿16항목을 열거하고 요청함; 검색 미검출을 필수항목 검사 제외 사유로 사용하지 않음
  - 설명받을 권리/약관 필독 안내는 기존 요청의 정확한 근거 줄0, 교정 후 각각1줄 회수
  - 이자지급제한은 기존에도 줄 ID가 있었지만 문자가 깨져 실제 의미 근거로 충분하지 않았음
  - C-049는 교정 검색 후 카테고리 실행 예산 때문에 보류됨; 파서 누락/검색 미발견/미해당으로 분류하면 안 됨
judge_observations:
  - 초기17쌍 중 유효 계약16/출력실패1; 일반 프롬프트 보완 후17쌍 중 유효15/출력실패2
  - 직접 제공한 명확한 지급제한 문구를 모델이 인정하면서도 전체 PARTIAL을 이유로1건 기권이 지속됨
  - 출력실패는 재시도 후 빈 결과 객체 등 형식 오류이며 법규상 판단불가와 다름
  - 첫 만기후이율 oracle은 금리조회 탭 조건 근거가 빠졌고 후속에서만 추가; 그 행의 차이는 프롬프트만의 효과가 아님
projection_observations:
  - 공통 화면/다운로드 변환 함수에서 각17건 결론/이유/인용/처리실패 분리를 대조
  - 브라우저 재배포/원본 bbox 육안 재검사는 미실행; 실제 위치 정확도 전수 통과를 뜻하지 않음
conclusion:
  - 정상 원문과 근거 구조 전달은 필요하지만 충분조건이 아님
  - 파서 담당은 원문/조건/수치/각주/좌표/읽기 상태 보존에 집중
  - 과도한 기권, 일부 근거로 전체 충족, 빈 판정 객체, 검색 예산은 우리 소비 경로의 과제
```

따라서 파서의 `needs_review`를 없애거나 전체 상태를 강제로 `READY`로 만들지 않는다. **구간별 판독 상태를 정확하게 제공**해야 우리 쪽이 (a) 그 구간의 명확한 존재 증거는 사용하고, (b) 읽지 못한 곳에 있을 수 있는 문구의 미기재 확정은 막을 수 있다. 모델의 기권을 줄이기 위해 원문 문구를 템플릿 예시와 같게 고쳐 출력하는 것도 금지한다.

## 4. 고정 commit 감사에서 발견한 전달·운영 이슈

| ID / 우선순위 | 확인/탐색 위치 | 상태·문제 | 필요한 처리 |
| --- | --- | --- | --- |
| I01 / P0 | `parsing_service.py` | SOURCE_AUDIT: 원시 Default JSON 미저장 | 승인 저장/참조 방식으로 원시 응답과 실행 버전 보존. 재파싱 없이 손실 경계 대조 가능하게 함 |
| I02 / P0 | `hrc_exporter.py` | SOURCE_AUDIT: 내부 줄/문단 ID·bbox·confidence 등이 HRC 증거로 전달되지 않음; 제목 page도 없음 | KL 출력 계약 유지하면서 승인된 별도 증거 전달 경로 협의. HRC만으로 우리 증거 계약 충족 주장 금지 |
| I03 / P0 | `etl_adapter.py` | SOURCE_AUDIT: `parentId`, `childId`, `error_type`, `list_hierarchy`를 읽는 필드로 분류하나 내부에 보존하지 않음 | 원시값 또는 명시적인 동등 의미 필드로 보존; 알 수 없는 새 필드도 원시 보관에서 손실 방지 |
| I04 / P0 | adapter/exporter | SYNTHETIC_REPRO: 셀만 있고 본문이 빈 표가 누락; `pageLen` 불일치는 경고만 남고 일부 텍스트로 `parsed_status=S` 가능 | 셀/HTML 보존, 오류/미처리/빈 페이지 구분. 처리 성공과 전체 판독 성공을 별도 표현 |
| I05 / P1 | 페이지 정규화 | SYNTHETIC_REPRO: 입력 pageId 0,1 → 출력1,1 | 실제 provider 기준 0/1-based 확인, 전체에 일관된 변환·중복검증. 개별 값 truthy fallback 금지 |
| I06 / P1 | 하위 프로세스 실행 | SYNTHETIC_REPRO: communicate 후 returncode 미검사로 초기 exit1이 PARSING에 잔류 가능 | 비정상 종료/타임아웃을 terminal failure로 기록; 성공 산출물/로그 보존 |
| I07 / P1 | ZIP 응답/정리 | SOURCE_AUDIT: 전달 전에 작업 폴더 삭제 | 계약에 맞는 수신 확인 또는 보존/재수신/TTL 정책 협의. 응답 생성 성공을 수신 완료로 간주 금지 |
| I08 / P1 | `main.py` filename/uuid | SOURCE_AUDIT: 입력을 경로에 바로 결합하며 삭제도 수행; 실제 공격 재현은 하지 않음 | 저장 파일명 서버측 결정, ID 검증, resolve 후 작업 루트 containment, 승인된 작업 폴더만 정리 |
| I09 / P2 | 업로드/ETL 호출/정리 | SOURCE_AUDIT: 큰 객체 메모리 적재, 일시 실패 재시도/품질 재분석 부재, README 24시간 정리 구현 미확인 | 크기 제한·timeout·재시도 가능 오류 분류·시도별 로그/보존부터 확인. 무제한 재시도·품질 무검증 덮어쓰기 금지 |

수신 시 이미 고친 이슈는 재수정하지 말고 commit·테스트 증거로 종료한다. 위 이슈를 실제 고객사 OCR 오독의 증거로 사용하지 않는다.

## 5. 필요한 정보와 이유 — semantic requirements

각 R 항목에 `RAW_PRESENT / DELIVERY_FIX / EXTRACTION_REQUIRED / UNSUPPORTED / UNVERIFIED` 중 하나와 실제 필드 경로를 회신한다. 원시에 있으면 전달 수정, 원시에도 없으면 추출/재판독 또는 미지원 명시다.

| ID / 우선순위 | 필요한 정보 | 이유 / 소비 동작 |
| --- | --- | --- |
| R01 / P0 | 파일 대응 키, 원본/원시 결과 참조·해시, 파서/provider 모델·설정 버전 | 다른 파일/시도 결과 혼합 방지, 재현/재시도/증거 추적. 실제 값 없는 해시를 꾸며 넣지 않음 |
| R02 / P0 | 전체 페이지/영역/줄 원문, 읽기 순서, 원문 출처(digital/OCR/VLM/unknown) | 필수 문구 누락 판정과 금지 문구 검색. 선택/요약 밖 문장도 검색 가능해야 함. 작은 글씨·표·각주·미배정 줄 포함 |
| R03 / P0 | 파일/페이지/영역/줄 대응, bbox·기준 렌더·크기·단위·회전/크롭·변환 | 원본 강조, 정확한 인용, 위치/인접성 검토. 기존 위치가 있어도 내보내기에서 빠지면 소비 불가 |
| R04 / P0 | 예상/처리/실패/미처리 페이지, 빈 페이지와 실패 구분, 부분/전체 읽기, 불확실 구간/사유·retryable | 못 읽은 곳을 ‘미기재’로 오판하지 않기 위함. 프로세스 DONE이나 텍스트 일부 존재는 전체 판독 완료 증거가 아님 |
| R05 / P0 if selection exists | OCR/VLM 후보·선택 출처·교정 이력 참조, 선택 문장의 source line/region, mapping 정밀도, needs_review/이유 | 잘 읽힌 일부를 전체로 착각하지 않기 위함. 라벨 설명과 본문 혼동 방지. 선택 단계가 없으면 N/A로 명시하고 새 단계 생성 불필요 |
| R06 / P1 | 표 HTML 또는 행/열/병합/셀 원문·위치·원문 참조 | ‘최고금리/기본금리’, 기간/금액/조건이 다른 셀과 섞이지 않게 함. 본문이 비어도 셀 정보 보존. 글만 이어붙인 표는 관계 손실 가능 |
| R07 / P1 | 가능한 글자 크기/굵기/색상/대비 및 값·단위·방법·출처·미지원 사유 | 시인성/강조 검토. font metadata pt와 OCR glyph bbox px를 구분; 렌더 DPI만으로 실제 인쇄 mm 추정 금지 |
| R08 / P1 if observed | 제목→값, 각주→본문, 연속 표/페이지 등의 원시 관계·양끝 참조 | 떨어진 조건·각주를 함께 검색. provider가 주면 보존; 없으면 우리 추론과 observed 구분. 법규 적용 여부 생성 요청 아님 |
| R09 / optional | 구조 역할/의미 라벨과 근거/출처/신뢰도 | 검색 보조. 사용자 상세 상품군 대체·템플릿 확정·근거 본문 대체·단독 제외 필터로 사용 금지 |

읽기 상태는 더 정교하게 요청한다. 최소 원시 warning/error를 보존하고, 가능한 작은 구간에 연결한다. 전체 파일에만 `needs_review=true`가 있으면 우리 쪽은 넓게 보류할 수밖에 없다. 반대로 측정하지 않은 구간을 임의로 `false`로 바꾸어 보류 수를 줄이지 않는다. `unknown`은 `false`가 아니다.

파서 단계에서만 해결할 수 있는 경계: 원시 결과 자체의 누락/오독 재판독, 원본에 대응하는 관측 좌표·렌더 기준 추출, 셀/스타일/읽지 못한 영역의 관측. 원시 결과에 이미 있으면 **추출 재개발 없이 전달 수정**이다. 우리 후처리로 가능한 경계: 원시 ID의 이름 공간 변환, 제공된 좌표 변환, 사용자 입력 주입, 근거 연결/청킹/검색, 적용조건·의무별 판정 및 사람 검토. 관측 관계가 없어 우리가 추론한 것은 observed로 승격하지 않는다.

## 6. 전달 데이터 형태 — 의미 예시, 현재 API/JSON Schema 아님

아래는 **합성 자료의 독립 예시**다. 필드명·enum은 협의용이며 그대로 기존 운영 어댑터에 넣으면 호환된다는 뜻이 아니다. 현재 Default JSON을 원형 보존하고 field mapping만 합의해도 된다. 사용자 입력과 내부 ID는 우리 쪽이 추가할 수 있다. ID 생성 시 파일/페이지 범위와 재시도 버전을 구분한다.

```json
{
  "contract": "parser-evidence-semantic-example-v1",
  "status": "PROPOSAL_NOT_DEPLOYED",
  "source": {
    "asset_key": "synthetic-file-a",
    "original_filename": "synthetic.pdf",
    "source_sha256": null,
    "raw_artifact_ref": "opaque-internal-artifact-id",
    "raw_sha256": null,
    "parser_commit": "synthetic-build",
    "provider": "synthetic",
    "provider_version": null,
    "models": {},
    "settings_sha256": null
  },
  "caller_context": {
    "advertisement_id": "synthetic-ad-a",
    "product_classification_code": null,
    "media_codes": [],
    "authority": "caller_unmodified"
  },
  "coverage": {
    "expected_pages": 1,
    "processed_page_ids": ["f1:p1"],
    "failed_page_ids": [],
    "unprocessed_page_ids": [],
    "read_status": "partial",
    "complete_document_read": false,
    "warnings": ["unread_region_present"]
  },
  "pages": [{
    "page_id": "f1:p1",
    "provider_page_id": 0,
    "provider_page_index_base": 0,
    "original_page_no": 1,
    "parse_status": "partial",
    "coordinates": {
      "render_ref": "opaque-render-id",
      "canvas_width": 1000,
      "canvas_height": 1400,
      "unit": "px",
      "origin": "top-left",
      "bbox_format": "xyxy",
      "rotation_degrees": 0,
      "crop_box": null,
      "source_to_canvas": null,
      "physical_size_mm": null,
      "unavailable_reason": "원본 변환/물리 크기 미제공; bbox는 지정 렌더 기준"
    },
    "lines": [
      {"id":"f1:p1:L1","region_id":"f1:p1:R1","text":"구분","bbox":[20,20,100,40],"source":"digital","confidence":null,"reading_status":"readable","needs_review":false,"style":null},
      {"id":"f1:p1:L2","region_id":"f1:p1:R1","text":"값 A","bbox":[20,50,100,70],"source":"ocr","confidence":null,"reading_status":"uncertain","needs_review":true,"reason":"일부 문자 판독 불확실","style":null}
    ],
    "selected_segments": [{
      "id":"f1:p1:S1","text":"값 A","source_line_ids":["f1:p1:L2"],
      "mapping_status":"exact","selected_source":"ocr",
      "needs_review":true,"reason":"줄 대응은 정확하나 문자의 정확성은 미확정"
    }],
    "tables": [{
      "id":"f1:p1:T1","structure_status":"observed",
      "cells":[
        {"id":"c1","row":0,"col":0,"row_span":1,"col_span":1,"text":"구분","line_ids":["f1:p1:L1"],"bbox":[20,20,100,40]},
        {"id":"c2","row":1,"col":0,"row_span":1,"col_span":1,"text":"값 A","line_ids":["f1:p1:L2"],"bbox":[20,50,100,70],"header_cell_ids":["c1"]}
      ]
    }],
    "relations": [{"type":"header_for","from_line_ids":["f1:p1:L1"],"to_line_ids":["f1:p1:L2"],"basis":"observed"}],
    "unread_regions": [{"region_id":"f1:p1:R2","bbox":[20,900,980,1250],"reason":"텍스트 검출 후 판독 실패","retryable":true}]
  }],
  "capabilities": {
    "font_metadata":"unsupported",
    "contrast_measurement":"unsupported",
    "physical_dimensions":"unavailable"
  }
}
```

### 의미 계약

- `exact`는 **선택 결과와 원문 참조의 대응**이지 OCR 문자의 정답 보장이 아니다. `exact + needs_review=true`는 가능하다. 영역만 연결되면 `region_only`, 대응 불명이면 `unresolved`; 모든 줄을 붙여 exact로 표시 금지.
- 원문 전체 저장소와 선택 뷰를 분리한다. 선택되지 않은 줄도 원문에 남겨야 한다. 파서가 선택 기능을 제공하지 않으면 selected_segments는 생략 가능하다.
- 같은 원문 줄이 여러 선택 문장의 근거가 될 수 있으므로 다대다 출처 연결을 허용한다. 원문 ID 중복/충돌과 정상적인 다대다 참조를 혼동하지 않는다. 소유권 배정은 우리 어댑터에서 별도 검증한다.
- bbox가 없으면 null + unavailable reason. `(0,0,0,0)` 같은 가짜 좌표로 채우지 않는다. 좌표가 부모 영역 수준이면 줄 정확도라고 표시하지 않는다.
- affine을 제공한다면 `[a,b,c,d,e,f]`, `x'=a*x+c*y+e`, `y'=b*x+d*y+f`. 원점·단위·크롭·회전이 적용된 단계와 참조 이미지가 명확해야 한다.
- 표 셀 text와 정본 줄 text가 다르면 조용히 덮어쓰지 말고 충돌/선택 이력으로 보존한다. 표 제목·행/열·각주를 이용해 수치를 다른 조건과 연결하지 않도록 한다.
- confidence는 해당 provider의 척도/대상과 함께 전달한다. 임의 공통 임계값으로 법규 충족/위반을 생성하지 않는다. 미측정은 null/unknown이고 0이나100이 아니다.
- 스타일은 실제 제공 가능한 `value/unit/source/method`만 전달한다. 이미지 glyph_height_px와 선언 font_size_pt를 구분한다. 대비 관측에는 측정 대상·방법·전경/배경 근거가 필요하며 없는 값은 추정 생성하지 않는다.
- 성공/부분/실패를 구분하고 성공 데이터는 보존한다. 파일 단위 재시도만 지원한다면 그 사실을 기록한다. 지원하지 않는 페이지 단위 재시도를 약속할 필요는 없다.
- 원시 응답은 접근 통제된 승인 경로에 보존하고 URL 자격증명·토큰을 패킷/일반 로그에 넣지 않는다. KL ZIP 허용 형식은 그대로 유지한다. 증거 동반 경로는 합의 전 임의 구현/배포하지 않는다.

## 7. 작업 순서와 수용 테스트

```yaml
sequence:
  - checkout/deployment commit 확인; Default JSON과 HRC의 실제 필드 매핑 작성
  - I01..I04/R01..R05: 원시 증거·위치·읽기 상태 손실 및 부분성 처리부터 수정
  - I05..I09: 페이지/프로세스/복구/파일 경계 확인; 변경 권한 밖 정책은 명시 질문
  - R06..R08: 이미 있는 표/스타일/관계 보존; 없는 관측은 지원 여부 회신
  - 합성 계약 검사 수행; 가능한 환경에서 동일 원본의 단계별 대조
  - 변경 commit/정확한 실행 명령/검사 결과/미지원 필드/실환경 미검증을 인계
```

| Test ID | 입력/상황 | 기대 결과 |
| --- | --- | --- |
| A01 | 동일 광고2파일 + 독립 광고1파일, 같은 로컬 page/line 번호 | 파일 대응·네임스페이스 충돌 없음; 독립 광고 내용 혼입 없음 |
| A02 | provider pageId 0,1 및 별도 1,2 fixture | 각각 정상2페이지 또는 명시적 계약 오류; 1,1로 조용한 병합 금지 |
| A03 | 전체 원문에서 일부만 선택; 선택 텍스트 OCR 교정 | 원문 전체·선택 이력 보존, 참조 정밀도 정직하게 표시, 미선택 줄 미소실 |
| A04 | OCR/VLM 불일치·저신뢰 줄·일부 미판독 영역 | 관련 ID/사유 보존; 부분 읽기를 전체 완료로 승격하지 않음 |
| A05 | 정상 빈 페이지, 실패 페이지, 미처리 페이지 각각 | 서로 다른 상태. expected/processed/failed가 모순되면 검증 실패 또는 partial |
| A06 | 본문 빈 표지만 셀/HTML 있음, 병합셀·금리/조건 열 | 셀 보존; 행/열/병합과 헤더-값 관계 유지; 원문과 셀 충돌 기록 |
| A07 | PNG/이미지 PDF/디지털 PDF; 회전/크롭/해상도 변화 | 실제 동일 렌더에서 bbox가 해당 문구를 지시; unknown 변환은 명시 |
| A08 | 스타일 미지원 PNG와 실제 font metadata 제공 문서 | 미지원 null/사유; 관측 px/pt 구분; 물리 크기·대비 임의 생성 없음 |
| A09 | 파서 초기 import 실패, exit!=0, timeout | PARSING에 영구 잔류하지 않고 오류/시도 이력/성공 산출물 보존 |
| A10 | 일시 ETL 실패와 영구 형식 오류 | 허용된 일시 오류만 제한 재시도; 시도별 원인 보존; 무한 반복/원본 덮어쓰기 없음 |
| A11 | 결과 응답 중 연결 단절 | 합의된 보존/재수신 정책 확인; 전송 전 삭제로 유일 증거 상실하지 않음 |
| A12 | 악성 filename/uuid/경로, 과대 업로드 | 임시 fixture 내부에서 검증; 작업 루트 밖 접근/삭제 금지, 크기 제한 |
| A13 | 입력 상세 상품군/매체와 모델 추정 다름 | 호출자 확정값 유지; 추론은 별도. 템플릿 선택/법규 verdict 생성하지 않음 |
| A14 | 다른 페이지 각주·표 연속 및 추정 관계 | 실제 관계만 observed, 소유권/양끝 존재 검사. 추정 관계를 사실로 승격 금지 |
| A15 | 같은 원본의 Default → 정규화 → HRC + 승인 증거 채널 | 각 R 항목이 어디서 유지/소실되는지 필드별 확인. HRC 계약과 증거 계약 별도 검사 |

완료 보고는 필드가 있는 JSON 한 건으로 대체하지 않는다. 원본→원시 추출→정규화→최종 전달을 따라 각 테스트의 실제 값을 비교한다. 원문 줄 참조 유효성, 의미상 정상 전사, 해당 문구를 지시하는 bbox는 각각 별개 검사다. 새로운 모델 호출이 필요한 경우 고객사 승인 경로/실행 권한부터 확인하고, 그렇지 않은 전달 결함은 합성 fixture로 먼저 수정·검증한다.

실제 고객사 환경에 접근하지 못하면 A15의 실제 ETL 실행은 `UNVERIFIED_ENVIRONMENT`로 보고한다. 모의 Default fixture로 변환/오류 처리는 검증 가능하지만 실제 OCR 품질이나 고객사 연동 성공으로 보고하지 않는다. 고객사 권한자가 실행할 재현 절차를 남긴다.

## 8. 우리에게 반환할 결과 형식

```yaml
parser_handoff_response:
  inspected_commit: null
  deployed_commit: null
  environment: null
  requirement_mapping:
    - id: R01
      status: UNVERIFIED
      raw_field_paths: []
      exported_field_paths: []
      owner: parser_or_etl_or_review_pipeline
      change: null
      unsupported_reason: null
      test_ids: []
  # R01..R09 각각 한 행. 해당 기능이 없다면 미지원/비해당 사유를 적고 생략하지 않음.
  issues:
    - id: I01
      status: OPEN
      evidence: null
      fixed_commit: null
  tests:
    - id: A01
      kind: synthetic_or_real
      command: null
      outcome: NOT_RUN
      artifact_ref: null
  proposed_delivery_channel: null
  approval_needed: []
  remaining_extraction_gaps: []
  consumer_adapter_changes_needed: []
  contract_version_and_migration: null
  executable_reproduction_commands: []
  raw_to_export_loss_audit: []
  unverified_items_with_reasons: []
  real_etl_and_kl_verified: false
```

가능한 환경에서 **동일 원본 + 실제 Default JSON + 최종 HRC + 승인된 증거 산출물**을 내부 승인 경로로 대조한다. 이 문서 전달이 해당 자료의 외부 전송 승인은 아니다. 실제 자료가 없으면 필드 매핑과 합성 재현부터 완료한다.

## 9. 출처·추적 정보

패킷 작성 근거: `nh-ad-compliance/docs/parser-handoff-quickstart.md` v1.5, `parser-schema-change-request-current.md` v1.8, `custom-parser-audit-current.md` v1.0, `pipeline-design-review-current.md` v1.11, `handoff-current.md` v1.31. 최신 실측 근거는 우리 로컬 `output/pipeline-end-to-end-20260915/separation-diagnostic/comparison.json`과 원본/예측 freeze다. 위 내용은 본문에 의미를 포함했으므로 수신 측이 이 파일들을 모두 읽거나 접근할 필요는 없다. 원본·판정문·접속정보는 이 패킷에 첨부하지 않았다.

우리 코드 탐색 힌트: `rag-pipeline/rag/parsing/parser_contract_adapter.py`, `rag/judgment/reading_quality.py`, `rag/judgment/condition_contracts.py`, `tools/run_operational_e2e.py`, `tools/run_gemma_exhaustive_dgx.py`(마지막 네 경로도 rag-pipeline 아래). 이 코드의 수정 책임은 우리 쪽이다.

기존 `parser-handoff-vnext-proposal` JSON/Schema도 협의안이다. 위 semantic-example은 설명 범위를 넓힌 별도 예시이며 기존 proposal Schema 검증 대상이 아니다. 합의되면 최종 wire 계약을 단일 버전으로 확정하고 양측 adapter/검증기를 맞춘다. 이 문서 작성으로 운영 스키마를 변경하지 않았다.

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.6 | 2026-09-16 | 한 줄의 복수 명시 표제 라벨 보존과 묶음 진단 경계 |
| v1.5 | 2026-09-16 | 라벨 입력의 원문 품질·전체 기재요령·P3 보조 문맥 전달과 실제 전체 심의 검증 |
| v1.4 | 2026-09-16 | 비연속 라벨 줄 선택과 P1 내보내기·검색 입력의 범위 재검증 |
| v1.3 | 2026-09-15 | 상위 템플릿 자동분류 제외와 하위 라벨/원문 대응 책임 추가 |
| v1.2 | 2026-09-15 | 시인성 좌표 전용·사람 검토 범위와 현행 스키마 수용 경계 반영 |
| v1.1 | 2026-09-15 | 최신 Spark 분리 진단 반영, 필요한 관측/전달과 우리 판정 오류의 경계·비희석 작업 지시·완료 증거 보강 |
| v1.0 | 2026-09-15 | 수신 코덱스용 독립 패킷: 계열/환경/책임/요구 이유/합성 스키마/이슈/수용 검사/반환 계약 통합 |
