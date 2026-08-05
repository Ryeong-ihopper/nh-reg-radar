# -*- coding: utf-8 -*-
"""협회·정부 매뉴얼 15종 → 검색 항목.

규칙리스트 1,744건의 **출처**가 이 매뉴얼들이다. 그중 375건은 근거가 법령이 아니라
매뉴얼 자체이고(「매뉴얼자체」), 미해결 88건도 대부분 이 안에 실려 있다 — 실측:
「협회 내부 심사지침(절세 표시기준)」은 M01 별첨 3, 「단순광고제도 운영관련
가이드라인」은 M01 [참고] 로 전문이 들어 있었다. 따로 구할 문서가 아니었다.

**법령과 나누는 기준이 다르다.** 법령은 조문이라는 안정적인 경계가 있지만 매뉴얼은
장·절 번호가 문서마다 제각각이다(Ⅰ / 1. / 가. / □ / ■). 그래서 **머리로 보이는 줄을
경계로 삼되, 너무 잘게 갈리지 않도록 최소 길이를 둔다.**

  python rag/manuals.py                    # 통계
  python rag/manuals.py --out output/_rag/manual_chunks.jsonl
"""
import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import file_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = (r"C:\Users\babie\OneDrive\Desktop\씨지인사이드"
       r"\(참고용) 데이터셋 작업 과정\02_원본소스\매뉴얼_원본")
OUT = os.path.join(ROOT, "output", "_rag", "manual_chunks.jsonl")

# 규칙리스트의 「출처 매뉴얼」 코드(M01…M15)가 파일 앞 번호와 같다.
# 이 코드로 규칙과 매뉴얼 항목을 이어 붙인다.
MANUALS = {
    "M01": ("금융투자협회 투자광고심사 매뉴얼 및 사례집", "금융투자협회", 2021),
    "M02": ("사전심의 대상 기준(개별 영업점 자체제작 광고물)", "전국은행연합회", 2023),
    "M03": ("예금성상품 광고시 준수사항", "전국은행연합회", 2023),
    "M04": ("은행연합회 광고심의 매뉴얼", "전국은행연합회", 2023),
    "M05": ("대출모집인 광고 유의사항", "전국은행연합회", 2024),
    "M06": ("블로그 후기·게시물(인쇄물) 광고 유의사항", "전국은행연합회", 2024),
    "M07": ("SNS광고·기존 가입상품 추가 광고 유의사항", "전국은행연합회", 2025),
    "M08": ("대출성 상품 광고시 준수사항", "전국은행연합회", 2025),
    "M09": ("여신금융협회 광고심의 업무매뉴얼", "여신금융협회", 2025),
    "M10": ("생성형 AI·외국어 번역·다크패턴 관련 광고 유의사항", "전국은행연합회", 2026),
    "M11": ("퇴직연금 수익률 광고시 유의사항", "금융투자협회", 2026),
    "M12": ("투자광고시 금융투자상품별 유의사항 문구", "금융투자협회", 2026),
    "M13": ("광고심의규정 개정 관련 FAQ", "여신금융협회", 2021),
    "M14": ("투자광고 관련 금소법령·협회규정·표시광고법령 등 안내", "금융투자협회", 2025),
    "M15": ("금융광고규제 가이드라인", "금융위원회·금융감독원", 2021),
}

# 머리로 볼 표기. 문서마다 다르므로 전부 받는다. 뒤에 제목이 이어져야 머리로 친다.
_HEAD = re.compile(
    r"^(?:"
    r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[.．]?\s*"          # Ⅰ. Ⅱ.
    r"|제\s*\d+\s*[장절편]\s*"                  # 제1장
    r"|별첨\s*\d+\s*[.．]?\s*"                  # 별첨 3
    r"|\d{1,2}\s*[.．]\s*"                     # 1.
    r"|[가-힣]\s*[.．]\s*"                      # 가.
    r"|[■□◆◇○●▶]\s*"                        # □ ■
    r")(?=\S)")
# 사례·참고 블록도 경계로 본다. 매뉴얼의 실제 값어치가 여기 있다.
_CASE = re.compile(r"^\s*[\[［]\s*(사례|참고|예시|Q&?A)")

MIN_CHARS = 120      # 이보다 짧으면 앞 항목에 붙인다(표 셀 한 줄이 항목이 되는 것 방지)
MAX_CHARS = 1400     # 법령 청킹과 같은 상한


def dedup_cells(text):
    """병합 셀 반복을 걷어낸다.

    document-processor 는 TableIR 을 만들 때 expand_merged_cells() 로 병합 칸을
    칸 수만큼 복제한다(설계대로다). 텍스트로 펼 때는 그 확장을 되돌려야 한다 —
    실측: 광고 HWP 에서 상품명이 한 줄에 7번 반복돼 분량이 3배가 됐다.
    """
    seen, out = set(), []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        cells = [c.strip() for c in s.split("|")] if "|" in s else [s]
        keep = [c for c in cells if c and c not in seen]
        seen.update(keep)
        if keep:
            out.append(" | ".join(keep) if len(keep) > 1 else keep[0])
    return "\n".join(out)


def split_sections(text):
    """머리 표기를 경계로 항목을 나눈다. [(제목, 본문)]"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out, title, body = [], "", []

    def flush():
        b = "\n".join(body).strip()
        if title or b:
            out.append((title, b))

    for l in lines:
        is_head = (_HEAD.match(l) and len(l) <= 60) or _CASE.match(l)
        if is_head and len("\n".join(body)) >= MIN_CHARS:
            flush()
            title, body = l, []
        elif is_head and not body and not title:
            title = l
        else:
            body.append(l)
    flush()

    # 상한 초과분은 줄 경계에서 자른다. 법령과 달리 항·호 구조가 없어 문단으로 나눈다.
    final = []
    for t, b in out:
        while len(b) > MAX_CHARS:
            cut = b.rfind("\n", 0, MAX_CHARS)
            if cut < MIN_CHARS:
                cut = MAX_CHARS
            final.append((t, b[:cut].strip()))
            b = b[cut:].strip()
        if b or t:
            final.append((t, b))
    return final


def load(src=SRC, verbose=True):
    rows = []
    for fn in sorted(os.listdir(src)):
        m = re.match(r"(\d{2})\.", fn)
        if not m:
            continue
        code = f"M{m.group(1)}"
        if code not in MANUALS:
            continue
        title, issuer, year = MANUALS[code]
        raw = file_text.extract(os.path.join(src, fn))
        text = dedup_cells(raw)
        secs = split_sections(text)
        for i, (head, body) in enumerate(secs, 1):
            full = (f"[{title}] {head}".rstrip() + "\n" + body).strip()
            rows.append({
                "reg": title, "kind": "manual", "type": "매뉴얼",
                "code": code, "issuer": issuer, "year": year,
                "key": f"{code}#{i}", "title": head[:60],
                "part": i, "parts": len(secs),
                "text": full, "chars": len(full),
                "id": f"{code}#{i}",
            })
        if verbose:
            print(f"  {code}  {len(raw):>8,}자 → 중복제거 {len(text):>8,}자 "
                  f"→ 항목 {len(secs):>4}개   {title[:38]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    rows = load(a.src)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    c = sorted(r["chars"] for r in rows)
    print(f"\n매뉴얼 {len(MANUALS)}종 → 항목 {len(rows):,}개 · {sum(c):,}자")
    print(f"길이: 중앙 {c[len(c)//2]:,} · p90 {c[int(len(c)*.9)]:,} · 최대 {c[-1]:,}")
    print(f"발행기관: {collections.Counter(r['issuer'] for r in rows).most_common()}")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
