# -*- coding: utf-8 -*-
"""심의 체크리스트·사례 → 검색 평가셋(gold).

**직접 만들지 않는다.** 「심의사례 NH농협은행 준법감시부 1.xlsx」의 체크리스트 시트는
준법감시부가 실제로 쓰는 표라, 점검항목마다 근거규정이 이미 붙어 있다.

  DEP-INC-06 | 예금성 | 포함사항 | 이자율·수익률의 범위 및 산출기준을 표시하였는가?
             | 기준 §16① 5 나

점검내용이 곧 질의, 근거규정이 곧 정답이다. 내가 광고를 읽고 정답을 지어내면 그건
내 판단을 재는 것이지 시스템을 재는 것이 아니다 — 사람이 만든 공식 매핑을 쓴다.

**약칭을 실제 규정명·조문키로 옮기는 것이 이 모듈의 일이다.** 「기준 §16① 5 나」는
사람에게는 자명하지만 검색 결과와 대조하려면 `은행 광고심의 기준 및 세칙 / 제16조`
로 바꿔야 한다. 항·호·목(① 5 나)까지는 청크 단위가 조문이라 버린다 — 조문 하나가
맞으면 맞은 것으로 본다.

  python rag/build_gold.py
  python rag/build_gold.py --check      # 정답 조문이 코퍼스에 실재하는지만 확인
"""
import os
import re
import sys
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = r"C:\Users\babie\OneDrive\Desktop\씨지인사이드\심의사례 NH농협은행 준법감시부 1.xlsx"
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")
OUT = os.path.join(ROOT, "output", "_rag", "gold.json")

# 약칭 → 코퍼스의 실제 규정명. 표에 쓰인 표기를 그대로 키로 둔다.
# 긴 것부터 맞춰야 「금소법 시행령」이 「금소법」으로 잘못 잡히지 않는다(아래 정렬).
ALIAS = {
    "기준": "은행 광고심의 기준 및 세칙",
    "세칙": "은행 광고심의 기준 및 세칙",
    "금소법 시행령": "금융소비자 보호에 관한 법률 시행령",
    "금소법": "금융소비자 보호에 관한 법률",
    "감독규정": "금융소비자 보호에 관한 감독규정",
    "정보통신망법 시행령": "정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "금융지주회사법": "금융지주회사법",
    "광고에 관한 심사지침": "금융상품 등의 표시·광고에 관한 심사지침",
    "광고 심사지침": "금융상품 등의 표시·광고에 관한 심사지침",
    "표시·광고 심사지침": "금융상품 등의 표시·광고에 관한 심사지침",
}
_ALIAS_ORDER = sorted(ALIAS, key=len, reverse=True)

# §16① 5 나 · §22③ 4 · §50④ · §22조④ 3 나  — 조 번호만 뽑는다
_SEC = re.compile(r"§\s*(\d+)\s*(?:조)?\s*(?:의\s*(\d+))?")
# 감독규정 별표 3 같은 별표 참조
_TBL = re.compile(r"별표\s*0*(\d+)")


def parse_ref(text):
    """근거규정 문자열 → [(규정명, 조문키), ...]

    「금소법 §22③ 4, 금소법 시행령 §18① 1 다」처럼 여럿이 콤마로 붙는다.
    쉼표로 자른 뒤 조각마다 규정명을 찾되, 규정명이 생략된 조각은 **앞 조각의 것을
    물려받는다**(「기준 §16① 2, 기준 §16① 8」은 둘 다 있지만 「금소법 §22⑦,
    시행령 §19①, 감독규정 §18」처럼 섞이는 경우가 있어 순서대로 흘려보낸다).
    """
    out, cur = [], None
    for part in re.split(r"[,]", str(text or "")):
        part = part.strip()
        if not part:
            continue
        matched = None
        for a in _ALIAS_ORDER:
            if part.startswith(a) or f" {a} " in f" {part} ":
                matched = ALIAS[a]
                break
        if matched:
            cur = matched
        elif part.startswith("시행령") and cur:
            # 「정보통신망법 §50④, 시행령 §61③」의 시행령은 **바로 앞 법**의 시행령이다.
            # 이걸 한 법으로 고정해 두면 조용히 틀린 정답이 박힌다(실측: 금소법
            # 시행령 제61조로 잘못 잡혀 3건이 코퍼스에서 안 나왔다 — 안 나와서
            # 들켰지, 우연히 존재하는 조문이었으면 못 잡을 뻔했다).
            cur = cur if cur.endswith("시행령") else cur + " 시행령"
        if not cur:
            continue
        for m in _SEC.finditer(part):
            n, sub = m.group(1), m.group(2)
            out.append((cur, f"제{n}조" + (f"의{sub}" if sub else "")))
        for m in _TBL.finditer(part):
            out.append((cur, f"[별표 {int(m.group(1)):04d}]"))
    # 중복 제거(순서 유지)
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def load_chunks():
    rows = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[(r["reg"], r.get("key", ""))].append(i)
    return rows, by


