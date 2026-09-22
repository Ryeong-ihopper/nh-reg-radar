# -*- coding: utf-8 -*-
"""Run advertisement -> rule discovery -> Gemma judgment as one auditable job.

The runner never reads gold, researcher feedback or case-specific mappings.
Unverified routing values may rank candidates but cannot remove a supported
product family or a template T rule.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from rag.retrieval.evidence_bundle import search_terms, supplement_evidence  # noqa: E402
from rag.judgment.manual_review import (  # noqa: E402
    attach_visual_retrieval_evidence,
    deferred_input_reason,
    has_text_decision_facet,
    partition_visual_review_candidates,
    requires_visual_review,
)

import build_silver_requests as judgment_input  # noqa: E402
import hybrid_rule_retrieval as discovery  # noqa: E402
from model_result_io import load_results  # noqa: E402
from rag import build_items as v2_source  # noqa: E402
from rag.contracts.validation import (  # noqa: E402
    DISCOVERY_VERSION,
    FREEZE_VERSION,
    OPERATIONAL_RESULT_VERSION,
    validate_integrated_input,
    validate_operational_result,
    validate_search_collections,
)
from rag.judgment.policy import (  # noqa: E402
    confirmed_template,
    deterministic_facts,
    enforce_review_policy,
    require_confirmed_product_group,
    routing_field,
)
from regulation_v2_catalog import load_template_candidate_rules  # noqa: E402
from rag.judgment.applicability import partition_operational_candidates, screen_rules  # noqa: E402
from rag.judgment.decision_guides import (  # noqa: E402
    attach_decision_guides,
    load_decision_guides,
)
from rag.judgment.condition_contracts import (  # noqa: E402
    VERSION as CONDITION_CONTRACT_VERSION,
    attach_condition_contracts,
    audit_v2_source_items,
    audit_compiled_rules,
)
from rag.judgment.family_prompts import prompt_for_family  # noqa: E402
from rag.judgment.candidate_activation import (  # noqa: E402
    CONTENT_TIER,
    VISUAL_TIER,
    activated_retrieval_rows,
    load_candidate_activation_policy,
)
from rag.judgment.operational_catalog import (  # noqa: E402
    audit_canonical_template_coverage,
    load_operational_catalog,
)
from rag.judgment.operational_selection import (  # noqa: E402
    activate_retrieved,
    confirmed_metadata_facts,
    select_supplemental_plans,
)
from rag.judgment.rule_relations import (  # noqa: E402
    apply_satisfaction_relations,
    expand_relation_dependencies,
)
from dgx_openai_client import post_json  # noqa: E402
from dgx_bge_client import rerank as gpu_rerank  # noqa: E402
from rag.templates.catalog import TemplateCatalog  # noqa: E402
from rag.templates.methodology import methodology_workbooks  # noqa: E402
from rag.templates.coverage import audit_template_coverage  # noqa: E402
from rag.retrieval.context import expand_source_context  # noqa: E402
from rag.retrieval.queries import build_context_queries  # noqa: E402
from rag.retrieval.candidates import (  # noqa: E402
    audit_only_candidates,
    balanced_candidates,
    formal_judgment_candidates,
)
from rag.judgment.reading_quality import needs_reading_review, uncertain_ad_readings  # noqa: E402
from rag.judgment.source_checks import evidence_rows_for_rule  # noqa: E402

# Existing reports/tests import this name; execution itself is provider-neutral.
dgx_rerank = gpu_rerank


OPERATIONAL_SYSTEM = """당신은 NH 금융광고의 운영 심의 판정기다. 입력된 심의 기준만
사용하고, 사례 정답이나 외부 규칙을 만들지 말라.

1. 각 rule은 독립적으로 판정하되 광고의 공통 사실은 일관되게 적용한다.
2. 적용성과 판정을 분리한다. 외부자료나 미확정 메타데이터가 필요하면 UNDETERMINED다.
3. routing은 confirmed|verified|provided인 값만 확정 사실로 쓴다. null을 본문 부재로 간주하지 않는다.
4. documents는 규칙별 근거 창이다. evidence_scope 밖 근거를 쓰지 말라.
5. parser_coverage=PARTIAL 또는 complete_ad_scan=false이면 문구 부재를 확정하지 말라.
   reading_quality의 LOCAL_REGIONS_ONLY 불확실성은 해당 규칙의 evidence_scope에 포함될 때만
   그 규칙에 적용한다. 다른 영역의 판독·라벨 확인 필요를 광고 전체 미완료로 확대하지 말라.
6. 표시의무의 누락은 complete_ad_scan=true일 때만 MISSING이다. 금지 표현이 실제 근거에
   관찰된 경우만 VIOLATED다. 누락 주장을 VIOLATED/OBSERVED로 우회하지 말라.
   전체 광고의 다른 위치에 있는 필수 요소도 확인하고, 일부 인용문에 없다는 이유로 누락이라 하지 말라.
7. PARTIAL 입력의 미확인 구성요소는 UNDETERMINED며 전체 COMPLIANT로 확정하지 않는다.
8. 수치는 실제 입력값·산식·결과를 확인한 때만 판정하고 조건이 비면 UNDETERMINED다.
9. 예시의 숫자·상품명·기호·날짜 표면형식은 완전일치 의무가 아니다. 의미상 동등 표현을 인정한다.
   '또는/택일'은 허용 방식 중 하나면 충족하는 대안이다. 허용 방식 A를 확인하고도 B가 없어서
   위반이라고 하지 말라. '및/모두'의 동시 의무와 구분하고 선택한 방식의 필수 요소만 확인한다.
10. template_basis는 일반 템플릿 원문의 독립 점검항목이다. REQUIRED는 필수, CONDITIONAL은
    기재요령 조건이 확인될 때만 필수다. 법령 근거가 없으면 만들지 말라.
11. deterministic_facts와 파서 시인성 값은 제공된 그대로만 사용하고 재계산·추정하지 않는다.
12. VIOLATION과 UNDETERMINED는 needs_researcher_review=true다.
13. 탭·메뉴·섹션 제목에 나란히 표시된 항목명은 실제 유의사항 문장이 아니다. 메뉴명을
    '한 줄의 복수 유의사항'으로 보아 위반으로 판정하지 말라.
14. deterministic_facts가 심의번호 또는 유효기간 자리표시자 형식의 존재를 확정하면,
    0·O·○·□·X 자리표시자라는 이유만으로 누락·형식 위반으로 판정하지 말라.
15. media_type이 provided/confirmed/verified이면 그 값이 실제 광고 전달 매체다. 본문에 PUSH·문자·알림이
    언급됐다는 이유로 NOTICE·BRANCH_FLYER·MOBILE_BANNER·WEB_BANNER·WEB_PRODUCT_PAGE·EVENT_PAGE를
    PUSH·SMS·ALIMTALK 전송매체로 바꾸어 적용하지 말라.
16. parser_visibility의 line_styles는 파서가 관측한 값만 사용한다. size_basis=declared는 선언 pt,
    size_basis=fontbox는 글꼴칸 실측값이므로 절대 pt 기준으로 서로 바꾸어 판단하지 않는다.
    색상 값만으로 대비를 추정하지 말고 contrast_ratio 같은 측정값이 없으면 대비 판정은 판단불가다.
17. VIOLATED의 evidence는 reason에서 주장하는 위반 사실을 직접 담은 줄이어야 한다.
    full_ad_text에서만 확인한 사실을 documents의 무관한 줄에 연결하지 말고, 직접 근거가
    evidence_scope에 없으면 UNDETERMINED로 판정하라.
18. condition_contract를 의무 판정보다 먼저 검사한다. scope_text의 대상자·상품·상황·매체·절차
    한정은 모두 같은 광고 맥락에서 성립해야 MATCHED다. 예를 들어 넓은 '담당자' 표현만으로
    더 좁은 모집인·특정 영업주체 조건을 충족했다고 추정하지 않는다. 조건이 불명확하면
    의무를 충족·위반으로 확정하지 말고 UNDETERMINED로 둔다.
19. review_context.review_date는 전달된 심의일이다. 서비스에서는 광고 최초 등록일로 고정한다.
광고에 인쇄된 금리 기준일과 구분하고,
    원문 규칙이 심의시점과의 기간 비교를 요구하면 두 날짜를 대조한다. 검토일이 없으면 추정하지 않는다.
20. template_basis.text_facet_only=true이면 읽을 수 있는 텍스트 의무만 판정한다.
    시인성·로고·중첩 구조의 충족 여부는 별도 사람 검토에 남아 있으며 텍스트 판정으로 확정하지 않는다.
21. '조건 성립 시 생략 가능'은 면제 조건이다. 면제를 확인하지 못한 것을 미해당으로 바꾸지 않는다.
    의무가 적용되는 조건과 생략이 허용되는 조건을 구분하고, 미확정이면 UNDETERMINED다.
22. canonical_execution_plan이 있으면 applicability_inputs를 의무보다 먼저 각각 확인하고,
    obligations의 원자 의무를 빠짐없이 requirement_checks에 대응시킨다. RULE 소유 조건과 계산은
    제공된 확정값을 그대로 사용하고, HUMAN 소유 원자는 자동 충족·위반으로 판정하지 않는다.
    전체 판정은 하나의 키워드가 아니라 applicability_logic과 obligation_logic에 맞춰 작성한다.
23. 광고 원문 전체 판독이 완료됐고 긍정형 내용 발동조건(추천·보증, 계산 결과, 후기, 비교,
    수익률 등)을 뒷받침하는 직접 문구가 어디에도 없으면 그 조건은 UNDETERMINED가 아니라
    NOT_MATCHED다. AND 조건 하나가 NOT_MATCHED이면 다른 외부 조건이 미확정이어도 적용성은
    NOT_APPLICABLE이다. 단순 숫자 하나나 주제가 비슷한 문장을 발동 근거로 사용하지 않는다.
