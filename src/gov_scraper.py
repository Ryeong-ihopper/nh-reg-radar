# -*- coding: utf-8 -*-
"""
정부기관 게시판 어댑터 — 금융위원회(fsc) · 금융감독원(fss).

협회 실무자료는 회원사에만 배포돼 자동 수집이 불가능하지만, 금융위·금감원 자료는
공개 게시판에 올라온다. 두 기관은 게시판 구조만 다를 뿐 수집 방식이 같아
(제목 검색 → 첨부 고르기 → 내용 해시로 변경 감지) 한 모듈로 합쳐 두었다.

  kind="fsc"   정책마당   /po010101/<게시물번호>          첨부: /comm/getFile
  kind="fss"   보도자료   /fss/bbs/B0000188/view.do       첨부: /fss/cmmn/file/fileDown.do

게시물 번호는 하드코딩하지 않고 **제목으로 검색해서 찾는다** — 개정판이 새 게시물로
올라오면 번호가 바뀌기 때문(은행연 어댑터와 같은 방식).

── 현재 등록 대상 없음(TARGETS 가 비어 있다) ─────────────────────────────
게시판 자료는 **기관이 버전 식별자를 주지 않는다.** 법제처는 일련번호(MST),
금투협은 이력번호(historySeq)를 발급하지만, 게시판은 제목·파일명 규칙으로 짐작하는
수밖에 없어 개정판 첨부 이름이 조금만 달라져도 놓친다. "개정을 확실히 잡을 수 있는
자료만 자동 수집한다"는 원칙에 따라

  · 금융위 가이드라인 2건 → 수동 관리(output/_reference/ 에 보관)
  · 금감원 보도자료      → 본문뿐이라 심의에서 인용할 근거가 아니라 제외
                            (체크리스트·심의사례 인용 실측 0회)

로 정리했다. 확실히 추적할 수 있는 자료가 생기면 아래 TARGETS 에 검색어·파일조건만
적으면 그대로 동작한다.
"""
import os
import re
import ssl
import json
import hashlib
import urllib.parse
import urllib.request

import applog

log = applog.get_logger(__name__)

FSC_SITE = "https://www.fsc.go.kr"
FSC_LIST = FSC_SITE + "/po010101"                    # 정책마당 > 정책일반
FSC_FILE = FSC_SITE + "/comm/getFile"

FSS_SITE = "https://www.fss.or.kr"
FSS_LIST = FSS_SITE + "/fss/bbs/B0000188/list.do"    # 보도자료
FSS_VIEW = FSS_SITE + "/fss/bbs/B0000188/view.do"
FSS_MENU = "200218"

UA = {"User-Agent": "Mozilla/5.0"}

# 규정명 → {"검색어", "파일조건"(파일명에 모두 들어가야 할 문자열), "확장자"}
# 같은 검색어에 여러 편이 걸리므로 파일명 조건으로 편을 구분한다.
TARGETS = {"fsc": {}, "fss": {}}

# 기관별 표시 정보 (수집 결과 JSON 에 그대로 들어간다)
_ORG = {
    "fsc": {"종류": "가이드라인", "발행기관": "금융위원회·금융감독원", "이름": "금융위"},
    "fss": {"종류": "안내자료", "발행기관": "금융감독원", "이름": "금감원"},
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")


def _safe(name):
    import law_scraper
    return law_scraper._safe(name)


def _ctx(kind):
    c = ssl.create_default_context()
    if kind == "fss":
        # 금감원 서버는 체인 검증에서 걸리는 경우가 있어 완화한다(공개 게시물 조회 전용).
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
    return c


def _get(url, kind, binary=False, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90, context=_ctx(kind)) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "ignore")
        except Exception as e:                      # 일시적 오류는 재시도
            last = e
            log.warning("%s 요청 실패(%d/%d) %s: %s", kind, i + 1, retries, url[:90], e)
    raise last


# ── 게시물 검색 ──────────────────────────────────────────────────────────
# 검색어가 여러 게시물에 걸리므로 첫 번째를 그냥 쓰면 안 된다.
# 호출부에서 첨부 조건까지 맞는 게시물을 골라야 한다.

def _find_posts(keyword, kind):
    """제목 검색 결과 [(게시물번호, 제목)] — 최신순."""
    if kind == "fsc":
        url = f"{FSC_LIST}?curPage=1&srchKey=&srchText={urllib.parse.quote(keyword)}"
        pat = r'href="[^"]*?/po010101/(\d+)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{6,160})'
        html = _get(url, kind)
        pairs = [(m[0], m[1]) for m in re.findall(pat, html)]
    else:
        url = (f"{FSS_LIST}?menuNo={FSS_MENU}&searchCnd=1&searchWrd="
               + urllib.parse.quote(keyword))
        html = _get(url, kind)
        pairs = [(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)))
                 for m in re.finditer(r'nttId=(\d+)[^>]*>(.*?)</a>', html, re.S)]
    out, seen = [], set()
    for no, title in pairs:
        t = re.sub(r"\s+", " ", title).strip()
        if len(t) > 6 and no not in seen:
            seen.add(no)
            out.append((no, t))
    return out


