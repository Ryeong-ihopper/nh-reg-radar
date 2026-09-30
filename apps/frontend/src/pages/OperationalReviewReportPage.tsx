import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { operationalRequest } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { type ResultWorkspace, type ResultRow, reviewItemTitle, reviewVerdict } from "../components/operationalResultModel";
import { OperationalOriginalPanel } from "../components/OperationalOriginalPanel";
import { OperationalReviewDetail, VerdictBadge } from "../components/OperationalReviewDetail";
import { ErrorState, LoadingState } from "../components/RequestState";

const VERDICTS = ["위반", "판단불가", "충족", "미해당"] as const;
const humanFinalDecisionEnabled = import.meta.env.VITE_OPERATIONAL_HUMAN_DECISION === "true";

export function OperationalResultsPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [active, setActive] = useState("");
  const [hovered, setHovered] = useState("");
  const [verdictFilter, setVerdictFilter] = useState("전체");
  const [locateRequest, setLocateRequest] = useState(0);
  const [focusedEvidence, setFocusedEvidence] = useState<ResultRow | null>(null);
  const [decisionComment, setDecisionComment] = useState("");
  const status = useQuery({queryKey: ["review-progress", reviewId], queryFn: () => api.getReviewStatus(token, reviewId)});
  const adId = status.data?.advertisementId ?? "";
  const advertisement = useQuery({queryKey: ["advertisement", adId], queryFn: () => api.getAdvertisement(token, adId), enabled: Boolean(adId)});
  const workspace = useQuery({queryKey: ["operational-workspace", reviewId], queryFn: () => operationalRequest<ResultWorkspace>(token, `reviews/${reviewId}/workspace`), retry: false});
  const finalDecision = useMutation({
    mutationFn: (decision: "APPROVED" | "REJECTED") => operationalRequest(token, `reviews/${reviewId}/decision`, {decision, comment: decisionComment.trim()}),
    onSuccess: () => void workspace.refetch(),
  });
  const rows = useMemo(() => (workspace.data?.rows ?? []).filter(row => VERDICTS.includes(row.verdict as typeof VERDICTS[number])), [workspace.data]);
  const selected = rows.find(row => (row.row_id ?? row.item_id) === active);
  const previewRow = rows.find(row => (row.row_id ?? row.item_id) === hovered) ?? (selected ? focusedEvidence ?? selected : undefined);
  const filteredRows = rows.filter(row => verdictFilter === "전체" || reviewVerdict(row.verdict) === verdictFilter);
  const verdictFilters = ["전체", "적정", "부적정", "확인필요", ...(rows.some(row => reviewVerdict(row.verdict) === "해당없음") ? ["해당없음"] : [])];
  const omissions = workspace.data?.execution_omissions ?? [];

  return <section className="single-review review-report-page" aria-label="AI 검토 결과">
    <header className="single-review-header">
      <div><p className="eyebrow">AI 심의 결과</p><h2>심의 결과 리포트</h2>
        <p className="review-page-description">{advertisement.data?.advertisementName ?? "광고"} · 광고 원문과 항목별 판정을 나란히 확인합니다.</p>
        <nav aria-label="검토 진행 상황" className="result-progress"><span>결과 확인{workspace.data?.source_policy === "template-only" ? " · 템플릿 심의" : ""}</span><Link to={`/reviews/${encodeURIComponent(reviewId)}/status`}>진행 기록</Link></nav>
      </div>
      <div className="form-actions review-report-actions"><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/suggestions`}>추천 문구·수정 초안</Link><button type="button" onClick={() => window.print()}>PDF 저장·인쇄</button></div>
    </header>
    {status.isError ? <ErrorState error={status.error} onRetry={() => void status.refetch()} /> : null}
    {workspace.isPending ? <LoadingState label="검토 결과를 불러오는 중입니다." /> : null}
    {workspace.isError ? <ErrorState error={workspace.error} onRetry={() => void workspace.refetch()} /> : null}
    {workspace.data ? <div className="review-report-workspace">
      <OperationalOriginalPanel reviewId={reviewId} token={token} row={previewRow} locateRequest={locateRequest} />
      <section className="review-item-panel" aria-label="항목별 판정">
        {selected ? <>
          <header className="review-detail-nav"><button type="button" className="button-secondary" onClick={() => setActive("")}>← 항목 목록</button><span>{rows.findIndex(row => (row.row_id ?? row.item_id) === active) + 1} / {rows.length}</span></header>
          <div className="review-detail-scroll"><OperationalReviewDetail row={selected} reviewId={reviewId} showSuggestionLink={false} onLocate={segment => {
            setFocusedEvidence(segment ? {...selected, row_id: `${selected.row_id ?? selected.item_id}:${segment.line_ref}`,
              evidence: segment.text, evidence_locations: segment.locations, review_locations: []} : null);
            setLocateRequest(value => value + 1);
          }} /></div>
        </> : <>
          <header><h3>항목별 판정 <small>{filteredRows.length} / {rows.length}건</small></h3>
            <div className="review-verdict-filters" role="group" aria-label="판정별 보기">
              {verdictFilters.map(filter => (
                <button key={filter} type="button" data-verdict={filter} aria-pressed={verdictFilter === filter}
                  onClick={() => { setVerdictFilter(filter); setHovered(""); }}>
                  <span className="review-filter-label">{filter}</span>
                  <span className="review-filter-count">{filter === "전체" ? rows.length : rows.filter(row => reviewVerdict(row.verdict) === filter).length}</span>
                </button>
              ))}
            </div>
          </header>
          <div className="review-result-list" aria-label="항목별 판정 목록">
            {omissions.length ? <aside className="state-message" role="alert"><strong>과거 실행 누락 {omissions.length}건 · 재처리 필요</strong><p>모든 대상 항목의 검토가 완료된 상태가 아닙니다.</p></aside> : null}
            {workspace.data.output_failure_count ? <aside className="state-message" role="alert"><strong>판정 처리 실패 {workspace.data.output_failure_count}건</strong><p>{workspace.data.partial_result_warning}</p><details><summary>실패 항목 확인</summary><ul>{workspace.data.output_failure_pairs?.map((failure, index) => <li key={`${failure.scope_id ?? failure.ad_id}:${failure.item_id}`}>항목 {index + 1} · 모델 응답 형식 또는 원문 근거 연결 실패</li>)}</ul></details></aside> : null}
            {filteredRows.map((row) => {
              const rowId = row.row_id ?? row.item_id;
              return <button type="button" className="review-result-card" key={rowId} onMouseEnter={() => setHovered(rowId)} onMouseLeave={() => setHovered("")} onFocus={() => setHovered(rowId)} onBlur={() => setHovered("")} onClick={() => { setActive(rowId); setHovered(""); setFocusedEvidence(null); }}>
                <span className="review-item-number">{String(rows.indexOf(row) + 1).padStart(2, "0")}</span>
                <span className="review-result-copy"><strong>{reviewItemTitle(row)}</strong><span className="review-result-summary">{row.reason?.trim() || "저장된 판정 사유가 없습니다."}</span></span>
                <VerdictBadge value={row.verdict} />
              </button>;
            })}
            {!rows.length ? <p className="review-empty-note">표시할 판정 항목이 없습니다.</p> : null}
            {workspace.data.template_coverage?.length ? <details className="template-coverage-details"><summary>기준표 전체 항목 처리 내역</summary>{workspace.data.template_coverage.map((coverage, index) => <p key={index}>{coverage.template_section} · 전체 {coverage.rule_count}항목 · 자동 판정 요청 {coverage.requested_count} · 사람 확인 포함 {coverage.manual_review_count} · 처리 기록 누락 {coverage.missing_count}</p>)}</details> : null}
            {humanFinalDecisionEnabled ? <section className="human-final-decision" aria-labelledby="human-final-decision-heading"><div><h3 id="human-final-decision-heading">준법 담당자 최종 판단</h3><p>최종 판단을 기록해도 원래 AI 판정은 변경되지 않습니다.</p></div>
              {workspace.data.human_decision ? <dl className="human-decision-record"><div><dt>최종 상태</dt><dd>{workspace.data.human_decision.decision === "APPROVED" ? "승인" : "반려"}</dd></div><div><dt>담당자</dt><dd>{workspace.data.human_decision.reviewer_id}</dd></div><div><dt>판단 시각</dt><dd>{new Date(workspace.data.human_decision.decided_at).toLocaleString("ko-KR")}</dd></div>{workspace.data.human_decision.comment ? <div><dt>검토 의견</dt><dd>{workspace.data.human_decision.comment}</dd></div> : null}</dl> : <><label htmlFor="final-decision-comment"><span>검토 의견</span><textarea id="final-decision-comment" value={decisionComment} maxLength={1000} onChange={event => setDecisionComment(event.target.value)} placeholder="반려 시 사유를 반드시 입력해 주세요." /></label>{finalDecision.isError ? <ErrorState error={finalDecision.error} /> : null}<div className="form-actions"><button type="button" className="button-secondary" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("REJECTED")}>반려</button><button type="button" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("APPROVED")}>최종 승인</button></div></>}
            </section> : null}
          </div>
        </>}
      </section>
    </div> : null}
  </section>;
}
