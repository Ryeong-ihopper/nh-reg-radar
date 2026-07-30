# nh-reg-radar

금융 광고심의 근거 규정 수집 · 조문 단위 개정 감지.

**변경 감지 대상은 자동 수집이 가능한 자료로 한정한다.** 발행 기관이 버전 식별자를
제공하지 않아 개정 여부를 확실히 판별할 수 없는 자료는 수동 관리로 분류하고,
변경 감지 파이프라인과 조회 화면에서 제외한다.

```
$ python src/check_updates.py
[변경] 금융소비자 보호에 관한 법률 시행령
   added     부칙11     바뀐 글자 40/41자 (97.6%)
   modified  제43조     바뀐 글자 389/789자 (49.3%)
   modified  [별표0002] 바뀐 글자 351/1258자 (27.9%)
```

## 수집 대상

| 출처 | 건수 | 방식 | 변경 감지 키 |
|---|---:|---|---|
| 국가법령정보센터 — 법령 | 20 | Open API | `일련번호\|시행일자\|공포번호` |
| 국가법령정보센터 — 행정규칙 | 18 | Open API (필드명 상이) | 〃 |
| 금융투자협회 | 2 | 웹 엔드포인트 + HWP 첨부 | `seq\|historySeq` |
| 여신금융협회 | 2 | HWP 첨부 (세션·토큰) | 파일 sha256 |
| 전국은행연합회 | 1 | HWP 첨부 (세션·토큰) | 파일 sha256 |

규모: 조문 4,473 · 부칙 1,113 · 별표 465 · 첨부 831개(76MB)

어댑터 공통 인터페이스: `current_meta(name, kind)` / `_version_key(meta)` / `collect(name, kind)`

정부기관 게시판(금융위·금감원) 어댑터 `gov_scraper.py` 는 구현돼 있으나 등록 대상이 없다.
게시판은 버전 식별자를 발급하지 않아 개정판 첨부 이름이 달라지면 놓치기 때문이다.

## 요구사항

