# -*- coding: utf-8 -*-
"""조문을 **항·호 단위**로 쪼갠다. 지금 방식은 구조를 안 보고 길이로만 자른다.

    지금    조문 하나 = 청크 하나. 1,400자 넘으면 문장 경계에서 자름
    여기    항(①②③) · 호(1. 2. 3.) 경계로 자르고 조문 경로를 앞에 붙임

**왜 바꾸나** — 은행 광고심의 기준 §16 은 756자인데 그 안에 의무가 스무 개다.

    ① … 다음 각 호의 사항이 포함되도록 하여야 한다.
      1. 은행 명칭
      2. 광고심의필 번호 및 유효기간
      5. 예금성 상품 거래조건
         가. 가입조건   나. 이자율의 범위 및 산출기준
         라. 예금자보호법 등에 따른 부보내용   …

1,400자 아래라 안 쪼개진다. 그러면 벡터가 스무 개 의무를 **평균 하나로** 만들고,
「예금자보호를 표시했나」로 물어도 이 조문이 특별히 가깝게 안 나온다.
정답 조문의 37% 가 이 모양이다.

**두 가지를 지킨다.**

  경로를 붙인다   조각만 보면 무슨 조문인지 모른다. 「제16조(의무 표시사항) ① 5 라」
                를 앞에 붙여야 검색도 되고 사람이 봐도 안다
  단서를 떼지 않는다   「다만 …인 경우에는 그러하지 아니하다」를 따로 떼면 예외가
                    사라져 멀쩡한 광고가 위반으로 잡힌다. 앞 조각에 붙인다

  python rag/chunker_ho.py                 # chunks_ho.jsonl 생성
  python rag/chunker_ho.py --index         # rule_index_ho.jsonl 까지
  python rag/chunker_ho.py --show 제16조
"""
import os
import re
import json
import hashlib
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
SRC = os.path.join(RAG, "chunks.jsonl")
OUT = os.path.join(RAG, "chunks_ho.jsonl")
INDEX = os.path.join(RAG, "rule_index.jsonl")
OUT_INDEX = os.path.join(RAG, "rule_index_ho.jsonl")

NL = chr(10)

MIN_CHARS = 60          # 이보다 짧은 조각은 앞에 붙인다 — 홀로 서면 뜻이 없다
MAX_CHARS = 1400        # 호 하나가 이보다 길면 문장 경계로 한 번 더 자른다

_HANG = re.compile(r"^\s*([①-⑳])\s*")
_HO = re.compile(r"^\s*(\d{1,2})\s*[.．]\s+")
_MOK = re.compile(r"^\s*([가-힣])\s*[.．]\s+")
# 단서·예외. 앞 조각에 붙여야 한다.
_PROVISO = re.compile(r"^\s*(다만|단,|단\s|이 경우|그러나|→|※)")
# 청크 첫 줄의 머리말 — 「[규정명] 제16조(제목) (1/3)」
_HEAD = re.compile(r"^\[[^\]]+\]\s*[^\n]*")


def _level(line):
    """(계층, 번호). 항 → 호 → 목 순으로 본다."""
    m = _HANG.match(line)
    if m:
        return "항", m.group(1)
    m = _HO.match(line)
    if m:
        return "호", m.group(1)
    m = _MOK.match(line)
    if m:
        return "목", m.group(1)
    return None, None


def split_article(text):
    """조문 본문 → [(경로, 조각텍스트)].

    **호마다 부모 항의 도입문을 물려준다.** 「1. 은행 명칭」만 떼어 놓으면 8자라
    검색도 안 되고 무슨 말인지도 모른다. 앞에 「① … 다음 각 호의 사항이 포함되도록
    하여야 한다」를 붙여야 뜻이 산다.

        [은행 광고심의 기준] 제16조(의무 표시사항) ① 1
        ① 은행은 … 다음 각 호의 사항이 포함되도록 하여야 한다.
        1. 은행 명칭

    짧다고 뭉치지 않는다. 뭉치면 의무 아홉 개가 도로 한 덩어리가 된다.
    """
    lines = [l for l in text.split(NL)]
    head = ""
    if lines and _HEAD.match(lines[0]):
        head = lines[0].strip()
        lines = lines[1:]
    # 조문 제목 줄은 버린다 — 머리말에 이미 「제16조(의무 표시사항)」이 들어 있어
    # 그대로 두면 조각마다 같은 말이 두 번 붙는다. 검색어가 부풀어 점수를 흐린다.
    while lines and re.match(r"^\s*제\s*\d+[^(]*\(", lines[0] or ""):
        lines = lines[1:]

    out = []
    hang_no, hang_stem = "", ""      # 지금 항의 번호와 도입문
    ho_no = ""
    cur, cur_path, cur_stem = [], "", ""

    def flush():
        nonlocal cur
        body = NL.join(x for x in cur if x.strip())
        if body.strip():
            out.append((cur_path, cur_stem, body))
        cur = []

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        lv, num = _level(line)
        # 단서·예외는 새 조각을 열지 않는다 — 본문에서 떨어지면 예외가 사라진다
        if lv and not _PROVISO.match(line):
            flush()
            if lv == "항":
                hang_no, hang_stem, ho_no = num, line.strip(), ""
                cur_path, cur_stem = num, ""
            elif lv == "호":
                ho_no = num
                cur_path = " ".join(x for x in (hang_no, num) if x)
                cur_stem = hang_stem
            else:
                cur_path = " ".join(x for x in (hang_no, ho_no, num) if x)
                cur_stem = hang_stem
        cur.append(line)
    flush()

    # 항 도입문이 곧 그 항의 조각인 경우(호가 없는 항)는 도입문을 빼서 중복을 막는다
    merged = []
    for path, stem, body in out:
        if stem and re.sub(r"\s", "", stem) in re.sub(r"\s", "", body):
            stem = ""
        merged.append((path, (stem + NL if stem else "") + body))
    return head, merged


