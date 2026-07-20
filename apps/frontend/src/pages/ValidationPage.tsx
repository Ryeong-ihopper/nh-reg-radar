import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import {
  api,
  type ExcludeReasonCode,
  type ValidationDataset,
  type ValidationEvaluation,
  type ValidationMetricCode,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/RequestState";
import {
  advertisementTypeLabel,
  productGroupLabel,
} from "../components/displayLabels";

const METRICS: ValidationMetricCode[] = [
  "REQUIRED_PHRASE_ACCURACY",
  "MISLEADING_EXPRESSION_ACCURACY",
  "EVIDENCE_PRECISION",
  "HUMAN_AGREEMENT_RATE",
];
const EXCLUDE_REASONS: ExcludeReasonCode[] = [
  "OCR_UNREADABLE",
  "PRODUCT_CONDITION_AMBIGUOUS",
  "REFERENCE_NOT_PROVIDED",
  "SOURCE_FILE_CORRUPTED",
  "LABEL_UNCLEAR",
  "DUPLICATE_SAMPLE",
  "OUT_OF_SCOPE",
];
const DATASET_EDIT_ROLES = new Set(["COMPLIANCE_REVIEWER", "STANDARD_MANAGER"]);
const EVALUATION_RUN_ROLES = new Set(["COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"]);

const EXCLUDE_REASON_LABELS: Record<ExcludeReasonCode, string> = {
  OCR_UNREADABLE: "문구 판독 불가",
  PRODUCT_CONDITION_AMBIGUOUS: "상품 조건이 불명확함",
  REFERENCE_NOT_PROVIDED: "검토 근거가 제공되지 않음",
  SOURCE_FILE_CORRUPTED: "원본 파일을 읽을 수 없음",
  LABEL_UNCLEAR: "정답 판단이 불명확함",
  DUPLICATE_SAMPLE: "중복 샘플",
  OUT_OF_SCOPE: "검증 범위 외",
};

function DatasetList({
  datasets,
  selectedIds,
  onToggle,
}: {
  datasets: ValidationDataset[];
  selectedIds?: string[];
  onToggle?: (datasetId: string) => void;
}) {
  if (datasets.length === 0)
    return <p className="state-message">등록된 검증 데이터가 없습니다.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {onToggle ? <th>선택</th> : null}
            <th>데이터셋</th>
            <th>분류</th>
            <th>버전</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((dataset) => (
            <tr key={dataset.datasetId}>
              {onToggle ? (
                <td>
                  <input
                    aria-label={`${dataset.datasetName} 선택`}
                    type="checkbox"
                    checked={selectedIds?.includes(dataset.datasetId) ?? false}
                    onChange={() => onToggle(dataset.datasetId)}
                  />
                </td>
              ) : null}
              <td>
                <strong>{dataset.datasetName}</strong>
              </td>
              <td>
                {productGroupLabel(dataset.productGroup)} ·{" "}
                {advertisementTypeLabel(dataset.advertisementType)}
              </td>
              <td>{dataset.datasetVersion}판</td>
              <td>
                {dataset.excluded
                  ? EXCLUDE_REASON_LABELS[
                      dataset.excludeReasonCode ?? "OUT_OF_SCOPE"
                    ]
                  : "평가 대상"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DatasetRegistration({
  datasets,
  onSubmitDataset,
  onSubmitJudgment,
  isCreatingDataset,
  isCreatingJudgment,
  datasetError,
  judgmentError,
}: {
  datasets: ValidationDataset[];
  onSubmitDataset: (event: FormEvent<HTMLFormElement>) => void;
  onSubmitJudgment: (event: FormEvent<HTMLFormElement>) => void;
  isCreatingDataset: boolean;
  isCreatingJudgment: boolean;
  datasetError: unknown;
  judgmentError: unknown;
}) {
  return (
    <div className="validation-grid">
      <section>
        <h3>검증 데이터 등록</h3>
        <form onSubmit={onSubmitDataset}>
          <label>
            데이터셋명
            <input
              name="datasetName"
              placeholder="예: 예금 금리 안내문 검증"
              required
            />
          </label>
          <label>
            상품군
            <select name="productGroup">
              <option value="DEPOSIT">예금</option>
              <option value="SAVINGS">적금</option>
              <option value="DEMAND_DEPOSIT">입출금</option>
              <option value="EVENT">이벤트</option>
              <option value="LOAN">대출</option>
            </select>
          </label>
          <label>
            광고유형
            <select name="advertisementType">
              <option value="BRANCH_FLYER">영업점 전단</option>
              <option value="WEB_BANNER">웹 배너</option>
              <option value="MOBILE_BANNER">모바일 배너</option>
            </select>
          </label>
          <label>
            샘플 광고물
            <input name="advertisementFile" type="file" required />
          </label>
          <label>
            담당자 의견
            <textarea name="humanReviewComment" />
          </label>
          <label>
            정답 데이터 (JSON)
            <textarea name="labelJson" defaultValue="{}" />
          </label>
          <div className="validation-exclusion">
            <label className="inline-check">
              <input name="excluded" type="checkbox" />
              <span>이 검증 데이터를 이번 평가에서 제외</span>
            </label>
            <p>파일을 읽을 수 없거나 정답 판단이 어려운 경우에만 선택하세요.</p>
          </div>
          <label>
            제외 사유
            <select name="excludeReasonCode">
              {EXCLUDE_REASONS.map((reason) => (
                <option key={reason} value={reason}>
                  {EXCLUDE_REASON_LABELS[reason]}
                </option>
              ))}
            </select>
          </label>
          <label>
            제외 상세
            <input name="excludeReasonDetail" />
          </label>
          <button disabled={isCreatingDataset} type="submit">
            {isCreatingDataset ? "등록 중..." : "검증 데이터 등록"}
          </button>
          {datasetError ? <ErrorState error={datasetError} /> : null}
        </form>
      </section>
      <section>
        <h3>담당자 판단 등록</h3>
        <form onSubmit={onSubmitJudgment}>
          <label>
            데이터셋
            <select name="datasetId" required>
              {datasets.map((dataset) => (
                <option key={dataset.datasetId} value={dataset.datasetId}>
                  {dataset.datasetName}
                </option>
              ))}
            </select>
          </label>
          <label>
            대상 문구
            <input name="targetText" required />
          </label>
          <label>
            검토 유형
            <select name="reviewType">
              <option value="REQUIRED_PHRASE">필수 문구</option>
              <option value="MISLEADING_EXPRESSION">과장·오인 표현</option>
              <option value="OCR_QUALITY">문구 판독 품질</option>
            </select>
          </label>
          <label>
            기대 결과
            <select name="expectedStatus">
              <option value="APPROPRIATE">적정</option>
              <option value="NEEDS_REVISION">수정 필요</option>
              <option value="NEEDS_CONFIRMATION">확인 필요</option>
            </select>
          </label>
          <label>
            위험도
            <select name="riskLevel">
              <option value="LOW">낮음</option>
              <option value="MEDIUM">중간</option>
              <option value="HIGH">높음</option>
            </select>
          </label>
          <label>
            판단 의견
            <textarea name="comment" />
          </label>
          <div className="validation-exclusion">
            <label className="inline-check">
              <input name="judgmentExcluded" type="checkbox" />
              <span>이 담당자 판단을 이번 평가에서 제외</span>
            </label>
            <p>평가에 쓰지 않을 판단 항목에만 선택하세요.</p>
          </div>
          <label>
            제외 사유
            <select name="judgmentExcludeReasonCode">
              {EXCLUDE_REASONS.map((reason) => (
                <option key={reason} value={reason}>
                  {EXCLUDE_REASON_LABELS[reason]}
                </option>
              ))}
            </select>
          </label>
          <button disabled={isCreatingJudgment} type="submit">
            {isCreatingJudgment ? "저장 중..." : "담당자 판단 등록"}
          </button>
          {judgmentError ? <ErrorState error={judgmentError} /> : null}
        </form>
      </section>
    </div>
  );
}

export function ValidationDatasetsPage() {
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [page, setPage] = useState(1);
  const canEdit =
    session?.user.roles.some((role) => DATASET_EDIT_ROLES.has(role)) ?? false;
  const datasets = useQuery({
    queryKey: ["validation-datasets", page],
    queryFn: () => api.listValidationDatasets(token, page),
    enabled: Boolean(token),
  });
  const createDataset = useMutation({
    mutationFn: api.createValidationDataset.bind(api, token),
    onSuccess: () => void datasets.refetch(),
  });
  const createJudgments = useMutation({
    mutationFn: ({
      datasetId,
      input,
    }: {
      datasetId: string;
      input: Parameters<typeof api.createValidationJudgments>[2];
    }) => api.createValidationJudgments(token, datasetId, input),
    onSuccess: () => void datasets.refetch(),
  });

  function submitDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const advertisementFile = data.get("advertisementFile");
    if (!(advertisementFile instanceof File)) return;
    const excluded = data.get("excluded") === "on";
    createDataset.mutate({
      datasetName: String(data.get("datasetName")),
      productGroup: data.get("productGroup") as "DEPOSIT",
      advertisementType: data.get("advertisementType") as "BRANCH_FLYER",
      advertisementFile,
      humanReviewComment: String(data.get("humanReviewComment") || ""),
      labelJson: String(data.get("labelJson") || ""),
      excluded,
      excludeReasonCode: excluded
        ? (data.get("excludeReasonCode") as ExcludeReasonCode)
        : undefined,
      excludeReasonDetail: excluded
        ? String(data.get("excludeReasonDetail") || "")
        : undefined,
    });
  }
  function submitJudgment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const excluded = data.get("judgmentExcluded") === "on";
    createJudgments.mutate({
      datasetId: String(data.get("datasetId")),
      input: {
        judgments: [
          {
            targetText: String(data.get("targetText")),
            reviewType: data.get("reviewType") as "REQUIRED_PHRASE",
            expectedStatus: data.get("expectedStatus") as "APPROPRIATE",
            riskLevel: data.get("riskLevel") as "LOW",
            comment: String(data.get("comment") || ""),
            excluded,
            excludeReasonCode: excluded
              ? (data.get("judgmentExcludeReasonCode") as ExcludeReasonCode)
              : null,
          },
        ],
      },
    });
  }

  return (
    <section aria-labelledby="validation-datasets-heading">
      <PageHeader
        headingId="validation-datasets-heading"
        eyebrow="검토 품질 관리"
        title="검증 데이터 및 담당자 판단"
        description="검토 품질을 점검할 샘플과 담당자 판단을 등록하고, 평가에 사용할 기준을 관리합니다."
      />
      {datasets.isPending ? (
        <LoadingState label="검증 데이터를 불러오는 중입니다." />
      ) : null}
      {datasets.isError ? (
        <ErrorState
          error={datasets.error}
          onRetry={() => void datasets.refetch()}
        />
      ) : null}
      {datasets.data ? (
        <>
          <DatasetList datasets={datasets.data.items} />
          <Pagination
            page={datasets.data.page}
            totalPages={datasets.data.totalPages}
            totalElements={datasets.data.totalElements}
            onPageChange={setPage}
          />
        </>
      ) : null}
      {canEdit && datasets.data ? (
        <DatasetRegistration
          datasets={datasets.data.items}
          onSubmitDataset={submitDataset}
          onSubmitJudgment={submitJudgment}
          isCreatingDataset={createDataset.isPending}
          isCreatingJudgment={createJudgments.isPending}
          datasetError={createDataset.error}
          judgmentError={createJudgments.error}
        />
      ) : (
        <p className="state-message state-warning">
          현재 역할은 검증 데이터와 판단 결과를 조회할 수 있습니다.
        </p>
      )}
      <Link className="button-link" to="/validation/evaluations">
        검증 결과 평가하기
      </Link>
    </section>
  );
}

function EvaluationResult({
  evaluation,
}: {
  evaluation: ValidationEvaluation;
}) {
  return (
    <section aria-label="평가 결과">
      <h3>평가 결과</h3>
      <p>
        평가 상태:{" "}
        {evaluation.evaluationStatus === "COMPLETED" ? "완료" : "처리 중"} ·
        데이터셋 {evaluation.datasetSnapshotCount}건
      </p>
      <div className="result-kpis">
        {evaluation.metrics.map((metric) => (
          <article key={metric.metricCode}>
            <span>{metric.metricName}</span>
            <strong>
              {metric.notApplicable ? "미적용" : `${metric.score}%`}
            </strong>
            <small>
              {metric.notApplicable
                ? "평가할 데이터가 없습니다."
                : `${metric.numerator}/${metric.denominator} · 목표 ${metric.targetScore}% · ${metric.achieved ? "달성" : "미달"}`}
            </small>
          </article>
        ))}
      </div>
      <h4>평가 제외 집계</h4>
      {evaluation.exclusionSummary.length ? (
        <ul>
          {evaluation.exclusionSummary.map((item) => (
            <li key={item.excludeReasonCode}>
              {EXCLUDE_REASON_LABELS[item.excludeReasonCode]}: {item.count}건
            </li>
          ))}
        </ul>
      ) : (
        <p>승인된 평가 제외 항목이 없습니다.</p>
      )}
    </section>
  );
}

export function ValidationEvaluationPage() {
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const canRun =
    session?.user.roles.some((role) => EVALUATION_RUN_ROLES.has(role)) ?? false;
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [evaluationId, setEvaluationId] = useState("");
  const [result, setResult] = useState<ValidationEvaluation | null>(null);
  const [page, setPage] = useState(1);
  const datasets = useQuery({
    queryKey: ["validation-datasets-evaluation", page],
    queryFn: () => api.listValidationDatasets(token, page),
    enabled: Boolean(token),
  });
  const evaluation = useMutation({
    mutationFn: () =>
      api.createValidationEvaluation(token, {
        datasetIds: selectedIds,
        metrics: METRICS,
        excludeInvalidSamples: true,
        reviewSelectionPolicy: "LATEST_COMPLETED",
      }),
    onSuccess: setResult,
  });
  const lookup = useMutation({
    mutationFn: (id: string) => api.getValidationEvaluation(token, id),
    onSuccess: setResult,
  });
  function toggle(datasetId: string) {
    setSelectedIds((current) =>
      current.includes(datasetId)
        ? current.filter((id) => id !== datasetId)
        : [...current, datasetId],
    );
  }
  return (
    <section aria-labelledby="validation-evaluation-heading">
      <PageHeader
        headingId="validation-evaluation-heading"
        eyebrow="검토 품질 관리"
        title="검증 결과 평가"
        description="선택한 검증 데이터로 AI 검토 품질을 평가하고, 목표 달성 여부를 확인합니다."
      />
      {datasets.isPending ? (
        <LoadingState label="평가 대상 데이터를 불러오는 중입니다." />
      ) : null}
      {datasets.isError ? (
        <ErrorState
          error={datasets.error}
          onRetry={() => void datasets.refetch()}
        />
      ) : null}
      {datasets.data ? (
        <>
          <DatasetList
            datasets={datasets.data.items}
            selectedIds={selectedIds}
            onToggle={toggle}
          />
          <Pagination
            page={datasets.data.page}
            totalPages={datasets.data.totalPages}
            totalElements={datasets.data.totalElements}
            onPageChange={setPage}
          />
        </>
      ) : null}
      {canRun ? (
        <button
          type="button"
          disabled={selectedIds.length === 0 || evaluation.isPending}
          onClick={() => evaluation.mutate()}
        >
          {evaluation.isPending ? "평가 중..." : "선택 데이터 평가 실행"}
        </button>
      ) : (
        <p className="state-message state-warning">
          현재 역할은 저장된 평가 결과를 조회할 수 있습니다.
        </p>
      )}
      {evaluation.isError ? <ErrorState error={evaluation.error} /> : null}
      <form
        className="evaluation-lookup"
        onSubmit={(event) => {
          event.preventDefault();
          if (evaluationId.trim()) lookup.mutate(evaluationId.trim());
        }}
      >
        <label>
          이전 평가 결과 조회
          <input
            aria-label="평가 결과 번호"
            value={evaluationId}
            onChange={(event) => setEvaluationId(event.target.value)}
            placeholder="평가 결과 번호 입력"
          />
        </label>
        <button disabled={lookup.isPending} type="submit">
          {lookup.isPending ? "조회 중..." : "조회"}
        </button>
      </form>
      {lookup.isError ? <ErrorState error={lookup.error} /> : null}
      {result ? <EvaluationResult evaluation={result} /> : null}
      <Link className="button-link button-secondary" to="/validation/datasets">
        검증 데이터 관리로
      </Link>
    </section>
  );
}
