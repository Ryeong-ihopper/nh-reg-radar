# -*- coding: utf-8 -*-
"""
여신금융협회(CREFIA) 자율규제규정 어댑터  ── m.crefia.or.kr (모바일, 서버렌더링)

규정 본문이 웹 텍스트로 없고 HWP/PDF 첨부로만 제공됨. 따라서:
  1) 모바일 자율규제 목록 페이지에서 대상 규정의 첨부 파일명을 찾고
  2) /common/downloadFile.do 로 파일을 라이브 다운로드
  3) SHA-256 해시로 변경 감지(= 버전키), document-processor 로 텍스트/표 파싱

check_updates.py 어댑터 인터페이스: current_meta / _version_key / collect
"""
import os
import re
import sys
import json
import html as htmllib
import hashlib
import urllib.parse
import urllib.request
import name_match

sys.stdout.reconfigure(encoding="utf-8")

import file_text   # PDF/HWP → 텍스트(document-processor 우선)

SITE = "https://m.crefia.or.kr"
LIST_URL = SITE + "/mobile/infocenter/regulation/selfRegulation.xx"
DL_URL = SITE + "/common/downloadFile.do"
FILE_TYPE = "selfRegulation"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
FILE_DIR = os.path.join(OUT_DIR, "files")

_cache = {}   # name -> {"filename", "bytes", "sha256"}  (한 실행 내 중복 다운로드 방지)


def _get(url, binary=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": LIST_URL})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", errors="replace")


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


def _norm(s):
    """비교용 정규화: [..]·(..) 제거 후 한글/숫자만 남김."""
    s = htmllib.unescape(s)
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    return re.sub(r"[^가-힣0-9]", "", s)


def _list_files():
    """목록 페이지 → [파일명, ...] (fn_downloadFile 의 selfRegulation 항목)."""
    html = _get(LIST_URL)
    files = []
    for m in re.finditer(r"fn_downloadFile\('([^']+)'\s*,\s*'selfRegulation'", html):
        files.append(m.group(1))
    return files


def _match_file(name):
    """규정명 → 목록의 실제 파일명. 공통 규칙(name_match)으로 귀속을 가린다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sibs = name_match.siblings_of(name, "crefia", os.path.join(root, "targets.json"))
    return name_match.pick(name, _list_files(), sibs)


def _download(filename):
    url = f"{DL_URL}?fileName={urllib.parse.quote(filename)}&fileType={FILE_TYPE}&keyNum=&date=&pFileEnc="
    return _get(url, binary=True)


def current_meta(name, kind="crefia"):
    filename = _match_file(name)
    if not filename:
        return None
    data = _download(filename)
    sha = hashlib.sha256(data).hexdigest()
    _cache[name] = {"filename": filename, "bytes": data, "sha256": sha}
    # 파일명에서 시행/개정일 추출 시도 (예: (2023.2.1._시행), (2022.05.02. 개정))
    dm = re.search(r"(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})", filename)
    eff = f"{dm.group(1)}{int(dm.group(2)):02d}{int(dm.group(3)):02d}" if dm else ""
    return {"name": name, "kind": "crefia", "filename": filename,
            "MST": sha[:12], "ID": sha[:12], "시행일자": eff,
            "버전번호": sha[:12], "sha256": sha}


def _version_key(meta):
    return "sha256:" + meta["sha256"]


def collect(name, kind="crefia", want_files=True, verbose=True):
    c = _cache.get(name)
    if not c:
        meta = current_meta(name, kind)
        if not meta:
            if verbose:
                print(f"  → '{name}' 여신협 목록에서 못 찾음")
            return None
        c = _cache[name]
    filename, data, sha = c["filename"], c["bytes"], c["sha256"]

    # 원본 파일 저장
    fdir = os.path.join(FILE_DIR, _safe(name))
    os.makedirs(fdir, exist_ok=True)
    fpath = os.path.join(fdir, _safe(filename))
    with open(fpath, "wb") as f:
        f.write(data)

    # 텍스트/표 파싱
    text = file_text.extract(fpath)
    # 본문 상단의 제정/개정 이력에서 가장 최근 날짜 = 최근개정일
    dates = re.findall(r"(\d{4})[.\s]+(\d{1,2})[.\s]+(\d{1,2})\.?\s*(?:제정|개정|시행)",
                       text[:1500])
    eff = ""
    if dates:
        ymd = max(f"{y}{int(m):02d}{int(d):02d}" for y, m, d in dates)
        eff = ymd
    if verbose:
        print(f"  → 다운로드 {len(data):,}B · 파싱 {len(text):,}자 · "
              f"시행 {eff or '?'} · sha {sha[:12]}")

    os.makedirs(OUT_DIR, exist_ok=True)
    base = _safe(name)
    record = {
        "법령명": name, "종류": "crefia_규정", "발행기관": "여신금융협회",
        "원본파일": filename, "sha256": sha, "버전키": _version_key({"sha256": sha}),
        "시행일자": eff, "출처": LIST_URL,
        "통계": {"본문길이": len(text)},
        "본문": text,
    }
    with open(os.path.join(OUT_DIR, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    header = (f"{name}\n[여신금융협회 자율규제규정] 시행 {eff or '?'} · "
              f"원본 {filename} · sha {sha[:12]}")
    with open(os.path.join(OUT_DIR, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(header + "\n" + "=" * 70 + "\n\n" + text)
    if verbose:
        print(f"  → 저장: output/{base}.json, output/{base}.txt (원본: files/{base}/)")
    return record


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "여신전문금융회사 등의 광고에 관한 규정",
        "여신전문금융회사 등의 광고에 관한 규정 세부지침",
    ]
    for t in targets:
        print(f"[CREFIA] {t}")
        collect(t)
