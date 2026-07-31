# -*- coding: utf-8 -*-
"""
규정 원본 vs 파싱결과 로컬 비교 뷰어 생성기.

output/_review/review.html 하나를 만든다 (더블클릭으로 브라우저에서 바로 열림,
서버·인터넷 연결 불필요 — 데이터가 파일 안에 전부 내장됨).

좌측 = "원본 화면" 이 기본:
  - law/admrul/kofia : 실제 공식 웹페이지를 iframe 으로 그대로 띄움
  - crefia/kfb(+ 별표 PDF) : 다운로드해둔 원본 파일 자체를 <embed> 로 띄움
    (PDF만 가능. 같은 이름 PDF 가 있는 HWP 는 내려받기 안내, 없는 HWP 만 변환해 표시)
  텍스트 검색이 필요하면 좌측 상단에서 "📝 텍스트 추출"로 전환 가능
  (law/admrul=API 원본 JSON, kofia=원본 HTML, crefia/kfb=최종 결과와는 별개로
   구현된 폴백 추출기(olefile 직접 파싱/pdfplumber) 결과 — 교차검증용).
우측 = 우리 파서 최종 결과 (output/<name>.txt), 고정.

원본은 이미 수집해둔 로컬 산출물이 아니라, 재실행 시 law.go.kr·KOFIA 는 라이브로
다시 조회한다 (CREFIA/KFB 는 이미 받아둔 첨부파일만 쓰고 재다운로드는 안 함 —
세션/암호화 체인을 불필요하게 다시 타지 않기 위함).
"""
import os
import re
import sys
import json
import hashlib
import html as htmllib
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

import law_scraper
import kofia_scraper
import file_text
import build_diff_view          # '변경 내역' 탭 데이터·렌더러 재사용
import hwp_pdf                  # PDF 짝이 없는 HWP 만 변환
from diff_report import _ART

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
REVIEW_DIR = os.path.join(OUT_DIR, "_review")

EMBEDDABLE_EXT = (".pdf",)   # 브라우저 <embed> 로 바로 띄울 수 있는 확장자


def _safe(name):
    return law_scraper._safe(name)


def _read_final_txt(name):
    p = os.path.join(OUT_DIR, _safe(name) + ".txt")
    if not os.path.exists(p):
        return "(파싱 결과 없음 — collect() 먼저 실행 필요)"
    return open(p, encoding="utf-8").read()


