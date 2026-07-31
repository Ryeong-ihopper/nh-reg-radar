# -*- coding: utf-8 -*-
"""
국가법령정보센터(법제처) Open API 스크래퍼  ── 어댑터 겸용
- 법령(law): 법률/시행령/시행규칙  → 조문(조>항>호>목) 구조화
- 행정규칙(admrul): 감독규정/시행세칙/고시  → 조문(조 단위) + 첨부파일

담는 것 : 조문 + 부칙 + 별표(텍스트+파일링크) + (행정규칙)첨부파일 + 버전 메타
빼는 것 : 개정문, 제개정이유  (변경 감지에 불필요)

이 파일은 단독 실행도 되지만, check_updates.py 가 어댑터로 import 해서 쓴다.
  - current_meta(name, kind) : 검색만으로 현재 버전 메타(변경 감지용) 반환
  - collect(name, kind)      : 본문/파일 전체 수집·저장, 저장된 메타 반환
"""
import os
import re
import sys
import json
import time
import html as htmllib
import urllib.parse
import urllib.request
from content_hash import sha256_structure
import name_match
import applog

log = applog.get_logger(__name__)

sys.stdout.reconfigure(encoding="utf-8")  # 콘솔 한글 깨짐 방지 (제자리 변경)

# 법제처 Open API 는 **신청한 사람의 아이디**로만 호출된다(이메일 앞부분).
# 코드에 박아두면 남의 계정으로 호출하게 되고 사용량 제한도 공유되므로,
# 환경변수로 받는다.  설정:  setx LAWGO_OC "회사아이디"
#   신청: https://open.law.go.kr  (무료, 즉시 발급)
# 법제처 Open API 이용자 ID. 개인 계정을 코드에 박아 두면 그대로 공유되므로
# 기본값 없이 환경변수로만 받는다.
# import 시점이 아니라 **실제로 호출할 때** 검사한다. 이 모듈에는 _safe() 처럼
# API 와 무관한 함수도 있어서, import 만으로 죽으면 관련 없는 기능까지 막힌다.
OC = os.environ.get("LAWGO_OC", "")


def require_oc():
    if not OC:
        raise SystemExit(
            "환경변수 LAWGO_OC 가 필요합니다.\n"
            "  법제처 Open API 이용자 ID(신청 시 쓴 이메일의 @ 앞부분)를 넣으세요.\n"
            "  발급: https://open.law.go.kr (무료, 즉시)  ·  예) setx LAWGO_OC myid")
    return OC
SITE = "https://www.law.go.kr"
BASE = SITE + "/DRF"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
FILE_DIR = os.path.join(OUT_DIR, "files")
_body_cache = {}

# 소스 종류별 필드/엔드포인트 매핑 (법령 vs 행정규칙의 스키마 차이 흡수)
KIND = {
    "law": {
        "target": "law",
        "list_root": "LawSearch", "list_item": "law",
        "name_f": "법령명한글", "mst_f": "법령일련번호",
        "id_f": "법령ID", "eff_f": "시행일자", "ver_f": "공포번호",
        "body_root": "법령", "fetch_param": "MST",
    },
    "admrul": {
        "target": "admrul",
        "list_root": "AdmRulSearch", "list_item": "admrul",
        "name_f": "행정규칙명", "mst_f": "행정규칙일련번호",
        "id_f": "행정규칙ID", "eff_f": "시행일자", "ver_f": "발령번호",
        "body_root": "AdmRulService", "fetch_param": "LID",
    },
}


# ── HTTP ────────────────────────────────────────────────────────────────
def _get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


# ── 공통 헬퍼 ───────────────────────────────────────────────────────────
def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _join(text):
    """내용 필드가 문자열·리스트·중첩리스트로 오는 경우 모두 평탄화.

    법제처 API 는 필드에 따라 &lt;/&gt; 처럼 HTML 엔티티로 이스케이프해 줄 때가 있다
    (실측: 삭제된 별표 7건의 제목 — "삭제 &lt;2016. 7. 28.&gt;"). 그대로 저장하면
    화면에 꺾쇠 대신 문자열이 찍힌다. 조문·항·호·목·부칙·별표 내용이 전부 이 함수를
    거치므로 여기서 한 번에 언이스케이프한다.
    """
    if text is None:
        return ""
    if isinstance(text, list):
        return "\n".join(p for p in (_join(t) for t in text) if p)
    return htmllib.unescape(str(text))


