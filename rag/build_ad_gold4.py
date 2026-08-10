# -*- coding: utf-8 -*-
"""정답을 **엑셀이 준 조문 주소 그대로** 쓴다. 추측을 빼는 것이 요점이다.

앞서 두 번 헤맸다.

    ad_gold2  체크항목 → 통합본 체크리스트 → 규칙 ID
              → R-0662(이자율 범위)가 정답이 됐는데 지적은 만기후이율이었다
    ad_gold3  지적내용 → 규칙 요약 낱말 겹침
              → 나아졌지만 여전히 1등·2등을 두고 사람이 고민해야 한다

**둘 다 엑셀에 없는 것을 만들어 내려다 생긴 일이다.** 심의사례 엑셀은 규칙 ID 를
안 적는다. 대신 **조문 주소를 항·호·목까지 적어 놓았다.**

    근거규정   기준 §16① 5 나       제16조 1항 5호 나목

내가 이걸 조 단위로만 저장해서 「제16조」가 됐고, 그러면 §16 안의 의무 스무 개가
전부 정답이 되어 48개가 걸렸다. 호 단위 색인에는 주소가 살아 있다.

    ho_path  "5 나"   "나. 이자율의 범위 및 산출기준"

**추측이 없다.** 엑셀이 적은 주소를 그대로 찾아가는 것이라 사람이 고를 게 없다.

  python rag/build_ad_gold4.py
  python rag/build_ad_gold4.py --show
"""
import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
HO = os.path.join(RAG, "rule_index_ho.jsonl")
OUT = os.path.join(RAG, "ad_gold4.json")
NL = chr(10)

# 심의사례가 쓰는 줄임말 → 규정 정식 이름. `build_gold.py` 의 것과 같아야 한다.
ALIAS = {
    "기준": "은행 광고심의 기준 및 세칙",
    "금소법": "금융소비자 보호에 관한 법률",
    "금소법 시행령": "금융소비자 보호에 관한 법률 시행령",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "시행령": "금융소비자 보호에 관한 법률 시행령",
    "감독규정": "금융소비자 보호에 관한 감독규정",
    "표시·광고 심사지침": "금융상품 등의 표시·광고에 관한 심사지침",
}
_HANG = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

# 「기준 §16① 5 나」·「금소법 §22③ 4」·「기준 §17 1」 을 다 받는다.
# **「§22조④」처럼 「조」가 붙어 오는 것도 받는다** — 실제 심의사례에 그렇게
# 적힌 줄이 있어 파싱이 통째로 실패했다.
_REF = re.compile(
    r"(?P<name>[^§]*)§\s*(?P<jo>\d+(?:\s*-\s*\d+)?)\s*조?"
    r"(?:\s*의\s*(?P<ji>\d+))?\s*"
    r"(?P<hang>[①-⑮])?\s*"
    r"(?P<ho>\d+)?\s*"
    r"(?P<mok>[가-힣])?")

# 조문형이 아닌 지침. 「표시·광고 심사지침 Ⅴ.3.가」 꼴이다. 색인에는 key=Ⅴ,
# ho_path=「3 가」로 들어 있어 그대로 가리킬 수 있다.
_ROMAN = re.compile(
    r"(?P<name>[^Ⅰ-Ⅹ]*?)\s*(?P<jo>[Ⅰ-Ⅹ]+)\s*[.．]\s*"
    r"(?P<ho>\d+)?\s*[.．]?\s*(?P<mok>[가-힣])?")


def parse_ref(text):
    """근거규정 문자열 → [(규정, 조, 경로)]. 경로는 ho_path 와 같은 모양."""
    out = []
    for part in re.split(r"[,\n]", str(text or "")):
        # 조문형이 아닌 지침을 먼저 본다. 「표시·광고 심사지침 Ⅴ.3.가」처럼
        # § 없이 로마숫자로 적힌 것이라, § 패턴으로는 아예 안 걸린다.
        if "§" not in part and re.search(r"[Ⅰ-Ⅹ]\s*[.．]", part):
            rm = _ROMAN.search(part)
            if rm:
                nm = ALIAS.get(rm.group("name").strip(" ·,"),
                               rm.group("name").strip(" ·,"))
                bits = [x for x in (rm.group("ho"), rm.group("mok")) if x]
                out.append((nm, rm.group("jo"), " ".join(bits)))
            continue
        m = _REF.search(part)
        if not m:
            continue
        name = m.group("name").strip(" ·,")
        name = ALIAS.get(name, name) if name else (out[-1][0] if out else None)
        if not name:
            continue
        jo = "제" + re.sub(r"\s", "", m.group("jo")) + "조"
        if m.group("ji"):
            jo += "의" + m.group("ji")
        # ho_path 는 「① 5 나」 또는 「5 나」 꼴이다. 있는 것만 이어 붙인다.
        bits = [x for x in (m.group("hang"), m.group("ho"), m.group("mok")) if x]
        out.append((name, jo, " ".join(bits)))
    return out


