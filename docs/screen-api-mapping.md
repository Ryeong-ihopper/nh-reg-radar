# 화면-API 매핑표

## 금리 근거 분리와 기재 방식 집계 — 2026-09-30

기존 workspace 응답의 rows에 evidence_segments(line_ref, text, locations)와 group_members를 추가한다. 각 segment는 정확한 원문 줄에서만 좌표를 구하며 다른 인용의 영역 좌표를 섞지 않는다. group_members는 동결된 logical_group 메타데이터로만 구성한다. source_ads 및 저장 결과 원본은 유지한다. 새 API나 상태 변경 요청은 없다.

## 운영 결과 목록 필터와 위치 이동 — 2026-09-30

`GET /operational/reviews/{review_id}/workspace`의 저장 판정 행을 클라이언트에서 전체·적정·부적정·확인필요로 필터링한다. 행의 저장 사유를 카드에 요약하고 `evidence_locations` 또는 판단불가의 `review_locations`를 원문 이미지 bbox 이동에 사용한다. 저장 좌표가 빈 행은 임의 위치로 연결하지 않는다. 결과 화면의 내보내기 버튼은 표시하지 않지만 기존 JSON 응답과 저장 결과는 유지한다. 새 API 호출이나 데이터 변경 요청은 없다.

## 광고 등록 안내 블록 제거 — 2026-09-30

등록 화면의 심의 흐름 안내는 표시 전용으로 API 입력값이 아니다. 해당 블록을 제거해도 capabilities 조회, 상품·매체 선택, 광고 등록과 운영 intake 요청은 그대로 유지한다. 구조화 작업대장 경로 `/review-criteria`는 별도 화면에서 유지한다.

## 광고 매체 대표 선택지와 전송 코드 — 2026-09-30

운영 등록은 API의 활성 코드 중 `SMS`, `LMS`, `MMS`, `PUSH`, `EMAIL`, `ALIMTALK`, `WEB_BANNER`, `WEB_PRODUCT_PAGE`, `SOCIAL_MEDIA`, `NOTICE`, `VIDEO`만 표시한다. 배너·팝업은 `WEB_BANNER`, 웹·앱 상세·이벤트는 `WEB_PRODUCT_PAGE`, SNS·검색은 `SOCIAL_MEDIA`, 문서·인쇄·현장·옥외는 `NOTICE`를 대표 코드로 사용한다. `OTHER`는 등록 화면에서 제외한다. 선택된 코드를 `POST /advertisements`와 운영 intake의 `media_codes[]`에 동일하게 전달한다. 과거 광고의 상세 코드는 읽기·표시·재현할 수 있도록 API와 저장소에 유지한다.

## IRP 펀드 노출 복수 운용상품 입력 — 2026-09-30

IRP 펀드상품 노출을 고르면 기존 분류 코드를 routing과 intake의 `product_classification_code`에 유지하고, 추가로 고른 ETF·ELB만 `underlying_products[]`에 보낸다. 펀드는 분류에 이미 포함돼 `FUND` 코드를 중복 전송하지 않는다. 추가 상품이 없다고 확정하면 빈 배열과 `CONFIRMED`, 기타 운용상품이 불명확하면 빈 배열과 `UNCONFIRMED`를 보낸다. 미노출 IRP의 상품 배열은 비운다. 기존 API 필드와 DB 구조를 사용한다.

## IRP 전용 분류의 화면 연결 — 2026-09-30

`GET /operational/capabilities`에서 받은 IRP 미노출·펀드 노출 분류는 일반 심의방법과 다른 화면 묶음에 표시한다. 선택하면 기존과 같이 해당 IRP 분류 코드를 `PUT routing`과 `PUT intake.products[].product_classification_code`에 그대로 보낸다. 일반 퇴직연금 공통 분류의 `underlying_products[]` 복수 체크로 자동 치환하지 않는다. 선택지 아래 설명 문구는 API 입력값이 아니다.

## 광고 매체·운용상품 선택 연결 — 2026-09-30

등록 화면의 매체 선택은 `GET /codes/advertisement-types`의 활성 코드에서 가져온다. 기존 코드와 신규 `LMS`·`MMS`·`SEARCH_AD`·`POPUP`을 묶어 표시하되 등록 `POST /advertisements`의 `advertisementType`과 운영 `PUT /operational/advertisements/{id}/intake`의 `media_codes[]`에 동일한 코드를 전달한다. 퇴직연금 상세 상품군은 일반 공통 분류만 고르고 `GET /operational/capabilities`의 연결된 펀드·ETF·ELB를 체크한다. 기존 routing에는 공통 분류, intake에는 `FUND`·`ETF`·`ELB` 복수 배열과 확정 상태를 전송한다. 정기예금 등 기타는 빈 배열과 `UNCONFIRMED`로 남겨 사람 확인 대상에 둔다.

## 운용상품 선택 표시 정리 — 2026-09-29

등록 화면의 이전 상세 상품군 직접 선택과 아래 복수 체크는 같은 운용상품 상태를 표시했다. 현재는 상세 상품군에서 퇴직연금 일반만 선택하고 아래 체크로 복수 운용상품을 구성한다. CSS 선택칸 표시와 기존 capabilities·routing·intake 연결을 사용한다. 비보호 안내문구/로고 판단은 등록 안내문에서 새로 결정하지 않는다.

## 추출 상태의 진행·결과 연결 — 2026-09-29

저장된 파서 관찰에서 파일·페이지별 추출 상태를 읽기 전용으로 표시한다. 처리 완료와 추출 정확성을 구별하며 confidence를 신뢰도 백분율로 변환하지 않는다. 완전 실패/파일 실패, 부분 판독·빈 영역, 불확실 판독, 좌표 없음, 미검증 복구 후보, 기록 없음과 모델 출력 실패를 구분한다. 좌표 없는 판독 확인 대상도 숨기지 않고 파일·페이지의 원본 대조 대상으로 남긴다. 원본 P1/P3·저장 예측·법령 판본·상태는 변경하지 않는다.

진행 화면의 종료 상태와 결과 화면은 동일한 인증 workspace의 extraction_status를 사용한다. 출력 계약 실패 건수는 별도 기존 경고로 유지한다. JSON 다운로드는 같은 projection을 포함하고 별도 파싱/모델 호출을 하지 않는다.


## Showcase 화면의 운영 API 연결 — 2026-09-29

`/review-results`·`/recommendations`는 기존 광고 목록과 광고별 심의 이력 조회로 실제 회차를 선택한다. 완료 회차는 결과 또는 수정 초안으로, 진행/실패 회차는 진행 기록으로 이동한다. `/reviews/:reviewId/suggestions`는 다른 검토 화면과 같은 ReviewScopedBoundary 아래에 둔다.

결과 표와 상세·초안은 인증된 workspace GET을 공유한다. 판정 저장값·집계·인용 계약은 유지하며 표시용 item_title/source_product/template_guidance/display_checks/template_violation_guidance/template_review_guidance를 동결 요청에서 제공한다. 원문 보기만 기존 parser-layout/preview/hwp-html GET을 추가 호출한다. 초안 편집·예시 가져오기·복사는 클라이언트 상태이며 추천 생성/채택 API를 호출하지 않는다.

`/legal-references`는 기존 review-worklist GET의 TEMPLATE 행에서 source.legal_basis.statute/association을 투영한다. 현재 매핑 자료 내 검색·템플릿 필터는 클라이언트에서 처리한다. 선택 근거의 항목은 `/review-criteria?item=...`으로 이동한다. 외부 공식 법령명 검색 URL은 화면 링크이며 신규 법령 검색 서버 API나 판단 경로가 아니다. 결과 법령 링크는 각 저장 row.rule_basis.legal_basis_refs에서만 만든다.

## HWP HTML 원문 보기 — 2026-09-28

[ADR-0088](adr/ADR-0088-hwp-html-review-display.md)에 따라 HWP/HWPX 결과의 기본 원문 보기는 심의에 사용한 파서 이미지이며 정적 HTML 본문 읽기를 함께 제공한다. 사용자에게는 “심의 화면 · 근거 위치”와 “본문 읽기 · HTML”로 안내한다. 2026-09-28 사용자가 표시 방식 결정을 위임했고, 심의와 근거 좌표의 일치를 우선했다. 인증된 GET `/operational/reviews/{review_id}/hwp-html/{asset_id}`는 해당 심의·광고 파일 소유권과 원본 체크섬·HTML 해시를 확인한다. 저장된 파서 HTML을 우선 사용하고 과거 결과에 없으면 동일 원본에서 HTML만 생성·보관한다. 이 조회는 파싱·검색·판정을 재실행하지 않는다. HTML은 스크립트·외부 요청을 차단한 격리 iframe으로 표시하며 실제 원문에 유일하게 대응하는 인용만 문구 강조한다. 반복 문구·위치 불명은 임의로 강조하지 않는다. HTML 위에 P1 bbox를 그리지 않고 별도 파서 이미지 보기에서 기존 좌표를 확인한다. 이미지·이미지 PDF 경로와 기존 저장 판단은 유지한다.

## 최신 파서 계약 연결 — 2026-09-28

[최신 파서 계약](parser-schema-current-2026-09-28.md)에 따라 nh-parser-fin main 9733d9f의 P1 v4/P3 v9를 명시적으로 지원한다. 영역 라벨은 parser_label_hints로 검색·모델 입력에 전달하며 줄 증거로 승격하지 않는다. kind·text_source·품질 경고·표 셀과 미배정 줄을 보존한다. 최신 CLI는 --compact-output이며 HWP는 upstream run.py를 사용한다. parser_revision을 intake에 포함해 이전 파서의 부모 캐시를 재사용하지 않는다.

결과 화면의 preview_path는 인증된 GET `/operational/reviews/{review_id}/parser-page/{page_no}`다. 해당 심의·파일 소유권·원본 체크섬·P1/P3 해시·canvas와 페이지 이미지 해시를 검사하며 실패 시 독립 변환 화면으로 대체하지 않는다. 새 HWP 화면은 실제 파서 렌더 좌표계이며 한컴 원본 조판과 같다는 주장을 하지 않는다. 제품 PostgreSQL·NormalizedDocument 계약은 변경하지 않는 loopback 운영 경계다.

## 심의 흐름·상품 관계·근거 정책 — 2026-09-28

[흐름과 구조화 기준](review-flow-and-structuring-2026-09-28.md), [ADR-0087](adr/ADR-0087-product-composition-and-evidence-policy.md)에 따라 퇴직연금 공통 + 복수 운용상품 선택을 입력부터 정본 전개·확정 사실·coverage까지 연결한다. ETF·ELB 비보호2항목의 본문/로고 예외와 줄 배치33항목을 분리한다. 239개 프로그램에 검사별 라벨/어휘 또는 어휘 근거 정책을 연결하고 정책 해시도 검증한다.

사이트 `/review-criteria`에239+32+34 작업대장을 연결했다. 보완32·추가34는 의미·범위·판본·예외·입력 확인이 필요한 구조화 작업 대상이며 자동 판정에 일괄 활성화하지 않는다. 추가34는 잔여19·공유3·시각7·정책1·범위 보류2·판본 보류2다. 기존 상태·결과와 P1/P3·정답 격리를 유지한다.

등록 화면 → PUT routing → PUT intake(운용상품 선택 포함) → POST review 순서를 유지한다. `product_classification_code`는 퇴직연금 일반, `underlying_products`는 체크한 운용상품 코드로 전달한다. 다른 상세 상품군으로 변경하면 운용상품 선택을 비운다. 구조화 작업대장 `/review-criteria` → GET `/operational/review-worklist`, 등록 선택지 → GET `/operational/capabilities`다. 작업대장은 판정 요청에 전송하지 않는다.

## 광고 단위 삭제 연결 — 2026-09-23

S-002 광고물 목록의 종료 상태 행에서 `심의 결과 삭제`는 사용자 확인 후 `DELETE /api/v1/operational/advertisements/{advertisementId}`를 호출한다. 이 요청은 해당 광고와 모든 심의 회차·결과·원본·처리 데이터의 삭제 요청이다. 취소 시 호출하지 않으며,204 성공 시 목록을 다시 조회해 행을 제거한다. 진행 중 심의의409와 권한·대상·서버 오류는 목록에 표시한다. 결과 화면에는 이 action을 연결하지 않는다.

## 결과 필터와 적용 제외 데이터 — 2026-09-22

S-006은 기존 workspace `rows`의 전체 판정을 기본 표시하고 `전체·위반·판단불가·충족` 네 필터로 같은 응답을 다시 요청하지 않고 전환한다. 우선 검토·규제목록 확인 버튼과 출처별 필터는 제거한다. `excluded_rows`는 응답과 JSON 내보내기에 보존하지만 화면에서는 렌더링하지 않는다. 헤더 로고는 번들 정적 자산이다. API 경로·응답 스키마·저장 결과는 변경하지 않는다.

## 광고물 상세·검토 이력 병렬 조회 — 2026-09-18

광고물 상세 진입 시 `GET /advertisements/{advertisementId}`와 `GET /advertisements/{advertisementId}/reviews`를 동시에 호출한다. 이력 요청은 상세 응답 완료를 기다리지 않으며, 성공 응답은 동일 광고 query key에서 30초 동안 fresh 상태로 재사용한다. 두 API의 인증·부서 접근 검사는 각각 유지한다.

## 투자성 상품군 연결 — 2026-09-17

S-003의 투자성 선택은 제품 API `productGroup=INVESTMENT`, intake `product_group=투자성`, 사용자 선택 `product_classification_code`로 전달한다. `/operational/capabilities`는 `투자성상품-`으로 시작하는 템플릿을 `productGroup=INVESTMENT`로 반환한다. 서버는 상위 상품군과 상세 템플릿 접두어가 다르면422로 거부한다.

## 원문 줄 구조 판정 연결 — 2026-09-17

