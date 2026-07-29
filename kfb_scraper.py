# -*- coding: utf-8 -*-
"""
전국은행연합회(KFB) 자율규제 규정 어댑터  ── www.kfb.or.kr (euc-kr, 세션 필요)

규정은 게시판 첨부(HWP/PDF)로만 제공. 다운로드가 4단계 체인:
  1) 목록 페이지 GET (PHPSESSID 쿠키 획득)
  2) 상세 페이지(reform_info_view.php?idx=N) GET → enc_para 토큰 추출
     (토큰은 요청마다 재생성되므로 같은 세션에서 즉시 사용)
  3) /include/download.php?enc_para=토큰 GET → JS 리다이렉트 URL(down.kfb.or.kr) 추출
  4) 리다이렉트 URL을 euc-kr 퍼센트 인코딩해 GET → 실제 파일

변경 감지: 파일 SHA-256. 파싱: document-processor(file_text).
check_updates.py 어댑터 인터페이스: current_meta / _version_key / collect
"""
import os
import re
import sys
import json
import hashlib
import http.client
import ssl
import time
import urllib.parse
import urllib.error
import urllib.request
import http.cookiejar

sys.stdout.reconfigure(encoding="utf-8")

import file_text

BASE = "https://www.kfb.or.kr/"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "output")
FILE_DIR = os.path.join(OUT_DIR, "files")

# 규정명 → 게시판 제목 검색 키워드. idx 는 하드코딩하지 않고 검색으로 자동 발견한다
# (개정이 새 게시물로 올라와 idx 가 바뀌어도 자동 추적됨).
KEYWORDS = {
    "은행 광고심의 기준 및 세칙": "광고심의",
    "은행 광고심의 기준": "광고심의",
    "은행 광고심의 기준 세칙": "광고심의",
}

_cache = {}   # name -> {"filename","bytes","sha256","idx"}


def _norm(s):
    return re.sub(r"[^가-힣0-9]", "", s)


def _resolve_idx(op, name):
    """게시판 제목 검색으로 규정에 맞는 게시물 idx 를 자동 발견."""
    kw = KEYWORDS.get(name, name)
    sw = urllib.parse.quote(kw, encoding="euc-kr")
    url = BASE + "publicdata/reform_info.php?col=TITLE&sw=" + sw
    h = _get(op, url)[0].decode("euc-kr", "replace")
    # readRun(idx) 앞의 텍스트(제목)와 함께 후보 수집
    cands = []
    for m in re.finditer(r"readRun\((\d+)\)", h):
        ctx = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[m.start() - 500:m.start()]))
        cands.append((int(m.group(1)), _norm(ctx)))
    if not cands:
        return None
    # 규정명 토큰이 가장 많이 겹치는 게시물 선택
    toks = [t for t in re.split(r"\s+", name) if len(_norm(t)) >= 2]
    best = max(cands, key=lambda c: sum(_norm(t) in c[1] for t in toks))
    return best[0]


def _opener():
    cj = http.cookiejar.CookieJar()
    context = ssl.create_default_context()
    # KFB 서버는 일부 최신 OpenSSL 기본값과 handshake 호환 문제가 있다.
    # 인증서 검증은 유지하고 이 서버 연결에만 레거시 cipher 협상을 허용한다.
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=context),
    )
    op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "Chrome/120 Safari/537.36"), ("Accept-Language", "ko-KR,ko;q=0.9")]
    return op


