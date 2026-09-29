import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { downloadOperationalResult, operationalRequest } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { type ResultWorkspace, resultCounts, reviewVerdict, reviewItemTitle } from "../components/operationalResultModel";
import { OperationalOriginalPanel } from "../components/OperationalOriginalPanel";
import { OperationalReviewDetail, VerdictBadge } from "../components/OperationalReviewDetail";
import { ErrorState, LoadingState } from "../components/RequestState";
import { ExtractionStatusPanel } from "../components/ExtractionStatusPanel";

const VERDICTS = ["위반", "판단불가", "충족", "미해당"] as const;
type Verdict = typeof VERDICTS[number];
type Filter = "ALL" | Verdict;
const COUNT_KEY = {위반: "violation", 판단불가: "unknown", 충족: "compliant", 미해당: "notApplicable"} as const;
const ORDER: Record<string, number> = {위반: 0, 판단불가: 1, 충족: 2, 미해당: 3};
const humanFinalDecisionEnabled = import.meta.env.VITE_OPERATIONAL_HUMAN_DECISION === "true";

export function OperationalResultsPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [active, setActive] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [keyword, setKeyword] = useState("");
  const [problemFirst, setProblemFirst] = useState(false);
  const [view, setView] = useState<"REPORT" | "ORIGINAL">("REPORT");
  const [decisionComment, setDecisionComment] = useState("");
  const status = useQuery({queryKey: ["review-progress", reviewId], queryFn: () => api.getReviewStatus(token, reviewId)});
  const adId = status.data?.advertisementId ?? "";
  const advertisement = useQuery({queryKey: ["advertisement", adId], queryFn: () => api.getAdvertisement(token, adId), enabled: Boolean(adId)});
  const workspace = useQuery({queryKey: ["operational-workspace", reviewId], queryFn: () => operationalRequest<ResultWorkspace>(token, `reviews/${reviewId}/workspace`), retry: false});
  const finalDecision = useMutation({
    mutationFn: (decision: "APPROVED" | "REJECTED") => operationalRequest(token, `reviews/${reviewId}/decision`, {decision, comment: decisionComment.trim()}),
    onSuccess: () => void workspace.refetch(),
  });
  const allRows = useMemo(() => (workspace.data?.rows ?? []).filter(row => VERDICTS.includes(row.verdict as Verdict)), [workspace.data]);
  const counts = resultCounts(allRows);
  const rows = useMemo(() => {
    const query = keyword.trim().toLocaleLowerCase();
    const visible = allRows.filter(row => (filter === "ALL" || row.verdict === filter)
      && (!query || `${reviewItemTitle(row)} ${row.evidence ?? ""} ${row.reason}`.toLocaleLowerCase().includes(query)));
    return problemFirst ? [...visible].sort((a,b) => ORDER[a.verdict] - ORDER[b.verdict]) : visible;
  }, [allRows, filter, keyword, problemFirst]);
  const selected = rows.find(row => (row.row_id ?? row.item_id) === active) ?? rows[0];
  const selectedId = selected?.row_id ?? selected?.item_id;
  const omissions = workspace.data?.execution_omissions ?? [];
  async function downloadJson() {
    const url = URL.createObjectURL(await downloadOperationalResult(token, reviewId));
    const link = document.createElement("a"); link.href = url; link.download = `review-${reviewId}.json`; link.click();
    URL.revokeObjectURL(url);
  }
  return <section className="single-review review-report-page" aria-label="AI 검토 결과">
    <header className="single-review-header"><div><p className="eyebrow">AI 심의 결과</p><h2>심의 결과 리포트</h2><p className="review-page-description">항목별 문구와 기준표 조건을 대조하고, 확인하거나 수정할 부분을 살펴보세요.</p>
      <nav aria-label="검토 진행 상황" className="result-progress"><span>결과 확인{workspace.data?.source_policy === "template-only" ? " · 템플릿 심의" : ""}</span><Link to={`/reviews/${encodeURIComponent(reviewId)}/status`}>진행 기록</Link></nav></div>
      <div className="form-actions"><button type="button" className="button-secondary" onClick={() => window.print()}>PDF 저장·인쇄</button><details className="review-export-menu"><summary>내보내기</summary><button type="button" onClick={() => void downloadJson()} disabled={!reviewId}>결과 JSON 다운로드</button></details></div>
    </header>
    {status.isError ? <ErrorState error={status.error} onRetry={() => void status.refetch()} /> : null}
    {workspace.isPending ? <LoadingState label="검토 결과를 불러오는 중입니다." /> : null}
    {workspace.isError ? <ErrorState error={workspace.error} onRetry={() => void workspace.refetch()} /> : null}
    {omissions.length ? <aside className="state-message" role="alert"><strong>과거 실행 누락 {omissions.length}건 · 재처리 필요</strong><p>모든 대상 항목의 검토가 완료된 상태가 아닙니다.</p></aside> : null}
    {workspace.data?.output_failure_count ? <aside className="state-message" role="alert"><strong>판정 처리 실패 {workspace.data.output_failure_count}건</strong><p>{workspace.data.partial_result_warning}</p><details><summary>실패 항목 확인</summary><ul>{workspace.data.output_failure_pairs?.map((failure,index) => <li key={`${failure.scope_id ?? failure.ad_id}:${failure.item_id}`}>항목 {index+1} · 모델 응답 형식 또는 원문 근거 연결 실패</li>)}</ul></details></aside> : null}
    {workspace.data ? <>
      <ExtractionStatusPanel value={workspace.data.extraction_status} />
      <div className="review-report-summary"><div className="review-ad-summary"><span className="review-document-icon" aria-hidden="true">▤</span><div><h3>{advertisement.data?.advertisementName ?? "광고 검토"}</h3><p>{allRows.length}개 판정 항목 · AI 검토 결과</p><small>최종 판단은 준법 담당자가 확인합니다.</small></div></div>
        <div className="review-stat-cards" aria-label="판정 요약">{VERDICTS.map(verdict => <button type="button" key={verdict} data-verdict={verdict} aria-pressed={filter === verdict} onClick={() => setFilter(filter === verdict ? "ALL" : verdict)}><span>{reviewVerdict(verdict)}</span><strong>{counts[COUNT_KEY[verdict]]}<small>항목</small></strong></button>)}</div>
      </div>
      <div className="review-report-toolbar"><div className="review-view-switch" aria-label="결과 보기 방식"><button type="button" aria-pressed={view === "REPORT"} onClick={() => setView("REPORT")}>항목별 판정</button><button type="button" aria-pressed={view === "ORIGINAL"} onClick={() => setView("ORIGINAL")}>광고 원문·위치</button></div><Link to={`/reviews/${encodeURIComponent(reviewId)}/suggestions`}>추천 문구·수정 초안 →</Link></div>
      <div className="review-report-workspace" data-view={view}>
        {view === "ORIGINAL" ? <OperationalOriginalPanel reviewId={reviewId} token={token} row={selected} /> : <div className="review-item-panel"><header><h3>항목별 판정 <small>{rows.length}건</small></h3><p>광고 문구와 판정을 먼저 확인하고, 항목을 선택해 상세 근거를 보세요.</p></header>
          <div className="verdict-filter" aria-label="판정 상태 필터"><button type="button" aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")}>전체 {counts.total}</button>{VERDICTS.map(verdict => <button type="button" key={verdict} data-verdict={verdict} aria-pressed={filter === verdict} onClick={() => setFilter(verdict)}>{reviewVerdict(verdict)} {counts[COUNT_KEY[verdict]]}</button>)}</div>
          <div className="review-item-tools"><label><span className="sr-only">판정 항목 검색</span><input aria-label="판정 항목 검색" value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="항목·광고 문구 찾기" /></label><label className="inline-check"><input type="checkbox" checked={problemFirst} onChange={event => setProblemFirst(event.target.checked)} />문제 항목 우선</label></div>
          <div className="review-table-scroll" tabIndex={0} aria-label="항목별 판정 목록"><table className="review-item-table"><thead><tr><th>항목</th><th>광고물 내 문구</th><th>판정</th></tr></thead><tbody>{rows.map((row,index) => {
            const rowId = row.row_id ?? row.item_id;
            return <tr key={rowId} tabIndex={0} data-active={rowId === selectedId} className="single-regulation" onFocus={() => setActive(rowId)} onClick={() => setActive(rowId)} onKeyDown={event => {if(event.key === "Enter" || event.key === " "){event.preventDefault();setActive(rowId);}}}>
              <th scope="row"><span className="review-item-number">{String(index+1).padStart(2,"0")}</span><strong>{reviewItemTitle(row)}</strong></th><td><span className="review-table-quote">{row.evidence?.trim() || (row.verdict === "판단불가" ? "원문 확인 필요" : "연결된 문구 없음")}</span></td><td><VerdictBadge value={row.verdict} /></td>
            </tr>;
          })}</tbody></table>{!rows.length ? <p className="review-empty-note">조건에 맞는 판정 항목이 없습니다.</p> : null}</div>
          {workspace.data.template_coverage?.length ? <details className="template-coverage-details"><summary>기준표 전체 항목 처리 내역</summary>{workspace.data.template_coverage.map((coverage,index) => <p key={index}>{coverage.template_section} · 전체 {coverage.rule_count}항목 · 자동 판정 요청 {coverage.requested_count} · 사람 확인 포함 {coverage.manual_review_count} · 처리 기록 누락 {coverage.missing_count}</p>)}</details> : null}
        </div>}
        <div className="review-detail-column">{view === "ORIGINAL" && rows.length ? <label className="review-item-picker">확인할 항목<select value={selectedId} onChange={event => setActive(event.target.value)}>{rows.map(row => <option key={row.row_id ?? row.item_id} value={row.row_id ?? row.item_id}>{reviewVerdict(row.verdict)} · {reviewItemTitle(row)}</option>)}</select></label> : null}{selected ? <OperationalReviewDetail row={selected} reviewId={reviewId} onLocate={() => setView("ORIGINAL")} /> : <p className="review-empty-note">선택할 항목이 없습니다.</p>}</div>
      </div>
    </> : null}
    {humanFinalDecisionEnabled ? <section className="human-final-decision" aria-labelledby="human-final-decision-heading"><div><h3 id="human-final-decision-heading">준법 담당자 최종 판단</h3><p>최종 판단을 기록해도 원래 AI 판정은 변경되지 않습니다.</p></div>
      {workspace.data?.human_decision ? <dl className="human-decision-record"><div><dt>최종 상태</dt><dd>{workspace.data.human_decision.decision === "APPROVED" ? "승인" : "반려"}</dd></div><div><dt>담당자</dt><dd>{workspace.data.human_decision.reviewer_id}</dd></div><div><dt>판단 시각</dt><dd>{new Date(workspace.data.human_decision.decided_at).toLocaleString("ko-KR")}</dd></div>{workspace.data.human_decision.comment ? <div><dt>검토 의견</dt><dd>{workspace.data.human_decision.comment}</dd></div> : null}</dl> : <><label htmlFor="final-decision-comment"><span>검토 의견</span><textarea id="final-decision-comment" value={decisionComment} maxLength={1000} onChange={event => setDecisionComment(event.target.value)} placeholder="반려 시 사유를 반드시 입력해 주세요." /></label>{finalDecision.isError ? <ErrorState error={finalDecision.error} /> : null}<div className="form-actions"><button type="button" className="button-secondary" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("REJECTED")}>반려</button><button type="button" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("APPROVED")}>최종 승인</button></div></>}
    </section> : null}
  </section>;
}
