# -*- coding: utf-8 -*-
"""**흩어진 조각을 하나로 잇는다.** 광고 하나 → 심의사례 모양 결과.

지금까지 조각들이 서로를 안 불렀다.

    twohop.py    광고 → 규칙 → 조문       찾기만 하고 판정 안 함
    detect.py    규칙 → 문구 대조 → OK/NG  찾기를 안 거치고 전부 대조
    rule_match   규칙 문구 사전
    → 셋이 따로 돈다

여기서 잇는다. **방향이 둘이고 둘 다 필요하다.**

    ① 목록 → 광고   상품군으로 규칙을 조회해 전부 대조   → 누락을 잡는다
                   **검색을 안 쓴다.** 검색은 「있는 것을 찾는 도구」라 없음을
                   증명하지 못한다. 검색을 끼우면 검색 실패가 누락으로 둔갑한다

    ② 광고 → 조문   광고 청크로 규정을 검색              → 근거를 붙인다
                   여기는 검색이 맞다. 광고에 있는 표현이 무엇에 걸리는지 찾는 일

    ③ 위치 역추적   판정에 쓴 문구를 광고 청크에서 되찾음  → bbox·offset
                   **검색이 아니라 문자열 매칭이다.** 스키마 주석이 그렇게 못 박았다
                   ("위치(bbox) 필드 없음 → target_text 로 chunks/lines 역추적")

출력은 `reviews` 테이블 모양이다.

    target_text · result_status · risk_level · reason · compliance_id · recommendation

  python rag/review.py --ad 2026_004_예금성
  python rag/review.py --all --out output/_rag/review_result.json
"""
import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
NL = chr(10)

# 규칙의 「우선순위 · 위반 시」 → risk_level. 사이트 화면의 「높음」이 이 자리다.
RISK = {("필수", "반려"): "HIGH", ("필수", "수정"): "HIGH",
        ("필수", ""): "MEDIUM", ("권장", "반려"): "MEDIUM"}


def risk_of(chk):
    imp = str(chk.get("importance") or "")
    act = str(chk.get("violation_action") or "")
    return RISK.get((imp, act)) or ("HIGH" if imp == "필수" else "LOW")


def norm(s):
    return re.sub(r"[\s·ㆍ]", "", str(s or ""))


def locate(needle, chunks):
    """문구가 광고의 어느 청크에 있나. **검색이 아니라 문자열 매칭이다.**

    벡터로 찾으면 「비슷한 곳」이 나오는데, 위치 표시는 「그 글자가 있는 곳」이어야
    한다. 비슷한 곳에 밑줄을 그으면 사람이 무엇을 고쳐야 할지 모른다.
    """
    n = norm(needle)
    if not n:
        return None
    for c in chunks:
        if n[:30] in norm(c.get("text")):
            return c
    return None


