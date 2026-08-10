# -*- coding: utf-8 -*-
"""광고를 **파서로** 다시 읽는다. 지금까지 통짜 문자열로 쓰고 있었다.

`extract_ads.py` 는 HWP 에서 글자만 긁어 `ads.jsonl` 에 문자열 하나로 넣었다.
그런데 `cg_ocr_vlm/document-processor` 가 같은 파일을 이렇게 읽는다.

    표 17행 × 7열, 셀 단위로 분리     「대출금리 | 최저 연 4.45% ~ 최대 연 5.45%」
    run_style  size_pt · bold · color   시인성 판정에 필요
    bbox · page_number                  위치 표시에 필요
    native_anchor.structural_path       「s1.p1.r1.tbl1.tr1.tc1.p1.r1」 역추적

**통짜로 뭉개면서 셋을 다 잃었다.**

    글자 크기가 없으니   「유의사항 글자크기 작음」 판정 불가
    표 셀이 없으니      「'26.3.12」가 무엇의 기준일인지 모름 (바인딩 소실)
    좌표가 없으니       어디를 고쳐야 하는지 못 짚음

이 파서는 다른 저장소(cg_ocr_vlm)의 것이라 그쪽 venv 로 돌린다. 우리 저장소에
의존성을 들이지 않는다 — 파이썬 3.13 이 필요하고 우리는 3.14 다.

  python rag/parse_ads.py            # 파서 venv 를 찾아 실행
  python rag/parse_ads.py --show 2026_001_대출성
"""
import os
import re
import sys
import json

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import paths as P
import subprocess
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
SRC = P.SAMPLE_DIR

# ⚠ **폐쇄망에서는 이대로 못 돈다.** 다른 저장소(`cg_ocr_vlm`)의 venv 파이썬을
# subprocess 로 부른다 — 그 저장소가 없으면 죽고, DAP 반입 대상도 아니다.
# `ads_parsed.jsonl` 이 이 스크립트로만 만들어지고 측정·판정이 전부 그 파일에
# 기대므로, 옮길 때는 둘 중 하나를 해야 한다.
#   ① document-processor 를 같은 환경에 설치하고 `PARSE_ADS_PYTHON` 을 비운다
#      (그러면 이 인터프리터에서 바로 돈다)
#   ② 외부망에서 `ads_parsed.jsonl` 을 만들어 산출물만 반입한다
DP = os.environ.get(
    "DOC_PROCESSOR_DIR",
    os.path.join(os.path.dirname(ROOT), "cg_ocr_vlm", "document-processor"))
PY = os.environ.get("PARSE_ADS_PYTHON",
                    os.path.join(DP, ".venv", "Scripts", "python.exe"))
OUT = os.path.join(RAG, "ads_parsed.jsonl")
NL = chr(10)

# 파서 venv 안에서 돌 코드. **여기서 필요한 것만 뽑아 넘긴다** — 파서 원본 JSON 은
# 이미지 base64 까지 들어 있어 한 건에 수 MB 다. 그대로 들고 오면 못 쓴다.
RUNNER = r'''
import sys, json, glob, os
from document_processor.api import _resolve_document_args

def walk(paras, out, path=(), table=None):
    """DocIR 을 훑어 **셀 단위 문단**을 뽑는다.

    표를 문단 하나로 뭉개면 「대출금리」와 「최저 연 4.45%~」가 붙어 버려서
    무엇의 값인지 모른다(바인딩 소실). 셀의 (행,열)을 남기면 그게 산다.
    """
    for p in paras:
        d = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        runs = [c for c in (d.get("content") or []) if c.get("run_style")]
        txt = (d.get("text") or "").strip()
        if txt:
            rep = max(runs, key=lambda r: len(r.get("text") or ""), default=None)
            st = (rep or {}).get("run_style") or {}
            out.append({
                "chunk_id": d.get("node_id"),
                "page": d.get("page_number"),
                "text": txt,
                "bbox": d.get("bbox"),
                "path": (d.get("native_anchor") or {}).get("structural_path"),
                "표": table,
                "style": {"size_pt": st.get("size_pt"), "bold": st.get("bold"),
                          "color": st.get("color"), "underline": st.get("underline"),
                          "highlight": st.get("highlight")},
            })
        for c in (d.get("content") or []):
            cells = c.get("cells")
            if not cells:
                continue
            tid = c.get("node_id")
            for ri, row in enumerate(cells, 1):
                for ci, cell in enumerate(row, 1):
                    walk(cell.get("paragraphs") or [], out, path,
                         {"table_id": tid, "row": ri, "col": ci,
                          "rows": c.get("row_count"), "cols": c.get("col_count")})

files = sorted(glob.glob(os.path.join(sys.argv[1], "*")))
rows = []
for f in files:
    name = os.path.basename(f)
    if name.startswith("~$"):
        continue
    try:
        r = _resolve_document_args(document=None, source_path=f)
    except Exception as e:
        rows.append({"파일": name, "오류": f"{type(e).__name__}: {e}"[:200]})
        continue
    ps = []
    walk(r.doc.paragraphs, ps)
    rows.append({"파일": name, "doc_type": str(r.source_doc_type),
                 "문단수": len(ps), "청크": ps})
print(json.dumps(rows, ensure_ascii=False))
'''


