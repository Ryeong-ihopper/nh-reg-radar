# -*- coding: utf-8 -*-
"""첨부파일 추출 상태 점검 (텍스트 글자수 / 이미지 수 / 실패 여부).

품질 점검에서 쓰려고 분리했다. 첨부가 762개라 매번 다 여는 건 20분 넘게 걸리므로
**파일 내용 해시로 캐시**한다. 파일이 안 바뀌면 두 번째 실행부터는 즉시 끝난다.

여기서 잡으려는 문제 두 가지:
  1) 추출 실패 — 법제처가 HWPX(OOXML)를 .hwp 확장자로 주는 경우가 있어
     구형 OLE 파서가 열지 못한다. 같은 이름 PDF 가 있으면 실질 피해는 없지만,
     없으면 그 별표는 내용이 아예 없는 셈이 된다.
  2) 이미지 미추출 — 규정에 그림으로 들어간 광고 예시·도표가 텍스트에 없으면
     개정으로 그림이 바뀌어도 변경 감지가 못 잡는다.
"""
import os
import json
import hashlib

import applog

log = applog.get_logger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(ROOT, "output", "_audit.json")
SUPPORTED = (".pdf", ".hwp", ".hwpx", ".docx")
# 판정 방식이 바뀌면 올린다 → 옛 캐시를 자동으로 버린다
RULE_VER = 1

_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            c = json.load(open(CACHE_PATH, encoding="utf-8"))
            _cache = c if c.get("_ver") == RULE_VER else {"_ver": RULE_VER}
        except Exception:
            _cache = {"_ver": RULE_VER}
    return _cache


def save():
    if _cache:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        json.dump(_cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False)


def audit(path):
    """{chars, imgs, err} — 파일 하나의 추출 상태."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        return {"chars": 0, "imgs": 0, "err": ""}    # zip/xlsx 등은 대상 아님
    cache = _load()
    key = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    if key in cache:
        return cache[key]
    import file_text
    from document_processor import DocIR
    rec = {"chars": 0, "imgs": 0, "err": ""}
    try:
        ir = DocIR.from_file(path)
        rec["imgs"] = len(getattr(ir, "assets", None) or {})
        rec["chars"] = len(file_text.extract_docproc(path))
    except Exception as e:
        rec["err"] = f"{type(e).__name__}: {e}"[:150]
    cache[key] = rec
    return rec


def audit_dir(fdir):
    """폴더 안 첨부 전체 → {파일명: {chars, imgs, err}}"""
    if not os.path.isdir(fdir):
        return {}
    out = {}
    for f in sorted(os.listdir(fdir)):
        p = os.path.join(fdir, f)
        if os.path.isfile(p) and os.path.splitext(f)[1].lower() in SUPPORTED:
            out[f] = audit(p)
    return out


def seed_from(scan_json):
    """이미 돌려 둔 전수 스캔 결과로 캐시를 채운다(첫 실행 20분을 아낀다)."""
    cache = _load()
    n = 0
    for r in json.load(open(scan_json, encoding="utf-8")):
        if not os.path.exists(r["file"]):
            continue
        key = hashlib.sha256(open(r["file"], "rb").read()).hexdigest()[:16]
        cache[key] = {"chars": r.get("chars", 0), "imgs": r.get("imgs", 0),
                      "err": r.get("err", "")}
        n += 1
    save()
    return n


if __name__ == "__main__":
    import sys
    import glob
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "--seed":
        print("캐시 주입:", seed_from(sys.argv[2]), "건")
        raise SystemExit
    files = sorted(f for f in glob.glob(os.path.join(ROOT, "output/files/*/*"))
                   if os.path.splitext(f)[1].lower() in SUPPORTED)
    err = img = 0
    for i, f in enumerate(files, 1):
        r = audit(f)
        err += bool(r["err"])
        img += bool(r["imgs"])
        if i % 100 == 0:
            print(f"  {i}/{len(files)} …", flush=True)
    save()
    print(f"첨부 {len(files)}개 · 추출 실패 {err} · 이미지 보유 {img}")
