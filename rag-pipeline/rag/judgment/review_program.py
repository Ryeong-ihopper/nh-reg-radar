"""Source-bound review programs shared by compilation and operational execution."""
from __future__ import annotations

import calendar
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from rag.judgment.bonus_evidence import bonus_operands

VERSION = "review-program-v1"
KINDS = {"PRESENCE", "SEMANTIC", "PROHIBITION", "CONDITIONAL", "ALTERNATIVE",
         "NUMERIC_DATE", "VISUAL", "EXTERNAL", "REVIEW_REQUEST"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def execution_digest(plan):
    return digest({key: plan[key] for key in ('source', 'applicability_inputs',
                   'applicability_logic', 'obligations', 'obligation_logic')})


def apply_programs(document, policies):
    """Apply reviewed source-bound edits, never advertisement-specific branches."""
    result = copy.deepcopy(document)
    policies_by_id = {p["plan_id"]: p for p in policies["plans"]}
    templates = [p for p in result["plans"] if p["source"]["source_kind"] == "TEMPLATE"]
    if set(policies_by_id) != {p["plan_id"] for p in templates}:
        raise ValueError("review programs must cover exactly the canonical templates")
    for plan in templates:
        policy = policies_by_id[plan["plan_id"]]
        if plan["source_sha256"] != policy["base_source_sha256"]:
            raise ValueError(f"{plan['plan_id']}: source revision needs program review")
        if policy.get("source_revision"):
            plan["source"].update(copy.deepcopy(policy["source_revision"]))
            plan["source_sha256"] = digest(plan["source"])
        for key in ("applicability_inputs", "applicability_logic", "obligations", "obligation_logic"):
            if key in policy:
                plan[key] = copy.deepcopy(policy[key])
        program = copy.deepcopy(policy["program"])
        if not program["kinds"] or set(program["kinds"]) - KINDS:
            raise ValueError("unknown review program kind")
        if program["mode"] == "REVIEW_ONLY":
            if plan["obligations"] or program["allowed_outcomes"] != ["UNDETERMINED"]:
                raise ValueError("review-only item must not have artificial obligations")
        program.update(schema_version=VERSION, source_sha256=plan["source_sha256"])
        program["program_sha256"] = digest({"policy": policy, "source": plan["source_sha256"]})
        program["execution_sha256"] = execution_digest(plan)
        plan["review_program"] = program
        if any(a['owners']['human'] for a in plan['obligations']) and any(a['owners']['llm'] for a in plan['obligations']):
            plan['prompt_family'] = 'HYBRID_VISUAL'
        plan["complexity"] = len(plan["applicability_inputs"]) + sum(
            1 + int(a["owners"].get("human", False)) + int(a["owners"].get("external_input", False))
            for a in plan["obligations"])
    result["counts"]["obligation_atoms"] = sum(len(p["obligations"]) for p in result["plans"])
    result["counts"]["application_inputs"] = sum(len(p["applicability_inputs"]) for p in result["plans"])
    result['counts']['families'] = dict(Counter(p['prompt_family'] for p in result['plans']))
    result["review_program_source_binding"] = {
        "base_binding": document["source_binding_sha256"], "policies_sha256": digest(policies)}
    result["source_binding_sha256"] = digest(result["review_program_source_binding"])
    return result


def program_trace(contract, checks, conditions, verdict):
    program = contract.get("review_program") or {}
    if not program:
        return None
    return {"executor": VERSION, "program_sha256": program["program_sha256"],
            "source_sha256": program["source_sha256"], "kinds": program["kinds"],
            "decision": contract["obligation_logic"], "verdict": verdict,
            "facts": [{"ref": c.get("condition_ref"), "status": c.get("status")}
                      for c in conditions or []],
            "checks": [{"ref": c.get("obligation_ref"), "status": c.get("status"),
                        "line_refs": c.get("evidence_line_refs") or []} for c in checks or []]}


def refresh_program_trace(contract, result, stage):
    if not contract.get('review_program'):
        return
    updated = program_trace(contract, result.get('requirement_checks'),
                            result.get('condition_checks'), result.get('verdict'))
    updated['stage'] = stage
    updated['applicability'] = result.get('applicability')
    previous = result.get('review_program_trace')
    if previous and previous != updated:
        result.setdefault('review_program_history', []).append(previous)
    result['review_program_trace'] = updated


def date_check(adapter, check, payload, item_id):
    """Compare a uniquely cited basis date, never a model-supplied calculation."""
    if adapter.get("kind") != "BASIS_DATE_WITHIN":
        return None
    unknown = {"status": "UNDETERMINED", "finding_basis": "UNKNOWN",
               "evidence_ids": [], "evidence_line_refs": [],
               "reason": "금리 기준일의 단일 원문 근거와 심의일을 확인해야 합니다."}
    try:
        reviewed = date.fromisoformat((payload.get("review_context") or {})["review_date"])
    except (KeyError, TypeError, ValueError):
        return unknown
    allowed = set((payload.get("evidence_scope", {}).get(item_id) or {}).get("evidence_ids") or [])
    refs = set(check.get("evidence_line_refs") or [])
    observed = []
    cited_rates = set()
    for doc in payload.get("documents") or []:
        if doc.get("evidence_id") not in allowed:
            continue
        for ref, text in (doc.get("line_texts") or {}).items():
            if ref not in refs or ref not in (doc.get("line_refs") or []):
                continue
            roles = re.findall(r'(?:기본|우대|최저|최고)금리', re.sub(r'\s+', '', text))
            if '%' in text:
                cited_rates.update(roles)
            if '기준' not in text:
                continue
            for match in re.finditer(r"(?<!\d)(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})(?:일)?", text):
                try:
                    observed.append((date(*map(int, match.groups())), doc["evidence_id"], ref, text))
                except ValueError:
                    return unknown
    # Retrieval chunks may overlap, but two distinct original lines are not
    # interchangeable operands merely because they print the same date.
    observed = list({(row[2], row[0], row[3]): row for row in observed}.values())
    # A line with competing dates, or a detached date among several rates,
    # has no authenticated rate/date pairing. Never infer it from adjacency.
    def roles_for(row):
        return re.findall(r'(?:기본|우대|최저|최고)금리', re.sub(r'\s+', '', row[3]))
    paired = all(len(roles_for(row)) == 1 and '%' in row[3] for row in observed)
    dated_rates = {role for row in observed for role in roles_for(row)}
    if (not observed or len({row[2] for row in observed}) != len(observed)
            or (len(observed) > 1 and not paired)
            or (len(cited_rates) > 1 and (not paired or cited_rates != dated_rates))):
        unknown['reason'] = '금리별 기준일과 원문 줄의 연결을 하나로 확정할 수 없습니다. 기본금리·우대금리 등 서로 다른 금리의 날짜는 각각 확인해야 합니다.'
        unknown['evidence_ids'] = list(dict.fromkeys(row[1] for row in observed))
        unknown['evidence_line_refs'] = list(dict.fromkeys(row[2] for row in observed))
        return unknown
    if adapter["unit"] == "CALENDAR_MONTH":
        month = reviewed.month - 1 or 12
        year = reviewed.year - (reviewed.month == 1)
        earliest = date(year, month, min(reviewed.day, calendar.monthrange(year, month)[1]))
    elif adapter["unit"] == "DAYS":
        earliest = reviewed - timedelta(days=int(adapter["amount"]))
    else:
        raise ValueError("unsupported date comparison unit")
    satisfied = all(earliest <= row[0] <= reviewed for row in observed)
    return {"status": "SATISFIED" if satisfied else "VIOLATED", "finding_basis": "OBSERVED",
            "evidence_ids": list(dict.fromkeys(row[1] for row in observed)),
            "evidence_line_refs": [row[2] for row in observed],
            "reason": '\n'.join(
                f'기준일 근거: "{text}". 심의 기준일 {reviewed.isoformat()}, 허용 기간 {earliest.isoformat()}~{reviewed.isoformat()} 대비 ' +
                ('기간을 충족합니다.' if earliest <= value <= reviewed else '기간을 벗어납니다.')
                for value, _, _, text in observed)}


def computed_check(adapter, check, payload, item_id):
    if adapter.get('kind') == 'LOAN_RATE_ENDPOINT_EQUALITY':
        from rag.judgment.loan_rate_evidence import endpoint_check
        return endpoint_check(adapter, check, payload, item_id)
    if adapter.get('kind') == 'SOURCE_SCOPED_BASIS_DATE_EQUALITY':
        from rag.judgment.basis_date_evidence import date_equality_check
        return date_equality_check(adapter, check, payload, item_id)
    if adapter.get('kind') == 'LOAN_AMOUNT_CAP_WITHIN':
        from rag.judgment.loan_amount_evidence import amount_check
        return amount_check(adapter, check, payload, item_id)
    if adapter.get('kind') == 'ADVERTISED_ARITHMETIC_CONSISTENCY':
        # The separately gated whole-item explicit arithmetic executor owns it.
        return None
    if adapter.get("kind") != "BONUS_SUM_BOUND":
        if adapter.get('kind') == 'BASIS_DATE_WITHIN' or not adapter.get('kind'):
            return date_check(adapter, check, payload, item_id)
        return {'status': 'UNDETERMINED', 'finding_basis': 'UNKNOWN', 'evidence_ids': [],
                'evidence_line_refs': [], 'reason': '원문이 지정한 결정론 비교의 지원 여부를 확인해야 합니다.'}
    unresolved = {"status": "UNDETERMINED", "finding_basis": "UNKNOWN", "evidence_ids": [],
                  "evidence_line_refs": [], "reason": "같은 광고·상품·개정본에서 전체 판독이 완료된 최대 우대금리와 조건별 금리·개수·동일 연 단위·줄 인용의 검증된 근거가 필요합니다."}
    operands = bonus_operands(payload, item_id, check.get('evidence_line_refs') or [])
    if operands is None:
        return unresolved
    satisfied = operands['maximum'] <= operands['sum']
    quotes = ' / '.join('"' + line + '"' for line in operands['quotes'].splitlines())
    return {'status': 'SATISFIED' if satisfied else 'VIOLATED', 'finding_basis': 'OBSERVED',
            'evidence_ids': operands['evidence_ids'], 'evidence_line_refs': operands['evidence_line_refs'],
            'reason': '비교 근거: ' + quotes + '. 전체 조건별 연 우대금리 합과 최대 우대금리의 관계가 ' +
                      ('충족됩니다.' if satisfied else '충족되지 않습니다.')}



def load_policies(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != VERSION:
        raise ValueError("unsupported review program policy")
    return value


def verified_calculated_values(contract, checks, payload, item_id):
    """Authenticate derived values by recomputation, not a model-supplied trace."""
    authored = {o['obligation_id']: o for o in contract.get('obligation_checks') or []}
    values = []
    for check in checks or []:
        if not isinstance(check, dict):
            continue
        adapter = (authored.get(check.get('obligation_ref')) or {}).get('deterministic_adapter') or {}
        if adapter.get('kind') != 'LOAN_RATE_ENDPOINT_EQUALITY':
            continue
        computed = computed_check(adapter, check, payload, item_id)
        trace = computed.get('calculation_trace') or {}
        if (computed.get('finding_basis') == 'OBSERVED'
                and computed.get('status') in {'SATISFIED', 'VIOLATED'}
                and all(check.get(key) == computed.get(key) for key in
                        ('status', 'finding_basis', 'evidence_ids', 'evidence_line_refs', 'calculation_trace'))
                and trace.get('calculated_endpoint') is not None):
            values.append(trace['calculated_endpoint'])
    return values
