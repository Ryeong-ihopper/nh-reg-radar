# -*- coding: utf-8 -*-
"""광고 → 규칙 → 조문. **손으로 쓴 질의 규칙을 버리고 데이터로 대체한다.**

지금 질의 생성은 이렇게 생겼다.

    (r"연\\s*최고|우대금리", "이자율의 범위와 산출기준… 표시해야 하는 의무"),
    (r"예금자보호|5천만원",  "예금자보호 대상 여부와 보호 한도 표시 의무"),
    …14개

**주먹구구다.** 14개 밖의 표현은 질의가 아예 안 만들어지고, 규정이 바뀌면 손으로
고쳐야 하고, 왜 저 14개인지 근거가 없다.

같은 일을 데이터가 이미 한다. **규칙 1,744건이 광고 어휘와 법률 어휘 사이의
다리다.**

    규칙 R-0605  "예금성 의무표시 - 예금자보호법 등에 따른 부보내용"
      판단기준   "예금자보호 문구와 보호한도가 광고물에 표기되어 있는지 확인"
      근거       은행 광고심의 기준 제16조 제1항 제5호 라목

규칙 문장은 **실무 어휘**로 쓰여 있어 광고문과 말이 겹치고, **근거로 조문이 달려
있다.** 그래서 두 걸음으로 간다.

    ① 광고 청크 → 규칙 검색        광고 말투 ↔ 실무 말투. 겹친다
    ② 걸린 규칙의 근거 → 조문       링크를 따라간다. 검색이 아니라 조회다

손으로 쓴 14개가 하려던 일을 규칙 1,744건이 대신한다. 규칙이 늘면 저절로 늘어난다.

  python rag/twohop.py --ad 2026_004_예금성
  python rag/twohop.py --measure          # 심의사례 15건으로 채점
"""
import os
import re
import sys
import json
import math
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
INDEX = os.path.join(RAG, "rule_index.jsonl")
VECS = os.path.join(RAG, "vectors.f16.npy")
NL = chr(10)
RRF_K = 60


def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"


def tokenize(s):
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", str(s or ""))
    for w in re.findall(r"[가-힣]+", str(s or "")):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out


class BM25:
    def __init__(self, rows):
        docs, df = [], collections.Counter()
        for r in rows:
            tf = collections.Counter(tokenize(index_text(r)))
            docs.append(tf)
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1+(n-c+0.5)/(c+0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in d.items():
                self.inv[t].append((i, f))
        self.dl = [sum(d.values()) for d in docs]
        self.avgdl = sum(self.dl)/max(n, 1)

    def __call__(self, q, k=50, allow=None):
        K1, B = 1.2, 0.75
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = self.inv.get(t)
            if not post:
                continue
            w = self.idf[t]
            for i, f in post:
                if allow is not None and not allow(i):
                    continue
                sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*self.dl[i]/self.avgdl))
        return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]


def rrf(*rankings, top=50):
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


def ad_chunks(text, max_chars=500):
    out, buf = [], []
    for line in text.split(NL):
        line = line.strip()
        if not line:
            continue
        buf.append(line)
        if len(NL.join(buf)) >= max_chars:
            out.append(NL.join(buf))
            buf = []
    if buf:
        out.append(NL.join(buf))
    return [c for c in out if len(c) >= 25] or [text[:500]]


