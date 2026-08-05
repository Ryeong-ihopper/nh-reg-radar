# -*- coding: utf-8 -*-
"""규칙리스트 v3 의 「근거 상세」를 우리 코퍼스의 조문에 붙인다.

v3 에는 규칙 1,744건마다 어느 법 몇 조가 근거인지 적혀 있고(「근거 상세」), 그 조문을
가져온 결과도 함께 있다(「인용 조문 원문」). 그런데 **가져오기가 자주 틀렸다** — 446건은
아예 실패했고, 성공한 것도 가지번호를 놓쳐 엉뚱한 조문을 담은 경우가 있다(실측: 근거는
자본시장법 제117조의9(투자광고의 특례)인데 원문은 제117조(청산)).

**그래서 「근거 상세」만 원천으로 쓰고 본문은 우리 코퍼스에서 찾는다.** 우리 코퍼스는
조문지도 246행과 대조해 검증했고(본문 일치 178·유사 19·어긋남 0), v3 의 fetch 결과는
검증된 적이 없다. v3 의 원문은 대조용으로만 써서 서로 다르면 확인 신호로 남긴다.

매칭이 어려운 이유는 표기가 제각각이라서다(886가지). 세 가지를 처리한다.

  법령명   「금융투자협회 규정」·「금소법」·「…에 관한 규정제2-40조」(공백 없음)
  문맥물림 「금소법 제22조…, 시행령 제18조…, 감독규정 …」— 뒤엣것이 앞을 이어받는다
  조문키   「제2-37조제1항제3호」→ 제2-37조, 「별표10-1」→ [별표 0010의1]
           항·호·목은 버린다 — 우리 청크가 조문 단위이므로

  python rag/match_rules.py
  python rag/match_rules.py --out output/_rag/rules_matched.json --show 20
"""
import os
import re
import sys
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = (r"C:\Users\babie\OneDrive\Desktop\씨지인사이드"
        r"\(참고용) 데이터셋 작업 과정\01_핵심데이터\중요_NH_광고심의_규칙리스트_v3.xlsx")
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")
OUT = os.path.join(ROOT, "output", "_rag", "rules_matched.json")

COL = {"규칙ID": 1, "카테고리": 2, "상품": 3, "매체": 4, "요약": 5, "판단기준": 6,
       "위반시": 7, "우선순위": 8, "원문인용": 9, "출처매뉴얼": 10, "출처페이지": 11,
       "근거종류": 12, "근거상세": 13, "상태": 14, "인용조문원문": 18,
       "근거출처태그": 20, "관련성판정": 22}

