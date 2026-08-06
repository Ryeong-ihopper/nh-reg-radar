# -*- coding: utf-8 -*-
"""심의 체크리스트 339문항 → 광고에 던질 점검 항목.

**누락은 검색으로 잡을 수 없다.** 광고에 「예금자보호」가 없으면 거기서 나올 질의도
없다. 광고를 읽어 질의를 만드는 방식은 **있는 것만** 찾는데, 심의 지적의 큰 몫은
**없는 것**이다(실측: 판본 004→005 의 차이가 「만기후이율·중도해지이율」 한 줄,
ELD 008→009 가 「미래수익 보장 아님」 단서였다).

그래서 담당자가 실제로 하는 순서를 그대로 따른다.

    1. 상품군·매체 확인
    2. 해당 필수 표시사항 목록을 꺼내 하나씩 대조    ← 여기. 검색을 쓰지 않는다
    3. 광고 문구를 훑으며 걸리는 표현 찾기           ← 검색

**목록은 이미 있다.** 규제정책연구소가 M04+M12 를 합쳐 만든 통합체크리스트 339문항에
문항마다 근거 규정이 붙어 있다. 우리가 만들면 그건 우리 판단을 재는 것이지 심의를
재는 것이 아니다.

  python rag/checklist.py                    # 통계
  python rag/checklist.py --product 예금성    # 그 상품에 던질 문항
"""
import os
import re
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = (r"C:\Users\babie\OneDrive\Desktop\씨지인사이드"
        r"\(참고용) 데이터셋 작업 과정\01_핵심데이터"
        r"\중요_NH_광고심의_통합체크리스트.xlsx")
OUT = os.path.join(ROOT, "output", "_rag", "checklist.json")

# 광고 상품군 → 체크리스트의 「상품_구분」. 「전체」는 언제나 함께 던진다.
PRODUCT = {"예금성": "예금", "대출성": "대출", "투자성": "투자"}

# **문항의 방향을 문구로 가른다.** 대분류는 상품별로 48갈래나 되어 쓸 수 없다
# (「ELS/DLS」·「랩 어카운트」·「부동산 펀드」…). 반면 질문 어미는 두 갈래뿐이다.
#   긍정형 226건  「…을 표시하였는가?」        → 없으면 위반(누락)
#   부정형 113건  「…하지 않았는가?」          → 있으면 위반(금지)
_NEG = re.compile(r"않았는가|없는가|아닌가|하지\s*아니하였는가|금지")


def kind(question):
    """REQUIRE(있어야 함) / PROHIBIT(없어야 함)."""
    return "PROHIBIT" if _NEG.search(str(question or "")) else "REQUIRE"


def load(xlsx=XLSX):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    out = []
    for r in wb["전체_체크리스트"].iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        no, src, page, ptype, big, mid, ref, orig, q = (
            [str(x or "").strip() for x in r[:9]] + [""] * 9)[:9]
        question = q or orig
        if not question:
            continue
        out.append({
            "id": f"CL-{int(no):03d}",
            "상품": ptype, "대분류": big, "중분류": mid,
            "질문": question,
            "방향": kind(question),
            "근거": ref.replace("\n", " / "),
            "출처": f"{src} p.{page}".strip(),
            # 근거가 없는 문항이 117건 있다. 지적은 할 수 있어도 **근거를 못 댄다** —
            # 심의 의견서에 규정을 적어야 하므로 사람이 확인할 대상으로 표시해 둔다.
            "근거있음": bool(ref.strip()),
        })
    wb.close()
    return out


# 「(환율·주가연동예금의 경우) …」 「(통계수치·도표 인용 시) …」 처럼 앞에 조건이
# 달린 문항. 조건이 안 맞으면 위반이 아니라 **해당 없음**이다. 이걸 구분하지 않으면
# 지면 예금 광고에 「전송자의 명칭을 표시하였는가」가 지적으로 뜬다.
_COND = re.compile(r"^\s*[(（]([^)）]{2,40})[)）]")
# 괄호가 없어도 조건부인 것들. 어미로 잡는다.
_COND_TAIL = re.compile(r"(?:하는|인|있는|받는)\s*경우|시\s|때\s")


def is_conditional(item):
    """조건부 문항인가. 질문과 **대분류를 함께** 본다.

    조건이 대분류에만 있는 것이 있다 — 「전송자의 명칭 및 연락처를 표시하였는가?」는
    질문만 보면 무조건인데 대분류가 `전자적 전송매체 이용 광고시 준수사항` 이다.
    문자·이메일 광고에만 해당하므로 지면 광고에 지적으로 뜨면 안 된다.
    """
    q = str(item.get("질문") or "")
    big = str(item.get("대분류") or "")
    return bool(_COND.match(q) or _COND_TAIL.search(q[:40])
                or _COND_TAIL.search(big) or "시 " in big or big.endswith("시"))


