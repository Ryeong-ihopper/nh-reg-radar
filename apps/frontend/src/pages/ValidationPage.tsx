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
import { ErrorState, LoadingState } from "../components/RequestState";

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

function DatasetList({ datasets, selectedIds, onToggle }: { datasets: ValidationDataset[]; selectedIds?: string[]; onToggle?: (datasetId: string) => void }) {
  if (datasets.length === 0) return <p className="state-message">등록된 검증 데이터셋이 없습니다.</p>;
  return <div className="table-scroll"><table><thead><tr>{onToggle ? <th>선택</th> : null}<th>데이터셋</th><th>분류</th><th>버전</th><th>제외</th></tr></thead><tbody>{datasets.map((dataset) => <tr key={dataset.datasetId}>{onToggle ? <td><input aria-label={`${dataset.datasetName} 선택`} type="checkbox" checked={selectedIds?.includes(dataset.datasetId) ?? false} onChange={() => onToggle(dataset.datasetId)} /></td> : null}<td><strong>{dataset.datasetName}</strong><br /><small>{dataset.datasetId}</small></td><td>{dataset.productGroup} / {dataset.advertisementType}</td><td>v{dataset.datasetVersion}</td><td>{dataset.excluded ? dataset.excludeReasonCode ?? "제외" : "평가 대상"}</td></tr>)}</tbody></table></div>;
}

export function ValidationDatasetsPage() {
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const canEdit = session?.user.roles.some((role) => DATASET_EDIT_ROLES.has(role)) ?? false;
  const datasets = useQuery({ queryKey: ["validation-datasets"], queryFn: () => api.listValidationDatasets(token), enabled: Boolean(token) });
  const createDataset = useMutation({ mutationFn: api.createValidationDataset.bind(api, token), onSuccess: () => void datasets.refetch() });
  const createJudgments = useMutation({ mutationFn: ({ datasetId, input }: { datasetId: string; input: Parameters<typeof api.createValidationJudgments>[2] }) => api.createValidationJudgments(token, datasetId, input), onSuccess: () => void datasets.refetch() });

  function submitDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const excluded = data.get("excluded") === "on";
    const advertisementFile = data.get("advertisementFile");
    if (!(advertisementFile instanceof File)) return;
    createDataset.mutate({
      datasetName: String(data.get("datasetName")), productGroup: data.get("productGroup") as "DEPOSIT", advertisementType: data.get("advertisementType") as "BRANCH_FLYER",
      advertisementFile, humanReviewComment: String(data.get("humanReviewComment") || ""), labelJson: String(data.get("labelJson") || ""), excluded,
      excludeReasonCode: excluded ? data.get("excludeReasonCode") as ExcludeReasonCode : undefined, excludeReasonDetail: excluded ? String(data.get("excludeReasonDetail") || "") : undefined,
    });
  }

  function submitJudgment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const excluded = data.get("judgmentExcluded") === "on";
    createJudgments.mutate({ datasetId: String(data.get("datasetId")), input: { judgments: [{ targetText: String(data.get("targetText")), reviewType: data.get("reviewType") as "REQUIRED_PHRASE", expectedStatus: data.get("expectedStatus") as "APPROPRIATE", riskLevel: data.get("riskLevel") as "LOW", comment: String(data.get("comment") || ""), excluded, excludeReasonCode: excluded ? data.get("judgmentExcludeReasonCode") as ExcludeReasonCode : null }] } });
  }

  return <section aria-labelledby="validation-datasets-heading"><p className="eyebrow">S-015 PoC 검증 관리</p><h2 id="validation-datasets-heading">검증 데이터셋 및 담당자 판단</h2><p>DB의 versioned 데이터셋과 정답 판단을 평가 원천으로 관리합니다.</p>
    {datasets.isPending ? <LoadingState label="검증 데이터셋을 불러오는 중입니다." /> : null}{datasets.isError ? <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} /> : null}{datasets.data ? <DatasetList datasets={datasets.data.items} /> : null}
    {canEdit ? <div className="validation-grid"><section><h3>검증 데이터 등록</h3><form onSubmit={submitDataset}><label>데이터셋명<input name="datasetName" required /></label><label>상품군<select name="productGroup"><option value="DEPOSIT">DEPOSIT</option><option value="SAVINGS">SAVINGS</option><option value="DEMAND_DEPOSIT">DEMAND_DEPOSIT</option><option value="EVENT">EVENT</option></select></label><label>광고유형<select name="advertisementType"><option value="BRANCH_FLYER">BRANCH_FLYER</option><option value="WEB_BANNER">WEB_BANNER</option><option value="MOBILE_BANNER">MOBILE_BANNER</option></select></label><label>샘플 광고물<input name="advertisementFile" type="file" required /></label><label>담당자 의견<textarea name="humanReviewComment" /></label><label>정답 JSON<textarea name="labelJson" defaultValue="{}" /></label><label className="checkbox-field"><input name="excluded" type="checkbox" /> 평가 제외</label><label>제외 사유<select name="excludeReasonCode">{EXCLUDE_REASONS.map((reason) => <option key={reason}>{reason}</option>)}</select></label><label>제외 상세<input name="excludeReasonDetail" /></label><button disabled={createDataset.isPending} type="submit">{createDataset.isPending ? "등록 중..." : "검증 데이터 등록"}</button>{createDataset.isError ? <ErrorState error={createDataset.error} /> : null}</form></section>
      <section><h3>담당자 판단 등록</h3><form onSubmit={submitJudgment}><label>데이터셋<select name="datasetId" required>{datasets.data?.items.map((dataset) => <option key={dataset.datasetId} value={dataset.datasetId}>{dataset.datasetName}</option>)}</select></label><label>대상 문구<input name="targetText" required /></label><label>검토 유형<select name="reviewType"><option value="REQUIRED_PHRASE">REQUIRED_PHRASE</option><option value="MISLEADING_EXPRESSION">MISLEADING_EXPRESSION</option><option value="OCR_QUALITY">OCR_QUALITY</option></select></label><label>기대 결과<select name="expectedStatus"><option value="APPROPRIATE">APPROPRIATE</option><option value="NEEDS_REVISION">NEEDS_REVISION</option><option value="NEEDS_CONFIRMATION">NEEDS_CONFIRMATION</option></select></label><label>위험도<select name="riskLevel"><option value="LOW">LOW</option><option value="MEDIUM">MEDIUM</option><option value="HIGH">HIGH</option></select></label><label>판단 의견<textarea name="comment" /></label><label className="checkbox-field"><input name="judgmentExcluded" type="checkbox" /> 판단 항목 제외</label><label>제외 사유<select name="judgmentExcludeReasonCode">{EXCLUDE_REASONS.map((reason) => <option key={reason}>{reason}</option>)}</select></label><button disabled={createJudgments.isPending} type="submit">{createJudgments.isPending ? "저장 중..." : "담당자 판단 등록"}</button>{createJudgments.isError ? <ErrorState error={createJudgments.error} /> : null}</form></section></div> : <p className="state-message state-warning">현재 역할은 데이터셋과 판단 결과를 조회만 할 수 있습니다.</p>}
    <Link className="button-link" to="/validation/evaluations">성능 평가로</Link></section>;
}

