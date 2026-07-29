# -*- coding: utf-8 -*-
"""
버전 간 조문 단위 diff — 변경 감지 시 "무엇이 바뀌었나"를 요약한다.
저장된 TXT(사람이 읽는 정서본)를 조문 단위로 쪼개 신설/삭제/변경 조문을 뽑는다.
모든 소스 공통(법제처·금투협·여신협·은행연합) — TXT 한 줄 = 조문/항/호 단위이므로.
"""
import re
import difflib

# 조문/별표 헤더 인식: 제1조, 제2조의2, 제1-1조(KOFIA), [별표 3]·[별지 제2호], 부칙 등
# 별지도 별표와 같은 첨부 단위다(법제처·금투협 모두 씀). 빼면 목록에서 통째로 사라진다.
_ART = re.compile(r"(제\s*\d+(?:-\d+)?조(?:의\d+)?)"
                  r"|(\[(?:별표|별지|서식|별책)[^\]]*\])|(부\s*칙)")


# 부칙 시작 줄. 소스마다 표기가 다르다.
#   법제처 TXT : "부   칙" (구분선) → "부칙 <제31553호,2021.3.23>"
#   여신협 HWP : "부칙 (2016.09.30 제정)"
_ADDENDA_HEAD = re.compile(r"^\s*부\s*칙")
# 부칙을 구분할 고정 식별자(공포번호 우선, 없으면 날짜). 순번이 아니라 이 값을 키에 쓴다.
_ADDENDA_NO = re.compile(r"제\s*(\d+)\s*호")
_ADDENDA_DATE = re.compile(r"(\d{4})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})")


_KDATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_ARTNO_N = re.compile(r"제\s*(\d+)")


def _addenda_tag(line, following=()):
    """부칙 헤더 줄 → 안정적인 식별자. 못 찾으면 None.

    은행연 문서처럼 헤더가 그냥 '부칙' 한 줄이고 날짜가 다음 줄
    "제1조(시행일) … 2022년 10월 17일부터 시행한다"에 있는 경우도 있어
    뒤따르는 줄까지 훑는다.
    """
    for src in (line,) + tuple(following):
        m = _ADDENDA_NO.search(src)
        if m:
            return f"부칙제{m.group(1)}호"
        m = _ADDENDA_DATE.search(src) or _KDATE.search(src)
        if m:
            return f"부칙{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"
    return None


def _part_title(lines, i):
    """조번호가 1로 되돌아간 지점 앞에서 문서 제목처럼 보이는 줄을 찾는다.
    (은행연은 '기준'과 '세칙' 두 규정이 한 파일에 들어 있다)"""
    for j in range(i - 1, max(-1, i - 7), -1):
        s = lines[j].strip()
        if not s or len(s) > 40:
            continue
        if _ART.search(s) or s.startswith(("|", "<", "①")) or s[0].isdigit():
            continue
        return re.sub(r"\s+", " ", s)
    return None


def split_articles(txt):
    """TXT → {조문키: [줄, ...]} (등장 순서 유지).

    부칙 안에도 제1조(시행일)·제2조… 가 따로 있다. 이를 본칙 조문과 같은 키로
    묶으면 "제1조 변경"처럼 엉뚱하게 보고되고, 순번 접미(제1조#3)로 구분하면
    부칙이 하나 늘 때마다 뒤가 밀려 가짜 변경이 생긴다.
    그래서 부칙마다 **공포번호나 날짜로 된 고정 접두**를 붙인다.
      예) 부칙2016.09.30:제1조  ·  부칙제31553호:제2조
    """
    lines = txt.splitlines()
    arts = {}
    order = []
    cur = "머리말"
    tag = None            # 지금 어느 부칙 안에 있는지
    part = None           # 한 파일에 규정이 둘 이상일 때의 구분(은행연 기준/세칙)
    seen_max = 0          # 본칙에서 지금까지 본 최대 조번호(1로 되돌아가면 새 규정)

    for i, line in enumerate(lines):
        if _ADDENDA_HEAD.match(line):
            t = _addenda_tag(line, lines[i + 1:i + 4])
            if t:         # 식별자가 있을 때만 새 부칙 시작으로 본다
                tag = t   # (법제처의 "부   칙" 구분선은 식별자가 없어 그냥 통과)
                seen_max = 0
                cur = f"{part}:{tag}" if part else tag
                if cur not in arts:
                    arts[cur] = []; order.append(cur)
                arts[cur].append(line.rstrip())
                continue

        m = _ART.search(line)
        if m and (m.start() <= 2 or line.lstrip().startswith(m.group(0))):
            label = (m.group(0) or "").replace(" ", "")
            num = _ARTNO_N.search(label)
            n = int(num.group(1)) if num else 0
            # 본칙에서 조번호가 1로 되돌아가면 다른 규정이 이어 붙은 것으로 본다
            if tag is None and n == 1 and seen_max >= 3:
                part = _part_title(lines, i) or f"제{(2 if not part else 3)}편"
                seen_max = 0
            if tag is None:
                seen_max = max(seen_max, n)
            if tag and label != "부칙":
                label = f"{tag}:{label}"
            if part:
                label = f"{part}:{label}"
            cur = label
            # 그래도 겹치면(같은 부칙 안 중복 등) 마지막 수단으로만 접미를 붙인다
            base, k = cur, 2
            while cur in arts and arts[cur]:
                cur = f"{base}#{k}"; k += 1
        if cur not in arts:
            arts[cur] = []; order.append(cur)
        arts[cur].append(line.rstrip())
    return arts, order