S-006은 workspace 행의 `line_structure_assessment`가 있으면 정확 렌더링 줄로 확인한 결과 사유를 표시한다. 동일 줄 복수 문구 규칙은 `evidence_line_refs`와 완전일치 렌더링 좌표를 사용하며, 서로 다른 줄이나 한 문장을 위반 근거로 합치지 않는다. 저장 모델 응답과 원본 좌표는 변경하지 않는다.

## 이전 최신 심의 단건 삭제 연결 — 2026-09-17

당시 S-002 광고물 목록의 `심의 결과 삭제`는 `DELETE /api/v1/operational/advertisements/{advertisementId}/latest-review`를 호출했다. 2026-09-23부터 목록 버튼은 상단의 광고 단위 삭제 경로를 사용한다. 최신 심의 단건 경로는 내부 호환용으로만 유지한다.

S-003 운영 등록에서 `광고 형식·매체`로 표시하는 기존 `advertisementType`은 intake `media_codes[]`로 전달되고 통합 판정 문서의 `routing_metadata.media_type`으로 주입된다. 상세 상품군의 템플릿 선택과 별개이며, 둘 중 하나로 다른 값을 추정하거나 덮어쓰지 않는다.

## 현행 결정 — 2026-09-17 템플릿 우선·규제목록 v2 보완 심의

단일 HWP의 workspace/export는 저장된 integrated 원문과 parser-layout의 유일한 완전일치(공백·줄바꿈 제외)를 표시 전용으로 연결한다. evidence_locations에 원문 line_ref 기반 key, 실제 pageNo/source_page_no, asset_id, 줄 bbox와 canvas 크기를 반환한다. 선택된 근거 줄에만 연결하며 검색·모델 호출이나 저장 판정 변경은 없다. 기존 직접 좌표가 우선이고 다른 파일·중복 문구로 연결하지 않는다.

새 심의 `/operational/capabilities`는 `sourcePolicy=template-plus-v2`와 `내부 심의 템플릿 + 규제목록 v2`를 반환한다. workspace의 `source_policy`는 결과 audit.rule_sources.policy를 사용한다. 과거 raw 결과·카드·법령 근거를 재작성하지 않는다. 원본 확인 S-004는 현재 심의 상태에 따라 진행 화면 또는 결과 화면을 가리키는 버튼형 다음 단계 링크를 표시한다.

템플릿 `legal_basis_refs`는 실제 원문에 제공된 참조만 화면의 근거 법령·규정 접기/펼치기에 연결한다. 미제공이면 해당 블록을 표시하지 않는다. 좌표 API 값은 유지하고 테두리만1px로 변경한다. 템플릿 coverage는 상단 대신 판정 목록의 처리 내역에서 확인한다. 실패/누락 경고, export 판정 내용, 광고물 목록 및 진행 기록 접근은 유지한다.

## 판독 가드 이후 활성 근거 — 2026-09-16

판독 가드가 철회한 판단의 인용은 활성 근거의 텍스트·ID·줄·bbox에서 함께 제외한다. 적용성 게이트 보류는 해당 결론의 인용을 제거하고, 일부 요건 보류는 나머지 독립 관찰 근거를 유지한다. 가드 없는 판단불가의 인용을 일괄 숨기거나 검색 후보로 대체하지 않는다. 기존 저장 판정·원응답·가드 이전 결과는 그대로 보존하고 조회 시 비변경 투영을 적용한다.

화면은 workspace의 활성 근거와 `reading_quality_review`를 사용한다. export 표시 행은 workspace와 동일하고 `source_results`는 감사용이다. 원래 인용을 다른 bbox로 치환하지 않는다.


## 명시 표제와 단순 언급의 구분 — 2026-09-16

항목명으로 시작한다는 이유만으로 일반 문장·메뉴를 명시 표제로 확정하거나 모델의 다른 라벨을 삭제하지 않는다. 선택 템플릿의 항목명/기존 별칭과 정확히 대응하는 표제, 단위가 붙은 표제, 명시 구분자 뒤 값이 이어지는 필드만 기존 표제 우선 경로에 들어간다. 심의번호는 기존 표식 바로 뒤 식별 숫자가 이어지는 형식을 보존하며 번호의 유효성이나 심의 적합성을 확정하는 규칙으로 사용하지 않는다. 단순 언급은 의미 모델에 맡기며 이 수정이 모델 의미 정확도를 보증하지 않는다.

이는 기존 사용자 템플릿·원문 접지 계약을 잘못 실행한 일반 구현 오류 수정이다. 특정 광고의 이름·숫자·정답을 추가하지 않는다. P1/P3의 원문·줄·좌표와 사람 검토 경계를 유지한다. 양성 표제/단위/번호와 음성 일반 문장/메뉴, 모델의 다른 유효 라벨 보존을 합성 검사한다. 현행 재사용 정책은 `user-template-labeling-v5`이며 v4 이하 부모 P1/P3는 재사용하지 않는다. 독립 평가는 미관찰 광고와 사람 확정 정답을 확보한 뒤 수행한다.


## 복수 표제의 하위 라벨 보존 — 2026-09-16

복수 명시 표제 후처리 수정과 함께 parser-intake 재사용 정책을 `user-template-labeling-v4`로 올린다. 기존 v3 이하 산출물은 부모 재사용 조건을 만족하지 못하며 과거 결과는 보존한다. 공개 API·화면·DB 필드를 변경하지 않는다. 한 줄에 근거가 있는 여러 라벨은 같은 원문 좌표를 사용할 수 있다.

## 라벨 의미·원문 품질 보완 — 2026-09-16

하위 라벨 모델에 줄별 OCR source/confidence와 기존 저신뢰 판독 기준의 사람 확인 표시를 전달한다. 명확한 디코딩 손상 또는 기존 설정 기준 미만 OCR 줄에는 모델 신뢰도가 높거나 명시 표제가 있어도 라벨을 확정하지 않는다. 원문과 독립적으로 읽을 수 있는 다른 줄의 라벨은 보존한다. 템플릿 기재요령의 240자/2항목 절단을 제거하고 모든 기재요령을 전달한다. P3가 실제 선택한 VLM 판독문은 줄 번호 없는 문맥 보조로 구분하며 P1에 없는 정보를 P1 라벨 근거로 승격하지 않는다. 회사/상품 고유 이름과 메뉴·절차 문단, 실제 조건과 계산기 입력 예시를 구별하도록 공통 안내를 보완한다. 특정 광고 이름·수치·답지 조건을 추가하지 않는다. 저신뢰 기준은 기존 OCR 재판독 설정을 사용하며 높은 OCR 신뢰도가 정확도를 보증하지는 않는다. 당시 재사용 정책은 `user-template-labeling-v3`였으며 현행 정책은 상단을 따른다. 최종 스키마 수령과 별도 광고의 사람 확정 정답에 기반한 독립 평가를 완료한 것으로 취급하지 않는다.


# 화면-API 매핑표

2026-09-30: 운영 workspace·parser-layout·parser-page API 경로는 유지한다. P1 v5/P3 v10도 같은 원문 이미지·출처 해시 연결을 사용한다. 판정 필터의 색상/정렬과 위치 없음 사유 구분은 표시 변경이며 저장된 판정과 좌표를 바꾸지 않는다.


전체 실행의 파일별/병합 입력 비교에서 표 라벨 경계의 자산 접두어 연결 오류를 발견했다. 병합 시 라벨과 원문 참조 모두에 접두어를 붙이지만 청킹은 원문 참조에서만 접두어를 떼어 라벨 경계를 놓쳤다. 전체 참조를 우선하고 접두어 없는 구형 라벨만 현재 영역의 유일한 줄로 연결하도록 수정했다. 다른 자산의 동일 접미사와 모호한 구형 참조는 연결하지 않는다. 기존 통합 입력을 고정한 오프라인 검사에서 coarse31 유지, fine49→56으로 파일별 청킹 합계와 일치했다. RAG279+21 통과. 광고 문구나 정답별 예외는 없다. 이미 진행 중이던49청크 판정은 원래 입력으로 보존하고, 완료 후 검증된 새 P1/P3를 재사용해 수정 청킹의 검색·판정부터 별도 재실행한다. 이는 OCR 재실행이나 판정 응답의 성공할 때까지 재호출이 아니라 일반 연결 결함 수정에 따른 새 입력 검증이다.

## 상세 상품군의 파서 전달

등록자가 선택한 상세 상품군으로 서버가 연결한 `internal_template_id`는 파싱 전부터 적용한다. 파서는 사용자에게 템플릿 재선택을 요구하거나 자동 재분류하지 않고, 그 안의 하위 항목을 원문 줄에 라벨링한다. 기존 등록/결과 API 필드와 시인성 사람 검토 화면을 사용한다. 라벨/선택 문장의 원문 대응이 불명확하면 기존 사람 확인 표시를 보존한다.

2026-09-16 후속: 라벨의 잘못된 원문 참조는 검색 입력에서 제외하고 기존 `needs_review` 표시로 연결한다. 화면/API/DB 필드는 추가하지 않는다. 파서 재사용 정책은 `user-template-labeling-v2`로 갱신해 이전 라벨링 정책의 부모 산출물을 새 심의에서 재사용하지 않는다. 과거 결과와 원문 파일은 보존한다.

## AI 활용 금융상품 광고심의 적정성 검토 에이전트

## 문서 현행 정보

| 항목 | 내용 |
| --- | --- |
| 현행 버전 | v1.100 |
| 기준일 | 2026-09-30 |

## 현행 시인성·판독 불확실성 처리 범위

기존 operational workspace/execution 응답의 deferred_rules.reason과 review_candidate_rows를 사람 검토 표시로 사용한다. API 경로·DB 스키마·출력 enum 변경 없음. 원문 bbox 조회와 페이지/파일 이동은 유지하며 시인성 검토 사유를 일반 입력요건으로 덮어 표시하지 않는다.


원본 확대와 독립 스크롤은 클라이언트 동작이다. 페이지 변경은 기존 파일 preview API를 자산 ID와 로컬 페이지로 호출한다.
운영 workspace/export의 `template_example`을 참고 문구로 표시하고 `requirement_checks`로 미기재 주장과 원문 연결 실패 안내를 구분한다. 새 모델 호출은 없다.

operational workspace 결과 행은 활성 판정 근거를 `evidence_locations`, 판단불가의 사람 확인 대상을 `review_locations`로 분리한다. 판정에 귀속되지 않은 지역 문제는 `LOCAL_READING_REVIEW` 내부 행 하나에 `review_locations`를 모으고 화면 제목은 `원문 판독 확인`으로 표시한다. 클라이언트는 판단불가이면서 활성 근거가 없을 때만 `review_locations`를 강조한다. 명시적 줄 참조가 없는 여러 줄 청크는 좌표로 확장하지 않으며, 단일 좌표 annotation API는 정확 `LINE` 좌표 중 가장 작은 하나를 대표로 반환한다.

## 변경 이력