| | 용도 | 없으면 |
|---|---|---|
| Python 3.10+ | | |
| **JRE 17+** | `document-processor` (표 구조 복원) | 수집 실패 |
| **`LAWGO_OC`** | 법제처 Open API ID — [open.law.go.kr](https://open.law.go.kr) 무료 | 실행 중단 |
| LibreOffice + [H2Orestart](https://github.com/ebandal/H2Orestart/releases) | 뷰어에서 HWP 표시 (선택) | HWP 미표시 |

```bash
setx LAWGO_OC 발급받은아이디        # Windows
export LAWGO_OC=발급받은아이디       # macOS/Linux

pip install -r requirements.txt
python src/file_text.py             # 자바·파서 동작 확인
python src/check_updates.py         # 첫 수집 (20~40분)
```

## 명령

| 명령 | 동작 |
|---|---|
| `src/check_updates.py` | 감지 → 변경분 재수집 → DB 적재 → 품질 점검 |
| `src/check_updates.py --dry` | 감지만 |
| `src/check_updates.py --deep` | 본문 해시까지 비교 (버전 동일, 내용만 수정된 경우) |
| `src/check_updates.py --only "여신"` | 이름 부분일치 대상만 (실패분 재시도) |
| `src/quality_check.py` | 수집 품질 점검 |
| `src/build_review.py` | 원본 대조 화면 → `output/_review/review.html` |
| `uvicorn api:app` | 조회 API → `/docs` (`PYTHONPATH=src`) |
| `tools/discover_targets.py` | 대상 추가 전 공식 명칭 조회 |
| `tools/validate_outputs.py --live` | 수집 결과 ↔ 공식 원문 대조 |

대상 추가는 `targets.json`. 명칭은 `tools/discover_targets.py`로 조회한 값을 쓸 것
(「표시ㆍ광고의 공정화에 관한 법률」의 구분자는 `·` 이 아니라 `ㆍ`).

## 구조

```
targets.json                수집 대상 목록
src/                        파이프라인
  check_updates.py            전체 흐름
   ├─ law_scraper.py            법제처 (법령 + 행정규칙)
   ├─ kofia_scraper.py          금융투자협회
   ├─ crefia_scraper.py         여신금융협회
   ├─ kfb_scraper.py            전국은행연합회
   ├─ gov_scraper.py            정부기관 게시판 (금융위·금감원)
   ├─ name_match.py             이름으로 문서를 고르는 공통 규칙
   ├─ file_text.py              HWP/PDF → 텍스트 (표 보존 + 이미지 추출)
   ├─ diff_report.py            조문 단위 비교
   ├─ quality_check.py          수집 품질 점검 (첨부 추출 상태 포함)
   └─ ingest / store / db       SQLite 적재
  build_review.py             원본 대조 화면
  api.py                      조회 API
tools/                      개발·검수 보조 (파이프라인이 import 하지 않음)
tests/                      네트워크 없이 도는 검증 스크립트
deploy/                     Dockerfile · k8s · PostgreSQL 스키마 · 배치 실행 스크립트
output/                     *.json  *.txt  files/(첨부)  files/*/_img/(이미지)
                            _versions/  _reports/  regulations.db  _review/review.html
```

`src/` 안의 모듈은 서로 평면 import 한다. `tools/` `tests/` 는 상단에서 `sys.path` 에
`src/` 를 넣고 실행한다.

## 구현 노트

**조문 번호를 diff 키로 사용.** 위치 기반(N번째 조문)이면 조문 삽입 시 뒤가 밀려
오탐이 발생한다(실측 456건). 한국 법령은 가지번호(제80조의2)를 쓰므로 번호가 안정적이다.
부칙 내부 조문은 공포번호·날짜 접두로 구분한다 (`부칙제31553호:제2조`).

**글자 단위 diff.** 줄 단위면 120자 중 3자 변경에도 줄 전체가 표시된다.
변경 구간만 추출해 한 사례에서 9,804자 → 118자.

**이름으로 문서를 고를 때의 함정.** 「…규정」 ⊂ 「…규정 시행세칙」이라 부분일치로 첫
후보를 집으면 규정 자리에 시행세칙이 조용히 들어온다. 이름 길이 비교도 안전하지 않다
(원본에 수식어가 붙으면 역전). `name_match.py` 가 **다른 등록 대상의 이름**까지 보고
귀속을 가린다.

**표 구조 보존, 폴백 없음.** 첨부의 64%가 표를 포함하고, 별표·별지는 표가 곧 내용이다.
표를 행·열로 복원하는 경로는 `document-processor`뿐이라 필수 의존으로 두고,
불가 시 폴백 없이 실패시킨다. 단 파서가 특정 도형 구조에서 죽는 경우가 있어
LibreOffice PDF 변환 우회로를 예외 경로로 둔다.

**이미지.** OCR 미지원. `files/*/_img/`에 파일로 저장하고 본문에는 내용 해시 줄을 남긴다
(그림 변경 → 해시 변경 → diff 검출).

**품질 점검**(`quality_check.py`, 매 수집 후 자동)이 검출한 사례:
조문 1개로 수집되던 규정(본문을 35만 자 단일 문자열로 제공 → 605개로 분리),
다운로드 실패 시 0바이트 파일 잔존, 조문 인용을 조문 시작으로 오인(중복 20건),
협회 별표 143개 내용 누락(68만 자).

**응답 절단 대응.** 금투협은 3회 중 1회꼴로 ~32KB에서 응답이 끊긴다.
문서 종료 태그를 확인하고 아니면 재요청한다(절단분 파싱 시 대량 삭제로 오탐).

## 뷰어

`src/build_review.py` → `output/_review/review.html` (단일 파일, 오프라인)

좌: 공식 원본(웹페이지 또는 첨부) / 우: 수집 결과. 조문 단위 대조.
조문·부칙·별표 점프, 동기 스크롤, 삭제 별표 회색 표시, 변경 내역 탭.

원본은 매번 다시 받지 않고 **수집 결과의 버전키를 키로 캐시**한다
(`output/_review/_viewcache.json`). 버전키가 그대로면 원본도 그대로다.
전체 재생성이 8~12분에서 3초로 줄었다.

## 제약

- API 인증 없음 — 로컬 전용
- SQLite 단일 노드 — 다중 접속 시 `deploy/sql/regulation_schema.sql`(PostgreSQL)로 이전
- Dockerfile / k8s 매니페스트 미검증
- `output/_versions` 보관 세대 제한 없음
- OCR 미지원