"""


# A response which contains more than six rule judgments has only one contract
# retry before the DGX runner splits it.  Starting with eight rules therefore
# creates large, expensive requests that commonly become two or more physical
# calls anyway.  Four keeps the result contract comfortably inside the model's
# structured-output budget, while six remains available for measured tuning.
DEFAULT_RULES_PER_JUDGMENT = 4
MAX_RULES_PER_JUDGMENT = 6
DEFAULT_JUDGMENT_MAX_TOKENS = 4096

ROUTING_MANIFEST_VERSION = "operational-routing-manifest-v1"
ROUTING_OVERRIDE_FIELDS = {
    "product_group",
    "product_subtype",
    "template_id",
    "ad_type",
    "product_name_shown",
    "media_type",
    "review_stage",
    "association_pre_review",
    "external_evidence_available",
}

# The model needs the v2 decision content, but not relational bookkeeping used
# only by retrieval or audit joins.  This projection is derived solely from a
# loaded v2 row; it never introduces a rule, a case mapping, or a new
# interpretation.  Keeping it in one place also makes the prompt contract
# explicit and prevents every JSONL batch from carrying unused fields.
MODEL_RULE_FIELDS = (
    "item_id",
    "source_sheet",
    "category",
    "category_label",
    "product_groups",
    "product_subtype",
    "template_required",
    "title",
    "question",
    "criterion",
    "input_requirement",
    "judgment_type",
    "judgment_mode",
    "required_medium",
    "violation_grade",
    "v2_note",
    "standard_guidance",
    "standard_examples",
    "rule_summaries",
    "basis_details",
    "legal_basis",
    "example_policy",
    "example_text",
    "guide",
    "decision_guides",
    "decision_guide_policy",
    "condition_contract",
    "template_basis",
    "canonical_execution_plan",
)


def model_rule_view(rule: dict[str, Any]) -> dict[str, Any]:
    """Return the template/v2 rule view needed by the judgment model."""
    return {
        field: rule[field]
        for field in MODEL_RULE_FIELDS
        if field in rule and rule[field] not in (None, "", [], {})
    }


def template_scoped_rule(rule: dict[str, Any], template_id: str | None) -> bool:
    """Keep generic rules and exact confirmed-template rules only.

    A blank v2 product_subtype means the rule applies across subtypes.  A
    populated subtype is a v2 applicability condition, so a *confirmed* parser
    template can safely exclude a different subtype.  Inferred templates never
    call this function as a narrowing gate.
    """
    subtype = rule.get("product_subtype")
    return not subtype or not template_id or str(subtype) == str(template_id)


# v2의 템플릿 섹션은 "[T-108] 예금성상품-적립식"처럼 T 코드 접두어를 달고 기록된다.
# 접두어는 표기일 뿐 결합 대상이 아니므로 비교 전에 벗긴다.
_TEMPLATE_CODE_PREFIX = re.compile(r"^\s*\[[^\]]*\]\s*")


def v2_template_sections(rule: dict[str, Any]) -> list[str]:
    """v2 행이 원문에 적어 둔 템플릿 결합 값을 정규화해 돌려준다."""
    raw_sections = rule.get("template_sections")
    if isinstance(raw_sections, (list, tuple, set)):
        values = [str(value) for value in raw_sections]
    else:
        values = re.split(r"[,;|\n]+", str(raw_sections or ""))
    sections = [_TEMPLATE_CODE_PREFIX.sub("", value).strip() for value in values]
    return [value for value in sections if value]


def v2_declares_template_binding(rule: dict[str, Any]) -> bool:
    """이 v2 행이 특정 템플릿에 결합된다고 원문에 적혀 있는지 본다.

    결합을 적어 두지 않은 행은 상품군 범위가 유일한 원문 한정이다. 그런 행까지
    템플릿 결합을 요구하면 심의 대상에서 조용히 사라지므로 구분해서 다룬다.
    """
    if str(rule.get("product_subtype") or "").strip():
        return True
    return bool(v2_template_sections(rule))


def v2_explicitly_mapped_to_template(
    rule: dict[str, Any], template_id: str | None
) -> bool:
    """Use only source-authored template bindings for the priority v2 pass.

    This intentionally performs no semantic/title similarity mapping. A v2 row
    is priority-mapped only through its explicit ``product_subtype`` or
    ``template_sections`` field; otherwise it remains eligible for the
    supplemental full-v2 retrieval pass.
    """
    if not template_id or rule.get("source_sheet") == "HWPX_TEMPLATE":
        return False
    target = str(template_id).strip()
    subtype = _TEMPLATE_CODE_PREFIX.sub(
        "", str(rule.get("product_subtype") or "")
    ).strip()
    if subtype and subtype == target:
        return True
    return target in set(v2_template_sections(rule))


def v2_is_general_presence_obligation(rule: dict[str, Any]) -> bool:
    """Identify product-scoped disclosure duties that cannot rely on retrieval.

    If required text is absent, the advertisement has no matching query phrase.
    Therefore checklist-style presence duties without a source-authored subtype
    or template binding must be enumerated for every applicable product. The
    applicability contract still decides conditional triggers; this function
    only prevents silent candidate loss.
    """
    return (
        rule.get("source_sheet") != "HWPX_TEMPLATE"
        and rule.get("category") == "PRESENCE"
        and rule.get("judgment_mode") == "체크리스트"
        and not v2_declares_template_binding(rule)
    )


_CONFIRMED_ROUTING_STATUSES = {"provided", "confirmed", "verified"}
_ELECTRONIC_DELIVERY_MEDIA = {"PUSH", "SMS", "MMS", "LMS", "ALIMTALK", "EMAIL"}


def v2_applies_to_confirmed_media(
    rule: dict[str, Any], routing: dict[str, Any]
) -> bool:
    """Select source-authored media obligations without relying on ad wording.

    Presence rules are needed precisely when required text is absent, so hybrid
    search over the advertisement cannot be the only way to discover them. A
    confirmed web routing value may enumerate a v2 rule when the rule itself
    names that medium or names electronic-delivery advertising generally.
    No item ID, advertisement text, or case answer is used here.
    """
    media = routing.get("media_type") or {}
    if not isinstance(media, dict):
        return False
    status = str(media.get("status") or "").strip().lower()
    value = str(media.get("value") or "").strip().upper()
    if status not in _CONFIRMED_ROUTING_STATUSES or value not in _ELECTRONIC_DELIVERY_MEDIA:
        return False
    rule_text = " ".join(
        str(rule.get(field) or "")
        for field in ("title", "question", "criterion", "v2_note")
    ).upper()
    named_media = {
        medium
        for medium in _ELECTRONIC_DELIVERY_MEDIA
        if re.search(rf"(?<![A-Z]){re.escape(medium)}(?![A-Z])", rule_text)
    }
    if named_media:
        return value in named_media
    return any(token in rule_text for token in (
        "전자적 전송매체", "영리목적 광고성 정보", "광고성 정보 전송",
    ))


def vector_cache_paths(
    cache_dir: Path,
    *,
    kind: str,
    source: Path,
    variant: str = "",
) -> tuple[Path, Path]:
    """Stable content-addressed vector cache paths shared by operational jobs."""
    identity = sha256(source)
    suffix = f"-{variant}" if variant else ""
    stem = f"{kind}-{identity}{suffix}"
    return cache_dir / f"{stem}.f16.npy", cache_dir / f"{stem}.meta.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _basis_ref(value: Any) -> str:
    """규칙 근거 한 건을 표시 가능한 참조 문자열로 만든다.

    v2의 ``규칙근거``는 규칙 객체 목록이라 ``str()``을 그대로 쓰면 파이썬 dict
    repr이 최종 화면까지 흘러간다. 객체는 식별자를 우선 쓰고, 없으면 요약을 쓴다.
    """
    if isinstance(value, dict):
        for key in ("id", "rule_id", "요약"):
            picked = str(value.get(key) or "").strip()
            if picked:
                return picked
        return ""
    return str(value or "").strip()


def _basis_strings(*values: Any) -> list[str]:
    output: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            output.extend(ref for ref in (_basis_ref(item) for item in value) if ref)
        else:
            ref = _basis_ref(value)
            if ref:
                output.append(ref)
    return list(dict.fromkeys(output))


def rule_basis(
    rule: dict[str, Any], *, regulation_sha256: str | None, template_sha256: str | None
) -> dict[str, Any]:
    """Bind every finding to an authoritative source without inventing law refs."""
    template = rule.get("template_basis") or {}
    is_template = rule.get("source_sheet") == "HWPX_TEMPLATE"
    legal_refs = _basis_strings(
        template.get("legal_basis_refs"),
        rule.get("legal_basis"),
        rule.get("representative_rule_id"),
        rule.get("supporting_rules"),
        rule.get("basis_details"),
    )
    source_ref = template.get("source_ref") if is_template else None
    if not isinstance(source_ref, str) or not source_ref.strip():
        source_ref = f"{rule.get('source_sheet') or 'REGULATION_V2'}:{rule['item_id']}"
    return {
        "item_id": rule["item_id"],
        "source_type": "INTERNAL_TEMPLATE" if is_template else "REGULATION_V2",
        "source_ref": source_ref,
        "source_sha256": (
            template.get("source_sha256") or template_sha256
            if is_template else (regulation_sha256 or None)
        ),
        "legal_basis_refs": legal_refs,
        "basis_status": (
            "LEGAL_BASIS_BOUND" if legal_refs else
            "SOURCE_BOUND" if is_template else
            "LEGAL_BASIS_NOT_PROVIDED"
        ),
    }


def decision_trace(result: dict[str, Any] | None, source: str | None) -> dict[str, Any]:
    trace = {
        "decision_source": (
            "DETERMINISTIC_RULE_RELATION" if (result or {}).get("relation_resolution") else
            "DETERMINISTIC_SOURCE_ARITHMETIC" if (source or '').endswith('#DETERMINISTIC_SOURCE_ARITHMETIC') else "LLM_VALIDATED_BY_DETERMINISTIC_GUARDRAILS"
            if result else "OUTPUT_CONTRACT_FAILURE"
        ),
        "model_result_source": source,
        "evidence_ids": list((result or {}).get("evidence_ids") or []),
        "evidence_line_refs": list((result or {}).get("evidence_line_refs") or []),
    }
    if (result or {}).get("relation_resolution"):
        trace["relation_resolution"] = result["relation_resolution"]
    return trace

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ad_identity(ad: dict[str, Any]) -> str:
    return str(ad.get("ad_id") or (ad.get("document") or {}).get("ad_id") or "").strip()


def load_ads(directory: Path) -> dict[str, dict[str, Any]]:
    ads: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        ad = json.loads(path.read_text(encoding="utf-8"))
        validate_integrated_input(ad)
        if (ad.get("document") or {}).get("products"):
            raise ValueError(
                "multi-product source must be expanded with "
                "product_scoped_documents before direct CLI execution"
            )
        ad_id = ad_identity(ad)
        if not ad_id:
            raise ValueError(f"ad_id가 없는 입력: {path}")
        if ad_id in ads:
            raise ValueError(f"중복 ad_id: {ad_id}")
        ads[ad_id] = ad
    if not ads:
        raise ValueError(f"광고 JSON이 없음: {directory}")
    return ads


def parser_coverage(ad: dict[str, Any]) -> str:
    """Return document execution coverage, not local reading confidence.

    ``unverified_recovery_candidates`` are page-sweep hints which were not
    assigned to the canonical line partition.  Their presence must remain
    auditable, but a single unverified token must not downgrade an otherwise
    complete advertisement and disable every text check.  The same boundary
    applies to empty or uncertain regions: they stay in the reading-quality
    audit and only affect rules whose evidence scope touches those regions.
    ``PARTIAL`` is reserved for a failed document/page scan or an inexact
    canonical line partition.  Layout and visibility availability are
    evaluated independently by ``automated_input_ready``.
    """
    quality = ad.get("quality") or {}
    pages = ad.get("pages") or []
    partial = bool(
        not quality.get("line_partition_exact")
        or not pages
        or any(page.get("parse_status") not in {None, "ok"} for page in pages)
    )
    return "PARTIAL" if partial else "READY"


def routing_context(ad: dict[str, Any], product_route: dict[str, Any]) -> dict[str, Any]:
    """Preserve routing provenance without turning inferred values into hard gates."""
    context: dict[str, Any] = {"product_group": product_route}
    if isinstance(ad.get("routing"), dict):
        values = ad["routing"]
        quality = ad.get("routing_quality") or {}
        for field in (
            "template_id",
            "product_subtype",
            "ad_type",
            "product_name_shown",
            "media_type",
            "review_stage",
            "association_pre_review",
            "external_evidence_available",
        ):
            detail = quality.get(field) if isinstance(quality.get(field), dict) else {}
            value = values.get(field)
            context[field] = {
                "value": value,
                "source": detail.get("source"),
                "status": detail.get("status") or ("unknown" if value in (None, "") else "inferred"),
            }
        return context

    metadata = ((ad.get("document") or {}).get("routing_metadata") or {})
    classification_source = metadata.get("classification_source")
    for field in (
        "template_id",
        "product_subtype",
        "ad_type",
        "product_name_shown",
        "media_type",
        "review_stage",
        "association_pre_review",
        "external_evidence_available",
    ):
        raw = metadata.get(field)
        if isinstance(raw, dict):
            context[field] = {
                "value": raw.get("value"),
                "source": raw.get("source"),
                "status": raw.get("status") or "unknown",
            }
        else:
            context[field] = {
                "value": raw,
                "source": classification_source,
                "status": "unknown" if raw in (None, "") else "inferred",
            }
    return context


def model_routing_view(routing: dict[str, Any]) -> dict[str, Any]:
    """Project routing provenance without sending discovery traces to Gemma.

    Product discovery retains its full audit trail in ``01_discovery.json``.
    The judgment model only needs the confirmed value, provenance status and
    the hard-route marker required by the output-contract validator.
    """
    raw_product_route = routing.get("product_group") or {}
    groups = raw_product_route.get("candidate_product_groups") if isinstance(raw_product_route, dict) else None
    if (
        not isinstance(groups, list)
        or len(groups) != 1
        or raw_product_route.get("routing_provisional") is not False
        or raw_product_route.get("hard_route") is not True
    ):
        raise ValueError("model routing view requires one confirmed hard product route")
    product_group = str(groups[0])
    output: dict[str, Any] = {
        "product_group": {
            "value": product_group,
            "source": "confirmed_product_route",
            "status": "confirmed",
            "routing_provisional": False,
            "candidate_product_groups": [product_group],
        }
    }
    for field, raw in routing.items():
        if field == "product_group":
            continue
        normalized = routing_field(raw)
        output[field] = {
            "value": normalized.get("value"),
            "source": normalized.get("source"),
            "status": normalized.get("status"),
        }
    return output


def model_deterministic_facts(
    facts: dict[str, Any], documents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Keep global text facts and only request-local visibility observations."""
    output = {key: value for key, value in facts.items() if key != "parser_visibility"}
    allowed = {str(document.get("parent_evidence_id") or document["evidence_id"]) for document in documents}
    allowed_lines = {str(ref) for document in documents for ref in document.get("line_refs") or []}
    visibility = (facts.get("parser_visibility") or {})
    pages = []
    for page in visibility.get("pages") or []:
        regions = []
        for region in page.get("regions") or []:
            if str(region.get("evidence_id")) not in allowed:
                continue
            projected = {**region, "line_styles": [
                line for line in region.get("line_styles") or []
                if str(line.get("line_ref")) in allowed_lines
            ]}
            regions.append(projected)
        if regions:
            pages.append({
                "page_no": page.get("page_no"),
                "canvas_w": page.get("canvas_w"),
                "canvas_h": page.get("canvas_h"),
                "dpi": page.get("dpi"),
                "physical_width_mm": page.get("physical_width_mm"),
                "physical_height_mm": page.get("physical_height_mm"),
                "regions": regions,
            })
    output["parser_visibility"] = {
        "source": "parser_or_ocr",
        "pages": pages,
        "recalculated_by_review_pipeline": False,
    }
    return output