def _get(op, url, ref=None, retries=3):
    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(url)
        if ref:
            req.add_header("Referer", url if ref is True else ref)
        try:
            with op.open(req, timeout=60) as r:
                return r.read(), r.headers
        except (ssl.SSLError, http.client.IncompleteRead, urllib.error.URLError,
                TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt + 1 < retries:
                time.sleep(0.5 * (attempt + 1))
    raise last_error


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


def _download(name):
    """제목 검색으로 idx 자동 발견 후 첨부파일을 4단계 체인으로 받아
    (idx, 파일명, bytes) 반환. 전 과정 같은 세션(쿠키) 유지."""
    op = _opener()
    list_url = BASE + "publicdata/reform_info.php"
    _get(op, list_url)                                     # 1) 쿠키
    idx = _resolve_idx(op, name)                           # 게시물 idx 자동 발견
    if idx is None:
        raise RuntimeError("게시판 제목 검색에서 규정을 찾지 못함")
    detail = BASE + f"publicdata/reform_info_view.php?idx={idx}&col=TITLE&pg=1"
    h = _get(op, detail, list_url)[0].decode("euc-kr", "replace")   # 2) 상세
    m = re.search(r"include/download\.php\?enc_para=([^\"']+)", h)
    if not m:
        raise RuntimeError("enc_para 토큰을 찾지 못함")
    h2 = _get(op, BASE + "include/download.php?enc_para=" + m.group(1),
              detail)[0].decode("euc-kr", "replace")        # 3) 리다이렉트 페이지
    loc = re.search(r'location\.href="([^"]+)"', h2)
    if not loc:
        raise RuntimeError("리다이렉트 URL을 찾지 못함")
    sp = urllib.parse.urlsplit(loc.group(1))
    q = urllib.parse.parse_qs(sp.query)
    filename = q.get("filename", [""])[0] or q.get("realfile", [""])[0]
    newq = "&".join(f"{k}=" + urllib.parse.quote(v[0], encoding="euc-kr")
                    for k, v in q.items())                  # 4) euc-kr 인코딩
    final = urllib.parse.urlunsplit((sp.scheme, sp.netloc, sp.path, newq, ""))
    data = _get(op, final, detail)[0]
    return idx, filename, data


def current_meta(name, kind="kfb"):
    if name not in KEYWORDS:
        return None
    idx, filename, data = _download(name)
    sha = hashlib.sha256(data).hexdigest()
    _cache[name] = {"filename": filename, "bytes": data, "sha256": sha, "idx": idx}
    return {"name": name, "kind": "kfb", "filename": filename, "idx": idx,
            "MST": sha[:12], "ID": str(idx), "시행일자": "",
            "버전번호": sha[:12], "sha256": sha}


def _version_key(meta):
    return "sha256:" + meta["sha256"]


def collect(name, kind="kfb", want_files=True, verbose=True):
    c = _cache.get(name)
    if not c:
        meta = current_meta(name, kind)
        if not meta:
            if verbose:
                print(f"  → '{name}' KFB 검색 키워드 없음/미발견(KEYWORDS 확인)")
            return None
        c = _cache[name]
    filename, data, sha, idx = c["filename"], c["bytes"], c["sha256"], c.get("idx")

    fdir = os.path.join(FILE_DIR, _safe(name))
    os.makedirs(fdir, exist_ok=True)
    fpath = os.path.join(fdir, _safe(filename) or "attachment.hwp")
    with open(fpath, "wb") as f:
        f.write(data)

    text = file_text.extract(fpath)
    dates = re.findall(r"(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})\.?\s*(?:제정|개정|시행)",
                       text[:1500])
    eff = max((f"{y}{int(m):02d}{int(d):02d}" for y, m, d in dates), default="")
    if verbose:
        print(f"  → 다운로드 {len(data):,}B · 파싱 {len(text):,}자 · "
              f"시행 {eff or '?'} · sha {sha[:12]}")

    os.makedirs(OUT_DIR, exist_ok=True)
    base = _safe(name)
    record = {
        "법령명": name, "종류": "kfb_규정", "발행기관": "전국은행연합회",
        "게시물idx": idx, "원본파일": filename,
        "sha256": sha, "버전키": _version_key({"sha256": sha}), "시행일자": eff,
        "출처": BASE + f"publicdata/reform_info_view.php?idx={idx}",
        "통계": {"본문길이": len(text)}, "본문": text,
    }
    with open(os.path.join(OUT_DIR, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    header = (f"{name}\n[전국은행연합회 자율규제] 시행 {eff or '?'} · "
              f"원본 {filename} · sha {sha[:12]}")
    with open(os.path.join(OUT_DIR, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(header + "\n" + "=" * 70 + "\n\n" + text)
    if verbose:
        print(f"  → 저장: output/{base}.json, output/{base}.txt (원본: files/{base}/)")
    return record


if __name__ == "__main__":
    targets = sys.argv[1:] or ["은행 광고심의 기준 및 세칙"]
    for t in targets:
        print(f"[KFB] {t}")
        collect(t)