class Review:
    def __init__(self, product="예금"):
        import rule_match as RM
        # **twohop2 를 쓴다.** 옛 `twohop.py` 는 조 단위 색인(9,335)이고
        # 근거를 조까지만 따라가, 최근 측정(`ad_gold4`·호 단위 정답)과 다른
        # 알고리즘이었다. 여기만 옛것을 쓰면 화면에 뜨는 근거가 보고한 숫자와
        # 다른 경로에서 나온다.
        import twohop2 as TH
        self.RM = RM
        self.TH = TH
        self.rules = RM.load_rules(product=product)
        self.checks = {}
        p = os.path.join(RAG, f"checks_{product}.json")
        if os.path.exists(p):
            for c in json.load(open(p, encoding="utf-8"))["checks"]:
                self.checks[c["id"]] = c
        self.th = TH.TwoHop2()
        self.row_of = {r["evidence_id"]: i for i, r in enumerate(self.th.rows)
                       if r["evidence_id"].startswith("R-")}

    # ── ① 목록 → 광고 (전수 매칭, 후보를 안 자름) ──────────────────────
    def track_missing(self, ad_text, chunks):
        """규칙 **전부**를 광고 전체와 비교한다. 상위 k 로 자르지 않는다.

        자르지 않는 것이 핵심이다. 검색은 후보 50개만 보고 나머지를 안 보므로
        「못 찾음」이 「없음」을 뜻하지 못한다. 전수로 비교하면 못 찾은 것은
        정말 없는 것이다.

        광고가 1,000~2,000자라 838건을 다 대조해도 비용이 안 든다.

        **문구가 없는 규칙은 판정하지 않고 「확인필요」로 둔다.** 억지로 NG 를
        매기면 근거 없는 지적이 쏟아지고, 억지로 OK 를 매기면 놓친다.
        """
        out = []
        for r in self.rules:
            v, found = self.RM.judge(r, ad_text)
            if v is None:
                rid = self.RM._s(r.get("규칙ID"))
                chk = self.checks.get(rid, {})
                out.append({
                    "규칙": rid, "제목": self.RM._s(r.get("요약")),
                    "result_status": "확인필요",
                    "risk_level": risk_of(chk),
                    "reason": "문구로 판정할 수 없는 규칙 — 사람 또는 LLM 확인 필요",
                    "recommendation": chk.get("recommendation"),
                    "compliance_ref": chk.get("article_no"),
                    "target_text": None, "위치": None,
                    "판정근거": "UNDECIDED", "방향": "목록→광고",
                })
                continue
            if v != "NG":
                continue
            rid = self.RM._s(r.get("규칙ID"))
            chk = self.checks.get(rid, {})
            want = r.get("_문구") or []
            out.append({
                "규칙": rid,
                "제목": self.RM._s(r.get("요약")),
                "result_status": "수정필요",
                "risk_level": risk_of(chk),
                "reason": f"요구 문구를 광고에서 못 찾음: {want}",
                "recommendation": chk.get("recommendation"),
                "compliance_ref": chk.get("article_no") or self.RM._s(r.get("근거 상세")),
                "target_text": None,          # 누락은 가리킬 문구가 없다
                "위치": None,
                "판정근거": "RULE",
                "방향": "목록→광고",
            })
        return out

    # ── ② 근거 조문 붙이기 (링크 조회, 검색 아님) ───────────────────────
    def evidence_for(self, rule_ids):
        """규칙 → 근거 조문. **검색하지 않는다.**

        전에는 「검색해서 나온 상위 10개 중에 그 규칙이 있으면 근거를 붙인다」로
        했는데, 상위 10에 안 들면 근거가 안 붙었다(실제로 0건이 나왔다).
        규칙에 근거가 이미 달려 있으므로 링크를 따라가면 된다.
        """
        # **엑셀이 아니라 색인에서 규칙을 찾는다.** `rule_match.load_rules` 는
        # 엑셀 원본을 읽어 근거 필드가 없다. 근거는 `match_rules.py` 가 조문에
        # 연결하며 붙인 것이라 `rule_index_ho.jsonl` 쪽에만 있다.
        out = {}
        for rid in rule_ids:
            i = self.row_of.get(rid)
            if i is None:
                continue
            # twohop2.hop2 는 행 번호를 받아 (행, 걸린규칙, 위치) 를 준다.
            out[rid] = [self.th.rows[j] for j, _, _ in self.th.hop2([i])]
        return out

    # ── ③ 위치 역추적 ───────────────────────────────────────────────────
    def attach_location(self, findings, chunks):
        for f in findings:
            t = f.get("target_text")
            if not t:
                continue
            c = locate(t, chunks)
            if c:
                f["위치"] = {"chunk_id": c.get("chunk_id"), "bbox": c.get("bbox")}
        return findings

    def run(self, ad, product="예금", k=10):
        text = ad["text"] if isinstance(ad, dict) else ad
        chunks = ad.get("chunks") if isinstance(ad, dict) else None
        if not chunks:
            chunks = [{"chunk_id": "raw", "bbox": None, "text": text}]

        pg = {"예금": "예금성", "대출": "대출성"}.get(product)
        findings = self.track_missing(text, chunks)

        # 근거는 **규칙 링크로** 붙인다. 검색 결과와 대조하지 않는다.
        ev = self.evidence_for([f["규칙"] for f in findings])
        for f in findings:
            f["근거조문"] = [{
                "evidence_id": a["evidence_id"],
                "article_no": a.get("article_no"),
                "title": a.get("title"),
                "본문": (a.get("content") or "")[:300],
            } for a in ev.get(f["규칙"], [])[:3]]

        # 검색은 **①이 판정 못 한 규칙**을 사람·LLM 에게 넘길 때 순서를 정하는 데
        # 쓴다. 판정 자체에는 안 쓴다 — 그러면 검색 실패가 「위반 없음」이 된다.
        # twohop2.hop1 은 **청크 목록**을 받는다(전문 한 덩어리가 아니라).
        qs = [c.get("text") or "" for c in chunks if len((c.get("text") or "")) >= 15]
        qs.sort(key=len, reverse=True)
        qs = qs[:14] or [text[:500]]
        prod = {"예금성": "DEPOSIT", "대출성": "LOAN"}.get(pg)
        undecided = [self.th.rows[i]
                     for i in self.th.hop1(qs, k, "hybrid", product=prod)]

        self.attach_location(findings, chunks)
        c = collections.Counter(f["result_status"] for f in findings)
        return {
            "지적": findings,
            "판정분포": dict(c),
            "확인필요_우선순위": [{"규칙": r["evidence_id"], "제목": r.get("title")}
                            for r in undecided],
            "근거_붙은_지적": sum(1 for f in findings if f.get("근거조문")),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    ads = {}
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)

    targets = ([a.ad] if a.ad else
               sorted(ads) if a.all else [])
    if not targets:
        ap.error("--ad 또는 --all")

    engines, out = {}, {}
    for aid in targets:
        product = "대출" if "대출성" in aid else "예금"
        if product not in engines:
            engines[product] = Review(product)
        r = engines[product].run(ads[aid], product)
        out[aid] = r
        d = r["판정분포"]
        print(f"{aid:20s} 수정필요 {d.get('수정필요',0):3d} · 확인필요 "
              f"{d.get('확인필요',0):3d} · 근거 붙음 {r['근거_붙은_지적']:3d}")
        if a.ad:
            for f in r["지적"]:
                if f["result_status"] != "수정필요":
                    continue
                print(f"\n  [{f['risk_level']}] {f['규칙']} {f['제목'][:50]}")
                print(f"    {f['result_status']} · {f['reason'][:70]}")
                print(f"    근거 {f['compliance_ref']}")
                for e in f.get("근거조문", [])[:2]:
                    print(f"      {e['evidence_id']} {e['article_no'] or ''} "
                          f"{e['title'][:36]}")
                if f.get("recommendation"):
                    print(f"    개선안 {f['recommendation'][:60]}")

    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