def resolve(by, reg, key):
    """(규정명, 조문키) → 청크 번호 목록. 정확히 없으면 접두 일치로 한 번 더 본다."""
    hit = by.get((reg, key))
    if hit:
        return hit
    # 「제16조」로 찾는데 코퍼스 키가 「제16조의2」뿐인 경우 등
    out = []
    for (r, k), v in by.items():
        if r == reg and k.startswith(key):
            out += v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(a.xlsx, read_only=True, data_only=True)
    rows, by = load_chunks()

    gold, unresolved = [], []

    # ── 1) 체크리스트 97항목 — 공식 매핑이라 가장 신뢰도가 높다 ────────────
    for r in wb["체크리스트"].iter_rows(values_only=True):
        if not r or not r[0] or str(r[0]).count("-") != 2:
            continue
        item_id, ptype, kind, q, ref = (str(x or "").strip() for x in r[:5])
        refs = parse_ref(ref)
        idxs, miss = [], []
        for reg, key in refs:
            got = resolve(by, reg, key)
            (idxs.extend(got) if got else miss.append(f"{reg} {key}"))
        if miss:
            unresolved.append((item_id, ref, miss))
        if not idxs:
            continue
        gold.append({"id": item_id, "출처": "체크리스트", "상품유형": ptype,
                     "구분": kind, "q": q, "근거원문": ref,
                     "정답": [{"reg": reg, "key": key} for reg, key in refs],
                     "정답청크": sorted(set(idxs))})

    # ── 2) 심의사례 20건 — 실제로 지적된 건이라 질의가 더 현실적이다 ───────
    for sheet, ptype in (("예금성 광고", "예금성"), ("대출성 광고", "대출성")):
        for r in wb[sheet].iter_rows(min_row=4, values_only=True):
            if not r or r[0] in (None, "") or not str(r[0]).strip().isdigit():
                continue
            no, name, _, _, _, _, chk, ref, op, detail = (
                [str(x or "").strip() for x in r[:10]] + [""] * 10)[:10]
            refs = parse_ref(ref)
            idxs, miss = [], []
            for reg, key in refs:
                got = resolve(by, reg, key)
                (idxs.extend(got) if got else miss.append(f"{reg} {key}"))
            if miss:
                unresolved.append((f"{ptype}#{no}", ref, miss))
            if not idxs:
                continue
            # 질의는 '점검내용 + 실제 지적사유'로 만든다 — 체크리스트만 쓰면
            # 일반론이 되고, 지적사유를 붙여야 그 광고의 상황이 들어간다.
            q = chk if not detail else f"{chk} ({op}: {detail})"
            gold.append({"id": f"{ptype}-사례{no}", "출처": "심의사례",
                         "상품유형": ptype, "구분": op, "q": q, "광고명": name,
                         "근거원문": ref,
                         "정답": [{"reg": reg, "key": key} for reg, key in refs],
                         "정답청크": sorted(set(idxs))})

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(gold, f, ensure_ascii=False, indent=1)

    print(f"gold {len(gold)}건 · 출처 "
          f"{collections.Counter(g['출처'] for g in gold).most_common()}")
    print(f"상품유형 {collections.Counter(g['상품유형'] for g in gold).most_common()}")
    n = [len(g['정답청크']) for g in gold]
    print(f"항목당 정답청크: 중앙 {sorted(n)[len(n)//2]} · 최소 {min(n)} · 최대 {max(n)}")
    print(f"저장: {a.out}")

    if unresolved:
        print(f"\n⚠ 코퍼스에서 못 찾은 참조 {len(unresolved)}건 — "
              f"약칭 매핑이나 조문 표기를 확인해야 한다")
        for i, (iid, ref, miss) in enumerate(unresolved[:12]):
            print(f"  {iid:16s} {ref[:40]:40s} → {', '.join(miss)}")


if __name__ == "__main__":
    main()
