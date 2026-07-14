import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type ReportFormat, type SuggestionDecisionInput } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";

const DECISION_LABELS = {
  ACCEPTED: "채택",
  REJECTED: "미채택",
  MODIFIED_AND_USED: "수정 후 사용",
} as const;

export function M6SupportPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [decisionStatus, setDecisionStatus] = useState<keyof typeof DECISION_LABELS>("ACCEPTED");
  const [decisionError, setDecisionError] = useState("");
  const [qaAnswer, setQaAnswer] = useState<Awaited<ReturnType<typeof api.askComplianceQuestion>> | null>(null);
  const [report, setReport] = useState<Awaited<ReturnType<typeof api.createReviewReport>> | null>(null);

  const suggestions = useQuery({
    queryKey: ["review-suggestions", reviewId],
    queryFn: () => api.listReviewSuggestions(token, reviewId),
    enabled: Boolean(token && reviewId),
  });
  const opinion = useQuery({
    queryKey: ["opinion-draft", reviewId],
    queryFn: () => api.listOpinionDrafts(token, reviewId),
    enabled: Boolean(token && reviewId),
  });
  const decision = useMutation({
    mutationFn: ({ suggestionId, input }: { suggestionId: string; input: SuggestionDecisionInput }) => api.recordSuggestionDecision(token, suggestionId, input),
    onSuccess: () => void suggestions.refetch(),
  });
  const question = useMutation({ mutationFn: (questionText: string) => api.askComplianceQuestion(token, { question: questionText }), onSuccess: setQaAnswer });
  const createDraft = useMutation({ mutationFn: () => api.createOpinionDraft(token, reviewId), onSuccess: () => void opinion.refetch() });
  const updateDraft = useMutation({ mutationFn: ({ draftId, finalContent }: { draftId: string; finalContent: string }) => api.updateOpinionDraft(token, draftId, { finalContent }), onSuccess: () => void opinion.refetch() });
  const createReport = useMutation({ mutationFn: (format: ReportFormat) => api.createReviewReport(token, reviewId, { format, includeAnnotations: true, includeSuggestions: true, includeOpinionDraft: true, includeEvidenceDetails: true }), onSuccess: setReport });

  function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const suggestion = suggestions.data?.[0];
    if (!suggestion) return;
    const finalText = new FormData(event.currentTarget).get("finalText")?.toString().trim() ?? "";
    if (decisionStatus === "MODIFIED_AND_USED" && !finalText) {
      setDecisionError("수정 후 사용에는 최종 문구가 필요합니다.");
      return;
    }
    setDecisionError("");
    decision.mutate({ suggestionId: suggestion.suggestionId, input: { decisionStatus, finalText: finalText || null } });
  }

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const questionText = new FormData(event.currentTarget).get("question")?.toString().trim() ?? "";
    if (questionText) question.mutate(questionText);
  }

  function submitDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const draft = opinion.data?.[0];
    if (!draft) return;
    const finalContent = new FormData(event.currentTarget).get("finalContent")?.toString().trim() ?? "";
    if (finalContent) updateDraft.mutate({ draftId: draft.draftId, finalContent });
  }

  async function downloadReport() {
    if (!report) return;
    const blob = await api.downloadReviewReport(token, report.reportId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `review-report-${report.reportId}.${report.format.toLowerCase()}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-labelledby="m6-support-heading">
      <p className="eyebrow">담당자 지원 산출물</p>
      <h2 id="m6-support-heading">검토 지원 및 리포트</h2>
      <p className="state-message state-warning"><strong>최종 판단 안내</strong><br />AI 결과는 담당자 검토 지원용이며 자동으로 확정되지 않습니다.</p>

      <section aria-labelledby="suggestion-heading"><h3 id="suggestion-heading">문구 추천</h3>
        {suggestions.isPending ? <LoadingState label="추천 문구를 불러오는 중입니다." /> : null}
        {suggestions.isError ? <ErrorState error={suggestions.error} onRetry={() => void suggestions.refetch()} /> : null}
        {suggestions.data?.[0] ? <><p><strong>{suggestions.data[0].originalText}</strong> → {suggestions.data[0].suggestedText}</p><p>{suggestions.data[0].suggestionReason}</p>
          <form onSubmit={submitDecision}><label>판단<select value={decisionStatus} onChange={(event) => setDecisionStatus(event.target.value as keyof typeof DECISION_LABELS)}>{Object.entries(DECISION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label>최종 문구<textarea name="finalText" /></label>
            {decisionError ? <p role="alert" className="state-message state-error">{decisionError}</p> : null}
            {decision.isError ? <ErrorState error={decision.error} /> : null}
            <button type="submit" disabled={decision.isPending}>{decision.isPending ? "저장 중..." : "담당자 판단 저장"}</button>
          </form></> : null}
      </section>

      <section aria-labelledby="qa-heading"><h3 id="qa-heading">광고 규정 Q&A</h3><form onSubmit={submitQuestion}><label>질문<textarea name="question" required /></label><button type="submit" disabled={question.isPending}>{question.isPending ? "답변 생성 중..." : "근거 기반 질문"}</button></form>
        {question.isError ? <ErrorState error={question.error} /> : null}
        {qaAnswer ? <article className="result-detail"><h4>{qaAnswer.answerSummary}</h4><p>{qaAnswer.answerDetail}</p>{qaAnswer.needsHumanReview ? <p className="state-message state-warning">근거가 부족하여 담당자 확인이 필요합니다.</p> : null}<h5>근거</h5>{qaAnswer.evidences.length ? <ul>{qaAnswer.evidences.map((evidence) => <li key={evidence.evidenceId}><strong>{evidence.title}</strong>: {evidence.matchedText}</li>)}</ul> : <p>연결된 근거가 없습니다.</p>}</article> : null}
      </section>

      <section aria-labelledby="opinion-heading"><h3 id="opinion-heading">심의 의견 초안</h3>
        {opinion.isPending ? <LoadingState label="심의 의견 초안을 불러오는 중입니다." /> : null}{opinion.isError ? <ErrorState error={opinion.error} onRetry={() => void opinion.refetch()} /> : null}
        {!opinion.data?.[0] ? <button type="button" onClick={() => createDraft.mutate()} disabled={createDraft.isPending}>{createDraft.isPending ? "초안 생성 중..." : "심의 의견 초안 생성"}</button> : <form onSubmit={submitDraft}><p>{opinion.data[0].draftContent}</p><label>담당자 수정본<textarea name="finalContent" defaultValue={opinion.data[0].finalContent ?? opinion.data[0].draftContent} required /></label><button type="submit" disabled={updateDraft.isPending}>{updateDraft.isPending ? "저장 중..." : "수정본 저장"}</button></form>}
        {createDraft.isError ? <ErrorState error={createDraft.error} /> : null}{updateDraft.isError ? <ErrorState error={updateDraft.error} /> : null}
      </section>

      <section aria-labelledby="report-heading"><h3 id="report-heading">불변 리포트 스냅샷</h3><p>HWPX 원본을 기준으로 PDF 변환본을 생성하며, 생성 후 검토·기준 변경과 무관하게 같은 스냅샷을 유지합니다.</p>
        <button type="button" onClick={() => createReport.mutate("HWPX")} disabled={createReport.isPending}>HWPX 리포트 생성</button>{" "}<button type="button" onClick={() => createReport.mutate("PDF")} disabled={createReport.isPending}>PDF 리포트 생성</button>
        {createReport.isError ? <ErrorState error={createReport.error} /> : null}
        {report ? <article className="result-detail"><p>상태: {report.reportStatus} · 스냅샷 {report.snapshotVersion}</p><p>해시: <code>{report.snapshotHash}</code></p>{report.sourceReportId ? <p>HWPX 원본: {report.sourceReportId}</p> : null}<button type="button" onClick={() => void downloadReport()}>권한 확인 후 다운로드</button></article> : null}
      </section>
      <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>검토 결과로</Link><Link className="button-link" to="/advertisements">광고물 목록</Link></div>
    </section>
  );
}

export function ComparisonPage() {
  const { advertisementId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [result, setResult] = useState<{
    revisionId: string;
    comparison: Awaited<ReturnType<typeof api.createAdvertisementComparison>>;
    newReviewId: string;
  } | null>(null);
  const createComparison = useMutation({
    mutationFn: async ({ baseReviewId, revisionMemo, revisedAdvertisementFile }: {
      baseReviewId: string;
      revisionMemo?: string;
      revisedAdvertisementFile: File;
    }) => {
      const revision = await api.createAdvertisementRevision(token, advertisementId, {
        revisionMemo,
        revisedAdvertisementFile,
      });
      const comparison = await api.createAdvertisementComparison(token, advertisementId, {
        baseReviewId,
        revisionId: revision.revisionId,
      });
      const rerun = await api.rerunReview(token, baseReviewId, {
        reason: `수정본 ${revision.revisionId} 등록 후 재검토`,
      });
      return { revisionId: revision.revisionId, comparison, newReviewId: rerun.newReviewId };
    },
    onSuccess: setResult,
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const revisedAdvertisementFile = data.get("revisedAdvertisementFile");
    if (!(revisedAdvertisementFile instanceof File) || revisedAdvertisementFile.size === 0) return;
    const revisionMemo = String(data.get("revisionMemo") ?? "").trim();
    createComparison.mutate({
      baseReviewId: String(data.get("baseReviewId")),
      revisionMemo: revisionMemo || undefined,
      revisedAdvertisementFile,
    });
  }
  return <section aria-labelledby="comparison-heading"><p className="eyebrow">수정 전후 비교</p><h2 id="comparison-heading">수정본 재검토 비교</h2><form onSubmit={submit}><label>기준 검토 ID<input name="baseReviewId" required /></label><label>수정 메모<textarea name="revisionMemo" /></label><label>수정 광고 파일<input name="revisedAdvertisementFile" type="file" accept="image/png,image/jpeg,application/pdf" required /></label><button type="submit" disabled={createComparison.isPending}>{createComparison.isPending ? "등록·비교·재검토 중..." : "수정본 등록 후 비교·재검토"}</button></form>{createComparison.isError ? <ErrorState error={createComparison.error} /> : null}{result ? <article className="result-detail"><p>수정본 ID: <code>{result.revisionId}</code> · 재검토 ID: <code>{result.newReviewId}</code></p><p>해결 {result.comparison.resolvedIssueCount} · 미해결 {result.comparison.unresolvedIssueCount} · 신규 {result.comparison.newIssueCount}</p><ul>{result.comparison.items?.map((item, index) => <li key={`${item.reviewItemId}-${index}`}><strong>{item.resolutionStatus}</strong> {item.originalText} → {item.revisedText}{item.reanalysisReviewId ? ` (재분석 ${item.reanalysisReviewId})` : ""}</li>)}</ul></article> : null}<Link className="button-link button-secondary" to={`/advertisements/${encodeURIComponent(advertisementId)}`}>광고물 상세로</Link></section>;
}