# **「전체」로 분류됐지만 실제로는 투자성 전용인 문항이 섞여 있다.** M12(금투협
# 투자광고 매뉴얼)에서 온 것들인데, 통합할 때 상품 구분이 「전체」로 붙었다.
# 예금 광고에 「투자원금 손실 가능성을 표시하였는가」가 지적으로 뜨면 안 된다.
#
# **출처 매뉴얼로 가르면 안 된다.** M12 · 전체 · 필수 40건을 근거 법령별로 세어 보니
# 21건이 금소법 계열(모든 상품 공통)이고 17건만 투자성 전용이었다. 출처로 자르면
# 「수수료 부과기준·절차를 기재하였는가」(금소법§22③제2호) 같은 공통 의무가 통째로
# 사라진다.
#
# 그래서 **근거 법령과 질문 낱말**로 가른다. 근거가 투자성 법령이거나 질문이 투자성
# 상품을 이름으로 부르면 투자성 전용이다. 완벽하지 않은 어림이므로 사람이 한 번
# 훑어야 한다 — 아래 목록에 없는 표현이 나오면 새어 나간다.
_INV_BASIS = re.compile(r"협회규정|금투업규정|증발공|자본시장|투자광고")
_INV_WORD = re.compile(
    r"투자원금|금융투자상품|공모증권|투자설명서|집합투자|수익증권|파생결합|"
    r"랩\s?어카운트|투자자문|투자일임|퇴직연금|월지급식|펀드|신탁|"
    r"ELS|DLS|ELB|DLB|ELF|ETF|ETN|ELW|IMA|CMA|CFD")


def _investment_only(x):
    if x["상품"] != "전체" or x["방향"] != "REQUIRE":
        return False
    return bool(_INV_BASIS.search(x.get("근거") or "")
                or _INV_WORD.search(x.get("질문") or ""))


def for_ad(items, product=None):
    """광고 하나에 던질 문항. 해당 상품 + 「전체」. **같은 질문은 하나로 묶는다.**

    상품을 모르면 전부 던진다 — **줄이려다 빠뜨리는 것이 더 나쁘다.** 누락 검사에서
    문항이 빠지면 그 위반은 영영 안 잡힌다.

    중복을 묶는 이유는 M04 와 M12 를 합칠 때 같은 의무가 상품별로 따로 실려서다
    (「수수료 및 부대비용…」이 예금·대출·전체에 각각 있다). 그대로 던지면 같은 지적이
    여러 번 나와 사람이 세 번 확인하게 된다. **근거는 합쳐서 남긴다.**
    """
    if product:
        want = {PRODUCT.get(product, product), "전체"}
        sel = [x for x in items if x["상품"] in want]
        if PRODUCT.get(product) != "투자":
            sel = [x for x in sel if not _investment_only(x)]
    else:
        sel = list(items)

    merged, seen = [], {}
    for x in sel:
        key = re.sub(r"\s+", "", x["질문"])
        if key in seen:
            m = seen[key]
            if x["근거"] and x["근거"] not in m["근거"]:
                m["근거"] = (m["근거"] + " / " + x["근거"]).strip(" /")
            m["_묶임"].append(x["id"])
            continue
        y = dict(x, _묶임=[x["id"]], 조건부=is_conditional(x))
        seen[key] = y
        merged.append(y)
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--product", default=None, help="예금성 · 대출성 · 투자성")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()

    items = load(a.xlsx)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(items, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"체크리스트 {len(items)}문항 → {a.out}\n")
    print(f"방향:   {collections.Counter(x['방향'] for x in items).most_common()}")
    print(f"상품:   {collections.Counter(x['상품'] for x in items).most_common()}")
    n = sum(1 for x in items if not x["근거있음"])
    print(f"근거 없는 문항: {n}건 — 지적은 해도 규정을 못 댄다(사람 확인 대상)\n")

    for p in ("예금성", "대출성", "투자성"):
        sel = for_ad(items, p)
        c = collections.Counter(x["방향"] for x in sel)
        print(f"  {p} 광고 1건에 던질 문항 {len(sel):>4}개 "
              f"= 필수 {c['REQUIRE']:>3} · 금지 {c['PROHIBIT']:>3}")

    if a.show:
        sel = for_ad(items, a.product)
        print(f"\n== 표본 ({a.product or '전체'}) ==")
        for x in sel[:a.show]:
            print(f"  [{x['방향']:8s}] {x['질문'][:66]}")
            print(f"             근거 {x['근거'][:56] or '(없음)'}")


if __name__ == "__main__":
    main()
