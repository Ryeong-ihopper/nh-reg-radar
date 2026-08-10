# -*- coding: utf-8 -*-
"""규칙을 **문구로 먼저 판정**한다. LLM 은 못 정한 것만 받는다.

2026-08-07 심의사례로 채점하니 LLM 판정이 **0/5** 였다. 원인을 보니 둘이었다.

  ① 물어보지 않았다
     「만기후이율 누락」 지적에 해당하는 규칙 R-0610 이 규칙리스트에는 있는데
     체크리스트 87문항에는 없다. 안 물었으니 못 잡는 게 당연하다.

  ② 넓게 읽었다
     「수신거부 무료전화를 표시했는가」에 광고의 "수신거부 : 올원뱅크>알림설정"
     을 인용하며 OK 라고 했다. **인용은 진짜였다** — 환각이 아니라 문항을 느슨
     하게 해석한 것이다.

둘 다 LLM 을 잘 달래서 고칠 문제가 아니다. ①은 **규칙을 더 던지면** 되고,
②는 **글자로 확인하면** 된다. 「만기후이율」이 광고에 있느냐 없느냐는 판단이
아니라 사실이다.

    규칙 402건 → 문구 매칭 → OK/NG 확정
                          → 문구가 없는 규칙은 판정하지 않고 LLM 으로 넘긴다

**문구가 없으면 판정하지 않는다.** 억지로 판정하면 근거 없는 NG 가 쏟아지고,
그것을 걸러내느라 사람이 더 일하게 된다.

  python rag/rule_match.py --ad 2026_004_예금성
  python rag/rule_match.py --score          # 심의사례로 채점
"""
import os
import re
import sys
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
# **경로를 박아 두지 않는다.** `review.py` 가 실행 중에 `load_rules()` 를 부르므로
# 이게 박혀 있으면 다른 PC 에서 바로 FileNotFoundError 다.
#   setx NH_RULES_XLSX "D:\...\규칙리스트.xlsx"
XLSX = os.environ.get(
    "NH_RULES_XLSX",
    os.path.join(os.path.expanduser("~"), "Downloads",
                 "NH_광고심의_규칙리스트_조문지도, 체크리스트 통합.xlsx"))
ADS = os.path.join(RAG, "ads.jsonl")
SCOPE = os.path.join(RAG, "scope_excluded.json")

PRODUCT = {"예금성": "예금", "대출성": "대출", "투자성": "투자"}

# ── 문구를 어디서 얻나 ────────────────────────────────────────────────────
# 셋인데 **출처를 반드시 구분해 남긴다.** 수동으로 적은 문구가 잘 맞는 것은
# 당연하고, 그것을 성능으로 읽으면 안 된다.
#
#   따옴표  판단기준 안의 「」·"" 안 문구. 담당자가 직접 적은 것이라 가장 믿을 만하다
#   수동    내가 적은 것. **적은 이유를 같이 남긴다**
#
# **나열 패턴에서 뽑는 방법은 버렸다.** 「광고물에 은행 명칭이 표기되어 있는지」에서
# 「광고물에 은행 명칭이」를 뽑아 광고에서 찾으니 당연히 없고, 전부 NG 가 됐다.
# 규칙 문장의 조각은 **광고에 나타날 말이 아니다.**
#
# 여기서 갈래가 갈린다. 의무표시사항에는 두 종류가 있다.
#
#   고정 문구형   광고에 그 글자가 그대로 나온다
#                 「(광고)」 · 「예금자보호법에 따라 보호」 · 「만기후이율」
#                 → 문구 매칭이 된다
#   값 형        광고마다 값이 다르다
#                 은행 명칭 = "NH농협은행" · 이자율 = "연 2.3%"
#                 → 문구로는 못 찾는다. 값을 알아보는 눈이 필요하다
#
# 지금 문구 매칭이 다룰 수 있는 것은 **고정 문구형뿐이다.**
_QUOTE = re.compile(r"[\"“”「『]([^\"“”「」『』]{2,30})[\"“”」』]")

# 따옴표 안이 **문구가 아니라 예시**인 경우를 알아본다. 「연 최저 X.XX%」의
# X.XX 는 자리표시자지 찾을 글자가 아니다. 이걸 그대로 찾으면 모든 광고가 NG 가
# 된다(실제로 8건 중 6건이 그랬다).
_PLACEHOLDER = re.compile(r"[XxOo○×]{2,}|[XxOo]\.[XxOo]|\d-[Xx]{3,}")

# 문구 사전은 **코드에 두지 않는다.** 규칙은 DB 에 있는데 판정 문구만 코드에
# 박혀 있으면 규칙 하나 늘 때마다 배포해야 하고, 담당자가 직접 못 고친다.
# 지금은 파일이지만 자리는 **규칙 테이블의 컬럼**이다(파일 안 _대상컬럼 참고).
PATTERNS = os.path.join(RAG, "rule_patterns.json")