def _content(v):
    return v.get("content", "") if isinstance(v, dict) else (v or "")


def _links(v):
    out = []
    for x in _as_list(v):
        x = str(x)
        out.append(SITE + x if x.startswith("/") else x)
    return out


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


# ── 검색 (변경 감지에 필요한 최소 정보) ─────────────────────────────────
def search(name, kind):
    cfg = KIND[kind]
    q = urllib.parse.quote(name)
    require_oc()
    url = f"{BASE}/lawSearch.do?OC={OC}&target={cfg['target']}&type=JSON&query={q}&display=50"
    data = json.loads(_get(url))
    items = data.get(cfg["list_root"], {}).get(cfg["list_item"], [])
    return items if isinstance(items, list) else [items]


def _match(name, kind):
    """검색 결과에서 이 대상에 해당하는 항목 반환.

    예전에는 정확 일치가 없으면 **검색 첫 항목**을 그냥 썼다. 그러면 법령명이
    바뀌었을 때 엉뚱한 법령을 조용히 수집하게 된다. 지금은 공통 규칙(name_match)으로
    고르고, 정확 일치가 아니면 **경고를 남긴다**.
    """
    cfg = KIND[kind]
    items = search(name, kind)
    if not items:
        return None
    sibs = name_match.siblings_of(name, kind, os.path.join(ROOT, "targets.json"))
    hit = name_match.pick(name, items, sibs, key=lambda i: i.get(cfg["name_f"], ""))
    if hit is None:
        log.error("'%s' 과 맞는 검색 결과가 없습니다. 후보: %s",
                  name, [i.get(cfg["name_f"], "") for i in items[:3]])
        return None
    got = hit.get(cfg["name_f"], "")
    if name_match.norm(got) != name_match.norm(name):
        log.warning("이름이 정확히 일치하지 않습니다: 요청 '%s' → 선택 '%s'"
                    " (법령명이 바뀌었을 수 있으니 targets.json 확인 필요)", name, got)
    return hit


def current_meta(name, kind, deep=False):
    """현재 버전 메타 반환. deep일 때만 본문을 조회해 해시까지 계산."""
    cfg = KIND[kind]
    it = _match(name, kind)
    if not it:
        return None
    meta = {
        "name": it.get(cfg["name_f"], name),
        "kind": kind,
        "MST": str(it.get(cfg["mst_f"], "")),
        "ID": str(it.get(cfg["id_f"], "")),
        "시행일자": str(it.get(cfg["eff_f"], "")),
        "버전번호": str(it.get(cfg["ver_f"], "")),   # 공포번호 or 발령번호
    }
    if deep:
        body = fetch_body(meta)
        _body_cache[(kind, meta["MST"], meta["ID"])] = body
        meta["content_hash"] = _body_content_hash(body, kind)
    return meta


def _official_version_key(meta):
    return f"{meta['MST']}|{meta['시행일자']}|{meta['버전번호']}"


def _version_key(meta):
    """공식 버전과 본문 해시를 함께 사용해 조용한 본문 수정도 감지."""
    official = _official_version_key(meta)
    content_hash = meta.get("content_hash")
    return f"{official}|sha256:{content_hash}" if content_hash else official


# ── 본문 조회 ───────────────────────────────────────────────────────────
def fetch_body(meta):
    cache_key = (meta["kind"], meta["MST"], meta["ID"])
    if cache_key in _body_cache:
        return _body_cache[cache_key]
    cfg = KIND[meta["kind"]]
    param = cfg["fetch_param"]
    val = meta["MST"] if param == "MST" else meta["ID"]
    require_oc()
    url = f"{BASE}/lawService.do?OC={OC}&target={cfg['target']}&type=JSON&{param}={val}"
    return json.loads(_get(url))[cfg["body_root"]]


