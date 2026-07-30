# -*- coding: utf-8 -*-
"""
금융위원회(fsc.go.kr) 정책마당 첨부자료 수집 어댑터.

협회 실무자료는 회원사에만 공문으로 배포돼 자동 수집이 불가능하지만,
**금융위·금감원이 낸 자료는 공개 게시판에 올라온다.** 「금융광고규제 가이드라인」이
그 경우라 여기서 받는다.

게시물 번호(upperNo)를 하드코딩하지 않고 **제목 검색으로 찾는다** — 개정판이
새 게시물로 올라오면 번호가 바뀌기 때문(은행연 어댑터와 같은 방식).

변경 감지 키는 첨부파일 내용의 sha256. 게시물이 새로 올라와도 첨부 내용이
같으면 변경으로 보지 않는다.
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

SITE = "https://www.fsc.go.kr"
LIST_URL = SITE + "/po010101"          # 정책마당 > 정책일반
FILE_URL = SITE + "/comm/getFile"
UA = {"User-Agent": "Mozilla/5.0"}

# 현재 등록 대상 없음.
#
# 금융위 게시판 자료는 **기관이 버전 식별자를 주지 않는다.** 법제처는 일련번호(MST),
# 금투협은 이력번호(historySeq)를 발급하지만, 게시판은 우리가 제목·파일명 규칙으로
# 짐작하는 수밖에 없다. 개정판 첨부 이름이 조금만 달라져도 놓친다.
#
# 그래서 **개정을 확실히 잡을 수 있는 자료만 자동 수집한다**는 원칙에 따라
# 금융위 가이드라인 2건은 수동 관리로 옮겼다(파일은 output/_reference/ 에 보관).
# 게시판 구조·검색 방식은 아래 함수에 그대로 남아 있으므로,
# 확실히 추적할 수 있는 자료가 생기면 검색어·파일조건만 적으면 동작한다.
TARGETS = {}


def _safe(name):
    import law_scraper
    return law_scraper._safe(name)


def _get(url, retries=3):
    ctx = ssl.create_default_context()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                return r.read()
        except Exception as e:                      # 일시적 오류는 재시도
            last = e
            log.warning("fsc 요청 실패(%d/%d) %s: %s", i + 1, retries, url[:90], e)
    raise last


def _find_posts(keyword):
    """제목 검색 결과 [(게시물번호, 제목)] — 최신순.

    검색어가 여러 게시물에 걸리므로(예: '광고' 관련 다른 보도자료) 첫 번째를
    그냥 쓰면 안 된다. 호출부에서 첨부 조건까지 맞는 게시물을 골라야 한다.
    """
    url = f"{LIST_URL}?curPage=1&srchKey=&srchText={urllib.parse.quote(keyword)}"
    html = _get(url).decode("utf-8", "ignore")
    out, seen = [], set()
    for no, title in re.findall(
            r'href="[^"]*?/po010101/(\d+)[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{6,160})', html):
        if no in seen:
            continue
        seen.add(no)
        out.append((no, re.sub(r"\s+", " ", title).strip()))
    return out


def _attachments(upper_no):
    """게시물의 첨부파일 [(파일명, fileNo)] 목록.

    같은 fileNo 가 '파일다운로드' 라는 대체텍스트로 한 번 더 잡히므로
    실제 파일명(확장자가 있는 쪽)만 남긴다.
    """
    html = _get(f"{LIST_URL}/{upper_no}").decode("utf-8", "ignore")
    out = []
    for m in re.finditer(
            r'getFile\?srvcId=BBSTY1&(?:amp;)?upperNo=%s&(?:amp;)?fileTy=ATTACH&(?:amp;)?fileNo=(\d+)'
            r'[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,160})' % upper_no, html):
        fname = re.sub(r"\s+", " ", m.group(2)).strip()
        if "." in fname:                    # '파일다운로드' 같은 대체텍스트 제외
            out.append((fname, m.group(1)))
    return out


def _pick(atts, cond, ext):
    for fname, no in atts:
        low = fname.lower()
        if low.endswith(ext) and all(c in fname for c in cond):
            return fname, no
    return None, None


def current_meta(name, kind="fsc"):
    """{name, 게시물번호, 제목, 파일명, fileNo, sha256, 버전키} — 못 찾으면 None."""
    spec = TARGETS.get(name)
    if not spec:
        log.error("fsc 대상에 등록되지 않은 이름: %s", name)
        return None
    # 검색 결과를 최신순으로 훑으며 **조건에 맞는 첨부가 실제로 있는** 게시물을 고른다
    no = title = fname = fno = None
    for cand_no, cand_title in _find_posts(spec["검색어"]):
        f, n = _pick(_attachments(cand_no), spec["파일조건"], spec["확장자"])
        if n:
            no, title, fname, fno = cand_no, cand_title, f, n
            break
    if not fno:
        log.error("검색 결과 중 조건에 맞는 첨부를 가진 게시물이 없음: %s", name)
        return None
    data = _get(f"{FILE_URL}?srvcId=BBSTY1&upperNo={no}&fileTy=ATTACH&fileNo={fno}")
    if len(data) < 1024:
        log.error("첨부가 너무 작음(%d바이트) — 다운로드 실패로 본다: %s", len(data), name)
        return None
    sha = hashlib.sha256(data).hexdigest()
    return {"name": name, "kind": "fsc", "게시물번호": no, "제목": title,
            "파일명": fname, "fileNo": fno, "sha256": sha, "bytes": data,
            # 게시물 번호가 바뀌어도 내용이 같으면 변경 아님 → 키는 내용 해시.
            # MST/시행일자/버전번호는 법제처 전용 필드지만 check_updates 가 공통으로
            # 쓰므로 파일 기반 어댑터(kfb/crefia)와 같은 방식으로 채워 준다.
            "버전키": sha[:16], "공식버전키": sha[:16],
            "MST": sha[:12], "ID": no, "시행일자": "", "버전번호": sha[:12]}


def _version_key(meta):
    return meta["버전키"]


def collect(name, kind="fsc", want_files=True, verbose=True):
    import file_text
    meta = current_meta(name)
    if not meta:
        raise RuntimeError(f"금융위 게시판에서 찾지 못함: {name}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    fdir = os.path.join(out_dir, "files", _safe(name))
    os.makedirs(fdir, exist_ok=True)
    fpath = os.path.join(fdir, meta["파일명"])
    # 0바이트 껍데기가 남지 않도록 메모리에 다 받은 뒤에 쓴다
    with open(fpath, "wb") as f:
        f.write(meta["bytes"])

    text = file_text.extract(fpath)
    rec = {
        "법령명": name, "종류": "가이드라인", "발행기관": "금융위원회·금융감독원",
        "게시물번호": meta["게시물번호"], "게시물제목": meta["제목"],
        "버전키": meta["버전키"], "공식버전키": meta["공식버전키"],
        "본문해시": meta["sha256"],
        "출처": f"{LIST_URL}/{meta['게시물번호']}",
        "통계": {"본문길이": len(text)},
        "본문": text,
        "첨부": [{"파일명": meta["파일명"], "sha256": meta["sha256"],
                  "바이트": len(meta["bytes"])}],
    }
    with open(os.path.join(out_dir, _safe(name) + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, _safe(name) + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if verbose:
        print(f"  → 본문 {len(text):,}자 · 첨부 {meta['파일명']}")
        print(f"  → 저장: output/{_safe(name)}.json, output/{_safe(name)}.txt")
    return rec


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for n in (sys.argv[1:] or list(TARGETS)):
        print(f"[{n}]")
        collect(n)