def load_patterns(path=PATTERNS):
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8")).get("규칙", {})


def _s(x):
    return str(x if x is not None else "").strip()


def norm(s):
    """띄어쓰기·가운뎃점만 지운다. **그 이상 지우지 않는다** — 「무료전화」와
    「무료 전화」는 같게 보되, 「수신거부」와 「수신 거부 무료전화」는 달라야 한다."""
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))


# 규칙이 요구하는 긴 문구는 광고마다 말이 조금씩 다르다.
#   규칙  "계약체결 전 금융상품 설명서 및 약관을 읽어 볼 것"
#   광고  "계약 체결 전 상품설명서와 약관을 반드시 읽어보시기 바랍니다"
# 글자 그대로 찾으면 없다고 나오지만 **뜻은 같다.** 그래서 긴 문구는 낱말로
# 쪼개 얼마나 겹치는지를 본다. 짧은 문구(「(광고)」)는 그대로 있어야 한다 —
# 쪼개면 아무 데나 걸린다.
_LONG = 8
_WORD_HIT = 0.7


def _words(p):
    return [w for w in re.split(r"[^가-힣A-Za-z0-9]+", str(p)) if len(w) >= 2]


def _has(phrase, normalized_ad):
    if len(norm(phrase)) < _LONG:
        return norm(phrase) in normalized_ad
    ws = _words(phrase)
    if not ws:
        return norm(phrase) in normalized_ad
    hit = sum(1 for w in ws if norm(w) in normalized_ad)
    return hit / len(ws) >= _WORD_HIT


_COND = re.compile(r"^([^,]{2,60}?)\s*(?:하는|인|되는)?\s*경우[,\s]")


def _condition(rule):
    """조건부 규칙이면 조건 낱말 목록, 아니면 빈 목록."""
    m = _COND.match(_s(rule.get("판단 기준")))
    if not m:
        return []
    return [w for w in _words(m.group(1)) if len(w) >= 2][:4]


def phrases_of(rule, patterns):
    """(문구 목록, 출처). 문구를 못 만들면 빈 목록 — 그러면 판정하지 않는다."""
    rid = _s(rule.get("규칙ID"))
    p = patterns.get(rid)
    if p:
        return list(p["values"]), ("정규식" if p["type"] == "REGEX" else "사전")
    body = _s(rule.get("판단 기준"))
    q = [x.strip() for x in _QUOTE.findall(body + " " + _s(rule.get("요약")))]
    q = [x for x in q if len(norm(x)) >= 2]
    # 자리표시자가 든 것은 예시다. 정규식을 손으로 붙이기 전까지는 판정하지 않는다.
    if any(_PLACEHOLDER.search(x) for x in q):
        return [], "예시(정규식 필요)"
    # 문구가 아니라 문서 이름인 경우 — 「…지침」·「…규정」으로 끝나면 찾을 말이 아니다
    q = [x for x in q if not re.search(r"(지침|규정|기준|법률|매뉴얼)$", x.strip())]
    if q:
        return q, "따옴표"
    return [], "없음"


def load_rules(xlsx=XLSX, product="예금"):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    it = wb["규칙"].iter_rows(values_only=True)
    head = [_s(c) for c in next(it)]
    rules = [dict(zip(head, r)) for r in it if r and r[0] is not None]
    wb.close()

    scope = json.load(open(SCOPE, encoding="utf-8"))["규칙"] if os.path.exists(SCOPE) else {}
    pats = load_patterns()
    want = {product, "전체"}
    out = []
    for r in rules:
        if not ({x.strip() for x in _s(r.get("상품")).split(",")} & want):
            continue
        if _s(r.get("규칙ID")) in scope:        # 제외 예정은 판정하지 않는다
            continue
        ph, src = phrases_of(r, pats)
        r["_문구"], r["_문구출처"] = ph, src
        out.append(r)
    return out


def judge(rule, ad_text):
    """문구로 정할 수 있으면 OK/NG, 못 정하면 None(LLM 으로 넘김)."""
    ph = rule["_문구"]
    if not ph:
        return None, []
    if rule["_문구출처"] == "정규식":
        # 정규식은 띄어쓰기를 지운 문자열에 걸면 안 된다 — \s 가 뜻을 잃는다
        m = re.search(ph[0], ad_text)
        return ("OK" if m else "NG"), ([m.group(0)] if m else [])
    # 조건부 규칙 — 조건이 안 맞는 광고는 판정 대상이 아니다(N/A).
    # 「환율·주가연동예금 등을 광고하는 경우」를 적금 광고에 들이대면 안 된다.
    cond = _condition(rule)
    if cond and not any(norm(c) in norm(ad_text) for c in cond):
        return "N/A", []

    A = norm(ad_text)
    prohibit = _s(rule.get("카테고리")) == "금지"
    found = [p for p in ph if _has(p, A)]
    if prohibit:
        return ("NG" if found else "OK"), found
    # 표시의무 — 나열형이면 **하나라도 빠지면 NG** 다. 「기간별·중도해지·만기후」는
    # 셋 다 있어야 한다는 뜻이지 아무거나 하나가 아니다.
    return ("OK" if len(found) == len(ph) else "NG"), found