class TwoHop:
    def __init__(self):
        self.rows = [json.loads(l) for l in open(INDEX, encoding="utf-8")]
        self.n_rules = sum(1 for r in self.rows
                           if r["evidence_id"].startswith("R-"))
        self.bm = BM25(self.rows)
        self.V = None
        import numpy as np
        if os.path.exists(VECS):
            V = np.load(VECS).astype("float32")
            if V.shape[0] == len(self.rows):
                self.V = V
        self.EMB = None
        # 규칙 → 근거 조문 행번호. **검색이 아니라 링크다.** 규칙에 이미 붙어 있는
        # 근거를 따라가는 것이라 틀릴 수가 없다.
        by = collections.defaultdict(list)
        for i, r in enumerate(self.rows):
            if r["evidence_id"].startswith("R-"):
                continue
            # 「제2-38조」·「제16조의2」 같은 가지번호를 다 받아야 한다.
            # 「제\d+조」만 보면 규정류 조문이 통째로 안 잡혀 근거가 거의 안 붙는다.
            m = re.match(r"\[([^\]]+)\]\s*(제\s*\d+(?:-\d+)?\s*조(?:\s*의\s*\d+)?)",
                         r.get("content") or "")
            if m:
                by[(m.group(1).strip(), re.sub(r"\s", "", m.group(2)))].append(i)
        self.by_article = by
        # 매뉴얼 코드 → 그 매뉴얼의 청크들. 매뉴얼 근거를 붙이는 데 쓴다.
        bym = collections.defaultdict(list)
        for i, r in enumerate(self.rows):
            code = (r.get("metadata_json") or {}).get("출처매뉴얼")
            if code and r["evidence_id"].startswith("M-"):
                bym[code].append(i)
        self.by_manual = bym

    def _emb(self):
        if self.EMB is None:
            import torch
            torch.set_num_threads(os.cpu_count() or 4)
            from sentence_transformers import SentenceTransformer
            self.EMB = SentenceTransformer("BAAI/bge-m3")
        return self.EMB

    def _vec(self, q, k, only_rules, keep=None):
        import numpy as np
        qv = self._emb().encode([q], normalize_embeddings=True).astype("float32")[0]
        s = self.V @ qv
        if only_rules:
            s[self.n_rules:] = -1e9
        if keep is not None:
            mask = np.full(len(s), True)
            mask[keep] = False
            s[mask] = -1e9
        return list(np.argsort(-s)[:k])

    def _allow(self, product):
        """상품군 필터. **이게 없으면 예금 광고에 ISA·CMA 규칙이 딸려 나온다**
        (실제로 그랬다). 상품군이 빈 규칙은 「전체」라 통과시킨다 — 빼면
        금소법 기반 공통 의무가 통째로 사라진다."""
        want = {"예금성": "DEPOSIT", "대출성": "LOAN",
                "투자성": "INVESTMENT"}.get(product)

        def ok(i):
            if i >= self.n_rules:
                return False
            if not want:
                return True
            pg = self.rows[i].get("product_group") or []
            return (not pg) or (want in pg)
        return ok

    def hop1(self, ad_text, k=20, how="hybrid", product=None):
        """광고 청크마다 규칙을 찾고 RRF 로 합친다. **규칙만 본다.**"""
        chunks = ad_chunks(ad_text)
        allow = self._allow(product)
        keep = [i for i in range(self.n_rules) if allow(i)]
        ranks = []
        for c in chunks:
            if how in ("bm25", "hybrid"):
                ranks.append(self.bm(c, 50, allow=allow))
            if how in ("vector", "hybrid") and self.V is not None:
                ranks.append(self._vec(c, 50, only_rules=True, keep=keep))
        merged = rrf(*ranks, top=k) if ranks else []
        return [self.rows[i] for i in merged]

    def hop2(self, rules):
        """규칙의 근거를 따라 조문·매뉴얼을 가져온다. 링크 조회다.

        **조문만 보면 안 된다.** 규칙 1,744건 중 375건은 근거가 매뉴얼 발췌뿐이다
        (basis_origin=MANUAL_SELF). 조문만 근거로 인정하면 그 375건은 근거가
        영영 0건이고, 「왜 이게 위반인가」에 답할 수 없다.

            R-0610 근거   유형 "발췌" · article_no "M04 p.27"
                         본문 "기간/금액별로 상이한 이율 적용 시 …"

        매뉴얼 코드(M04)로 색인의 매뉴얼 청크를 찾는다. 못 찾으면 **근거에 적힌
        발췌 본문을 그대로 쓴다** — 조문이 아니어도 근거는 근거다.
        """
        out, seen = [], set()
        for r in rules:
            for b in (r.get("근거") or []):
                reg = str(b.get("규정") or "").strip()
                ano = str(b.get("article_no") or "").strip()
                key = (reg, re.sub(r"\s", "", ano))
                hits = self.by_article.get(key, [])
                if hits:
                    for i in hits:
                        if i not in seen:
                            seen.add(i)
                            out.append((self.rows[i], r["evidence_id"]))
                    continue
                # 매뉴얼 발췌 — 「M04 p.27」에서 코드를 뽑아 매뉴얼 청크를 찾는다
                m = re.match(r"(M\d{2})", ano)
                if m:
                    code = m.group(1)
                    got = [i for i in self.by_manual.get(code, [])][:2]
                    for i in got:
                        if i not in seen:
                            seen.add(i)
                            out.append((self.rows[i], r["evidence_id"]))
                    if got:
                        continue
                # 그것도 없으면 근거에 적힌 발췌 본문을 그대로 근거로 낸다
                body = str(b.get("본문") or "").strip()
                if body:
                    out.append(({"evidence_id": f"EXCERPT:{ano or reg}",
                                 "article_no": ano or None,
                                 "title": str(b.get("제목") or "") or (reg if reg != "-" else "매뉴얼 발췌"),
                                 "content": body}, r["evidence_id"]))
        return out

    def review(self, ad_text, k=10, how="hybrid", product=None):
        rules = self.hop1(ad_text, k, how, product)
        arts = self.hop2(rules)
        return rules, arts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--how", default="hybrid",
                    choices=("bm25", "vector", "hybrid"))
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("-k", type=int, nargs="*", default=[1, 3, 5, 10])
    a = ap.parse_args()

    th = TwoHop()
    print(f"색인 {len(th.rows):,} · 규칙 {th.n_rules:,} · "
          f"벡터 {'있음' if th.V is not None else '없음'}")

    ads = {}
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)

    if a.ad:
        pg = ("예금성" if "예금성" in a.ad else
              "대출성" if "대출성" in a.ad else None)
        rules, arts = th.review(ads[a.ad]["text"], 10, a.how, pg)
        print(f"\n== {a.ad} ==")
        print("\n걸린 규칙:")
        for i, r in enumerate(rules, 1):
            print(f"  {i:2d}. {r['evidence_id']} {r.get('title','')[:56]}")
        print("\n근거 조문(규칙 링크를 따라감):")
        for art, rid in arts[:10]:
            print(f"  {art['evidence_id']} {art.get('article_no') or '':10s} "
                  f"{art.get('title','')[:40]}   ← {rid}")

    if a.measure:
        gold = json.load(open(os.path.join(RAG, "ad_gold.json"),
                              encoding="utf-8"))["건"]
        KL = a.k
        print(f"\n심의사례 {len(gold)}건 · 「광고→규칙→조문」")
        print(f"{'검색':10s} " + "  ".join(f"R@{k:<4d}" for k in KL))
        for how in (("bm25", "vector", "hybrid") if th.V is not None
                    else ("bm25",)):
            hit = {k: 0 for k in KL}
            n = 0
            for g in gold:
                want = {(str(x[0]), re.sub(r"\s", "", str(x[1])))
                        for x in (g.get("정답") or [])
                        if isinstance(x, (list, tuple)) and len(x) >= 2
                        and not str(x[0]).startswith("?")}
                if not want:
                    continue
                n += 1
                aid = g["광고id"]
                pg = ("예금성" if "예금성" in aid else
                      "대출성" if "대출성" in aid else None)
                rules = th.hop1(ads[aid]["text"], max(KL), how, pg)
                pos = None
                for r_, rule in enumerate(rules, 1):
                    refs = {(str(b.get("규정") or "").strip(),
                             re.sub(r"\s", "", str(b.get("article_no") or "")))
                            for b in (rule.get("근거") or [])}
                    if refs & want:
                        pos = r_
                        break
                for k in KL:
                    if pos and pos <= k:
                        hit[k] += 1
            print(f"{how:10s} " + "  ".join(f"{hit[k]/n*100:5.1f}%" for k in KL)
                  + f"   n={n}")
        print("\n※ 「걸린 규칙이 정답 조문을 근거로 달고 있나」를 센다.")
        print("  손으로 쓴 질의 규칙 14개를 하나도 안 썼다.")


if __name__ == "__main__":
    main()
