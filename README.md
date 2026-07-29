# 금융 광고심의 근거 법령·규정 수집 및 변경 감지

금융 광고심의에 필요한 법령·협회 규정을 자동으로 수집하고, 개정되면 **어느 조문이
어떻게 바뀌었는지**까지 찾아내는 파이프라인.

수집 대상 8건 — 법제처 4건(법률·시행령·감독규정·시행세칙), 협회 4건(금융투자협회 1,
여신금융협회 2, 전국은행연합회 1).

---

## 시작하기

### 1. 사전 준비 (둘 다 필수)

**① 자바 런타임 JRE 17 이상**

HWP·PDF에서 **표를 행·열 그대로** 뽑는 `document-processor`가 자바 기반이다.
자바가 없으면 수집이 **실패한다**(예전엔 조용히 품질 낮은 파서로 넘어갔으나,
표가 깨진 데이터가 쌓이는 게 더 위험해서 실패하도록 바꿨다).

```bash
java -version          # 17 이상이면 OK
```
없으면 https://adoptium.net 에서 설치 후 `JAVA_HOME` 설정.

**② 법제처 Open API 아이디**

https://open.law.go.kr 에서 무료 발급(이메일 앞부분이 아이디가 된다).

```bash
setx LAWGO_OC "발급받은아이디"      # Windows
export LAWGO_OC=발급받은아이디       # macOS/Linux
```
설정하지 않으면 개발자 개인 아이디로 호출되므로 **회사에서 쓸 때는 반드시 발급받을 것.**

### 2. 설치

```bash
pip install -r requirements.txt
python file_text.py                  # 자바·파서 정상 동작 확인
```

### 3. 첫 수집

```bash
python check_updates.py              # 8건 수집 (10~20분, 외부 사이트 접속)
```

---

## 자주 쓰는 명령

| 명령 | 하는 일 |
|---|---|
| `python check_updates.py` | 변경 감지 + 변경분만 재수집 + DB 적재 |
| `python check_updates.py --dry` | 감지만 (아무것도 바꾸지 않음) |
| `python check_updates.py --deep` | 본문 해시까지 비교(버전은 같은데 내용만 손본 경우 검출) |
| `python check_updates.py 은행` | 이름에 '은행'이 든 대상만 — **실패분 재시도용** |
| `python build_review.py` | 검수 화면 생성 → `output/_review/review.html` |
| `python validate_outputs.py --live` | 수집 결과를 공식 원문과 대조 |
| `run_api.bat` | 조회 API 실행 → http://localhost:8000/docs |

테스트: `test_pipeline_db.py` `test_api.py` `test_admrul_split.py`
`test_content_hash.py` `test_resilience.py`
(수집 결과가 필요한 테스트는 없으면 안내 후 건너뛴다)

---

## 구조

```
targets.json          수집 대상 목록 (여기에 추가하면 대상이 늘어남)
     ↓
check_updates.py      ★ 전체 흐름의 중심
     ├─ law_scraper.py      법제처 (법령 + 행정규칙)
     ├─ kofia_scraper.py    금융투자협회 (웹 스크래핑)
     ├─ crefia_scraper.py   여신금융협회 (HWP 첨부)
     ├─ kfb_scraper.py      전국은행연합회 (HWP 첨부, 세션+토큰 필요)
     ├─ file_text.py        HWP/PDF → 텍스트 (표 구조 보존)
     ├─ diff_report.py      조문 단위 비교
     └─ ingest.py / store.py / db.py   SQLite 적재
     ↓
output/               결과물 (.json/.txt), files/(원본첨부),
                      _versions/(이전 버전), _reports/(리포트·로그),
                      regulations.db, _review/(검수 화면)
```

**코드를 처음 볼 때 순서**: `check_updates.py` → `law_scraper.py` →
`diff_report.py` → (필요하면) `ingest.py`. 이 넷이 로직의 90%.

---

## 변경 감지 방식

버전이 바뀌었는지 판단하는 기준이 출처마다 다르다.

| 출처 | 기준 | 이유 |
|---|---|---|
| 법제처 | `일련번호\|시행일자\|공포번호` | 공식 버전 정보를 제공 |
| 금융투자협회 | `seq\|historySeq` | 개정마다 새 이력번호 발급 |
| 여신협·은행연 | 원본 **파일 해시** | 버전 정보가 없음. 같은 게시글에서 첨부만 바뀌어도 잡아야 함 |

평소엔 버전 정보만 확인하고(본문 미조회), `--deep`일 때만 본문까지 비교한다.

**변경 시**: 기존 결과를 `output/_versions/<규정명>/<이전버전>/`로 옮기고 새로 수집한다.
**옛 자료는 지우지 않는다.**

---

## 운영 시 알아둘 것

- **협회 사이트는 간헐적으로 접속이 실패한다** (금투협은 실측 3회 중 1회).
  실패는 리포트뿐 아니라 **알림으로도** 남으므로 반드시 확인할 것. 실패분만
  다시 돌리려면 `python check_updates.py <규정명 일부>`.
- **중복 실행은 자동으로 차단**된다(`.run.lock`). 30분 넘게 남아 있으면 죽은
  프로세스로 보고 무시한다.
- `state.json`은 임시파일→교체 방식으로 저장하고 `.bak`을 남긴다. 손상되면
  자동 복구한다.
- 로그는 `output/_reports/app.log` (5MB × 5개 로테이션). 배치 실행은
  `cron.log`에도 남는다.

## 아직 안 된 것

- **API 인증 없음** — 로컬 전용. 외부 공개 전 반드시 추가할 것
- **SQLite 단일 노드** — 다중 접속이 필요하면 `sql/regulation_schema.sql`의
  PostgreSQL 스키마로 이전(테이블·컬럼명을 동일하게 맞춰둠)
- **Dockerfile / k8s 매니페스트는 미검증** — 배포처가 정해지지 않아 작성만 해둠
- **`output/_versions` 보관 세대 제한 없음** — 개정이 쌓이면 용량 증가
