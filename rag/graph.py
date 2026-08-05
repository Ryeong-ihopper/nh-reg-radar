# -*- coding: utf-8 -*-
"""랭그래프 껍데기 — DAP 주피터에서 실행할 형태.

**로직은 여기 없다.** `pipeline.py` 의 순수 함수를 노드로 감쌀 뿐이다. 그렇게 나눈
이유는 하나다 — 로직이 그래프 안에 들어가면 **랭그래프 없이는 한 줄도 못 돌려 본다.**
DAP 의 랭그래프 버전이 우리 것과 다를 수 있고, 그때 고칠 곳이 이 파일 하나여야 한다.

랭그래프가 여기서 실제로 해 주는 일:
  · 단계마다 상태를 남긴다 — 어디서 무엇이 비었는지 사후에 볼 수 있다
  · 근거가 없으면 판정을 건너뛰는 분기
  · 체크포인터를 붙이면 광고 수백 건을 돌리다 끊겨도 이어서 돌릴 수 있다

  python rag/graph.py --ad 2026_005_예금성 --product DEPOSIT
"""
import os
import sys
import json
import argparse
from typing import TypedDict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pipeline as P
import search as S


class State(TypedDict, total=False):
    ad_id: str
    ad_text: str
    how: str
    medium: Optional[str]
    product: Optional[str]
    queries: list
    query_source: str
    candidates: list
    evidences: list
    reranker: str
    verdict: dict


# 색인은 노드마다 다시 읽으면 안 된다(8,309건 × 광고 수). 모듈 수준에 한 번만 둔다.
_ROWS, _N_RULES = None, None


def _index():
    global _ROWS, _N_RULES
    if _ROWS is None:
        _ROWS, _N_RULES = S.load_index()
    return _ROWS, _N_RULES


def n_make_queries(state: State) -> State:
    qs, src = P.make_queries(state["ad_text"])
    return {"queries": qs, "query_source": src}


def n_retrieve(state: State) -> State:
    rows, _ = _index()
    cands = P.retrieve(state["queries"], rows, state.get("how", "hybrid"),
                       P.CAND_K, state.get("medium"), state.get("product"))
    return {"candidates": cands}


def n_rerank(state: State) -> State:
    rows, _ = _index()
    top, src = P.rerank(state["ad_text"], state["candidates"], rows, P.TOP_K)
    return {"evidences": top, "reranker": src}


def n_judge(state: State) -> State:
    rows, _ = _index()
    return {"verdict": P.judge(state["ad_text"], state["evidences"], rows)}


def n_no_evidence(state: State) -> State:
    """근거가 하나도 없을 때. **LLM 을 부르지 않는다.**

    근거 없이 판정을 시키면 모델이 상식으로 답을 지어내고, 그게 근거 있는 판정과
    같은 모양으로 나온다. 검색이 실패한 것을 판정 실패로 덮으면 안 된다.
    """
    return {"verdict": {"판정": "확인필요", "사유": "검색된 근거가 없습니다.",
                        "근거": [], "수정제안": "", "_source": "no-evidence"},
            "reranker": "none"}


def has_evidence(state: State) -> str:
    return "judge" if state.get("evidences") else "no_evidence"


def build():
    from langgraph.graph import StateGraph, START, END

    g = StateGraph(State)
    g.add_node("make_queries", n_make_queries)
    g.add_node("retrieve", n_retrieve)
    g.add_node("rerank", n_rerank)
    g.add_node("judge", n_judge)
    g.add_node("no_evidence", n_no_evidence)

    g.add_edge(START, "make_queries")
    g.add_edge("make_queries", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_conditional_edges("rerank", has_evidence,
                            {"judge": "judge", "no_evidence": "no_evidence"})
    g.add_edge("judge", END)
    g.add_edge("no_evidence", END)
    return g.compile()


def to_review_item(state: State):
    """스키마의 review_items / review_item_evidences 모양으로."""
    rows, n_rules = _index()
    return {
        "광고id": state.get("ad_id"),
        "질의": state.get("queries", []),
        "_질의출처": state.get("query_source"),
        "_리랭커": state.get("reranker"),
        "근거": [{
            "rank_no": n,
            "evidence_id": rows[i]["evidence_id"],
            "kind": "규칙" if i < n_rules else "조문",
            "title": rows[i].get("title", ""),
            "article_no": rows[i].get("article_no", ""),
            "match_source": "HYBRID" if state.get("how") == "hybrid"
                            else str(state.get("how", "")).upper(),
            "matched_queries": q,
        } for n, (i, q) in enumerate(state.get("evidences") or [], 1)],
        "판정": state.get("verdict", {}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ad")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--how", default="bm25", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("--product", default=None)
    ap.add_argument("--medium", default=None)
    ap.add_argument("--out")
    a = ap.parse_args()

    app = build()
    ads = P.load_ads()
    if a.ad:
        ads = [x for x in ads if x["광고id"] == a.ad]
    elif not a.all:
        ads = ads[:1]

    out = []
    for ad in ads:
        st = app.invoke({"ad_id": ad["광고id"], "ad_text": ad["text"],
                         "how": a.how, "medium": a.medium, "product": a.product})
        item = to_review_item(st)
        out.append(item)
        print("=" * 78)
        print(f"{item['광고id']}  질의 {len(item['질의'])}개 [{item['_질의출처']}]"
              f" · 리랭커 {item['_리랭커']}")
        for e in item["근거"]:
            print(f"   {e['rank_no']}. [{e['kind']}] {e['evidence_id']} "
                  f"{e['title'][:52]}")
        print(f"   판정: {item['판정'].get('판정') or '—'}")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"\n저장: {a.out}  ({len(out)}건)")


if __name__ == "__main__":
    main()
