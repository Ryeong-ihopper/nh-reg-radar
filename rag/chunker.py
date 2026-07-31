# -*- coding: utf-8 -*-
"""
조문 단위 항목 → 임베딩에 넣을 청크.

설계 근거(rag/chunk_stats.py 실측, 대상 43건·항목 5,732개)
  조문  중앙 354자 · p90 1,328자 · p99 3,547자
  부칙  중앙 143자 · p99 10,106자
  별표  중앙 2,289자 · 최대 427,360자 — 전체 글자수의 절반이 여기 있다

그래서 규칙을 셋으로 나눈다.

1. **조문이 기본 청크다.** 이미 수집기가 나눠 놓았고 키가 안정적이라(제80조의2)
   개정 감지와 같은 단위다. 90%가 1,328자 이하라 그대로 쓸 수 있다.

2. **한도를 넘는 것만 항/호 경계에서 2차 분할한다.** 문자 수로 기계적으로 자르지
   않는다 — 조문은 항(①②③) → 호(1. 2.) → 목(가. 나.)으로 이미 나뉘어 있어
   그 경계로 자르면 문장이 끊기지 않는다.

3. **잘린 조각에는 겹침(overlap) 대신 머리글을 붙인다.** 법령은 앞뒤 문맥보다
   "어느 규정 몇 조인가"가 결정적이라, 앞 청크 꼬리를 복사하는 것보다
   `[규정명] 제12조(광고) (2/3)` 한 줄이 검색 품질에 더 기여한다. 중복 저장도 없다.

버리는 것은 없다. 별표·부칙도 전부 청크로 만들되 `type` 으로 구분해 두어
검색 단계에서 걸러 쓸 수 있게 한다(서식·경과조치는 심의 근거로 인용되지 않는다).

  python rag/chunker.py                      # 통계만
  python rag/chunker.py --out chunks.jsonl   # 파일로 저장
  python rag/chunker.py --max 1400 --target 900
"""
import os
import re
import sys
import json
import hashlib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sections
import classify

ROOT = sections.ROOT
_dropped = []


def log_drop(items):
    """인덱스에서 뺀 것을 남긴다. 조용히 줄이면 '전부 넣었다'로 읽힌다."""
    global _dropped
    _dropped = items
DEFAULT_OUT = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")

# 목표/최대 글자 수. 임베딩 모델이 정해지면 토크나이저 기준으로 다시 잡는다.
# 한국어는 모델에 따라 1토큰이 1.2~2.0자라, 512토큰 모델이면 max 를 650 근처로,
# 8k 토큰 모델(bge-m3 계열)이면 훨씬 키워도 된다.
TARGET_CHARS = 900
MAX_CHARS = 1400

# 항/호/목 경계. 이 앞에서 자른다.
_BOUNDARY = re.compile(r"^\s*(?:[①-⑳]|\d+\.|[가-힣]\.|\(\d+\))")


def _pieces(text):
    """텍스트를 자를 수 있는 최소 단위로 쪼갠다(항/호/목 → 줄 → 문장)."""
    lines = [l for l in text.split("\n") if l.strip()]
    out, cur = [], []
    for l in lines:
        if cur and _BOUNDARY.match(l):
            out.append("\n".join(cur))
            cur = []
        cur.append(l)
    if cur:
        out.append("\n".join(cur))
    # 한 조각이 그대로 최대치를 넘으면(표가 통째로 든 별표 등) 문장 단위로 더 쪼갠다
    fine = []
    for p in out:
        if len(p) <= MAX_CHARS:
            fine.append(p)
            continue
        buf = ""
        for sent in re.split(r"(?<=[.。」』\]])\s+|\n", p):
            if buf and len(buf) + len(sent) + 1 > MAX_CHARS:
                fine.append(buf)
                buf = ""
            buf = (buf + "\n" + sent).strip() if buf else sent
        if buf:
            fine.append(buf)
    return fine


def _pack(pieces, target, maximum):
    """조각들을 목표 크기까지 그리디하게 묶는다."""
    out, cur = [], ""
    for p in pieces:
        if cur and (len(cur) + len(p) + 1 > maximum
                    or len(cur) >= target):
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + p) if cur else p
    if cur:
        out.append(cur)
    return out


def _header(sec, part, total):
    """청크 앞에 붙는 한 줄. 어느 규정 어느 조문인지를 항상 들고 다니게 한다."""
    label = sec["key"] or ""
    if sec["title"]:
        label += f"({sec['title']})"
    pos = f" ({part}/{total})" if total > 1 else ""
    return f"[{sec['reg']}] {label}{pos}".strip()


