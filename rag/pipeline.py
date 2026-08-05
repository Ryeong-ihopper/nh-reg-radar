# -*- coding: utf-8 -*-
"""광고 심의 파이프라인 — 순수 함수 4개.

    광고문 → ① 질의 생성 → ② 검색 → ③ 리랭킹 → ④ 판정

**랭그래프를 여기 넣지 않는다.** DAP 주피터에 랭그래프가 깔려 있어 배포는 그쪽으로
하지만, 핵심 로직이 그래프 안에 들어가면 **랭그래프 없이는 한 줄도 못 돌려 본다.**
여기 함수들은 넘파이·표준 라이브러리만으로 돌고, `rag/graph.py` 가 이걸 노드로 감싼다.
DAP 의 랭그래프 버전이 달라지면 껍데기만 고치면 된다.

  python rag/pipeline.py --ad 2026_001_대출성
  python rag/pipeline.py --text "연 최고 7.0% 우대금리 제공"
  python rag/pipeline.py --all --out output/_rag/review_items.json
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm
import search as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
ADS = os.path.join(RAG, "ads.jsonl")
AD_CHUNKS = os.path.join(RAG, "ad_chunks.jsonl")

TOP_K = 5           # ADR-0043: 검토항목 하나에 근거 1~5개
CAND_K = 30         # 리랭커에 넘길 후보 수


# ── ① 질의 생성 ───────────────────────────────────────────────────────────
_QGEN = """다음은 금융상품 광고문입니다. 이 광고가 광고심의 규정에 걸릴 수 있는
쟁점을 찾아, 규정을 검색할 질의를 만드세요.

규칙:
- 광고에 실제로 나온 표현을 근거로만 만들 것. 없는 쟁점을 지어내지 말 것
- 질의는 규정 용어로 쓸 것 (예: "이자율의 범위와 산출기준 표시 의무")
- 한 줄에 하나씩, 최대 {k}개
- 다른 말은 쓰지 말 것

광고문:
{ad}"""


def make_queries(ad_text, k=8):
    """광고문 → 쟁점 질의 목록. Gemma 가 없으면 규칙 기반 목으로 간다."""
    got = llm.chat([{"role": "user", "content": _QGEN.format(k=k, ad=ad_text[:4000])}],
                   max_tokens=512)
    if got is None:
        return llm.mock_queries(ad_text, k), "mock"
    qs = [l.strip(" -•*\t") for l in got.splitlines() if l.strip()]
    qs = [q for q in qs if len(q) >= 6][:k]
    # **비면 목으로 되돌린다.** LLM 이 빈 줄이나 거절문을 주면 검색이 아무것도 못
    # 받고, 그 결과가 「걸린 규칙 없음」으로 보인다 — 실패가 정상처럼 보이는 모양이다.
    return (qs, "llm") if qs else (llm.mock_queries(ad_text, k), "mock-fallback")


# ── ② 검색 ────────────────────────────────────────────────────────────────
def retrieve(queries, rows, how="hybrid", k=CAND_K, medium=None, product=None):
    """질의마다 검색해 RRF 로 합친다. (색인번호, 어느 질의에서 왔나)"""
    rankings, origin = [], {}
    for q in queries:
        got = [i for i, _ in S.search(q, rows, how, k, medium, product)]
        rankings.append(got)
        for i in got:
            origin.setdefault(i, []).append(q)
    merged = S.rrf(*rankings, top=k) if rankings else []
    return [(i, origin.get(i, [])) for i in merged]


# ── ③ 리랭킹 ──────────────────────────────────────────────────────────────
def rerank(ad_text, cands, rows, k=TOP_K, model=None):
    """교차 인코더로 다시 매긴다. 모델이 없으면 순서를 그대로 둔다.

    **없을 때 조용히 넘어가되 그 사실을 남긴다.** 리랭커를 못 돌린 결과와 돌린 결과가
    같은 모양으로 나오면, 나중에 성능을 비교할 때 무엇을 보고 있는지 알 수 없다.
    """
    if not cands:
        return [], "none"
    try:
        from FlagEmbedding import FlagReranker
    except ImportError:
        return cands[:k], "skipped(모듈 없음)"
    global _RR
    try:
        _RR
    except NameError:
        _RR = FlagReranker(model or "BAAI/bge-reranker-v2-m3", use_fp16=True)
    pairs = [[ad_text[:2000], S.index_text(rows[i])[:2000]] for i, _ in cands]
    scores = _RR.compute_score(pairs, normalize=True)
    if not isinstance(scores, list):
        scores = [scores]
    order = sorted(zip(cands, scores), key=lambda x: -x[1])[:k]
    return [(c[0], c[1]) for c, _ in order], "bge-reranker-v2-m3"


# ── ④ 판정 ────────────────────────────────────────────────────────────────
_JUDGE = """당신은 금융광고 심의 담당자입니다. 아래 광고문이 제시된 규정에
맞는지 판정하세요.

