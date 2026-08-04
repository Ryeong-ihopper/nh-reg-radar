# -*- coding: utf-8 -*-
"""광고 샘플(HWP/PDF/PNG) → 텍스트. 검색 파일럿의 질의 원본을 만든다.

수집기가 규정을 뽑을 때 쓰는 file_text 를 그대로 재사용한다 — 실제 서비스에서도
광고는 같은 파서를 타므로, 여기서 다른 방법으로 뽑으면 파일럿 결과가 실제와 어긋난다.

  python rag/extract_ads.py
  python rag/extract_ads.py --src "<폴더>" --out output/_rag/ads.jsonl
"""
import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import file_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = r"C:\Users\babie\OneDrive\Desktop\씨지인사이드\샘플데이터"
DEFAULT_OUT = os.path.join(ROOT, "output", "_rag", "ads.jsonl")

# 파일명이 곧 메타데이터다 — NH농협은행-2026_004-예금성.hwp
_NAME = re.compile(r"(?P<기관>[^-]+)-(?P<연도>\d{4})_(?P<번호>\d+)-(?P<상품군>[가-힣]+)")


def parse_name(fn):
    m = _NAME.search(os.path.splitext(fn)[0])
    if not m:
        return None
    d = m.groupdict()
    # `_edited` 같은 꼬리표는 같은 광고의 다른 판본이라 구분해 둔다
    d["판본"] = "수정본" if "_edited" in fn else "원본"
    d["광고id"] = f"{d['연도']}_{d['번호']}_{d['상품군']}"
    return d


def clean(text):
    """OCR/파서 산출물에서 검색에 방해되는 것만 덜어낸다.

    표 괘선(`|  |`)과 이미지 목록은 광고 '내용'이 아니라 파일 구조라, 질의로 쓰면
    법령 텍스트와 엉뚱한 데서 유사도가 붙는다. 본문 자체는 손대지 않는다 —
    마케팅 문구를 법령체로 다듬으면 그건 이미 (B) 쟁점 질의 생성이지 원문이 아니다.

    **병합 셀 중복 제거가 핵심이다.** HWP 표에서 가로로 병합된 칸을 파서가 칸 수만큼
    복사해 내보내서, 대출성 광고가 실측 6,152~7,418자로 부풀어 있었다. 중복을 걷어내면
    1,923~2,446자 — 임베딩 창(2,560토큰)에 들어간다. 안 걷으면 광고 뒷부분(유의사항·
    설명의무 고지 등 심의에서 정작 중요한 대목)이 잘려 나간다.
    """
    cells, seen, out = [], set(), []
    for l in text.split("\n"):
        s = l.strip()
        if not s or re.fullmatch(r"[|\s]*", s):
            continue
        if s.startswith("[이미지") or re.match(r"^\s*이미지\d+\s", s):
            continue
        cells += [c.strip() for c in s.split("|")] if "|" in s else [s]
    for c in cells:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.src)
                   if os.path.splitext(f)[1].lower() in
                   (".hwp", ".hwpx", ".pdf", ".png", ".jpg", ".docx"))
    print(f"대상 {len(files)}건\n")

    rows, fails = [], []
    for fn in files:
        meta = parse_name(fn)
        if not meta:
            print(f"  ? 이름 형식 불일치 — 건너뜀: {fn}")
            continue
        try:
            raw = file_text.extract(os.path.join(a.src, fn))
        except Exception as e:                      # 파서가 죽어도 나머지는 계속
            fails.append((fn, str(e)[:80]))
            print(f"  ! 추출 실패: {fn} — {str(e)[:60]}")
            continue
        text = clean(raw)
        rows.append({**meta, "파일": fn, "chars": len(text), "text": text})
        print(f"  {meta['광고id']:20s} {meta['판본']:4s} {len(text):>6,}자  {fn}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n저장: {a.out}  ({len(rows)}건)")
    if rows:
        c = sorted(r["chars"] for r in rows)
        print(f"길이: 중앙 {c[len(c)//2]:,}자 · 최소 {c[0]:,} · 최대 {c[-1]:,}")
    if fails:
        print(f"\n실패 {len(fails)}건:")
        for fn, e in fails:
            print(f"  {fn} — {e}")


if __name__ == "__main__":
    main()