| 버전 | 기준일 | 변경 내용 |
| --- | --- | --- |
| v1.100 | 2026-09-30 | 금리별 원문 근거 분리와 공통 전제·논리 그룹 중복 종합 교정 |
| v1.99 | 2026-09-30 | 운영 광고 매체 11개 대표 코드와 등록·입력 매핑 |
| v1.98 | 2026-09-30 | IRP 펀드 기본 분류에 ETF·ELB 추가 코드만 전송 |
| v1.97 | 2026-09-30 | IRP 전용 화면 묶음과 기존 라우팅·입력 코드 보존 |
| v1.96 | 2026-09-30 | 매체 공통코드·등록·운영 입력 연결과 퇴직연금 공통/복수 체크 계약 정리 |
| v1.95 | 2026-09-29 | 운용상품 선택 표시 정리 |
| v1.94 | 2026-09-29 | 추출 상태의 진행·결과 연결 |
| v1.93 | 2026-09-29 | 운영 사이드바·결과 표/선택 상세·추천 초안·TEMPLATE 근거 검색의 기존 읽기 API 연결 |
| v1.92 | 2026-09-28 | 퇴직연금 펀드·ETF·ELB 직접 선택지와 기존 입력 계약·초기화 회귀 반영 |
| v1.91 | 2026-09-28 | HWP 심의 이미지 기본 보기·HTML 본문 읽기 선택 보기 |
| v1.90 | 2026-09-28 | HWP HTML 원문 표시·동일 원본 캐시·격리·인용 강조 계약 |
| v1.89 | 2026-09-28 | 최신 파서 v4/v9·판본 재사용·영역 힌트·실제 렌더 좌표 연결 |
| v1.88 | 2026-09-28 | 심의 흐름·복수 운용상품·근거 정책·구조화 작업대장 연결 |
| v1.87 | 2026-09-23 | 목록의 심의 결과 삭제를 광고 전체 삭제 API와 연결 |
| v1.86 | 2026-09-22 | 결과 전체 기본·판정별 네 필터와 정적 로고 연결 |
| v1.85 | 2026-09-18 | workspace 행 출처로 우선 검토와 규제목록 판단불가 필터를 클라이언트에서 분리 |
| v1.84 | 2026-09-18 | workspace 결과의 확인 필요 기본 필터와 excluded_rows 화면 비노출 연결 |
| v1.83 | 2026-09-18 | 광고물 상세와 기존 검토 이력 API의 병렬 호출 및 30초 캐시 연결을 반영 |
| v1.82 | 2026-09-17 | S-003 투자성 상품군·상세 템플릿·확정 RAG 라우팅 연결 |
| v1.81 | 2026-09-17 | S-006의 유의사항 동일 줄 구조 판정과 정확 렌더링 줄 감사 연결 |
| v1.80 | 2026-09-17 | capabilities의 template-plus-v2 복원과 원본 확인의 버튼형 다음 단계 연결 |
| v1.79 | 2026-09-17 | S-002 상세 보기 옆 최신 심의 삭제 연결과 광고 형식·매체의 media_type 전달 명시 |
| v1.78 | 2026-09-17 | S-006의 확인 후 로컬 종료 심의 단건 삭제 연결 |
| v1.77 | 2026-09-17 | workspace/export의 HWP 정확 문구 대응 좌표 연결 공유 |
| v1.76 | 2026-09-17 | 템플릿 단독 심의와 원문 중심 결과 화면 적용 |
| v1.75 | 2026-09-17 | 지역 판독 불확실성의 확인 위치 분리·다중 줄 bbox 확장 및 합집합 제거 |
| v1.74 | 2026-09-17 | 저장 판정의 불완전 판독 누락 확정을 비파괴적으로 보류하는 공통 화면·내보내기 projection |
| v1.73 | 2026-09-17 | 결과 제목의 내부 규칙 ID 비노출, API 및 근거 연결 계약 유지 |
| v1.72 | 2026-09-16 | 사람 확인의 판단불가 통합·미해당 별도 내역·발견 후보 실행 제한 제거 |
| v1.71 | 2026-09-16 | 연구원 피드백: 출처 ID 숨김·조문 출처별 줄바꿈·동일 표기 중복 제거 |
| v1.70 | 2026-09-16 | 등록일 심의 기준·원문 직접 인용 연결 계약 |
| v1.69 | 2026-09-16 | 운영 결과의 커버리지와 판정 출처 표시 연결 |
| v1.68 | 2026-09-16 | 판독 가드 철회 인용의 활성 근거·좌표 제외와 감사 보존 |
| v1.67 | 2026-09-16 | 단순 항목명 언급의 명시 표제 오분류 방지 |
| v1.66 | 2026-09-16 | 복수 명시 표제 라벨 보존 버전의 재사용 경계 |
| v1.65 | 2026-09-16 | 라벨 입력의 원문 품질·전체 기재요령·P3 보조 문맥 전달과 실제 전체 심의 검증 |
| v1.64 | 2026-09-16 | 하위 라벨 참조 검증의 사람 확인 연결과 파서 재사용 정책 v2 반영 |
| v1.63 | 2026-09-15 | 사용자 상세 상품군을 파싱 전부터 적용하는 내부 연결 명시 |
| v1.62 | 2026-09-15 | 시인성 좌표 전용·사람 검토 범위와 현행 스키마 수용 경계 반영 |
| v1.61 | 2026-09-15 | 원본 독립 탐색과 preview API, 템플릿 예시·요소 검사 표시 연결 |
| v1.60 | 2026-09-11 | 복수 광고 자산의 파일별 독립 파싱을 서버 전체 2개 슬롯으로 제한하는 실행 경계 추가 |
| v1.59 | 2026-09-11 | 동일 광고 복수 파일의 부분 파서 실패 시 실패 자산만 재시도하고 작업 로그를 보존하는 실행 경계 추가 |
| v1.58 | 2026-09-11 | 초안/최종 접수값을 제거하고 사람 최종 결정 보조 API를 기본 화면 비노출 옵션으로 전환 |
| v1.57 | 2026-09-11 | 접수 검토 단계와 결과 규칙 근거를 전달하고 사람 최종 승인·반려를 별도 불변 보조 API로 연결 |
| v1.56 | 2026-09-11 | 광고별 카드 일괄 등록을 기존 단건 광고·routing·intake·review API의 독립 병렬 호출로 연결하고 부분 실패 재요청 경계를 명시 |
| v1.55 | 2026-09-07 | 로컬 결과 화면은 workspace 또는 reference의 실제 표시 행에서 집계하고 parser-layout과 원본 preview를 함께 사용. items/annotations 경로는 요약 화면으로 이동 |
| v1.54 | 2026-09-07 | 로컬 자동심의 시연 모드에서 실행기에 연결된 입력과 핵심 결과 화면만 노출하도록 화면/API 사용 경계를 축소 |
| v1.53 | 2026-09-07 | 로컬 자동심의 S-007에 파서 영역·줄 좌표 조회와 HWP 200-DPI 미리보기 연결을 추가 |
| v1.52 | 2026-09-06 | 로컬 자동심의 어댑터의 템플릿 확인·실제 실행·진행·결과 API 연결을 추가 |
| v1.51 | 2026-07-28 | 검토 전환 시 이전 검토의 조회 조건(선택 항목, 검색·페이지 조건)과 세션을 요청에 사용하지 않는 기준을 검토 화면 전체로 확대 (API 계약 변경 없음) |
| v1.50 | 2026-07-28 | S-010에서 검토 식별자가 바뀌면 이전 검토의 Q&A 세션을 요청에 사용하지 않는 기준을 반영 (API 계약 변경 없음) |
| v1.49 | 2026-07-28 | S-010 질문 전송 시 진행 중인 이력 조회를 먼저 취소하고, 성공 시 즉시 재조회 없이 응답 메시지를 추가하는 기준을 반영. 이전 질의응답 조회가 끝나기 전에는 전송하지 않으며, 실패한 질문은 같은 질문 내용으로 현재 검토 세션에 개별 재호출한다 (API 계약 변경 없음) |
| v1.48 | 2026-07-28 | S-010 Q&A 탭의 공통 탭 바 배치와 대화 목록 내부 스크롤 기준을 화면설계서와 정합하도록 반영 (API 계약 변경 없음) |
| v1.47 | 2026-07-23 | S-007 원본 미리보기 폭맞춤·위치 확인 필요 하단 배치와 S-010 검토별 Q&A 이력 조회/세션 재개 계약을 추가 |
| v1.46 | 2026-07-22 | S-007 PDF 원본은 descriptor의 경량 페이지 수 조회 후 content 한 페이지를 조회하며, 동일 파일·페이지 재표시는 서버 cache를 사용하고 OpenDataLoader PDF 좌표는 실제 페이지 좌상단 정규화 값으로 표시하도록 정정 |
| v1.45 | 2026-07-22 | 개발 VM Vite 서버가 `nh-compliance.ihopper.co.kr` Host 요청을 명시 허용하도록 추가 |
| v1.44 | 2026-07-22 | S-005 SSE 진행 상태 stream과 S-008 `includeAppropriate` 기본 비포함·사용자 전체 보기 전환을 매핑 |
| v1.43 | 2026-07-22 | S-002 시스템 관리자 목록에서 현재 페이지 개별·전체 선택 삭제가 기존 DELETE 계약을 항목별로 호출하도록 추가 |
| v1.42 | 2026-07-22 | 시스템 관리자 전용 광고물 삭제 API와 삭제 후 목록 복귀·원본/연결 검토 결과 비노출 화면 흐름을 추가 |
| v1.41 | 2026-07-21 | S-007 HWP/HWPX는 private SVG의 실제 글자 좌표와 `matchedText`의 정확 일치 시 원본 하이라이트를 허용하고, S-009는 원문·권고 문구 비교 필드를 표시하도록 정정 (API 계약 변경 없음) |
| v1.40 | 2026-07-21 | S-007 HWP/HWPX는 document-processor text/layout 좌표가 결합된 Annotation만 private SVG 원본 위 BOX로 표시하고, offset만 있는 항목은 원본 위치 미확정으로 처리하도록 정정 (API 계약 변경 없음) |
| v1.39 | 2026-07-21 | 4단계 `/reviews/{reviewId}/support` 탭의 사용자 노출 명칭을 `검토 및 리포트`로 통일 (API 계약 변경 없음) |
| v1.38 | 2026-07-21 | S-010을 4단계 결과 확인의 `/reviews/{reviewId}/results/qa` 탭으로 분리하고, 기존 요약·광고물 조회값을 Q&A 요청 범위에 자동 적용하도록 화면 매핑을 정정 (API 계약 변경 없음) |
| v1.37 | 2026-07-21 | S-006/S-008을 원본 좌측·검토 정보 우측의 넓은 작업공간으로 재배치하고 좌측 탐색 접기·반복 안내 제거를 반영 (API 계약 변경 없음) |
| v1.36 | 2026-07-20 | S-005 상태 조회의 `jobStatus`·`failedReasonCode`·`reviewStatus`로 기술 일시 오류 재시도와 OCR 판독 불가·일반 확인 필요 안내를 구분하도록 반영 (API 계약 변경 없음) |
| v1.35 | 2026-07-20 | S-003·S-014·검증 화면의 상품군 공통 코드에 대출을 추가하고, API enum과 화면 선택값을 동기화 |
| v1.34 | 2026-07-20 | 로그인 공개 화면은 API 계약 변경 없이 헤더 제외 뷰포트에 맞춘 중앙 레이아웃으로 불필요한 세로 스크롤을 제거하도록 정정 |
| v1.33 | 2026-07-20 | S-003의 취소·광고물 등록 액션을 별도 sticky 컨테이너 없이 폼 최하단의 일반 액션 행으로 배치하도록 화면 반영을 정정 (API 계약 변경 없음) |
| v1.32 | 2026-07-20 | S-009는 `includeSuggestion=true` 검토 완료 시 위험 Rule 결과·연결 근거에서 생성된 추천을 표시하고, LLM 문장 보강 실패 시에도 기본 추천을 유지하도록 worker 생성 경계를 반영 |
| v1.31 | 2026-07-20 | S-009 추천 문구 목록이 비어 있을 때 항목별 검토 결과의 수정 권고로 이어지는 빈 상태를 추가 (API 계약 변경 없음) |
| v1.30 | 2026-07-20 | S-007 BOX의 normalized coordinate를 스크롤 뷰포트가 아닌 실제 원본 미디어 기준으로 변환하고, hover·선택 표현이 원문을 가리지 않도록 정정 (API 계약 변경 없음) |
| v1.29 | 2026-07-20 | HWP/HWPX 변환 SVG도 Blob 이미지로 가로폭에 맞춰 렌더링하고, 미리보기 영역의 가로 스크롤을 차단해 세로 스크롤로 원본을 확인하도록 정정 (API 계약 변경 없음) |
| v1.28 | 2026-07-20 | S-005가 GET 검토 상태의 완료 응답을 확인한 뒤 지연된 비완료 응답으로 완료 UI를 되돌리지 않도록 화면 상태 안정화 경계를 반영 (API 계약 변경 없음) |
| v1.27 | 2026-07-20 | S-007이 Annotation의 업무 파일 분류가 아닌 preview 콘텐츠 MIME 타입으로 렌더링 형식을 결정하도록 정정 (API 계약 변경 없음) |
| v1.26 | 2026-07-20 | S-005 중립 단계 카드, 원본 내부 스크롤, S-008 문구 우선 칩·표 상세 및 Annotation 좌표 기반 원본 위치 이동을 반영 (API 계약 변경 없음) |
| v1.25 | 2026-07-20 | S-006 기본정보 표·간결한 원본 병행 패널·중립 최종 판단 안내 표시를 반영 (API 계약 변경 없음) |
| v1.24 | 2026-07-20 | ADR-0078의 test/admin PoC 계정 프로필을 반영 (API 역할 계약 변경 없음) |
| v1.23 | 2026-07-20 | 역할 기반 접근 제한 화면의 중립 테두리 표시를 반영 (API 계약 변경 없음) |
| v1.22 | 2026-07-20 | S-014의 개별 검색 데이터 갱신은 신규·개정 자료 확인 및 단건 색인 실패 복구용이며, 공통 검색 설정 변경은 별도 전체 일괄 갱신 범위임을 화면 안내에 반영 (API 계약 변경 없음) |
| v1.21 | 2026-07-20 | S-014에서 청크 확인, 검색 데이터 갱신, 검토 적용 중지를 사용자용 명칭으로 구분하고 검색 갱신과 적용 중지가 서로 독립된 API 동작임을 명시 (API 계약 변경 없음) |
| v1.20 | 2026-07-20 | API 호출 없이 렌더링 실패를 처리하는 전용 오류 경계 화면의 중립 중앙 안내·뷰포트 높이 경계를 반영 |
| v1.19 | 2026-07-20 | API 계약 변경 없이 접근 거부 상태의 중립 표시, 데스크톱 고정 탐색 및 검증 제외 선택의 화면 안내 경계를 동기화 |
| v1.18 | 2026-07-20 | API 계약은 유지하고 S-012/S-014/S-015/S-016의 화면 기본 출력에서 기술 식별자·해시·원시 enum을 제거하여 일반 업무 용어로 표시하는 경계를 반영 |
| v1.17 | 2026-07-18 | S-014 규정·가이드라인 등록 화면의 적용 범위·문서 정보·검토 본문 흐름과 검색 반영의 사용자용 상태명을 반영 (API 계약 변경 없음) |
| v1.16 | 2026-07-18 | 광고물 상세의 기존 검토 이력 조회·진행/결과 복귀와 핵심 화면 공통 업무 단계·결과 하위 탐색 표시를 반영 |
| v1.15 | 2026-07-18 | 로그인 카드의 정적 NH농협은행 로고를 제거하고 인증 후 공통 헤더에만 유지하도록 화면 표시 경계를 정정 |
| v1.14 | 2026-07-18 | S-004~S-008 원본 자동 미리보기와 Worker 단계별 진행률·화면 이탈 후 서버 작업 지속 경계를 반영 |
| v1.13 | 2026-07-17 | 로그인·공통 헤더의 NH농협은행 로고 표시와 대체 텍스트는 API 호출 없이 정적 자산으로 제공함을 명시 |
| v1.12 | 2026-07-17 | HWP/HWPX private SVG 미리보기 호출, 실패 코드 및 Text IR 병행 표시를 반영 |
| v1.11 | 2026-07-16 | S-004 로컬 오늘 기준일 기본값, S-005 완료 단계 정합성, S-007 HWP/HWPX preview 비호출과 Text IR 안내를 반영 |
| --- | --- | --- |
| v1.10 | 2026-07-16 | 로그인 UI에서 내부 마일스톤 표기를 제거하고 사용자용 제목만 유지하는 화면 반영 기준을 추가 |
| v1.9 | 2026-07-16 | 앱 시작·401 refresh 복구, collection pagination, S-006 광고 상세 병합과 S-013 prefill, 복수 suggestion 판단 호출을 화면 흐름에 동기화 |
| v1.8 | 2026-07-15 | OpenAPI v0.7.0의 정확히 다섯 Validation operation으로 S-015 데이터셋/판단과 S-016 불변 KPI 실행/조회를 연결하고 권한·평가 제외·분모 0 미적용 표시 경계를 동기화 |
| v1.7 | 2026-07-15 | OpenAPI v0.6.0 S-009~S-013 생성 client route, 문구 판단 검증, 비단정 Q&A, 초안 이력, 불변 HWPX/PDF snapshot과 구조 비교 화면 상태 동기화 |
| v1.6 | 2026-07-14 | OpenAPI v0.5.0 S-006~S-008 결과 요약·상세·Annotation 생성 client route와 preview/필터/부분 실패·권한 화면 상태 동기화 |
| v1.5 | 2026-07-14 | OpenAPI v0.4.0 S-004/S-005 요청·진행·retry/stale/final failure·quality warning·재분석·권한/redaction client 흐름 동기화 |
| v1.4 | 2026-07-14 | S-014 내부 기준 등록의 필수 metadata JSON, 상위 필드 정합성 및 `REFERENCE_METADATA_INVALID` 안전 표시 경계 반영 |
| v1.3 | 2026-07-14 | S-014 생성 client 연동, 역할별 route gate, 직접 입력 등록·불변 version·Hybrid 503·Chunk redaction의 화면 상태를 실행 흐름과 동기화 |
| v1.2 | 2026-07-14 | S-014 기준자료 단건/이력/reindex/chunk 계약 확정, 관리자 상태·오류·내부 인덱스 식별자 redaction 경계 반영 |
| v1.1 | 2026-07-14 | M2 로그인·광고물 목록·등록·기본 상세의 실제 API 호출, 상태, 권한 및 계약 생성 타입 사용 기준 반영 |
| v1.0 | 2026-07-13 | ADR-0001~ADR-0074 검토 결과 반영, 화면/API 호출 정합성 기준 보강 |