def diff_texts(old_txt, new_txt, max_lines=8):
    ao, _ = split_articles(old_txt)
    an, order = split_articles(new_txt)
    added = [k for k in order if k not in ao and k != "머리말"]
    removed = [k for k in ao if k not in an and k != "머리말"]
    changed = []
    for k in order:
        # 공백/빈 줄 차이는 무시 (내용 변경만 잡음)
        oc = [l for l in ao.get(k, []) if l.strip()]
        nc = [l for l in an.get(k, []) if l.strip()]
        if k in ao and k in an and oc != nc:
            d = [l for l in difflib.unified_diff(oc, nc, lineterm="", n=0)
                 if l and l[0] in "+-" and not l.startswith(("+++", "---"))
                 and l[1:].strip()]
            if d:
                changed.append({"조문": k, "diff": d[:max_lines],
                                "생략": max(0, len(d) - max_lines)})
    return {"신설": added, "삭제": removed, "변경": changed,
            "요약": f"신설 {len(added)} · 삭제 {len(removed)} · 변경 {len(changed)}"}


def inline_diff(old, new, merge_gap=6, min_run=2):
    """한 줄 안에서 '실제로 바뀐 구간'만 찾는다.

    줄 단위 diff는 120자 줄에서 3글자만 바뀌어도 줄 전체를 변경으로 표시한다.
    글자 단위로 비교하되, 너무 잘게 쪼개지면 오히려 읽기 어려우므로
      · 변경 사이에 낀 짧은 공통 구간(merge_gap 이하)은 변경에 흡수하고
      · 너무 짧은 변경 조각(min_run 미만)은 앞뒤와 합친다.
    반환: (old_segs, new_segs), seg = (op, text), op ∈ {"same", "diff"}
    """
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    ops = [list(o) for o in sm.get_opcodes()]

    # 변경과 변경 사이의 짧은 공통 구간은 변경으로 흡수 (조각남 방지)
    for i in range(1, len(ops) - 1):
        if (ops[i][0] == "equal" and ops[i][2] - ops[i][1] <= merge_gap
                and ops[i - 1][0] != "equal" and ops[i + 1][0] != "equal"):
            ops[i][0] = "replace"

    old_segs, new_segs = [], []

    def push(segs, op, text):
        if not text:
            return
        if segs and segs[-1][0] == op:
            segs[-1] = (op, segs[-1][1] + text)
        else:
            segs.append((op, text))

    for tag, i1, i2, j1, j2 in ops:
        same = tag == "equal"
        # 아주 짧은 공통 구간이 양끝에 남으면 변경으로 취급해 경계를 정리
        if same and (i2 - i1) < min_run and (old_segs or new_segs):
            same = False
        push(old_segs, "same" if same else "diff", old[i1:i2])
        push(new_segs, "same" if same else "diff", new[j1:j2])
    return old_segs, new_segs


def changed_ratio(old, new):
    """줄에서 실제로 바뀐 글자 비율(0~1). 하이라이트 범위 판단용."""
    o, n = inline_diff(old, new)
    ch = sum(len(t) for op, t in n if op == "diff")
    return ch / max(len(new), 1)


def pair_changed_lines(old_lines, new_lines):
    """삭제(-)/추가(+) 줄을 내용이 비슷한 것끼리 짝지어 준다.
    짝이 지어진 줄만 '수정'으로 보고 줄 안 비교를 할 수 있다."""
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news = old_lines[i1:i2], new_lines[j1:j2]
        used = set()
        for o in olds:
            best, score = None, 0.0
            for k, n in enumerate(news):
                if k in used:
                    continue
                r = difflib.SequenceMatcher(None, o, n, autojunk=False).ratio()
                if r > score:
                    best, score = k, r
            if best is not None and score >= 0.5:   # 절반 이상 닮았으면 같은 줄의 수정
                used.add(best)
                pairs.append(("modified", o, news[best]))
            else:
                pairs.append(("removed", o, None))
        for k, n in enumerate(news):
            if k not in used:
                pairs.append(("added", None, n))
    return pairs


def format_report(name, d):
    lines = [f"[{name}] 조문 변경 요약 — {d['요약']}"]
    if d["신설"]:
        lines.append("  신설: " + ", ".join(d["신설"][:20]))
    if d["삭제"]:
        lines.append("  삭제: " + ", ".join(d["삭제"][:20]))
    for c in d["변경"][:15]:
        lines.append(f"  변경 {c['조문']}:")
        for l in c["diff"]:
            lines.append("     " + l[:100])
        if c["생략"]:
            lines.append(f"     …(+{c['생략']}줄)")
    return "\n".join(lines)
