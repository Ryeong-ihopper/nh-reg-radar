from rag.judgment.rule_relations import apply_satisfaction_relations, expand_relation_dependencies
import pytest


def result(verdict, *, reason="", refs=None):
    return {
        "item_id": "X",
        "applicability": "APPLICABLE",
        "verdict": verdict,
        "evidence_ids": [],
        "evidence_line_refs": refs or [],
        "requirement_checks": [{
            "obligation_ref": "O1",
            "status": "SATISFIED" if verdict == "COMPLIANT" else "UNDETERMINED",
            "finding_basis": "OBSERVED" if verdict == "COMPLIANT" else "UNKNOWN",
            "evidence_ids": [],
            "evidence_line_refs": refs or [],
            "reason": reason,
        }],
    }


def test_explicit_satisfied_if_relation_borrows_target_result_and_evidence():
    values = {
        "GENERAL": result("UNDETERMINED"),
        "DETAIL": result("COMPLIANT", reason="'연 0.2%'가 표시되어 있습니다.", refs=["L1"]),
    }
    rules = {"GENERAL": {"rule_relations": [{
        "relation_type": "SATISFIED_IF", "target_item_ids": ["DETAIL"],
        "join": "ANY", "description": "세부 수수료 표시 결과를 준용",
    }]}}
    resolved = apply_satisfaction_relations(values, rules)
    assert resolved["GENERAL"]["verdict"] == "COMPLIANT"
    assert resolved["GENERAL"]["evidence_line_refs"] == ["L1"]
    assert resolved["GENERAL"]["requirement_checks"][0]["reason"] == "'연 0.2%'가 표시되어 있습니다."
    assert resolved["GENERAL"]["relation_resolution"]["satisfied_target_item_ids"] == ["DETAIL"]
    assert values["GENERAL"]["verdict"] == "UNDETERMINED"


def test_relation_is_not_inferred_and_all_requires_every_target():
    values = {"GENERAL": result("UNDETERMINED"), "A": result("COMPLIANT"),
              "B": result("UNDETERMINED")}
    assert apply_satisfaction_relations(values, {})["GENERAL"]["verdict"] == "UNDETERMINED"
    rules = {"GENERAL": {"rule_relations": [{
        "relation_type": "SATISFIED_IF", "target_item_ids": ["A", "B"], "join": "ALL",
    }]}}
    assert apply_satisfaction_relations(values, rules)["GENERAL"]["verdict"] == "UNDETERMINED"


def test_relation_targets_are_added_to_candidates_transitively():
    rules = {
        "A": {"rule_relations": [{"target_item_ids": ["B"]}]},
        "B": {"rule_relations": [{"target_item_ids": ["C"]}]},
        "C": {},
    }
    assert expand_relation_dependencies(["A"], rules) == ["A", "B", "C"]


def test_relation_resolution_is_independent_of_rule_iteration_order():
    rules = {"A": {"rule_relations": [{"relation_type": "SATISFIED_IF", "target_item_ids": ["B"]}]},
             "B": {"rule_relations": [{"relation_type": "SATISFIED_IF", "target_item_ids": ["C"]}]}, "C": {}}
    values = {"A": result("UNDETERMINED"), "B": result("UNDETERMINED"),
              "C": result("COMPLIANT", refs=["source-line"], reason="source statement")}
    resolved = apply_satisfaction_relations(values, rules)
    assert resolved["A"]["verdict"] == "COMPLIANT"
    assert resolved["A"]["evidence_line_refs"] == ["source-line"]
    assert values["A"]["verdict"] == "UNDETERMINED"


def test_cycles_and_unknown_targets_do_not_silently_resolve():
    cycle = {"A": {"rule_relations": [{"target_item_ids": ["B"]}]},
             "B": {"rule_relations": [{"target_item_ids": ["A"]}]}}
    with pytest.raises(ValueError, match="cyclic"):
        expand_relation_dependencies(["A"], cycle)
    with pytest.raises(ValueError, match="cyclic"):
        apply_satisfaction_relations({"A": result("UNDETERMINED"), "B": result("COMPLIANT")}, cycle)
    with pytest.raises(ValueError, match="unknown"):
        expand_relation_dependencies(["A"], {"A": cycle["A"]})


def test_relation_does_not_bypass_scope_or_drop_independent_obligations():
    relation = {"relation_type": "SATISFIED_IF", "target_item_ids": ["B"]}
    rules = {"A": {"rule_relations": [relation]}}
    for scope in ("NOT_APPLICABLE", "UNDETERMINED"):
        values = {"A": {**result("UNDETERMINED"), "applicability": scope}, "B": result("COMPLIANT")}
        assert apply_satisfaction_relations(values, rules)["A"] == values["A"]
    rules["A"]["condition_contract"] = {"obligation_checks": [{"obligation_id": "O1"}, {"obligation_id": "O2"}]}
    values = {"A": result("UNDETERMINED"), "B": result("COMPLIANT")}
    assert apply_satisfaction_relations(values, rules)["A"] == values["A"]