---

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 화면-API 매핑표 |
| 프로젝트명 | AI 활용 금융상품 광고심의 적정성 검토 에이전트 |
| 문서 버전 | v1.7 |
| 작성 목적 | 화면별 호출 API, 호출 시점, 요청값, 응답값, 화면 반영 항목을 정의 |
| 기준 문서 | 화면설계서 v0.1, API 명세서 v0.1 |
| API Base URL | `/api/v1` |

---

# 1. 작성 기준

## 1.1 매핑 기준

본 문서는 화면별로 다음 기준에 따라 API를 매핑한다.

| 구분 | 설명 |
| --- | --- |
| 화면 ID | 화면설계서의 화면 ID |
| 화면명 | 사용자에게 표시되는 화면명 |
| 호출 시점 | 화면 진입, 조회 버튼 클릭, 저장 버튼 클릭, 행 선택 등 |
| API | 호출할 API Endpoint |
| Method | HTTP Method |
| 주요 요청값 | Path Variable, Query Parameter, Request Body, Form Data |
| 주요 응답값 | 화면에 표시하거나 후속 처리에 사용하는 값 |
| 화면 반영 | 응답 데이터를 화면 어디에 표시하는지 |
| 비고 | 추가 개발 필요 API, 권한, 예외 사항 |

---

## 1.2 공통 호출 API

여러 화면에서 공통으로 사용할 가능성이 높은 API는 다음과 같다.

| 구분 | API | Method | 설명 | 비고 |
| --- | --- | --- | --- | --- |
| 로그인 | `/auth/login` | POST | access token과 사용자 context 수신 | `credentials: include`, `refreshToken` httpOnly cookie는 브라우저가 관리. UI는 `로그인`만 표시하며 내부 마일스톤 명칭과 NH농협은행 로고를 노출하지 않는다. 로고는 인증 후 공통 헤더에서 API 없이 정적 자산과 대체 텍스트로 제공한다. |
| 로그아웃 | `/auth/logout` | POST | refresh session revoke와 cookie 삭제 | 화면은 성공/실패와 무관하게 메모리 access token 제거 |
| 사용자 정보 | `/users/me` | GET | 로그인 사용자 정보 조회 | API 명세서 정의됨 |
| 공통 코드 | `/codes/product-groups` | GET | 상품군 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/advertisement-types` | GET | 광고유형 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/review-types` | GET | 검토유형 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/risk-levels` | GET | 위험도 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 공통 코드 | `/codes/review-statuses` | GET | 검토 상태 코드 조회 | `/codes/{codeGroup}`으로 정의됨 |
| 파일 미리보기 descriptor | `/files/{fileId}/preview` | GET | 권한 검증 후 backend 상대 미리보기 경로와 페이지 메타데이터 조회 | API 명세서 정의됨 |
| 파일 미리보기 content | `/files/{fileId}/preview/content` | GET | `pageNo`의 렌더링 이미지를 Bearer 인증 backend proxy로 조회 | API 명세서 정의됨 |
| 파일 다운로드 | `/files/{fileId}/download` | GET | 첨부파일을 Bearer 인증 backend proxy로 다운로드 | API 명세서 정의됨 |

---

# 2. 화면별 API 매핑 요약

| 화면 ID | 화면명 | 주요 API |
| --- | --- | --- |
| S-001 | 메인 대시보드 | 대시보드 요약 조회, 최근 광고물 조회 |
| S-002 | 광고물 목록 | 광고물 목록 조회 |
| S-003 | 광고물 등록 | 광고물 등록, 광고물 수정 |
| S-004 | AI 검토 요청 | 광고물 상세 조회, AI 검토 요청 |
| S-005 | 검토 진행 상태 | AI 검토 진행 상태 조회, 재분석 요청 |
| S-006 | 검토 결과 요약 | 검토 요약 조회, 상세 항목 조회 |
| S-007 | 광고 화면 검토 UI | 파일 미리보기, Annotation 조회, 검토 항목 상세 조회 |
| S-008 | 상세 검토 결과 | 검토 항목 목록 조회, 검토 항목 상세 조회 |
| S-009 | 문구 추천 | 문구 추천 조회, 채택 여부 저장 |
| S-010 | 광고 규정 Q&A | 질의응답 요청, Q&A 이력 조회 |
| S-011 | 심의 의견 초안 | 초안 생성, 초안 수정 |
| S-012 | 검토 리포트 | 리포트 생성, 리포트 조회, 다운로드 |
| S-013 | 수정 전후 비교 | 수정본 등록, 비교 요청, 비교 결과 조회 |
| S-014 | 기준자료 관리 | 기준자료 목록 조회, 등록, 수정, 비활성화 |
| S-015 | 검토 품질 관리 | 검증 데이터 조회, 등록, 담당자 판단 등록 |
| S-016 | 검증 결과 평가 | 성능 평가 실행, 평가 결과 조회 |
| S-017 | 사용자/권한 관리 | 사용자 목록 조회, 권한 변경, 감사 로그 조회 |

---

# 3. 상세 화면-API 매핑

---

## S-001 메인 대시보드

### 3.1 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-001 |
| 화면명 | 메인 대시보드 |
| 화면 목적 | 광고물 검토 현황, 최근 광고물, 주요 리스크 현황을 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자, 관리자 |

---

### 3.2 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 대시보드 요약 조회 | `/dashboard/summary` | GET | `fromDate`, `toDate`, `departmentId` | 전체 광고물 수, 검토 대기, 분석 중, 검토 완료, 확인 필요 건수 | 검토 현황 요약 영역 |
| 화면 진입 | 위험도 현황 조회 | `/dashboard/risk-summary` | GET | `fromDate`, `toDate`, `departmentId` | 위험도 높음/중간/낮음/확인 필요 건수 | 주요 리스크 현황 영역 |
| 화면 진입 | 최근 광고물 조회 | `/advertisements` | GET | `page=1`, `size=5`, `sort=createdAt,desc` | 최근 광고물 목록 | 최근 등록 광고물 영역 |
| 광고물 등록 클릭 | 화면 이동 | - | - | - | - | S-003 이동 |
| 광고물 목록 클릭 | 화면 이동 | - | - | - | - | S-002 이동 |

### 3.3 추가 필요 API

| API | 사유 |
| --- | --- |
| `/dashboard/summary` | 현재 API 명세서에 없음. 대시보드용 집계 API 필요 |
| `/dashboard/risk-summary` | 위험도 집계 전용 API 필요 |

---

## S-002 광고물 목록

### 3.4 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-002 |
| 화면명 | 광고물 목록 |
| 화면 목적 | 등록된 광고물과 AI 검토 상태 조회 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.5 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 목록 기본 조회 | `/advertisements` | GET | `page`, `size` | 광고물 목록, 페이지 정보 | 목록 영역 |
| 조회 버튼 클릭 | 조건 검색 | `/advertisements` | GET | `keyword`, `productGroup`, `advertisementType`, `reviewStatus`, `riskLevel`, `fromDate`, `toDate`, `page`, `size` | 조건에 맞는 광고물 목록 | 목록 영역 |
| 목록 행 클릭 | 광고물 상세 이동 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 광고물 상세정보 | S-006 또는 상세 화면 이동 전 데이터 |
| AI 검토 요청 클릭 | 검토 요청 화면 이동 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 광고물 기본정보, 파일정보 | S-004 이동 |
| 리포트 보기 클릭 | 리포트 상세 조회 | `/reports/{reportId}` | GET | `reportId` | 리포트 메타데이터, 다운로드 URL | S-012 이동 |

M2 1차 화면은 OpenAPI v0.2.0 `AdvertisementPage`에 잠긴 광고물 ID·광고명·상품군·광고유형·담당부서·등록자·등록일시·검토 상태만 표시한다. 종합 위험도와 리포트 action은 해당 후속 capability 계약이 잠기기 전에는 요청하거나 임시 필드로 합성하지 않는다. 목록 loading/empty/error와 역할 거부를 각각 표시하며, 오류는 code 매핑 문구와 `traceId`만 노출한다.

### 3.5.1 M2 기본 상세 상태

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 목록 ID 클릭 | M2 광고물 기본 상세 | `/advertisements/{advertisementId}` | GET | `advertisementId` | `AdvertisementDetail`, 안전한 `AdvertisementFile` 메타데이터 | `/advertisements/{advertisementId}` 기본정보·파일 목록 |
| 광고물 상세 진입 | 기존 검토 이력 조회 | `/advertisements/{advertisementId}/reviews` | GET | `advertisementId` | `ReviewHistory[]`: 회차, 검토 상태, 위험도, 요청·완료일 | 상세정보 API와 병렬 호출, 30초 캐시 재사용, 최근 검토 우선 표시 및 진행 중이면 S-005·완료/확인 필요이면 S-006 복귀 링크 제공 |
| 시스템 관리자 삭제 | 광고물·연결 결과 비노출 | `/advertisements/{advertisementId}` | DELETE | `advertisementId` | `204 No Content` | 확인 대화상자 뒤 목록으로 복귀한다. 삭제 후 원본 파일과 연결 검토 결과는 일반 조회 경로에서 표시하지 않는다. |
| 시스템 관리자 선택 삭제 | 현재 페이지 광고물 일괄 삭제 | `/advertisements/{advertisementId}` | DELETE (항목별) | 선택한 `advertisementId` 목록 | 각 항목 `204 No Content` | 개별 선택 또는 현재 페이지 전체 선택 뒤 확인 대화상자를 표시한다. 별도 bulk API는 만들지 않으며 완료·실패 후 목록을 다시 조회한다. |
| 단건 권한 거부 | 부서 scope 거부 | `/advertisements/{advertisementId}` | GET | 타 부서 `advertisementId` | 403 `ErrorResponse` | 전용 권한 안내. raw message, object key, presigned URL 미표시 |
| 파일 미리보기 클릭 | 미리보기 descriptor 조회 | `/files/{fileId}/preview` | GET | `fileId`, `pageNo=1` | `FilePreview`, backend 상대 `previewPath` | 안전한 content 경로 검증 후 다음 호출 |
| descriptor 검증 후 | 렌더링 이미지 조회 | `/files/{fileId}/preview/content` | GET | `fileId`, `pageNo` | PNG/JPEG 또는 PDF의 OCR 동일 200-DPI PNG, HWP/HWPX 변환 `image/svg+xml` binary | object URL로 화면 미리보기. HWP/HWPX SVG는 이미지처럼 가로폭에 맞춰 렌더링하고 가로 스크롤 없이 세로 스크롤로 확인한다. Bearer 인증 유지 |
| 파일 다운로드 클릭 | 원본 파일 proxy 다운로드 | `/files/{fileId}/download` | GET | `fileId` | binary, `Content-Disposition` | 파일명으로 저장. Bearer 인증 유지 |
| 파일 권한 거부 | 부서 scope 거부 | 위 파일 API | GET | 타 부서 `fileId` | 403 `ErrorResponse` | 미리보기/다운로드 전용 권한 안내. raw message, bucket, object key 미표시 |

---

## S-003 광고물 등록

### 3.6 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-003 |
| 화면명 | 광고물 등록 |
| 화면 목적 | AI 검토 대상 광고물과 관련 파일 등록 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.7 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 상품군 코드 조회 | `/codes/product-groups` | GET | 없음 | 상품군 코드 목록 | 상품군 선택값 |
| 화면 진입 | 광고유형 코드 조회 | `/codes/advertisement-types` | GET | 없음 | 광고유형 코드 목록 | 광고유형 선택값 |
| 저장 버튼 클릭 | 광고물 등록 | `/advertisements` | POST | `multipart/form-data`: 광고명, 상품군, 광고유형, 광고채널, 담당부서, 광고파일, 상품설명서, 약관, 추가 첨부파일(최대 10개) | `advertisementId`, `reviewStatus`, 파일 정보 | 저장 완료 메시지, S-002 또는 S-004 이동 |
| AI 검토 요청 클릭 | 광고물 등록 후 검토 요청 화면 이동 | `/advertisements` → `/advertisements/{advertisementId}` | POST → GET | 등록 Form Data | 광고물 ID, 상세정보 | S-004 이동 |
| 수정 모드 저장 | 광고물 기본정보 수정 | `/advertisements/{advertisementId}` | PATCH | 광고명, 상품군, 광고유형, 메모 | 수정일시 | 수정 완료 메시지 |

M2 1차 등록은 OpenAPI v0.2.0 생성 타입을 client 경계에서 사용한다. 공통 코드 loading/error, 필수값, 광고 파일·상품설명서·약관·추가 첨부파일 각각의 허용 확장자·50 MiB 선검증과 추가 첨부파일 최대 10개 제한, 역할별 등록 action을 처리한다. `multipart/form-data`의 `Content-Type` boundary는 브라우저가 설정한다. 성공 시 응답 `advertisementId`의 기본 상세로 이동하며, 서버 오류의 raw `message`/`details`에 포함될 수 있는 내부 경로나 민감 원문은 화면에 직접 표시하지 않는다.

---

## S-004 AI 검토 요청

### 3.8 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-004 |
| 화면명 | AI 검토 요청 |
| 화면 목적 | 광고물에 적용할 검토 항목 선택 및 AI 분석 요청 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.9 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회·원본 자동 미리보기 | `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `advertisementId`, `fileId`, `pageNo` | 광고명, 상품군, 광고유형, 파일 목록·private preview | 입력 영역과 원본 병행 패널 |
| 화면 진입 | 검토유형 코드 조회 | `/codes/review-types` | GET | 없음 | 검토유형 코드 목록 | 검토 항목 선택 영역 |
| 분석 요청 클릭 | AI 검토 요청 | `/advertisements/{advertisementId}/reviews` | POST | `CreateReviewRequest`: `standardEffectiveDate`(사용자 로컬 오늘 날짜 기본값, 변경 가능), `reviewTypes`, `includeSuggestion`, `includeOpinionDraft`, `requestMemo` | `ReviewAccepted`: `reviewId`, `jobId`, `reviewStatus`, `standardVersionIds`, `requestedAt` | 응답 `reviewId`로 S-005 이동 |
| 이전 클릭 | 화면 이동 | - | - | - | - | S-002 이동 |

