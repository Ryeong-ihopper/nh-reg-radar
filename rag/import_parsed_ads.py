# -*- coding: utf-8 -*-
"""`nh-parsing-test` 의 파싱 결과를 광고 입력으로 들여온다.

**직접 파싱하지 않는다.** 옆 저장소(`cg_ocr_vlm/nh-parsing-test`)가 이미 실물
광고 19건을 다 파싱해 뒀고, 우리가 `parse_ads.py` 로 만든 것보다 낫다.

    | | nh-parsing-test | 우리 parse_ads.py |
    |---|---|---|
    | 이미지 PDF·PNG 2건 | **OCR 됨**(1,945자·1,716자) | 0자 — document-processor 는 OCR 이 없다 |
    | 대출성 광고 | 1,969자 | 9,037자 — **병합 셀이 5~7회씩 중복** |
    | 위치 정보 | bbox·confidence·역할(본문/유의사항) | 없음 |

중복이 왜 문제인가 — 같은 유의문구가 5번 들어가면 판정 LLM 이 「표시가 충분하다」
쪽으로 기울고, 광고문을 자를 때 그 중복이 앞자리를 다 먹어 뒷부분(부대비용·
수수료 고지)이 통째로 잘린다. 실측에서 대출성 판정이 1/10 이었다.

산출물은 `ads_parsed.jsonl` 과 **같은 모양**이라 아래 것들이 그대로 읽는다.
`pipeline.py` · `twohop2.py` · `full_colab.ipynb`

  python rag/import_parsed_ads.py                 # 미리보기
  python rag/import_parsed_ads.py --write         # ads_parsed.jsonl 갱신
"""
import os
import re
import sys
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
OUT = os.path.join(RAG, "ads_parsed.jsonl")

# 옆 저장소 산출물. 경로는 환경변수로 바꿀 수 있다.
SRC = os.environ.get(
    "NH_PARSED_DIR",
    os.path.join(os.path.dirname(ROOT), "cg_ocr_vlm", "nh-parsing-test",
                 "out", "json"))

# 「NH농협은행-2026_002-대출성」 → 「2026_002_대출성」 (기존 광고id 규칙)
_ID = re.compile(r"(\d{4})[_-](\d{3})[_-](예금성|대출성|투자성|보장성)")


def ad_id(doc_id):
    m = _ID.search(str(doc_id or ""))
    return f"{m.group(1)}_{m.group(2)}_{m.group(3)}" if m else None


def to_ad(d):
    """파싱 JSON → 광고 한 건(ads_parsed.jsonl 모양)."""
    aid = ad_id(d.get("doc_id") or "")
    if not aid:
        return None
    chunks, seen = [], set()
    for p in d.get("pages") or []:
        for r in p.get("regions") or []:
            for n, l in enumerate(r.get("lines") or []):
                t = (l.get("text") or "").strip()
                if not t:
                    continue
                # **같은 문장을 여러 번 담지 않는다.** 병합 셀이 펼쳐지면
                # 같은 유의문구가 5~7회씩 들어와 광고가 2배 넘게 부푼다.
                key = re.sub(r"\s+", "", t)
                if key in seen:
                    continue
                seen.add(key)
                chunks.append({
                    "chunk_id": f"{r.get('region_id') or p.get('page_no')}_{n:03d}",
                    "text": t,
                    "bbox": l.get("bbox") or r.get("bbox"),
                    "page": p.get("page_no"),
                    "역할": r.get("role"),
                    "출처": l.get("source"),
                    "confidence": l.get("confidence"),
                })
    return {
        "광고id": aid,
        "파일": d.get("source_file"),
        "doc_type": d.get("file_type"),
        "상품군": d.get("product_group"),
        "광고종류": d.get("ad_type"),
        "_파싱경로": sorted({p.get("parse_route") for p in (d.get("pages") or [])
                          if p.get("parse_route")}),
        "청크": chunks,
        "text": "\n".join(c["text"] for c in chunks),
    }


def load_all(src=SRC):
    if not os.path.isdir(src):
        raise FileNotFoundError(
            f"파싱 결과 폴더가 없다: {src}\n"
            f"  → NH_PARSED_DIR 환경변수로 지정한다")
    out = []
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        if "pages" not in d:
            continue
        ad = to_ad(d)
        if ad and ad["text"].strip():
            out.append(ad)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--write", action="store_true", help="ads_parsed.jsonl 갱신")
    a = ap.parse_args()

    ads = load_all(a.src)
    old = {}
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            x = json.loads(l)
            old.setdefault(x["광고id"], x)

    print(f"{'광고id':20s} {'경로':13s} {'글자':>6s} {'청크':>5s}   전(글자/청크)")
    for ad in ads:
        o = old.get(ad["광고id"])
        was = (f"{len((o.get('text') or '')):6d} / {len(o.get('청크') or []):4d}"
               if o else "        (없음)")
        print(f"{ad['광고id']:20s} {','.join(ad['_파싱경로']):13s} "
              f"{len(ad['text']):6d} {len(ad['청크']):5d}   {was}")

    gone = set(old) - {a_["광고id"] for a_ in ads}
    if gone:
        print(f"\n※ 새 자료에 없는 광고 {len(gone)}건: {', '.join(sorted(gone))}")

    if a.write:
        with open(OUT, "w", encoding="utf-8") as f:
            for ad in ads:
                f.write(json.dumps(ad, ensure_ascii=False) + "\n")
        print(f"\n저장: {OUT}  ({len(ads)}건)")
    else:
        print("\n(미리보기다. 실제로 바꾸려면 --write)")


if __name__ == "__main__":
    main()