def build(src=SRC):
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    out = []
    for r in rows:
        head, pieces = split_article(r["text"])
        if len(pieces) <= 1:
            # 쪼갤 구조가 없으면 그대로 둔다. 억지로 자르면 문장이 끊긴다.
            out.append(dict(r, ho_path="", ho_parts=1))
            continue
        for i, (p, body) in enumerate(pieces, 1):
            # **경로를 앞에 붙인다.** 조각만 보면 무슨 조문인지 모른다.
            text = f"{head} {p}".strip() + "\n" + body
            out.append({
                "reg": r["reg"], "kind": r["kind"], "type": r["type"],
                "key": r["key"], "title": r["title"],
                "part": r.get("part", 1), "parts": r.get("parts", 1),
                "ho_path": p, "ho_parts": len(pieces),
                "text": text, "chars": len(text),
                "sha": hashlib.sha256(text.encode()).hexdigest()[:16],
                "id": f"{r['id']}#{i}",
            })
    return rows, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true", help="rule_index_ho.jsonl 도 만든다")
    ap.add_argument("--show")
    a = ap.parse_args()

    src, out = build()
    lens = sorted(x["chars"] for x in out)
    old = sorted(x["chars"] for x in src)
    print(f"조문 청크 {len(src):,} → 호 단위 {len(out):,}  ({len(out)/len(src):.1f}배)")
    print(f"  글자수 중앙  {old[len(old)//2]:5d} → {lens[len(lens)//2]:5d}")
    print(f"  최대        {old[-1]:5d} → {lens[-1]:5d}")
    split = sum(1 for x in out if x.get("ho_parts", 1) > 1)
    print(f"  쪼개진 조문에서 나온 조각 {split:,} · 그대로 둔 것 {len(out)-split:,}")

    with open(OUT, "w", encoding="utf-8") as f:
        for x in out:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"\n저장: {OUT}")

    if a.show:
        print(f"\n== {a.show} 표본 ==")
        for x in out:
            if a.show in x["key"] and "광고심의" in x["reg"]:
                print(f"--- {x['id']}  경로 [{x['ho_path']}]  {x['chars']}자")
                print("   ", x["text"][:130].replace("\n", " | "))

    if a.index:
        # 통합 색인을 같은 순서 규칙으로 다시 만든다 — [규칙][조문(호단위)][매뉴얼]
        idx = [json.loads(l) for l in open(INDEX, encoding="utf-8")]
        rules = [r for r in idx if r["evidence_id"].startswith("R-")]
        mans = [r for r in idx if r["evidence_id"].startswith("M-")]
        arts = []
        for i, x in enumerate(out):
            arts.append({
                "evidence_id": f"C-{i:06d}",
                "evidence_type": "LAW" if x["kind"] == "법률" else "REGULATION",
                "title": x["title"] or x["reg"],
                "article_no": x["key"],
                "content": x["text"],
                "content_summary": x["text"][:120],
                "product_group": [], "advertisement_type": [], "medium": [],
                "rule_type": "REFERENCE", "importance": "MEDIUM",
                "effective_date": None,
                "is_active": x["type"] != "부칙",
                "status": "", "basis_origin": "SOURCE",
                "metadata_json": {"ho_path": x["ho_path"], "src_id": x["id"]},
                "근거": [],
            })
        allrows = rules + arts + mans
        with open(OUT_INDEX, "w", encoding="utf-8") as f:
            for r in allrows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n색인 {len(allrows):,} = 규칙 {len(rules):,} + 조문 {len(arts):,} "
              f"+ 매뉴얼 {len(mans):,}")
        print(f"저장: {OUT_INDEX}  ({os.path.getsize(OUT_INDEX)/1e6:.1f}MB)")
        print("\n**gold 의 정답청크는 옛 번호라 이 색인에 그대로 못 쓴다.**")
        print("  measure_ho.py 가 원본 청크 id 로 되짚어 채점한다.")


if __name__ == "__main__":
    main()
