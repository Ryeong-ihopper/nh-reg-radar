"""Compile the current deposit/loan/investment review scope into typed plans.

This compiler is intentionally upstream of operational activation.  It replaces
superseded physical source rows, retains every in-scope supplemental candidate,
and gives each source row the same applicability/evidence/decision contract.
It never reads advertisements, answers, predictions, or feedback artifacts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any


SCHEMA_VERSION = "canonical-execution-plans-v2"
SUPERSEDED_TEMPLATE_NUMBERS = {
    *range(1, 29),       # revised named-loan methodology
    *range(58, 73),      # revised demand-deposit methodology
    *range(255, 264),    # revised retirement base methodology
}


SUPPLEMENT_OBLIGATIONS: dict[str, list[tuple[str, str]]] = {
    "C-015": [("중요사항과 의무표시사항이 허용된 동일 화면 범위에 제공되는가", "LLM"),
              ("동일 화면 또는 허용 연결화면의 배치가 확인되는가", "HUMAN")],
    "C-017": [("경제적 대가를 받았다는 사실이 명시되는가", "LLM"),
              ("표시 위치·크기·대비가 쉽게 인식되는가", "HUMAN")],
    "C-018": [("수신거부 또는 수신동의 철회 안내가 있는가", "LLM"),
              ("무료로 의사를 전달할 수 있는 수단임이 표시되는가", "RULE_LLM"),
              ("표시된 수단이 해당 전송 채널의 거부 방법과 연결되는가", "LLM_EXTERNAL")],
    "C-019": [("요구 위치가 확인된 제목·본문 첫머리에 광고 표시가 있는가", "RULE"),
              ("필요한 발송회사명이 표시되는가", "LLM")],
    "C-020": [("전송자 명칭이 표시되는가", "LLM"),
              ("전송자 연락처가 표시되고 단순 발신번호와 구별되는가", "RULE_LLM")],
    "C-025": [("투자광고 LMS·MMS 머리말에 회사명과 광고 표시가 있는가", "RULE_LLM"),
              ("해당 매체에서 생략할 수 없는 투자광고 의무표시가 모두 있는가", "LLM")],
    "C-032": [("무료·면제되는 IRP 수수료 종류와 범위가 표시되는가", "LLM"),
              ("펀드보수 등 별도 비용 가능성이 표시되는가", "LLM")],
    "C-059": [("같은 계산·상품·기간에 대응되는 기준일들이 서로 일치하는가", "RULE_LLM")],
    "C-061": [("통계·도표의 자료 출처가 표시되는가", "LLM"),
              ("통계·도표의 기준일이 표시되는가", "RULE")],
    "C-082": [("미확정 법령·제도 내용의 변경 가능성이 표시되는가", "LLM_EXTERNAL")],
    "C-085": [("복수 투자상품의 공통 위험이 상위 개념으로 정확히 표시되는가", "LLM"),
              ("상품별 고유 위험이 공통문구로 대체되지 않았는가", "LLM"),
              ("필요한 수수료 표시가 있는가", "LLM")],
    "C-090": [("모든 비교대상에 동일 출처의 평가자료를 사용했는가", "RULE_LLM"),
              ("평가자료 출처가 표시되는가", "LLM"),
              ("공표일이 표시되는가", "RULE"),
              ("출처·공표일이 비교수치와 가까이 배치되는가", "HUMAN")],
    "C-091": [("특정 계좌개설 소요시간의 예외가 함께 표시되는가", "LLM"),
              ("예외가 시간 주장과 가까이 배치되는가", "HUMAN")],
    "C-094": [("제도·법령의 시행시점이 표시되는가", "RULE_EXTERNAL"),
              ("시행 전 소비자에게 필요한 중요사항이 표시되는가", "LLM_EXTERNAL")],
    "C-099": [("표시 수익률이 세전인지 세후인지 구분되는가", "RULE_LLM")],
    "C-102": [("제휴서비스 제공조건과 이용요건이 표시되는가", "LLM_EXTERNAL"),
              ("제휴서비스 제한·종료 등 중요 제약이 표시되는가", "LLM_EXTERNAL")],
    "C-125": [("배너·팝업 자체에 생략 불가능한 투자광고 표시사항이 있는가", "LLM"),
              ("랜딩으로 대체 가능한 항목과 불가능한 항목이 구분되는가", "RULE_LLM")],
    "C-132": [("광고가 제시한 최대 비용이 정확히 표시되는가", "RULE_EXTERNAL"),
              ("같은 조건에서 가능한 최소 수익·불리한 결과가 함께 표시되는가", "RULE_EXTERNAL"),
              ("유리·불리한 극값의 글자크기와 배치가 균형적인가", "HUMAN")],
    "C-134": [("수상·인증의 정확한 내용이 표시되는가", "LLM_EXTERNAL"),
              ("수상·인증 시기가 표시되는가", "RULE"),
              ("광고 상품·회사·연도와 근거가 일치하는가", "RULE_EXTERNAL")],
    "D-163": [("같은 기준의 합계·비율·기간 계산이 산술적으로 일치하는가", "RULE")],
    "D-166": [("투자상품을 다른 상품유형으로 오인시키는 명칭·설명이 없는가", "LLM_EXTERNAL")],
    "D-181": [("손실보전 또는 원금·수익 보장을 약속·암시하지 않는가", "LLM_EXTERNAL")],
    "D-182": [("특정금전신탁의 운용상품·유형을 사업자가 미리 정한 것처럼 표시하지 않는가", "LLM_EXTERNAL")],
    "D-188": [("이용후기 광고가 구체적 투자상품·수익률을 언급하지 않는가", "LLM")],
    "D-191": [("절세효과를 상품 운용수익이나 수익률처럼 표현하지 않는가", "LLM_EXTERNAL"),
              ("표시한 세제 기준·한도가 적용시점의 자료와 일치하는가", "RULE_EXTERNAL")],
    "D-201": [("복수상품의 텍스트·수치·위험이 각각 해당 상품에 연결되는가", "LLM"),
              ("복수상품이 시각적으로 구획되어 있는가", "HUMAN")],
    "D-206": [("추천·보증의 경제적 이해관계가 명시되는가", "LLM_EXTERNAL"),
              ("소비자가 쉽게 인식할 위치·형태인가", "HUMAN")],
    "D-228": [("경제적 이해관계 표시가 광고 본문 독자에게 명확한 언어인가", "LLM")],
    "D-229": [("어떤 경제적 대가를 받았는지 구체적으로 표시하는가", "LLM_EXTERNAL")],
    "C-046": [("과거 재무상태·영업실적 표시가 원문 기준에 맞고 오인을 유발하지 않는가", "RULE_LLM_EXTERNAL")],
    "D-184": [("예상·목표 등 미실현 수익률을 실제 성과처럼 표시하지 않는가", "LLM_EXTERNAL")],
    "D-240": [("의무표시·위험고지가 배경색과 뚜렷이 구별되는가", "HUMAN")],
}


# Every retained supplemental rule is decomposed at compile time.  These are
# source-derived applicability facts, not advertisement-specific runtime
# branches.  Product/media facts come from confirmed metadata; content facts
# require an observation from the advertisement.
SUPPLEMENT_APPLICABILITY: dict[str, list[tuple[str, str, str]]] = {
    "C-015": [("온라인 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("유리한 내용을 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-017": [("투자상품 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("이용후기를 광고에 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-018": [("광고성 전자적 전송인가", "RULE", "CONFIRMED_METADATA"),
              ("전달 매체가 원문 적용 매체인가", "RULE", "CONFIRMED_METADATA")],
    "C-019": [("광고성 전자적 전송인가", "RULE", "CONFIRMED_METADATA"),
              ("전송물에 제목과 본문 구조가 있는가", "RULE_LLM", "AD_OR_CONFIRMED_METADATA")],
    "C-020": [("광고성 전자적 전송인가", "RULE", "CONFIRMED_METADATA"),
              ("전달 매체가 전송자 표시 기준 적용 매체인가", "RULE", "CONFIRMED_METADATA")],
    "C-025": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("전달 매체가 LMS 또는 MMS인가", "RULE", "CONFIRMED_METADATA")],
    "C-032": [("IRP 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("수수료 무료 또는 면제 혜택을 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-059": [("서로 대응되는 수치 또는 자료를 함께 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("그 수치 또는 자료의 기준일 비교가 필요한가", "RULE_LLM", "AD_OR_CONFIRMED_METADATA")],
    "C-061": [("통계 수치 또는 조사 결과를 주장 근거로 인용하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-082": [("제도 또는 법령의 도입·변경을 안내하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("시행 전 혜택을 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-085": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("서로 다른 금융투자상품을 함께 설명하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-090": [("비교광고인가", "RULE_LLM", "AD_OR_CONFIRMED_METADATA"),
              ("외부 평가 또는 자료를 비교 근거로 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-091": [("계좌개설 소요시간을 특정하여 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-094": [("제도 또는 법령의 도입·변경을 안내하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("시행 전 혜택을 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-099": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("수익률을 표시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-102": [("제휴 또는 연계 서비스를 혜택으로 제공하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "C-125": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("매체 형식이 배너 또는 팝업인가", "RULE", "CONFIRMED_METADATA")],
    "C-132": [("수익 또는 비용을 표시하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("범위 또는 유리한 극값으로 표시하는가", "RULE_LLM", "AD_OR_CONFIRMED_METADATA")],
    "C-134": [("수상 또는 인증 실적을 광고하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-163": [("합계·비율·기간 계산 결과를 표시하는가", "RULE", "DETERMINISTIC_ADAPTER"),
              ("표시된 값들이 같은 기준으로 연결되는가", "RULE", "DETERMINISTIC_ADAPTER")],
    "D-166": [("투자상품 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("상품 유형을 나타내는 명칭을 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-181": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("손실보전 또는 이익보장 약속 표현이 실제 있는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-182": [("신탁 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("편입 운용상품을 특정해 제시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-188": [("투자상품 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("이용후기를 광고에 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-191": [("투자상품 광고인가", "RULE", "CONFIRMED_METADATA"),
              ("절세효과를 수치 또는 혜택으로 광고하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-201": [("투자광고인가", "RULE", "CONFIRMED_METADATA"),
              ("서로 다른 금융투자상품을 함께 설명하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-206": [("추천 또는 보증 표현을 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("추천·보증 주체와 경제적 대가 또는 이해관계가 확인되는가", "LLM_EXTERNAL", "AD_AND_EXTERNAL")],
    "D-228": [("추천 또는 보증 표현을 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("추천·보증 주체와 경제적 대가 또는 이해관계가 확인되는가", "LLM_EXTERNAL", "AD_AND_EXTERNAL")],
    "D-229": [("추천 또는 보증 표현을 사용하는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("추천·보증 주체와 경제적 대가 또는 이해관계가 확인되는가", "LLM_EXTERNAL", "AD_AND_EXTERNAL")],
    "C-046": [("과거의 재무상태 또는 영업실적을 표시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-184": [("실현되지 않은 예상 또는 목표 수익률을 표시하는가", "LLM", "ADVERTISEMENT_OBSERVATION")],
    "D-240": [("의무표시사항·위험고지·경고문구가 있는가", "LLM", "ADVERTISEMENT_OBSERVATION"),
              ("해당 문구의 배경색 비교 영역을 확인할 수 있는가", "RULE", "CONFIRMED_LAYOUT_INPUT")],
}


# This source guidance applies only when the primary disclosure is absent. It
# is not a prerequisite for checking an already displayed company name.
TEMPLATE_APPLICABILITY_OVERRIDES: dict[str, list[tuple[str, str, str]]] = {
    "MTH-DEPOSIT-DEMAND-R04": [],
}

TEMPLATE_OBLIGATION_OVERRIDES: dict[str, list[tuple[str, str]]] = {
    "MTH-DEPOSIT-DEMAND-R04": [
        ("NH농협은행 명칭이 표시되는가", "LLM"),
    ],
}

TEMPLATE_OBLIGATION_LOGIC_OVERRIDES: dict[str, dict[str, Any]] = {}

DETERMINISTIC_OBLIGATION_ADAPTERS: dict[tuple[str, str], dict[str, str]] = {
    ("D-163", "O1"): {"kind": "ADVERTISED_ARITHMETIC_CONSISTENCY"},
}


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _template_number(rule_id: str) -> int | None:
    match = re.fullmatch(r"TPL-MAP-(\d{3})", rule_id)
    return int(match.group(1)) if match else None


def _source_text(source_fields: dict[str, Any]) -> str:
    return "\n".join(str(value).strip() for value in source_fields.values()
                     if value is not None and str(value).strip())


def _owner_contract(owner: str) -> dict[str, Any]:
    tokens = set(owner.split("_"))
    return {
        "rule": "RULE" in tokens,
        "llm": "LLM" in tokens,
        "external_input": "EXTERNAL" in tokens,
        "human": "HUMAN" in tokens,
    }


def _effective_owner(rule_id: str, obligation_id: str, owner: str) -> str:
    """Do not label an obligation deterministic without an executable adapter.

    RULE_LLM means the model extracts the source-grounded semantic/format fact
    and deterministic validators may constrain it. RULE alone is reserved for
    adapters that can produce the result without model interpretation.
    """
    if owner == "RULE" and (rule_id, obligation_id) not in DETERMINISTIC_OBLIGATION_ADAPTERS:
        return "RULE_LLM"
    return owner


def _gate_text(gate: Any) -> str:
    """Return the authored predicate from both legacy and current gate shapes."""
    if isinstance(gate, dict):
        for key in ("predicate_text", "text", "name"):
            value = str(gate.get(key) or "").strip()
            if value:
                return value
        raise ValueError(f"applicability gate has no predicate text: {gate!r}")
    value = str(gate or "").strip()
    if not value:
        raise ValueError("empty applicability gate")
    return value


def _gate_source_ref(gate: Any) -> str:
    if not isinstance(gate, dict):
        return ""
    return str(gate.get("source_clause_ref") or gate.get("source_field") or "").strip()


def _application_inputs(rule: dict[str, Any]) -> list[dict[str, Any]]:
    def fact(
        fact_id: str, name: str, owner: str, value_type: str
    ) -> dict[str, Any]:
        value = {
            "fact_id": fact_id,
            "name": name,
            "owner": owner,
            "type": value_type,
            "unknown_policy": "UNDETERMINED",
        }
        # These facts ask whether positive content exists in the advertisement.
        # Once the per-rule advertisement scan is complete, an uncited UNKNOWN
        # means the trigger was not observed. External and exemption facts stay
        # open-world because the advertisement alone cannot disprove them.
        if (
            "LLM" in owner
            and "EXTERNAL" not in owner
            and value_type in {"ADVERTISEMENT_OBSERVATION", "AD_OR_CONFIRMED_METADATA"}
        ):
            value["absence_policy"] = "NOT_SATISFIED_IF_COMPLETE_AD_SCAN"
        return value

    values = []
    if rule["source_kind"] == "TEMPLATE":
        values.append(fact("A1", "selected_template", "RULE", "CONFIRMED_METADATA"))
        applicability = rule.get("applicability") or {}
        if rule["rule_id"] in TEMPLATE_APPLICABILITY_OVERRIDES:
            for index, (name, owner, value_type) in enumerate(
                    TEMPLATE_APPLICABILITY_OVERRIDES[rule["rule_id"]], 2):
                values.append(fact(f"A{index}", name, owner, value_type))
            return values
        triggers = list(applicability.get("triggers") or [])
        exceptions = list(applicability.get("exceptions") or [])
        exception_refs = {_gate_source_ref(gate) for gate in exceptions if _gate_source_ref(gate)}
        exception_texts = {_gate_text(gate) for gate in exceptions}
        # The legacy compiler could classify one "생략 가능" clause as both a
        # trigger and an exception.  Keeping both makes ALL(trigger, NOT
        # exception) unsatisfiable.  Such a clause is an exception only.
        triggers = [gate for gate in triggers
                    if not (_gate_source_ref(gate) in exception_refs
                            or _gate_text(gate) in exception_texts)]
        for index, trigger in enumerate(triggers, 2):
            values.append(fact(f"A{index}", _gate_text(trigger), "LLM",
                               "AD_OR_CONFIRMED_METADATA"))
    else:
        clauses = SUPPLEMENT_APPLICABILITY.get(rule["rule_id"])
        if not clauses:
            raise ValueError(f"{rule['rule_id']}: missing supplemental applicability decomposition")
        values.extend(fact(f"A{index}", name, owner, value_type)
                      for index, (name, owner, value_type) in enumerate(clauses, 1))
    for index, exception in enumerate((rule.get("applicability") or {}).get("exceptions") or [], 1):
        values.append({"fact_id": f"E{index}", "name": _gate_text(exception),
                       "owner": "RULE_LLM", "type": "EXEMPTION",
                       "unknown_policy": "UNDETERMINED"})
    return values


def _generic_obligations(rule: dict[str, Any]) -> list[tuple[str, str]]:
    decision = rule.get("decision") or {}
    route = str(decision.get("route") or "LLM_WITH_RULE_GATES")
    source = rule.get("source_fields") or {}
    parts = []
    for label, field in (("점검항목", "label"), ("충족기준", "satisfied"),
                         ("위반기준", "violated"), ("확인필요", "review")):
        value = str(source.get(field) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    text = "\n".join(parts) or _source_text(source)
    example = str(source.get("example") or "").strip()
    criteria = "\n".join(str(source.get(field) or "")
                           for field in ("satisfied", "violated", "review"))
    if example and re.search(r"예시\s*문구와\s*유사(?:한\s*)?(?:의미|문구)", criteria):
        text += (
            "\n의미 기준: 다음 예시의 핵심 의무 전체와 의미상 동등한 구체적 내용이어야 하며, "
            "제목이나 예시의 일부 명사만으로 충족하지 않음 — " + example
        )
    owners = []
    if "RULE" in route:
        owners.append("RULE")
    if "LLM" in route:
        owners.append("LLM")
    if "HUMAN" in route:
        owners.append("HUMAN")
    if not owners:
        owners.append("LLM")
    return [(text, "_".join(owners))]


def _template_obligations(rule: dict[str, Any]) -> list[tuple[str, str]]:
    """Split only source-explicit components of a source-authored checklist row."""
    if rule["rule_id"] in TEMPLATE_OBLIGATION_OVERRIDES:
        return TEMPLATE_OBLIGATION_OVERRIDES[rule["rule_id"]]
    source = rule.get("source_fields") or {}
    label = str(rule.get("label") or source.get("label") or "").replace("\n", " ").strip()
    criteria = "\n".join(str(source.get(field) or "").strip()
                           for field in ("satisfied", "violated", "review")
                           if str(source.get(field) or "").strip())
    full = "\n".join([criteria, str(source.get("example") or "").strip()])
    output: list[tuple[str, str]] = []
    if "심의번호" in label:
        output.extend([
            ("원문이 요구하는 심의주체 명칭이 표시되는가", "RULE_LLM"),
            ("심의필 번호가 요구 형식으로 표시되는가", "RULE"),
            ("유효기간 시작일과 종료일이 표시되는가", "RULE"),
        ])
    elif "예금자보호" in label:
        output.append(("원문이 요구하는 예금자보호 또는 비보호 내용이 표시되는가", "LLM"))
        if "로고" in full:
            output.append(("원문이 요구하는 예금자보호 로고가 원본에 표시되는가", "HUMAN"))
    elif ("설명 받을 권리" in full or "설명받을 권리" in full) and (
            "상품설명서" in full or "투자설명서" in full or "약관" in full):
        output.append(("금융상품에 관해 충분한 설명을 받을 권리가 표시되는가", "LLM"))
        output.append(("가입·투자 전 원문이 지정한 설명서·약관 확인 안내가 표시되는가", "LLM"))
    elif "원금" in full and "손실" in full and "귀속" in full:
        output.append(("투자원금 손실 가능성이 표시되는가", "LLM"))
        output.append(("그 손실이 투자자에게 귀속된다는 사실이 표시되는가", "LLM"))
    elif "금리" in label or "이율" in label:
        output.append((f"{label}의 원문상 금리·이율 내용이 광고 대상과 연결되어 표시되는가", "LLM"))
        if re.search(r"(?:'연'|‘연’|연\s*\(|12개월)", full):
            output.append(("연 기준 또는 원문이 허용한 12개월 기준이 표시되는가", "RULE"))
        if "기준일" in full:
            output.append(("금리·이율의 기준일자가 표시되는가", "RULE"))
        if "세전" in full:
            output.append(("세전 여부가 표시되는가", "RULE"))
        if "적용" in full and ("금액" in full or "한도" in full):
            output.append(("금리 적용금액 또는 한도가 원문 요건대로 표시되는가", "RULE_LLM"))
    else:
        return _generic_obligations(rule)
    return list(dict.fromkeys(output))


def _plan(rule: dict[str, Any]) -> dict[str, Any]:
    obligations = (SUPPLEMENT_OBLIGATIONS.get(rule["rule_id"])
                   or (_template_obligations(rule) if rule["source_kind"] == "TEMPLATE"
                       else _generic_obligations(rule)))
    source_fields = rule.get("source_fields") or {}
    source_example = str(source_fields.get("example") or "").strip()
    source_criterion = "\n".join(
        str(source_fields.get(field) or "").strip()
        for field in ("satisfied", "violated", "review")
        if str(source_fields.get(field) or "").strip()
    )
    atoms = [{
        "obligation_id": f"O{index}",
        "text": text,
        "owners": _owner_contract(_effective_owner(rule["rule_id"], f"O{index}", owner)),
        "evidence": {
            "advertisement_direct_quote_required": "HUMAN" not in owner,
            "absence_requires_complete_scan": True,
            "same_advertisement_product_revision_scope": True,
            "rule_or_example_text_is_advertisement_evidence": False,
        },
        "interpretation_hints": ([{
            "role": "NON_BINDING_SOURCE_EXAMPLE",
            "text": source_example,
            "exact_match_required": False,
            "may_be_cited_as_advertisement_evidence": False,
        }] if source_example else []),
        "retrieval_queries": list(dict.fromkeys(filter(None, [
            text,
            str(rule.get("label") or "").strip(),
            source_criterion,
            source_example,
        ]))),
        **({"deterministic_adapter": DETERMINISTIC_OBLIGATION_ADAPTERS[(rule["rule_id"], f"O{index}")]}
           if (rule["rule_id"], f"O{index}") in DETERMINISTIC_OBLIGATION_ADAPTERS else {}),
    } for index, (text, owner) in enumerate(obligations, 1)]
    logic = TEMPLATE_OBLIGATION_LOGIC_OVERRIDES.get(
        rule["rule_id"], {"all": [{"ref": atom["obligation_id"]} for atom in atoms]}
    )
    application_inputs = _application_inputs(rule)
    family = _family(atoms)
    source = {
        "rule_id": rule["rule_id"], "source_kind": rule["source_kind"],
        "product_template": rule.get("product_template"), "label": rule.get("label"),
        "source_fields": rule.get("source_fields") or {},
        "source_provenance": rule.get("source") or {},
        "legal_basis": rule.get("legal_basis") or {},
    }
    unresolved = [value for value in (rule.get("unresolved") or [])
                  if not (rule["rule_id"] in SUPPLEMENT_OBLIGATIONS
                          and value == "ATOMIC_CLAUSE_APPROVAL_REQUIRED")
                  and not (value == "VISUAL_FACET_REQUIRES_HUMAN"
                           and any(atom["owners"]["human"] for atom in atoms))]
    held_facets = []
    if "SOURCE_SCOPE_TERM_CONFLICT" in unresolved:
        unresolved.remove("SOURCE_SCOPE_TERM_CONFLICT")
        held_facets.append({
            "facet": "line_layout_violation_condition",
            "reason": "SOURCE_SCOPE_TERM_CONFLICT",
            "source_text": str(source_fields.get("violated") or "").strip(),
            "execution": "NOT_COMPILED_UNTIL_SOURCE_OWNER_CLARIFIES_SCOPE_TERM",
            "remaining_text_obligation_active": True,
        })
    return {
        "plan_id": rule["rule_id"], "source": source,
        "source_sha256": _sha(source), "applicability_inputs": application_inputs,
        "applicability_logic": {"all": [
            {"fact": value["fact_id"]} for value in application_inputs if not value["fact_id"].startswith("E")
        ] + [{"not": {"fact": value["fact_id"]}} for value in application_inputs
             if value["fact_id"].startswith("E")]},
        "obligations": atoms, "obligation_logic": logic,
        "atomization": {
            "basis": ("AUTHORED_SUPPLEMENT_COMPONENTS" if rule["rule_id"] in SUPPLEMENT_OBLIGATIONS
                      else "SOURCE_AUTHORED_TEMPLATE_ROW_WITH_EXPLICIT_COMPONENT_SPLITS"),
            "source_row_remains_review_unit": rule["source_kind"] == "TEMPLATE",
            "example_values_are_exact_requirements": False,
        },
        "prompt_family": family, "complexity": _complexity(application_inputs, atoms),
        "unresolved": list(dict.fromkeys(unresolved)),
        "held_facets": held_facets,
        "release_state": "OPERATIONAL_CATALOG_CONNECTED",
    }


def _family(atoms: list[dict[str, Any]]) -> str:
    owners = Counter(key for atom in atoms for key, enabled in atom["owners"].items() if enabled)
    if owners["human"] and not (owners["rule"] or owners["llm"]):
        return "HUMAN_VISUAL"
    if owners["external_input"]:
        return "EXTERNAL_COMPARISON"
    if owners["human"]:
        return "HYBRID_VISUAL"
    if owners["rule"] and owners["llm"]:
        return "HYBRID_FACT_SEMANTIC"
    if owners["rule"]:
        return "DETERMINISTIC_FORMAT_OR_NUMBER"
    return "SEMANTIC_PRESENCE_OR_PROHIBITION"


def _complexity(inputs: list[dict[str, Any]], atoms: list[dict[str, Any]]) -> int:
    return len(inputs) + len(atoms) + sum(
        int(atom["owners"][key]) for atom in atoms for key in ("external_input", "human")
    )


def _reviewed_methodology_basis(
    methodologies: dict[str, Any], methodology_review: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return display-only authority mappings from the reviewed exact row correspondence.

    A corresponding old row supplies citations only. It does not merge the old
    judgment criterion into the revised methodology row. Newly added rows stay
    unmapped unless their own methodology source explicitly names an authority.
    """
    if methodology_review.get("schema_version") != "methodology-execution-review-v1":
        raise ValueError("methodology review is not the reviewed correspondence schema")
    methodology_ids = {str(row.get("rule_id") or "") for row in methodologies.get("rules") or []}
    rows = methodology_review.get("correspondence")
    if not isinstance(rows, list):
        raise ValueError("methodology review correspondence must be a list")
    reviewed_ids = [str(row.get("new_rule_id") or "") for row in rows]
    if len(reviewed_ids) != len(set(reviewed_ids)) or set(reviewed_ids) != methodology_ids:
        raise ValueError("methodology review does not exactly cover the methodology snapshot")

    rules = {str(row["rule_id"]): row for row in methodologies["rules"]}
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        rule_id = str(row["new_rule_id"])
        if row.get("source") != rules[rule_id].get("source"):
            raise ValueError(f"{rule_id}: reviewed source differs from methodology source")
        old = row.get("old_source_fields") or {}
        basis: dict[str, Any] = {}
        statute = str(old.get("근거(법령)") or "").strip()
        association = str(old.get("근거(협회 규정)") or "").strip()
        if statute and statute != "-":
            basis["statute"] = statute
        if association and association != "-":
            basis["association"] = association

        methodology = rules[rule_id]
        if (
            "ASSOCIATION_GUIDANCE" in (methodology.get("source_types") or [])
            and "SOURCE_SCOPE_TERM_CONFLICT" not in (methodology.get("issues") or [])
        ):
            guidance = "은행연합회 지도사항"
            basis["association"] = "\n".join(dict.fromkeys(filter(None, [
                association if association != "-" else "", guidance,
            ])))
        if basis:
            basis.update({
                "display_only_not_new_obligation": True,
                "correspondence_relation": row.get("relation"),
                "mapping_status": old.get("매핑상태"),
                "mapping_confidence": old.get("매칭 신뢰도"),
            })
        output[rule_id] = basis
    return output


