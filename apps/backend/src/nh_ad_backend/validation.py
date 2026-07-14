"""M7 validation datasets and deterministic KPI evaluations.

The database is the runtime source of truth.  Git fixtures may exercise the
same pure scoring and snapshot helpers, but they are never loaded by runtime
code and no provider/network adapter is used here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from threading import RLock
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from nh_ad_backend.domain import AuditEvent, CurrentUser
from nh_ad_backend.results import ResultItem, ResultService
from nh_ad_backend.reviews import Review, ReviewService
from nh_ad_backend.services import ServiceError


METRIC_ORDER = (
    "REQUIRED_PHRASE_ACCURACY",
    "MISLEADING_EXPRESSION_ACCURACY",
    "EVIDENCE_PRECISION",
    "HUMAN_AGREEMENT_RATE",
)
METRIC_NAMES = {
    "REQUIRED_PHRASE_ACCURACY": "필수 문구 검토 정확도",
    "MISLEADING_EXPRESSION_ACCURACY": "위험 표현 검토 정확도",
    "EVIDENCE_PRECISION": "근거 매칭 적정성",
    "HUMAN_AGREEMENT_RATE": "담당자 판단 일치율",
}
METRIC_TARGETS = {
    "REQUIRED_PHRASE_ACCURACY": Decimal("80"),
    "MISLEADING_EXPRESSION_ACCURACY": Decimal("75"),
    "EVIDENCE_PRECISION": Decimal("85"),
    "HUMAN_AGREEMENT_RATE": Decimal("75"),
}
EXCLUDE_REASON_CODES = frozenset(
    {
        "OCR_UNREADABLE",
        "PRODUCT_CONDITION_AMBIGUOUS",
        "REFERENCE_NOT_PROVIDED",
        "SOURCE_FILE_CORRUPTED",
        "LABEL_UNCLEAR",
        "DUPLICATE_SAMPLE",
        "OUT_OF_SCOPE",
    }
)
VALIDATION_ROLES = frozenset({"COMPLIANCE_REVIEWER", "STANDARD_MANAGER", "SYSTEM_ADMIN"})


@dataclass(frozen=True)
class ValidationDataset:
    dataset_id: str
    dataset_name: str
    product_group: str
    advertisement_type: str
    dataset_version: int
    is_excluded: bool
    created_at: datetime
    created_by: str
    advertisement_id: str | None = None
    sample_file_id: str | None = None
    product_condition_file_id: str | None = None
    human_review_comment: str | None = None
    label_json: dict[str, object] | None = None
    exclude_reason_code: str | None = None
    exclude_reason: str | None = None
    excluded_by: str | None = None
    excluded_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


@dataclass(frozen=True)
class ValidationJudgment:
    judgment_id: str
    dataset_id: str
    target_text: str
    review_type: str
    expected_status: str
    judgment_version: int
    judged_by: str
    judged_at: datetime
    risk_level: str | None = None
    evidence_comment: str | None = None
    is_excluded: bool = False
    exclude_reason_code: str | None = None
    exclude_reason: str | None = None
    excluded_by: str | None = None
    excluded_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None


@dataclass(frozen=True)
class EvaluationMetric:
    evaluation_metric_id: UUID
    metric_code: str
    metric_name: str
    score: Decimal | None
    target_score: Decimal
    achieved: bool
    numerator: Decimal
    denominator: int
    excluded_count: int
    partial_count: int
    not_applicable: bool
    detail_json: dict[str, object]


@dataclass(frozen=True)
class ValidationEvaluation:
    evaluation_id: str
    evaluation_status: str
    dataset_ids: tuple[str, ...]
    exclude_invalid_samples: bool
    review_selection_policy: str
    total_sample_count: int
    excluded_sample_count: int
    exclusion_summary: tuple[dict[str, object], ...]
    dataset_snapshot: tuple[dict[str, object], ...]
    judgment_snapshot: tuple[dict[str, object], ...]
    exclusion_snapshot: tuple[dict[str, object], ...]
    ai_result_snapshot: tuple[dict[str, object], ...]
    version_snapshot: dict[str, object]
    evaluation_policy_snapshot: dict[str, object]
    snapshot_hash: str
    snapshot_created_at: datetime
    created_at: datetime
    created_by: str
    metrics: tuple[EvaluationMetric, ...]


class ValidationRepository(Protocol):
    def create_dataset(self, dataset: ValidationDataset) -> None: ...
    def list_datasets(self, page: int, size: int) -> tuple[list[ValidationDataset], int]: ...
    def get_dataset(self, dataset_id: str) -> ValidationDataset | None: ...
    def add_judgments(self, judgments: Iterable[ValidationJudgment]) -> None: ...
    def next_judgment_version(self, dataset_id: str, target_text: str, review_type: str) -> int: ...
    def list_judgments(self, dataset_id: str) -> list[ValidationJudgment]: ...
    def save_evaluation(self, evaluation: ValidationEvaluation) -> None: ...
    def get_evaluation(self, evaluation_id: str) -> ValidationEvaluation | None: ...


class InMemoryValidationRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._datasets: dict[str, ValidationDataset] = {}
        self._judgments: list[ValidationJudgment] = []
        self._evaluations: dict[str, ValidationEvaluation] = {}

    def create_dataset(self, dataset: ValidationDataset) -> None:
        with self._lock:
            if dataset.dataset_id in self._datasets:
                raise ValueError("DATASET_ALREADY_EXISTS")
            self._datasets[dataset.dataset_id] = copy.deepcopy(dataset)

    def list_datasets(self, page: int, size: int) -> tuple[list[ValidationDataset], int]:
        with self._lock:
            values = sorted(self._datasets.values(), key=lambda item: item.created_at, reverse=True)
            return copy.deepcopy(values[page * size : (page + 1) * size]), len(values)

    def get_dataset(self, dataset_id: str) -> ValidationDataset | None:
        with self._lock:
            value = self._datasets.get(dataset_id)
            return copy.deepcopy(value) if value else None

    def add_judgments(self, judgments: Iterable[ValidationJudgment]) -> None:
        with self._lock:
            self._judgments.extend(copy.deepcopy(list(judgments)))

    def next_judgment_version(self, dataset_id: str, target_text: str, review_type: str) -> int:
        with self._lock:
            versions = [
                item.judgment_version
                for item in self._judgments
                if item.dataset_id == dataset_id
                and item.target_text == target_text
                and item.review_type == review_type
            ]
            return max(versions, default=0) + 1

    def list_judgments(self, dataset_id: str) -> list[ValidationJudgment]:
        with self._lock:
            latest: dict[tuple[str, str], ValidationJudgment] = {}
            for item in self._judgments:
                if item.dataset_id != dataset_id:
                    continue
                key = (item.target_text, item.review_type)
                if key not in latest or latest[key].judgment_version < item.judgment_version:
                    latest[key] = item
            return copy.deepcopy(sorted(latest.values(), key=lambda item: item.judgment_id))

    def save_evaluation(self, evaluation: ValidationEvaluation) -> None:
        with self._lock:
            if evaluation.evaluation_id in self._evaluations:
                raise ValueError("EVALUATION_ALREADY_EXISTS")
            self._evaluations[evaluation.evaluation_id] = copy.deepcopy(evaluation)

    def get_evaluation(self, evaluation_id: str) -> ValidationEvaluation | None:
        with self._lock:
            value = self._evaluations.get(evaluation_id)
            return copy.deepcopy(value) if value else None


class PostgresValidationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_dataset(self, dataset: ValidationDataset) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO validation.validation_datasets
                    (dataset_id,dataset_name,advertisement_id,product_group,advertisement_type,
                     sample_file_id,product_condition_file_id,human_review_comment,label_json,
                     dataset_version,is_excluded,exclude_reason_code,exclude_reason,excluded_by,
                     excluded_at,created_at,created_by,updated_at,updated_by)
                    VALUES (:dataset_id,:dataset_name,:advertisement_id,:product_group,
                     :advertisement_type,:sample_file_id,:product_condition_file_id,
                     :human_review_comment,CAST(:label_json AS jsonb),:dataset_version,:is_excluded,
                     :exclude_reason_code,:exclude_reason,:excluded_by,:excluded_at,:created_at,
                     :created_by,:updated_at,:updated_by)
                """),
                {**asdict(dataset), "label_json": _json(dataset.label_json)},
            )

    def list_datasets(self, page: int, size: int) -> tuple[list[ValidationDataset], int]:
        with self._engine.connect() as connection:
            total = int(
                connection.execute(
                    text("SELECT count(*) FROM validation.validation_datasets")
                ).scalar_one()
            )
            rows = connection.execute(
                text("""
                    SELECT * FROM validation.validation_datasets
                    ORDER BY created_at DESC,dataset_id LIMIT :size OFFSET :offset
                """),
                {"size": size, "offset": page * size},
            ).mappings()
            return [self._dataset(dict(row)) for row in rows], total

    def get_dataset(self, dataset_id: str) -> ValidationDataset | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM validation.validation_datasets WHERE dataset_id=:id"),
                    {"id": dataset_id},
                )
                .mappings()
                .first()
            )
            return self._dataset(dict(row)) if row else None

    def add_judgments(self, judgments: Iterable[ValidationJudgment]) -> None:
        with self._engine.begin() as connection:
            for item in judgments:
                connection.execute(
                    text("""
                        INSERT INTO validation.validation_judgments
                        (judgment_id,dataset_id,target_text,review_type,expected_status,risk_level,
                         evidence_comment,is_excluded,exclude_reason_code,exclude_reason,excluded_by,
                         excluded_at,judgment_version,judged_by,judged_at,updated_at,updated_by)
                        VALUES (:judgment_id,:dataset_id,:target_text,:review_type,:expected_status,
                         :risk_level,:evidence_comment,:is_excluded,:exclude_reason_code,
                         :exclude_reason,:excluded_by,:excluded_at,:judgment_version,:judged_by,
                         :judged_at,:updated_at,:updated_by)
                    """),
                    asdict(item),
                )

    def next_judgment_version(self, dataset_id: str, target_text: str, review_type: str) -> int:
        with self._engine.connect() as connection:
            current = connection.execute(
                text("""
                    SELECT max(judgment_version) FROM validation.validation_judgments
                    WHERE dataset_id=:dataset_id AND target_text=:target_text
                      AND review_type=:review_type
                """),
                {
                    "dataset_id": dataset_id,
                    "target_text": target_text,
                    "review_type": review_type,
                },
            ).scalar_one()
            return int(current or 0) + 1

    def list_judgments(self, dataset_id: str) -> list[ValidationJudgment]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT DISTINCT ON (target_text,review_type) *
                    FROM validation.validation_judgments WHERE dataset_id=:dataset_id
                    ORDER BY target_text,review_type,judgment_version DESC,judged_at DESC
                """),
                {"dataset_id": dataset_id},
            ).mappings()
            return [self._judgment(dict(row)) for row in rows]

    def save_evaluation(self, evaluation: ValidationEvaluation) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO validation.evaluations
                    (evaluation_id,evaluation_status,dataset_ids,exclude_invalid_samples,
                     review_selection_policy,total_sample_count,excluded_sample_count,
                     exclusion_summary_json,dataset_snapshot_json,judgment_snapshot_json,
                     exclusion_snapshot_json,ai_result_snapshot_json,version_snapshot_json,
                     evaluation_policy_snapshot_json,snapshot_hash,snapshot_created_at,created_at,
                     created_by)
                    VALUES (:evaluation_id,:evaluation_status,CAST(:dataset_ids AS jsonb),
                     :exclude_invalid_samples,:review_selection_policy,:total_sample_count,
                     :excluded_sample_count,CAST(:exclusion_summary AS jsonb),
                     CAST(:dataset_snapshot AS jsonb),CAST(:judgment_snapshot AS jsonb),
                     CAST(:exclusion_snapshot AS jsonb),CAST(:ai_result_snapshot AS jsonb),
                     CAST(:version_snapshot AS jsonb),CAST(:policy_snapshot AS jsonb),
                     :snapshot_hash,:snapshot_created_at,:created_at,:created_by)
                """),
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "evaluation_status": evaluation.evaluation_status,
                    "dataset_ids": _json(evaluation.dataset_ids),
                    "exclude_invalid_samples": evaluation.exclude_invalid_samples,
                    "review_selection_policy": evaluation.review_selection_policy,
                    "total_sample_count": evaluation.total_sample_count,
                    "excluded_sample_count": evaluation.excluded_sample_count,
                    "exclusion_summary": _json(evaluation.exclusion_summary),
                    "dataset_snapshot": _json(evaluation.dataset_snapshot),
                    "judgment_snapshot": _json(evaluation.judgment_snapshot),
                    "exclusion_snapshot": _json(evaluation.exclusion_snapshot),
                    "ai_result_snapshot": _json(evaluation.ai_result_snapshot),
                    "version_snapshot": _json(evaluation.version_snapshot),
                    "policy_snapshot": _json(evaluation.evaluation_policy_snapshot),
                    "snapshot_hash": evaluation.snapshot_hash,
                    "snapshot_created_at": evaluation.snapshot_created_at,
                    "created_at": evaluation.created_at,
                    "created_by": evaluation.created_by,
                },
            )
            for metric in evaluation.metrics:
                connection.execute(
                    text("""
                        INSERT INTO validation.evaluation_metrics
                        (evaluation_metric_id,evaluation_id,metric_code,metric_name,score,
                         target_score,achieved,numerator,denominator,excluded_count,partial_count,
                         not_applicable,detail_json)
                        VALUES (:evaluation_metric_id,:evaluation_id,:metric_code,:metric_name,
                         :score,:target_score,:achieved,:numerator,:denominator,:excluded_count,
                         :partial_count,:not_applicable,CAST(:detail_json AS jsonb))
                    """),
                    {
                        **asdict(metric),
                        "evaluation_id": evaluation.evaluation_id,
                        "detail_json": _json(metric.detail_json),
                    },
                )

    def get_evaluation(self, evaluation_id: str) -> ValidationEvaluation | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM validation.evaluations WHERE evaluation_id=:id"),
                    {"id": evaluation_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            metric_rows = connection.execute(
                text("""
                    SELECT * FROM validation.evaluation_metrics WHERE evaluation_id=:id
                    ORDER BY CASE metric_code
                      WHEN 'REQUIRED_PHRASE_ACCURACY' THEN 1
                      WHEN 'MISLEADING_EXPRESSION_ACCURACY' THEN 2
                      WHEN 'EVIDENCE_PRECISION' THEN 3 ELSE 4 END
                """),
                {"id": evaluation_id},
            ).mappings()
            metrics = tuple(
                EvaluationMetric(
                    item["evaluation_metric_id"],
                    item["metric_code"],
                    item["metric_name"],
                    Decimal(item["score"]) if item["score"] is not None else None,
                    Decimal(item["target_score"]),
                    item["achieved"],
                    Decimal(item["numerator"]),
                    item["denominator"],
                    item["excluded_count"],
                    item["partial_count"],
                    item["not_applicable"],
                    dict(item["detail_json"] or {}),
                )
                for item in metric_rows
            )
            return ValidationEvaluation(
                row["evaluation_id"],
                row["evaluation_status"],
                tuple(row["dataset_ids"]),
                row["exclude_invalid_samples"],
                row["review_selection_policy"],
                row["total_sample_count"],
                row["excluded_sample_count"],
                tuple(row["exclusion_summary_json"] or ()),
                tuple(row["dataset_snapshot_json"]),
                tuple(row["judgment_snapshot_json"]),
                tuple(row["exclusion_snapshot_json"]),
                tuple(row["ai_result_snapshot_json"]),
                dict(row["version_snapshot_json"]),
                dict(row["evaluation_policy_snapshot_json"]),
                row["snapshot_hash"],
                row["snapshot_created_at"],
                row["created_at"],
                row["created_by"],
                metrics,
            )

    @staticmethod
    def _dataset(row: Mapping[str, Any]) -> ValidationDataset:
        return ValidationDataset(
            dataset_id=str(row["dataset_id"]),
            dataset_name=str(row["dataset_name"]),
            product_group=str(row["product_group"]),
            advertisement_type=str(row["advertisement_type"]),
            dataset_version=int(row["dataset_version"]),
            is_excluded=bool(row["is_excluded"]),
            created_at=row["created_at"],
            created_by=str(row["created_by"]),
            advertisement_id=_optional_str(row["advertisement_id"]),
            sample_file_id=_optional_str(row["sample_file_id"]),
            product_condition_file_id=_optional_str(row["product_condition_file_id"]),
            human_review_comment=_optional_str(row["human_review_comment"]),
            label_json=dict(row["label_json"]) if row["label_json"] else None,
            exclude_reason_code=_optional_str(row["exclude_reason_code"]),
            exclude_reason=_optional_str(row["exclude_reason"]),
            excluded_by=_optional_str(row["excluded_by"]),
            excluded_at=row["excluded_at"],
            updated_at=row["updated_at"],
            updated_by=_optional_str(row["updated_by"]),
        )

    @staticmethod
    def _judgment(row: Mapping[str, Any]) -> ValidationJudgment:
        return ValidationJudgment(
            judgment_id=str(row["judgment_id"]),
            dataset_id=str(row["dataset_id"]),
            target_text=str(row["target_text"]),
            review_type=str(row["review_type"]),
            expected_status=str(row["expected_status"]),
            judgment_version=int(row["judgment_version"]),
            judged_by=str(row["judged_by"]),
            judged_at=row["judged_at"],
            risk_level=_optional_str(row["risk_level"]),
            evidence_comment=_optional_str(row["evidence_comment"]),
            is_excluded=bool(row["is_excluded"]),
            exclude_reason_code=_optional_str(row["exclude_reason_code"]),
            exclude_reason=_optional_str(row["exclude_reason"]),
            excluded_by=_optional_str(row["excluded_by"]),
            excluded_at=row["excluded_at"],
            updated_at=row["updated_at"],
            updated_by=_optional_str(row["updated_by"]),
        )


def canonical_snapshot_hash(snapshot: object) -> str:
    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def calculate_metrics(cases: Iterable[Mapping[str, object]]) -> tuple[EvaluationMetric, ...]:
    by_metric: dict[str, list[Mapping[str, object]]] = {code: [] for code in METRIC_ORDER}
    for case in cases:
        code = str(case.get("metricCode", ""))
        if code in by_metric:
            by_metric[code].append(case)
    metrics: list[EvaluationMetric] = []
    for code in METRIC_ORDER:
        numerator = Decimal("0")
        denominator = excluded_count = partial_count = 0
        details: list[dict[str, object]] = []
        for case in by_metric[code]:
            excluded = bool(case.get("excluded")) and bool(case.get("exclusionApproved", True))
            if excluded:
                excluded_count += 1
                details.append({"caseId": case.get("caseId"), "excluded": True})
                continue
            score = Decimal(str(case.get("matchScore", 0)))
            if score not in {Decimal("0"), Decimal("0.5"), Decimal("1")}:  # pragma: no cover
                raise ValueError("INVALID_MATCH_SCORE")
            denominator += 1
            numerator += score
            partial_count += score == Decimal("0.5")
            details.append(
                {"caseId": case.get("caseId"), "excluded": False, "matchScore": str(score)}
            )
        not_applicable = denominator == 0
        score_value = (
            None
            if not_applicable
            else (numerator / Decimal(denominator) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        target = METRIC_TARGETS[code]
        metrics.append(
            EvaluationMetric(
                uuid4(),
                code,
                METRIC_NAMES[code],
                score_value,
                target,
                False
                if not_applicable
                else bool(score_value is not None and score_value >= target),
                numerator,
                denominator,
                excluded_count,
                partial_count,
                not_applicable,
                {"cases": details},
            )
        )
    return tuple(metrics)


class ValidationService:
    def __init__(
        self,
        repository: ValidationRepository,
        *,
        reviews: ReviewService | None = None,
        results: ResultService | None = None,
        now: Callable[[], datetime] | None = None,
        identifier: Callable[[str], str] | None = None,
        audit_sink: Callable[[AuditEvent], None] | None = None,
    ) -> None:
        self.repository = repository
        self.reviews = reviews
        self.results = results
        self._now = now or (lambda: datetime.now(UTC))
        self._identifier = identifier or (lambda prefix: f"{prefix}-{secrets.token_hex(8).upper()}")
        self._audit_sink = audit_sink or (lambda _event: None)

    def create_dataset(
        self,
        actor: CurrentUser,
        *,
        dataset_name: str,
        product_group: str,
        advertisement_type: str,
        advertisement_file: Mapping[str, object],
        product_condition_file: Mapping[str, object] | None,
        human_review_comment: str | None,
        label_json: str | None,
        excluded: bool,
        exclude_reason_code: str | None,
        exclude_reason_detail: str | None,
        trace_id: str,
    ) -> ValidationDataset:
        self._authorize(actor, "VALIDATION_DATASET_CREATE", trace_id)
        if not dataset_name.strip() or not product_group.strip() or not advertisement_type.strip():
            raise ServiceError(400, "BAD_REQUEST", "필수 입력값을 확인해 주세요.")
        if not advertisement_file.get("content"):
            raise ServiceError(400, "BAD_REQUEST", "검증 광고 파일이 필요합니다.")
        self._validate_exclusion(excluded, exclude_reason_code)
        try:
            labels = json.loads(label_json) if label_json else {}
        except json.JSONDecodeError as exc:
            raise ServiceError(400, "BAD_REQUEST", "labelJson 값을 확인해 주세요.") from exc
        if not isinstance(labels, dict):
            raise ServiceError(400, "BAD_REQUEST", "labelJson 값을 확인해 주세요.")
        labels = copy.deepcopy(labels)
        labels["_artifacts"] = {
            "advertisement": _artifact_metadata(advertisement_file),
            "productCondition": (
                _artifact_metadata(product_condition_file) if product_condition_file else None
            ),
        }
        now = self._now()
        dataset = ValidationDataset(
            dataset_id=self._identifier("DATASET"),
            dataset_name=dataset_name.strip(),
            product_group=product_group,
            advertisement_type=advertisement_type,
            dataset_version=1,
            is_excluded=excluded,
            created_at=now,
            created_by=actor.user_id,
            human_review_comment=human_review_comment,
            label_json=labels,
            exclude_reason_code=exclude_reason_code if excluded else None,
            exclude_reason=exclude_reason_detail if excluded else None,
            excluded_by=actor.user_id if excluded else None,
            excluded_at=now if excluded else None,
        )
        try:
            self.repository.create_dataset(dataset)
        except ValueError as exc:
            raise ServiceError(409, "CONFLICT", "검증 데이터셋을 저장할 수 없습니다.") from exc
        self._audit(
            actor, "VALIDATION_DATASET_CREATE", "SUCCESS", None, dataset.dataset_id, trace_id
        )
        return dataset

    def list_datasets(
        self, actor: CurrentUser, page: int, size: int, trace_id: str
    ) -> tuple[list[ValidationDataset], int]:
        self._authorize(actor, "VALIDATION_DATASET_LIST", trace_id)
        values = self.repository.list_datasets(page, size)
        self._audit(actor, "VALIDATION_DATASET_LIST", "SUCCESS", None, None, trace_id)
        return values

    def create_judgments(
        self,
        actor: CurrentUser,
        dataset_id: str,
        values: Iterable[Mapping[str, object]],
        trace_id: str,
    ) -> list[ValidationJudgment]:
        self._authorize(actor, "VALIDATION_JUDGMENT_CREATE", trace_id)
        if self.repository.get_dataset(dataset_id) is None:
            raise ServiceError(404, "NOT_FOUND", "검증 데이터셋을 찾을 수 없습니다.")
        now = self._now()
        judgments: list[ValidationJudgment] = []
        for value in values:
            target_text = str(value.get("targetText", "")).strip()
            review_type = str(value.get("reviewType", "")).strip()
            expected_status = str(value.get("expectedStatus", "")).strip()
            excluded = bool(value.get("excluded", False))
            reason_code = _optional_str(value.get("excludeReasonCode"))
            if not target_text or not review_type or not expected_status:
                raise ServiceError(400, "BAD_REQUEST", "담당자 판단 필수값을 확인해 주세요.")
            self._validate_exclusion(excluded, reason_code)
            judgments.append(
                ValidationJudgment(
                    self._identifier("JUDG"),
                    dataset_id,
                    target_text,
                    review_type,
                    expected_status,
                    self.repository.next_judgment_version(dataset_id, target_text, review_type),
                    actor.user_id,
                    now,
                    _optional_str(value.get("riskLevel")),
                    _optional_str(value.get("comment")),
                    excluded,
                    reason_code if excluded else None,
                    _optional_str(value.get("excludeReasonDetail")) if excluded else None,
                    actor.user_id if excluded else None,
                    now if excluded else None,
                )
            )
        if not judgments:
            raise ServiceError(400, "BAD_REQUEST", "담당자 판단을 하나 이상 등록해 주세요.")
        self.repository.add_judgments(judgments)
        self._audit(actor, "VALIDATION_JUDGMENT_CREATE", "SUCCESS", None, dataset_id, trace_id)
        return judgments

    def create_evaluation(
        self,
        actor: CurrentUser,
        *,
        dataset_ids: Iterable[str],
        metrics: Iterable[str],
        exclude_invalid_samples: bool,
        review_selection_policy: str,
        trace_id: str,
    ) -> ValidationEvaluation:
        self._authorize(actor, "VALIDATION_EVALUATION_CREATE", trace_id)
        ids = tuple(dict.fromkeys(dataset_ids))
        requested_metrics = tuple(dict.fromkeys(metrics))
        if (
            not ids
            or not requested_metrics
            or any(code not in METRIC_ORDER for code in requested_metrics)
        ):
            raise ServiceError(400, "BAD_REQUEST", "평가 대상과 KPI를 확인해 주세요.")
        if review_selection_policy != "LATEST_COMPLETED":
            raise ServiceError(400, "BAD_REQUEST", "지원하지 않는 검토 선택 정책입니다.")
        datasets: list[ValidationDataset] = []
        judgments: list[ValidationJudgment] = []
        ai_snapshots: list[dict[str, object]] = []
        cases: list[dict[str, object]] = []
        for dataset_id in ids:
            dataset = self.repository.get_dataset(dataset_id)
            if dataset is None:
                raise ServiceError(
                    409, "EVALUATION_INPUT_NOT_READY", "평가 데이터셋을 찾을 수 없습니다."
                )
            datasets.append(dataset)
            current_judgments = self.repository.list_judgments(dataset_id)
            judgments.extend(current_judgments)
            review, items = self._latest_result(dataset)
            if review is not None:
                ai_snapshots.append(_review_snapshot(review, items))
            cases.extend(self._cases(dataset, current_judgments, items, exclude_invalid_samples))
        exclusions = _exclusion_snapshots(cases)
        exclusion_counts = Counter(
            str(value["excludeReasonCode"])
            for value in exclusions
            if value.get("excluded") and value.get("excludeReasonCode")
        )
        exclusion_summary = tuple(
            {"excludeReasonCode": code, "count": count}
            for code, count in sorted(exclusion_counts.items())
        )
        metric_values = calculate_metrics(cases)
        dataset_snapshot = tuple(_dataset_snapshot(value) for value in datasets)
        judgment_snapshot = tuple(_judgment_snapshot(value) for value in judgments)
        version_snapshot = _version_snapshot(ai_snapshots)
        policy_snapshot: dict[str, object] = {
            "excludeInvalidSamples": exclude_invalid_samples,
            "kpiPolicyVersion": "m7-kpi-v1",
            "matchScores": ["1.0", "0.5", "0"],
            "reviewSelectionPolicy": review_selection_policy,
            "requestedMetrics": list(requested_metrics),
            "targets": {code: str(METRIC_TARGETS[code]) for code in sorted(METRIC_TARGETS)},
        }
        canonical_input = {
            "aiResults": ai_snapshots,
            "datasets": list(dataset_snapshot),
            "exclusions": list(exclusions),
            "judgments": list(judgment_snapshot),
            "policy": policy_snapshot,
            "versions": version_snapshot,
        }
        now = self._now()
        evaluation = ValidationEvaluation(
            self._identifier("EVAL"),
            "COMPLETED",
            ids,
            exclude_invalid_samples,
            review_selection_policy,
            len(datasets),
            sum(1 for dataset in datasets if dataset.is_excluded),
            exclusion_summary,
            dataset_snapshot,
            judgment_snapshot,
            exclusions,
            tuple(ai_snapshots),
            version_snapshot,
            policy_snapshot,
            canonical_snapshot_hash(canonical_input),
            now,
            now,
            actor.user_id,
            metric_values,
        )
        try:
            self.repository.save_evaluation(evaluation)
        except ValueError as exc:
            raise ServiceError(409, "CONFLICT", "평가 결과를 저장할 수 없습니다.") from exc
        self._audit(
            actor,
            "VALIDATION_EVALUATION_CREATE",
            "SUCCESS",
            None,
            evaluation.evaluation_id,
            trace_id,
        )
        return evaluation

    def get_evaluation(
        self, actor: CurrentUser, evaluation_id: str, trace_id: str
    ) -> ValidationEvaluation:
        self._authorize(actor, "VALIDATION_EVALUATION_READ", trace_id)
        value = self.repository.get_evaluation(evaluation_id)
        if value is None:
            raise ServiceError(404, "NOT_FOUND", "평가 결과를 찾을 수 없습니다.")
        self._audit(actor, "VALIDATION_EVALUATION_READ", "SUCCESS", None, evaluation_id, trace_id)
        return value

    def _latest_result(
        self, dataset: ValidationDataset
    ) -> tuple[Review | None, tuple[ResultItem, ...]]:
        if self.reviews is None or self.results is None or dataset.advertisement_id is None:
            return None, ()
        completed = [
            item
            for item in self.reviews.repository.list(dataset.advertisement_id)
            if item.completed_at is not None and item.status == "REVIEW_COMPLETED"
        ]
        if not completed:
            return None, ()
        review = max(
            completed,
            key=lambda item: (
                item.completed_at or datetime.min.replace(tzinfo=UTC),
                item.review_round,
            ),
        )
        return review, tuple(self.results.repository.list_items(review.review_id))

    @staticmethod
    def _cases(
        dataset: ValidationDataset,
        judgments: Iterable[ValidationJudgment],
        result_items: tuple[ResultItem, ...],
        exclude_invalid_samples: bool,
    ) -> list[dict[str, object]]:
        label_cases = (dataset.label_json or {}).get("cases")
        if isinstance(label_cases, list):
            label_values = [
                copy.deepcopy(value) for value in label_cases if isinstance(value, dict)
            ]
            for value in label_values:
                approved = bool(value.get("exclusionApproved", value.get("excluded", False)))
                value["excluded"] = (
                    bool(value.get("excluded")) and approved and exclude_invalid_samples
                )
            return label_values
        item_by_key = {(item.review_type, item.target_text): item for item in result_items}
        values: list[dict[str, object]] = []
        for judgment in judgments:
            result = item_by_key.get((judgment.review_type, judgment.target_text))
            score = _status_score(
                judgment.expected_status, result.result_status if result else None
            )
            excluded = (
                exclude_invalid_samples
                and judgment.is_excluded
                and bool(
                    judgment.exclude_reason_code and judgment.excluded_by and judgment.excluded_at
                )
            )
            base = {
                "caseId": judgment.judgment_id,
                "matchScore": str(score),
                "excluded": excluded,
                "exclusionApproved": excluded,
                "excludeReasonCode": judgment.exclude_reason_code,
                "aiError": result is None or score == 0,
            }
            code = {
                "REQUIRED_PHRASE": "REQUIRED_PHRASE_ACCURACY",
                "MISLEADING_EXPRESSION": "MISLEADING_EXPRESSION_ACCURACY",
            }.get(judgment.review_type)
            if code:
                values.append({**base, "metricCode": code})
            values.append(
                {
                    **base,
                    "caseId": f"{judgment.judgment_id}-HUMAN",
                    "metricCode": "HUMAN_AGREEMENT_RATE",
                }
            )
        for item in result_items:
            if item.evidences:
                for evidence in item.evidences:
                    score = Decimal("1") if evidence.relevance_score >= 0.7 else Decimal("0.5")
                    values.append(
                        {
                            "caseId": evidence.evidence_id,
                            "metricCode": "EVIDENCE_PRECISION",
                            "matchScore": str(score),
                            "excluded": False,
                            "aiError": False,
                        }
                    )
            elif item.evidence_status != "NOT_REQUIRED":
                values.append(
                    {
                        "caseId": f"{item.review_item_id}-EVIDENCE",
                        "metricCode": "EVIDENCE_PRECISION",
                        "matchScore": "0",
                        "excluded": False,
                        "aiError": True,
                    }
                )
        if dataset.is_excluded and exclude_invalid_samples:
            for value in values:
                value["excluded"] = True
                value["exclusionApproved"] = bool(
                    dataset.exclude_reason_code and dataset.excluded_by and dataset.excluded_at
                )
                value["excludeReasonCode"] = dataset.exclude_reason_code
        return values

    def _authorize(self, actor: CurrentUser, action: str, trace_id: str) -> None:
        if set(actor.roles) & VALIDATION_ROLES:
            return
        self._audit(actor, action, "DENIED", "ROLE_SCOPE", None, trace_id)
        raise ServiceError(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")

    @staticmethod
    def _validate_exclusion(excluded: bool, reason_code: str | None) -> None:
        if excluded and reason_code not in EXCLUDE_REASON_CODES:
            raise ServiceError(400, "BAD_REQUEST", "평가 제외 사유를 확인해 주세요.")
        if not excluded and reason_code is not None:
            raise ServiceError(400, "BAD_REQUEST", "평가 제외 여부와 사유를 확인해 주세요.")

    def _audit(
        self,
        actor: CurrentUser,
        action: str,
        result: str,
        reason: str | None,
        target_id: str | None,
        trace_id: str,
    ) -> None:
        self._audit_sink(
            AuditEvent(
                action_type=action,
                result=result,
                reason_code=reason,
                actor_user_id=actor.user_id,
                actor_department_id=actor.department_id,
                actor_role=actor.roles[0] if actor.roles else None,
                target_type="VALIDATION",
                target_id=target_id,
                trace_id=trace_id,
                created_at=self._now(),
            )
        )


def evaluation_response(value: ValidationEvaluation) -> dict[str, object]:
    return {
        "evaluationId": value.evaluation_id,
        "evaluationStatus": value.evaluation_status,
        "snapshotHash": value.snapshot_hash,
        "snapshotCreatedAt": value.snapshot_created_at,
        "datasetSnapshotCount": len(value.dataset_snapshot),
        "reviewSelectionPolicy": value.review_selection_policy,
        "versionSnapshot": value.version_snapshot,
        "exclusionSummary": list(value.exclusion_summary),
        "metrics": [
            {
                "metricCode": item.metric_code,
                "metricName": item.metric_name,
                "score": float(item.score) if item.score is not None else None,
                "numerator": float(item.numerator),
                "denominator": item.denominator,
                "excludedCount": item.excluded_count,
                "partialCount": item.partial_count,
                "notApplicable": item.not_applicable,
                "targetScore": float(item.target_score),
                "achieved": item.achieved,
            }
            for item in value.metrics
        ],
    }


def dataset_response(value: ValidationDataset) -> dict[str, object]:
    return {
        "datasetId": value.dataset_id,
        "datasetName": value.dataset_name,
        "productGroup": value.product_group,
        "advertisementType": value.advertisement_type,
        "advertisementId": value.advertisement_id,
        "sampleFileId": value.sample_file_id,
        "productConditionFileId": value.product_condition_file_id,
        "humanReviewComment": value.human_review_comment,
        "labelJson": value.label_json,
        "datasetVersion": value.dataset_version,
        "excluded": value.is_excluded,
        "excludeReasonCode": value.exclude_reason_code,
        "excludeReasonDetail": value.exclude_reason,
        "excludedBy": value.excluded_by,
        "excludedAt": value.excluded_at,
        "createdAt": value.created_at,
        "updatedAt": value.updated_at,
    }


def judgment_response(value: ValidationJudgment) -> dict[str, object]:
    return {
        "judgmentId": value.judgment_id,
        "datasetId": value.dataset_id,
        "targetText": value.target_text,
        "reviewType": value.review_type,
        "expectedStatus": value.expected_status,
        "riskLevel": value.risk_level,
        "comment": value.evidence_comment,
        "excluded": value.is_excluded,
        "excludeReasonCode": value.exclude_reason_code,
        "excludeReasonDetail": value.exclude_reason,
        "judgmentVersion": value.judgment_version,
        "judgedBy": value.judged_by,
        "judgedAt": value.judged_at,
    }


def _artifact_metadata(value: Mapping[str, object]) -> dict[str, object]:
    content = value.get("content")
    if not isinstance(content, bytes):
        raise ServiceError(400, "BAD_REQUEST", "검증 파일을 읽을 수 없습니다.")
    return {
        "fileName": str(value.get("fileName", "")),
        "contentType": _optional_str(value.get("contentType")),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _dataset_snapshot(value: ValidationDataset) -> dict[str, object]:
    return {
        "datasetId": value.dataset_id,
        "datasetVersion": value.dataset_version,
        "sampleFileId": value.sample_file_id,
        "productConditionFileId": value.product_condition_file_id,
        "productGroup": value.product_group,
        "advertisementType": value.advertisement_type,
        "labelJson": copy.deepcopy(value.label_json),
    }


def _judgment_snapshot(value: ValidationJudgment) -> dict[str, object]:
    return {
        "judgmentId": value.judgment_id,
        "judgmentVersion": value.judgment_version,
        "datasetId": value.dataset_id,
        "targetText": value.target_text,
        "reviewType": value.review_type,
        "expectedStatus": value.expected_status,
        "riskLevel": value.risk_level,
    }


def _review_snapshot(review: Review, items: tuple[ResultItem, ...]) -> dict[str, object]:
    return {
        "reviewId": review.review_id,
        "reviewStatus": review.status,
        "completedAt": review.completed_at,
        "reviewItems": [
            {
                "reviewItemId": item.review_item_id,
                "reviewType": item.review_type,
                "targetText": item.target_text,
                "resultStatus": item.result_status,
                "riskLevel": item.risk_level,
                "sourceEngine": item.source_engine,
                "sourceVersion": item.source_version,
                "standardVersionIds": [evidence.standard_version_id for evidence in item.evidences],
            }
            for item in items
        ],
    }


def _version_snapshot(ai_results: Iterable[Mapping[str, object]]) -> dict[str, object]:
    standards: set[str] = set()
    source_versions: set[str] = set()
    for review in ai_results:
        review_items = review.get("reviewItems", [])
        if not isinstance(review_items, list):
            continue
        for item in review_items:
            if not isinstance(item, dict):
                continue
            standards.update(str(value) for value in item.get("standardVersionIds", []))
            if item.get("sourceVersion"):
                source_versions.add(str(item["sourceVersion"]))
    return {
        "standardVersionIds": sorted(standards),
        "modelVersion": ",".join(sorted(source_versions)) or "provider-free-runtime-v1",
        "promptVersion": "provider-free-prompt-v1",
        "parserOcrPolicy": "ADR-0065/ADR-0072/ADR-0073",
        "ragSearchPolicy": "ADR-0043/ADR-0071",
    }


def _exclusion_snapshots(cases: Iterable[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    values: dict[str, dict[str, object]] = {}
    for index, case in enumerate(cases):
        case_id = str(case.get("caseId") or f"case-{index}")
        if case_id in values:
            continue
        values[case_id] = {
            "caseId": case_id,
            "excluded": bool(case.get("excluded")),
            "excludeReasonCode": case.get("excludeReasonCode"),
            "excludedBy": case.get("excludedBy"),
            "excludedAt": case.get("excludedAt"),
        }
    return tuple(values[key] for key in sorted(values))


def _status_score(expected: str, actual: str | None) -> Decimal:
    if actual == expected:
        return Decimal("1")
    if {expected, actual} == {"NEEDS_REVISION", "NEEDS_CONFIRMATION"}:
        return Decimal("0.5")
    return Decimal("0")


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported canonical snapshot value: {type(value).__name__}")