판정은 다음 셋 중 하나입니다.
- 적합: 규정 위반이 없음
- 부적합: 규정 위반이 있음
- 확인필요: 광고문만으로는 판단할 수 없음

반드시 아래 JSON 형식으로만 답하세요.
{{"판정": "적합|부적합|확인필요", "사유": "...", "근거": ["evidence_id", ...],
  "수정제안": "..."}}

규정:
{evidences}

광고문:
{ad}"""


def judge(ad_text, evidences, rows):
    """근거 묶음으로 판정. Gemma 가 없으면 판정 자리를 비워 둔다."""
    if not evidences:
        return {"판정": "확인필요", "사유": "검색된 근거가 없습니다.",
                "근거": [], "수정제안": "", "_source": "no-evidence"}
    body = "\n\n".join(
        f"[{rows[i]['evidence_id']}] {rows[i].get('title','')}\n"
        f"{(rows[i].get('content') or '')[:600]}" for i, _ in evidences)
    got = llm.chat([{"role": "user", "content": _JUDGE.format(evidences=body,
                                                             ad=ad_text[:4000])}],
                   max_tokens=1024, json_mode=True)
    if got is None:
        return {"판정": None, "사유": llm.MOCK_VERDICT,
                "근거": [rows[i]["evidence_id"] for i, _ in evidences],
                "수정제안": "", "_source": "mock"}
    try:
        out = json.loads(got)
    except json.JSONDecodeError:
        # **파싱 실패를 판정으로 바꾸지 않는다.** 「확인필요」로 뭉개면 모델이 형식을
        # 못 지킨 것과 진짜 애매한 광고가 구분되지 않는다.
        return {"판정": None, "사유": "LLM 응답을 JSON 으로 읽지 못했습니다.",
                "근거": [], "수정제안": "", "_source": "parse-error",
                "_raw": got[:500]}
    out["_source"] = "llm"
    return out


# ── 전체 ──────────────────────────────────────────────────────────────────
def review(ad_text, rows=None, n_rules=None, how="hybrid",
           medium=None, product=None, k=TOP_K):
    """광고문 하나 → 검토 결과. review_items 한 건에 해당한다."""
    if rows is None:
        rows, n_rules = S.load_index()
    queries, qsrc = make_queries(ad_text)
    cands = retrieve(queries, rows, how, CAND_K, medium, product)
    top, rrsrc = rerank(ad_text, cands, rows, k)
    verdict = judge(ad_text, top, rows)
    return {
        "질의": queries, "_질의출처": qsrc,
        "_리랭커": rrsrc,
        "근거": [{
            "rank_no": n,
            "evidence_id": rows[i]["evidence_id"],
            "kind": "규칙" if (n_rules and i < n_rules) else "조문",
            "title": rows[i].get("title", ""),
            "article_no": rows[i].get("article_no", ""),
            "match_source": "HYBRID" if how == "hybrid" else how.upper(),
            "matched_queries": q,
        } for n, (i, q) in enumerate(top, 1)],
        "판정": verdict,
    }


def load_ads():
    return [json.loads(l) for l in open(ADS, encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad", help="광고id (ads.jsonl)")
    ap.add_argument("--text", help="광고문 직접 입력")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--how", default="bm25", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("--product", default=None)
    ap.add_argument("--medium", default=None)
    ap.add_argument("--out")
    a = ap.parse_args()

    rows, n_rules = S.load_index()
    print(f"색인 {len(rows):,}건 · Gemma {'연결됨' if llm.available() else '없음(목)'}"
          f" · 검색 {a.how}\n")

    targets = []
    if a.text:
        targets = [{"광고id": "(직접입력)", "text": a.text}]
    elif a.all:
        targets = load_ads()
    elif a.ad:
        targets = [x for x in load_ads() if x["광고id"] == a.ad]
        if not targets:
            ap.error(f"광고를 못 찾음: {a.ad}")
    else:
        ap.error("--ad · --text · --all 중 하나가 필요합니다")

    out = []
    for ad in targets:
        r = review(ad["text"], rows, n_rules, a.how, a.medium, a.product)
        r["광고id"] = ad["광고id"]
        out.append(r)
        print("=" * 78)
        print(f"{ad['광고id']}  ({ad.get('상품군','')})  질의 {len(r['질의'])}개"
              f" [{r['_질의출처']}] · 리랭커 {r['_리랭커']}")
        for q in r["질의"][:4]:
            print(f"   ? {q[:70]}")
        for e in r["근거"]:
            print(f"   {e['rank_no']}. [{e['kind']}] {e['evidence_id']} "
                  f"{e['title'][:52]}")
        print(f"   판정: {r['판정'].get('판정') or '—'} · {r['판정']['사유'][:70]}")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out}  ({len(out)}건)")


if __name__ == "__main__":
    main()
