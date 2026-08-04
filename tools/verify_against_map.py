# -*- coding: utf-8 -*-
"""사람이 만든 조문 지도와 우리 파싱 결과를 대조한다.

`260716_3_전체조문지도.xlsx` 는 담당자가 매뉴얼을 훑어 「어느 조문이 인용되는가」를
손으로 정리한 표다. **조문 원문까지 들어 있어** 우리 파싱 결과의 독립 검증에 쓸 수 있다.

자동 검사(quality_check.py)는 우리가 미리 정한 규칙만 본다. 실제로 7/31 에 나온 버그
다수가 자동 검사를 통과한 상태였고, 사람이 목록을 눈으로 훑다가 발견했다. 이 대조는
**우리가 만들지 않은 기준**으로 보는 것이라 그 사각을 줄인다.

세 가지를 본다.
  1. 지도에 있는 법령이 우리 수집 대상에 있는가          (수집 범위 누락)
  2. 그 조문이 우리 파싱 결과에 있는가                    (조문 분리 실패)
  3. 조문 본문 앞부분이 지도의 원문과 일치하는가          (내용 어긋남)

  python tools/verify_against_map.py
  python tools/verify_against_map.py --show 30
"""
import os
import re
import sys
import json
import argparse
import collections
import difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = (r"C:\Users\babie\OneDrive\Desktop\씨지인사이드"
       r"\(참고용) 데이터셋 작업 과정\01_핵심데이터\260716_3_전체조문지도.xlsx")
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")


def norm_name(s):
    """법령명 비교용 정규화. 띄어쓰기·가운뎃점 표기가 자료마다 다르다."""
    s = re.sub(r"[\s·ㆍ・]", "", str(s or ""))
    return s.replace("(", "").replace(")", "")


# 지도와 우리 대상의 이름이 다른 경우. 같은 문서를 다르게 부르는 것뿐이라
# 이걸 안 풀면 멀쩡한 규정이 「수집 대상 아님」으로 잡힌다(실측: 「은행 광고심의
# 기준」·「은행 광고심의 기준 세칙」 37행이 거짓 경보였다 — 우리는 둘을 합쳐
# 「은행 광고심의 기준 및 세칙」 한 건으로 수집한다).
ALIAS = {
    "은행광고심의기준": "은행 광고심의 기준 및 세칙",
    "은행광고심의기준세칙": "은행 광고심의 기준 및 세칙",
    "은행광고심의기준및세칙": "은행 광고심의 기준 및 세칙",
}


def norm_text(s):
    """본문 비교용.

    **개정 표기를 지운다.** 법제처 본문에는 「① … 이용할 수 있다. <개정 2023.3.14>
    1. 정보주체의 …」처럼 항과 호 사이에 이력이 끼어 있는데, 지도의 인용문에는 없다.
    이걸 안 지우면 내용이 같은데도 문자열이 끊겨 「어긋남」으로 잡힌다(실측: 80건
    중 상당수가 이 이유였다).
    """
    s = re.sub(r"[<〈][^>〉]{0,40}?(?:개정|신설|전문개정|일부개정|삭제)[^>〉]{0,40}[>〉]", "",
               str(s or ""))
    s = re.sub(r"\s+", "", s)
    return s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")


# 「제2조(정의)」처럼 인용문 앞에 붙는 조문 머리. 지도는 조문 머리 뒤에 **특정 항만**
# 잘라 붙이는데(「제2조(정의)②영 제2조…」) 우리 본문은 ①부터 순서대로 다 있다.
# 머리를 떼고 나머지로 찾아야 실제 포함 여부를 볼 수 있다.
_ART_HEAD = re.compile(r"^제\d+(?:-\d+)?조(?:의\d+)?(?:\([^)]{0,60}\))?")


def probe_of(quoted):
    """지도 인용문 → 우리 본문에서 찾을 조각.

    앞의 조문 머리를 떼고, 항 번호(①)도 뗀다. 남은 실질 문장 60자면 다른 조문과
    우연히 겹칠 일이 없다.
    """
    s = _ART_HEAD.sub("", quoted)
    s = re.sub(r"^[①-⑮\d.]+", "", s)
    return s[:60]


