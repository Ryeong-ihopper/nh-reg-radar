# -*- coding: utf-8 -*-
"""
새로 수집한 내용이 기존보다 급감하면 저장을 막는다.

실측 사고: 금투협 「금융투자회사의 영업 및 업무에 관한 규정」이 개정되면서
사이트의 첨부 목록이 50개 → 0개가 됐다(협회가 서식을 아직 안 올렸거나 링크
방식이 바뀐 것으로 보임). "새 버전이 나왔다"는 이유만으로 그대로 받으면,
멀쩡히 갖고 있던 첨부 50개가 빈 것으로 조용히 덮어써진다 — 개정 감지가
"버전이 바뀌었다"만 보고 "내용이 말이 되는가"는 안 보기 때문이다.

이 파일은 저장 여부를 판단하는 게이트 하나만 한다. 각 스크레이퍼는
다운로드를 실제로 하기 **전에**(이미 받아버리면 늦다) 이 게이트를 거치고,
막히면 기존 output/*.json·*.txt 를 그대로 두고 결과를 _quarantine/ 에만 남긴다.
"""
import os
import json
import datetime


class CollapseBlocked(Exception):
    """급감 감지로 저장이 막혔을 때 스크레이퍼가 던진다.

    그냥 None 을 반환하면 호출부(check_updates.py)가 "검색 안 됨"·"이름 못 찾음"
    같은 다른 실패 사유와 구분하지 못해, 상태 파일을 그대로 진행시키거나 그냥
    조용히 넘어갈 수 있다(실측: 처음 구현에서 실제로 이렇게 새서, 다음 실행부터
    "이미 최신"으로 오판하고 다시는 재시도하지 않을 뻔했다). 예외로 던져서
    호출부가 반드시 인지하고 상태 갱신을 건너뛰도록 강제한다.
    """
    def __init__(self, name, reason):
        self.name = name
        self.reason = reason
        super().__init__(f"{name}: {reason}")


def _safe(name):
    for c in '\\/:*?"<>|':
        name = name.replace(c, "_")
    return name.strip()


def load_old_count(out_dir, name, field):
    """기존 저장 파일에서 비교 기준 수량을 읽는다.
    field 가 배열이면 길이, 문자열이면 글자수. 파일이 없으면 None(비교 안 함 — 최초 수집)."""
    p = os.path.join(out_dir, _safe(name) + ".json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return None
    v = old.get(field)
    if isinstance(v, (list, str)):
        return len(v)
    return None


def is_collapse(old_count, new_count, ratio=0.5, floor=3):
    """기존 대비 급감했는지 판단.

    - old_count 가 None(최초 수집) 이거나 floor 이하로 원래 적었던 경우는
      급감으로 보지 않는다 — 별표가 원래 2~3개뿐인 규정은 1개만 줄어도
      비율로는 급감처럼 보인다.
    - 0 이 되는 경우는 비율과 무관하게 항상 막는다. 완전히 사라지는 것은
      "이번에 하나도 안 바뀌었다"와 구분이 안 되므로 절대 정상일 수 없다.
    - 그 외에는 기존 대비 ratio 미만(기본 절반 미만)이면 막는다.
    """
    if old_count is None or old_count <= floor:
        return False
    if new_count == 0:
        return True
    return new_count < old_count * ratio


def quarantine(out_dir, name, record, text, reason, verbose=True):
    """저장을 보류하고 검토용 사본만 남긴다. 기존 output/*.json·*.txt 는 손대지 않는다."""
    qdir = os.path.join(out_dir, "_quarantine")
    os.makedirs(qdir, exist_ok=True)
    base = _safe(name)
    payload = {
        "감지시각": datetime.datetime.now().isoformat(timespec="seconds"),
        "사유": reason,
        "레코드": record,
    }
    with open(os.path.join(qdir, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if text is not None:
        with open(os.path.join(qdir, base + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
    if verbose:
        print(f"  ⚠ 저장 보류: {reason}")
        print(f"     기존 output/{base}.json 은 그대로 두고, "
              f"output/_quarantine/{base}.json 에 검토용으로만 남김")


def check_and_maybe_block(out_dir, name, field, new_count, record, text, verbose=True):
    """대표 진입점. (허용여부, 사유) 반환 — 막혔으면 quarantine 까지 이 함수가 처리한다.
    호출부는 반환값이 False 면 그대로 저장을 건너뛰고 return 하면 된다."""
    old_count = load_old_count(out_dir, name, field)
    if not is_collapse(old_count, new_count):
        return True, None
    reason = f"{field} {old_count}개 → {new_count}개로 급감"
    quarantine(out_dir, name, record, text, reason, verbose)
    return False, reason