def compile_current_scope(
    routing: dict[str, Any],
    methodologies: dict[str, Any],
    methodology_review: dict[str, Any],
) -> dict[str, Any]:
    if routing.get("physical_item_count") != 305:
        raise ValueError("routing snapshot is not the reviewed 305-item source")
    retained = []
    for rule in routing["rules"]:
        number = _template_number(str(rule.get("rule_id") or ""))
        if rule.get("source_kind") == "TEMPLATE" and str(rule.get("product_template") or "").startswith("카드"):
            continue
        if number in SUPERSEDED_TEMPLATE_NUMBERS:
            continue
        retained.append(rule)
    methodology_basis = _reviewed_methodology_basis(methodologies, methodology_review)
    new_rules = []
    for row in methodologies["rules"]:
        new_rules.append({
            "rule_id": row["rule_id"], "source_kind": "TEMPLATE",
            "product_template": row["template_section"], "label": row["label"],
            "source_fields": {
                "label": row["label"], "example": row["display_example"],
                "satisfied": row["outcomes"]["satisfied_when"],
                "violated": row["outcomes"]["violated_when"],
                "violation_guidance": row["outcomes"]["violation_guidance"],
                "review": row["outcomes"]["review_when"],
                "review_guidance": row["outcomes"]["review_guidance"],
            },
            "applicability": row["applicability"],
            "decision": {"route": row["decision_route"]},
            "unresolved": row["issues"],
            "source": row.get("source") or {},
            "legal_basis": methodology_basis[row["rule_id"]],
        })
    candidates = [*retained, *new_rules]
    ids = [row["rule_id"] for row in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate canonical rule id")
    if len(candidates) != 271:
        raise ValueError(f"expected 271 current-scope candidates, found {len(candidates)}")
    supplemental_ids = {row["rule_id"] for row in candidates if row["source_kind"] != "TEMPLATE"}
    if supplemental_ids != set(SUPPLEMENT_APPLICABILITY):
        raise ValueError("supplemental applicability coverage differs from current scope")
    plans = [_plan(rule) for rule in candidates]
    counts = {
        "candidate_source_records": len(plans),
        "template_records": sum(p["source"]["source_kind"] == "TEMPLATE" for p in plans),
        "supplemental_records": sum(p["source"]["source_kind"] != "TEMPLATE" for p in plans),
        "obligation_atoms": sum(len(p["obligations"]) for p in plans),
        "application_inputs": sum(len(p["applicability_inputs"]) for p in plans),
        "plans_with_unresolved": sum(bool(p["unresolved"]) for p in plans),
        "plans_with_held_facets": sum(bool(p["held_facets"]) for p in plans),
        "families": dict(sorted(Counter(p["prompt_family"] for p in plans).items())),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": "DEPOSIT_LOAN_INVESTMENT",
        "policies": {
            "examples_are_advertisement_evidence": False,
            "examples_are_non_binding_retrieval_and_interpretation_hints": True,
            "answers_predictions_feedback_loaded": False,
            "unknown_applicability_is_not_inapplicable": True,
            "aggregation_owner": "CODE",
            "operationally_connected": True,
        },
        "counts": counts,
        "plans": plans,
        "source_binding_sha256": _sha({
            "routing": routing,
            "methodologies": methodologies,
            "methodology_review": methodology_review,
        }),
    }
