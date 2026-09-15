"""Operational applicability screening; receives only v2 and advertisement evidence.

No case IDs, answer keys, or per-regulation overrides belong here. A negative
decision needs cited advertisement evidence. Uncertain or invalid responses
never silently remove a rule.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


SYSTEM = """금융광고 운영 적용성 검사다. 제공된 광고와 규제목록 v2만 사용한다.
충족/위반은 아직 판정하지 않고, 해당 광고에 검사할 규칙인지 결정한다.
각 규칙마다 item_id, applicability, input_mode, evidence_ids, reason을 반환한다.
applicability: APPLICABLE / NOT_APPLICABLE / UNDETERMINED.
input_mode: TEXT / PARTIAL / EXTERNAL.
TEXT: 해당 규칙의 실제 판정기준 전체를 제공 텍스트만으로 검사 가능.
PARTIAL: 텍스트 요건은 검사 가능하지만 위치/대비/랜딩/상품정본 등의 요건도 남음.
EXTERNAL: 현재 텍스트로 확인할 구성요소가 전혀 없고 외부자료가 필수.

상품군=전체는 모든 조건까지 무조건 적용된다는 뜻이 아니다. 점검문구, 판정기준,
근거규칙요약, 비고에 적힌 매체/광고형태/기관/절차/상품의 선행조건을 확인한다.
직접 광고와 추천인 대가성 후기, 은행 내부심의와 다른 협회의 번호체계,
가입 광고와 기존회원 안내, 광고문과 링크된 앱/웹 화면은 서로 구분한다.
자료에 없는 기관 제한을 출처 이름만으로 만들어내지는 말라.
광고 본문에 매체가 명시되어 있으면 그 근거를 사용한다. routing의 null은
본문에 있는 정보까지 없다는 뜻이 아니다. 접수값과 본문이 충돌하면 UNDETERMINED.
필수 문구가 없다는 이유로 표시의무를 미해당으로 제외하지 말라.
AI 제작 여부, 실제 상품 계산방식, 외부 운영 사실을 문구 부재만으로 부정하지 말라.
전체 광고가 제공되었고 특정 추천/공동/비교/추첨 등의 광고형태가 없으면 그 조건부
규칙은 미해당으로 분리할 수 있다. 일반 명확성/허위/조건 은폐 검사는 유지한다.
입력요건 열은 참고하되 실제 검사항목을 분해한다. 문구 존재/수치/줄 구분을
좌표 검사와 혼동하지 말고, 실제 위치/크기/색상 판단에 좌표가 없으면 TEXT로 두지 말라.
PARTIAL은 전체 충족 확정이 불가능하다. EXTERNAL/UNDETERMINED를 미해당으로 숨기지 말라.
적용조건과 의무 이행 여부를 분리한다. 매체 등 선행조건이 맞으면 APPLICABLE이다.
필수문구의 존재/적정성이 불명확해도 적용성은 APPLICABLE이며 본판정에서 검사한다.
예컨대 특정 매체의 표시의무는 그 매체임이 확인되면 적용된다. 표시 내용이 잘못됐거나
없는 것은 적용성 미확정 사유가 아니다. PARTIAL은 input_mode에만 쓸 수 있다.
review_stage, association_pre_review 등 접수자가 확정한 업무 조건이 있으면 규칙의
사전심의·사후보고·협회심의 선행조건에 사용한다. 사전심의 단계라는 이유만으로 아직
발급되지 않은 최종 심의필 번호를 누락 위반으로 만들지 않는다.
검사할 수 없다는 이유나 적용된다고 단정할 근거가 없다는 이유는 미해당 증명이 아니다.
미해당은 v2 선행조건과 광고 사실이 명확히 양립하지 않을 때만 사용한다.
NOT_APPLICABLE은 반드시 documents의 실제 evidence_id를 인용하고 불충족 선행조건을
설명한다. 광고 전문이 제공되지 않았으면 문구 부재만으로 NOT_APPLICABLE은 금지한다.
규칙 ID나 과거 답은 추론 근거가 아니다. 요청 규칙을 전부 한 번씩 반환한다.
출력은 {"results":[{"item_id":"...","applicability":"APPLICABLE",
"input_mode":"TEXT","evidence_ids":["..."],"reason":"..."}]} JSON 하나다.
"""


def validate_screen(value: Any, rules: list[dict], documents: list[dict]) -> list[dict]:
    rows = value.get("results") if isinstance(value, dict) else None
    expected = {r["item_id"] for r in rules}
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("applicability response cardinality mismatch")
    if {r.get("item_id") for r in rows if isinstance(r, dict)} != expected:
        raise ValueError("applicability response IDs mismatch")
    allowed = {d["evidence_id"] for d in documents}
    for row in rows:
        if row.get("applicability") not in {"APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED"}:
            raise ValueError("invalid applicability")
        if row.get("input_mode") not in {"TEXT", "PARTIAL", "EXTERNAL"}:
            raise ValueError("invalid input mode")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or any(ref not in allowed for ref in refs):
            raise ValueError("unknown applicability evidence")
        if row["applicability"] == "NOT_APPLICABLE" and not refs:
            raise ValueError("negative screening without evidence")
        if not str(row.get("reason") or "").strip():
            raise ValueError("missing screening reason")
    return rows


def screen_rules(*, rules: list[dict], documents: list[dict], routing: dict,
                 complete_ad_scan: bool, model: str, post: Callable,
                 workers: int = 2) -> tuple[dict[str, dict], list[dict]]:
    """Constrained output; preserve valid rows and retry only malformed rows."""
    def run(batch: list[dict], retries: int = 2, repair: str = "") -> tuple[list[dict], list[dict]]:
        payload = {"routing": routing, "documents": documents,
                   "complete_ad_scan": complete_ad_scan, "rules": batch}
        schema = {"type": "object", "required": ["results"], "additionalProperties": False,
            "properties": {"results": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["item_id", "applicability", "input_mode", "evidence_ids", "reason"],
                "properties": {
                    "item_id": {"type": "string", "enum": [r["item_id"] for r in batch]},
                    "applicability": {"type": "string", "enum": ["APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED"]},
                    "input_mode": {"type": "string", "enum": ["TEXT", "PARTIAL", "EXTERNAL"]},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                }}}}}
        request = {"model": model, "temperature": 0, "max_tokens": 5000,
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": "operational_applicability", "strict": True, "schema": schema}},
                   "messages": [{"role": "system", "content": SYSTEM + repair},
                                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
        trace = {"request": request}
        try:
            response = post(request)
            trace["response"] = response
            content = response["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
            raw_rows = parsed.get("results", []) if isinstance(parsed, dict) else []
            if not isinstance(raw_rows, list):
                raise ValueError("results must be a list")
            rows, invalid, errors = [], [], []
            for rule in batch:
                matches = [r for r in raw_rows if isinstance(r, dict) and r.get("item_id") == rule["item_id"]]
                try:
                    rows.extend(validate_screen({"results": matches}, [rule], documents))
                except (ValueError, TypeError) as exc:
                    invalid.append(rule)
                    errors.append(f"{rule['item_id']}: {exc}")
            if invalid:
                trace["error"] = "; ".join(errors)
                trace["preserved_item_ids"] = [r["item_id"] for r in rows]
                recovered, retry_traces = repair_invalid(invalid, retries, trace["error"])
                rows.extend(recovered)
            else:
                retry_traces = []
            # An incomplete view never proves a negative advertisement-wide condition.
            if not complete_ad_scan:
                for row in rows:
                    if row["applicability"] == "NOT_APPLICABLE":
                        row.update(applicability="UNDETERMINED",
                                   reason="incomplete advertisement: exclusion not established")
            order = {rule["item_id"]: i for i, rule in enumerate(batch)}
            return sorted(rows, key=lambda r: order[r["item_id"]]), [trace, *retry_traces]
        except Exception as exc:
            trace["error"] = str(exc)
            rows, retry_traces = repair_invalid(batch, retries, str(exc))
            return rows, [trace, *retry_traces]

    def repair_invalid(batch, retries, error):
        if retries:
            size = max(1, len(batch) // 2)
            rows, traces = [], []
            for offset in range(0, len(batch), size):
                repaired, rt = run(batch[offset:offset + size], retries - 1,
                    "\n직전 출력 계약 오류만 수정해 재응답한다. 판정값을 정답에 맞추지 않는다.\n" + error)
                rows.extend(repaired)
                traces.extend(rt)
            return rows, traces
        return [{"item_id": r["item_id"], "applicability": "UNDETERMINED",
                     "input_mode": "EXTERNAL", "evidence_ids": [],
                     "reason": "적용성 응답 검증 실패: 재확인 필요"} for r in batch], []

    batches = [rules[i:i + 10] for i in range(0, len(rules), 10)]
    rows, traces = [], []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for batch_rows, batch_traces in pool.map(run, batches):
            rows.extend(batch_rows)
            traces.extend(batch_traces)
    return {r["item_id"]: r for r in rows}, traces


def split_operational_candidates(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    visible, excluded = [], []
    for candidate in candidates:
        judgment = candidate.get("judgment") or {}
        target = excluded if (judgment.get("applicability") == "NOT_APPLICABLE"
                              and judgment.get("verdict") == "NOT_APPLICABLE") else visible
        target.append(candidate)
    return visible, excluded


def partition_operational_candidates(
    candidates: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Separate formal findings, uncertain supplemental leads, and exclusions."""
    visible, excluded = split_operational_candidates(candidates)
    formal, review = [], []
    for candidate in visible:
        judgment = candidate.get("judgment") or {}
        if (
            candidate.get("discovery_tier") == "SUPPLEMENTAL_V2"
            and judgment.get("applicability") == "UNDETERMINED"
        ):
            review.append(candidate)
        else:
            formal.append(candidate)
    return formal, review, excluded
