# -*- coding: utf-8 -*-
"""
금융감독원(fss.or.kr) 보도자료 첨부 수집 어댑터.

금감원은 「주요 금융상품 광고 점검결과 조치 및 유의사항 안내」처럼 **실제 광고를
점검하고 지적사항을 정리한 자료**를 보도자료로 낸다. 규정은 아니지만 심의 실무에
바로 쓰이므로 수집한다.

금융위(fsc_scraper)와 게시판 구조가 다르다.
  - 목록: /fss/bbs/B0000188/list.do?menuNo=200218&searchCnd=1&searchWrd=<검색어>
  - 본문: /fss/bbs/B0000188/view.do?nttId=<번호>&menuNo=200218
  - 첨부: /fss/cmmn/file/fileDown.do?menuNo=200218&atchFileId=<id>&fileSn=<n>&bbsId=

게시물 번호를 하드코딩하지 않고 **제목 검색으로 찾는다.** 이 시리즈는 ①대출 ②ETF
③보험 순으로 편이 늘고 있어서, 같은 검색어로 새 편이 올라오면 그대로 잡힌다.

변경 감지 키는 첨부 PDF 의 sha256.
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

SITE = "https://www.fss.or.kr"
LIST_URL = SITE + "/fss/bbs/B0000188/list.do"      # 보도자료
VIEW_URL = SITE + "/fss/bbs/B0000188/view.do"
MENU = "200218"
UA = {"User-Agent": "Mozilla/5.0"}

# 규정명 → 검색어 + 첨부 파일명 조건
# 같은 검색어에 여러 편이 걸리므로 파일명 조건으로 편을 구분한다.
# 현재 등록 대상 없음.
#
# 금감원 보도자료 게시판에는 「주요 금융상품 광고 점검결과 조치 및 유의사항 안내」
# 같은 자료가 있고 내용도 유용하지만, **보도자료 본문뿐이라 심의에서 인용할 수 있는
# 근거가 아니다**(체크리스트·심의사례 인용 실측 0회). 그래서 수집 대상에 넣지 않는다.
#
# 금감원이 별첨 형태의 가이드라인·기준을 내면 그때 아래에 추가한다.
# 게시판 구조는 파악해 두었으므로 검색어·파일조건만 적으면 동작한다.
TARGETS = {}


def _safe(name):
    import law_scraper
    return law_scraper._safe(name)


def _ctx():
    c = ssl.create_default_context()
    # 금감원 서버는 체인 검증에서 걸리는 경우가 있어 완화한다(공개 게시물 조회 전용).
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _get(url, binary=False, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90, context=_ctx()) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "ignore")
        except Exception as e:
            last = e
            log.warning("fss 요청 실패(%d/%d) %s: %s", i + 1, retries, url[:90], e)
    raise last


def _find_posts(keyword):
    """제목 검색 결과 [(nttId, 제목)] — 최신순."""
    url = (f"{LIST_URL}?menuNo={MENU}&searchCnd=1&searchWrd="
           + urllib.parse.quote(keyword))
    html = _get(url)
    out, seen = [], set()
    for m in re.finditer(r'nttId=(\d+)[^>]*>(.*?)</a>', html, re.S):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if len(t) > 6 and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), t))
    return out


def _attachments(ntt_id):
    """[(파일명, 다운로드 URL)] — 실제 파일명이 있는 항목만."""
    html = _get(f"{VIEW_URL}?nttId={ntt_id}&menuNo={MENU}")
    out = []
    for m in re.finditer(
            r'href="(/fss/cmmn/file/fileDown\.do\?[^"]+)"[^>]*>\s*<span class="file-name">'
            r'.*?<span class="name">\s*([^<]+?)\s*(?:<|$)', html, re.S):
        fname = re.sub(r"\s+", " ", m.group(2)).strip()
        if "." in fname:
            out.append((fname, SITE + m.group(1).replace("&amp;", "&")))
    return out


def current_meta(name, kind="fss"):
    spec = TARGETS.get(name)
    if not spec:
        log.error("fss 대상에 등록되지 않은 이름: %s", name)
        return None
    # 검색 결과를 최신순으로 훑으며 **조건에 맞는 첨부가 실제로 있는** 게시물을 고른다
    for no, title in _find_posts(spec["검색어"]):
        for fname, url in _attachments(no):
            if (fname.lower().endswith(spec["확장자"])
                    and all(c in fname for c in spec["파일조건"])):
                data = _get(url, binary=True)
                if len(data) < 1024:
                    log.error("첨부가 너무 작음(%d바이트): %s", len(data), name)
                    return None
                sha = hashlib.sha256(data).hexdigest()
                return {"name": name, "kind": "fss", "게시물번호": no, "제목": title,
                        "파일명": fname, "sha256": sha, "bytes": data,
                        "버전키": sha[:16], "공식버전키": sha[:16],
                        # 법제처 전용 필드지만 check_updates 가 공통으로 쓴다
                        "MST": sha[:12], "ID": no, "시행일자": "", "버전번호": sha[:12]}
    log.error("검색 결과 중 조건에 맞는 첨부를 가진 게시물이 없음: %s", name)
    return None


def _version_key(meta):
    return meta["버전키"]


def collect(name, kind="fss", want_files=True, verbose=True):
    import file_text
    meta = current_meta(name)
    if not meta:
        raise RuntimeError(f"금감원 게시판에서 찾지 못함: {name}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    fdir = os.path.join(out_dir, "files", _safe(name))
    os.makedirs(fdir, exist_ok=True)
    # 추출기(OpenDataLoader CLI)가 경로에 든 일부 문자에서 실패한다.
    # 실제로 대상 이름에 em-dash(—)가 있을 때 exit 1 로 죽었다.
    fpath = os.path.join(fdir, _safe(meta["파일명"]))
    with open(fpath, "wb") as f:          # 메모리에 다 받은 뒤 쓴다(0바이트 방지)
        f.write(meta["bytes"])

    text = file_text.extract(fpath)
    rec = {
        "법령명": name, "종류": "안내자료", "발행기관": "금융감독원",
        "게시물번호": meta["게시물번호"], "게시물제목": meta["제목"],
        "버전키": meta["버전키"], "공식버전키": meta["공식버전키"],
        "본문해시": meta["sha256"],
        "출처": f"{VIEW_URL}?nttId={meta['게시물번호']}&menuNo={MENU}",
        "통계": {"본문길이": len(text)},
        "본문": text,
        "첨부": [{"파일명": meta["파일명"], "sha256": meta["sha256"],
                  "바이트": len(meta["bytes"])}],
    }
    base = _safe(name)
    with open(os.path.join(out_dir, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if verbose:
        print(f"  → 본문 {len(text):,}자 · 첨부 {meta['파일명'][:50]}")
        print(f"  → 저장: output/{base}.json, output/{base}.txt")
    return rec


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for n in (sys.argv[1:] or list(TARGETS)):
        print(f"[{n}]")
        collect(n)