def norm_reg(s):
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(HO, encoding="utf-8")]
    arts = [(i, r) for i, r in enumerate(rows)
            if r["evidence_id"].startswith("C-")]
    # (규정, 조, 경로) → 행번호. 경로가 빈 것도 넣어 둔다(항·호가 없는 조문).
    idx = {}
    for i, r in arts:
        m = re.match(r"\[([^\]]+)\]", r.get("content") or "")
        if not m:
            continue
        key = (norm_reg(m.group(1)), re.sub(r"\s", "", r.get("article_no") or ""),
               (r.get("metadata_json") or {}).get("ho_path", ""))
        idx.setdefault(key, []).append(i)

    prev = json.load(open(os.path.join(RAG, "ad_gold.json"),
                          encoding="utf-8"))["건"]
    out, miss = [], []
    for g in prev:
        refs = parse_ref(g["근거원문"])
        hits, detail = [], []
        for name, jo, path in refs:
            k = (norm_reg(name), re.sub(r"\s", "", jo), path)
            got = idx.get(k)
            how = "정확"
            if not got:
                # 색인의 ho_path 는 항 번호가 빠지기도 한다. 조문 첫머리의 ① 이
                # 도입문으로 흡수돼 「① 5 나」가 아니라 「5 나」로 저장된 경우다.
                # 그래서 **항을 뗀 주소**를 먼저 보고, 그다음 목·호를 하나씩 뗀다.
                bits = path.split()
                cands = []
                if bits and bits[0] and bits[0] in _HANG:
                    cands.append(" ".join(bits[1:]))          # 항만 뗌
                    cands.append(" ".join(bits[1:-1]))        # 항 떼고 목도 뗌
                cands += [" ".join(bits[:-1]), ""]            # 목 뗌 · 조 전체
                for c in cands:
                    if c == path:
                        continue
                    got = idx.get((k[0], k[1], c))
                    if got:
                        how = ("정확(항 표기 차이)" if c == " ".join(bits[1:])
                               else f"부분({c or '조 전체'})")
                        break
            if got:
                hits += got
                detail.append({"규정": name, "조": jo, "경로": path,
                               "찾음": how, "행수": len(got)})
            else:
                detail.append({"규정": name, "조": jo, "경로": path,
                               "찾음": "없음", "행수": 0})
        row = dict(g)
        row["정답행"] = sorted(set(hits))
        row["주소"] = detail
        out.append(row)
        if not hits:
            miss.append(row)

    json.dump({"설명": "광고 → 걸린 조문. **엑셀의 근거규정 주소를 항·호·목까지 "
                     "그대로 따라간 것.** 추측이 없다.",
               "색인": "rule_index_ho.jsonl", "건": out},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n = [len(x["정답행"]) for x in out if x["정답행"]]
    print(f"심의사례 {len(prev)}건 → 조문 연결 {len(n)}건 · 못 찾음 {len(miss)}건")
    print(f"  정답 행수 — 최소 {min(n) if n else 0} · 최대 {max(n) if n else 0} · "
          f"평균 {sum(n)/max(len(n),1):.1f}")
    print("  (앞 정답셋은 48~140행이었다)\n")
    for x in out:
        d = x["주소"][0] if x["주소"] else {}
        print(f"  {x['광고id']:16s} {x['근거원문'][:24]:26s} → "
              f"{len(x['정답행']):3d}행  [{d.get('찾음','-')}]  {x['지적'][:26]}")
        if a.show:
            for i in x["정답행"][:3]:
                print(f"       {(rows[i].get('content') or '')[:80].replace(NL,' | ')}")
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