def chunks_of(sec, target=TARGET_CHARS, maximum=MAX_CHARS):
    body = sec["text"]
    parts = [body] if len(body) <= maximum else _pack(_pieces(body), target, maximum)
    total = len(parts)
    out = []
    for i, p in enumerate(parts, 1):
        head = _header(sec, i, total)
        text = head + "\n" + p
        out.append({
            "reg": sec["reg"], "kind": sec["kind"], "type": sec["type"],
            "key": sec["key"], "title": sec["title"],
            "part": i, "parts": total,
            "text": text, "chars": len(text),
            "sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        })
    return out


def build(only=None, target=TARGET_CHARS, maximum=MAX_CHARS, keep_forms=False):
    secs = sections.all_sections(only)
    # 빈 서식은 광고심의 근거가 될 수 없다. 인덱스에서 뺀다(수집·변경 감지에서는
    # 그대로 둔다 — 서식이 바뀌어도 개정이다).
    dropped = []
    if not keep_forms:
        secs, dropped = classify.split_tables(secs)
        if dropped:
            log_drop(dropped)
    out, seen = [], {}
    for s in secs:
        # 같은 파일에 두 문서가 이어 붙은 경우(은행연 「기준」+「세칙」은 둘 다 제1조로
        # 시작한다) 키가 겹친다. 조용히 덮어쓰지 않도록 항목 단위로 일련번호를 붙인다.
        base = f"{s['reg']}#{s['key']}"
        occ = seen[base] = seen.get(base, 0) + 1
        if occ > 1:
            base += f"@{occ}"
        for c in chunks_of(s, target, maximum):
            c["id"] = f"{base}#{c['part']}"
            out.append(c)
    return out


def _pctl(v, p):
    return sorted(v)[int(round((len(v) - 1) * p / 100))] if v else 0


def main():
    global MAX_CHARS
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", help="이름 부분일치 대상만")
    ap.add_argument("--target", type=int, default=TARGET_CHARS)
    ap.add_argument("--max", type=int, default=MAX_CHARS, dest="maximum")
    ap.add_argument("--out", nargs="?", const=DEFAULT_OUT, default=None,
                    help="JSONL 로 저장 (경로 생략 시 output/_rag/chunks.jsonl)")
    ap.add_argument("--keep-forms", action="store_true",
                    help="빈 서식 별표도 인덱스에 넣는다(기본은 제외)")
    a = ap.parse_args()

    MAX_CHARS = a.maximum          # _pieces 가 참조한다
    cs = build(a.only, a.target, a.maximum, a.keep_forms)
    if not cs:
        print("청크가 없습니다.")
        return

    lens = [c["chars"] for c in cs]
    by = {}
    for c in cs:
        by[c["type"]] = by.get(c["type"], 0) + 1
    split = sum(1 for c in cs if c["parts"] > 1)
    src = len({(c["reg"], c["key"], c["part"] == 1) for c in cs if c["part"] == 1})

    if _dropped:
        print(f"인덱스에서 뺀 서식 별표 {len(_dropped)}개 · "
              f"{sum(len(s['text']) for s in _dropped):,}자 "
              f"(수집·변경 감지에는 그대로 남아 있음)")
    print(f"청크 {len(cs):,}개  (원본 항목 {src:,}개 → 분할된 것에서 {split:,}조각)")
    print("  유형별: " + " · ".join(f"{k} {v:,}" for k, v in by.items()))
    print(f"  길이  중앙 {_pctl(lens,50):,} · p90 {_pctl(lens,90):,} · "
          f"p99 {_pctl(lens,99):,} · 최대 {max(lens):,} · 합계 {sum(lens):,}자")
    over = sum(1 for x in lens if x > a.maximum)
    print(f"  최대치({a.maximum:,}자) 초과 {over}개"
          + ("  ← 더 쪼갤 수 없는 한 덩어리" if over else ""))

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            for c in cs:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"\n저장: {os.path.relpath(a.out, ROOT)} "
              f"({os.path.getsize(a.out)/1e6:.1f}MB)")
    else:
        print("\n[예시]")
        for c in cs[:2] + [c for c in cs if c["parts"] > 2][:2]:
            print("─" * 90)
            print(c["id"])
            print(c["text"][:300].replace("\n", " ⏎ "))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
