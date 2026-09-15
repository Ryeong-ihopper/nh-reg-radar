import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, resolveApiUrl } from "../api/client";
import { operationalRequest, type ParserLayout } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { missingSourceLabel, resultEvidenceBoxes, resultCounts, type ResultWorkspace } from "../components/operationalResultModel";
import { ErrorState, LoadingState } from "../components/RequestState";
import { WorkflowSteps } from "../components/WorkflowSteps";

type Verdict = "위반" | "판단불가" | "충족" | "미해당";
type VerdictFilter = "ALL" | Verdict;

const VERDICTS: Verdict[] = ["위반", "판단불가", "충족", "미해당"];
const VERDICT_ORDER: Record<Verdict, number> = { 위반: 0, 판단불가: 1, 충족: 2, 미해당: 3 };
const COUNT_KEY = { 위반: "violation", 판단불가: "unknown", 충족: "compliant", 미해당: "notApplicable" } as const;
const humanFinalDecisionEnabled = import.meta.env.VITE_OPERATIONAL_HUMAN_DECISION === "true";

function isVerdict(value: string): value is Verdict {
  return VERDICTS.includes(value as Verdict);
}

export function OperationalResultsPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [active, setActive] = useState("");
  const [filter, setFilter] = useState<VerdictFilter>("ALL");
  const [pageNo, setPageNo] = useState(1);
  const [previewUrl, setPreviewUrl] = useState("");
  const [zoom, setZoom] = useState(0);
  const [naturalWidth, setNaturalWidth] = useState(0);
  const [followEvidence, setFollowEvidence] = useState(true);
  const [decisionComment, setDecisionComment] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const status = useQuery({ queryKey: ["review-progress", reviewId], queryFn: () => api.getReviewStatus(token, reviewId) });
  const adId = status.data?.advertisementId ?? "";
  const advertisement = useQuery({ queryKey: ["advertisement", adId], queryFn: () => api.getAdvertisement(token, adId), enabled: Boolean(adId) });
  const workspace = useQuery({ queryKey: ["operational-workspace", reviewId], queryFn: () => operationalRequest<ResultWorkspace>(token, `reviews/${reviewId}/workspace`), retry: false });
  const layout = useQuery({ queryKey: ["operational-parser-layout", reviewId], queryFn: () => operationalRequest<ParserLayout>(token, `reviews/${reviewId}/parser-layout`), retry: false });
  const originals = advertisement.data?.files.filter((file) => file.fileType === "ADVERTISEMENT") ?? [];
  const layoutPage = layout.data?.pages.find((page) => page.page_no === pageNo);
  const original = originals.find((file) => file.fileId === layoutPage?.asset_id) ?? originals[0];
  const sourcePageNo = layoutPage?.source_page_no ?? pageNo;
  const preview = useQuery({ queryKey: ["result-preview", original?.fileId, sourcePageNo], queryFn: () => api.getFilePreviewAsset(token, original!.fileId, sourcePageNo), enabled: Boolean(original) });
  const finalDecision = useMutation({
    mutationFn: (decision: "APPROVED" | "REJECTED") => operationalRequest(token, `reviews/${reviewId}/decision`, { decision, comment: decisionComment.trim() }),
    onSuccess: () => void workspace.refetch(),
  });

  useEffect(() => {
    if (!preview.data) return;
    const url = URL.createObjectURL(preview.data.blob);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [preview.data]);

  const allRows = useMemo(() => (workspace.data?.rows ?? [])
    .filter((row): row is typeof row & { verdict: Verdict } => isVerdict(row.verdict))
    .sort((left, right) => VERDICT_ORDER[left.verdict] - VERDICT_ORDER[right.verdict]), [workspace.data]);
  const counts = resultCounts(allRows);
  const reviewCandidateRows = useMemo(() => (workspace.data?.review_candidate_rows ?? [])
    .filter((row): row is typeof row & { verdict: Verdict } => isVerdict(row.verdict)), [workspace.data]);
  const rows = filter === "ALL" ? allRows : allRows.filter((row) => row.verdict === filter);
  const deferred = workspace.data?.deferred_rules ?? [];
  const mapped = useMemo(() => new Map([...allRows, ...reviewCandidateRows].map((row) => [row.row_id ?? row.item_id, resultEvidenceBoxes(row, layout.data)])), [allRows, reviewCandidateRows, layout.data]);
  const currentBoxes = mapped.get(active) ?? [];

  function highlight(id: string) {
    setActive(id);
    const first = mapped.get(id)?.[0];
    if (first && followEvidence) setPageNo(first.pageNo);
  }

  async function downloadJson() {
    const response = await fetch(resolveApiUrl(`/operational/reviews/${encodeURIComponent(reviewId)}/export.json`), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("결과 JSON을 만들지 못했습니다.");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = `review-${reviewId}.json`; link.click();
    URL.revokeObjectURL(url);
  }

  function printResult() {
    window.print();
  }

  function locationLabel(rowId: string, verdict: Verdict, evidence: string) {
    const boxes = mapped.get(rowId) ?? [];
    if (boxes.length) return `광고 원본 근거 위치 ${boxes.length}곳 · ${[...new Set(boxes.map((box) => box.pageNo))].join(", ")}쪽${boxes.some(box => box.precision === "REGION") ? " · 영역 단위 연결 포함(정확한 줄 미확정)" : ""}`;
    const row = [...allRows, ...reviewCandidateRows].find(value => (value.row_id ?? value.item_id) === rowId);
    return row ? missingSourceLabel(row) : missingSourceLabel({item_id:rowId,title:"",question:"",criterion:"",reason:"",verdict,evidence});
  }

  useEffect(() => {
    const first = currentBoxes.find((box) => box.pageNo === pageNo);
    const element = canvas.current;
    if (!first || !element || !followEvidence) return;
    const frame = requestAnimationFrame(() => {
      const image = element.querySelector("img");
      if (image) element.scrollTo({ top: Math.max(0, image.clientHeight * first.bbox[1] / first.height - element.clientHeight * 0.3), behavior: "instant" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, pageNo, previewUrl, currentBoxes, followEvidence, zoom]);

  const reviewState = counts.violation > 0 ? "위반 항목 확인 필요" : counts.unknown > 0 ? "판단불가 항목 확인 필요" : "자동 검토 완료";

  return <section className="single-review" aria-label="AI 검토 결과">
    <WorkflowSteps current={4} advertisementId={adId} reviewId={reviewId} />
    <header className="single-review-header"><div><p className="eyebrow">4단계 · 결과 확인</p><h2>{advertisement.data?.advertisementName ?? "광고 검토"}</h2>
      <p className="panel-note">실제 파서·검색·판정 실행 결과입니다. 규정 카드를 선택하면 광고 원본에서 연결된 근거 문구를 강조합니다.</p></div>
      <div className="form-actions"><button type="button" onClick={() => void downloadJson()} disabled={!reviewId}>결과 JSON 다운로드</button><button type="button" className="button-secondary" onClick={printResult}>PDF 저장·인쇄</button><Link className="button-link button-secondary" to="/advertisements">광고물 목록</Link></div></header>
    {status.isError ? <ErrorState error={status.error} onRetry={() => void status.refetch()} /> : null}
    {workspace.isPending ? <LoadingState label="검토 결과를 불러오는 중입니다." /> : null}
    {workspace.isError ? <ErrorState error={workspace.error} onRetry={() => void workspace.refetch()} /> : null}
    <div className="operational-summary" aria-label="판정 상태 요약">
      <article className="operational-summary-state"><span>검토 상태</span><strong>{reviewState}</strong><small>높음·중간·낮음은 광고의 판정값이 아닙니다. 위반·판단불가 항목을 먼저 확인하는 데만 쓰는 보조 우선순위입니다.</small></article>
      <article><span>위반</span><strong data-verdict="위반">{counts.violation}</strong></article>
      <article><span>판단불가</span><strong data-verdict="판단불가">{counts.unknown}</strong></article>
      <article><span>충족</span><strong data-verdict="충족">{counts.compliant}</strong></article>
      <article><span>미해당</span><strong data-verdict="미해당">{counts.notApplicable}</strong></article>
    </div>
    {workspace.data?.output_failure_count ? <aside className="state-message" role="alert"><strong>판정 처리 실패 {workspace.data.output_failure_count}건</strong><p>{workspace.data.partial_result_warning}</p><details><summary>실패 규칙 확인</summary><ul>{workspace.data.output_failure_pairs?.map((failure) => <li key={`${failure.scope_id ?? failure.ad_id}:${failure.item_id}`}>{failure.item_id} · 모델 응답 형식 또는 원문 근거 연결 실패</li>)}</ul></details></aside> : null}
    <div className="single-review-grid">
      <aside className="single-advertisement"><div className="single-advertisement-toolbar"><strong title={original?.fileName}>광고 원본{original?.fileName ? ` · ${original.fileName}` : ""}</strong>
        <div className="original-navigation"><button aria-label="이전 원본 페이지" disabled={pageNo <= 1} onClick={() => setPageNo((page) => page - 1)}>이전</button>
          <label>페이지 <select aria-label="원본 페이지" value={pageNo} onChange={event => setPageNo(Number(event.target.value))}>{(layout.data?.pages ?? [{page_no:1}]).map(page => <option key={page.page_no} value={page.page_no}>{page.page_no} / {layout.data?.pages.length ?? 1}</option>)}</select></label>
          <button aria-label="다음 원본 페이지" disabled={pageNo >= (layout.data?.pages.length ?? 1)} onClick={() => setPageNo((page) => page + 1)}>다음</button></div></div>
        <div className="original-view-controls"><label>확대 <select aria-label="원본 확대" value={zoom} onChange={event => setZoom(Number(event.target.value))}><option value={0}>화면 폭 맞춤</option><option value={1}>100% · 원본 크기</option><option value={1.5}>150%</option><option value={2}>200%</option></select></label>
          {previewUrl ? <a href={previewUrl} target="_blank" rel="noreferrer">원본 새 탭</a> : null}
          <label className="evidence-follow"><input type="checkbox" checked={followEvidence} onChange={event => setFollowEvidence(event.target.checked)} />근거 자동이동</label></div>
        {preview.isPending ? <LoadingState label="광고 원본을 준비하는 중입니다." /> : null}
        {preview.isError ? <ErrorState error={preview.error} onRetry={() => void preview.refetch()} /> : null}
        {layout.isError ? <p role="status" className="panel-note">근거 위치를 불러오지 못했습니다. 원본은 확인할 수 있습니다. <button onClick={() => void layout.refetch()}>다시 시도</button></p> : null}
        <div className="single-advertisement-scroll" ref={canvas}>
          {previewUrl && !preview.isPending ? <div className="single-advertisement-canvas" style={{width:zoom && naturalWidth ? `${naturalWidth * zoom}px` : "100%"}}><img src={previewUrl} alt="심의 광고 원본" onLoad={event => setNaturalWidth(event.currentTarget.naturalWidth)} />
            {currentBoxes.filter((box) => box.pageNo === pageNo).map((box) => <span data-testid="active-evidence-box" key={box.key} className="review-evidence-highlight" style={{ left: `${box.bbox[0] / box.width * 100}%`, top: `${box.bbox[1] / box.height * 100}%`, width: `${(box.bbox[2] - box.bbox[0]) / box.width * 100}%`, height: `${(box.bbox[3] - box.bbox[1]) / box.height * 100}%` }} />)}
          </div> : null}
        </div><p className="panel-note">작은 글씨는 원본 크기 또는 새 탭에서 확인하세요. 양쪽 목록은 독립적으로 스크롤됩니다. 영역 연결은 정확 줄이 아닌 근사 위치입니다.</p>
      </aside>
      <div className="single-regulations"><header className="single-regulations-heading"><div><h3>규정별 판정 <small>{rows.length}건</small></h3><p>위험도 대신 판정 상태를 기준으로 확인합니다.</p></div></header>
        <div className="verdict-filter" aria-label="판정 상태 필터"><button type="button" aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")}>전체 {counts.total}</button>{VERDICTS.map((verdict) => <button key={verdict} type="button" data-verdict={verdict} aria-pressed={filter === verdict} onClick={() => setFilter(verdict)}>{verdict} {counts[COUNT_KEY[verdict]]}</button>)}</div>
        <div className="single-regulations-scroll" tabIndex={0} aria-label="규정별 판정 목록">
        {rows.map((row) => { const rowId = row.row_id ?? row.item_id; return <article key={rowId} tabIndex={0} data-active={rowId === active} className="single-regulation" onMouseEnter={() => highlight(rowId)} onFocus={() => highlight(rowId)} onClick={() => highlight(rowId)}>
          <header><strong>{row.item_id} · {row.title}</strong><span className="regulation-verdict" data-verdict={row.verdict}>{row.verdict}</span></header>
          {row.question ? <p className="regulation-question">{row.question}</p> : null}
          {row.template_example ? <p className="template-item-detail"><strong>템플릿 참고 문구</strong> {row.template_example}<small>동일 취지의 표현을 허용하며, 예시와의 문구 완전일치를 요구하지 않습니다.</small></p> : null}
          <p>{row.reason}</p>
          {row.rule_basis ? <p className="regulation-basis"><strong>판정 기준</strong> {row.rule_basis.source_type === "INTERNAL_TEMPLATE" ? "내부 심의 템플릿" : "규제목록 v2"} · {row.rule_basis.source_ref}{row.rule_basis.legal_basis_refs.length ? ` · ${row.rule_basis.legal_basis_refs.join(" · ")}` : " · 별도 법령 근거 미기재"}</p> : null}
          <small>{locationLabel(rowId, row.verdict, row.evidence)}</small>
        </article>; })}
        {!rows.length && workspace.data ? <p className="panel-note">이 상태의 판정 항목이 없습니다.</p> : null}
        {reviewCandidateRows.length ? <details className="state-message"><summary>추가 검토 후보 {reviewCandidateRows.length}건</summary>
          <p className="panel-note">템플릿 밖 v2 검색에서 발견됐지만 적용 조건이 확정되지 않은 항목입니다. 정식 판정 집계에는 포함하지 않습니다.</p>
          {reviewCandidateRows.map((row) => { const rowId = row.row_id ?? row.item_id; return <article key={rowId} tabIndex={0} data-active={rowId === active} className="single-regulation" onMouseEnter={() => highlight(rowId)} onFocus={() => highlight(rowId)} onClick={() => highlight(rowId)}>
            <header><strong>{row.item_id} · {row.title}</strong><span className="regulation-verdict" data-verdict={row.verdict}>{row.verdict}</span></header>
            {row.question ? <p className="regulation-question">{row.question}</p> : null}<p>{row.reason}</p><small>{locationLabel(rowId, row.verdict, row.evidence)}</small>
          </article>; })}
        </details> : null}
        {deferred.length ? <details className="panel-note"><summary>판정 미실행 항목 {deferred.length}건 · 사유 구분</summary>
          <p>다른 템플릿 범위 {deferred.filter(row => row.deferred_kind === "OTHER_TEMPLATE").length}건 · 입력·구조 확인 필요 {deferred.filter(row => row.deferred_kind === "INPUT_OR_STRUCTURE").length}건 · 추가 검색 실행 한도 {deferred.filter(row => row.deferred_kind === "EXECUTION_BUDGET").length}건</p>
          <p>실행 한도로 보류된 항목은 미해당이나 충족으로 판정된 것이 아닙니다.</p>
          <ul>{deferred.map((row, index) => <li key={`${row.scope_id}:${row.item_id}:${index}`}>{row.item_id} · {row.deferred_kind === "OTHER_TEMPLATE" ? "선택한 상세 상품군의 템플릿 범위 밖" : row.deferred_kind === "EXECUTION_BUDGET" ? "추가 검색 실행 한도로 미판정" : "입력 또는 원문 구조 확인 필요"}</li>)}</ul>
        </details> : null}
        </div>
      </div>
    </div>
    {humanFinalDecisionEnabled ? <section className="human-final-decision" aria-labelledby="human-final-decision-heading">
      <div><h3 id="human-final-decision-heading">준법 담당자 최종 판단</h3><p>AI 결과와 승인·반려를 분리해 기록하며, 최종 판단을 남겨도 원래 AI 판정은 변경되지 않습니다.</p></div>
      {workspace.data?.human_decision ? <dl className="human-decision-record"><div><dt>최종 상태</dt><dd>{workspace.data.human_decision.decision === "APPROVED" ? "승인" : "반려"}</dd></div><div><dt>담당자</dt><dd>{workspace.data.human_decision.reviewer_id}</dd></div><div><dt>판단 시각</dt><dd>{new Date(workspace.data.human_decision.decided_at).toLocaleString("ko-KR")}</dd></div>{workspace.data.human_decision.comment ? <div><dt>검토 의견</dt><dd>{workspace.data.human_decision.comment}</dd></div> : null}</dl> : <>
        <label htmlFor="final-decision-comment"><span>검토 의견</span><textarea id="final-decision-comment" value={decisionComment} maxLength={1000} onChange={(event) => setDecisionComment(event.target.value)} placeholder="반려 시 사유를 반드시 입력해 주세요." /></label>
        {finalDecision.isError ? <ErrorState error={finalDecision.error} /> : null}
        <div className="form-actions"><button type="button" className="button-secondary" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("REJECTED")}>반려</button><button type="button" disabled={finalDecision.isPending} onClick={() => finalDecision.mutate("APPROVED")}>최종 승인</button></div>
      </>}
    </section> : null}
  </section>;
}