def art_key(s):
    """「제15조」·「제4-11조」·「제80조의2」 → 비교용 키."""
    m = re.search(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?", str(s or ""))
    if not m:
        return None
    a, b, c = m.groups()
    return f"제{a}" + (f"-{b}" if b else "") + "조" + (f"의{c}" if c else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=MAP)
    ap.add_argument("--show", type=int, default=15)
    a = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(a.map, read_only=True, data_only=True)
    rows = [r for r in wb["2_전체조문지도"].iter_rows(min_row=2, values_only=True)
            if r and r[1]]
    wb.close()

    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    our_regs = {norm_name(c["reg"]): c["reg"] for c in chunks}
    # 규정명+조문키 → 본문(같은 조문이 여러 청크면 이어 붙인다)
    by_art = collections.defaultdict(str)
    for c in chunks:
        k = art_key(c.get("key", ""))
        if k:
            by_art[(norm_name(c["reg"]), k)] += c["text"]

    stat = collections.Counter()
    miss_reg, miss_art, mismatch = [], [], []

    for r in rows:
        name, jo, orig, typ, how, rel = r[1], r[2], r[7], r[8], r[9], r[12]
        nn = norm_name(name)
        nn = norm_name(ALIAS.get(nn, nn))
        stat["전체"] += 1

        if nn not in our_regs:
            stat["수집대상아님"] += 1
            miss_reg.append((name, typ, how, rel))
            continue

        k = art_key(jo)
        if not k:                      # 「(전체)」처럼 조문 지정이 없는 행
            stat["조문미지정"] += 1
            continue

        body = by_art.get((nn, k))
        if not body:
            stat["조문없음"] += 1
            miss_art.append((name, jo, rel))
            continue

        stat["조문있음"] += 1
        if not orig or len(str(orig)) < 30:
            stat["원문없어비교생략"] += 1
            continue

        want = probe_of(norm_text(orig))
        have = norm_text(body)
        if len(want) < 20:
            stat["원문없어비교생략"] += 1
            continue
        if want in have:
            stat["본문일치"] += 1
        else:
            # 못 찾으면 우리 본문 어디와도 안 닮았는지 본다. 앞 400자만 보면
            # 뒤쪽 항에 있는 내용을 놓치므로 전체에서 가장 닮은 구간을 찾는다.
            sm = difflib.SequenceMatcher(None, want, have)
            m = sm.find_longest_match(0, len(want), 0, len(have))
            cover = m.size / len(want)
            if cover > 0.7:
                stat["본문유사"] += 1
            else:
                stat["본문어긋남"] += 1
                mismatch.append((name, jo, want[:50], cover))

    print(f"조문 지도 {stat['전체']}행\n")
    for k in ("수집대상아님", "조문미지정", "조문없음", "조문있음",
              "본문일치", "본문유사", "본문어긋남", "원문없어비교생략"):
        if stat[k]:
            print(f"  {k:14s} {stat[k]:>4}")

    if miss_reg:
        c = collections.Counter((m[0], m[1], m[2], m[3]) for m in miss_reg)
        print(f"\n■ 수집 대상에 없는 법령·규정 ({len(c)}종 · {len(miss_reg)}행)")
        for (nm, typ, how, rel), n in c.most_common(a.show):
            print(f"  {n:>3}행  {str(rel or ''):8s} {str(typ or ''):8s} "
                  f"{str(how or ''):14s} {nm}")

    if miss_art:
        print(f"\n■ 규정은 있는데 그 조문이 없음 ({len(miss_art)}건)")
        for nm, jo, rel in miss_art[:a.show]:
            print(f"  {str(rel or ''):8s} {nm[:34]:34s} {jo}")

    if mismatch:
        print(f"\n■ 본문이 어긋남 ({len(mismatch)}건)")
        for nm, jo, w, ratio in mismatch[:a.show]:
            print(f"  {ratio:.2f}  {nm[:28]:28s} {str(jo):10s} {w}")


if __name__ == "__main__":
    main()