---

## S-005 검토 진행 상태

### 3.10 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-005 |
| 화면명 | 검토 진행 상태 |
| 화면 목적 | AI 분석 진행 상태 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.11 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입/비 terminal 자동 갱신 | 검토 진행 상태·원본 병행 표시 | `/reviews/{reviewId}/status` → `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `reviewId`, `advertisementId`, `fileId`, `pageNo` | `ReviewProgress`: `currentStep`, `progressRate`, `steps`, `jobStatus`, `failedReasonCode`, `reviewStatus` 및 파일 preview | Worker가 영속한 단계별 진행률과 원본을 함께 표시한다. `RETRY_PENDING`은 기술 일시 오류의 자동 재시도, `OCR_UNREADABLE`은 원본 품질 확인, 그 외 `CHECK_REQUIRED`은 검토 근거·조건 확인으로 구분해 안내한다. 화면 이탈은 서버 작업을 중단하지 않고 재진입 시 최신 상태를 조회한다. `COMPLETED` Job은 모든 정의된 step을 완료로 표시 |
| 새로고침 클릭 | 상태 갱신 | `/reviews/{reviewId}/status` | GET | `reviewId` | 최신 `ReviewProgress` | 진행률 및 단계 갱신. terminal 상태에서는 자동 갱신 중지 |
| 결과 보기 클릭 | 검토 결과 요약 이동 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 검토 요약 | S-006 이동 |
| `isRetryable=true` 실패/stale에서 재분석 클릭 | AI 재분석 요청 | `/reviews/{reviewId}/rerun` | POST | `RerunReviewRequest`: `reason`, `reviewTypes` | `RerunReviewAccepted`: `newReviewId`, `previousReviewId`, `jobId`, `reviewStatus` | 이력을 덮어쓰지 않고 `newReviewId`의 S-005 표시 |
| 타 부서·권한 부족 | 상태/재분석 거부 | 위 API | GET/POST | Bearer 인증, `reviewId` | 403 일반화 응답 | 전용 권한 없음 상태. raw artifact/object key/presigned URL 미표시 |

---

## S-006 검토 결과 요약

### 3.12 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-006 |
| 화면명 | 검토 결과 요약 |
| 화면 목적 | AI 검토 결과의 종합 위험도와 주요 리스크 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.13 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회·원본 자동 미리보기 | `/advertisements/{advertisementId}` → `/files/{fileId}/preview` | GET | `advertisementId`, `fileId`, `pageNo` | 광고 기본정보, 파일정보·private preview | 데스크톱 좌측의 넓은 원본 패널과 우측 광고 기본정보 표. 구현 방식 설명은 표시하지 않음 |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 종합 위험도, 문제 건수, 검토유형별 요약, 주요 리스크 | 검토 요약 영역 |
| 주요 리스크 클릭 | 검토 항목 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 판단 사유, 근거, 추천 문구, ADR-0066 기준 Coordinate | 상세 팝업 또는 S-008 이동 |
| 광고 화면 보기 클릭 | Annotation 조회 | `/reviews/{reviewId}/annotations` | GET | `reviewId`, `pageNo` | Annotation 표시 모드, 위치 상태, Coordinate/텍스트 위치 | S-007 이동 |
| 상세 결과 보기 클릭 | 상세 목록 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 상세 검토 항목 목록 | S-008 이동 |
| 문구 추천 보기 클릭 | 문구 추천 조회 | `/reviews/{reviewId}/suggestions` | GET | `reviewId` | 추천 문구 목록 | S-009 이동 |
| 리포트 생성 클릭 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST | 리포트 옵션 | `reportId`, `reportStatus` | S-012 이동 |

---

## S-007 광고 화면 검토 UI

### 3.14 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-007 |
| 화면명 | 광고 화면 검토 UI |
| 화면 목적 | 광고 원본 위에 문제 영역, 위험도, 근거를 시각적으로 표시 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.15 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 광고물 상세 조회 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 파일 ID, 광고 기본정보 | 상단 정보 영역 |
| 화면 진입 | 광고 파일 미리보기 | `/files/{fileId}/preview` | GET | `fileId`, `pageNo` | 렌더링 이미지 또는 preview URL | 이미지/PDF/HWP/HWPX 모두 광고 원본 미리보기 영역에 호출. HWP/HWPX는 private 변환 SVG를 반환 |
| 화면 진입 | Annotation 조회 | `/reviews/{reviewId}/annotations` | GET | `reviewId`, `pageNo`, `reviewType` | 표시 모드, 위치 상태, Coordinate/텍스트 위치, 위험도, 검토유형 | 파일 형식별 Annotation 표시. HWP/HWPX는 구조 좌표를 우선 표시하고, 없으면 private SVG 글자 좌표와 `matchedText`가 정확히 일치하는 항목만 원본 위에 표시한다. 일치하지 않는 offset 항목은 원본 위치 미확정 목록으로 표시 |
| 로컬 자동심의 화면 진입 | 파서 좌표 조회 | `/operational/reviews/{reviewId}/parser-layout` | GET | `reviewId` | 200-DPI canvas, 페이지별 parser region/line bbox와 실제 텍스트 | 로컬 opt-in 전용. bbox 토글로 원본 위에 표시하며 제품 OpenAPI 계약에는 포함하지 않음 |
| Annotation 또는 목록 항목 클릭 | 검토 항목 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 원문, 문제유형, 판단사유, 근거, 추천문구 | 선택 항목 상세 패널 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 기준명, 조항, 내용, 적용일 | 근거 상세 팝업 |
| 필터 선택 | Annotation 필터링 | `/reviews/{reviewId}/annotations` | GET | `reviewType`, `riskLevel`, `pageNo` | 필터링된 Annotation 목록 | 화면 표시 갱신 |

### 3.16 추가 필요 API

| API | 사유 |
| --- | --- |
| `/files/{fileId}/preview` | 광고 원본 이미지/PDF 렌더링 표시 필요 |
| `/files/{fileId}/pages` | 다중 페이지 광고물의 페이지 수 조회 필요 시 추가 |

---

## S-008 상세 검토 결과

### 3.17 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-008 |
| 화면명 | 상세 검토 결과 |
| 화면 목적 | 항목별 검토 결과, 판단 사유, 근거, 추천 문구 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.18 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 상세 검토 결과 목록 조회 | `/reviews/{reviewId}/items` | GET | `reviewType`, `riskLevel`, `resultStatus`, `page`, `size` | 검토 항목 목록 | 목록 영역 |
| 조회/필터 클릭 | 상세 결과 조건 조회 | `/reviews/{reviewId}/items` | GET | 필터 조건 | 필터링된 검토 항목 목록 | 목록 영역 갱신 |
| 행 클릭 | 검토 항목 상세 조회·원본 위치 이동 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewId`, `reviewItemId` | 상세 판단 사유, ADR-0043 기준 핵심 근거 최대 3개, 추천 문구, Coordinate | 문구 우선 상세 패널을 표로 표시하고 Coordinate가 있으면 같은 화면의 원본 미리보기를 해당 위치로 스크롤 |
| 광고 화면에서 보기 클릭 | Annotation 위치 이동 | `/reviews/{reviewId}/annotations` | GET | `reviewItemId` 또는 `pageNo` | 표시 모드, 위치 상태, Coordinate/텍스트 위치 | S-007 이동 후 Coordinate가 있으면 원본 캔버스를 해당 위치로 스크롤 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 근거 상세정보 | 근거 팝업 |

### 3.18.1 M5 생성 client 실행 매핑

| 화면/route | 생성 operation | 실행 상태 및 화면 반영 |
| --- | --- | --- |
| S-006 `/reviews/{reviewId}/results` | `getReviewSummary` | 종합 위험도·집계·주요 리스크를 표시하고 `EvidenceStatus`의 검색 장애와 업무적 근거 부족을 서로 다른 안내로 표시한다. |
| S-008 `/reviews/{reviewId}/results/items` | `listReviewItems`, `getReviewItem` | 기본 조회는 `includeAppropriate=false`로 적정 항목을 숨기며 사용자가 전체 보기 전환 시 이를 true로 바꾼다. `reviewType`, `riskLevel`, `resultStatus` query도 생성 타입으로 전달한다. 문구를 우선 표시하고 검토 유형·판정·위험도는 칩으로 보조하며, 상세의 판단 방식·수정 권고·근거 상태는 표로 표시한다. Coordinate가 있으면 원본 미리보기의 해당 위치로 이동한다. |
| S-007 `/reviews/{reviewId}/results/annotations` | `listReviewAnnotations` | `pageNo`, `reviewType`, `riskLevel` query와 BOX/TEXT_HIGHLIGHT/LIST_ONLY/UNAVAILABLE 표시 모드를 소비하며, 위치 신뢰도 확인 목록을 유지한다. |
| S-007 원본 미리보기 | `getFilePreview` 후 `/files/{fileId}/preview/content` | Bearer 인증으로 descriptor의 동일 origin content만 Blob URL로 표시한다. PDF descriptor는 페이지 수만 확인하고 content에서 선택 페이지 raster를 한 번만 불러온다. Annotation의 `fileType`은 업무상 분류이므로 렌더링 형식 판정에 사용하지 않고 preview 콘텐츠 MIME 타입을 사용한다. 이미지와 PDF raster, HWP/HWPX 변환 SVG는 원본 media와 동일한 positioned wrapper 안에 가로폭 기준으로 표시한다. PNG/JPEG/PDF BOX는 실제 원본 페이지의 좌상단 정규화 좌표를 그 media 폭·높이로 변환한다. HWP/HWPX는 구조 좌표를 직접 BOX로 사용하지 않고 SVG 실제 글자 좌표와 API의 `matchedText`를 정확히 대조해 일치할 때만 하이라이트하며, API/원본 콘텐츠를 외부로 노출하지 않는다. |
| 공통 | 위 네 M5 operation | loading/empty/error/403을 전용 상태로 표시하고 서버 원문, raw artifact/object key/presigned URL은 렌더링하지 않는다. |

---

## S-009 문구 추천

### 3.19 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-009 |
| 화면명 | 문구 추천 |
| 화면 목적 | 위험 표현에 대한 대체 문구와 담당자 채택 여부 관리 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.20 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 문구 추천 목록 조회 | `/reviews/{reviewId}/suggestions` | GET | `reviewId` | 원문, 추천 문구, 추천 사유, 근거 ID, 채택 상태 | `includeSuggestion=true`인 검토는 완료 worker가 위험 Rule 결과와 연결 근거로 생성한 추천을 표시한다. LLM 문장 보강은 선택적이며 실패 시 Rule 기본 추천을 유지한다. 빈 배열이면 빈 상태와 S-008 이동을 표시 |
| 추천 항목 클릭 | 관련 검토 상세 조회 | `/reviews/{reviewId}/items/{reviewItemId}` | GET | `reviewItemId` | 판단 사유, 위험도, 근거 | 문제 분석 영역 |
| 근거 상세 클릭 | 근거 상세 조회 | `/evidences/{evidenceId}` | GET | `evidenceId` | 근거 상세정보 | 근거 팝업 |
| 채택/미채택/수정 후 저장 클릭 | 문구 추천 판단 저장 | `/suggestions/{suggestionId}/decision` | PATCH | `decisionStatus`, `finalText`, `comment`. `MODIFIED_AND_USED`는 `finalText` 필수 | 저장 결과, 수정일시, 최종 사용 문구 | 채택 상태 갱신 |

---

## S-010 광고 규정 Q&A