def select_ads(
    ads: dict[str, dict[str, Any]],
    coarse: list[dict[str, Any]],
    fine: list[dict[str, Any]],
    selected_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not selected_ids:
        return ads, coarse, fine
    requested = set(selected_ids)
    missing = sorted(requested - set(ads))
    if missing:
        raise ValueError(f"--ad-id not found in inputs: {missing}")
    return (
        {ad_id: ads[ad_id] for ad_id in sorted(requested)},
        [row for row in coarse if str(row.get("ad_id")) in requested],
        [row for row in fine if str(row.get("ad_id")) in requested],
    )


def evidence_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in sorted(rows, key=lambda value: value["doc_id"]):
        output.append({
            "evidence_id": row["doc_id"],
            "parent_evidence_id": row.get("parent_doc_id"),
            "asset_id": row.get("asset_id"),
            "source_file": row.get("source_file"),
            "source_page_no": row.get("source_page_no"),
            "table": row.get("table"),
            "source_relations": row.get("source_relations") or [],
            "page_no": row.get("page_no"),
            "region_id": row.get("region_id"),
            "product_id": row.get("product_id"),
            "labels": row.get("labels") or [],
            "line_refs": row.get("line_refs") or [],
            "bbox": row.get("bbox"),
            "layout": row.get("layout"),
            "source_role": row.get("source_role") or "ADVERTISEMENT_CONTENT",
            "source_role_basis": row.get("source_role_basis"),
            "line_bboxes": row.get("line_bboxes") or {},
            "line_texts": row.get("line_texts") or {},
            "span_status": row.get("span_status") or "region_level_selected_text",
            "text_selection": row.get("text_selection") or {},
            "text": row.get("text_canonical") or row.get("text_search") or "",
        })
    return output


def template_rule_doc(rule: dict[str, Any]) -> dict[str, Any]:
    canonical_queries = [
        query
        for atom in (rule.get("canonical_execution_plan") or {}).get("obligations") or []
        for query in atom.get("retrieval_queries") or []
    ]
    parts = [
        rule.get("title"),
        rule.get("question"),
        rule.get("criterion"),
        rule.get("example_text"),
        rule.get("guide"),
        *canonical_queries,
    ]
    return {
        "doc_id": rule["item_id"],
        "item_id": rule["item_id"],
        "category": rule["category"],
        "category_label": rule["category_label"],
        "product_groups": rule["product_groups"],
        "product_subtype": rule.get("product_subtype"),
        "title": rule["title"],
        "question": rule["question"],
        "criterion": rule["criterion"],
        "search_text": " ".join(str(value).strip() for value in parts if str(value or "").strip()),
        "search_text_variant": "v2-template",
    }


def judgment_rule_text(rule: dict[str, Any]) -> str:
    guides = rule.get("decision_guides") or []
    guide_text = " ".join(
        str(value)
        for guide in guides
        for field in (
            "label",
            "applicability_conditions",
            "requirements",
            "compliant_examples",
            "violation_conditions",
            "review_conditions",
        )
        for value in (
            guide.get(field) if isinstance(guide.get(field), list) else [guide.get(field)]
        )
        if value
    )
    return " ".join(
        str(value).strip()
        for value in (
            rule.get("title"),
            rule.get("question"),
            rule.get("criterion"),
            rule.get("standard_examples"),
            rule.get("standard_guidance"),
            rule.get("example_text"),
            rule.get("guide"),
            guide_text,
        )
        if str(value or "").strip()
    )


def rerank_prohibition_candidates(
    candidates: list[dict[str, Any]],
    *,
    rules: dict[str, dict[str, Any]],
    fine_documents: dict[str, dict[str, Any]],
    rrf_k: int,
    candidate_pool: int,
) -> list[dict[str, Any]]:
    """Reorder, but never threshold-delete, hybrid prohibition candidates."""
    pool, _ = balanced_candidates(candidates, rules, candidate_pool)
    pairs = []
    retained = []
    pair_indexes = []
    for candidate in pool:
        triggers = candidate.get("trigger_evidence") or []
        rule = rules.get(str(candidate.get("item_id")))
        if rule is None:
            continue
        contexts, indexes = [], []
        for event in triggers:
            trigger = event.get("trigger") or {}
            trigger_id = str(trigger.get("doc_id") or "")
            if trigger_id not in fine_documents:
                continue
            context_ids = list(dict.fromkeys([*(trigger.get("query_context_doc_ids") or []), trigger_id]))
            if any(doc_id not in fine_documents for doc_id in context_ids):
                raise ValueError("reranker query context refers to missing evidence")
            if any(set(context_ids) == set(previous) for previous in contexts):
                continue
            contexts.append(context_ids)
            indexes.append(len(pairs))
            pairs.append([
                "\n".join(str(fine_documents[doc_id].get("text_canonical") or
                              fine_documents[doc_id].get("text_search") or "") for doc_id in context_ids),
                judgment_rule_text(rule),
            ])
        if indexes:
            retained.append(candidate)
            pair_indexes.append(indexes)
            candidate["reranker_evidence_ids"] = list(dict.fromkeys(key for group in contexts for key in group))
            candidate["reranker_contexts"] = contexts
    if not pairs:
        return candidates
    pair_scores = dgx_rerank(pairs, batch_size=16, max_length=512)
    if len(pair_scores) != len(pairs) or not np.isfinite(pair_scores).all():
        raise ValueError("reranker returned missing or non-finite scores")
    # A rule can be relevant to any one occurrence. Averaging would penalize
    # a strong match merely because other occurrences were also retrieved.
    scores = [max(float(pair_scores[i]) for i in indexes) for indexes in pair_indexes]
    for candidate, indexes in zip(retained, pair_indexes):
        candidate["reranker_context_scores"] = [float(pair_scores[i]) for i in indexes]
        candidate["reranker_aggregation"] = "max_unique_contexts"
    rerank_order = sorted(
        range(len(retained)),
        key=lambda index: (-float(scores[index]), str(retained[index]["item_id"])),
    )
    rerank_rank = {index: rank for rank, index in enumerate(rerank_order, 1)}
    for index, candidate in enumerate(retained):
        base_rank = int(candidate.get("rank") or index + 1)
        candidate["reranker_score"] = round(float(scores[index]), 8)
        candidate["reranker_rank"] = rerank_rank[index]
        candidate["hybrid_rerank_score"] = round(
            1.0 / (rrf_k + base_rank) + 1.0 / (rrf_k + rerank_rank[index]),
            10,
        )
    retained_ids = {str(row["item_id"]) for row in retained}
    unscored = [row for row in candidates if str(row["item_id"]) not in retained_ids]
    retained.sort(
        key=lambda row: (
            -row["hybrid_rerank_score"],
            row["reranker_rank"],
            int(row.get("rank") or 10**9),
            row["item_id"],
        )
    )
    output = [*retained, *unscored]
    for rank, row in enumerate(output, 1):
        row["final_rank"] = rank
    return output


def top_rule_evidence(
    item_id: str,
    *,
    rule_vector_by_id: dict[str, np.ndarray],
    ad_fine_rows: list[dict[str, Any]],
    fine_vector_by_id: dict[str, np.ndarray],
    trigger_ids: list[str],
    k: int,
    rule_text: str = "",
    rule_label: str = "",
) -> list[str]:
    """Select a small auditable evidence window for one rule.

    Dense similarity remains the broad retrieval signal, but a directly
    matching rule term gets first access to the small citable window.  This
    prevents a model which sees the complete transcript from attaching a
    nearby but unrelated line merely because the actual line was omitted from
    ``documents``.
    """
    vector = rule_vector_by_id[item_id]
    scored = sorted(
        (
            (
                float(np.dot(vector, fine_vector_by_id[row["doc_id"]])),
                str(row["doc_id"]),
            )
            for row in ad_fine_rows
        ),
        reverse=True,
    )
    vector_ranked = [doc_id for _, doc_id in scored]
    # The selected template's source field is a retrieval hint, never a
    # classification gate or proof of compliance. Preserve text/dense access
    # for unlabeled evidence and prefer readable observations among label hits.
    label_hits = [row for row in ad_fine_rows if rule_label and any(
        isinstance(label, dict) and str(label.get('label') or '').strip() == rule_label.strip()
        for label in row.get('labels') or [])]
    dense_position = {doc_id: rank for rank, doc_id in enumerate(vector_ranked)}
    label_hits.sort(key=lambda row: (needs_reading_review(row), dense_position[str(row['doc_id'])]))
    label_ranked = [str(row['doc_id']) for row in label_hits]

    terms = search_terms(rule_text)
    lexical_scored: list[tuple[int, int, str]] = []
    for row in ad_fine_rows:
        text = str(row.get("text_canonical") or row.get("text_search") or "").lower()
        matched = [term for term in terms if term in text]
        if matched:
            lexical_scored.append(
                (sum(min(len(term), 12) for term in matched), len(matched), str(row["doc_id"]))
            )
    lexical_scored.sort(key=lambda value: (-value[0], -value[1], value[2]))
    lexical_ranked = [doc_id for _, _, doc_id in lexical_scored]

    # Preserve triggers. Reserve the first lexical and dense hits so lexical
    # matches cannot consume the entire citable window; fuse the rest by rank.
    fused_scores: dict[str, float] = collections.defaultdict(float)
    for ranking in (lexical_ranked, vector_ranked):
        for rank, doc_id in enumerate(ranking, 1):
            fused_scores[doc_id] += 1.0 / (60 + rank)
    fused = sorted(fused_scores, key=lambda doc_id: (-fused_scores[doc_id], doc_id))
    ranked = list(dict.fromkeys([*label_ranked[:1], *lexical_ranked[:1], *vector_ranked[:1], *fused]))
    selected = list(dict.fromkeys(trigger_ids))
    if k <= 0:
        return selected
    retrieved = 0
    for doc_id in ranked:
        if doc_id in selected:
            continue
        selected.append(doc_id)
        retrieved += 1
        if retrieved >= k:
            break
    return selected


def t_rule_applies(rule: dict[str, Any], product_groups: list[str]) -> bool:
    allowed = set(rule.get("product_groups") or [])
    return "전체" in allowed or bool(allowed.intersection(product_groups))


def assert_candidate_product_scope(
    candidate_ids: list[str],
    *,
    rules: dict[str, dict[str, Any]],
    confirmed_product_groups: list[str],
) -> None:
    """Fail closed if any model candidate escaped the v2/template product scope.

    A supporting manual name is provenance, not an applicability override.  The
    authoritative product gate is the rule's ``product_groups`` value loaded
    from v2 or the independent template catalog.  This final assertion covers
    enumerated, template and retrieved prohibition candidates alike.
    """
    invalid: list[dict[str, Any]] = []
    for item_id in candidate_ids:
        rule = rules.get(item_id)
        if rule is None:
            invalid.append({"item_id": item_id, "reason": "missing rule definition"})
            continue
        allowed = set(map(str, rule.get("product_groups") or []))
        if "전체" not in allowed and not allowed.intersection(confirmed_product_groups):
            invalid.append({
                "item_id": item_id,
                "allowed_product_groups": sorted(allowed),
                "confirmed_product_groups": list(confirmed_product_groups),
            })
    if invalid:
        raise RuntimeError(
            "confirmed product scope outside judgment candidates: "
            + json.dumps(invalid, ensure_ascii=False)
        )


def automated_input_ready(
    rule: dict[str, Any], ad: dict[str, Any] | None = None
) -> bool:
    """Whether the integrated evidence contains the input v2 actually requires."""
    if requires_visual_review(rule):
        return False
    required_medium = str(rule.get("required_medium") or "").strip()
    if has_text_decision_facet(rule):
        required_medium = "텍스트"
    input_requirement = str(rule.get("input_requirement") or "").strip()
    if "랜딩캡처" in input_requirement and landing_capture_required(rule, ad):
        return False
    if ad is None:
        return required_medium not in {"레이아웃", "원문줄구조"} and "원본형식" not in input_requirement

    if required_medium == "원문줄구조":
        quality = ad.get("quality") or {}
        projection = (ad.get("diagnostics") or {}).get("rendered_line_projection") or {}
        pages = ad.get("pages") or []
        lines = [line for page in pages for region in (page.get("regions") or [])
                 for line in (region.get("lines") or [])]
        direct_geometry = bool(lines) and all(line.get("bbox") is not None for line in lines)
        return bool(
            quality.get("line_partition_exact") is True
            and all(page.get("parse_status") in {None, "ok"} for page in pages)
            and (projection.get("verified") is True or direct_geometry)
        )

    # Template wording about a line/placement is not a text rule.  Bounding
    # boxes establish where text is, but do not establish that two extracted
    # phrases are distinct checklist items on the same rendered line.  Until
    # the parser emits that verified grouping observation, retain it for human
    # review instead of asking the LLM to infer a violation from a section
    # heading or semantic label.
    if (
        rule.get("source_sheet") == "HWPX_TEMPLATE"
        and required_medium == "레이아웃"
        and (ad.get("layout_observations") or {}).get("verified_line_grouping") is not True
    ):
        return False

    pages = ad.get("pages") or []
    regions = [region for page in pages for region in (page.get("regions") or [])]
    has_spatial_layout = any(
        region.get("bbox") is not None
        or ((region.get("visibility") or {}).get("position") is not None)
        or any(line.get("bbox") is not None for line in (region.get("lines") or []))
        for region in regions
    )
    rule_text = " ".join(
        str(rule.get(field) or "")
        for field in (
            "title", "question", "criterion", "guide", "decision_criteria",
            "input_requirement", "required_medium",
        )
    )
    has_font_measurement = any(
        any(
            (line.get("style") or {}).get(field) is not None
            for field in ("size_pt", "size_pt_min", "size_pt_max")
        )
        for region in regions
        for line in (region.get("lines") or [])
    ) or any(
        any(
            (region.get("visibility") or {}).get(field) is not None
            for field in ("minimum_font_pt", "font_size_pt", "font_size_ratio")
        )
        for region in regions
    )
    has_contrast_measurement = any(
        any(
            (region.get("visibility") or {}).get(field) is not None
            for field in ("contrast_ratio", "minimum_contrast_ratio", "foreground_background_contrast")
        )
        for region in regions
    )
    has_visibility_measurement = has_font_measurement or has_contrast_measurement or any(
        any(
            value is not None
            for key, value in (region.get("visibility") or {}).items()
            if key != "position"
        )
        for region in regions
    )
    has_original_structure = bool(
        (ad.get("quality") or {}).get("line_partition_exact") is True
        and all(page.get("parse_status") in {None, "ok"} for page in pages)
        and any(
            line.get("style") is not None or line.get("bbox") is not None
            for region in regions
            for line in (region.get("lines") or [])
        )
    )
    if required_medium == "레이아웃":
        if not has_spatial_layout:
            return False
        if any(token in rule_text for token in ("글자 크기", "글씨 크기", "폰트", "pt", "포인트")) and not has_font_measurement:
            return False
        if any(token in rule_text for token in ("대비", "명도", "배경색", "색상 대비")) and not has_contrast_measurement:
            return False
        if any(token in rule_text for token in ("시인성", "가독성")) and not has_visibility_measurement:
            return False
    if "원본형식" in input_requirement and not has_original_structure:
        return False
    return True


def landing_capture_required(
    rule: dict[str, Any], ad: dict[str, Any] | None = None
) -> bool:
    """Return whether this routed ad still needs a separate landing capture.

    A full web product/event page is itself the destination content.  v2 rows
    that mention a landing capture for space-limited banners, search ads, SNS
    or messages must not make the same external input mandatory for such a
    page.  With no trusted media routing, retain the conservative deferral.
    """
    if "랜딩캡처" not in str(rule.get("input_requirement") or ""):
        return False
    if ad is None:
        return True
    media = (
        (((ad.get("document") or {}).get("routing_metadata") or {}).get("media_type") or {})
        if isinstance(ad, dict) else {}
    )
    media_value = str(media.get("value") or "") if isinstance(media, dict) else str(media or "")
    media_status = str(media.get("status") or "") if isinstance(media, dict) else ""
    if media_status in {"provided", "confirmed", "verified"} and media_value in {
        "WEB_PRODUCT_PAGE", "EVENT_PAGE",
    }:
        return False
    return True


def freeze_manifest(
    args: argparse.Namespace,
    *,
    request_path: Path,
    discovery_path: Path,
    ad_count: int,
) -> dict[str, Any]:
    code_paths = [
        Path(__file__),
        ROOT / "rag/contracts/validation.py",
        ROOT / "rag/judgment/applicability.py",
        ROOT / "rag/judgment/policy.py",
        ROOT / "rag/judgment/reading_quality.py",
        ROOT / "rag/judgment/temporal.py",
        ROOT / "rag/judgment/source_checks.py",
        ROOT / "rag/judgment/grounding.py",
        ROOT / "rag/judgment/evidence_projection.py",
        ROOT / "rag/judgment/condition_contracts.py",
        ROOT / "rag/judgment/candidate_activation.py",
        ROOT / "rag/judgment/operational_catalog.py",
        ROOT / "rag/judgment/operational_selection.py",
        ROOT / "rag/judgment/family_prompts.py",
        ROOT / "rag/judgment/obligation_logic.py",
        ROOT / "rag/judgment/manual_review.py",
        ROOT / "rag/templates/catalog.py",
        ROOT / "rag/templates/methodology.py",
        ROOT / "rag/templates/coverage.py",
        ROOT / "rag/retrieval/queries.py",
        ROOT / "rag/retrieval/candidates.py",
        ROOT / "rag/retrieval/context.py",
        ROOT / "rag/retrieval/evidence_bundle.py",
        ROOT / "rag/parsing/source_structure.py",
        ROOT / "tools/hybrid_rule_retrieval.py",
        ROOT / "tools/build_ad_evidence_vectors.py",
        ROOT / "tools/run_gemma_exhaustive_dgx.py",
        ROOT / "tools/dgx_bge_client.py",
        ROOT / "tools/dgx_openai_client.py",
        ROOT / "tools/build_silver_requests.py",
        ROOT / "tools/regulation_v2_catalog.py",
        ROOT / "tools/model_result_io.py",
        ROOT / "rag/build_items.py",
    ]
    input_paths = [args.coarse, args.fine, request_path, discovery_path,
                   *sorted(args.inputs_dir.glob("*.json"))]
    if getattr(args, "source_policy", "template-plus-v2") == "template-plus-v2":
        input_paths.append(args.regulation)
    if args.decision_guide:
        input_paths.append(args.decision_guide)
    if args.candidate_activation_policy:
        input_paths.append(args.candidate_activation_policy)
    for path in (args.canonical_plans, args.catalog_migration, args.rule_dispositions):
        if path:
            input_paths.append(path)
    if getattr(args, "template_hwpx", None):
        input_paths.append(args.template_hwpx)
    if getattr(args, "template_methodology_dir", None):
        input_paths.extend(methodology_workbooks(args.template_methodology_dir))
    if args.routing_manifest:
        input_paths.append(args.routing_manifest)
    return {
        "schema_version": FREEZE_VERSION,
        "frozen_before_prediction": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ads": ad_count,
        "configuration": {
            "source_policy": getattr(args, "source_policy", "template-plus-v2"),
            "rule_search_text_variant": args.rule_search_text_variant,
            "per_chunk_k": args.per_chunk_k,
            "rrf_k": args.rrf_k,
            "batch_size": args.batch_size,
            "full_ad_max_chars": args.full_ad_max_chars,
            "evidence_per_rule": args.evidence_per_rule,
            "reranker_candidate_pool": args.reranker_candidate_pool,
            "context_char_budget": args.context_char_budget,
            "formal_candidate_scope": (
                "TEMPLATE_PRIMARY+MEDIA_CONDITIONED_V2+"
                "PRODUCT_CONTENT_CONDITIONED_V2+RELATION_DEPENDENCY"
            ),
            "per_chunk_k_scope": "per_category_per_channel",
            "judgment_batch_size": args.batch_size,
            "judgment_max_tokens": args.judgment_max_tokens,
            "vector_cache_dir": str(args.vector_cache_dir.resolve()),
            "enable_applicability_screen": args.enable_applicability_screen,
            "elasticsearch_url": args.es_url,
            "elasticsearch_index": args.es_index,
            "model": args.model,
            "decision_guide": str(args.decision_guide) if args.decision_guide else None,
            "candidate_activation_policy": (
                str(args.candidate_activation_policy)
                if args.candidate_activation_policy
                else None
            ),
            "canonical_plans": str(args.canonical_plans) if args.canonical_plans else None,
            "catalog_migration": str(args.catalog_migration) if args.catalog_migration else None,
            "rule_dispositions": str(args.rule_dispositions) if args.rule_dispositions else None,
            "template_methodology_dir": (
                str(args.template_methodology_dir.resolve())
                if args.template_methodology_dir
                else None
            ),
            "temperature": 0,
        },
        "inputs": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in input_paths
        ],
        "code": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in code_paths
        ],
        "data_leakage_policy": (
            "prediction receives only the configured rule sources and advertisement evidence; "
            "no gold, researcher O/X, ad-specific rule mapping or case answer"
        ),
    }