def _stats(name):
    p = os.path.join(OUT_DIR, _safe(name) + ".json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    return d.get("통계", {})


def _rel(fpath):
    return os.path.relpath(fpath, REVIEW_DIR).replace("\\", "/")


def _flat(v):
    """API 값이 문자열/리스트/중첩리스트로 오는 것을 문자열로 편다(내용 변경 없음)."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "\n".join(x for x in (_flat(i) for i in v) if x)
    if isinstance(v, dict):
        return str(v.get("content", ""))
    return str(v)


# 원본 텍스트(JSON/HTML) 안에서 '조문이 정의된 줄'만 골라내는 패턴.
# 인용(제7조제1항, 제7조에 따라)이 아니라 정의(제7조(목적), 제7조 삭제)만 잡는다.
_DEF_IN_RAW = re.compile(
    r"제\s*\d+(?:-\d+)?조(?:의\s*\d+)?(?=\s*[(（]|\s*삭제|\s*<)")


def raw_line_index(raw_text, kind):
    """원본 텍스트에서 각 조문이 **실제로 정의된 줄 번호**를 찾아 색인한다.

    좌측을 따로 가공해 보여주면 결국 파싱 결과와 같은 것을 두 번 보는 셈이라
    대조 의미가 없다. 그래서 원본(JSON/HTML)은 그대로 두고, '이 조문이 원본
    몇 번째 줄에 있는지'만 미리 계산해 정확히 찾아갈 수 있게 한다.
    """
    out, seen = [], {}
    for lineno, line in enumerate(raw_text.splitlines()):
        # JSON 은 "조문내용": "제7조(...)" 형태, HTML 은 <td> 제7조(...) 형태.
        # 어느 쪽이든 값이 조문 정의로 시작하는 줄만 헤더로 인정한다.
        m = _DEF_IN_RAW.search(line)
        if not m:
            continue
        before = line[:m.start()]
        # 값의 앞부분(따옴표/태그/공백/필드명)만 있어야 정의로 본다.
        # 문장 중간에 인용된 경우는 앞에 한글 본문이 길게 붙어 있으므로 걸러진다.
        if len(re.sub(r'[\s"><\[\]{},:]|조문내용|항내용|호내용|목내용|부칙내용|&nbsp;', "", before)) > 4:
            continue
        label = m.group(0).replace(" ", "")
        seen[label] = seen.get(label, 0) + 1
        out.append({"label": label, "line": lineno, "n": seen[label]})
    return out


def _files_in(name):
    d = os.path.join(OUT_DIR, "files", _safe(name))
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in sorted(os.listdir(d))]


def _fallback_text(fpath):
    """최종 결과(document-processor)와 무관하게 구현된 폴백 추출기로 교차검증용 텍스트 생성."""
    ext = os.path.splitext(fpath)[1].lower()
    try:
        if ext == ".hwp":
            return file_text.extract_hwp(fpath) or "(olefile 폴백 추출 실패/빈 결과)"
        if ext == ".pdf":
            return file_text.extract_pdf(fpath)
    except Exception as e:
        return f"(폴백 추출 실패: {e})"
    return "(이 확장자는 교차검증용 폴백 추출기가 없음 — 원본 파일을 직접 확인)"


# 삭제된 별표는 파일이 지워지지 않고 "<별표 1> <삭제 2012.12.27.>" 한 줄짜리 껍데기로 남는다
# (금투협 규정 별표 21개 중 11개). 파일명만으로는 알 수 없어 열어봐야 하는데, 목록에서
# 바로 보이도록 미리 판별해 둔다. 결과는 내용 해시로 캐시해 다시 열지 않는다.
_DEL_CACHE_PATH = os.path.join(REVIEW_DIR, "_deleted.json")
_del_cache = None
# 껍데기 판정: 본문이 짧고 그 안에 삭제 표기가 있는 경우만.
# 살아 있는 별표에도 "…삭제한다" 같은 말이 나오므로 길이 제한이 오탐을 막는다.
_DEL_MARK = re.compile(r"삭제\s*[<(]?\s*\d{4}|[<(]\s*삭제")
_DEL_MAX_BYTES = 64 * 1024      # 껍데기는 예외 없이 작다. 큰 파일은 열지 않는다
_DEL_MAX_CHARS = 120            # 추출 텍스트가 이보다 길면 내용이 있는 것
# 판정 기준(_DEL_MARK/_DEL_MAX_*)을 바꾸면 이 값을 올린다 → 옛 캐시를 자동으로 버린다
_DEL_RULE_VER = 2


def _load_del_cache():
    global _del_cache
    if _del_cache is None:
        try:
            c = json.load(open(_DEL_CACHE_PATH, encoding="utf-8"))
            _del_cache = c if c.get("_ver") == _DEL_RULE_VER else {"_ver": _DEL_RULE_VER}
        except Exception:
            _del_cache = {"_ver": _DEL_RULE_VER}
    return _del_cache


def save_del_cache():
    if _del_cache:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        json.dump(_del_cache, open(_DEL_CACHE_PATH, "w", encoding="utf-8"))


def _is_deleted(fpath):
    """'삭제' 표기만 남은 껍데기 별표인가."""
    if os.path.getsize(fpath) > _DEL_MAX_BYTES:
        return False
    if os.path.splitext(fpath)[1].lower() not in (".hwp", ".hwpx", ".pdf"):
        return False
    cache = _load_del_cache()
    key = hashlib.sha256(open(fpath, "rb").read()).hexdigest()[:16]
    if key in cache:
        return cache[key]
    try:
        txt = (file_text.extract(fpath) or "").strip()
    except Exception:
        cache[key] = False
        return False
    cache[key] = bool(txt) and len(txt) <= _DEL_MAX_CHARS and bool(_DEL_MARK.search(txt))
    return cache[key]


def _file_view(fpath):
    """파일 하나 → 화면 표시 정보.

    HWP 는 브라우저가 못 그린다. 같은 이름의 PDF 가 함께 오는 경우(법제처 별표)는
    그 PDF 가 목록에 별도 항목으로 있으므로 HWP 는 내려받기만 안내하고,
    PDF 가 없는 HWP 만 변환해서 보여준다.
    """
    ext = os.path.splitext(fpath)[1].lower()
    name = os.path.basename(fpath)
    rel, embeddable, converted = _rel(fpath), ext in EMBEDDABLE_EXT, False
    if ext in (".hwp", ".hwpx"):
        # 법제처 별표는 같은 내용을 PDF 로도 준다. 그 PDF 는 **목록에 이미 별도 항목**으로
        # 들어 있으므로, HWP 항목까지 같은 PDF 를 보여줄 필요가 없다 → 내려받기 안내.
        # 반대로 PDF 짝이 없는 HWP 는 변환하지 않으면 화면에서 볼 방법이 아예 없다 → 변환.
        twin = os.path.splitext(fpath)[0] + ".pdf"
        if not os.path.exists(twin) and hwp_pdf.available():
            pdf = hwp_pdf.to_pdf(fpath)
            if pdf:
                rel, embeddable, converted = _rel(pdf), True, True
    return {"name": name, "rel": rel, "ext": ext,
            "embeddable": embeddable, "converted": converted,
            "deleted": _is_deleted(fpath), "orig": _rel(fpath)}


# 좌측 '원본 화면' 데이터 캐시.
#
# build_view 는 대상마다 법제처 API·금투협 웹을 **라이브로 다시 조회**한다. 40개면
# 8~12분이 걸리는데, 대부분은 지난번과 같은 내용을 또 받는 것이다.
# 수집 결과의 버전키가 그대로면 원본도 그대로이므로, 버전키를 키로 캐시한다.
# (버전키가 바뀌었다 = 개정됐다 = 원본을 다시 받아야 한다)
_VIEW_CACHE_PATH = os.path.join(REVIEW_DIR, "_viewcache.json")
_view_cache = None


def _load_view_cache():
    global _view_cache
    if _view_cache is None:
        try:
            _view_cache = json.load(open(_VIEW_CACHE_PATH, encoding="utf-8"))
        except Exception:
            _view_cache = {}
    return _view_cache


def save_view_cache():
    if _view_cache:
        os.makedirs(REVIEW_DIR, exist_ok=True)
        json.dump(_view_cache, open(_VIEW_CACHE_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False)


def _version_of(name):
    """수집 결과에 저장된 버전키. 없으면 None(캐시 안 씀)."""
    p = os.path.join(OUT_DIR, _safe(name) + ".json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    return d.get("버전키") or d.get("본문해시")


def build_view_cached(name, kind):
    """build_view 결과를 버전키 기준으로 캐시해 재사용."""
    ver = _version_of(name)
    cache = _load_view_cache()
    hit = cache.get(name)
    if ver and hit and hit.get("ver") == ver:
        v = hit["v"]
        # 첨부 정보는 파일 상태(변환·삭제 판정)에 따라 달라질 수 있어 매번 다시 만든다
        if v.get("files"):
            v["files"] = [_file_view(p) for p in _files_in(name)]
        return v, hit["raw"], hit["desc"], hit["idx"]
    v, raw, desc, idx = build_view(name, kind)
    if ver:
        cache[name] = {"ver": ver, "v": v, "raw": raw, "desc": desc, "idx": idx}
    return v, raw, desc, idx


def build_view(name, kind):
    """좌측 '원본 화면'용 view 정보 + 텍스트모드용 rawText/rawDesc 반환."""
    if kind in ("law", "admrul"):
        meta = law_scraper.current_meta(name, kind)
        if not meta:
            return ({"mode": "webpage", "url": None, "files": []}, "(검색 실패)", "", [])
        # 법제처 공개 단축 주소(/법령/이름, /행정규칙/이름)를 쓴다.
        # 내부 상세 주소(lsInfoP.do / admRulInfoP.do)를 직접 넣으면 행정규칙은
        # 세션이 없어 "해당 법령이 존재하지 않습니다"가 뜬다. 단축 주소는 바깥
        # 페이지가 세션을 만든 뒤 iframe 으로 본문을 불러오므로 브라우저에서 정상 동작한다.
        seg = "행정규칙" if kind == "admrul" else "법령"
        url = ("https://www.law.go.kr/" + urllib.parse.quote(seg) + "/"
               + urllib.parse.quote(meta["name"].replace(" ", "")))
        body = law_scraper.fetch_body(meta)
        raw_text = json.dumps(body, ensure_ascii=False, indent=2)
        종류 = "행정규칙" if kind == "admrul" else "법령"
        raw_desc = (f"law.go.kr {종류} API 원본 JSON (일련번호 {meta['MST']}) — 필드명·중괄호가 "
                    f"섞여 있지만, 조문 위치를 미리 색인해 두어 점프·동기화는 정확히 동작한다")
        files = [_file_view(p) for p in _files_in(name)]   # 별표/첨부 PDF·HWP
        return ({"mode": "webpage", "url": url, "files": files}, raw_text, raw_desc,
                raw_line_index(raw_text, kind))

    if kind == "kofia":
        found = kofia_scraper._find_in_tree(name)
        if not found:
            return ({"mode": "webpage", "url": None, "files": []},
                    "(검색 실패)", "", [])
        title, seq, hseq = found
        url = f"{kofia_scraper.BODY_URL}?seq={seq}&historySeq={hseq}"
        html = kofia_scraper._get(url)
        desc = (f"law.kofia.or.kr 원본 HTML (seq={seq}, historySeq={hseq}) — 태그까지 "
                f"그대로. 조문 위치는 미리 색인해 두어 점프·동기화는 정확히 동작한다")
        # 금투협 별표는 본문 HTML 에 없고 첨부 HWP 로만 온다 → 파일 목록에 함께 노출
        files = [_file_view(p) for p in _files_in(name)]
        return ({"mode": "webpage", "url": url, "files": files}, html, desc,
                raw_line_index(html, kind))

    # crefia / kfb : 정식 웹페이지가 없고 첨부파일 자체가 규정 원문.
    files = _files_in(name)
    if not files:
        return {"mode": "file", "url": None, "files": []}, "(원본 파일 없음)", "", []
    main = files[0]
    extra = [_file_view(p) for p in files[1:]]
    raw_text = _fallback_text(main)
    desc = (f"⚠ 원본 아님 — 독립 폴백 추출기(olefile/pdfplumber 직접 파싱, document-processor와 "
            f"별개 구현) 결과. 최종 결과와 다르면 원본파일을 직접 여세요 ({os.path.basename(main)})")
    return ({"mode": "file", "url": None, "files": [_file_view(main)] + extra},
            raw_text, desc, raw_line_index(raw_text, kind))


_ADDENDA_ID = re.compile(r"제\s*([\d\-]+)\s*호|(\d{4})\s*[.\s]\s*(\d{1,2})\s*[.\s]\s*(\d{1,2})")
# 심사지침·예규는 조문이 아니라 로마숫자로 나뉜다(Ⅰ. 목적 / Ⅱ. 적용범위 …).
# 이걸 안 잡으면 본문 전체가 점프 목록에서 빠지고 부칙만 남는다.
# 제목만 뽑는다. "Ⅰ. 목적　이 심사지침은 …" 처럼 본문이 바로 이어지므로
# 전각공백·마침표·'이 ' 같은 문장 시작에서 끊는다.
# 로마숫자를 전용 문자(Ⅰ U+2160)로 치는 문서와 라틴 대문자(I U+0049)로 치는 문서가
# 섞여 있다. 한 문서 안에서도 섞인다 — 여신협 세부지침은 첫 항목만 "I. 목 적"(라틴)이고
# 나머지는 "Ⅱ. 정 의"(전용 문자)라, 라틴을 빼면 첫 항목만 목록에서 사라진다.
_ROMAN_HEAD = re.compile(r"^([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+)\s*\.\s*([^　.]{1,20}?)"
                         r"(?=　|\s{2,}|이\s|다음|$|[.·])")
# to_text() 가 만드는 별표 머리글: "[별표 0001] 제목" / "[별표 0001의2] 제목" / "[별표]"
# (번호를 4자리로 채우는 게 우리 형식. 원문 인용 "[별표 1의2]" 와 구분된다)
_TABLE_HEAD = re.compile(r"^\[(?:별표|별지|서식|별책)(?:\s+\d{4}(?:의\d+)?)?\]")
# to_text() 는 별표 머리글 뒤에 원본 파일명을 남긴다: "[별지 0001]  (원본 파일: 0001_(별지 제1호).hwp)"
_TABLE_SRC = re.compile(r"\(원본 파일:\s*(.+?)\)\s*$")


def _table_meta(line):
    """별표 머리글 → (제목, 원본파일명).

    법제처는 머리글에 제목이 붙어 오지만(「광고에 포함해야 하는 사항(제17조제2항 관련)」),
    **금투협은 제목이 비어 있다.** 그러면 점프 목록에 「[별지 0002]」만 남아 93개 중
    어느 것인지 알 수 없다. 파일명에는 정보가 살아 있으므로(0001_(별지 제1호).hwp)
    제목이 없을 때 거기서 가져온다.
    """
    m = _TABLE_HEAD.match(line)
    if not m:
        return "", ""
    rest, fname = line[m.end():].strip(), ""
    fm = _TABLE_SRC.search(rest)
    if fm:
        fname = fm.group(1).strip()
        rest = rest[:fm.start()].strip()
    if not rest and fname:
        stem = os.path.splitext(fname)[0]
        t = re.search(r"\(([^)]+)\)", stem)       # 0001_(별지 제1호) → 별지 제1호
        rest = t.group(1) if t else stem
    return rest, fname


def _addenda_label(line):
    """부칙 헤더 줄 → 목록에 쓸 이름. 헤더가 아니면 None.

    표기가 소스마다 다르다. 공포정보(호수/날짜)가 붙어 있으면 헤더로 본다.
      법제처   부칙 <제5741호,1999.2.1>  ·  부칙(정부조직법) <제5982호,1999.5.24>
      금투협   부 칙 (2026. 5. 22)
      여신협   부칙 (2016.09.30 제정)
      은행연   부칙            ← 공포정보 없음. 그래도 헤더이므로 살린다
    반대로 "부칙 제4조제6항 단서를 삭제한다"(다른 법의 부칙을 고치는 **본문**)는
    조문 인용이므로 걸러야 한다. → 뒤에 서술어가 이어지면 헤더가 아니다.
    """
    # 금투협은 부칙 제목을 대괄호로 감싼다: "[부 칙 (2026. 5. 22)]"
    s = line.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
    body = re.sub(r"^부\s*칙", "", s).strip()
    if not body:
        return "부칙"                     # 은행연처럼 표기가 '부칙' 하나뿐인 경우
    # 헤더는 부칙 바로 뒤에 공포정보가 괄호로 붙는다: <제N호,날짜> 또는 (날짜).
    # 인용은 "부칙 제4조제6항 단서를…" 처럼 조문 번호가 바로 온다.
    if body[0] not in "<(（":
        return None
    m = _ADDENDA_ID.search(body[:80])
    if not m:
        return "부칙"
    if m.group(1):
        return "부칙 제%s호" % m.group(1)
    return "부칙 %s.%02d.%02d" % (m.group(2), int(m.group(3)), int(m.group(4)))


def article_index(text):
    """최종 텍스트에서 조문/별표/부칙 헤더의 '줄 번호'를 찾아 점프 목록 생성.

    문자 위치(pos)로 비율 스크롤하면 줄바꿈이 많은 문서에서 크게 어긋난다.
    줄 번호를 주면 화면에서 해당 줄 요소로 정확히 이동할 수 있다.

    부칙은 개수가 많다(자본시장법 65개). 부칙마다 제1조(시행일)·제2조가 있어서
    그대로 두면 '부칙:제2조'가 85번 반복돼 목록에서 어느 것인지 알 수 없다.
    → **본칙 조문만 목록에 넣고, 부칙은 공포번호/날짜로 하나씩만** 넣는다.
    """
    out = []
    in_addenda = False
    in_tables = False       # 별표 구간에서는 별표 제목만 목록에 넣는다
    lines = text.splitlines()
    for lineno, line in enumerate(lines):
        stripped = line.strip()
        if stripped.replace(" ", "") == "부칙":
            in_addenda = True
            # to_text() 가 넣는 구분선("─── / 부   칙 / ───")은 목록에 넣지 않는다.
            # 반면 은행연처럼 표기가 '부칙' 하나뿐인 소스에서는 이게 진짜 헤더다.
            if lineno and set(lines[lineno - 1].strip()) <= {"─", ""}  \
                    and lines[lineno - 1].strip():
                continue
            out.append({"label": "부칙", "line": lineno})
            continue
        # 별표 구간은 부칙 뒤에 온다. 여기서 풀어주지 않으면 별표가 통째로 빠진다.
        # 구분선 표기가 소스마다 다르다: 법제처 "별표 / 서식", 금투협 "별표 / 별지".
        if re.match(r"^별표\s*/\s*(서식|별지)", stripped) or stripped.startswith("첨부파일"):
            in_addenda = False
            in_tables = True
            continue
        rm = _ROMAN_HEAD.match(stripped)
        if rm and not in_tables:
            # 제목 뒤에 본문이 바로 붙는 경우가 있어 조사/기관명 앞에서 한 번 더 끊는다
            title = re.split(r"(?=공정거래위원회|금융위원회|이\s|다음)",
                             rm.group(2).strip(), maxsplit=1)[0].strip()
            out.append({"label": f"{rm.group(1)}. {title[:20]}", "line": lineno})
            continue
        m = _ART.search(line)
        if not m:
            continue
        # 줄 앞부분에 있는 헤더만 인정(본문 중간의 조문 인용은 제외).
        # 금투협은 "[부 칙 (…)]" 처럼 대괄호로 감싸므로 그것도 앞부분으로 본다.
        head = stripped[1:].lstrip() if stripped.startswith("[") else stripped
        if not (m.start() <= 2 or head.startswith(m.group(0))):
            continue
        # 별표 본문의 "(제2-2조제1항 관련)" 같은 인용은 조문 헤더가 아니다.
        # 조문 헤더는 괄호로 시작하지 않는다.
        if stripped.startswith(("(", "（")):
            continue
        # 별표 안에는 표 내용·인용·별도 기준문서까지 들어 있어 조문처럼 보이는 줄이 많다.
        # 이 구간에서는 to_text() 가 만든 별표 머리글만 목록에 넣는다.
        # 우리 머리글은 번호를 4자리로 채운다("[별표 0001]"). 본문 안에 원문 그대로
        # 실려 있는 "[별표 1의2]", "[별지 제1호]" 는 내용이지 머리글이 아니다.
        if in_tables and not _TABLE_HEAD.match(stripped):
            continue
        extra = {}
        if in_tables:
            title, srcfile = _table_meta(stripped)
            extra = {"table": True, "title": title, "srcfile": srcfile}
        label = (m.group(0) or "").replace(" ", "")
        if label == "부칙":
            lab = _addenda_label(stripped)
            if lab is None:
                continue           # 부칙 헤더가 아니라 본문 중 인용
            label = lab
            # 부칙 헤더를 만난 시점부터 부칙 구간이다. 여기서 켜주지 않으면
            # 여신협처럼 "부칙 (2016.09.30 제정)" 형식인 소스는 구간 인식이 안 돼
            # 부칙 안의 제1조가 목록에 그대로 딸려 나온다.
            in_addenda = True
        elif in_addenda:
            continue               # 부칙 안의 조문은 목록에 넣지 않는다(너무 많다)
        out.append({"label": label, "line": lineno, **extra})
    seen = {}
    for it in out:
        seen[it["label"]] = seen.get(it["label"], 0) + 1
        it["n"] = seen[it["label"]]
    return out


# 별표 첨부 파일명 규칙이 소스마다 다르다.
#   행정규칙  별표0001.pdf · 별표0001의02.pdf · 별지0002.pdf   (가지번호는 2자리로 채움)
#   법령      law0105132025091621061KC_000100E.pdf            (…_번호4자리+가지2자리+E)
#   금투협    0001_(별지 제1호).hwp                            (본문 머리글에 파일명이 적혀 있음)
# 앞의 둘은 (구분, 번호, 가지) 로 정규화해서 맞춘다.
_F_ADMRUL = re.compile(r"^(별표|별지|서식|별책)\s*(\d{1,4})(?:의0*(\d+))?$")
_F_LAW = re.compile(r"_(\d{4})(\d{2})[A-Z]?$")
# 별표가 하나뿐인 규정은 번호 없이 「[별표]」로만 온다. 파일 쪽은 0000 을 쓴다.
_L_TABLE = re.compile(r"^\[(별표|별지|서식|별책)(?:\s*(\d{1,4})(?:의(\d+))?)?\]$")


def _file_key(stem):
    """첨부 파일 이름(확장자 제외) → (구분, 번호, 가지). 규칙에 안 맞으면 None."""
    m = _F_ADMRUL.match(stem)
    if m:
        return (m.group(1), int(m.group(2)), int(m.group(3) or 0))
    m = _F_LAW.search(stem)
    if m:
        return (None, int(m.group(1)), int(m.group(2)))   # 법령 파일명엔 구분이 없다
    return None


def link_table_files(index, files):
    """별표 점프 항목에 좌측에서 열 원본 파일을 연결한다(`fileIdx`).

    별표 검수는 결국 「첨부 원본 ↔ 파싱된 별표 텍스트」 1:1 대조인데, 지금까지는
    좌측 파일 선택과 우측 점프가 따로 놀아 사람이 손으로 짝을 맞춰야 했다.

    구분(별표/별지)이 본문 머리글과 파일명에서 어긋나는 경우가 있다 — 금융투자업규정은
    머리글이 「[별표 0001]」인데 파일은 `별지0001.pdf` 다. 그래서 구분까지 같은 것을
    먼저 찾고, 없으면 번호만으로 찾되 **후보가 하나일 때만** 쓴다(은행업감독규정처럼
    별표0001 과 별지0001 이 둘 다 있는 경우 잘못 짝지으면 안 된다).

    HWP 는 브라우저가 못 그리므로 같은 이름 PDF 가 있으면 그쪽을 가리킨다.
    """
    if not files:
        return index
    by_name = {f["name"]: i for i, f in enumerate(files)}
    by_key = {}                       # (구분,번호,가지) → 파일 인덱스
    by_num = {}                       # (번호,가지) → [파일 인덱스]
    for i, f in enumerate(files):
        k = _file_key(os.path.splitext(f["name"])[0])
        if not k:
            continue
        by_key.setdefault(k, i)
        by_num.setdefault(k[1:], []).append(i)

    def pdf_of(i):
        j = by_name.get(os.path.splitext(files[i]["name"])[0] + ".pdf")
        return j if j is not None else i

    for it in index:
        if not it.get("table"):
            continue
        i = by_name.get(it.get("srcfile") or "")            # 금투협: 머리글에 파일명이 있다
        if i is None:
            m = _L_TABLE.match(it["label"])
            if m:
                num = (int(m.group(2) or 0), int(m.group(3) or 0))
                i = by_key.get((m.group(1), *num))
                if i is None:
                    # 구분이 어긋나거나(별표↔별지) 법령 파일명이라 구분이 없는 경우
                    cand = {pdf_of(x) for x in by_num.get(num, [])}
                    if len(cand) == 1:
                        i = cand.pop()
        if i is not None:
            it["fileIdx"] = pdf_of(i)
    return index


def build():
    targets = json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
    os.makedirs(REVIEW_DIR, exist_ok=True)

    payload = []
    for t in targets:
        name, kind = t["name"], t["kind"]
        print(f"[준비] {name} ({kind})")
        try:
            view, raw_text, raw_desc, raw_index = build_view_cached(name, kind)
        except Exception as e:
            view = {"mode": "webpage", "url": None, "files": []}
            raw_text, raw_desc, raw_index = f"(원본 조회 실패: {e})", "", []
        final_text = _read_final_txt(name)
        payload.append({
            "name": name, "kind": kind,
            "stats": _stats(name),
            "view": view,
            "rawText": raw_text, "rawDesc": raw_desc,
            # 원본 텍스트에서 각 조문이 정의된 줄 번호 (정확한 동기화용)
            "rawIndex": raw_index,
            "final": final_text,
            "index": link_table_files(article_index(final_text),
                                      (view or {}).get("files") or []),
        })

    # 변경 내역 탭: DB에 쌓인 실제 개정을 조문 단위 색상 diff로 함께 싣는다
    try:
        import db
        con = db.connect()
        try:
            changes = build_diff_view.collect_changes(con)
        finally:
            con.close()
    except Exception as e:
        print(f"[경고] 변경 내역을 읽지 못했습니다(대조 탭은 정상): {e}")
        changes = []
    print(f"[준비] 변경 내역 {len(changes)}건")

    # 원본 HTML/텍스트에 "</script>" 가 섞여 있으면 <script> 태그가 중간에
    # 끊기므로 "</"→"<\/" 로 이스케이프해서 심는다.
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    changes_js = json.dumps(changes, ensure_ascii=False).replace("</", "<\\/")
    html = (HTML_TEMPLATE
            .replace("__DIFF_CSS__", build_diff_view.DIFF_CSS)
            .replace("__DIFF_JS__", build_diff_view.DIFF_JS)
            .replace("__CHANGES__", changes_js)
            .replace("__DATA__", data_js))
    out_path = os.path.join(REVIEW_DIR, "review.html")
    # 폴백 추출기가 드물게 깨진 서로게이트를 남길 수 있어 최종 인코딩 단계에서도 방어.
    with open(out_path, "wb") as f:
        f.write(html.encode("utf-8", errors="replace"))
    save_del_cache()
    save_view_cache()
    print(f"\n생성됨: {os.path.relpath(out_path, ROOT)}")
    print("브라우저로 더블클릭해서 열면 됩니다 (인터넷 연결 불필요, 파일 자체가 완결형).")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>규정 원본 vs 파싱결과 비교</title>
<style>
  :root {
    --bg: #f5f6f8; --panel: #ffffff; --border: #d9dde3; --text: #1c2126;
    --sub: #6b7480; --accent: #2563eb; --mark: #fff3a3; --markcur: #ffcf4d;
    /* 점프해서 멈춘 자리. 번쩍이는 순간은 --markcur 로 시작해 이 색으로 가라앉는다.
       계속 떠 있는 색이라 진하면 글자를 읽기 어렵다. */
    --hitrest: #fff2c8;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#14171c; --panel:#1b1f26; --border:#2c323b; --text:#e6e9ee; --sub:#8b93a1; --accent:#6ea8ff; --mark:#5a4a12; --markcur:#8a6a10; --hitrest:#3a300c; }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    background: var(--bg); color: var(--text);
    font-family: -apple-system, "Malgun Gothic", "Segoe UI", sans-serif;
    display: flex; flex-direction: column; height: 100vh; overflow: hidden;
  }
  header {
    padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--panel);
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }
  select { max-width: 340px; }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; white-space: nowrap; }
  select, input, button {
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
  }
  select { min-width: 260px; }
  button { cursor: pointer; }
  button:hover { border-color: var(--accent); }
  #stats { font-size: 12px; color: var(--sub); min-width: 0;
           overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #stats b { color: var(--text); }
  /* 검색창이 좁아 글자가 잘리던 문제: 남는 폭을 받아 늘어나되 최소 폭을 보장 */
  .search-wrap { display: flex; align-items: center; gap: 6px; margin-left: auto;
                 flex: 1 1 320px; min-width: 260px; max-width: 460px; }
  #searchBox { flex: 1 1 auto; min-width: 0; }
  #searchCount { font-size: 12px; color: var(--sub); min-width: 52px; text-align: right;
                 white-space: nowrap; }
  .search-wrap button { flex: 0 0 auto; padding: 6px 9px; }
  main { flex: 1; display: flex; min-height: 0; }
  #jump {
    width: 190px; border-right: 1px solid var(--border); background: var(--panel);
    overflow-y: auto; padding: 8px; flex-shrink: 0;
  }
  #jump h3 { font-size: 11px; color: var(--sub); text-transform: uppercase; margin: 4px 4px 8px; }
  #jump .item {
    display: block; width: 100%; text-align: left; background: none; border: none;
    padding: 5px 8px; font-size: 12.5px; border-radius: 5px; color: var(--text); cursor: pointer;
  }
  #jump .item:hover { background: var(--bg); }
  /* 클릭해서 이동한 항목 / 지금 화면에 보이는 항목 */
  #jump .item.on { background: var(--accent); color: #fff; font-weight: 700; }
  #jump .item.now:not(.on) { background: var(--bg); color: var(--accent); font-weight: 600; }
  /* 최종 결과를 줄 단위 요소로 그린다(정확한 점프용) */
  .pane-body pre .ln { display: block; }
  /* 조문 블록 전체가 아니라 **머리글 한 줄만** 강조한다.
     블록 전체에 bold 를 주면 본문이 통째로 진해져 읽기 어렵다. */
  .pane-body pre .ln.art { scroll-margin-top: 8px; }
  .pane-body pre .ln.art > .h { font-weight: 700; color: var(--text); }
  .pane-body pre .ln.art { border-left: 2px solid var(--border); padding-left: 8px; }
  .pane-body pre .ln.art:hover { border-left-color: var(--accent); }
  .pane-body pre .ln.hit {
    background: var(--hitrest); border-radius: 4px;
    box-shadow: inset 3px 0 0 var(--markcur);   /* 색이 옅어진 만큼 왼쪽에 표시를 남긴다 */
    animation: hitfade 0.85s ease-out;
  }
  /* transparent 로 끝내면 애니메이션이 끝나는 순간 기본값(진한 노랑)으로 되돌아가
     '번쩍 → 사라짐 → 다시 진해짐'이 된다. 가라앉을 색으로 끝내야 한다. */
  @keyframes hitfade { 0% { background: var(--markcur); } 100% { background: var(--hitrest); } }
  .panes { flex: 1; display: flex; min-width: 0; }
  .pane { flex: 1; display: flex; flex-direction: column; min-width: 0; border-right: 1px solid var(--border); }
  .pane:last-child { border-right: none; }
  .pane-head {
    padding: 8px 14px; border-bottom: 1px solid var(--border); background: var(--panel);
    font-size: 12.5px; color: var(--sub); display: flex; align-items: center; justify-content: space-between; gap: 10px;
  }
  /* 어느 쪽이 원본이고 어느 쪽이 파싱 결과인지 색과 라벨로 즉시 구분되게 */
  .side {
    font-size: 12px; font-weight: 800; letter-spacing: .02em; color: #fff;
    padding: 3px 10px; border-radius: 6px; white-space: nowrap; flex-shrink: 0;
  }
  .side.src { background: #6b7280; }          /* 원본 = 회색 */
  .side.out { background: #16a34a; }          /* 파싱 결과 = 초록 */
  @media (prefers-color-scheme: dark) {
    .side.src { background: #4b5563; } .side.out { background: #15803d; }
  }
  .pane.left  .pane-head { border-top: 3px solid #6b7280; }
  .pane.right .pane-head { border-top: 3px solid #16a34a; }
  .src-tag { font-size: 11.5px; font-weight: 700; color: var(--sub);
             border: 1px solid var(--border); border-radius: 5px; padding: 2px 7px;
             white-space: nowrap; flex-shrink: 0; }
  .side-note { font-size: 11.5px; color: var(--sub); overflow: hidden;
               text-overflow: ellipsis; white-space: nowrap; }
  /* 한 줄에 고정. 예전엔 파일마다 칩을 늘어놨는데 금융투자업규정은 159개라
     줄바꿈이 생겨 지저분했다 → 보기는 토글 2개, 대상은 드롭다운으로 고정 폭. */
  .pane-head .left-tools { display: flex; align-items: center; gap: 8px;
                           flex-wrap: nowrap; min-width: 0; flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px;
         overflow: hidden; flex-shrink: 0; }
  .seg .chip { border: none; border-radius: 0; padding: 5px 11px; background: var(--panel); }
  .seg .chip + .chip { border-left: 1px solid var(--border); }
  .seg .chip.active { background: var(--accent); color: #fff; }
  #fileSel { min-width: 0; flex: 1 1 auto; max-width: 340px; font-size: 12.5px;
             padding: 5px 8px; }
  /* 대상 선택은 '웹 화면'에서만 의미가 있다(텍스트 모드는 원본 응답 하나뿐).
     비활성일 때 흐리게 해서 지금 왜 안 먹는지 바로 알 수 있게 한다. */
  #fileSel:disabled { opacity: .4; cursor: not-allowed; }
  .pane-head a, .pane-head button.link { color: var(--accent); text-decoration: none; background: none; border: none; padding: 0; font-size: 12.5px; }
  .pane-head a:hover, .pane-head button.link:hover { text-decoration: underline; }
  .chip {
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 10px; font-size: 11.5px;
    background: var(--bg); cursor: pointer; color: var(--text);
  }
  .chip.active { border-color: var(--accent); color: var(--accent); }
  .pane-body { flex: 1; overflow: auto; background: var(--panel); position: relative; }
  .pane-body.text { padding: 14px 18px; }
  .pane-body pre {
    white-space: pre-wrap; word-break: break-word; font-family: "Consolas", "D2Coding", monospace;
    font-size: 13px; line-height: 1.55; margin: 0;
  }
  .pane-body iframe, .pane-body embed { width: 100%; height: 100%; border: none; display: block; }
  .fallback-msg { padding: 24px; color: var(--sub); font-size: 13px; line-height: 1.7; }
  .fallback-msg button { margin-top: 10px; }
  mark { background: var(--mark); color: inherit; border-radius: 2px; }
  mark.current { background: var(--markcur); }
  #syncBtn.active { border-color: var(--accent); color: var(--accent); }
  #syncBtn[disabled] { opacity: .4; cursor: not-allowed; }
  /* 탭: 이 화면에 기능이 둘이라는 걸 한눈에 보이게 크게 잡는다 */
  .tabs { display: flex; gap: 6px; flex-shrink: 0; }
  .tabs .tab {
    background: var(--bg); border: 1px solid var(--border); border-radius: 9px;
    padding: 7px 16px; font-size: 13.5px; color: var(--sub); cursor: pointer;
    font-weight: 700; display: flex; align-items: center; gap: 7px; line-height: 1.25;
  }
  .tabs .tab small { display: block; font-size: 11px; font-weight: 500; opacity: .85; }
  .tabs .tab:hover { border-color: var(--accent); color: var(--text); }
  .tabs .tab.active {
    background: var(--accent); border-color: var(--accent); color: #fff;
    box-shadow: 0 1px 6px rgba(37,99,235,.28);
  }
  .tabs .tab.active small { opacity: .92; }
  .tabs .badge {
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    background: var(--accent); color: #fff; font-size: 11px; font-weight: 700;
  }
  .tabs .tab.active .badge { background: rgba(255,255,255,.28); }
  .tools { display: contents; }
  .tools[hidden] { display: none; }
  #view-changes { flex: 1; overflow: auto; display: none; }
  body.tab-changes #view-compare { display: none; }
  body.tab-changes #view-changes { display: block; }
__DIFF_CSS__
</style>
</head>
<body class="diff-scope">
<header>
  <div class="tabs">
    <button class="tab active" data-tab="compare">📑 원본 대조
      <small>수집이 원문과 맞는지 확인</small></button>
    <button class="tab" data-tab="changes">🔍 변경 내역
      <small>어느 조문이 바뀌었는지</small><span class="badge" id="chgCount"></span></button>
  </div>
  <div class="tools" id="tools-compare">
    <select id="targetSel"></select>
    <button id="syncBtn" title="양쪽 다 텍스트 모드일 때만 동작: 한쪽 스크롤 시 반대쪽도 비율에 맞춰 이동">🔗 스크롤 동기화</button>
    <span id="stats"></span>
    <div class="search-wrap">
      <input id="searchBox" placeholder="본문 검색"
             title="입력하면 파싱 결과에서 찾아 표시합니다. 좌측을 '텍스트' 모드로 두면 원본도 함께 하이라이트됩니다. Enter=다음, Shift+Enter=이전">
      <span id="searchCount"></span>
      <button id="prevBtn">◀</button>
      <button id="nextBtn">▶</button>
    </div>
  </div>
  <div class="tools" id="tools-changes" hidden>
    <button class="chip" id="expandAll">전부 펼치기</button>
    <button class="chip" id="wholeLine">줄 전체 강조로 보기</button>
    <span class="legend" style="margin-left:auto">바뀐 글자만
      <span class="hi d">삭제</span> <span class="hi i">추가</span> 로 진하게 표시</span>
  </div>
</header>
<div id="view-changes"><div class="diff-wrap" id="diffRoot"></div></div>
<main id="view-compare">
  <div id="jump"><h3>조문 / 별표 / 부칙 점프</h3><div id="jumpList"></div></div>
  <div class="panes">
    <div class="pane left">
      <div class="pane-head">
        <div class="left-tools">
          <span class="side src">원본</span><span class="src-tag" id="srcTag"></span>
          <div class="seg" id="modeSeg">
            <button class="chip" id="modeScreenBtn" title="공식 웹페이지·PDF 를 그대로 표시">🖼 웹 화면</button>
            <button class="chip" id="modeTextBtn">📝 <b id="txtKind">텍스트</b></button>
          </div>
          <select id="fileSel" title="본문 또는 별표·첨부 파일 선택"></select>
        </div>
        <a id="rawLink" href="#" target="_blank" style="display:none">↗ 새 탭에서 열기</a>
      </div>
      <div class="pane-body" id="rawBody"></div>
    </div>
    <div class="pane right">
      <div class="pane-head">
        <span class="side out">파싱 결과</span>
        <span class="side-note" id="finalNote">우리 시스템이 뽑아낸 조문 — 왼쪽 원본과 같은지 확인</span>
        <button class="chip" id="soloOff" hidden
                style="margin-left:auto;white-space:nowrap">✕ 전체 보기</button>
      </div>
      <div class="pane-body text" id="finalBody"><pre id="finalPre"></pre></div>
    </div>
  </div>
</main>
<script>
const DATA = __DATA__;
const CHANGES = __CHANGES__;
__DIFF_JS__

// ── 탭 전환 ──────────────────────────────────────────────────────────
const diffRoot = document.getElementById('diffRoot');
document.getElementById('chgCount').textContent = CHANGES.length;
renderChanges(CHANGES, diffRoot);
bindDiffToggles(document.getElementById('expandAll'),
                document.getElementById('wholeLine'), CHANGES, diffRoot);
document.querySelectorAll('.tabs .tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tabs .tab').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  const changes = t.dataset.tab === 'changes';
  document.body.classList.toggle('tab-changes', changes);
  document.getElementById('tools-compare').hidden = changes;
  document.getElementById('tools-changes').hidden = !changes;
});

const sel = document.getElementById('targetSel');
// 어디서 가져온 규정인지 앞에 붙인다(법제처/협회가 섞여 있어 헷갈린다)
const SRC = {law: '법제처', admrul: '법제처', kofia: '금투협',
             crefia: '여신협', kfb: '은행연', fsc: '금융위'};
DATA.forEach((d, i) => {
  const o = document.createElement('option');
  o.value = i; o.textContent = `[${SRC[d.kind] || d.kind}] ${d.name}`;
  sel.appendChild(o);
});

const finalPre = document.getElementById('finalPre');
const rawBody = document.getElementById('rawBody');
const finalBody = document.getElementById('finalBody');
const rawLink = document.getElementById('rawLink');
const statsEl = document.getElementById('stats');
const jumpList = document.getElementById('jumpList');
const fileSel = document.getElementById('fileSel');
const soloOff = document.getElementById('soloOff');
const finalNote = document.getElementById('finalNote');
// 좌측은 그 별표 원본을 띄운 채로 우측만 전체로 되돌린다(문맥을 볼 때 쓴다)
soloOff.onclick = () => setSolo(null);
const modeScreenBtn = document.getElementById('modeScreenBtn');
const modeTextBtn = document.getElementById('modeTextBtn');
const syncBtn = document.getElementById('syncBtn');
let current = null;
let leftMode = 'screen';     // 'screen' | 'text'
let activeFile = null;       // 화면 모드에서 지금 보고 있는 첨부파일(있으면), 없으면 본문 웹페이지
let syncing = false;         // 스크롤 동기화 되받아치기 방지 (아래 linkScroll 참고)
let syncTimer = null;
let lastSyncedLabel = null;   // 마지막으로 좌측을 맞춘 조문

function escapeHtml(s) {
  return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
}

// 텍스트를 '조문 단위 블록'으로 그린다.
// 줄마다 <div> 를 만들면 큰 규정에서 4만 개가 넘어(자본시장법 시행령 원본 42,724줄)
// 검색할 때마다 그걸 통째로 다시 그리느라 심하게 느려진다. 점프는 조문 단위면
// 충분하므로 조문마다 블록 하나로 묶어 요소 수를 수십 배 줄인다.
function buildBlocks(text, index) {
  const lines = text.split('\n');
  const marks = (index || []).slice().sort((a, b) => a.line - b.line);
  const blocks = [];
  let pos = 0;
  for (const it of marks) {
    if (it.line > pos) blocks.push({label: null, line: pos, lines: lines.slice(pos, it.line)});
    const end = marks[marks.indexOf(it) + 1] ? marks[marks.indexOf(it) + 1].line : lines.length;
    blocks.push({label: it.label, line: it.line, lines: lines.slice(it.line, end)});
    pos = end;
  }
  if (pos < lines.length) blocks.push({label: null, line: pos, lines: lines.slice(pos)});
  // 이스케이프는 대상당 한 번만 하고 캐시한다(검색할 때마다 다시 하면 느리다).
  // 조문 블록은 머리글 한 줄만 <span class="h"> 로 감싸 그 줄만 굵게 보이게 한다.
  return blocks.map(b => {
    const esc = escapeHtml(b.lines.join('\n'));
    if (!b.label) return {...b, html: esc || '&nbsp;'};
    const nl = esc.indexOf('\n');
    const head = nl < 0 ? esc : esc.slice(0, nl);
    const rest = nl < 0 ? '' : esc.slice(nl);
    return {...b, html: `<span class="h">${head}</span>${rest}` || '&nbsp;'};
  });
}

const _blockCache = new Map();
function blocksOf(key, text, index) {
  if (!_blockCache.has(key)) _blockCache.set(key, buildBlocks(text, index));
  return _blockCache.get(key);
}

// 하이라이트는 **태그 밖 텍스트에만** 적용한다.
// 그냥 replace 하면 'span' 같은 검색어가 <span class="h"> 안을 건드려 화면이 깨진다.
function highlight(html, rx) {
  return html.split(/(<[^>]*>)/).map(
    p => p.charCodeAt(0) === 60 ? p : p.replace(rx, m => `<mark>${m}</mark>`)).join('');
}

function paint(container, blocks, prefix, query) {
  const rx = query ? new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi') : null;
  container.innerHTML = blocks.map(b => {
    const body = rx ? highlight(b.html, rx) : b.html;
    return b.label
      ? `<div class="ln art" id="${prefix}-${b.line}" data-label="${escapeHtml(b.label)}">${body}</div>`
      : `<div class="ln">${body}</div>`;
  }).join('');
}

// ── 좌우가 같은 대상을 보게 한다 ──────────────────────────────────────
// 좌측 드롭다운이 '지금 무엇을 보는가'를 정한다.
//   「규정 본문」  → 우측은 파싱 결과 전체
//   별표 파일     → 우측은 **그 별표 구간만** (별표 검수는 1:1 대조라 이게 기본)
// soloLine 은 그 구간 블록의 시작 줄. 블록이 이미 항목 단위로 잘려 있고 원래 줄
// 번호를 들고 있어서, 걸러내기만 하면 점프·동기화·검색이 그대로 동작한다.
let soloLine = null;
let fileLine = new Map();      // 파일 인덱스 → 그 파일에 대응하는 별표 블록의 줄
let fileLabel = new Map();     // 파일 인덱스 → 그 별표의 표시 이름

function renderFinal(d, query) {
  let blocks = blocksOf('f|' + d.name, d.final, d.index);
  if (soloLine !== null) blocks = blocks.filter(b => b.line === soloLine);
  paint(finalPre, blocks, 'art', query);
}

const NOTE_ALL = '우리 시스템이 뽑아낸 조문 — 왼쪽 원본과 같은지 확인';

function setSolo(line, name) {
  soloLine = line;
  soloOff.hidden = (line === null);
  finalNote.textContent = line === null ? NOTE_ALL
    : `${name || '선택한 항목'} 구간만 표시 중 — 왼쪽 원본과 1:1 대조`;
  renderFinal(current, lastQuery || null);
  finalBody.scrollTop = 0;
  reapplySearchIfAny();
}

// 좌측 파일 선택을 적용한다(드롭다운 조작·점프 클릭 양쪽에서 부른다).
function applyFile() {
  const files = (current.view && current.view.files) || [];
  const i = Number(fileSel.value);
  activeFile = i < 0 ? null : files[i];
  setSolo(i < 0 ? null : (fileLine.has(i) ? fileLine.get(i) : null),
          fileLabel.get(i));
  if (leftMode === 'screen') renderScreen();
}

function selectFile(v) {
  if (!fileSel.querySelector(`option[value="${v}"]`)) return false;
  fileSel.value = v;
  applyFile();
  // 별표는 원본 파일을 봐야 대조가 되므로 웹 화면 모드로 돌린다.
  // 조문으로 돌아가는 경우('-1')는 지금 모드를 그대로 둔다 — 텍스트 모드에서
  // 조문을 눌렀는데 화면이 통째로 바뀌면 동기화 대조가 끊긴다.
  if (Number(v) >= 0 && leftMode !== 'screen') setMode('screen');
  return true;
}

function render(idx) {
  const d = DATA[idx];
  current = d;
  leftMode = 'screen';
  activeFile = null;
  soloLine = null;          // 규정을 바꾸면 전체 보기로 돌아간다
  soloOff.hidden = true;
  finalNote.textContent = NOTE_ALL;
  // 별표 ↔ 첨부 파일 짝 (생성 시점에 파일명 규칙으로 이어 둔 것)
  fileLine = new Map();
  fileLabel = new Map();
  d.index.forEach(it => {
    if (it.fileIdx === undefined) return;
    if (!fileLine.has(it.fileIdx)) {
      fileLine.set(it.fileIdx, it.line);
      fileLabel.set(it.fileIdx, it.label + (it.title ? ' ' + it.title : ''));
    }
  });
  renderFinal(d, null);

  const statParts = Object.entries(d.stats || {}).map(([k, v]) => `<b>${v}</b>${k}`);
  statsEl.innerHTML = statParts.join(' · ');

  jumpList.innerHTML = '';
  d.index.forEach(it => {
    const b = document.createElement('button');
    b.className = 'item';
    // 별표는 번호만으로 구분이 안 된다(금투협은 93개가 전부 「[별지 NNNN]」).
    // 제목을 같이 띄운다 — 없으면 원본 파일명에서 뽑아 둔 것이 들어 있다.
    b.textContent = it.label + (it.n > 1 ? ` (${it.n})` : '')
                  + (it.title ? '  ' + it.title : '');
    b.title = b.textContent;
    b.onclick = () => jumpFinal(it.line, b, it);
    jumpList.appendChild(b);
  });

  // 볼 대상(규정 본문 / 별표·첨부) — 파일이 159개인 규정도 있어 드롭다운으로 만든다
  const files = (d.view && d.view.files) || [];
  const hasBody = d.view && d.view.mode === 'webpage';
  fileSel.innerHTML = '';
  if (hasBody) {
    const o = document.createElement('option');
    o.value = '-1'; o.textContent = '규정 본문';
    fileSel.appendChild(o);
  }
  files.forEach((f, i) => {
    const o = document.createElement('option');
    o.value = String(i);
    // 삭제된 별표는 파일이 남아 있을 뿐 내용이 없다. 하나씩 열어보지 않아도 알 수 있게 표시.
    o.textContent = f.name + (f.deleted ? '  ❌ 삭제됨'
                    : f.converted ? '  (PDF 변환본)'
                    : f.embeddable ? '' : '  (HWP — 같은 이름 PDF 항목 참고)');
    if (f.deleted) o.style.color = '#999';
    fileSel.appendChild(o);
  });
  fileSel.style.display = fileSel.options.length > 1 ? '' : 'none';
  activeFile = hasBody ? null : (files[0] || null);
  fileSel.value = hasBody ? '-1' : '0';
  fileSel.onchange = applyFile;

  setMode('screen');
  document.getElementById('searchBox').value = '';
  clearSearch();
}

function setMode(mode) {
  leftMode = mode;
  modeScreenBtn.classList.toggle('active', mode === 'screen');
  modeTextBtn.classList.toggle('active', mode === 'text');
  // 원본이 어떤 형식인지 버튼에 그대로 적어준다 (JSON / HTML / 추출 텍스트)
  const k = current.kind;
  const kindName = (k === 'law' || k === 'admrul') ? 'JSON 원문'
                 : (k === 'kofia') ? 'HTML 원문' : '추출 텍스트';
  const el = document.getElementById('txtKind');
  if (el) el.textContent = kindName;
  const st = document.getElementById('srcTag');
  if (st) st.textContent = SRC[k] || k;   // 어느 기관 자료인지 화면에도 표시
  // 대상 선택은 '웹 화면' 전용이다. 텍스트 모드에서는 원본 응답 하나뿐이라
  // 골라도 바뀌는 게 없으므로 비활성으로 두어 오해를 없앤다.
  const many = fileSel.options.length > 1;
  fileSel.disabled = (mode !== 'screen');
  fileSel.title = (mode === 'screen')
    ? '웹 화면에 표시할 대상 — 규정 본문 또는 별표·첨부 파일'
    : `대상 선택은 '웹 화면'에서만 쓰입니다 (지금은 ${kindName} 하나만 표시)`;
  if (many) fileSel.style.display = '';
  modeTextBtn.title = (k === 'law' || k === 'admrul')
    ? '법제처 API 가 준 JSON 응답 그대로 — 조문 점프·검색·동기화 가능'
    : (k === 'kofia') ? '협회 웹페이지 HTML 원문 그대로'
    : 'HWP 에서 뽑은 텍스트(교차검증용 별도 추출기)';
  // 화면(iframe)은 다른 사이트라 스크롤을 건드릴 수 없어 동기화가 불가능하다
  syncBtn.disabled = (mode === 'screen');
  lastSyncedLabel = null;
  _rawLineCache.clear();
  if (mode === 'screen') renderScreen(); else renderText();
}
modeScreenBtn.onclick = () => setMode('screen');
modeTextBtn.onclick = () => setMode('text');

function renderScreen() {
  const d = current;
  const v = d.view || {mode: 'webpage', url: null, files: []};
  rawBody.className = 'pane-body';
  rawBody.innerHTML = '';
  if (activeFile) {
    if (activeFile.embeddable) {
      rawBody.innerHTML = `<embed src="${activeFile.rel}" type="application/pdf">`;
    } else {
      rawBody.innerHTML = `<div class="fallback-msg">HWP 는 브라우저에서 열 수 없습니다.<br>
        같은 이름의 <b>PDF 항목이 목록에 따로 있으니</b> 그것으로 보시거나, 아래에서 내려받으세요.<br>
        이 컴퓨터엔 HWP를 열 수 있는 프로그램이 설치돼 있지 않아, 아래 버튼을 눌러도 안 열릴 수 있습니다
        (한글뷰어 등을 설치하면 열립니다).<br>지금은 우측 상단 "📝 텍스트 추출" 모드의 교차검증 결과로 확인하세요.<br>
        <button onclick="window.open('${activeFile.rel}')">📂 ${activeFile.name} 열기 시도</button></div>`;
    }
    rawLink.style.display = '';
    rawLink.href = activeFile.rel;
    rawLink.textContent = '↗ 새 탭에서 열기';
  } else if (v.mode === 'webpage' && v.url) {
    rawBody.innerHTML = `<iframe src="${v.url}"></iframe>`;
    rawLink.style.display = '';
    rawLink.href = v.url;
    rawLink.textContent = '↗ 새 탭에서 열기';
  } else {
    rawBody.innerHTML = `<div class="fallback-msg">표시할 원본 화면이 없습니다.</div>`;
    rawLink.style.display = 'none';
  }
}

// 좌측 = 원본 텍스트(JSON/HTML) 그대로. 조문이 정의된 줄은 생성 시점에 미리 색인해 뒀다.
function leftText()  { return current.rawText || ''; }
function leftIndex() { return current.rawIndex || []; }

// 좌측도 줄 단위로 그린다. 그래야 '몇 번째 줄'로 정확히 맞출 수 있다.
function renderRaw(query) {
  const pre = document.getElementById('rawPre');
  if (!pre) return;
  paint(pre, blocksOf('r|' + current.name, leftText(), leftIndex()), 'raw', query);
}

function renderText() {
  const desc = current.rawDesc || '';
  rawBody.className = 'pane-body text';
  rawBody.innerHTML = `<div style="padding:6px 0 10px;font-size:12px;color:var(--sub)">${escapeHtml(desc)}</div><pre id="rawPre"></pre>`;
  renderRaw(lastQuery || null);
  rawLink.style.display = 'none';
  reapplySearchIfAny();
}

// 좌측에서 같은 조문 찾기.
//  · '원본 항목' 모드: 좌우를 같은 규칙으로 색인했으므로 라벨을 정확히 맞춘다.
//  · '원본 JSON' 모드: 색인이 없어 문자열 검색으로 추정한다. 다만 "제7조제1항"
//    같은 인용에 걸리지 않도록 조문 정의 형태('제7조(')를 우선한다.
const _rawLineCache = new Map();
function findRawLine(label) {
  const key = current.name + '|' + leftMode + '|' + label;
  if (_rawLineCache.has(key)) return _rawLineCache.get(key);
  let found = -1;
  if (leftMode === 'items') {
    const hit = leftIndex().find(it => it.label === label);
    found = hit ? hit.line : -1;
  } else {
    const bare = label.replace(/^부칙[^:]*:/, '');
    const lines = leftText().split('\n');
    // 인용이 아니라 '정의'로 보이는 줄만: 제7조( 또는 "제7조( 로 시작
    const defRx = new RegExp('(^|["\\\\s>])' + bare.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + '\\\\s*\\\\(');
    found = lines.findIndex(l => defRx.test(l));
    if (found < 0) found = lines.findIndex(l => l.includes(bare));
  }
  _rawLineCache.set(key, found);
  return found;
}

function syncToArticle(label) {
  if (leftMode === 'screen') return false;
  const i = findRawLine(label);
  if (i < 0) return false;
  const el = document.getElementById('raw-' + i);
  if (!el) return false;
  el.scrollIntoView({block: 'start'});
  rawBody.querySelectorAll('.ln.hit').forEach(x => x.classList.remove('hit'));
  el.classList.add('hit');
  return true;
}

function markJump(btn) {
  if (!btn) return;
  jumpList.querySelectorAll('.item.on').forEach(x => x.classList.remove('on'));
  btn.classList.add('on');
}

function jumpFinal(line, btn, item) {
  // 별표를 고르면 좌측을 그 원본 파일로 바꾼다 → 우측은 자동으로 그 구간만 남는다.
  if (item && item.fileIdx !== undefined && selectFile(String(item.fileIdx))) {
    markJump(btn);
    return;
  }
  // 조문·부칙을 고르면 구간 한정을 풀고 전체에서 그 줄로 이동한다.
  if (soloLine !== null && !selectFile('-1')) setSolo(null);
  const el = document.getElementById('art-' + line);
  if (!el) return;
  const synced = syncBtn.classList.contains('active') && !syncBtn.disabled;
  // 동기화가 켜져 있으면 이동 중에 반대쪽이 되받아쳐 점프가 취소된다.
  // 이동하는 동안 동기화를 잠그고, 도착한 뒤 반대쪽을 한 번만 맞춘다.
  if (synced) holdSync(400);
  // 비율 추정이 아니라 실제 그 줄 요소로 이동하고, 어디에 왔는지 눈에 띄게 표시
  // (동기화 중에는 부드러운 스크롤이 되받아치기와 겹치므로 즉시 이동)
  el.scrollIntoView({block: 'start', behavior: synced ? 'auto' : 'smooth'});
  if (synced) {
    // 비율이 아니라 '같은 조문'을 찾아 맞춘다. 원본과 파싱본은 길이·순서가
    // 달라서 비율로 맞추면 전혀 다른 조문이 나란히 놓인다.
    const label = el.dataset.label;
    if (!syncToArticle(label)) syncOnce(finalBody, rawBody);   // 못 찾으면 비율로 대체
  }
  finalPre.querySelectorAll('.ln.hit').forEach(x => x.classList.remove('hit'));
  el.classList.add('hit');
  if (btn) {
    jumpList.querySelectorAll('.item.on').forEach(x => x.classList.remove('on'));
    btn.classList.add('on');
  }
}

// 지금 화면 맨 위에 있는 조문 요소
function currentArticleEl() {
  const arts = finalPre.querySelectorAll('.ln.art');
  const top = finalBody.getBoundingClientRect().top;
  let cur = null;
  for (const a of arts) {
    if (a.getBoundingClientRect().top - top <= 8) cur = a; else break;
  }
  return cur;
}

// 스크롤할 때 (1) 지금 보고 있는 조문을 왼쪽 목록에 표시하고
//            (2) 동기화가 켜져 있으면 좌측 원본도 '같은 조문'으로 맞춘다
finalBody.addEventListener('scroll', () => {
  if (!current) return;
  const arts = [...finalPre.querySelectorAll('.ln.art')];
  const cur = currentArticleEl();
  const items = jumpList.querySelectorAll('.item');
  items.forEach(x => x.classList.remove('now'));
  if (!cur) return;
  const i = arts.indexOf(cur);
  if (items[i]) items[i].classList.add('now');

  if (syncBtn.classList.contains('active') && !syncBtn.disabled && !syncing) {
    const label = cur.dataset.label;
    if (label && label !== lastSyncedLabel) {   // 조문이 바뀔 때만 맞춘다
      lastSyncedLabel = label;
      holdSync(200);
      syncToArticle(label);
    }
  }
}, {passive: true});

// ── 검색 (텍스트 모드에서만 좌측도 하이라이트) ─────────────────────────
let matches = []; let rawMatches = []; let mi = -1; let lastQuery = '';
function clearSearch() {
  matches = []; rawMatches = []; mi = -1; lastQuery = '';
  document.getElementById('searchCount').textContent = '';
  renderFinal(current, null);
  if (leftMode !== 'screen') renderRaw(null);
}
function reapplySearchIfAny() {
  if (lastQuery) doSearch(lastQuery, true);
}
function doSearch(q, keepBox) {
  if (!keepBox) document.getElementById('searchBox').value = q;
  lastQuery = q;
  if (!q) { clearSearch(); return; }
  if (q.length < 2) {   // 한 글자는 수천 건이 걸려 화면만 무거워진다
    document.getElementById('searchCount').textContent = '2자 이상';
    return;
  }
  renderFinal(current, q);   // 줄 구조와 조문 앵커를 유지한 채 하이라이트
  if (leftMode !== 'screen') renderRaw(q);
  matches = Array.from(finalPre.querySelectorAll('mark'));
  rawMatches = Array.from(rawBody.querySelectorAll('mark'));
  mi = matches.length ? 0 : -1;
  updateSearchPos();
}
function updateSearchPos() {
  matches.forEach(m => m.classList.remove('current'));
  rawMatches.forEach(m => m.classList.remove('current'));
  // 좌우 매치 수가 다를 수 있으므로(원본엔 목차·주석에도 같은 말이 나옴)
  // 개수를 양쪽 다 보여주고, 좌측은 같은 순번이 있으면 함께 이동시킨다.
  const cnt = document.getElementById('searchCount');
  const rawInfo = (leftMode !== 'screen' && rawMatches.length) ? ` · 원본 ${rawMatches.length}` : '';
  cnt.textContent = matches.length ? `${mi+1}/${matches.length}${rawInfo}` : `0/0${rawInfo}`;
  if (mi < 0) return;
  const m = matches[mi];
  m.classList.add('current');
  m.scrollIntoView({block: 'center'});
  if (leftMode !== 'screen' && rawMatches[mi]) {
    holdSync(200);                       // 좌측 이동이 동기화를 건드리지 않게
    rawMatches[mi].classList.add('current');
    rawMatches[mi].scrollIntoView({block: 'center'});
  }
}
// 한 글자마다 전체를 다시 그리면 큰 규정에서 멈춘 것처럼 느려진다.
// 타이핑이 멎은 뒤에 한 번만 검색한다.
let _searchTimer = null;
document.getElementById('searchBox').addEventListener('input', e => {
  const q = e.target.value.trim();
  clearTimeout(_searchTimer);
  if (!q) { clearSearch(); return; }
  document.getElementById('searchCount').textContent = '…';
  _searchTimer = setTimeout(() => doSearch(q, true), 250);
});
document.getElementById('nextBtn').onclick = () => { if (matches.length) { mi = (mi+1) % matches.length; updateSearchPos(); } };
document.getElementById('prevBtn').onclick = () => { if (matches.length) { mi = (mi-1+matches.length) % matches.length; updateSearchPos(); } };
document.getElementById('searchBox').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.shiftKey ? document.getElementById('prevBtn').onclick() : document.getElementById('nextBtn').onclick(); }
});

// ── 스크롤 동기화 (텍스트 모드 전용) ────────────────────────────────────
// 한쪽을 움직이면 반대쪽도 따라가는데, 그 '따라간 움직임'이 다시 원래 쪽을
// 밀어내는 되받아치기가 생긴다. scroll 이벤트는 다음 프레임에 오므로
// 플래그를 같은 함수 안에서 바로 풀면 막지 못한다 → 타이머로 잠시 잠근다.
// (syncing / syncTimer 는 위쪽에서 미리 선언해 둔다)
function holdSync(ms) {
  syncing = true;
  clearTimeout(syncTimer);
  syncTimer = setTimeout(() => { syncing = false; }, ms);
}

function syncOnce(from, to) {
  const ratio = from.scrollTop / Math.max(from.scrollHeight - from.clientHeight, 1);
  to.scrollTop = ratio * (to.scrollHeight - to.clientHeight);
}

syncBtn.onclick = () => { if (!syncBtn.disabled) syncBtn.classList.toggle('active'); };

// 좌측(원본)을 움직였을 때만 비율로 우측을 맞춘다.
// 우측→좌측은 위 scroll 핸들러가 '같은 조문' 기준으로 처리하므로 여기서 제외한다.
function linkScroll(a, b) {
  a.addEventListener('scroll', () => {
    if (!syncBtn.classList.contains('active') || syncBtn.disabled || syncing) return;
    holdSync(120);          // 반대쪽이 되받아치지 못하게 잠깐 잠금
    syncOnce(a, b);
  }, {passive: true});
}
linkScroll(rawBody, finalBody);

sel.addEventListener('change', () => render(Number(sel.value)));
render(0);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