### 3.21 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-010 |
| 화면명 | 광고 규정 Q&A |
| 화면 목적 | 광고 규정 관련 질문에 대한 RAG 기반 답변 제공 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.22 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 현재 검토 요약·광고물 조회 | `/reviews/{reviewId}/summary` → `/advertisements/{advertisementId}` | GET | `reviewId`, `advertisementId` | 기준 적용일, 상품군, 광고유형 | 별도 탭의 질문 범위로 자동 적용하고 현재 검토 기준으로 표시 |
| 화면 진입 | 현재 검토 Q&A 이력 조회 | `/qa/questions?reviewId={reviewId}` | GET | `reviewId` | 세션 ID, 질문, 답변, 근거, 생성 시각 | 같은 검토의 가장 최근 대화 세션을 복원 |
| 질문 보내기 클릭 | 광고 규정 질의응답 요청 | `/qa/questions` | POST | `question`, `reviewId`, `qaSessionId`, `productGroup`, `advertisementType`, `standardEffectiveDate` | 세션 ID, 질문, 답변 요약, 상세 설명, 근거, 추천 문구, 담당자 검토 필요 여부 | 첫 질문은 세션 생성, 후속 질문은 현재 세션에 추가 |
| 결과 요약/검토 및 리포트 탭 이동 | 화면 전환 | - | - | `reviewId` | - | Q&A는 서버에 저장하므로 재진입 시 이력을 복원 |

---

## S-011 심의 의견 초안

### 3.24 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-011 |
| 화면명 | 심의 의견 초안 |
| 화면 목적 | AI 검토 결과 기반 심의 의견 초안 생성 및 수정 |
| 주요 사용자 | 준법감시 담당자 |

---

### 3.25 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 주요 리스크, 문제 건수 | 광고 기본정보/요약 영역 |
| 화면 진입 | 상세 검토 항목 조회 | `/reviews/{reviewId}/items` | GET | `reviewId`, `riskLevel`, `resultStatus` | 검토 항목 목록 | 초안 포함 항목 선택 |
| 초안 생성 클릭 | 심의 의견 초안 생성 | `/reviews/{reviewId}/opinion-drafts` | POST | `includeReviewItemIds`, `templateType`, `additionalInstruction` | `draftId`, `draftContent`, 포함 항목 | AI 생성 초안 영역 |
| 저장 클릭 | 심의 의견 초안 수정 | `/opinion-drafts/{draftId}` | PATCH | `finalContent` | 수정 결과, 수정일시 | 담당자 수정 영역 저장 |
| 기존 초안 조회 | 초안 목록 조회 | `/reviews/{reviewId}/opinion-drafts` | GET | `reviewId` | 초안 목록 또는 최신 초안 | 초안 목록 영역 |

### 3.26 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /opinion-drafts/{draftId}` | 초안 단건 상세 조회 필요 |

---

## S-012 검토 리포트

### 3.27 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-012 |
| 화면명 | 검토 리포트 |
| 화면 목적 | 광고물별 검토 결과 리포트 생성, 미리보기, 다운로드 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.28 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검토 결과 요약 조회 | `/reviews/{reviewId}/summary` | GET | `reviewId` | 검토 요약 | 리포트 미리보기 기본 정보 |
| 화면 진입 | 상세 항목 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 상세 검토 항목 목록, ADR-0043 기준 핵심 근거 1~3개 | 리포트 상세 항목 |
| 리포트 생성 클릭 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST | `reportType`, `format=HWPX/PDF`, `includeAnnotations`, `includeSuggestions`, `includeOpinionDraft`, `includeEvidenceDetails` | `reportId`, `reportStatus` | 생성 완료 메시지 |
| 미리보기 클릭 | 리포트 상세 조회 | `/reports/{reportId}` | GET | `reportId` | 리포트 메타데이터, 다운로드 URL | 미리보기 영역 |
| 다운로드 클릭 | 리포트 다운로드 | `/reports/{reportId}/download` | GET | `reportId` | Binary File | 파일 다운로드 |
| 인쇄 클릭 | 프론트 처리 | - | - | - | - | 브라우저 인쇄 또는 파일 인쇄 |

---

## S-013 수정 전후 비교

### 3.29 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-013 |
| 화면명 | 수정 전후 비교 |
| 화면 목적 | 최초 광고안과 수정 광고안의 차이 및 지적사항 해결 여부 확인 |
| 주요 사용자 | 상품부서 담당자, 준법감시 담당자 |

---

### 3.30 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 기존 광고물 상세 조회 | `/advertisements/{advertisementId}` | GET | `advertisementId` | 원본 광고물 정보, 파일정보 | 원본 정보 영역 |
| 화면 진입 | 기존 검토 결과 조회 | `/reviews/{reviewId}/items` | GET | `reviewId` | 기존 지적사항 목록 | 수정 전 영역 |
| 수정본 업로드 클릭 | 수정본 등록 | `/advertisements/{advertisementId}/revisions` | POST | `multipart/form-data`: `revisionMemo`, `revisedAdvertisementFile` | `revisionId`, `reviewStatus` | 수정본 등록 완료 |
| 비교 실행 클릭 | 수정 전후 비교 요청 | `/advertisements/{advertisementId}/comparisons` | POST | `baseReviewId`, `revisionId`, `compareTypes` | `comparisonId`, 해결/미해결/신규 건수 | 비교 결과 요약 |
| 비교 결과 조회 | 비교 상세 조회 | `/comparisons/{comparisonId}` | GET | `comparisonId` | 변경 문구, 해결 여부, 신규 리스크 | 비교 상세 영역 |
| 재분석 요청 클릭 | AI 재분석 요청 | `/reviews/{reviewId}/rerun` | POST | `reason`, `reviewTypes` | `newReviewId` | S-005 이동 |

### 3.30.1 M6 생성 client 실행 매핑

| 화면/route | 생성 operation | 실행 상태 및 화면 반영 |
| --- | --- | --- |
| S-009 `/reviews/{reviewId}/support` | `listReviewSuggestions`, `recordSuggestionDecision` | 추천 문구를 조회해 검토 문구와 권고 문구를 별도 비교 필드로 표시하고 `ACCEPTED`, `REJECTED`, `MODIFIED_AND_USED`를 저장한다. `MODIFIED_AND_USED`는 요청 전 `finalText`를 필수 검증하며 저장 후 목록을 다시 조회한다. |
| S-010 `/reviews/{reviewId}/results/qa` | `getReviewSummary`, `getAdvertisement`, `askComplianceQuestion` | 현재 검토의 상품군·광고유형·기준 적용일을 질문 범위에 자동 적용한다. 질문 결과의 답변 요약·상세·고정 근거·참고 문구를 표시하며, 근거가 없고 `needsHumanReview=true`이면 확정 답변 대신 담당자 확인 안내와 빈 근거 상태를 표시한다. 전송에 실패한 질문은 같은 질문 내용으로 다시 호출할 수 있게 유지한다. 재호출 시 질문 범위(세션, 상품군, 광고유형, 기준 적용일)는 현재 검토 상태로 다시 구성한다. 미해결 실패 질문이 여러 건이면 각각을 독립적으로 재호출하고, 재호출이 성공한 질문만 실패 상태에서 제외한다. 검토 식별자가 바뀌면 이전 검토의 `qaSessionId`를 사용하지 않는다. |
| S-011 `/reviews/{reviewId}/support` | `listOpinionDrafts`, `createOpinionDraft`, `updateOpinionDraft` | 최신 초안을 조회하고 없으면 생성한다. 원본 `draftContent`를 유지한 채 담당자 `finalContent`를 저장하고 다시 조회한다. |
| S-012 `/reviews/{reviewId}/support` | `createReviewReport`, `getReviewReport`, `downloadReviewReport` | HWPX/PDF 리포트의 생성 형식·준비 상태와 다운로드를 표시한다. 응답의 식별자·해시는 클라이언트 동작에만 사용하고 기본 화면에는 표시하지 않는다. 다운로드는 Bearer 권한을 확인하며 변환 실패는 원본 HWPX와 분리한다. |
| S-013 `/advertisements/{advertisementId}/comparisons` | `createAdvertisementComparison`, `getAdvertisementComparison` | 기존 검토에서 진입해 수정본을 비교하고 해결·미해결·신규 확인 건수와 항목을 표시한다. 비교 API의 식별자는 요청에만 사용하며 기본 화면에는 노출하지 않는다. |
| 공통 | 위 M6 operation | loading/error/403을 공통 상태로 표시하고 지원 산출물은 자동 확정하지 않는다. 화면은 내부 snapshot 원문, 감사 메타데이터, 저장소 경로를 노출하지 않는다. |

---

## S-014 기준자료 관리

### 3.31 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-014 |
| 화면명 | 검토 기준자료 관리 |
| 화면 목적 | 규정·가이드라인·내부 기준 등록 및 광고 검토 근거 관리 |
| 주요 사용자 | 기준 관리자, 시스템 관리자 |

---

### 3.32 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 기준자료 목록 조회 | `/standards` | GET | `page`, `size`, `activeOnly` | 기준자료 목록 | 목록 영역 |
| 조회 클릭 | 기준자료 조건 검색 | `/standards` | GET | `keyword`, `evidenceType`, `productGroup`, `advertisementType`, `ruleType`, `activeOnly` | 조건에 맞는 기준자료 목록 | 목록 영역 |
| 기준자료 등록 클릭 | 규정·가이드라인·내부 기준 등록 | `/standards` | POST | `multipart/form-data`: 기준명, `INTERNAL_STANDARD`, 상품군, 광고유형, 기준성격, 중요도, 적용일, 직접 입력 내용, 선택 원문 파일 및 `metadata` JSON(`owningDepartment`, `documentName`, `sectionPath`, `effectiveDate`, `version`, `productGroup`, `inputBoundary`) | `standardId`, `evidenceId`, `version` | 등록 완료 후 목록 갱신. `metadata.productGroup`/`effectiveDate`는 상위 multipart 필드와 같은 값 유지 |
| 행 클릭 | 기준자료 단건 조회 | `/standards/{standardId}` | GET | `standardId` | master와 현재 불변 version 상세 | 상세 영역 |
| 수정 클릭 | 기준자료 수정 | `/standards/{standardId}` | PATCH | 기준명, 내용, 적용일, 변경 사유 | 수정 결과 | 상세 영역 갱신 |
| 검토 적용 중지 클릭 | 기준자료 검토 적용 중지 | `/standards/{standardId}/deactivate` | PATCH | `reason` | 미적용 상태 | 기준자료와 이력은 유지하고 광고 검토·근거 검색 대상에서 제외 |
| 이력 보기 클릭 | 기준자료 변경 이력 조회 | `/standards/{standardId}/histories` | GET | `standardId` | 불변 version 변경 이력 목록 | 이력 패널 |
| 검색 데이터 갱신 클릭 | 선택한 기준자료 버전의 검색 데이터 갱신 요청 | `/standards/{standardId}/versions/{standardVersionId}/reindex` | POST | `reindexScope`, `reason`, model/version 정보 | `jobId`, `jobStatus` | 신규·개정 자료 확인 또는 단건 색인 실패 복구에 사용. 공통 모델·스키마 변경은 전체 일괄 갱신 범위 |
| 검색 데이터 갱신 상태 확인 | 기준자료 검색 데이터 갱신 상태 조회 | `/standard-reindex-jobs/{jobId}` | GET | `jobId` | 상태, 처리 건수, 실패 사유 | 상태 배지/오류 표시 |
| 청크 확인 클릭 | 기준자료 청크 목록 조회 | `/evidences/{evidenceId}/chunks` | GET | `evidenceId`, `page`, `size` | 내부 index/point/doc ID가 제거된 청크 내용·version·상태 | 관리자 보조 화면 |

### 3.33 확정 계약 경계

| API | 확정 기준 |
| --- | --- |
| `/standards/{standardId}/histories` | 불변 version 이력 조회 계약으로 사용 |
| `/standards/{standardId}` | master와 현재 version 단건 조회 계약으로 사용 |

### 3.34 화면 상태 및 권한 매핑

| 경계 | 화면 처리 |
| --- | --- |
| 생성 타입 | OpenAPI 0.3.0 frozen 문서로 생성한 `StandardPage`, `StandardDetail`, `StandardHistoryPage`, `StandardReindexJob`, `EvidenceChunkPage`, `EvidenceSearchResult`를 client와 화면 경계에 사용 |
| Route 권한 | `STANDARD_MANAGER`, `SYSTEM_ADMIN`만 `/standards` 접근과 navigation link를 허용하고, 그 외 role은 API 요청 전에 차단 |
| 목록/관리 loading | 목록 조회와 상세·이력·청크 확인·검색 데이터 갱신·등록·수정·검토 적용 중지 action 진행 상태를 분리해 표시 |
| Empty | 목록/이력/Chunk/검색 결과가 0건이면 해당 영역의 빈 상태 표시 |
| 오류/redaction | ADR-0045 일반화 문구와 안전한 traceId만 표시하고 server message 및 index/point/doc ID를 숨김 |
| 등록 metadata 오류 | `REFERENCE_METADATA_INVALID`를 필수 메타데이터 입력 확인 문구로 표시하고 안전한 traceId만 제공하며 backend 원문 message는 숨김 |
| Hybrid 장애 | `/evidences/search` 또는 재색인 503을 정상/빈 결과로 fallback하지 않고 검색 인프라 장애로 표시 |

---

## S-015 PoC 검증 관리

### 3.34 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-015 |
| 화면명 | PoC 검증 관리 |
| 화면 목적 | 검증 데이터셋 및 담당자 판단 결과 관리 |
| 주요 사용자 | 준법감시 담당자, 기준 관리자 |

---