function EvaluationResult({ evaluation }: { evaluation: ValidationEvaluation }) {
  return <section aria-label="평가 결과"><h3>평가 결과 {evaluation.evaluationId}</h3><p>상태 {evaluation.evaluationStatus} · 데이터셋 snapshot {evaluation.datasetSnapshotCount}건</p><p>불변 snapshot: <code>{evaluation.snapshotHash}</code></p><div className="result-kpis">{evaluation.metrics.map((metric) => <article key={metric.metricCode}><span>{metric.metricName}</span><strong>{metric.notApplicable ? "미적용" : `${metric.score}%`}</strong><small>{metric.notApplicable ? "분모 0 · 목표 판단 제외" : `${metric.numerator}/${metric.denominator} · 목표 ${metric.targetScore}% · ${metric.achieved ? "달성" : "미달"}`}</small></article>)}</div><h4>평가 제외 집계</h4>{evaluation.exclusionSummary.length ? <ul>{evaluation.exclusionSummary.map((item) => <li key={item.excludeReasonCode}>{item.excludeReasonCode}: {item.count}건</li>)}</ul> : <p>승인된 평가 제외 항목이 없습니다.</p>}</section>;
}

export function ValidationEvaluationPage() {
  const { session } = useAuth(); const token = session?.accessToken ?? "";
  const canRun = session?.user.roles.some((role) => EVALUATION_RUN_ROLES.has(role)) ?? false;
  const [selectedIds, setSelectedIds] = useState<string[]>([]); const [evaluationId, setEvaluationId] = useState(""); const [result, setResult] = useState<ValidationEvaluation | null>(null);
  const datasets = useQuery({ queryKey: ["validation-datasets-evaluation"], queryFn: () => api.listValidationDatasets(token), enabled: Boolean(token) });
  const evaluation = useMutation({ mutationFn: () => api.createValidationEvaluation(token, { datasetIds: selectedIds, metrics: METRICS, excludeInvalidSamples: true, reviewSelectionPolicy: "LATEST_COMPLETED" }), onSuccess: setResult });
  const lookup = useMutation({ mutationFn: (id: string) => api.getValidationEvaluation(token, id), onSuccess: setResult });
  function toggle(datasetId: string) { setSelectedIds((current) => current.includes(datasetId) ? current.filter((id) => id !== datasetId) : [...current, datasetId]); }
  return <section aria-labelledby="validation-evaluation-heading"><p className="eyebrow">S-016 성능 평가</p><h2 id="validation-evaluation-heading">PoC KPI 성능 평가</h2><p>점수·분자·분모·달성 여부는 서버에 저장된 불변 snapshot 값을 그대로 표시합니다.</p>{datasets.isPending ? <LoadingState label="평가 대상 데이터셋을 불러오는 중입니다." /> : null}{datasets.isError ? <ErrorState error={datasets.error} onRetry={() => void datasets.refetch()} /> : null}{datasets.data ? <DatasetList datasets={datasets.data.items} selectedIds={selectedIds} onToggle={toggle} /> : null}
    {canRun ? <button type="button" disabled={selectedIds.length === 0 || evaluation.isPending} onClick={() => evaluation.mutate()}>{evaluation.isPending ? "평가 중..." : "선택 데이터셋 평가 실행"}</button> : <p className="state-message state-warning">현재 역할은 저장된 평가 결과만 조회할 수 있습니다.</p>}{evaluation.isError ? <ErrorState error={evaluation.error} /> : null}
    <form onSubmit={(event) => { event.preventDefault(); if (evaluationId.trim()) lookup.mutate(evaluationId.trim()); }}><label>평가 ID<input value={evaluationId} onChange={(event) => setEvaluationId(event.target.value)} /></label><button disabled={lookup.isPending} type="submit">{lookup.isPending ? "조회 중..." : "평가 결과 조회"}</button></form>{lookup.isError ? <ErrorState error={lookup.error} /> : null}{result ? <EvaluationResult evaluation={result} /> : null}<Link className="button-link button-secondary" to="/validation/datasets">검증 데이터셋으로</Link></section>;
}