# ── 파서 ────────────────────────────────────────────────────────────────
def parse_articles_law(body):
    units = _as_list(body.get("조문", {}).get("조문단위", []))
    out = []
    for u in units:
        if u.get("조문여부") != "조문":
            continue
        art = {
            "조문번호": u.get("조문번호", ""),
            "조문가지번호": u.get("조문가지번호", ""),
            "조문제목": u.get("조문제목", ""),
            "조문내용": _join(u.get("조문내용", "")),
            "항": [],
        }
        for h in _as_list(u.get("항")):
            hang = {"항번호": h.get("항번호", ""), "항내용": _join(h.get("항내용", "")), "호": []}
            for ho in _as_list(h.get("호")):
                mok = [_join(m.get("목내용", "")) for m in _as_list(ho.get("목"))]
                hang["호"].append({"호번호": ho.get("호번호", ""),
                                  "호내용": _join(ho.get("호내용", "")), "목": mok})
            art["항"].append(hang)
        out.append(art)
    return out


# 행정규칙 조문 안의 항/호/목 분리.
# 법제처는 행정규칙 조문 하나를 통짜 문자열로 준다(법령과 달리 항/호/목이 나뉘어
# 오지 않음). 최대 4,900자가 줄바꿈 하나 없이 한 줄이라 한 단어만 개정돼도
# 조문 전체가 변경으로 잡혀 diff가 쓸모없어진다. 그래서 내용은 건드리지 않고
# 경계에 줄바꿈만 삽입한다.
#
# 마커를 정규식으로 한 번에 찾으면 오탐이 크다. 실제 원문에서
#   · "…을 말한다.1." 처럼 마커가 앞 글자에 붙어 있고
#   · "…농협은행다." 의 '다.'는 목 마커지만 "…라고 한다."의 '다.'는 문장 끝이며
#   · "<개정 2025.2.13>" 의 날짜는 호 번호처럼 보인다
# 따라서 **번호를 순번대로 추적**한다(1. 다음엔 2., 가. 다음엔 나.).
# 다음 번호가 안 나오면 목록이 끝난 것으로 보고 멈추므로 문장 끝 '다.'에 걸리지 않는다.
_MOK_CH = "가나다라마바사아자차카타파하"
_ANNOT = re.compile(r"<[^>]*>")
_DATE = re.compile(r"\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\.?")
_HANG = re.compile(r"(?=[①-⑳])")


def _cut_by_sequence(seg, markers):
    """markers 를 순서대로 찾아 그 위치에만 줄바꿈을 넣는다.
    앞 글자가 숫자/'의'/'제'인 경우(11. 안의 1., 1의2., 제2.)는 마커로 보지 않는다."""
    cuts = []
    start = 0
    for mk in markers:
        i = seg.find(mk, start)
        while i > 0 and (seg[i - 1].isdigit() or seg[i - 1] in "의제"):
            i = seg.find(mk, i + 1)
        if i < 0:
            break                      # 다음 번호가 없으면 목록 종료
        cuts.append(i)
        start = i + len(mk)
    if not cuts:
        return seg
    out, prev = [], 0
    for i in cuts:
        out.append(seg[prev:i])
        prev = i
    out.append(seg[prev:])
    return "\n".join(p for p in out if p)


def split_admrul_body(s):
    """통짜 조문 문자열의 항/호/목 경계에 줄바꿈만 삽입(내용 무변경)."""
    if not s:
        return s
    holes = []          # 날짜·<개정 …> 주석을 잠시 가려 번호로 오인되지 않게 한다

    def _mask(m):
        holes.append(m.group(0))
        return "\x00%d\x00" % (len(holes) - 1)

    t = _DATE.sub(_mask, _ANNOT.sub(_mask, s))

    ho = [f"{i}." for i in range(1, 61)]
    mok = [c + "." for c in _MOK_CH]
    parts = []
    for hang in _HANG.sub("\n", t).split("\n"):          # ① 항
        for h in _cut_by_sequence(hang, ho).split("\n"):  # 1. 호
            parts.extend(_cut_by_sequence(h, mok).split("\n"))  # 가. 목

    t = "\n".join(p for p in parts if p)
    t = re.sub(r"\x00(\d+)\x00", lambda m: holes[int(m.group(1))], t)
    # 줄 단위 strip 은 하지 않는다 — 경계 공백까지 지우면 원문이 바뀌어
    # 본문 해시가 실제 개정과 무관하게 달라진다(줄바꿈 '삽입'만 해야 함).
    return re.sub(r"\n{2,}", "\n", t).strip()