### 3.35 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 검증 데이터셋 목록 조회 | `/validation/datasets` | GET | `productGroup`, `advertisementType`, `page`, `size` | 검증 데이터셋 목록 | 목록 영역 |
| 검증 데이터 등록 클릭 | 검증 데이터셋 등록 | `/validation/datasets` | POST | `multipart/form-data`: 데이터셋명, 상품군, 광고유형, 샘플 광고물, 상품조건파일, 담당자 의견, 정답 JSON | `datasetId` | 등록 완료 메시지 |
| 행 클릭 | 검증 데이터셋 상세 조회 | `/validation/datasets/{datasetId}` | GET | `datasetId` | 샘플 광고물, 정답 데이터, AI 결과 | API 추가 필요 |
| 담당자 판단 등록 클릭 | 담당자 판단 결과 등록 | `/validation/datasets/{datasetId}/judgments` | POST | `judgments`, `excluded` | 등록 결과 | 판단 결과 영역 |
| AI 결과 비교 클릭 | 검증 비교 결과 조회 | `/validation/datasets/{datasetId}/comparison` | GET | `datasetId` | AI 판정, 담당자 판단, 일치 여부 | API 추가 필요 |
| 평가 제외 클릭 | 평가 제외 처리 | `/validation/datasets/{datasetId}/exclude` | PATCH | `excluded`, `excludeReason` | 평가 제외 상태 | API 추가 필요 |

M7 실행 화면은 frozen v0.7.0 범위의 `listValidationDatasets`, `createValidationDataset`, `createValidationJudgments` 세 operation만 사용한다. 데이터셋/판단 제외는 각 등록 요청의 `excluded`, `excludeReasonCode`, `excludeReasonDetail`로 처리하며 별도 PATCH 계약은 후속 범위로 유지한다.

| 실행 상태 | 화면 처리 |
| --- | --- |
| loading / empty | 목록 요청 중 loading과 0건 상태를 분리한다. |
| error | ADR-0045 안전 문구와 traceId만 표시한다. |
| permission | 준법감시/기준 관리자만 등록 action을 표시하고 시스템 관리자는 조회 전용, 상품부서 직접 접근은 요청 전에 차단한다. |
| version / exclusion | dataset version과 평가 대상/제외 사유를 목록에 표시한다. |

### 3.36 추가 필요 API

| API | 사유 |
| --- | --- |
| `/validation/datasets/{datasetId}` | 검증 데이터셋 단건 상세 조회 필요 |
| `/validation/datasets/{datasetId}/comparison` | AI 결과와 담당자 판단 비교 조회 필요 |
| `/validation/datasets/{datasetId}/exclude` | 평가 제외 처리 필요 |

---

## S-016 성능 평가

### 3.37 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-016 |
| 화면명 | 성능 평가 |
| 화면 목적 | PoC KPI별 성능 평가 실행 및 결과 확인 |
| 주요 사용자 | 준법감시 담당자, 시스템 관리자 |

---

### 3.38 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 최근 평가 결과 목록 조회 | `/validation/evaluations` | GET | `page`, `size`, `fromDate`, `toDate` | 평가 결과 목록 | API 추가 필요 |
| 평가 실행 클릭 | PoC 성능 평가 실행 | `/validation/evaluations` | POST | `datasetIds`, `metrics`, `excludeInvalidSamples` | `evaluationId`, KPI별 점수, 목표 달성 여부 | 평가 결과 영역 |
| 평가 결과 상세 클릭 | 평가 결과 조회 | `/validation/evaluations/{evaluationId}` | GET | `evaluationId` | KPI 점수, 오류 유형, 개선 필요사항 | 상세 영역 |
| 결과 다운로드 클릭 | 평가 결과 다운로드 | `/validation/evaluations/{evaluationId}/download` | GET | `evaluationId`, `format` | Binary File | API 추가 필요 |
| 결과보고서 반영 클릭 | 결과보고서 반영 | `/validation/evaluations/{evaluationId}/report-reflection` | POST | 반영 항목 | 반영 결과 | API 추가 필요 |

M7 실행 화면은 frozen v0.7.0의 `createValidationEvaluation`, `getValidationEvaluation` 두 operation만 사용한다. 평가 이력 목록·다운로드·결과보고서 반영은 후속 API 범위이며 현재 화면에서 호출하지 않는다.

| 실행 상태 | 화면 처리 |
| --- | --- |
| stored KPI | 서버의 score/분자/분모/목표/달성 여부를 그대로 표시하고 재계산하지 않는다. |
| denominator 0 | `notApplicable=true`를 `미적용`, `분모 0 · 목표 판단 제외`로 표시한다. |
| exclusion | `exclusionSummary`를 승인 제외 사유별 건수로 표시한다. |
| permission | 준법감시/시스템 관리자는 실행·조회, 기준 관리자는 조회 전용, 상품부서는 route 차단한다. |
| error | 평가 대상 없음과 조회 실패를 ADR-0045 안전 오류 상태로 표시한다. |

### 3.39 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /validation/evaluations` | 평가 이력 목록 조회 필요 |
| `GET /validation/evaluations/{evaluationId}/download` | 평가 결과 파일 다운로드 필요 |
| `POST /validation/evaluations/{evaluationId}/report-reflection` | PoC 결과보고서 반영 기능 필요 시 추가 |

---

## S-017 사용자/권한 관리

### 3.40 화면 개요

| 항목 | 내용 |
| --- | --- |
| 화면 ID | S-017 |
| 화면명 | 사용자/권한 관리 |
| 화면 목적 | 사용자 계정, 권한, 감사 로그 관리 |
| 주요 사용자 | 시스템 관리자 |

---

### 3.41 API 매핑

| 호출 시점 | 기능 | API | Method | 주요 요청값 | 주요 응답값 | 화면 반영 |
| --- | --- | --- | --- | --- | --- | --- |
| 화면 진입 | 사용자 목록 조회 | `/admin/users` | GET | `keyword`, `departmentId`, `role`, `status`, `page`, `size` | 사용자 목록 | 목록 영역 |
| 사용자 등록 클릭 | 사용자 등록 | `/admin/users` | POST | 사용자명, 부서, 이메일, 권한 | 사용자 ID | 목록 영역 갱신 |
| 권한 변경 클릭 | 사용자 권한 변경 | `/admin/users/{userId}/roles` | PATCH | `roles` | 변경 결과 | 권한 영역 갱신 |
| 비활성화 클릭 | 사용자 비활성화 | `/admin/users/{userId}/deactivate` | PATCH | `reason` | 비활성화 결과 | 목록 영역 갱신 |
| 로그 조회 클릭 | 시스템 로그 조회 | `/admin/audit-logs` | GET | `userId`, `actionType`, `fromDate`, `toDate` | 감사 로그 목록 | 로그 영역 |

### 3.42 추가 필요 API

| API | 사유 |
| --- | --- |
| `GET /admin/users/{userId}` | 사용자 상세 조회 필요 |

---

# 4. 주요 사용자 액션별 API 흐름

## 4.1 광고물 등록 후 AI 검토 요청

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-003 | 광고물 정보 입력 및 파일 업로드 | `/advertisements` | POST |
| 2 | S-004 | 검토 항목 선택 | `/advertisements/{advertisementId}` | GET |
| 3 | S-004 | AI 검토 요청 | `/advertisements/{advertisementId}/reviews` | POST |
| 4 | S-005 | 진행 상태 확인 | `/reviews/{reviewId}/status` | GET |
| 5 | S-006 | 결과 요약 확인 | `/reviews/{reviewId}/summary` | GET |

---

## 4.2 검토 결과 상세 확인

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-006 | 검토 결과 요약 확인 | `/reviews/{reviewId}/summary` | GET |
| 2 | S-008 | 상세 검토 결과 조회 | `/reviews/{reviewId}/items` | GET |
| 3 | S-008 | 검토 항목 상세 확인 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 4 | S-008 | 근거 상세 확인 | `/evidences/{evidenceId}` | GET |

---

## 4.3 광고 화면에서 문제 영역 확인

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-007 | 광고 파일 미리보기 | `/files/{fileId}/preview` | GET |
| 2 | S-007 | 문제 영역 조회 | `/reviews/{reviewId}/annotations` | GET |
| 3 | S-007 | Annotation 또는 목록 항목 클릭 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 4 | S-007 | 근거 상세 확인 | `/evidences/{evidenceId}` | GET |

---

## 4.4 문구 추천 채택

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-009 | 추천 문구 목록 조회 | `/reviews/{reviewId}/suggestions` | GET |
| 2 | S-009 | 추천 문구 선택 | `/reviews/{reviewId}/items/{reviewItemId}` | GET |
| 3 | S-009 | 채택/미채택/수정 후 저장 | `/suggestions/{suggestionId}/decision` | PATCH |

---

## 4.5 리포트 생성 및 다운로드

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-012 | 리포트 생성 옵션 선택 | - | - |
| 2 | S-012 | 리포트 생성 | `/reviews/{reviewId}/reports` | POST |
| 3 | S-012 | 리포트 상세 조회 | `/reports/{reportId}` | GET |
| 4 | S-012 | 리포트 다운로드 | `/reports/{reportId}/download` | GET |

---

## 4.6 PoC 성능 평가

| 순서 | 화면 | 사용자 액션 | API | Method |
| --- | --- | --- | --- | --- |
| 1 | S-015 | 검증 데이터셋 등록 | `/validation/datasets` | POST |
| 2 | S-015 | 담당자 판단 등록 | `/validation/datasets/{datasetId}/judgments` | POST |
| 3 | S-016 | 성능 평가 실행 | `/validation/evaluations` | POST |
| 4 | S-016 | 평가 결과 조회 | `/validation/evaluations/{evaluationId}` | GET |

---

# 5. API 보완 필요 목록

현재 API 명세서 기준으로 화면 구현 시 추가 정의가 필요한 API는 다음과 같다.

| 구분 | API | 필요 화면 | 필요 사유 | 우선순위 |
| --- | --- | --- | --- | --- |
| 대시보드 | `/dashboard/summary` | S-001 | 검토 현황 집계 | 중요 |
| 대시보드 | `/dashboard/risk-summary` | S-001 | 위험도별 집계 | 중요 |
| 파일 | `/files/{fileId}/download` | S-014, S-017 | 첨부파일 다운로드 | 중요 |
| 의견 초안 | `GET /opinion-drafts/{draftId}` | S-011 | 초안 단건 상세 조회 | 중요 |
| 검증 | `/validation/datasets/{datasetId}` | S-015 | 검증 데이터셋 상세 조회 | 중요 |
| 검증 | `/validation/datasets/{datasetId}/comparison` | S-015 | AI 결과와 담당자 판단 비교 | 중요 |
| 검증 | `/validation/datasets/{datasetId}/exclude` | S-015 | 평가 제외 처리 | 중요 |
| 평가 | `GET /validation/evaluations` | S-016 | 평가 이력 목록 조회 | 중요 |
| 평가 | `/validation/evaluations/{evaluationId}/download` | S-016 | 평가 결과 다운로드 | 선택 |
| 평가 | `POST /validation/evaluations/{evaluationId}/report-reflection` | S-016 | PoC 결과보고서 반영 | 선택 |
| 관리자 | `GET /admin/users/{userId}` | S-017 | 사용자 상세 조회 | 중요 |

---

# 6. 화면별 권한 매핑

| 화면 ID | 화면명 | 상품부서 담당자 | 준법감시 담당자 | 기준 관리자 | 시스템 관리자 |
| --- | --- | --- | --- | --- | --- |
| S-001 | 메인 대시보드 | 조회 | 조회 | 조회 | 조회 |
| S-002 | 광고물 목록 | 조회 | 조회 | 불가 | 조회 |
| S-003 | 광고물 등록 | 등록 | 등록 | 불가 | 등록 |
| S-004 | AI 검토 요청 | 요청 | 요청 | 불가 | 요청 |
| S-005 | 검토 진행 상태 | 조회 | 조회 | 불가 | 조회 |
| S-006 | 검토 결과 요약 | 조회 | 조회 | 불가 | 조회 |
| S-007 | 광고 화면 검토 UI | 조회 | 조회 | 불가 | 조회 |
| S-008 | 상세 검토 결과 | 조회 | 조회 | 불가 | 조회 |
| S-009 | 문구 추천 | 조회/의견 | 조회/의견 | 불가 | 조회 |
| S-010 | 광고 규정 Q&A | 사용 | 사용 | 사용 | 사용 |
| S-011 | 심의 의견 초안 | 제한 | 생성/수정 | 불가 | 조회 |
| S-012 | 검토 리포트 | 생성/조회 | 생성/조회 | 불가 | 생성/조회 |
| S-013 | 수정 전후 비교 | 등록/조회 | 조회 | 불가 | 조회 |
| S-014 | 기준자료 관리 | 불가 | 제한 조회 | 등록/수정 | 등록/수정 |
| S-015 | PoC 검증 관리 | 불가 | 등록/조회 | 등록/조회 | 조회 |
| S-016 | 성능 평가 | 불가 | 실행/조회 | 조회 | 실행/조회 |
| S-017 | 사용자/권한 관리 | 불가 | 불가 | 불가 | 관리 |

---

# 7. 화면별 주요 예외 처리 매핑