def ad_id(fname):
    """파일명 → 광고id. `ads.jsonl` 과 같은 규칙이어야 정답셋이 이어진다."""
    m = re.search(r"(\d{4})_(\d{3})[-_]([가-힣]+)", fname)
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}_{m.group(3)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--show")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    if a.show and os.path.exists(a.out):
        rows = [json.loads(l) for l in open(a.out, encoding="utf-8")]
        r = next((x for x in rows if x.get("광고id") == a.show), None)
        if not r:
            print(f"없음: {a.show}")
            return
        print(f"== {r['광고id']} ==  청크 {len(r['청크'])}개")
        for c in r["청크"][:40]:
            st = c["style"]
            print(f"  {str(c['chunk_id'])[:18]:18s} "
                  f"{str(st.get('size_pt') or '-'):>5} "
                  f"{'B' if st.get('bold') else ' '} "
                  f"{(c['text'] or '')[:60]}")
        return

    if not os.path.exists(PY):
        print(f"파서 venv 가 없다: {PY}")
        return
    print(f"파서로 읽는 중… ({a.src})")
    got = subprocess.run([PY, "-c", RUNNER, a.src], capture_output=True,
                         text=True, encoding="utf-8", cwd=DP, timeout=900)
    if got.returncode != 0:
        print("파서 실행 실패:")
        print(got.stderr[-1500:])
        return
    data = json.loads(got.stdout.strip().splitlines()[-1])

    rows, fail = [], []
    for d in data:
        if d.get("오류"):
            fail.append((d["파일"], d["오류"]))
            continue
        aid = ad_id(d["파일"])
        if not aid:
            fail.append((d["파일"], "광고id 를 못 만듦"))
            continue
        # `_edited` 판본이 같은 id 로 오면 뒤엣것이 앞엣것을 덮는다. 앞엣것을 남긴다
        # — `ads.jsonl` 도 첫 것을 쓰므로 정답셋과 어긋나지 않게 맞춘다.
        if any(r["광고id"] == aid for r in rows):
            continue
        rows.append({"광고id": aid, "파일": d["파일"], "doc_type": d["doc_type"],
                     "청크": d["청크"],
                     "text": NL.join(c["text"] for c in d["청크"])})

    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + NL)

    import statistics
    n = [len(r["청크"]) for r in rows]
    sized = sum(1 for r in rows for c in r["청크"]
                if (c["style"] or {}).get("size_pt"))
    tot = sum(n)
    print(f"\n파싱 {len(rows)}건 · 실패 {len(fail)}건")
    print(f"  청크 합계 {tot:,} · 광고당 중앙 {statistics.median(n) if n else 0:.0f}")
    print(f"  글자크기가 있는 청크 {sized:,}/{tot:,} "
          f"({sized/max(tot,1)*100:.0f}%)")
    print(f"  저장: {a.out}")
    if fail:
        print("\n실패:")
        for f_, e in fail:
            print(f"  {f_[:44]:46s} {e[:70]}")
    print("\n비교 — 지금 쓰던 ads.jsonl 은 광고당 청크 1개(통짜)다.")


if __name__ == "__main__":
    main()