def audit(ad_text, rules):
    out = []
    for r in rules:
        v, found = judge(r, ad_text)
        out.append({"규칙ID": _s(r.get("규칙ID")), "요약": _s(r.get("요약")),
                    "카테고리": _s(r.get("카테고리")), "근거": _s(r.get("근거 상세")),
                    "문구출처": r["_문구출처"], "문구": r["_문구"],
                    "판정": v, "찾은문구": found})
    return out


def load_ads():
    seen = {}
    for l in open(ADS, encoding="utf-8"):
        a = json.loads(l)
        seen.setdefault(a["광고id"], a)
    return seen


# ── 채점 ──────────────────────────────────────────────────────────────────
# 심의사례 지적 → (광고 판본, 그 지적을 잡아야 할 규칙).
# **「NG 가 하나라도 나왔나」로 세면 안 된다.** 오탐이 쏟아져도 만점이 된다.
# 지적에 해당하는 그 규칙이 NG 인지를 보고, 오탐은 따로 센다.
CASES = [
    ("2026_004_예금성", "R-0610", "만기후이율 및 중도해지이율 누락"),
    ("2026_005_예금성", "R-0632", "수신거부를 앱푸시 방법으로 기재"),
    ("2026_007_예금성", None, "이자 지급제한 사유 누락 (해당 규칙 미확인)"),
]

# 오탐 확인용 — 이 광고들은 그 지적을 **안 받았다**. 같은 규칙이 여기서도 NG 면
# 규칙이 아니라 문구 사전이 틀린 것이다.
CONTROL = ["2026_005_예금성", "2026_006_예금성", "2026_007_예금성"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--product", default="예금")
    a = ap.parse_args()

    rules = load_rules(product=a.product)
    src = collections.Counter(r["_문구출처"] for r in rules)
    print(f"{a.product}성 규칙 {len(rules)}건 (제외예정 뺀 것)")
    for k in ("따옴표", "정규식", "사전", "예시(정규식 필요)", "없음"):
        print(f"  문구 {k}  {src[k]:4d}")
    covered = sum(v for k, v in src.items() if k in ("따옴표", "정규식", "사전"))
    print(f"  → 문구로 판정 가능 {covered}건 ({covered/len(rules)*100:.0f}%) · "
          f"나머지 {src['없음']}건은 LLM 몫\n")

    ads = load_ads()
    if a.ad:
        v = audit(ads[a.ad]["text"], rules)
        c = collections.Counter(str(x["판정"]) for x in v)
        print(f"{a.ad}  {dict(c)}")
        for x in v:
            if x["판정"] == "NG":
                print(f"  NG  {x['규칙ID']}  {x['요약'][:52]}")
                print(f"      찾은 문구 {x['찾은문구'] or '없음'} / 찾던 것 {x['문구']}")

    if a.score:
        print("== 심의사례 채점 ==")
        done = [c for c in CASES if c[1]]
        for aid, rid, 지적 in CASES:
            if not rid:
                print(f"  – {aid}  {지적}")
                continue
            v = {x["규칙ID"]: x for x in audit(ads[aid]["text"], rules)}
            x = v.get(rid)
            ok = x and x["판정"] == "NG"
            print(f"  {'○' if ok else '✕'} {aid}  {rid}  지적: {지적}")
            print(f"        판정 {x['판정'] if x else '규칙 없음'} · "
                  f"찾은 문구 {x['찾은문구'] if x else '-'}")
        print(f"\n  채점 가능한 것 {len(done)}/{len(CASES)}건 "
              f"(나머지는 해당 규칙을 아직 못 짚음)")

        print("\n== 오탐 — 지적 안 받은 광고에서도 NG 가 나오나 ==")
        for aid in CONTROL:
            v = audit(ads[aid]["text"], rules)
            ng = [x for x in v if x["판정"] == "NG"]
            print(f"  {aid}  NG {len(ng)}건 " +
                  (" · ".join(f"{x['규칙ID']}" for x in ng[:6]) or "없음"))

        print("\n※ R-0610 의 문구는 **내가 수동으로 적은 것**이라 맞는 게 당연하다.")
        print("  이 숫자를 성능으로 읽으면 안 된다. 지금 확인된 것은 「문구가 있으면")
        print("  판정이 갈린다」는 사실이지 「문구 사전을 자동으로 만들 수 있다」가")
        print("  아니다. 자동 추출은 따옴표 8건뿐이고 나머지는 사람이 적어야 한다.")


if __name__ == "__main__":
    main()