| 화면 ID | 주요 예외 | 관련 오류 코드 | 처리 방식 |
| --- | --- | --- | --- |
| S-003 | 지원하지 않는 파일 형식 | `FILE_NOT_SUPPORTED` | ADR-0045 기본 메시지 + 허용 확장자 안내 |
| S-003 | 파일 크기 초과 | `FILE_SIZE_EXCEEDED` | ADR-0045 기본 메시지 + 50MB 이하 파일 업로드 안내 |
| S-003 | 파일 손상 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 재업로드 안내 |
| S-004 | 이미 분석 중 | `REVIEW_ALREADY_RUNNING` | ADR-0045 기본 메시지 + 기존 분석 진행 상태 안내 |
| S-005 | 분석 실패 | `REVIEW_FAILED` | ADR-0045 기본 메시지 + 재분석 버튼 표시 |
| S-006 | 기준자료 부족 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + “기준자료 확인 필요” 표시 |
| S-007 | 파일 미리보기 실패 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 원본 파일 확인 안내 |
| S-007 | OCR 좌표 없음 | `OCR_FAILED` | ADR-0045 기본 메시지 + ADR-0051 기준 `LIST_ONLY` 또는 `UNAVAILABLE` 표시 |
| S-008 | 근거 없음 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + 확인 필요 표시 |
| S-009 | 추천 문구 없음 | `STANDARD_NOT_FOUND` | ADR-0045 기본 메시지 + 담당자 직접 검토 안내 |
| S-010 | 질문 범위 불명확 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 상품군/광고유형 선택 안내 |
| S-011 | 검토 결과 없음 | `NOT_FOUND` | ADR-0045 기본 메시지 + 초안 생성 제한 |
| S-012 | 리포트 생성 실패 | `INTERNAL_ERROR` | ADR-0045 기본 메시지 + 재시도 안내 |
| S-013 | 수정본 파일 오류 | `FILE_READ_FAILED` | ADR-0045 기본 메시지 + 수정본 재업로드 안내 |
| S-014 | 기준자료 중복 | `CONFLICT` | ADR-0045 기본 메시지 + 기존 기준자료 확인 안내 |
| S-015 | 정답 데이터 부족 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 담당자 판단 입력 요청 |
| S-016 | 평가 대상 없음 | `BAD_REQUEST` | ADR-0045 기본 메시지 + 검증 데이터셋 선택 안내 |
| S-017 | 권한 없음 | `FORBIDDEN` | ADR-0045 기본 메시지 + 접근 제한 안내 |

---

# 8. 결론

본 화면-API 매핑표는 화면설계서의 주요 화면과 API 명세서의 엔드포인트를 연결한 개발 연계 문서이다.

핵심 흐름은 다음과 같다.

1. `S-003 광고물 등록`에서 `/advertisements` API 호출
2. `S-004 AI 검토 요청`에서 `/advertisements/{advertisementId}/reviews` API 호출
3. `S-005 검토 진행 상태`에서 `/reviews/{reviewId}/status` API 호출
4. `S-006 검토 결과 요약`에서 `/reviews/{reviewId}/summary` API 호출
5. `S-007 광고 화면 검토 UI`에서 `/reviews/{reviewId}/annotations` 및 `/files/{fileId}/preview` API 호출
6. `S-008 상세 검토 결과`에서 `/reviews/{reviewId}/items` API 호출
7. `S-009 문구 추천`에서 `/reviews/{reviewId}/suggestions` 및 `/suggestions/{suggestionId}/decision` API 호출
8. `S-012 검토 리포트`에서 `/reviews/{reviewId}/reports` 및 `/reports/{reportId}/download` API 호출
9. `S-015~S-016`에서 PoC 검증 데이터셋과 KPI 평가 API 호출

이 문서를 기준으로 후속 단계에서는 **OpenAPI 3.0 명세**, **DB 설계서**, **화면별 Request/Response 상세 정의**, **테스트 케이스**를 작성하면 된다.

## 로컬 자동심의 어댑터 연결 (2026-09-06)

제품 OpenAPI는 유지하며 loopback 시연 모드에서만 아래 보조 API를 추가한다.
모든 보조 API는 기존 access token 인증을 사용하고 광고·검토별 접근 권한을 재확인한다.

| 화면 | 요청 | 실행 경계 |
| --- | --- | --- |
| S-004 | GET /api/v1/operational/capabilities | 고객용 상세 상품군 선택지 조회; 내부 템플릿 ID 비노출 |
| S-004 | PUT /api/v1/operational/advertisements/{id}/routing | 사용자 선택 상세 상품군 저장 후 내부 템플릿 자동 연결 |
| S-004 | 기존 POST /api/v1/advertisements/{id}/reviews | 광고 원본 파싱부터 정본 RAG 비동기 실행 접수 |
| S-005 | 기존 status/events·rerun | 실제 작업 단계·실패·재분석. 복수 파일 묶음은 성공 자산 보존 후 실패 자산만 단독 1회 재시도 |
| S-006 | 기존 summary/items/annotations | 저장된 실제 판정 투영 |
| S-006 | GET /api/v1/operational/reviews/{id}/execution | 처리 시간·자동판정/보류 건수 및 제외 사유 |
| S-006 (선택) | PUT /api/v1/operational/reviews/{id}/decision | 준법 담당자의 `APPROVED|REJECTED` 최종 결정을 AI 결과와 별도 불변 기록; 기본 PoC UI에서는 비노출 |

새 작업의 routing은 접수 시 동결한다. 이후 광고 설정 변경이 실행 중 작업을 바꾸지 않는다.

시연 모드는 기존 API 계약을 바꾸지 않고 화면 노출만 줄인다. 일괄 등록은 광고별 카드마다 기존 광고 등록 API를
한 번씩 호출하며, 같은 카드의 광고 원본 여러 개는 동일 `advertisementId`의 자산으로 전송한다. 카드별
등록→routing→intake→review 순서는 유지하되 서로 다른 카드는 병렬로 요청한다. 부분 실패 시 성공 카드는
재전송하지 않고 실패 카드만 화면에 보존한다. 상품군·상세 상품군·광고유형은 각 카드의 독립 입력이다.
실행기가 아직 사용하지 않는 채널·관련 문서·추가 첨부·메모 입력은 시연 화면에서 제공하지 않는다.
검토 요청은 전체 검토유형과 v2 기준을 고정 전송한다. 등록 단계에서 사용자가 선택한
`product_classification_code`를 보조 routing API에 저장하고 서버가 내부 `template_id`를 자동 연결한다.
결과 조회는 단일 workspace 화면으로 모으며 규칙별 `rule_basis`와 `decision_trace`를 투영한다.
Q&A·리포트·비교 API는 시연 흐름에서 호출하지 않는다. 사람 최종 결정은 실행 완료 후에만 허용하고
저장 뒤 수정하거나 AI 판정값을 덮어쓰지 않는다.


## 2026-09-16 운영 결과의 커버리지와 판정 출처 표시 연결

운영 workspace의 template_coverage를 선택 템플릿 처리 현황에 연결한다. rows[].judgment_scope=TEXT_ONLY는 텍스트 의무 범위만 표시한다. reading_quality_review는 시스템 보류 사유, model_assessment는 저장 감사에서 읽은 미채택 모델 판단이다. evidence_location_status는 원문 geometry 누락과 인용 연결 미완료를 구분하며 좌표를 추정 생성하지 않는다. 기존 결과·JSON 내보내기도 동일한 읽기 전용 투영을 사용한다.

설명의 적용성 미확정과 미해당 상태가 모순인 excluded_candidates는 공통 투영에서 rows의 판단불가로 드러낸다. model_assessment.status=WITHHELD_BY_APPLICABILITY_GUARD로 원래 모델 상태·사유를 보존한다. 확인된 미해당은 계속 제외하고, 원본 source_ads 및 저장 실행물은 변경하지 않는다.

## 등록일과 인용 전달

광고 created_at → 한국 날짜 review_date → advertisement_registration_date 출처 → 동결 RAG 입력/모델 입력 순서로 전달한다. review.requested_at은 재검토 수행 시각이며 심의 기준일을 변경하지 않는다. 직접 관찰한 충족·위반은 정확한 줄이 제공되면 evidence_line_refs를 필수로 반환하며 화면과 내보내기는 같은 저장 결과를 투영한다.

## 템플릿 출처와 근거 불일치 투영

workspace 각 행은 template_section 및 template_requirement를 원본 template_basis에서 전달한다. 클라이언트가 XML 경로에서 상품 유형을 추정하지 않는다. WITHHELD_BY_GROUNDING_GUARD는 저장 결과의 인용 불일치에 대한 표시 보류이며 원래 모델 설명과 구분한다. evidence_locations=[]는 다른 문구의 유사도 bbox로 대체하지 않는다.

## 연구원 피드백: 판정 기준 출처 표시 — 2026-09-16

판정 기준에는 내부 C/D/R/T/TPL ID·규제목록 버전·XML 위치를 표시하지 않고 법령/규정/기준명 및 조문번호를 출처별 줄바꿈으로 표시한다. 세미콜론/줄바꿈으로 묶인 출처를 분리하고 조문 뒤 괄호 설명을 제외한 표시 문자열이 같은 경우에만 중복 제거한다. 제16조 제1항 제4호와 제16조 제1항 4처럼 표기가 다른 출처는 동일 조항으로 추측해 통합하지 않고 병렬 표시한다. 명칭 내부 괄호와 서로 다른 조문은 보존한다. 내부 템플릿의 이름·상품 구분·필수 여부와 조문 미연결 안내는 유지한다. 항목 카드 제목의 추적용 ID와 원본 API/export의 rule_basis는 변경하지 않는다.

분류는 화면 표현 개선이며 규정 해석·검색·판정 로직 변경이 아니다. 합성 표시 회귀에서 표기 차이 보존, 완전 중복 제거, 내부 참조 제거, 서로 다른 조문·괄호 포함 기준명 보존과 입력 불변을 확인한다. 실제 브라우저에서 출처 항목의 줄바꿈과 내부 ID 미표시를 확인한다. 광고·모델 재실행은 하지 않는다.

## 사용자 결정: 결과 3종·사람 확인 통합·후보 실행 제한 제거 — 2026-09-16

메인 결과는 위반·판단불가·충족만 표시한다. 다른 템플릿 소속 항목은 목록·집계에서 제외하고 원저장 감사만 유지한다. 실제 NOT_APPLICABLE은 적용 제외 내역(excluded_rows)에 사유와 함께 보존하며 메인 카드·필터에 미해당을 두지 않는다. 적용성 미확정인 추가 v2 후보와 시인성/외부 자료/구조 확인은 모두 판단불가 목록·집계에 포함한다. 동일 scope/item의 보류는 중복 집계하지 않는다. 텍스트 충족에 필수 사람 확인이 남으면 전체 판단불가로 표시하고 자동 텍스트 결과를 automated_assessment에 보존한다. 이미 확인된 위반은 유지하며 남은 확인 사유를 함께 표시한다.

후보 개수 상한으로 규칙을 자르던 과거 방식은 사용하지 않는다. 현행 실행기는 출처 승인 티어로 정식 범위를 먼저 정해 `TEMPLATE_PRIMARY`, `MEDIA_CONDITIONED_V2`, 원문 결합·검색 발동형 `PRODUCT_CONTENT_CONDITIONED_V2`와 관계 의존 규칙을 판정한다. 시인성 규칙은 검색 후보와 근거를 유지하되 사람 검토로 보낸다. 나머지 `MAPPED_V2`, `GENERAL_V2_PRESENCE`, `SUPPLEMENTAL_V2`는 기존 역할에 따라 보강·평가 또는 발견 감사 후보로 보존한다. 용도가 사라진 `prohibition_max_candidates` 설정과 CLI는 제거했으며, 동시 실행 수·요청 배치 크기·reranker 범위는 처리 순서와 자원 관리에만 사용한다. 처리 실패를 충족·미해당·정상 완료로 숨기지 않는다.

workspace/export에 excluded_rows와 execution_omissions를 추가하며 review_candidate_rows/deferred_rules는 빈 호환 배열로 유지한다. 사람 확인은 manual_review_reasons와 실제 점검 제목/질문을 반환한다. 과거 파일에 제목이 없으면 검토 시 동결한 SHA와 동일한 규정 파일 및 저장 템플릿 카탈로그에서 표시 메타데이터만 보충한다. 버전 불일치면 현재 규정으로 바꾸지 않는다. 원저장·모델 판정·source_results는 변경하지 않는다. 과거 후보 실행 누락이 있다면 판단불가와 재처리 필요 경고로 드러내며 자동 완료로 표시하지 않는다.

양성/음성/경계 회귀는121개 검색 후보 보존, 미선택 제외, 사람 확인/적용성 미확정 통합, 위반 유지, 텍스트 충족 보류, 중복 제거, 상품별 scope 분리, 실제 미해당 별도 내역, 옛 실행 누락 경고, 원본 불변, 동결 출처 해시 일치/불일치를 포함한다. 광고 전체 재심의·모델 호출 없이 저장 결과를 대조한다.

## 결과 제목의 식별자 표시 — 2026-09-17

운영 결과 화면은 workspace의 title을 제목으로 사용하고 item_id를 제목·처리 실패 안내에 노출하지 않는다. item_id/row_id는 React 키·원본 위치 연결·API/export 추적에 그대로 사용한다. API 경로·응답 필드·저장 결과는 변경하지 않는다.

## 저장 결과의 판독 불확실성 재검증 — 2026-09-17

workspace와 JSON 다운로드는 같은 saved_workspace 경로에서 저장된 요청의 판독 상태와 규칙별 원문 범위를 사용한다. OBSERVED로 잘못 분류된 명시적인 누락 주장도 판독이 불완전하면 판단불가로 보류하며, 철회한 근거 좌표는 표시하지 않는다. 기존 보류 전 모델 판단에 원래 판정·사유를 남긴다. 원본 결과 파일·상태 데이터와 API 스키마는 변경하지 않는다. 독립적으로 검증되는 산술 위반은 유지한다.

## 로컬 운영 화면 추가 매핑 — 2026-09-18

| 화면 동작 | API/필드 | 비고 |
|---|---|---|
| 루프백 자동 세션 | `GET /api/v1/auth/local-session` | 로컬 운영 서버 전용, 배포/외부 요청 404 |
| 검색 청크 표시 | workspace `rows[].chunk_locations` | `evidence_locations`와 구분한 표시용 좌표 |
| 결과 JSON 다운로드 | `GET /api/v1/operational/reviews/{reviewId}/export.json` | 로컬 401 시 자동 세션 갱신 후 1회 재시도 |