# ── 법령명 정규화 ─────────────────────────────────────────────────────
# 표기 117종 → 정식 명칭. 긴 것부터 맞춰야 「금융소비자 보호에 관한 법률 시행령」이
# 「금융소비자 보호에 관한 법률」로 잘못 잡히지 않는다(아래에서 길이순 정렬).
ALIAS = {
    # 금투협
    "금융투자회사의 영업 및 업무에 관한 규정 시행세칙": "금융투자회사의 영업 및 업무에 관한 규정 시행세칙",
    "금융투자회사의 영업 및 업무에 관한 규정": "금융투자회사의 영업 및 업무에 관한 규정",
    "금융투자협회 규정": "금융투자회사의 영업 및 업무에 관한 규정",
    "협회규정": "금융투자회사의 영업 및 업무에 관한 규정",
    "금투협 영업규정": "금융투자회사의 영업 및 업무에 관한 규정",
    # 금투협 법규정보시스템에 실제로 등록된 이름으로 옮긴다. 규칙리스트는 「협회 …」로
    # 줄여 부르는데 사이트 이름은 다르다 — 이 매핑이 없어 25건이 매칭에서 빠져 있었다.
    # **「협회」를 뗀 형태도 함께 등록한다.** _LEAD 가 앞의 「공정위·협회」 같은 수식어를
    # 먼저 지우므로, 「협회 표준내부통제기준」만 등록하면 사전을 볼 때는 이미 사라져 있다.
    "협회 표준내부통제기준": "금융투자회사 표준내부통제기준",
    "표준내부통제기준": "금융투자회사 표준내부통제기준",
    "금융투자회사 표준내부통제기준": "금융투자회사 표준내부통제기준",
    "협회 모범규준(CMA 업무관련 모범규준)": "CMA 업무관련 모범규준",
    "모범규준(CMA 업무관련 모범규준)": "CMA 업무관련 모범규준",
    "모범규준(CMA": "CMA 업무관련 모범규준",
    "CMA 업무관련 모범규준": "CMA 업무관련 모범규준",
    "모범규준": "CMA 업무관련 모범규준",
    # 금소법 계열
    "금융소비자 보호에 관한 법률 시행령": "금융소비자 보호에 관한 법률 시행령",
    "금융소비자보호에 관한 법률 시행령": "금융소비자 보호에 관한 법률 시행령",
    "금융소비자 보호에 관한 감독규정 시행세칙": "금융소비자보호에 관한 감독규정 시행세칙",
    "금융소비자 보호에 관한 감독규정": "금융소비자 보호에 관한 감독규정",
    "금융소비자보호에 관한 감독규정": "금융소비자 보호에 관한 감독규정",
    "금융소비자 보호에 관한 법률": "금융소비자 보호에 관한 법률",
    "금융소비자보호법": "금융소비자 보호에 관한 법률",
    "금소법": "금융소비자 보호에 관한 법률",
    # 은행연 — 「기준」과 「세칙」이 한 파일로 수집돼 있다
    "은행 광고심의 기준 세칙": "은행 광고심의 기준 및 세칙",
    "은행 광고심의기준 세칙": "은행 광고심의 기준 및 세칙",
    "은행 광고심의 기준": "은행 광고심의 기준 및 세칙",
    "은행 광고심의기준": "은행 광고심의 기준 및 세칙",
    # 여신협
    "여신전문금융회사 등의 광고에 관한 규정 세부지침": "여신전문금융회사 등의 광고에 관한 규정 세부지침",
    "여신전문금융회사 등의 광고에 관한 규정": "여신전문금융회사 등의 광고에 관한 규정",
    # 같은 문서를 다르게 부른 것이다. 여신협 자율규제 목록 69건에 「여신금융상품 광고에
    # 관한 세부지침」이라는 문서는 없고, 엑셀이 인용한 본문(제3조 의무표시사항 …)이
    # 우리가 가진 세부지침에 그대로 있다. 참조 조문(제3·5·8~11조)도 전부 범위 안이다.
    "여신금융상품 광고에 관한 세부지침": "여신전문금융회사 등의 광고에 관한 규정 세부지침",
    # 자본시장 계열
    "자본시장과 금융투자업에 관한 법률 시행령": "자본시장과 금융투자업에 관한 법률 시행령",
    "자본시장과 금융투자업에 관한 법률": "자본시장과 금융투자업에 관한 법률",
    "자본시장법": "자본시장과 금융투자업에 관한 법률",
    "금융투자업규정 시행세칙": "금융투자업규정시행세칙",
    "금융투자업규정": "금융투자업규정",
    "금투업규정": "금융투자업규정",
    "증권의 발행 및 공시 등에 관한 규정": "증권의 발행 및 공시 등에 관한 규정",
    "증발공규정": "증권의 발행 및 공시 등에 관한 규정",
    # 공정위 심사지침
    "추천·보증 등에 관한 표시·광고 심사지침": "추천ㆍ보증 등에 관한 표시ㆍ광고 심사지침",
    "추천·보증 등에 대한 표시·광고 심사지침": "추천ㆍ보증 등에 관한 표시ㆍ광고 심사지침",
    "추천보증 심사지침": "추천ㆍ보증 등에 관한 표시ㆍ광고 심사지침",
    "금융상품 등의 표시·광고에 관한 심사지침": "금융상품 등의 표시·광고에 관한 심사지침",
    "표시·광고의 공정화에 관한 법률 시행령": "표시ㆍ광고의 공정화에 관한 법률 시행령",
    "표시·광고의 공정화에 관한 법률": "표시ㆍ광고의 공정화에 관한 법률",
    "표시광고법": "표시ㆍ광고의 공정화에 관한 법률",
    # 기타
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령":
        "정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령",
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률":
        "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "여신전문금융업법 시행령": "여신전문금융업법 시행령",
    "여신전문금융업법": "여신전문금융업법",
    "여전법": "여신전문금융업법",
    "예금자보호법": "예금자보호법",
    "퇴직연금감독규정": "퇴직연금감독규정",
    "은행업감독규정": "은행업감독규정",
    "금융지주회사법 시행령": "금융지주회사법 시행령",
    "금융지주회사법": "금융지주회사법",
    "소득세법 시행령": "소득세법 시행령",
    "소득세법": "소득세법",
    "약관의 규제에 관한 법률": "약관의 규제에 관한 법률",
    "약관법": "약관의 규제에 관한 법률",
    "은행법 시행령": "은행법 시행령",
    "은행법": "은행법",
    "보험업법 시행령": "보험업법 시행령",
    "보험업법": "보험업법",
    "금융회사의 지배구조에 관한 법률": "금융회사의 지배구조에 관한 법률",
    "지배구조법": "금융회사의 지배구조에 관한 법률",
    "전자상거래 등에서의 소비자보호에 관한 법률": "전자상거래 등에서의 소비자보호에 관한 법률",
    "전자상거래법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "개인정보 보호법": "개인정보 보호법",
    "개인정보보호법": "개인정보 보호법",
    "대부업 등의 등록 및 금융이용자 보호에 관한 법률":
        "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
    "대부업법": "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
    "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법":
        "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
    "인공지능기본법": "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
    "온라인투자연계금융업 및 이용자 보호에 관한 법률":
        "온라인투자연계금융업 및 이용자 보호에 관한 법률",
    "온라인투자연계금융업법": "온라인투자연계금융업 및 이용자 보호에 관한 법률",
    "상호저축은행법": "상호저축은행법",
    "여신전문금융업감독규정": "여신전문금융업감독규정",
    "금융지주회사감독규정": "금융지주회사감독규정",
}
# 「공정위 「…」」처럼 앞에 붙는 수식어. 떼고 나서 사전을 본다.
_LEAD = re.compile(r"^(?:공정위|금융위|금감원|협회|은행연합회|동)\s*[「'\"]?\s*")
_QUOTE = re.compile(r"[「」『』'\"]")

