# -*- coding: utf-8 -*-
"""
수집 결과(output/*.json) → 조문 단위 항목 목록.

청킹·임베딩의 입력을 만드는 공통 로더다. 수집기가 이미 조문/부칙/별표로 나눠
저장하고 항목마다 안정적인 키를 붙여 두었으므로(제80조의2, 부칙제31553호,
[별표0002]), **청크 경계를 새로 정의하지 않고 그 경계를 그대로 받는다.**
개정 감지가 쓰는 키와 같은 키를 쓰기 때문에, 나중에 "바뀐 조문만 재임베딩"이
자연스럽게 된다.

소스마다 저장 형태가 다르다.
  법제처(law/admrul)·금투협  조문/부칙/별표 배열
  여신협·은행연              첨부가 규정 원문이라 통짜 '본문' 문자열 하나
후자는 텍스트에서 조문 헤더를 찾아 나눈다.
"""
import os
import re
import sys
import json
import collections

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
TARGETS_PATH = os.path.join(ROOT, "targets.json")


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


def _s(v):
    """법제처 API 는 같은 필드를 문자열로도 리스트로도 준다(부칙 공포번호 등)."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "\n".join(x for x in (_s(i) for i in v) if x)
    if isinstance(v, dict):
        return _s(v.get("content"))
    return str(v)


def targets():
    return json.load(open(TARGETS_PATH, encoding="utf-8"))


def _record(name):
    p = os.path.join(OUT_DIR, _safe(name) + ".json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


# ── 조문 텍스트 조립 ─────────────────────────────────────────────────────
# 조문내용 아래에 항 → 호 → 목이 중첩된다. 임베딩에 넣을 텍스트는 이걸 다 편
# 하나의 문자열이다. 계층은 줄바꿈과 원래 번호(①, 1., 가.)로 남으므로 따로
# 표시를 덧붙이지 않는다.

def _article_text(a):
    # 금투협은 필드명이 다르다(조내용/조제목, 항·호 배열 없음). 법제처 이름만 보면
    # 빈 문자열이 나오고, add() 의 `if text:` 에 걸려 **조용히 버려진다** —
    # 에러도 경고도 없다(실측: 금투협 두 규정의 조문 399개가 통째로 사라져 있었고,
    # 별표는 정상이라 규정 단위로만 보면 정상으로 보였다).
    parts = [_s(a.get("조문내용") or a.get("조내용")).strip()]
    for h in a.get("항") or []:
        if _s(h.get("항내용")).strip():
            parts.append(_s(h["항내용"]).strip())
        for ho in h.get("호") or []:
            if _s(ho.get("호내용")).strip():
                parts.append(_s(ho["호내용"]).strip())
            for mok in ho.get("목") or []:
                mok = _s(mok).strip()
                if mok:
                    parts.append(mok)
    return "\n".join(p for p in parts if p)


# 개정이력 괄호. 실측(43개 대상 별표 전수)으로 쓰이는 키워드만 넣는다 — 삭제·전면개정도
# 나온다(금융지주회사감독규정 [별표0001의3]: "(전면개정 …, 삭제 2016.8.1.)").
# 한 줄에 여러 개가 이어 붙기도 한다("(신설…) (개정…) (개정…) (개정…) (개정…)" — 여신협
# [별지0060]) — 하나만 지우면 앞엣것들이 남아 제목이 되므로 **연속된 걸 통째로** 지운다.
_HIST_KW = "개정|신설|전문개정|전면개정|일부개정|삭제"
_HIST = re.compile(
    r"(?:\s*\((?:(?:" + _HIST_KW + r")[^)]*"      # (개정 2020.3.24., 삭제 …) — 키워드가 먼저
    r"|[\d.,\s]*(?:" + _HIST_KW + r"))\))+\s*$"    # (2013.12.31 개정) — 날짜가 먼저
)
# 빈 칸 서식("(     년   월   일 기준)")이 제목으로 잘못 뽑히는 걸 막는다.
# 실제 값이 채워진 "(2023년 12월 기준)"은 진짜 정보일 수 있어 건드리지 않는다 —
# 년/월/일 앞자리가 전부 비어(공백뿐) 있을 때만 서식으로 본다.
_BLANK_DATE = re.compile(r"^\(?\s*년\s*월\s*일\s*(?:기준|현재|자)?\s*\)?$")
# 「<신설 2021.10.18., 개정 2025.12.1.>」처럼 꺾쇠로 적힌 이력. 줄 어디에나 온다.
_ANG = re.compile(r"[<〈]\s*(?:개정|신설|전문개정|일부개정)[^>〉]*[>〉]")
_MARK = re.compile(r"^[<\[［]\s*(?:별지|별표|서식|첨부|별책)[^>\]］]*[>\]］]\s*")
# 본문 첫 줄의 실제 번호. 「<별지 제42호>」 「<별지 제29-3호>」 「<별표 5>」
# 가지번호 표기가 두 순서로 섞여 있다 — 「제29-3호」(가지가 호보다 앞) 와
# 「제3호의2」(호가 가지보다 앞). 순서 하나만 가정하면 다른 쪽이 매치 실패해
# 원래 JSON 의 구분·순번으로 잘못 폴백한다(실측: 금투협 시행세칙 별지 제3호의2 →
# [첨부 0005]로 오분류. 원래 구분이 '첨부'인 표지 항목이 있어 폴백값도 그럴듯해 보였다).
_NO_IN_BODY = re.compile(r"[<〈\[［]\s*(별지|별표|서식|첨부|별책)\s*제?\s*"
                         r"(\d+)(?:\s*(?:호\s*의|[-의])\s*(\d+))?\s*호?\s*[>〉\]］]")


def _title_from_body(text, limit=6):
    """별표 본문 첫머리에서 제목을 찾는다.

      <별지 제1호> (개정 2009.5.19., …)
      금융투자회사의 영업보고서        ← 이것
    앞의 「<별지 제1호>」는 번호 표시라 걷어내고, 표 행(|)과 법제처의 「■ …」
    머리 장식은 건너뛴다.

    다만 제목이 표 한 칸(박스)에 들어있는 문서가 있다 — 「| 펀드 판매회사 변경제한
    요청서 |」처럼 파이프가 정확히 2개면 여러 칸짜리 데이터 행이 아니라 제목을 감싼
    단일 셀이다(데이터 행은 칸이 여러 개라 파이프가 4개 이상). 그 경우 안의 글자만
    꺼내 후보로 본다. 이걸 놓치면 다음 줄의 서식 상용구(예: 「(발신일: 년 월 일)」)가
    제목으로 잘못 뽑힌다.
    """
    for raw in text.split("\n")[:limit + 2]:
        s = raw.strip()
        # "[이미지 N개 …]"·"이미지001 …" 는 file_text._image_lines() 가 붙이는
        # 이미지 목록 안내문이지 내용이 아니다. 그림만 있고 글자 제목이 아예 없는
        # 별표(실측: 금투협 [별지 0047의1])에서 이게 "제목"으로 잘못 뽑혔다.
        if not s or s.startswith("■") or re.match(r"^\[이미지\s*\d+개|^이미지\d+\s", s):
            continue
        if s.startswith("|"):
            if s.count("|") == 2 and s.endswith("|"):
                s = s.strip("|").strip()
                if not s:
                    continue
            else:
                continue
        s = _HIST.sub("", _ANG.sub("", s)).strip()
        if not s or _BLANK_DATE.match(s):
            continue
        m = _MARK.match(s)
        if m:
            s = _HIST.sub("", s[m.end():].strip())
            if not s or _BLANK_DATE.match(s):
                continue
        if re.search(r"[가-힣]", s) and 2 <= len(s) <= 60:
            return s
        if len(s) > 60:
            # 표 한 칸에 제목과 본문 전체가 줄바꿈 없이 붙어버린 경우가 있다(실측:
            # 금투협 [별지 0009] "집합투자기구 자산운용보고서   1. 자산운용보고서
            # 표준서식…" 19,494자 — 셀 하나에 규정 원문 전체가 들어있었다). 제목과
            # 본문 사이에 공백이 2칸 이상 벌어져 있는 경우가 많아 그 경계에서 잘라
            # 앞부분만 다시 후보로 본다.
            head = re.split(r"\s{2,}", s, maxsplit=1)[0].strip()
            if re.search(r"[가-힣]", head) and 2 <= len(head) <= 60:
                return head
    return ""


# 「Ⅰ. 목적」·「Ⅴ.금융상품…」 — 로마숫자 목차. 뒤에 마침표나 글자가 이어져야
# 한다(본문 중간의 낱개 로마숫자를 머리로 잡지 않도록).
_OUTLINE_KEY = re.compile(r"\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.．]?(?=\s*\S)")


def _article_key(a):
    """개정 감지가 쓰는 키와 같은 형식. 가지번호까지 포함해야 제80조와 제80조의2가 갈린다."""
    no = _s(a.get("조문번호")).strip()
    br = _s(a.get("조문가지번호")).strip().lstrip("0")
    if not no:
        # 번호 필드가 없는 소스가 둘 있다. 행정규칙은 본문 첫머리에, 금투협은
        # 조제목에 「제2-38조(투자광고)」 형태로 들어 있다. 둘 다 훑는다.
        for src in (a.get("조문내용"), a.get("조제목"), a.get("조내용")):
            m = re.match(r"\s*(제\s*\d+(?:-\d+)?조(?:의\s*\d+)?)", _s(src))
            if m:
                return m.group(1).replace(" ", "")
        # **조문이 아예 없는 문서가 있다.** 심사지침·모범규준은 「Ⅰ. 목적」처럼
        # 로마숫자 목차로 짜여 있어 여기서 빈 키가 나가고, 그러면 근거가
        # 「심사지침 Ⅴ. 1. 가」인 규칙을 어느 청크에도 이어 붙일 수 없다
        # (실측: gold 19건이 이 이유로 정답 없음 처리됐다). 목차 기호를 키로 쓴다.
        for src in (a.get("조문내용"), a.get("조제목"), a.get("조내용")):
            m = _OUTLINE_KEY.match(_s(src))
            if m:
                return m.group(1).replace(" ", "")
        return ""
    return f"제{no}조" + (f"의{br}" if br and br != "0" else "")


# 통짜 본문(여신협·은행연)을 나눌 때 쓰는 헤더 패턴. 줄 맨 앞에 오는 것만 헤더로
# 본다 — 본문 중간의 "…[별표1] 참고" 같은 인용을 헤더로 잡으면 안 된다.
_H_ART = re.compile(r"^(제\s*\d+(?:-\d+)?조(?:의\s*\d+)?)\s*(?:\(([^)]{0,60})\))?")
_H_ADD = re.compile(r"^부\s*칙\s*[(（<]?\s*([^)）>\n]{0,40})")
_H_TBL = re.compile(r"^[\[<]\s*(?:[^\]>]{0,20}?)(별표|별지|서식)\s*(\d*)\s*[\]>]\s*(.{0,60})")


def _split_body(text):
    """통짜 본문 → [(유형, 키, 제목, 텍스트)].

    본칙 → 부칙 → 별표 순으로 이어 붙은 한 덩어리라 그냥 조문 헤더만 찾으면
    **마지막 조문이 뒤의 별표를 통째로 삼킨다**(실측: 여신협 세부지침 제1조가
    31,757자). 세 종류 헤더를 모두 잡아 구간을 나눈다.

    부칙 안의 제1조(시행일)는 본칙 제1조와 키가 겹치므로 부칙 표기를 앞에 붙인다.
    """
    marks = []          # (위치, 유형, 키, 제목)
    for line_m in re.finditer(r"^.*$", text, re.M):
        line = line_m.group(0).strip()
        if not line:
            continue
        m = _H_TBL.match(line)
        if m:
            key = f"[{m.group(1)} {m.group(2)}]" if m.group(2) else f"[{m.group(1)}]"
            marks.append((line_m.start(), "별표", key, m.group(3).strip()))
            continue
        m = _H_ADD.match(line)
        if m:
            tag = re.sub(r"[^\d.]", "", m.group(1))[:10].strip(".")
            marks.append((line_m.start(), "부칙", f"부칙{tag}" if tag else "부칙", ""))
            continue
        m = _H_ART.match(line)
        if m:
            marks.append((line_m.start(), "조문", m.group(1).replace(" ", ""),
                          (m.group(2) or "").strip()))
    if not marks:
        return [("조문", "", "", text.strip())]

    out = []
    pre = text[:marks[0][0]].strip()
    if pre:
        out.append(("조문", "머리말", "", pre))
    addenda = None      # 지금 어느 부칙 구간에 있는지
    last_no = 0         # 그 부칙 안에서 마지막으로 본 조문 번호
    for i, (pos, typ, key, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end].strip()
        if typ == "부칙":
            addenda, last_no = key, 0
        elif typ == "별표":
            addenda = None
        elif addenda:
            # 부칙 조문은 제1조(시행일)부터 번호가 늘어난다. 번호가 되돌아가면
            # 부칙이 끝나고 **다음 문서의 본칙**이 시작된 것이다 — 은행연 파일은
            # 「기준」과 「세칙」 두 문서가 한 파일에 이어 붙어 있어 이게 실제로 나온다.
            n = int(re.sub(r"\D", "", key.split("의")[0]) or 0)
            if n and n <= last_no:
                addenda = None
            else:
                last_no = n
                typ, key = "부칙", f"{addenda}:{key}"
        out.append((typ, key, title, body))
    return out


def sections_of(name, kind):
    """규정 하나 → [{reg, kind, type, key, title, text}]"""
    rec = _record(name)
    if not rec:
        return []
    out = []

    def add(typ, key, title, text):
        text = _s(text).strip()
        if text:
            out.append({"reg": name, "kind": kind, "type": typ,
                        "key": key, "title": title, "text": text})

    if "조문" in rec:
        for a in rec.get("조문") or []:
            # 행정규칙에는 "제1편 총칙" 같은 편·장 구분줄이 조문 자리에 섞여 온다.
            # 내용이 제목과 같으면 구분줄이므로 청크로 만들지 않는다.
            body = _article_text(a)
            if a.get("구분") and body == _s(a.get("구분")).strip():
                continue
            # 조제목은 금투협 필드명. 「제2-38조(투자광고)」처럼 번호가 함께 들어
            # 있으므로 괄호 안만 제목으로 남긴다(키와 중복되지 않게).
            title = _s(a.get("조문제목")).strip()
            if not title:
                m = re.match(r"\s*제\s*\d+(?:-\d+)?조(?:의\s*\d+)?\s*\(([^)]*)\)",
                             _s(a.get("조제목")))
                title = m.group(1).strip() if m else _s(a.get("조제목")).strip()
            add("조문", _article_key(a), title, body)
        for b in rec.get("부칙") or []:
            no = _s(b.get("공포번호")).strip().splitlines()[0] if _s(b.get("공포번호")).strip() else ""
            add("부칙", f"부칙제{no}호" if no else "부칙", "", b.get("내용"))
        for i, t in enumerate(rec.get("별표") or [], 1):
            body = _s(t.get("내용"))
            # 금투협은 제목 필드를 비워 보내지만 본문 첫머리에 제목이 있다.
            if not _s(t.get("제목")).strip():
                t = {**t, "제목": _title_from_body(body)}
            kind_, no, br = _s(t.get("구분")) or "별표", _s(t.get("별표번호")).strip(), \
                _s(t.get("별표가지번호")).strip().lstrip("0")
            if not no:
                # 금투협은 별표번호를 안 준다. 배열 순번으로 채우면 **가지번호와
                # 첨부가 순번을 먹어 실제 번호와 어긋난다** — 배열 55번째가
                # 실제로는 「별지 제42호」다(가지번호 제29-3호·제40-1호 등으로 13칸 밀림).
                # 본문 첫 줄의 「<별지 제42호>」에서 진짜 번호를 읽는다.
                m = _NO_IN_BODY.match(body.lstrip())
                if m:
                    kind_, no, br = m.group(1), m.group(2), (m.group(3) or "")
                else:
                    no = f"{i:04d}"
            # 번호가 없는 별표(0)는 수집 TXT 도 「[별표]」로 쓴다 — 키를 맞춘다.
            if no.isdigit():
                key = f"[{kind_} {int(no):04d}" if int(no) else f"[{kind_}"
            else:
                key = f"[{kind_} {no}"
            key += (f"의{br}" if br else "") + "]"
            add("별표", key, _s(t.get("제목")).strip(), body)
    else:
        # 여신협·은행연: 첨부가 곧 원문이라 통짜 문자열 하나로 저장돼 있다
        for typ, key, title, text in _split_body(_s(rec.get("본문"))):
            add(typ, key, title, text)

    _check_loss(name, kind, rec, out)
    return out


# 원본 대비 몇 %까지 사라져도 넘어갈지. 삭제된 조문·빈 별표 때문에 조금은 준다.
_LOSS_LIMIT = 0.10


def _check_loss(name, kind, rec, out):
    """원본 항목 수와 만들어진 항목 수를 대조한다.

    **조용한 유실이 이 파일의 주된 사고 유형이다.** add() 는 본문이 비면 그냥 안
    넣는데, 소스마다 필드명이 달라(법제처 `조문내용` vs 금투협 `조내용`) 이름 하나만
    어긋나도 전부 빈 문자열이 되어 통째로 사라진다. 에러도 경고도 안 난다.

    실측: 금투협 두 규정의 조문 386개가 이렇게 사라져 있었다. 별표·부칙은 정상이라
    규정 단위로 보면 멀쩡해 보였고, quality_check 도 자동 검사도 못 잡았다. 사람이
    조문지도와 대조하고 나서야 드러났다.

    그래서 **내용이 아니라 개수를 본다.** 파싱이 어떻게 어긋나든 개수는 줄어든다.
    """
    if "조문" not in rec:
        return                      # 통짜 본문 소스는 원본 개수 개념이 없다
    got = collections.Counter(x["type"] for x in out)
    for field, typ in (("조문", "조문"), ("부칙", "부칙"), ("별표", "별표")):
        items = rec.get(field) or []
        if field == "조문":
            # 「제1장 총칙」 같은 장·절 구분줄이 조문 배열에 섞여 온다(실측: 은행업
            # 감독규정 177개 중 29개). 일부러 빼는 것이므로 분모에서도 뺀다 —
            # 안 그러면 정상인데도 16% 유실로 잡혀 경보가 늑대소년이 된다.
            items = [a for a in items
                     if not (a.get("구분")
                             and _article_text(a) == _s(a.get("구분")).strip())]
        want = len(items)
        if not want:
            continue
        have = got[typ]
        if have < want * (1 - _LOSS_LIMIT):
            raise ValueError(
                f"[{name}] {typ} 유실 의심 — 원본 {want}개 → {have}개 "
                f"({(1-have/want)*100:.0f}% 사라짐). 소스({kind})의 필드명이 "
                f"코드와 맞는지 확인하세요.")


def all_sections(only=None):
    out = []
    for t in targets():
        if only and only not in t["name"]:
            continue
        out.extend(sections_of(t["name"], t["kind"]))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    secs = all_sections(sys.argv[1] if sys.argv[1:] else None)
    by = {}
    for s in secs:
        by[s["type"]] = by.get(s["type"], 0) + 1
    print(f"항목 {len(secs):,}개 — " + " · ".join(f"{k} {v:,}" for k, v in by.items()))
    for s in secs[:3]:
        print(f"\n[{s['reg']}] {s['type']} {s['key']} {s['title']}")
        print(s["text"][:200].replace("\n", " ⏎ "))