def _attachments(no, kind):
    """게시물의 첨부 [(파일명, 다운로드 URL)] — 실제 파일명이 있는 항목만.

    fsc 는 같은 fileNo 가 '파일다운로드' 라는 대체텍스트로 한 번 더 잡히므로
    확장자가 있는 쪽만 남긴다.
    """
    out = []
    if kind == "fsc":
        html = _get(f"{FSC_LIST}/{no}", kind)
        pat = (r'getFile\?srvcId=BBSTY1&(?:amp;)?upperNo=%s&(?:amp;)?fileTy=ATTACH'
               r'&(?:amp;)?fileNo=(\d+)[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,160})' % no)
        for m in re.finditer(pat, html):
            fname = re.sub(r"\s+", " ", m.group(2)).strip()
            if "." in fname:
                out.append((fname, f"{FSC_FILE}?srvcId=BBSTY1&upperNo={no}"
                                   f"&fileTy=ATTACH&fileNo={m.group(1)}"))
    else:
        html = _get(f"{FSS_VIEW}?nttId={no}&menuNo={FSS_MENU}", kind)
        pat = (r'href="(/fss/cmmn/file/fileDown\.do\?[^"]+)"[^>]*>\s*'
               r'<span class="file-name">.*?<span class="name">\s*([^<]+?)\s*(?:<|$)')
        for m in re.finditer(pat, html, re.S):
            fname = re.sub(r"\s+", " ", m.group(2)).strip()
            if "." in fname:
                out.append((fname, FSS_SITE + m.group(1).replace("&amp;", "&")))
    return out


def _source_url(no, kind):
    return (f"{FSC_LIST}/{no}" if kind == "fsc"
            else f"{FSS_VIEW}?nttId={no}&menuNo={FSS_MENU}")


def current_meta(name, kind="fsc"):
    """{name, 게시물번호, 제목, 파일명, sha256, 버전키, bytes} — 못 찾으면 None."""
    spec = TARGETS.get(kind, {}).get(name)
    if not spec:
        log.error("%s 대상에 등록되지 않은 이름: %s", kind, name)
        return None
    # 검색 결과를 최신순으로 훑으며 **조건에 맞는 첨부가 실제로 있는** 게시물을 고른다
    for no, title in _find_posts(spec["검색어"], kind):
        for fname, url in _attachments(no, kind):
            if not fname.lower().endswith(spec["확장자"]):
                continue
            if not all(c in fname for c in spec["파일조건"]):
                continue
            data = _get(url, kind, binary=True)
            if len(data) < 1024:
                log.error("첨부가 너무 작음(%d바이트) — 다운로드 실패로 본다: %s",
                          len(data), name)
                return None
            sha = hashlib.sha256(data).hexdigest()
            return {"name": name, "kind": kind, "게시물번호": no, "제목": title,
                    "파일명": fname, "sha256": sha, "bytes": data,
                    # 게시물 번호가 바뀌어도 내용이 같으면 변경 아님 → 키는 내용 해시.
                    # MST/시행일자/버전번호는 법제처 전용 필드지만 check_updates 가
                    # 공통으로 쓰므로 파일 기반 어댑터(kfb/crefia)와 같게 채워 준다.
                    "버전키": sha[:16], "공식버전키": sha[:16],
                    "MST": sha[:12], "ID": no, "시행일자": "", "버전번호": sha[:12]}
    log.error("검색 결과 중 조건에 맞는 첨부를 가진 게시물이 없음: %s", name)
    return None


def _version_key(meta):
    return meta["버전키"]


def collect(name, kind="fsc", want_files=True, verbose=True):
    import file_text
    meta = current_meta(name, kind)
    if not meta:
        raise RuntimeError(f"{_ORG[kind]['이름']} 게시판에서 찾지 못함: {name}")

    fdir = os.path.join(OUT_DIR, "files", _safe(name))
    os.makedirs(fdir, exist_ok=True)
    # 추출기(OpenDataLoader CLI)가 경로에 든 일부 문자에서 실패한다.
    # 실제로 대상 이름에 em-dash(—)가 있을 때 exit 1 로 죽었다.
    fpath = os.path.join(fdir, _safe(meta["파일명"]))
    with open(fpath, "wb") as f:          # 메모리에 다 받은 뒤 쓴다(0바이트 방지)
        f.write(meta["bytes"])

    text = file_text.extract(fpath)
    base = _safe(name)
    rec = {
        "법령명": name, "종류": _ORG[kind]["종류"], "발행기관": _ORG[kind]["발행기관"],
        "게시물번호": meta["게시물번호"], "게시물제목": meta["제목"],
        "버전키": meta["버전키"], "공식버전키": meta["공식버전키"],
        "본문해시": meta["sha256"],
        "출처": _source_url(meta["게시물번호"], kind),
        "통계": {"본문길이": len(text)},
        "본문": text,
        "첨부": [{"파일명": meta["파일명"], "sha256": meta["sha256"],
                  "바이트": len(meta["bytes"])}],
    }
    with open(os.path.join(OUT_DIR, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if verbose:
        print(f"  → 본문 {len(text):,}자 · 첨부 {meta['파일명'][:50]}")
        print(f"  → 저장: output/{base}.json, output/{base}.txt")
    return rec


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    kind = sys.argv[1] if sys.argv[1:2] and sys.argv[1] in TARGETS else "fsc"
    names = [a for a in sys.argv[1:] if a not in TARGETS] or list(TARGETS[kind])
    if not names:
        print(f"등록된 {kind} 대상이 없습니다. TARGETS 를 채우세요.")
    for n in names:
        print(f"[{kind}] {n}")
        collect(n, kind)