# 앞 법령을 이어받는 표기. 「금소법 제22조…, 시행령 제18조…」의 시행령은 금소법 시행령이다.
INHERIT = {"시행령": " 시행령", "시행규칙": " 시행규칙", "감독규정": None,
           "세부지침": " 세부지침", "시행세칙": " 시행세칙", "동법": ""}
# 감독규정은 이름이 규칙적이지 않아 계열별로 따로 둔다.
INHERIT_MAP = {("금융소비자 보호에 관한 법률", "감독규정"): "금융소비자 보호에 관한 감독규정",
               ("금융소비자 보호에 관한 법률 시행령", "감독규정"): "금융소비자 보호에 관한 감독규정"}

_ALIAS_ORDER = sorted(ALIAS, key=len, reverse=True)

# ── 조문키 정규화 ─────────────────────────────────────────────────────
# 제2-37조 · 제117조의9 · 제80조의2. 항·호·목은 뒤에 붙어 있어도 버린다.
_ART = re.compile(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?")
# 별표9 · 별표 9 · 별표10-1 · 별표3-2] · 별지 제3호의2
_TBL = re.compile(r"(별표|별지|서식)\s*(?:제\s*)?0*(\d+)"
                  r"(?:\s*(?:호\s*의|[-의])\s*(\d+))?")


def norm_name(seg, prev=None):
    """조각에서 법령명을 뽑아 정식 명칭으로. 없으면 prev 를 문맥으로 물려받는다."""
    s = _QUOTE.sub("", _LEAD.sub("", seg.strip()))
    for a in _ALIAS_ORDER:
        if s.startswith(a):
            return ALIAS[a]
    # 법령명 없이 「시행령 제18조」처럼 시작하면 앞 법령을 이어받는다
    for token, suffix in INHERIT.items():
        if s.startswith(token) and prev:
            mapped = INHERIT_MAP.get((prev, token))
            if mapped:
                return mapped
            if suffix is None:
                return prev
            base = re.sub(r"\s*(시행령|시행규칙|시행세칙|세부지침)$", "", prev)
            return (base + suffix).strip()
    return None


def art_keys(seg):
    """조각에서 조문키를 전부. 값 하나가 아니라 **후보 목록**을 돌려준다.

    별표 키 형식이 소스마다 다르기 때문이다. 법제처·금투협은 자릿수를 채운
    `[별표 0009]` 를 쓰는데, 통짜 HWP 를 잘라 만든 여신협·은행연은 `[별표 3]` 처럼
    맨 숫자다. 한 형식만 만들면 다른 쪽이 통째로 안 맞는다(실측: 여신협 세부지침
    별표 참조 54건이 전부 실패).

    「제2-37조제1항제3호, 별표9」→ [[제2-37조], [[별표 0009], [별표 9]]]
    """
    out = []
    for m in _ART.finditer(seg):
        a, b, c = m.groups()
        key = f"제{a}" + (f"-{b}" if b else "") + "조" + (f"의{c}" if c else "")
        out.append([key])
    for m in _TBL.finditer(seg):
        kind, no, sub = m.groups()
        n, suf = int(no), (f"의{sub}" if sub else "")
        cands = [f"[{kind} {n:04d}{suf}]", f"[{kind} {n}{suf}]"]
        if sub:
            # 「별표3-2」가 「별표 3의2」가 아니라 별개 별표인 소스가 있다.
            # 가지 없는 형태도 후보에 넣어 둔다.
            cands += [f"[{kind} {n:04d}]", f"[{kind} {n}]"]
        out.append(cands)
    return out


def parse_basis(text):
    """근거 상세 → [(법령명, 조문키 or None)]. 조문키가 없으면 법령 전체 참조다."""
    out, prev = [], None
    for seg in re.split(r"[,;]", str(text or "")):
        seg = seg.strip()
        if not seg or seg == "-":
            continue
        name = norm_name(seg, prev)
        if not name:
            # 이름이 없고 물림도 안 되면 앞 법령의 추가 조문으로 본다
            # (「… 제22조 제3항, 제4항」처럼 조문만 이어지는 경우)
            name = prev
        if not name:
            continue
        prev = name
        cands = art_keys(seg)
        if cands:
            out.extend((name, tuple(c)) for c in cands)
        else:
            out.append((name, None))
    # 중복 제거(순서 유지)
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def load_corpus():
    rows = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[(r["reg"], r.get("key", ""))].append(i)
    regs = {r["reg"] for r in rows}
    return rows, by, regs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--show", type=int, default=12)
    a = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(a.xlsx, read_only=True, data_only=True)
    rows = [r for r in wb["전체_규칙"].iter_rows(min_row=2, values_only=True)
            if r and r[COL["규칙ID"]]]
    wb.close()
    chunks, by_key, regs = load_corpus()

    out, stat = [], collections.Counter()
    miss_reg, miss_art = collections.Counter(), collections.Counter()

    for r in rows:
        rec = {k: (str(r[i]).strip() if r[i] is not None else "") for k, i in COL.items()}
        basis = rec["근거상세"]

        if not basis or basis == "-":
            # 매뉴얼 자체가 근거다. 인용할 조문이 없는 것이 정상이며 「원문 인용」에
            # 매뉴얼 본문이 들어 있다. 근거를 「M12 p.18」 형태로 단다.
            rec["_유형"] = "매뉴얼"
            rec["_근거"] = [{"출처": rec["출처매뉴얼"], "페이지": rec["출처페이지"]}]
            rec["_청크"] = []
            stat["매뉴얼 자체"] += 1
            out.append(rec)
            continue

        refs = parse_basis(basis)
        hits, misses = [], []
        for name, cands in refs:
            if name not in regs:
                misses.append(f"규정없음:{name}")
                miss_reg[name] += 1
                continue
            if cands is None:
                hits.append({"reg": name, "key": None, "청크": []})   # 법령 전체 참조
                continue
            # 후보를 순서대로 대 본다. 앞엣것이 더 정확한 표기다.
            found = next(((k, by_key[(name, k)]) for k in cands
                          if (name, k) in by_key), None)
            if not found:
                misses.append(f"조문없음:{name} {cands[0]}")
                miss_art[f"{name} {cands[0]}"] += 1
                continue
            hits.append({"reg": name, "key": found[0], "청크": found[1]})

        rec["_유형"] = "법령"
        rec["_근거"] = hits
        rec["_미매칭"] = misses
        rec["_청크"] = sorted({i for h in hits for i in h["청크"]})
        if hits and not misses:
            stat["전부 매칭"] += 1
        elif hits:
            stat["일부 매칭"] += 1
        elif refs:
            stat["매칭 실패"] += 1
        else:
            stat["근거 해석 실패"] += 1
        out.append(rec)

    total = len(rows)
    usable = sum(1 for r in out if r["_유형"] == "매뉴얼" or r.get("_근거"))
    print(f"규칙 {total}건  →  사용 가능 {usable}건 ({usable/total*100:.0f}%)\n")
    print("== 유형별 ==")
    for k, v in stat.most_common():
        print(f"  {v:>5}  {k}")

    if miss_reg:
        print(f"\n== 코퍼스에 없는 규정 ({len(miss_reg)}종) ==")
        for k, v in miss_reg.most_common(a.show):
            print(f"  {v:>4}  {k}")
    if miss_art:
        print(f"\n== 규정은 있는데 그 조문이 없음 ({len(miss_art)}종) ==")
        for k, v in miss_art.most_common(a.show):
            print(f"  {v:>4}  {k}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
