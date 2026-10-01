# 최신 파서 계약과 운영 연결

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.4 |
| 기준일 | 2026-09-30 |
| 확인한 저장소 | [nh-parser-fin](https://github.com/cg-wnsdud/nh-parser-fin/tree/4968fa526d32183d656d011f9e986cdd9fd7b637) |
| 확인한 main | `4968fa526d32183d656d011f9e986cdd9fd7b637`(Python 3.11·`--template-id`, `parser-pipeline/` subtree) |
| 최신 외부 계약 | P1 `nh-ad-parse-evidence-v5` / P3 `nh-ad-region-review-input-v10` |

## 2026-09-30 저장소 편입과 사용자 템플릿

파서는 저장소의 `parser-pipeline/`(nh-parser-fin subtree)로 편입했다. 새 실행은 `nh_parser_fin`·`region-v10`만 사용하며, 아래 region-v9·외부 checkout 기록은 당시 운영 배포 이력이다. 브리지는 사용자 선택 템플릿을 `run.py --template-id`로 전달하고, 파서는 상품 소유권만 판정한 뒤 모든 상품·공통·미확정 영역에 그 템플릿의 구분값을 쓴다. P1 `template`과 P3 `document.template`이 `source: user_provided`로 사용자 값과 같아야 심의를 진행한다. 앱 이름 `예금성상품-지수연동예금(ELD)`는 파서 카탈로그 이름 `예금성상품-지수연동예금`으로 바꿔 전달한다. 파서 카탈로그에 없는 `투자성상품-ETF`·`-ELB`는 `--template-id` 없이 파서 자동 선택으로 실행하고 P1/P3 템플릿 일치만 검사한다. `--template-id`는 nh-parser-fin main `4968fa5`(PR #4)에 반영됐고 `parser-pipeline/`은 그 커밋과 트리가 같다.

## 2026-09-30 최신 계약 연결

최신 `export.py`는 P1 v5/P3 v10을 내보낸다. P3의 영역 ID·소유 상품·bbox·최종 문구·라벨·표 구분·확인필요·문구 출처와 페이지 canvas 구조는 유지된다. `region-v10` 프로필을 추가하고 v3/v6·v4/v9 과거 저장본 읽기를 보존한다. 버전 쌍이 섞이거나 P1/P3의 소유권·좌표·캔버스가 다르면 차단한다. 실행 프로필과 40자리 파서 커밋을 intake에 함께 저장해 이전 파서 캐시를 새 결과로 재사용하지 않는다.

PDF는 디지털 여부와 관계없이 시각 레이아웃/OCR 경로를 실행한다. 최신 기본 `anchor` 모드는 영역 판독 후 디지털 글자로 문구를 교정한다. 디지털 줄 삽입·이웃 줄 중복·의심 문구 경고와 `digital_anchor` 기록은 원본 P1에 남고, 연결 어댑터는 해당 관찰·페이지 통계를 검색 입력에도 보존한다. 교정된 최종 문구를 원래 OCR 줄과 정확히 일치한다고 승격하지 않는다.

HWP/HWPX는 원본 구조와 재구성 렌더를 사용하며, 재구성 화면과 한컴 원본 조판의 동일성을 보장하지 않는다. 이미지 PDF는 신뢰 가능한 디지털 줄이 없으면 OCR/시각 판독에 의존하고, 이미지는 입력 크기 조정 후의 실제 canvas를 사용한다. 모든 형식에서 화면은 같은 실행의 `media-index.json`과 PNG·P1/P3·원본 해시를 연결한다. v10에서도 파서 페이지 이미지를 수집·제공하도록 브리지를 갱신했다.

코드 지원과 운영 설치를 구별한다. 이번 확인 시작 시 운영 r30은 `9733d9f`·region-v9였다. 아래 r18/r11b 및 6건 연결 기록은 당시 검증 이력이며 최신 파서의 전 형식 정확도 보장이 아니다. 실제 최신본 검증·배포 여부는 [인수인계](handoff-current.md)의 최상단 기록을 따른다.

## 무엇을 받는가

실제 P1/P3 6건(최신 HWP1·과거 HWP1·PDF1·이미지3)을 후보 이미지에서 읽기 전용으로 재연결했고 원본 줄·문자를 보존했다. 레이아웃 누락은0이며 통합 입력6개와 검색 문서334개가 스키마 검사를 통과했다. 최신 HWP는29줄→영역7개·검색 세부18청크다. 과거 산출물을 현재 파서로 다시 파싱한 결과는 아니며 신규 금융 판정·gold 읽기를 실행하지 않았다. RAG unittest627건·함수21건, Linux 문서 일관성·거버넌스82건이 통과했다.

농협 심의 사이트의 현재 웹은 `nh-operational:1118-semantic-r18`, 이미지 SHA `sha256:ccade7f9bb0e87575da9a7966462e9c0725b766bf22c2bc340d76e66616bd246`이며 healthy·실행 중0이다. 웹만 갱신했고 광고21건·심의35건·저장 결과22개의 ID와 결과 파일 해시가 그대로다. 정본 결합 SHA는 `281e2010bf5e624bd12488c2e9595d270bddefd55962d411fb6a82025da1ad16`, source-manifest SHA는 `b70627c9536add0366947d74f41e37a939c2397998d05e8b75dfb1585ff245c4`다. 템플릿239개·보완0개 컴파일과 승인 입력 해시를 확인했다. 새 브라우저의 오류·데이터 변경 요청은0건이다. 아래 r11b 기록은 파서 도입 당시의 이력이다.

2026-09-29 후처리 점검: P1 layout_observation과 페이지 processing_route를 내부 레이아웃·추출 경로로 전달한다. bbox_source·bbox_quality·coordinate_surface·render_engine·원본 줄의 개행/좌표 누락 개수는 parser_observations로 검색과 압축 모델 입력까지 보존한다. 문자 범위가 원문과 맞더라도 실제 렌더 줄과 서로 다른 유의사항 의미 경계가 검증됐다는 뜻은 아니며 physical_line_verification은 NOT_ATTESTED다. 긴 논리 본문은 원본 개행에서 검색용 청크를 나누되 물리 줄 ID나 세부 bbox를 새로 만들지 않는다. 표 원자 행과 개행 없는 문장은 보존한다. 줄 없는 선택 본문은 유효 영역 bbox가 있어야 한다.

이미지에서 OCR과 VLM을 사용하고 PDF는 디지털 텍스트층의 품질에 따라 OCR 보완을 사용한다. HWP는 구조·HTML과 렌더 PDF의 디지털 줄을 결합하며 필요 시 시각 보완을 사용한다. OCR/구조 추출을 배타적인 두 경로로 가정하지 않는다. 서로 다른 입력의 최종 P1/P3 외형은 같아도 추출 출처와 좌표 화면은 구별해 보존한다. HWP 재구성 화면의 줄 배치를 한컴 원본 조판과 같다고 주장하지 않는다.

P1은 원문 줄·좌표·판독 후보·경고·표 셀을 남기는 근거 원장이다. P3은 다음 영역 입력을 전달한다. 같은 `region_id`로 P1 상세 근거를 조회한다. P1/P3는 규칙·구조화 이후에도 유지한다.

| P3 영역 필드 | 의미 | 심의에서의 사용 |
| --- | --- | --- |
| region_id | 페이지별 `pN_rNNN` ID | 출처·영역 하이라이트 연결 |
| product_id | 영역의 상품 소유권 | 사용자 확정 상품 범위와 대조하는 파서 관찰 |
| bbox | 렌더 페이지 픽셀 `[x1,y1,x2,y2]` | 실제 사용한 화면에 표시; 의무 충족의 증거가 아님 |
| selected_text | 최종 선택 문구 | 원문과 정확한 대응이 없으면 영역 수준 근거 |
| labels | 복수 구분값 문자열 | 검색 힌트; 값의 존재·역할·적정성의 증명이 아님 |
| kind | text 또는 table | 표 단위 분할 보존; 셀·관계는 P1 근거 확인 |
| needs_review | 추출 품질 확인 필요 | 광고 위반 여부가 아니며 P1 review_reasons와 함께 보존 |
| text_source | hwp/digital/ocr/vlm | 원문 추출과 VLM 최종 선택 출처 구분 |

문서에는 doc_id·source_file·file_type·classification·template, 상품별 review_units, 페이지에는 page_no·canvas가 있다. P3에는 회사명·상품명 등의 확정 key/value나 각 값의 검증된 정확도 확률이 없다. labels는 영역 분류다. P1 줄 confidence와 VLM 확신도도 정확도 확률로 해석하지 않는다. 후속 review_result_contract는 요청된 심의 출력 모양이며 파서의 광고 판정 결과가 아니다.

## 이전 운영본과의 차이

기존402ab4b는 P1 v3/P3 v6였다. 최신 main에는 HWP 입력 렌더 브랜치가 병합돼 있다. `run.py`에서 구조 추출·HTML/Chromium 또는 LibreOffice 렌더·시각 좌표 정렬을 처리하며 옛 ingest.hwp·assets 경로는 제거됐다. VLM은 항상 실행하고 `--with-vlm`은 제거됐다. `--compact-output`은 최종 P1/P3·이미지·media-index와 보고서를 저장한다.

시각 표는 기존 bbox와 문구를 보존해 검증·병합하고 전체 영역 Judge의 최종 문장을 P3로 전달한다. 원본/HTML 셀은 P1에 보존한다. VLM으로 셀 격자·의미 관계·좌표를 만들지 않는다. 다상품 파일명으로 다른 상품의 세부유형이 주입되는 기존 문제는 아직 있어 같은 상품 범위 패치를 적용하고 최신103개 테스트를 통과했다.

## 실제 연결 수정

- 어댑터는 명시된 v3/v6와 v4/v9만 지원한다. 혼합·미지원 버전은 차단한다. v9의 문서·페이지 canvas·상품 소유권·region_id·bbox가 P1과 일치하는지 검사한다.
- 원본 JSON과 해시는 보존한다. 내부 P1 evidence-v6/P3 region-input-v1 계약으로 변환하는 것은 파서 다운그레이드가 아니다.
- labels는 parser_label_hints로 검색·모델 입력까지 보존하되 정확한 줄 라벨로 승격하지 않는다. kind·text_source·review_reasons와 P1 셀·미배정 줄·복구 후보를 보존한다.
- `parser_contract_profile=region-v9`, 40자리 `parser_revision`을 명시하고 최신 CLI로 실행한다. HWP는 최신 upstream run.py를 사용하며 옛 parse_hwp_native.py를 거치지 않는다.
- intake에 parser_revision을 포함해 업데이트 전 부모 산출물을 새 파서 결과로 재사용하지 않는다. 과거 결과 조회는 기존 계약 지원을 유지한다.
- compact-output의 실제 페이지 PNG를 해당 심의·원본 체크섬·P1/P3 해시·canvas에 연결한다. 인증된 `/operational/reviews/{review_id}/parser-page/{page_no}`로 제공하고 결과 화면은 이 페이지를 사용한다. 재구성된 HWP 화면과 옛 LibreOffice 미리보기를 혼합하지 않는다. 화면이 없거나 해시가 다르면 명시적으로 표시 실패 처리하며 유효한 심의 원문은 버리지 않는다.
- Chromium은 파서 HWP HTML 렌더에 필요한 로컬 의존성이다. 기존 사내 document-processor 소스와 Python3.13 격리는 유지한다. 한컴 원본 조판과 재구성된 검토 화면이 동일하다는 주장은 하지 않는다.

## 검증 경계

최종 재확인에서 main이9733d9f로 갱신됐다. fdfc09f와의 Git 차이는 README.md 하나이며 패치 적용 후69개 소스 파일의 해시로 코드 동일성도 확인했다. 실제 HWP와 파서103개 검사는 fdfc09f에서 수행했다. 최종 r11b는 검증된 r11 이미지 위에 최신 README·파서 소스 판본 기록만 추가하고 parser_revision을9733d9f로 맞췄다. 재파싱으로 같은 샘플 결과를 덮어쓰지 않았다.

최신 파서103개·RAG555개·운영 브리지47개·프론트113개·Linux 거버넌스82개가 통과했다. RAG 필수 CI478개와 함수 검사21개도 통과했으며 전체555개와 겹치는 검사다. 어댑터·HTTP 원문 화면·최신 CLI·파서 판본별 부모 재사용 회귀를 추가했다. 타입 검사는 통과했고 린트는 오류0·기존 훅 경고2개다. Linux 문서 일관성 검사와 문서 가드도 통과했다.

기존 승인 HWP 한 건을 운영 상태가 아닌 별도 공간에서 실행했다. 파싱82.172초, 1페이지·7영역·29줄·영역 bbox7/7, 줄 분할은 정확히 보존됐다. 추출 출처는 digital이며 렌더 엔진은 document_processor_html_chromium이다. 검색 coarse7개·fine18개, fine의 라벨 힌트16개가 생성됐다. 저장된 실제 PNG1개의 canvas·P1/P3·원본 체크섬 연결 및 검색→모델 요청의 힌트 보존을 확인했다. 추출·계약 연결 검사이며 금융 판정 정확도 검증은 아니다. 신규 모델 판정과 gold 읽기는 실행하지 않았다. 실제 PDF·이미지3상품군 완주는 이번 검증 범위에 포함하지 않는다.

운영 이미지는 `nh-operational:1118-parser-r11b`, SHA `bee0e96ede6d76296975c75c46633b587de150bd48102c19397a7dce96efb41a`로 healthy다. parser_contract_profile은 region-v9이며 parser_revision은 최신40자리 커밋이다. 배포 전 상태 백업 SHA는 `754fff2d7c15a10ec8d696a9123d451e648a64031f8c80dd6d13502e20ad9dde`다. 배포 전후 광고21·심의35·실행 중0·저장 결과22개 ID/해시가 같으며 기존 모델·ES 컨테이너는 변경하지 않았다. 파서 소스 tar SHA는 `3a18fac170fab4de1cafc51082cbad1d04a2afae93e3b93faa9dbd5c1f716fa0`다. 기존 상품 범위 패치 외에 upstream 코드를 새로 변형하지 않았다.

열람 화면은 저장소 상위 `deliverables/parser-schema-20260928/index.html`이다. 최신 export.py에서 생성한 합성 예시와 실제 HWP 실행 P1/P3를 선택 목록에서 구분한다. 같은 폴더의 verification.json·preview-verification.json·deployment.json·browser-verification.json에 검사 증거를 남긴다. 새 브라우저에서 실제 P3 8필드·필드 검색·사이트 자동 접속·추가34행 작업대장·기존 심의 원문 조회를 확인했다. 광고·심의 변경 요청0건·페이지 오류0이다. 원본 광고 문구·서버 계정·연결 설정은 Git 문서나 공개 예시에 복사하지 않는다.

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.4 | 2026-09-30 | `parser-pipeline/` subtree(15f730d→4968fa5) 편입, 단일 실행 프로필과 사용자 템플릿 `--template-id` 전달·검사 |
| v1.3 | 2026-09-30 | 최신3d3dacbf·P1 v5/P3 v10 연결, 디지털 교정 관찰·실제 파서 이미지와 기존 계약 보존 |
| v1.2 | 2026-09-29 | 최신 레이아웃·추출 경로·좌표 화면의 모델 입력 전달, 논리 본문 청킹과 물리 줄 검증 구별 |
| v1.1 | 2026-09-28 | README 전용9733d9f 갱신·코드 해시 동일성·r11b 최종 배포 |
| v1.0 | 2026-09-28 | 최초 fdfc09f 계약·변경점·운영 어댑터·좌표·파서 판본 연결 기록 |