def manifest_routing_field(raw: Any) -> dict[str, Any]:
    """Normalize trusted upstream routing input without inferring its value."""
    if isinstance(raw, dict):
        normalized = routing_field(raw, default_source="upstream_routing_manifest")
        if normalized["status"] not in {"confirmed", "verified", "provided"}:
            raise ValueError("routing manifest fields must be confirmed, verified, or provided")
        return normalized
    if raw in (None, ""):
        raise ValueError("routing manifest fields cannot be empty")
    return {"value": raw, "source": "upstream_routing_manifest", "status": "provided"}


def apply_routing_manifest(
    ads: dict[str, dict[str, Any]],
    coarse: list[dict[str, Any]],
    fine: list[dict[str, Any]],
    manifest_path: Path,
) -> None:
    """Apply explicit upstream routing values consistently to all projections.

    The manifest is an input artifact, not a generated lookup: entries are
    keyed by parser doc_id, reject unknown/duplicate IDs, and are frozen with
    the prediction.  It cannot carry rule IDs, verdicts, or answer-key data.
    """
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, dict) or raw_manifest.get("schema_version") != ROUTING_MANIFEST_VERSION:
        raise ValueError(f"routing manifest must use {ROUTING_MANIFEST_VERSION}")
    entries = raw_manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("routing manifest entries must be a non-empty list")
    seen: set[str] = set()
    rows_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in [*coarse, *fine]:
        rows_by_ad[str(row.get("ad_id"))].append(row)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"ad_id", "routing_overrides"}:
            raise ValueError("each routing manifest entry requires only ad_id and routing_overrides")
        ad_id = str(entry["ad_id"])
        if not ad_id or ad_id in seen:
            raise ValueError(f"routing manifest has duplicate/empty ad_id: {ad_id!r}")
        if ad_id not in ads:
            raise ValueError(f"routing manifest references unknown ad_id: {ad_id}")
        seen.add(ad_id)
        overrides = entry["routing_overrides"]
        if not isinstance(overrides, dict) or not overrides:
            raise ValueError(f"routing manifest overrides must be non-empty: {ad_id}")
        unknown = set(overrides) - ROUTING_OVERRIDE_FIELDS
        if unknown:
            raise ValueError(f"unsupported routing manifest fields: {sorted(unknown)}")
        normalized = {field: manifest_routing_field(value) for field, value in overrides.items()}
        routing = ads[ad_id]["document"].setdefault("routing_metadata", {})
        routing.update(copy.deepcopy(normalized))
        validate_integrated_input(ads[ad_id])
        for row in rows_by_ad[ad_id]:
            row.setdefault("routing_metadata", {}).update(copy.deepcopy(normalized))
            row.setdefault("routing", {}).update(copy.deepcopy(normalized))
    validate_search_collections(ads.values(), coarse, fine)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-dir", type=Path, required=True)
    parser.add_argument("--review-date", type=date.fromisoformat,
                        help="Explicit review day (YYYY-MM-DD); never the printed rate basis date")
    parser.add_argument("--review-date-basis", default="explicit_review_date",
                        choices=("explicit_review_date", "advertisement_registration_date"))
    parser.add_argument("--coarse", type=Path, required=True)
    parser.add_argument("--fine", type=Path, required=True)
    parser.add_argument("--source-policy", choices=("template-only", "template-plus-v2"), default="template-only")
    parser.add_argument("--regulation", type=Path)
    parser.add_argument("--decision-guide", type=Path)
    parser.add_argument(
        "--candidate-activation-policy",
        type=Path,
        help=(
            "source-bound policy that promotes retrieved content-conditional v2 "
            "rules or routes visual rules to human review"
        ),
    )
    parser.add_argument("--canonical-plans", type=Path,
                        help="released canonical template and supplemental execution plans")
    parser.add_argument("--catalog-migration", type=Path,
                        help="exact canonical-to-legacy template catalog migration")
    parser.add_argument("--rule-dispositions", type=Path,
                        help="active, alias, template-support and hold registry")
    parser.add_argument("--template-hwpx", type=Path,
                        help="general template source; independent checklist, no v2 ID mapping required")
    parser.add_argument(
        "--template-methodology-dir",
        type=Path,
        help="directory containing general *심의방법.xlsx guides; case-answer files are ignored",
    )
    parser.add_argument(
        "--routing-manifest",
        type=Path,
        help=(
            "trusted upstream per-ad routing input, schema "
            f"{ROUTING_MANIFEST_VERSION}; never derived from filenames or gold"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--es-url",
        default=os.environ.get("NH_RAG_ES_URL", "http://127.0.0.1:19201"),
    )
    parser.add_argument("--es-index", default=os.environ.get("NH_RAG_ES_INDEX"))
    parser.add_argument("--rule-search-text-variant", choices=("core", "expanded"), default="core")
    parser.add_argument("--per-chunk-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_RULES_PER_JUDGMENT,
        help=(
            "maximum v2 rules per logical Gemma judgment request "
            f"(1-{MAX_RULES_PER_JUDGMENT}; default {DEFAULT_RULES_PER_JUDGMENT})"
        ),
    )
    parser.add_argument(
        "--judgment-max-tokens",
        type=int,
        default=DEFAULT_JUDGMENT_MAX_TOKENS,
        help=(
            "Gemma output budget per logical request; raise only after a "
            "measured contract truncation"
        ),
    )
    parser.add_argument(
        "--vector-cache-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "NH_RAG_VECTOR_CACHE_DIR",
                str(ROOT / "runtime-cache" / "vectors"),
            )
        ),
        help="shared content-addressed BGE vector cache; derived data only",
    )
    parser.add_argument("--evidence-per-rule", type=int, default=3)
    parser.add_argument("--context-char-budget", type=int, default=2400,
                        help="Additional source-region context characters per rule; 0 disables expansion")
    parser.add_argument("--full-ad-max-chars", type=int, default=12000)
    parser.add_argument("--reranker-candidate-pool", type=int, default=80)
    parser.add_argument(
        "--enable-applicability-screen",
        action="store_true",
        help="실험용 Gemma 1차 적용성 검사를 추가한다(운영 기본값은 꺼짐)",
    )
    parser.add_argument(
        "--allow-provisional-routing",
        action="store_true",
        help="Debug only: fail open to all supported product groups when product_group is not confirmed.",
    )
    parser.add_argument("--execute-judgment", action="store_true")
    parser.add_argument(
        "--resume-checkpoint",
        type=Path,
        help="Compatible Gemma checkpoint from a previous service attempt",
    )
    parser.add_argument("--host", default=os.environ.get("DGX_HOST"))
    parser.add_argument(
        "--key",
        type=Path,
        default=Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None,
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "NH_GPU_GEMMA_MODEL",
            os.environ.get("DGX_GEMMA_MODEL", "gemma-4-26b-NVFP4-MTP"),
        ),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--ad-id",
        action="append",
        default=[],
        help="Process only this ad_id; repeat for multiple ads.",
    )
    args = parser.parse_args()
    # The judgment subprocess runs with ``rag-pipeline`` as its working
    # directory.  Resolve once so CLI callers may safely pass a relative
    # output directory without the child looking in a different tree.
    args.output_dir = args.output_dir.resolve()
    template_only = args.source_policy == "template-only"
    if template_only and not args.template_hwpx:
        parser.error("template-only review requires --template-hwpx")
    if args.template_methodology_dir and not args.template_hwpx:
        parser.error("--template-methodology-dir requires --template-hwpx")
    if template_only and args.decision_guide:
        parser.error("v2 decision guides cannot be used with template-only review")
    if template_only and args.candidate_activation_policy:
        parser.error("v2 candidate activation cannot be used with template-only review")
    canonical_paths = (args.canonical_plans, args.catalog_migration, args.rule_dispositions)
    if any(canonical_paths) and not all(canonical_paths):
        parser.error("canonical catalog requires --canonical-plans, --catalog-migration and --rule-dispositions")
    if args.canonical_plans and args.candidate_activation_policy:
        parser.error("canonical catalog replaces the legacy candidate activation policy")
    if not template_only and (not args.es_index or not args.regulation):
        parser.error("--es-index or NH_RAG_ES_INDEX is required")
    if not 1 <= args.batch_size <= MAX_RULES_PER_JUDGMENT:
        parser.error(
            f"--batch-size must be between 1 and {MAX_RULES_PER_JUDGMENT}"
        )
    if args.judgment_max_tokens < 1024:
        parser.error("--judgment-max-tokens must be at least 1024")
    if args.template_hwpx and args.enable_applicability_screen:
        parser.error("template source uses the operational joint judgment; the v2-only experimental screen is unsupported")

    if not template_only:
        v2_source.set_agent_path(args.regulation)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ads = load_ads(args.inputs_dir)
    coarse = read_jsonl(args.coarse)
    fine = sorted(read_jsonl(args.fine), key=lambda row: row["doc_id"])
    validate_search_collections(ads.values(), coarse, fine)
    if args.routing_manifest:
        if not args.routing_manifest.is_file():
            parser.error(f"--routing-manifest not found: {args.routing_manifest}")
        apply_routing_manifest(ads, coarse, fine, args.routing_manifest)
    ads, coarse, fine = select_ads(ads, coarse, fine, args.ad_id)
    coarse_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    fine_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in coarse:
        coarse_by_ad[str(row["ad_id"])].append(row)
    for row in fine:
        fine_by_ad[str(row["ad_id"])].append(row)
    if set(ads) != set(coarse_by_ad) or set(ads) != set(fine_by_ad):
        raise RuntimeError(
            "광고 입력/coarse/fine ad_id 집합 불일치: "
            f"input_only={sorted(set(ads)-set(coarse_by_ad))}, "
            f"coarse_only={sorted(set(coarse_by_ad)-set(ads))}, "
            f"fine_only={sorted(set(fine_by_ad)-set(ads))}"
        )

    items, all_items_by_id = ([], {}) if template_only else discovery.load_scope(include_layout=True)
    # Search eligibility is not observation readiness. Keep product-relevant
    # layout rules searchable; automated_input_ready defers missing observations.
    all_source_items = (
        list(all_items_by_id.values())
        if isinstance(all_items_by_id, dict)
        else list(all_items_by_id)
    )
    v2_condition_audit = audit_v2_source_items(all_source_items)
    if (
        v2_condition_audit["compiled_rule_count"]
        != v2_condition_audit["source_rule_count"]
        or v2_condition_audit["missing_scope_count"]
    ):
        raise RuntimeError(f"v2 condition contract audit failed: {v2_condition_audit}")
    write_json(
        args.output_dir / "00_condition_contract_audit.json",
        {key: value for key, value in v2_condition_audit.items() if key != "contracts"},
    )
    cd_rules = [] if template_only else judgment_input.load_cd_rules(include_layout=True)
    if {item["id"] for item in items} != {rule["item_id"] for rule in cd_rules}:
        raise ValueError("search catalog and judgment rule definitions have different item IDs")
    template_catalog = (
        TemplateCatalog.from_hwpx(
            args.template_hwpx,
            methodology_dir=args.template_methodology_dir,
        )
        if args.template_hwpx
        else None
    )
    t_rules = template_catalog.operational_rules() if template_catalog else load_template_candidate_rules()
    canonical_catalog = None
    if args.canonical_plans:
        canonical_catalog = load_operational_catalog(
            args.canonical_plans,
            args.catalog_migration,
            args.rule_dispositions,
            legacy_template_rules=t_rules,
            v2_rules=cd_rules,
            include_supplements=not template_only,
        )
        t_rules = canonical_catalog.template_rules
        cd_rules = [
            canonical_catalog.supplemental_rules.get(rule["item_id"], rule)
            for rule in cd_rules
        ]
        write_json(args.output_dir / "00_canonical_catalog.json", {
            "source_sha256": canonical_catalog.source_sha256,
            "migration_sha256": canonical_catalog.migration_sha256,
            "disposition_sha256": canonical_catalog.disposition_sha256,
            "counts": canonical_catalog.counts,
        })
    if template_catalog:
        write_json(args.output_dir / "00_template_catalog.json", template_catalog.document)
        write_json(args.output_dir / "00_template_source.json", template_catalog.source)
    all_rules = [*cd_rules, *t_rules]
    guides = {} if template_only else load_decision_guides(
        args.decision_guide,
        regulation_path=args.regulation,
        known_item_ids=(rule["item_id"] for rule in all_rules),
    )
    attach_decision_guides(all_rules, guides)
    attach_condition_contracts(all_rules)
    candidate_activation_policy = (
        {}
        if template_only
        else load_candidate_activation_policy(
            args.candidate_activation_policy,
            regulation_path=args.regulation,
            rules=all_rules,
        )
    )
    write_json(args.output_dir / "00_compiled_obligation_audit.json", audit_compiled_rules(all_rules))
    rule_by_id = {row["item_id"]: row for row in all_rules}
    regulation_source_sha = None if template_only else sha256(args.regulation)
    template_source_sha = sha256(args.template_hwpx) if args.template_hwpx else None
    rule_basis_by_id = {
        item_id: rule_basis(
            rule,
            regulation_sha256=regulation_source_sha,
            template_sha256=template_source_sha,
        )
        for item_id, rule in rule_by_id.items()
    }
    cd_rule_docs = discovery.rule_docs(
        items, search_text_variant=args.rule_search_text_variant
    )
    rule_docs = [
        *cd_rule_docs,
        *(template_rule_doc(rule) for rule in t_rules),
    ]
    started_at = time.perf_counter()
    model = discovery.load_model()
    args.vector_cache_dir.mkdir(parents=True, exist_ok=True)
    rule_source = args.template_hwpx if template_only else args.regulation
    canonical_variant = canonical_catalog.source_sha256 if canonical_catalog else ""
    rule_vectors_path, rule_meta_path = vector_cache_paths(
        args.vector_cache_dir,
        kind="rules",
        source=rule_source,
        variant=(args.rule_search_text_variant + "-template-" + sha256(args.template_hwpx)
                 + ("-canonical-" + canonical_variant if canonical_variant else "")
                 if args.template_hwpx else args.rule_search_text_variant
                 + ("-canonical-" + canonical_variant if canonical_variant else "")),
    )
    rule_vectors, rule_vectors_cached, rule_embedding_seconds = discovery.load_or_encode(
        rule_docs,
        text_key="search_text",
        source=rule_source,
        vectors_path=rule_vectors_path,
        meta_path=rule_meta_path,
        model=model,
        batch_size=4,
        force=False,
    )
    fine_vectors_path, fine_meta_path = vector_cache_paths(
        args.vector_cache_dir,
        kind="evidence-fine",
        source=args.fine,
    )
    fine_vectors, fine_vectors_cached, fine_embedding_seconds = discovery.load_or_encode(
        fine,
        text_key="text_search",
        source=args.fine,
        vectors_path=fine_vectors_path,
        meta_path=fine_meta_path,
        model=model,
        batch_size=4,
        force=False,
    )
    if not template_only:
        args.es_index = discovery.versioned_rule_index(
            args.es_index, cd_rule_docs, rule_vectors[: len(cd_rule_docs)],
            source_sha=regulation_source_sha,
        )
        discovery.ensure_rule_index(
            args.es_url, args.es_index, cd_rule_docs,
            rule_vectors[: len(cd_rule_docs)], source_sha=regulation_source_sha,
        )
    fine_vector_by_id = {row["doc_id"]: vector for row, vector in zip(fine, fine_vectors)}
    rule_vector_by_id = {row["item_id"]: vector for row, vector in zip(rule_docs, rule_vectors)}

    discovery_ads = []
    requests = []
    requested_pairs: set[tuple[str, str]] = set()
    if args.enable_applicability_screen:
        # Applicability itself is a prediction: freeze inputs before calling it.
        screen_inputs = [
            args.regulation,
            args.coarse,
            args.fine,
            *sorted(args.inputs_dir.glob("*.json")),
        ]
        if args.decision_guide:
            screen_inputs.append(args.decision_guide)
        if args.template_hwpx:
            screen_inputs.append(args.template_hwpx)
        write_json(args.output_dir / "00_applicability_freeze.json", {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inputs": [
                {"path": str(path), "sha256": sha256(path)}
                for path in screen_inputs
            ],
            "code_sha256": sha256(Path(__file__)),
            "applicability_code_sha256": sha256(
                ROOT / "rag/judgment/applicability.py"
            ),
            "model": args.model,
            "full_ad_max_chars": args.full_ad_max_chars,
        })
    for ad_id in sorted(ads):
        search_queries, query_context_audit = build_context_queries(fine_by_ad[ad_id])
        context_queries = [] if template_only else [row for row in search_queries if row.get("_query_members")]
        query_vectors = dict(fine_vector_by_id)
        if context_queries:
            context_paths = vector_cache_paths(
                args.vector_cache_dir, kind="query-context", source=args.fine,
                variant=hashlib.sha256(ad_id.encode()).hexdigest()[:16] + "-whole-parent-v1")
            context_vectors, _, _ = discovery.load_or_encode(
                context_queries, text_key="text_search", source=args.fine,
                vectors_path=context_paths[0], meta_path=context_paths[1], model=model,
                batch_size=4, force=False)
            query_vectors.update(zip((row["doc_id"] for row in context_queries), context_vectors))
        route = discovery.routing_scope(coarse_by_ad[ad_id])
        route_context = routing_context(ads[ad_id], route)
        if args.allow_provisional_routing:
            candidate_groups = route["candidate_product_groups"]
        else:
            candidate_groups = [require_confirmed_product_group(route_context)]
            route = {
                **route,
                "candidate_product_groups": candidate_groups,
                "routing_provisional": False,
                "hard_route": True,
                "status": "routing_confirmed",
            }
            route_context["product_group"] = route
        confirmed_template_id = confirmed_template(route_context)
        canonical_selection = None
        if canonical_catalog:
            layout_available = any(
                region.get("bbox") is not None
                for page in (ads[ad_id].get("pages") or [])
                for region in (page.get("regions") or [])
            )
            canonical_selection = select_supplemental_plans(
                (
                    canonical_catalog.plans[item_id]
                    for item_id in canonical_catalog.supplemental_rules
                ),
                product_groups=candidate_groups,
                template_id=confirmed_template_id,
                routing=route_context,
                layout_available=layout_available,
            )
        all_product_items = [
            item for item in items if discovery.applicable_to_any(item, candidate_groups)
        ]
        product_items = [
            item
            for item in all_product_items
            if template_scoped_rule(item, confirmed_template_id)
        ]
        template_scope_deferred = [
            {
                "item_id": item["id"],
                "reason": "confirmed template does not match this v2 product subtype",
                "confirmed_template_id": confirmed_template_id,
                "rule_product_subtype": rule_by_id[item["id"]].get("product_subtype"),
            }
            for item in all_product_items
            if not template_scoped_rule(item, confirmed_template_id)
        ]
        # 2단계 우선 열거는 원문에 확정 템플릿 결합이 명시된 v2 행만
        # 대상으로 한다. 결합 미기재 행을 여기서 전수 열거하면 템플릿
        # 중심 정책이 다시 v2 전수 판정으로 변한다. 그런 행은 버리지 않고
        # 3단계 supplemental v2 검색에서 광고 촉발 근거를 찾은 경우만 판정한다.
        mapped_v2_items = [
            item for item in product_items
            if v2_explicitly_mapped_to_template(
                rule_by_id[item["id"]], confirmed_template_id
            )
        ]
        mapped_v2_ids = {item["id"] for item in mapped_v2_items}
        general_v2_items = [] if template_only else [
            item for item in product_items
            if item["id"] not in mapped_v2_ids
            and v2_is_general_presence_obligation(rule_by_id[item["id"]])
        ]
        general_v2_ids = {item["id"] for item in general_v2_items}
        if canonical_selection:
            canonical_enumerate_ids = set(canonical_selection.enumerate_ids)
            media_v2_items = [
                item for item in product_items if item["id"] in canonical_enumerate_ids
            ]
        else:
            media_v2_items = [] if template_only else [
                item for item in product_items
                if item["id"] not in mapped_v2_ids | general_v2_ids
                and v2_applies_to_confirmed_media(rule_by_id[item["id"]], route_context)
            ]
        # Template-linked v2 rows remain support/audit material until their
        # separate judgments have gold coverage. Only confirmed-media v2 rows
        # add a formal judgment beyond the selected template.
        formal_v2_items = [*media_v2_items]
        deferred_input_rules = [
            {
                "item_id": item["id"],
                "required_medium": item["필요매체"],
                "input_requirement": item["입력요건"],
                "reason": deferred_input_reason(rule_by_id[item["id"]]),
            }
            for item in formal_v2_items
            if not automated_input_ready(rule_by_id[item["id"]], ads[ad_id])
        ]
        if canonical_selection:
            deferred_input_rules.extend(dict(row) for row in canonical_selection.pending)
        mapped_v2_audit = [
            {
                "item_id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "discovery_method": "template_mapped_v2_enumeration",
                "input_ready": automated_input_ready(rule_by_id[item["id"]], ads[ad_id]),
                "input_deferred_reason": (
                    None if automated_input_ready(rule_by_id[item["id"]], ads[ad_id])
                    else deferred_input_reason(rule_by_id[item["id"]])
                ),
            }
            for item in mapped_v2_items
        ]
        general_v2_audit = [
            {
                "item_id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "discovery_method": "general_v2_presence_enumeration",
                "input_ready": automated_input_ready(rule_by_id[item["id"]], ads[ad_id]),
                "input_deferred_reason": (
                    None if automated_input_ready(rule_by_id[item["id"]], ads[ad_id])
                    else deferred_input_reason(rule_by_id[item["id"]])
                ),
            }
            for item in general_v2_items
        ]
        media_enumerated = [
            {
                "item_id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "discovery_method": (
                    "canonical_confirmed_metadata_enumeration"
                    if canonical_selection else "confirmed_media_v2_enumeration"
                ),
            }
            for item in media_v2_items
            if (
                automated_input_ready(rule_by_id[item["id"]], ads[ad_id])
                or args.enable_applicability_screen
            )
        ]
        template_value = confirmed_template(route_context)
        if template_only and template_value not in {rule.get("product_subtype") for rule in t_rules}:
            raise ValueError("selected template is missing from the authoritative template source")
        template_candidates = [
            {
                "item_id": rule["item_id"],
                "category": rule["category"],
                "title": rule["title"],
                "discovery_method": "confirmed_template_enumeration",
            }
            for rule in t_rules
            if template_value
            and t_rule_applies(rule, candidate_groups)
            and rule.get("product_subtype") == template_value
            and (not rule.get("template_basis") or rule["template_basis"]["structure_status"] == "STRUCTURED"
                 or rule["template_basis"].get("text_review_ready"))
            and automated_input_ready(rule, ads[ad_id])
        ]
        deferred_input_rules.extend(
            {"item_id": rule["item_id"], "reason": deferred_input_reason(rule),
             "required_medium": rule.get("required_medium"),
             "input_requirement": rule.get("input_requirement")}
            for rule in t_rules
            if rule.get("product_subtype") == template_value
            and (not rule.get("template_basis") or rule["template_basis"]["structure_status"] == "STRUCTURED")
            and not automated_input_ready(rule, ads[ad_id])
        )
        deferred_input_rules.extend(
            {"item_id": rule["item_id"], "reason": "template source structure requires review",
             "template_basis": rule["template_basis"]}
            for rule in t_rules
            if rule.get("product_subtype") == template_value and rule.get("template_basis")
            and rule["template_basis"]["structure_status"] != "STRUCTURED"
            and not rule["template_basis"].get("text_review_ready")
        )
        deferred_input_rules.extend(
            {"item_id": rule["item_id"], "title": rule["title"], "facet": "VISUAL_OR_STRUCTURE",
             "reason": "텍스트 의무는 별도 판정하며 배치·로고·중첩 원문 구조는 사람 확인 필요",
             "template_basis": rule["template_basis"]}
            for rule in t_rules if rule.get("product_subtype") == template_value
            and (rule.get("template_basis") or {}).get("manual_review_required")
        )
        deferred_template_rules = [
            rule["item_id"]
            for rule in t_rules
            if t_rule_applies(rule, candidate_groups)
            and rule.get("product_subtype") != template_value
        ]
        # Policy rows must remain searchable even if a broad source-shape rule
        # also classifies them as mapped/general. Their advertisement-content
        # trigger comes from retrieval, not from product-wide enumeration.
        activation_policy_ids = (
            set(canonical_catalog.supplemental_rules)
            if canonical_catalog else set(candidate_activation_policy)
        )
        priority_v2_ids = (
            mapped_v2_ids | general_v2_ids | {item["id"] for item in media_v2_items}
        ) - activation_policy_ids
        supplemental_v2 = [] if template_only else discovery.discover_prohibitions(
            search_queries,
            query_vectors,
            candidate_groups,
            base_url=args.es_url,
            index=args.es_index,
            per_chunk_k=args.per_chunk_k,
            rrf_k=args.rrf_k,
            deterministic_item_ids=priority_v2_ids,
            categories=("PRESENCE", "PROHIBIT", "STYLE"),
            allowed_item_ids=(
                set(canonical_catalog.supplemental_rules)
                if canonical_catalog else None
            ),
        )
        supplemental_v2 = rerank_prohibition_candidates(
            supplemental_v2,
            rules=rule_by_id,
            fine_documents={str(row["doc_id"]): row for row in fine_by_ad[ad_id]},
            rrf_k=args.rrf_k,
            candidate_pool=args.reranker_candidate_pool,
        )
        supplemental_v2_retrieved = supplemental_v2
        content_conditioned_v2 = (
            activate_retrieved(
                supplemental_v2_retrieved, canonical_selection.retrieval_ids
            )
            if canonical_selection else
            activated_retrieval_rows(
                supplemental_v2_retrieved,
                candidate_activation_policy,
                execution_tier=CONTENT_TIER,
            )
        )
        content_conditioned_v2 = [
            row
            for row in content_conditioned_v2
            if template_scoped_rule(
                rule_by_id[row["item_id"]], confirmed_template_id
            )
            and (
                automated_input_ready(rule_by_id[row["item_id"]], ads[ad_id])
                or args.enable_applicability_screen
            )
        ]
        policy_visual_v2 = (
            activate_retrieved(
                supplemental_v2_retrieved, canonical_selection.human_ids
            )
            if canonical_selection else
            activated_retrieval_rows(
                supplemental_v2_retrieved,
                candidate_activation_policy,
                execution_tier=VISUAL_TIER,
            )
        )
        supplemental_v2_audit = [
            {
                **row,
                "input_ready": automated_input_ready(
                    rule_by_id[row["item_id"]], ads[ad_id]
                ),
                "input_deferred_reason": (
                    None if automated_input_ready(rule_by_id[row["item_id"]], ads[ad_id])
                    else deferred_input_reason(rule_by_id[row["item_id"]])
                ),
                "template_scope_match": template_scoped_rule(
                    rule_by_id[row["item_id"]], confirmed_template_id
                ),
            }
            for row in supplemental_v2_retrieved
        ]
        # A retrieved visual rule is still a review candidate. Retrieval tells
        # us which source and advertisement region to surface; it does not
        # authorize Gemma to decide color, size, contrast or placement.
        supplemental_visual_ids = list(dict.fromkeys([
            row["item_id"]
            for row in [*supplemental_v2_retrieved, *policy_visual_v2]
            if template_scoped_rule(
                rule_by_id[row["item_id"]], confirmed_template_id
            )
            and requires_visual_review(rule_by_id[row["item_id"]])
        ]))
        _, supplemental_visual_review = partition_visual_review_candidates(
            supplemental_visual_ids, rule_by_id
        )
        supplemental_visual_review = attach_visual_retrieval_evidence(
            supplemental_visual_review, supplemental_v2_retrieved
        )
        deferred_input_rules.extend(supplemental_visual_review)
        supplemental_v2 = [
            row
            for row in supplemental_v2_retrieved
            if (
                automated_input_ready(rule_by_id[row["item_id"]], ads[ad_id])
                or args.enable_applicability_screen
            )
            and template_scoped_rule(
                rule_by_id[row["item_id"]], confirmed_template_id
            )
        ]
        audit_only_v2 = [
            *({**row, "discovery_tier": "MAPPED_V2"}
              for row in mapped_v2_audit),
            *({**row, "discovery_tier": "GENERAL_V2_PRESENCE"}
              for row in general_v2_audit),
            *({**row, "discovery_tier": "SUPPLEMENTAL_V2"}
              for row in supplemental_v2_audit),
        ]
        audit_by_item: dict[str, dict[str, Any]] = {}
        for row in audit_only_v2:
            item_id = str(row["item_id"])
            tier = str(row.get("discovery_tier") or "")
            if item_id not in audit_by_item:
                audit_by_item[item_id] = {
                    **row,
                    "discovery_tiers": [tier] if tier else [],
                }
                continue
            existing = audit_by_item[item_id]
            if tier and tier not in existing["discovery_tiers"]:
                existing["discovery_tiers"].append(tier)
        audit_only_v2 = list(audit_by_item.values())
        activated_ids = {
            row["item_id"]
            for row in [*content_conditioned_v2, *policy_visual_v2]
        }
        audit_only_v2 = [
            row for row in audit_only_v2 if row["item_id"] not in activated_ids
        ]
        candidate_rows = formal_judgment_candidates(
            template_primary=template_candidates,
            media_conditioned_v2=media_enumerated,
            product_content_conditioned_v2=content_conditioned_v2,
        )
        candidate_ids = list(dict.fromkeys(row["item_id"] for row in candidate_rows))
        original_candidate_ids = set(candidate_ids)
        candidate_ids = expand_relation_dependencies(candidate_ids, rule_by_id)
        relation_dependency_ids = set(candidate_ids) - original_candidate_ids
        audit_only_v2 = [
            row for row in audit_only_v2
            if row["item_id"] not in relation_dependency_ids
        ]
        candidate_budget_audit = audit_only_candidates(
            audit_only_v2,
            rule_by_id,
            reason="outside_formal_execution_scope",
        )
        # Candidate discovery and judgment capability are separate. Preserve
        # every discovered visual rule for the reviewer while withholding it
        # from automatic applicability/judgment calls.
        candidate_ids, visual_review_candidates = partition_visual_review_candidates(
            candidate_ids, rule_by_id
        )
        deferred_input_rules.extend(visual_review_candidates)
        deferred_input_rules = list({
            row["item_id"]: row for row in deferred_input_rules
        }.values())
        discovery_tier_by_item = {
            **{row["item_id"]: "TEMPLATE_PRIMARY" for row in template_candidates},
            **{row["item_id"]: "MEDIA_CONDITIONED_V2" for row in media_enumerated},
            **{
                row["item_id"]: "PRODUCT_CONTENT_CONDITIONED_V2"
                for row in content_conditioned_v2
            },
            **{item_id: "RELATION_DEPENDENCY" for item_id in relation_dependency_ids},
        }
        assert_candidate_product_scope(
            candidate_ids,
            rules=rule_by_id,
            confirmed_product_groups=candidate_groups,
        )
        screened = {}
        excluded_applicability = []
        applicability_pending = []
        full_documents = evidence_documents(coarse_by_ad[ad_id])
        complete_scan = parser_coverage(ads[ad_id]) == "READY"
        if args.execute_judgment and args.enable_applicability_screen:
            screened, trace = screen_rules(
                rules=[rule_by_id[item_id] for item_id in candidate_ids],
                documents=full_documents, routing=route_context,
                complete_ad_scan=complete_scan, model=args.model,
                post=lambda payload: post_json(payload, host=args.host, key=args.key, timeout=240),
                workers=min(args.workers, 2),
            )
            write_json(args.output_dir / f"00_applicability_{len(discovery_ads)}.json",
                       {"ad_id": ad_id, "screened": screened, "trace": trace})
            retained = []
            for item_id in candidate_ids:
                screen = screened[item_id]
                if screen["applicability"] == "NOT_APPLICABLE":
                    excluded_applicability.append(screen)
                if screen["input_mode"] == "EXTERNAL":
                    applicability_pending.append({"item_id": item_id, "reason": screen["reason"]})
                else:
                    # Applicability screening is advisory.  A fallible first
                    # model pass must not suppress a rule before the final
                    # judgment independently confirms NOT_APPLICABLE.
                    retained.append(item_id)
            candidate_ids = retained
            # Preserve genuinely unavailable rules which were outside the search candidates.
            deferred_input_rules.extend(
                {"item_id": item["id"],
                 "reason": deferred_input_reason(rule_by_id[item["id"]]),
                 "required_medium": item["필요매체"], "input_requirement": item["입력요건"]}
                for item in mapped_v2_items if item["id"] not in screened
                and not automated_input_ready(rule_by_id[item["id"]], ads[ad_id])
            )
            deferred_input_rules = list({
                row["item_id"]: row for row in deferred_input_rules
            }.values())
        missing_rule_defs = set(candidate_ids) - set(rule_by_id)
        if missing_rule_defs:
            raise RuntimeError(f"판정 정의가 없는 후보: {sorted(missing_rule_defs)}")
        fine_doc_by_id = {
            row["doc_id"]: evidence_documents([row])[0]
            for row in fine_by_ad[ad_id]
        }
        trigger_by_item = {
            row["item_id"]: [
                doc_id
                for event in row.get("trigger_evidence") or []
                for doc_id in ([str((event.get("trigger") or {}).get("doc_id"))] +
                               ((event.get("trigger") or {}).get("query_context_doc_ids") or []))
                if doc_id in fine_doc_by_id
            ]
            for row in supplemental_v2_retrieved
        }
        evidence_rows_by_item = {
            item_id: evidence_rows_for_rule(
                rule_by_id[item_id], fine_by_ad[ad_id],
                keep_doc_ids=trigger_by_item.get(item_id, []))
            for item_id in candidate_ids
        }
        evidence_by_item = {
            item_id: top_rule_evidence(
                item_id,
                rule_vector_by_id=rule_vector_by_id,
                ad_fine_rows=evidence_rows_by_item[item_id],
                fine_vector_by_id=fine_vector_by_id,
                trigger_ids=trigger_by_item.get(item_id, []),
                k=args.evidence_per_rule,
                rule_text=judgment_rule_text(rule_by_id[item_id]),
                rule_label=(str(rule_by_id[item_id].get('title') or '')
                            if rule_by_id[item_id].get('source_sheet') == 'HWPX_TEMPLATE' else ''),
            )
            for item_id in candidate_ids
        }
        context_audit = {}
        for item_id, seed_ids in evidence_by_item.items():
            selected, source_audit = expand_source_context(
                seed_ids, evidence_rows_by_item[item_id], char_budget=args.context_char_budget)
            remaining = args.context_char_budget - source_audit["added_chars"]
            selected, facet_audit = supplement_evidence(
                selected, evidence_rows_by_item[item_id], rule_by_id[item_id], char_budget=remaining)
            remaining -= facet_audit["added_chars"]
            evidence_by_item[item_id], followup_audit = expand_source_context(
                selected, evidence_rows_by_item[item_id], char_budget=remaining)
            context_audit[item_id] = {**source_audit, "source_facets": facet_audit,
                "followup_context": followup_audit,
                "total_added_chars": source_audit["added_chars"] + facet_audit["added_chars"] + followup_audit["added_chars"]}
        # Keep a short advertisement complete without repeating 200+ region
        # records (including long evidence IDs and line refs) in every rule
        # request.  The transcript is context only; retrieved fine documents
        # remain the sole citable evidence window.
        full_ad_text = "\n".join(doc["text"] for doc in full_documents)
        use_full_ad = len(full_ad_text) <= args.full_ad_max_chars
        facts = deterministic_facts(fine_by_ad[ad_id], ad=ads[ad_id])
        category_to_rules: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
        for item_id in candidate_ids:
            rule = rule_by_id[item_id]
            family = str(rule.get("canonical_prompt_family") or "HYBRID_FACT_SEMANTIC")
            category_to_rules[(rule["category"], family)].append(rule)
        for category in ("PRESENCE", "PROHIBIT", "STYLE"):
          families = sorted(family for cat, family in category_to_rules if cat == category)
          for family in families:
            category_rules = sorted(category_to_rules[(category, family)], key=lambda row: row["item_id"])
            for offset in range(0, len(category_rules), args.batch_size):
                batch = category_rules[offset:offset + args.batch_size]
                model_rules = [model_rule_view(rule) for rule in batch]
                request_id = f"operational:{ad_id}:{category}:{family}:{offset // args.batch_size + 1}"
                batch_evidence_ids = list(dict.fromkeys(
                    evidence_id
                    for rule in batch
                    for evidence_id in evidence_by_item[rule["item_id"]]
                ))
                docs = [fine_doc_by_id[evidence_id] for evidence_id in batch_evidence_ids]
                payload = {
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "review_context": {"review_date": args.review_date.isoformat() if args.review_date else None,
                                       "date_basis": args.review_date_basis},
                    "routing": model_routing_view(route_context),
                    "parser_coverage": parser_coverage(ads[ad_id]),
                    "reading_quality": {
                        "scope": "LOCAL_REGIONS_ONLY",
                        "requires_review": bool(uncertain_ad_readings(ads[ad_id])),
                        "uncertain_region_count": len(uncertain_ad_readings(ads[ad_id])),
                        "global_scan_incomplete": parser_coverage(ads[ad_id]) == "PARTIAL",
                    },
                    "full_ad_text": full_ad_text if use_full_ad else None,
                    "documents": docs,
                    "evidence_scope": {
                        rule["item_id"]: {
                            "evidence_ids": evidence_by_item[rule["item_id"]],
                            "complete_ad_scan": complete_scan and (use_full_ad or
                                len(evidence_by_item[rule["item_id"]]) == len(fine_by_ad[ad_id])),
                        }
                        for rule in batch
                    },
                    "deterministic_facts": model_deterministic_facts(facts, docs),
                    "applicability_screen": {r["item_id"]: screened.get(r["item_id"]) for r in batch},
                    "external_input_assessment": {r["item_id"]: screened.get(r["item_id"]) for r in batch},
                    "canonical_confirmed_facts": {
                        r["item_id"]: confirmed_metadata_facts(
                            canonical_catalog.plans[r["item_id"]],
                            product_groups=candidate_groups,
                            template_id=confirmed_template_id,
                            routing=route_context,
                            layout_available=layout_available,
                        )
                        for r in batch
                        if canonical_catalog and r["item_id"] in canonical_catalog.plans
                    },
                    "rules": model_rules,
                }
                requests.append({
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "category": category,
                    "requested_item_ids": [row["item_id"] for row in batch],
                    "rule_bases": {
                        row["item_id"]: rule_basis_by_id[row["item_id"]]
                        for row in batch
                    },
                    "messages": [
                        {"role": "system", "content": OPERATIONAL_SYSTEM + "\n\n" + prompt_for_family(family)},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                })
                requested_pairs.update((ad_id, row["item_id"]) for row in batch)
        for deferred in [*deferred_input_rules, *applicability_pending]:
            definition = rule_by_id.get(deferred['item_id'], {})
            deferred.setdefault('title', definition.get('title', deferred['item_id']))
            deferred.setdefault('question', definition.get('question', ''))
            deferred.setdefault('rule_basis', rule_basis_by_id.get(deferred['item_id']))
        discovery_ads.append({
            "ad_id": ad_id,
            "source_ad_id": (ads[ad_id].get("document") or {}).get("parent_ad_id") or ad_id,
            "product_id": (ads[ad_id].get("document") or {}).get("product_id"),
            "product_name": (ads[ad_id].get("document") or {}).get("product_name"),
            "routing": route_context,
            "template_coverage": (
                audit_canonical_template_coverage(
                    canonical_catalog, template_value, candidate_ids,
                    [*deferred_input_rules, *applicability_pending],
                )
                if canonical_catalog and template_value else
                audit_template_coverage(
                    template_catalog, template_value, t_rules, candidate_ids,
                    [*deferred_input_rules, *applicability_pending]
                ) if template_catalog and template_value else None
            ),
            "parser_coverage": parser_coverage(ads[ad_id]),
            "evidence_context": context_audit,
            "counts": {
                "coarse": len(coarse_by_ad[ad_id]),
                "fine": len(fine_by_ad[ad_id]),
                "presence_and_style": len(media_enumerated),
                "template_candidates": len(template_candidates),
                "template_scope_deferred": len(template_scope_deferred),
                "deferred_template_rules": len(deferred_template_rules),
                "deferred_input_rules": len(deferred_input_rules),
                "mapped_v2_candidates": len(mapped_v2_audit),
                "general_v2_presence_candidates": len(general_v2_audit),
                "media_conditioned_v2_candidates": len(media_enumerated),
                "product_content_conditioned_v2_candidates": len(content_conditioned_v2),
                "supplemental_v2_candidates": len(supplemental_v2_audit),
                "visual_review_v2_candidates": len(supplemental_visual_review),
                "audit_only_v2_candidates": len(audit_only_v2),
                "prohibition_candidates": sum(
                    rule_by_id[row["item_id"]]["category"] == "PROHIBIT"
                    for row in supplemental_v2_audit
                ),
                "judgment_candidates": len(candidate_ids),
                "canonical_metadata_enumerated": (
                    len(canonical_selection.enumerate_ids) if canonical_selection else 0
                ),
                "canonical_retrieval_eligible": (
                    len(canonical_selection.retrieval_ids) if canonical_selection else 0
                ),
                "canonical_human_retrieval_eligible": (
                    len(canonical_selection.human_ids) if canonical_selection else 0
                ),
            },
            "presence_and_style": media_enumerated,
            "mapped_v2_candidates": mapped_v2_audit,
            "general_v2_presence_candidates": general_v2_audit,
            "media_conditioned_v2_candidates": media_enumerated,
            "product_content_conditioned_v2_candidates": content_conditioned_v2,
            "template_candidates": template_candidates,
            "template_scope_deferred": template_scope_deferred,
            "deferred_template_rule_ids": deferred_template_rules,
            "deferred_input_rules": deferred_input_rules,
            "excluded_applicability": excluded_applicability,
            "applicability_pending": applicability_pending,
            "supplemental_v2_candidates": supplemental_v2_audit,
            "visual_review_v2_candidates": supplemental_visual_review,
            "audit_only_v2_candidates": audit_only_v2,
            "query_context": query_context_audit,
            "candidate_budget": candidate_budget_audit,
            "canonical_selection": ({
                "enumerate_ids": list(canonical_selection.enumerate_ids),
                "retrieval_ids": list(canonical_selection.retrieval_ids),
                "human_ids": list(canonical_selection.human_ids),
                "excluded": list(canonical_selection.excluded),
                "pending": list(canonical_selection.pending),
                "confirmed_facts": list(canonical_selection.confirmed_facts),
            } if canonical_selection else None),
            "prohibition_candidates": [
                row for row in supplemental_v2_audit
                if rule_by_id[row["item_id"]]["category"] == "PROHIBIT"
            ],
        })

    discovery_path = args.output_dir / "01_discovery.json"
    request_path = args.output_dir / "02_judgment_requests.jsonl"
    response_path = args.output_dir / "03_judgment_responses.json"
    final_path = args.output_dir / "04_operational_results.json"
    write_json(discovery_path, {
        "schema_version": DISCOVERY_VERSION,
        "gold_visible": False,
        "policy": {
            "source_policy": args.source_policy,
            "unverified_routing": (
                "reject before model execution unless --allow-provisional-routing is explicitly set"
            ),
            "template_primary": "enumerate every structured rule in the confirmed detailed-product template",
            "mapped_v2_priority": (
                "disabled" if template_only else
                "template support and discovery audit only until separate v2 gold is available"
            ),
            "confirmed_media_v2": "disabled" if template_only else "enumerate source-authored rules for confirmed delivery media",
            "general_v2_presence": (
                "disabled" if template_only else
                "discovery audit only; excluded from judgment until source-authored scope is approved"
            ),
            "supplemental_v2": (
                "disabled" if template_only else
                "retrieve remaining product-scoped v2 rules for discovery audit only"
            ),
            "formal_execution_scope": (
                "TEMPLATE_PRIMARY + MEDIA_CONDITIONED_V2 + required relation dependencies"
            ),
            "supplemental_recall_guard": "preserve every discovery in audit; schedule none for judgment",
            "evidence": "rule-to-ad BGE-M3 plus full context for short advertisements",
            "applicability": (
                "experimental Gemma pre-screen enabled; final judgment independently confirms"
                if args.enable_applicability_screen
                else "source-defined input gate; applicability decided in final judgment"
            ),
            "absence": "a narrowed evidence window cannot prove absence; model must abstain",
            "required_inputs": (
                "TEXT rules are judged; PARTIAL rules retain unknown external requirements "
                "and cannot be wholly compliant; EXTERNAL rules are deferred"
            ),
            "labels": "trace/ranking only, never exclusion",
        },
        "ads": discovery_ads,
    })
    request_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in requests),
        encoding="utf-8",
    )
    request_bytes = request_path.stat().st_size
    freeze_path = args.output_dir / "FREEZE_BEFORE_PREDICTION.json"
    if template_catalog and sha256(args.template_hwpx) != template_catalog.document["source"]["sha256"]:
        raise RuntimeError("template source changed during request preparation")
    if template_catalog and args.template_methodology_dir:
        loaded_hashes = {
            source["filename"]: source["sha256"]
            for source in template_catalog.document["methodology"]["sources"]
        }
        current_hashes = {
            path.name: sha256(path)
            for path in methodology_workbooks(args.template_methodology_dir)
        }
        if current_hashes != loaded_hashes:
            raise RuntimeError("template methodology source changed during request preparation")
    write_json(freeze_path, freeze_manifest(
        args,
        request_path=request_path,
        discovery_path=discovery_path,
        ad_count=len(ads),
    ))
    runtime_metrics_path = args.output_dir / "08_runtime_metrics.json"
    pre_judgment_metrics = {
        "schema_version": "operational-runtime-metrics-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase": "pre_judgment_complete",
        "wall_seconds_before_judgment": round(time.perf_counter() - started_at, 3),
        "vectors": {
            "cache_dir": str(args.vector_cache_dir.resolve()),
            "rule_vectors_cached": rule_vectors_cached,
            "rule_embedding_seconds": round(rule_embedding_seconds, 3),
            "fine_vectors_cached": fine_vectors_cached,
            "fine_embedding_seconds": round(fine_embedding_seconds, 3),
        },
        "judgment_plan": {
            "logical_requests": len(requests),
            "requested_pairs": len(requested_pairs),
            "request_jsonl_bytes": request_bytes,
            "batch_size": args.batch_size,
            "max_tokens": args.judgment_max_tokens,
        },
    }
    write_json(runtime_metrics_path, pre_judgment_metrics)

    if not args.execute_judgment:
        print(json.dumps({
            "status": "frozen_requests_ready",
            "ads": len(ads),
            "requests": len(requests),
            "pairs": len(requested_pairs),
            "freeze": str(freeze_path),
        }, ensure_ascii=False, indent=2))
        return

    command = [
        sys.executable,
        str(ROOT / "tools/run_gemma_exhaustive_dgx.py"),
        "--input", str(request_path),
        "--output", str(response_path),
        "--model", args.model,
        "--workers", str(args.workers),
        "--max-tokens", str(args.judgment_max_tokens),
    ]
    if args.host:
        command.extend(["--host", args.host])
    if args.key:
        command.extend(["--key", str(args.key)])
    if args.resume_checkpoint:
        command.extend(["--resume-checkpoint", str(args.resume_checkpoint.resolve())])
    judgment_started_at = time.perf_counter()
    subprocess.run(command, cwd=ROOT, check=True)
    judgment_wall_seconds = time.perf_counter() - judgment_started_at
    model_results, result_sources = load_results([response_path])
    response_payload = json.loads(response_path.read_text(encoding="utf-8"))
    physical_rows = response_payload.get("rows") or []
    regulation_sha = regulation_source_sha
    template_sha = sha256(args.template_hwpx) if args.template_hwpx else None
    missing_pairs = sorted(requested_pairs - set(model_results))
    extra_pairs = sorted(set(model_results) - requested_pairs)
    if extra_pairs:
        raise RuntimeError(f"요청 밖 모델 결과가 있음: {extra_pairs[:10]}")
    final_ads = []
    discovery_by_ad = {row["ad_id"]: row for row in discovery_ads}
    for ad_id in sorted(ads):
        ad_results = apply_satisfaction_relations(
            {
                pair[1]: enforce_review_policy(model_results[pair])
                for pair in requested_pairs
                if pair[0] == ad_id and pair in model_results
            },
            rule_by_id,
        )
        candidates = []
        for pair in sorted((pair for pair in requested_pairs if pair[0] == ad_id), key=lambda pair: pair[1]):
            result = ad_results.get(pair[1])
            candidates.append({
                "item_id": pair[1],
                "rule_basis": rule_basis_by_id[pair[1]],
                "condition_contract": rule_by_id[pair[1]]["condition_contract"],
                **({"template_basis": rule_by_id[pair[1]]["template_basis"]}
                   if rule_by_id[pair[1]].get("template_basis") else {}),
                "status": "predicted" if result else "OUTPUT_FAILURE",
                "judgment": result,
                "source": result_sources.get(pair),
                "decision_trace": decision_trace(result, result_sources.get(pair)),
                "discovery_tier": discovery_tier_by_item[pair[1]],
            })
        visible, review_candidates, excluded = partition_operational_candidates(candidates)
        final_ads.append({
            "ad_id": discovery_by_ad[ad_id].get("source_ad_id") or ad_id,
            "scope_id": ad_id,
            "product_id": discovery_by_ad[ad_id].get("product_id"),
            "product_name": discovery_by_ad[ad_id].get("product_name"),
            "routing": discovery_by_ad[ad_id]["routing"],
            "parser_coverage": discovery_by_ad[ad_id]["parser_coverage"],
            "template_coverage": discovery_by_ad[ad_id].get("template_coverage"),
            "deferred_rules": [
                *discovery_by_ad[ad_id].get("template_scope_deferred", []),
                *discovery_by_ad[ad_id]["deferred_input_rules"],
                *discovery_by_ad[ad_id].get("applicability_pending", []),
                *(
                    {
                        "item_id": item_id,
                        "reason": "routing did not select this rule's template section",
                    }
                    for item_id in discovery_by_ad[ad_id]["deferred_template_rule_ids"]
                ),
            ],
            "candidates": visible,
            "review_candidates": review_candidates,
            "excluded_candidates": excluded,
        })
    final_result = {
        "schema_version": OPERATIONAL_RESULT_VERSION,
        "status": "silver_researcher_review_required",
        "freeze": str(freeze_path),
        "audit": {
            "model": {
                "requested": args.model,
                "returned": sorted({
                    str(row.get("model_returned")) for row in physical_rows
                    if isinstance(row, dict) and row.get("model_returned")
                }),
                "temperature": 0,
            },
            "search": {
                "engine": ("Template enumeration + BGE-M3 evidence retrieval" if template_only else
                           "Elasticsearch BM25 + BGE-M3 + RRF + bge-reranker-v2-m3"),
                "index": None if template_only else args.es_index,
                "rule_search_text_variant": args.rule_search_text_variant,
            },
            "rule_sources": {
                "policy": args.source_policy,
                "regulation_v2_sha256": regulation_sha,
                "template_hwpx_sha256": template_sha,
            },
            "guardrails": {
                "decision_policy": "LLM output is accepted only after deterministic fact, routing, evidence-scope and output-contract validation",
                "condition_contract_version": CONDITION_CONTRACT_VERSION,
                "condition_contract_rule_count": len(rule_by_id),
                "v2_source_rule_count": v2_condition_audit["source_rule_count"],
                "v2_compiled_contract_count": v2_condition_audit["compiled_rule_count"],
                "v2_missing_scope_count": v2_condition_audit["missing_scope_count"],
                "v2_condition_mode_counts": v2_condition_audit["mode_counts"],
                "policy_sha256": sha256(ROOT / "rag/judgment/policy.py"),
                "condition_contract_sha256": sha256(
                    ROOT / "rag/judgment/condition_contracts.py"
                ),
                "validator_sha256": sha256(ROOT / "tools/run_gemma_exhaustive_dgx.py"),
            },
        },
        "counts": {
            "ads": len(ads),
            "requested_pairs": len(requested_pairs),
            "predicted_pairs": len(model_results),
            "output_failures": len(missing_pairs),
        },
        "output_failure_pairs": [
            {
                "ad_id": discovery_by_ad[ad_id].get("source_ad_id") or ad_id,
                "scope_id": ad_id,
                "product_id": discovery_by_ad[ad_id].get("product_id"),
                "item_id": item_id,
            }
            for ad_id, item_id in missing_pairs
        ],
        "ads": final_ads,
    }
    validate_operational_result(final_result)
    write_json(final_path, final_result)
    from rag.judgment.runtime_metrics import save_completed_runtime_metrics
    save_completed_runtime_metrics(runtime_metrics_path, {
        **pre_judgment_metrics,
        "wall_seconds_total": round(time.perf_counter() - started_at, 3),
    }, physical_rows, round(judgment_wall_seconds, 3))
    print(json.dumps({
        "status": "completed",
        "output": str(final_path),
        "ads": len(ads),
        "predicted_pairs": len(model_results),
        "output_failures": len(missing_pairs),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