# 행정규칙 조문 머리(제1-1조 / 제12조 / 제12조의2)와 편·장·절 제목.
# **반드시 여는 괄호가 뒤따라야 한다.** 조문 제목은 항상 "제3-7조(자산건전성 분류)"
# 형태이고, 본문 중의 인용은 "제3-7조 및 제3-8조를 적용하지 아니한다" 처럼 괄호가
# 없다. 괄호를 요구하지 않으면 인용에서 잘려 같은 조번호가 중복 생성된다.
_ADM_ART_HEAD = re.compile(r"제\s*\d+(?:-\d+)?\s*조(?:의\s*\d+)?\s*[(（【]")
_ADM_DIV_HEAD = re.compile(r"제\s*\d+\s*[편장절관]\s*[^\n]{0,40}")
# 심사지침·예규는 조문 대신 로마숫자로 나뉜다 (Ⅰ. 목적 / Ⅱ. 적용범위 …)
_ADM_ROMAN = re.compile(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*\.\s*\S")


def _art_key(m):
    """'제3-7조의2' → (3, 7, 2) 형태의 비교 가능한 번호."""
    g = re.match(r"제\s*(\d+)(?:-(\d+))?\s*조(?:의\s*(\d+))?", m)
    if not g:
        return None
    return (int(g.group(1)), int(g.group(2) or 0), int(g.group(3) or 0))


def _split_admrul_articles(text):
    """조문내용이 **통짜 문자열 하나**로 오는 경우 조 단위로 나눈다.

    법제처는 행정규칙마다 형태가 다르다.
      · 배열로 조문을 하나씩 주는 것 (금소법 감독규정 등)
      · 353,376자짜리 문자열 하나로 통째로 주는 것 (금융투자업규정 등)
      · 아예 조문이 아니라 'Ⅰ. 목적 / Ⅱ. 적용범위' 형식인 것 (심사지침·예규)

    문제는 본문 안의 **인용**도 "제3조(부당한 표시·광고행위의 금지)" 형태라
    모양만으로는 조문 머리와 구분되지 않는다는 점이다. 그래서 **조번호가
    순서대로 증가하는 것만** 조문 머리로 인정한다. 인용은 순서를 지키지 않으므로
    자연히 걸러진다. (조문형식이 아닌 문서는 남는 게 없어 통짜로 반환된다)
    """
    heads, last = [], (0, 0, 0)
    for m in _ADM_ART_HEAD.finditer(text):
        k = _art_key(m.group(0))
        if k and k > last:
            heads.append(m.start())
            last = k
    if len(heads) < 3:
        # 조문형이 아니다. 심사지침·예규는 'Ⅰ. 목적 / Ⅱ. 적용범위' 로 나뉘므로
        # 그 구분으로 자른다. 그마저 없으면 통짜로 둔다.
        rom = [m.start() for m in _ADM_ROMAN.finditer(text)]
        if len(rom) >= 2:
            out = [text[:rom[0]]] if rom[0] > 0 else []
            for i, s in enumerate(rom):
                out.append(text[s:rom[i + 1] if i + 1 < len(rom) else len(text)])
            return [x for x in out if x.strip()]
        return [text]
    out = []
    if heads[0] > 0:            # 첫 조문 앞의 편/장 제목
        out.append(text[:heads[0]])
    for i, s in enumerate(heads):
        out.append(text[s:heads[i + 1] if i + 1 < len(heads) else len(text)])
    return out


def parse_articles_admrul(body):
    """행정규칙 조문 → [{조문번호, 조문제목, 조문내용, ...}].

    법제처가 항/호/목을 나눠주지 않으므로 내용은 그대로 두고 경계에 줄바꿈만 넣는다.
    편·장·절 제목은 조문이 아니므로 '구분' 항목으로 따로 표시한다.
    """
    raw = _as_list(body.get("조문내용"))
    if len(raw) == 1 and isinstance(raw[0], str):
        raw = _split_admrul_articles(_join(raw[0]))   # 통짜 문자열이면 조 단위로 분해

    out = []
    for s in raw:
        s = _join(s).strip()
        if not s:
            continue
        m = _ADM_ART_HEAD.search(s[:60])
        if m and m.start() == 0:
            head = re.match(r"제\s*(\d+(?:-\d+)?)\s*조(?:의\s*(\d+))?", s)
            title = re.match(r"[^\(]{0,20}\(([^)]{1,60})\)", s)
            out.append({"조문번호": head.group(1) if head else "",
                        "조문가지번호": (head.group(2) or "") if head else "",
                        "조문제목": title.group(1) if title else "",
                        "조문내용": split_admrul_body(s), "항": []})
        elif _ADM_DIV_HEAD.match(s):
            # 편/장/절 제목 — 조문이 아니라 구분선. 조번호가 없어 키로 쓸 수 없다.
            out.append({"조문번호": "", "조문가지번호": "", "조문제목": "",
                        "구분": s.strip()[:60], "조문내용": s.strip(), "항": []})
        else:
            out.append({"조문번호": "", "조문가지번호": "", "조문제목": "",
                        "조문내용": split_admrul_body(s), "항": []})
    return out


def parse_addenda(body):
    """부칙: 법령은 부칙단위 리스트, 행정규칙은 평면 dict — 둘 다 처리."""
    sec = body.get("부칙")
    if not sec:
        return []
    units = sec.get("부칙단위") if isinstance(sec, dict) else sec
    if units is None:                      # 행정규칙 평면형
        units = [sec]
    out = []
    for u in _as_list(units):
        if not isinstance(u, dict):
            continue
        out.append({"공포일자": u.get("부칙공포일자", ""),
                    "공포번호": u.get("부칙공포번호", ""),
                    "내용": _join(u.get("부칙내용", ""))})
    return out


def parse_tables(body):
    units = _as_list(body.get("별표", {}).get("별표단위", []))
    out = []
    for u in units:
        if not isinstance(u, dict):
            continue
        out.append({
            "별표번호": u.get("별표번호", ""),
            "별표가지번호": u.get("별표가지번호", ""),
            "구분": u.get("별표구분", ""),
            "제목": htmllib.unescape(u.get("별표제목", "") or ""),
            "내용": _join(u.get("별표내용", "")),
            "PDF파일명": u.get("별표PDF파일명", ""),
            "HWP파일명": u.get("별표HWP파일명", ""),
            "PDF링크": _links(u.get("별표서식PDF파일링크")),
            "HWP링크": _links(u.get("별표서식파일링크")),
            "이미지링크": _links(u.get("별표서식이미지파일링크")),
        })
    return out


def parse_attachments(body):
    """행정규칙 첨부파일: 링크/파일명 병렬 배열."""
    att = body.get("첨부파일")
    if not isinstance(att, dict):
        return []
    links = _links(att.get("첨부파일링크"))
    names = _as_list(att.get("첨부파일명"))
    out = []
    for i, link in enumerate(links):
        out.append({"파일명": names[i] if i < len(names) else "", "링크": link})
    return out


def _body_content(body, kind):
    """변경 감지에 필요한 본문 구조만 추려 API의 비본문 메타 변동을 제외."""
    articles = parse_articles_law(body) if kind == "law" else parse_articles_admrul(body)
    return {
        "조문": articles,
        "부칙": parse_addenda(body),
        "별표": parse_tables(body),
        "첨부파일": parse_attachments(body) if kind == "admrul" else [],
    }


def _body_content_hash(body, kind):
    return sha256_structure(_body_content(body, kind))


# ── 파일 다운로드 ───────────────────────────────────────────────────────
def _table_stem(t, index):
    """별표 파일 저장용 이름. 별표와 별지는 번호가 겹칠 수 있어 구분을 넣는다."""
    category = (t.get("구분") or "별표").strip()
    branch = t.get("별표가지번호", "")
    branch = "" if branch in ("", "0", "00") else f"의{branch}"
    return f"{category}{t['별표번호']}{branch}" if t["별표번호"] else f"{category}{index:04d}"


def attach_saved_names(tables):
    """각 별표에 '실제로 저장되는 파일명'을 기록해 둔다.
    법제처는 행정규칙 별표에 파일명을 주지 않고 링크만 주기 때문에(법령은 줌),
    이 값이 없으면 화면에서 별표와 내려받은 파일을 연결할 수 없다."""
    for index, t in enumerate(tables, 1):
        stem = _table_stem(t, index)
        t["저장PDF"] = (t["PDF파일명"] or stem + ".pdf") if t["PDF링크"] else ""
        t["저장HWP"] = (t["HWP파일명"] or stem + ".hwp") if t["HWP링크"] else ""
    return tables


def download_files(tables, attachments, law_name):
    d = os.path.join(FILE_DIR, _safe(law_name))
    attach_saved_names(tables)
    jobs = []
    for t in tables:
        if t["저장PDF"]:
            jobs.append((t["PDF링크"][0], t["저장PDF"]))
        if t["저장HWP"]:
            jobs.append((t["HWP링크"][0], t["저장HWP"]))
    for i, a in enumerate(attachments):
        if a["링크"]:
            jobs.append((a["링크"], a["파일명"] or f"첨부{i+1}"))
    if not jobs:
        return 0
    os.makedirs(d, exist_ok=True)
    n = 0
    for url, fname in jobs:
        path = os.path.join(d, _safe(fname))
        try:
            # 먼저 받아서 확인한 뒤에 쓴다. open() 을 앞에 두면 다운로드가 실패해도
            # **0바이트 파일이 남아** 나중에 "파일은 있는데 파싱만 실패"로 보인다.
            data = _get(url, binary=True)
            if not data:
                raise ValueError("빈 응답")
            with open(path, "wb") as f:
                f.write(data)
            n += 1
        except Exception as e:
            print(f"    ! 파일 실패 {fname}: {e}")
            if os.path.exists(path):   # 이전 실행에서 남은 껍데기 정리
                os.remove(path)
    return n


# ── TXT 출력 ────────────────────────────────────────────────────────────
def to_text(header, articles, addenda, tables, attachments):
    lines = [header, "=" * 70, ""]
    for a in articles:
        if a["조문내용"]:
            lines.append(a["조문내용"])
        else:
            num = a["조문번호"] + ("의" + a["조문가지번호"] if a["조문가지번호"] else "")
            lines.append(f"제{num}조" + (f"({a['조문제목']})" if a["조문제목"] else ""))
        for h in a["항"]:
            if h["항내용"]:
                lines.append("  " + h["항내용"])
            for ho in h["호"]:
                if ho["호내용"]:
                    lines.append("    " + ho["호내용"])
                for m in ho["목"]:
                    lines.append("      " + m)
        lines.append("")
    if addenda:
        lines += ["", "─" * 70, "부   칙", "─" * 70, ""]
        for ad in addenda:
            lines += [ad["내용"], ""]
    if tables:
        lines += ["", "─" * 70, "별표 / 서식", "─" * 70, ""]
        for t in tables:
            # 별표가 하나뿐인 법령은 법제처가 번호를 '0000' 으로 준다(원문 표기는 그냥 '[별표]').
            no = "" if str(t["별표번호"]).strip("0") == "" else f" {t['별표번호']}"
            # 가지번호(별표 1의2)를 빼면 별표 1·1의2·1의3 이 모두 "[별표 0001]" 로 보여
            # 목록에서 구분이 안 된다.
            br = str(t.get("별표가지번호") or "").strip()
            if br and br.strip("0"):
                no += f"의{int(br)}"
            lines.append(f"[{t.get('구분') or '별표'}{no}] {t['제목']}")
            if t["내용"]:
                lines.append(t["내용"])
            files = [f for f in (t.get("저장PDF"), t.get("저장HWP")) if f]
            if files:
                lines.append("  (원본 파일: " + " / ".join(files) + ")")
            lines.append("")
    if attachments:
        lines += ["", "─" * 70, "첨부파일", "─" * 70, ""]
        for a in attachments:
            lines.append("  - " + a["파일명"])
    return "\n".join(lines)


# ── 수집 파이프라인 ─────────────────────────────────────────────────────
def collect(name, kind, want_files=True, verbose=True):
    meta = current_meta(name, kind)
    if not meta:
        if verbose:
            print(f"  → '{name}' 검색 결과 없음")
        return None
    body = fetch_body(meta)
    meta["content_hash"] = _body_content_hash(body, kind)
    info = body.get("기본정보") or body.get("행정규칙기본정보") or {}

    if kind == "law":
        articles = parse_articles_law(body)
    else:
        articles = parse_articles_admrul(body)
    addenda = parse_addenda(body)
    tables = parse_tables(body)
    attachments = parse_attachments(body) if kind == "admrul" else []

    if verbose:
        print(f"  → 조문 {len(articles)} · 부칙 {len(addenda)} · "
              f"별표 {len(tables)} · 첨부 {len(attachments)}")

    downloaded = 0
    if want_files:
        downloaded = download_files(tables, attachments, meta["name"])
        if verbose and downloaded:
            print(f"  → 파일 {downloaded}개 다운로드")
    else:
        attach_saved_names(tables)   # 파일을 안 받아도 어떤 파일과 짝인지는 기록해 둔다

    os.makedirs(OUT_DIR, exist_ok=True)
    base = _safe(meta["name"])
    법종 = _content(info.get("법종구분")) or info.get("행정규칙종류", "")
    dept = _content(info.get("소관부처")) or info.get("소관부처명", "")
    # 날짜 3종을 구분해서 담는다. '언제 바뀌었나'는 공포일(=관보 게재일)이고,
    # 시행일은 효력이 생기는 날이라 보통 몇 달 뒤다. 둘을 섞으면 안 된다.
    # 행정규칙은 '공포' 대신 '발령'이라는 말을 쓴다.
    공포일 = str(info.get("공포일자") or info.get("발령일자") or "")
    제개정 = _content(info.get("제개정구분")) or info.get("제개정구분명", "")
    header = (f"{meta['name']}\n[{법종}] 공포 {공포일 or '?'} · 시행 {meta['시행일자']} · "
              f"버전 {meta['버전번호']}"
              + (f" ({제개정})" if 제개정 else "") + f" · 소관 {dept}")

    record = {
        "법령명": meta["name"],
        "종류": kind,
        "법종구분": 법종,
        "소관부처": dept,
        "ID": meta["ID"],
        "MST": meta["MST"],
        "공포일자": 공포일,
        "시행일자": meta["시행일자"],
        "제개정구분": 제개정,
        "버전번호": meta["버전번호"],
        "버전키": _version_key(meta),
        "공식버전키": _official_version_key(meta),
        "본문해시": meta["content_hash"],
        "수집기준": "조문+부칙+별표" + ("+첨부" if kind == "admrul" else ""),
        "통계": {"조문수": len(articles), "부칙수": len(addenda),
                "별표수": len(tables), "첨부수": len(attachments),
                "다운로드파일수": downloaded},
        "조문": articles, "부칙": addenda, "별표": tables, "첨부파일": attachments,
    }
    with open(os.path.join(OUT_DIR, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(to_text(header, articles, addenda, tables, attachments))
    if verbose:
        print(f"  → 저장: output/{base}.json, output/{base}.txt")
    return record


# ── 단독 실행 ───────────────────────────────────────────────────────────
def _load_targets():
    p = os.path.join(ROOT, "targets.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return [{"name": n, "kind": "law"} for n in [
        "금융소비자 보호에 관한 법률", "금융소비자 보호에 관한 법률 시행령"]]


def main():
    args = sys.argv[1:]
    want_files = "--no-files" not in args
    names = [a for a in args if not a.startswith("--")]
    if names:
        targets = [{"name": n, "kind": "admrul" if ("규정" in n or "고시" in n
                    or "세칙" in n or "훈령" in n) else "law"} for n in names]
    else:
        targets = _load_targets()
    for i, t in enumerate(targets):
        print(f"[{i+1}/{len(targets)}] {t['name']} ({t['kind']})")
        collect(t["name"], t["kind"], want_files=want_files)
        if i < len(targets) - 1:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
