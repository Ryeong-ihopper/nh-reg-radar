# -*- coding: utf-8 -*-
"""이름으로 문서를 고를 때 쓰는 공통 규칙.

어댑터마다 "이름이 정확히 일치하는 걸 찾고, 없으면 대충 비슷한 걸" 하는 코드가
따로 있었는데, 그 '대충'이 전부 같은 함정을 밟고 있었다.

    「…광고에 관한 규정」  ⊂  「…광고에 관한 규정 세부지침」
    「…영업 및 업무에 관한 규정」 ⊂ 「…영업 및 업무에 관한 규정 시행세칙」

부분일치로 첫 후보를 집으면 **규정 자리에 시행세칙이 들어온다.** 목록 순서가
바뀌기만 해도 조용히 뒤바뀌고, 수집은 정상 종료되므로 아무도 모른다.

이름 길이로 고르는 것도 안전하지 않다. 원본 이름에 수식어가 붙으면
(「…규정(2026개정본)」) 세부지침 쪽이 더 짧아져 다시 뒤바뀐다.

그래서 **다른 등록 대상의 이름**을 같이 보고 귀속을 가린다.
후보가 더 구체적인(더 긴) 다른 대상 이름도 포함하면 그건 그 대상의 것이다.
"""
import re

_STRIP = re.compile(r"[\s_·ㆍ・.,()\[\]{}<>「」『』/\\-]")


def norm(s):
    return _STRIP.sub("", str(s or ""))


def pick(name, candidates, siblings=(), key=None):
    """후보 중 `name` 에 해당하는 것 하나. 없으면 None.

    name        찾으려는 대상 이름
    candidates  후보 목록(문자열 또는 임의 객체)
    siblings    같은 소스에 등록된 **다른** 대상 이름들
    key         후보에서 비교할 문자열을 꺼내는 함수(기본: 후보 자신)

    1) 정규화해서 완전히 같은 것이 있으면 그것
    2) 없으면 이름을 포함하는 후보 중, **다른 대상에 귀속되지 않는 것**
       (동점이면 군더더기가 적은 것)
    """
    get = key or (lambda x: x)
    k = norm(name)
    if not k:
        return None
    for c in candidates:
        if norm(get(c)) == k:
            return c
    others = [norm(s) for s in siblings]
    others = [o for o in others if len(o) > len(k)]
    hits = []
    for c in candidates:
        nc = norm(get(c))
        if k not in nc:
            continue
        if any(o in nc for o in others):    # 더 구체적인 대상의 문서다
            continue
        hits.append(c)
    return min(hits, key=lambda c: len(norm(get(c)))) if hits else None


def siblings_of(name, kind, targets_path):
    """targets.json 에서 같은 소스의 다른 대상 이름들."""
    import json
    try:
        return [t["name"] for t in json.load(open(targets_path, encoding="utf-8"))
                if t.get("kind") == kind and t["name"] != name]
    except Exception:
        return []
