# -*- coding: utf-8 -*-
"""매뉴얼 1,026청크를 통합색인에 넣는다. **근거의 큰 몫이 빠져 있었다.**

점검하다 찾은 것 — `manual_chunks.jsonl` 1,026건이 `rule_index.jsonl` 8,309건에
하나도 안 들어가 있었다.

    금융투자협회 투자광고심사 매뉴얼 및 사례집   357청크
    여신금융협회 광고심의 업무매뉴얼             236
    은행연합회 광고심의 매뉴얼                  139
    투자광고 관련 금소법령·협회규정 안내          118
    투자광고시 금융투자상품별 유의사항 문구         59
    광고심의규정 개정 관련 FAQ                   45
    금융광고규제 가이드라인                      36
    예금성상품 광고시 준수사항                    10

규칙 1,744건의 근거 상당수가 이 매뉴얼인데 정작 본문을 검색할 수 없었다.
과제 정의가 요구하는 「내부 광고심의 매뉴얼」·「금융위 가이드라인」이 이것이다.

**뒤에 붙인다. 앞이나 중간에 끼우지 않는다.** `gold.json` 의 정답청크가
`청크번호 + n_rules` 로 계산돼 있어, 중간에 끼우면 기존 정답이 전부 어긋난다.
그러면 오늘까지 낸 측정값이 조용히 무의미해진다.

    기존   [규칙 1,744][조문 6,565]                = 8,309
    이후   [규칙 1,744][조문 6,565][매뉴얼 1,026]  = 9,335
                                    ↑ 여기만 늘어난다

  python rag/add_manuals.py
  python rag/add_manuals.py --embed      # 늘어난 만큼 벡터도 이어 붙인다(CPU 약 10분)
"""
import os
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
INDEX = os.path.join(RAG, "rule_index.jsonl")
MANUAL = os.path.join(RAG, "manual_chunks.jsonl")
VECS = os.path.join(RAG, "vectors.f16.npy")
META = os.path.join(RAG, "vectors.meta.json")

# 매뉴얼 코드 → 상품군. 매뉴얼마다 다루는 상품이 다르다. 안 나누면 예금 광고에
# 투자광고 매뉴얼이 근거로 딸려 나온다.
PRODUCT = {
    "M01": ["INVESTMENT"], "M12": ["INVESTMENT"], "M13": ["INVESTMENT"],
    "M03": ["DEPOSIT"], "M05": ["LOAN"], "M08": ["LOAN"],
}


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def to_row(m, n):
    code = m.get("code") or ""
    return {
        "evidence_id": f"M-{n:06d}",
        "evidence_type": "MANUAL",
        "title": (m.get("title") or m.get("reg") or "").strip(),
        "article_no": None,
        "content": m.get("text") or "",
        "content_summary": (m.get("text") or "")[:120],
        "product_group": PRODUCT.get(code, []),      # 빈 목록 = 상품 안 가림
        "advertisement_type": [],
        "medium": [],
        "rule_type": "REFERENCE",
        "importance": "MEDIUM",
        # 매뉴얼은 시행일 개념이 없다. 발행연도만 있다.
        "effective_date": (f"{m['year']}-01-01" if m.get("year") else None),
        "is_active": True,
        "status": "확정",
        "basis_origin": "MANUAL",
        "metadata_json": {"출처매뉴얼": code, "발행기관": m.get("issuer"),
                          "매뉴얼명": m.get("reg"), "조각": m.get("key")},
        "근거": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true", help="벡터도 이어 붙인다")
    a = ap.parse_args()

    rows = load(INDEX)
    already = sum(1 for r in rows if r["evidence_id"].startswith("M-"))
    if already:
        print(f"색인에 이미 매뉴얼 {already}건이 있다 — 다시 넣지 않는다 "
              f"(두 번 넣으면 같은 근거가 중복으로 나온다)")
        if not a.embed:
            return
        # 색인은 그대로 두고 **벡터만** 이어 붙인다. 색인과 벡터가 따로 놀면
        # 벡터 검색이 엉뚱한 행을 가리키는데 그게 겉으로 안 드러난다.
        add = [r for r in rows if r["evidence_id"].startswith("M-")]
        n0 = len(rows) - len(add)
        _embed(rows, add, n0)
        return

    mans = load(MANUAL)
    add = [to_row(m, i) for i, m in enumerate(mans)]
    n0 = len(rows)
    rows += add

    with open(INDEX, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"색인 {n0:,} → {len(rows):,}  (매뉴얼 {len(add):,}건을 뒤에 붙임)")

    import collections
    c = collections.Counter(m.get("reg") for m in mans)
    for k, v in c.most_common():
        print(f"  {v:4d}  {k}")

    if not a.embed:
        print(f"\n※ 벡터는 아직 {n0:,}개다. --embed 로 이어 붙여야 벡터 검색이 맞는다.")
        return
    _embed(rows, add, n0)


def _embed(rows, add, n0):
    """색인 뒤에 붙은 행만 임베딩해 벡터에 이어 붙인다.

    **앞부분을 다시 만들지 않는다.** 같은 모델·같은 문자열이라 값이 같을 텐데도
    다시 만들면 CPU 로 두 시간이 더 들고, 미세한 차이가 생기면 어제 낸 측정값과
    오늘 것이 왜 다른지 못 가린다.
    """
    import numpy as np
    import torch
    torch.set_num_threads(os.cpu_count() or 4)
    from sentence_transformers import SentenceTransformer

    V = np.load(VECS).astype("float32")
    if V.shape[0] == len(rows):
        print(f"벡터가 이미 {V.shape[0]:,}개 — 할 일 없음")
        return
    assert V.shape[0] == n0, f"벡터 {V.shape[0]} 와 앞부분 {n0} 이 안 맞는다"
    m = SentenceTransformer("BAAI/bge-m3")
    texts = [f"{r['title']} {r.get('article_no') or ''} {r['content']}"[:1200]
             for r in add]
    new = m.encode(texts, batch_size=8, normalize_embeddings=True,
                   show_progress_bar=True).astype("float32")
    np.save(VECS, np.vstack([V, new]).astype("float16"))
    meta = json.load(open(META, encoding="utf-8"))
    meta.update({"n": len(rows), "n_manual": len(add)})
    json.dump(meta, open(META, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"벡터 {V.shape[0]:,} → {len(rows):,}")


if __name__ == "__main__":
    main()
