import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import {
  api,
  ApiError,
  type ReviewAnnotation,
  type ReviewAnnotationSearch,
  type ReviewItemSearch,
  type ReviewType,
} from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ErrorState, LoadingState } from "../components/RequestState";
import { ReviewNavigation } from "../components/ReviewNavigation";
import { ReviewOriginalPanel } from "../components/ReviewOriginalPanel";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { advertisementTypeLabel, annotationStatusLabel, productGroupLabel, reviewTypeLabel } from "../components/displayLabels";

const RISK_LABELS = {
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
  CHECK_REQUIRED: "확인 필요",
} as const;

const RESULT_LABELS = {
  APPROPRIATE: "적정",
  NEEDS_REVISION: "수정 필요",
  NEEDS_CONFIRMATION: "확인 필요",
} as const;

const REVIEW_TYPE_LABELS: Record<ReviewType, string> = {
  REQUIRED_PHRASE: "필수 문구",
  INTEREST_RATE: "금리·조건",
  MISLEADING_EXPRESSION: "위험 표현",
  PRODUCT_CONSISTENCY: "정합성",
  VISIBILITY: "시인성",
  OCR_QUALITY: "OCR 품질",
};

function decisionRuleLabel(rule: string): string {
  if (rule.startsWith("RULE_")) return "규칙 기반 판단";
  if (rule.startsWith("RAG_")) return "기준자료 기반 판단";
  if (rule.startsWith("LLM_")) return "AI 보조 판단";
  return "판단 근거 확인";
}

function ForbiddenState() {
  return <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>검토 결과를 볼 수 있는 부서 또는 역할인지 확인해 주세요.</p></div>;
}

function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}

function EvidenceNotice({ status }: { status: string }) {
  if (status === "SEARCH_UNAVAILABLE") return <p className="evidence-state evidence-failed">근거 검색을 완료하지 못했습니다. 기준자료를 확인해 주세요.</p>;
  if (status === "INSUFFICIENT") return <p className="evidence-state evidence-warning">기준자료 확인 필요</p>;
  if (status === "NOT_REQUIRED") return <p className="evidence-state">규칙 판정 · 근거 연결 불필요</p>;
  return <p className="evidence-state evidence-connected">근거 연결 완료</p>;
}

export function ReviewSummaryPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const summary = useQuery({
    queryKey: ["review-summary", reviewId],
    queryFn: () => api.getReviewSummary(session?.accessToken ?? "", reviewId),
    enabled: Boolean(reviewId),
    retry: false,
  });
  const advertisement = useQuery({
    queryKey: ["advertisement", summary.data?.advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", summary.data?.advertisementId ?? ""),
    enabled: Boolean(summary.data?.advertisementId),
    retry: false,
  });

  return (
    <section aria-labelledby="review-summary-heading">
      <WorkflowSteps current={4} advertisementId={summary.data?.advertisementId} reviewId={reviewId} />
      <PageHeader headingId="review-summary-heading" eyebrow="4단계 · 결과 확인" title="AI 검토 결과" description="위험 항목을 먼저 확인하고 원본·판단 근거·권고 조치를 함께 검토하세요." />
      <ReviewNavigation reviewId={reviewId} />
      {summary.isPending ? <LoadingState label="검토 결과 요약을 불러오는 중입니다." /> : null}
      {summary.isError && isForbidden(summary.error) ? <ForbiddenState /> : null}
      {summary.isError && !isForbidden(summary.error) ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
      {summary.data ? (
        <>
          <div className="review-workspace">
          <div>
          {summary.data && advertisement.isPending ? <LoadingState label="광고 기본정보를 불러오는 중입니다." /> : null}
          {advertisement.isError ? <ErrorState error={advertisement.error} onRetry={() => void advertisement.refetch()} /> : null}
          {advertisement.data ? <div className="table-scroll review-metadata-table-wrap">
            <table className="review-metadata-table" aria-label="광고 기본정보">
              <caption className="visually-hidden">광고 기본정보</caption>
              <tbody>
                <tr><th scope="row">광고명</th><td>{advertisement.data.advertisementName}</td></tr>
                <tr><th scope="row">상품군</th><td>{productGroupLabel(advertisement.data.productGroup)}</td></tr>
                <tr><th scope="row">광고유형</th><td>{advertisementTypeLabel(advertisement.data.advertisementType)}</td></tr>
                <tr><th scope="row">등록자</th><td>{advertisement.data.registeredBy}</td></tr>
                <tr><th scope="row">검토일</th><td>{new Date(summary.data.completedAt).toLocaleString("ko-KR")}</td></tr>
              </tbody>
            </table>
          </div> : null}
          <div className="result-kpis" aria-label="검토 결과 집계">
            <article><span>종합 위험도</span><strong data-risk={summary.data.overallRiskLevel}>{RISK_LABELS[summary.data.overallRiskLevel]}</strong></article>
            <article><span>전체 항목</span><strong>{summary.data.totalItemCount}</strong></article>
            <article><span>수정 필요</span><strong>{summary.data.needsRevisionCount}</strong></article>
            <article><span>확인 필요</span><strong>{summary.data.needsConfirmationCount}</strong></article>
          </div>
          <p className="panel-note">기준 적용일 {summary.data.standardEffectiveDate} · 완료 {new Date(summary.data.completedAt).toLocaleString("ko-KR")}</p>
          <h3>검토 유형별 요약</h3>
          {summary.data.reviewTypeSummary.length === 0 ? <p className="state-message">검토 결과가 없습니다.</p> : (
            <div className="table-scroll"><table><thead><tr><th>검토 유형</th><th>전체</th><th>수정 필요</th><th>확인 필요</th></tr></thead><tbody>{summary.data.reviewTypeSummary.map((item) => (
              <tr key={item.reviewType}><td>{reviewTypeLabel(item.reviewType)}</td><td>{item.totalCount}</td><td>{item.needsRevisionCount}</td><td>{item.needsConfirmationCount}</td></tr>
            ))}</tbody></table></div>
          )}
          <h3>주요 리스크</h3>
          {summary.data.topRisks.length === 0 ? <p>표시할 주요 리스크가 없습니다.</p> : <ul className="risk-list">{summary.data.topRisks.map((risk) => (
            <li key={risk.reviewItemId}>
              <div><strong>{risk.targetText}</strong><span className="risk-badge" data-risk={risk.riskLevel}>{RISK_LABELS[risk.riskLevel]}</span></div>
              <p>{risk.reason}</p><EvidenceNotice status={risk.evidenceStatus} />
              <Link to={`/reviews/${encodeURIComponent(reviewId)}/results/items?reviewItemId=${encodeURIComponent(risk.reviewItemId)}`}>상세 보기</Link>
            </li>
          ))}</ul>}
          <p className="state-message state-warning"><strong>최종 판단 안내</strong><br />AI 검토 결과는 준법심의 지원용이며, 최종 판단은 담당자가 수행해야 합니다.</p>
          <div className="form-actions">
            <Link className="button-link button-secondary" to="/advertisements">광고물 목록</Link>
            <Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/results/items`}>상세 결과 보기</Link>
            <Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/results/annotations`}>광고 화면 보기</Link>
            <Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/support`}>담당자 지원</Link>
            <Link className="button-link" to={`/advertisements/${encodeURIComponent(summary.data.advertisementId)}/comparisons?reviewId=${encodeURIComponent(reviewId)}`}>수정본 비교·재검토</Link>
          </div>
          </div>
          {advertisement.data ? <ReviewOriginalPanel accessToken={session?.accessToken ?? ""} advertisement={advertisement.data} /> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

export function ReviewItemsPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const { search } = useLocation();
  const initialReviewItemId = useMemo(() => new URLSearchParams(search).get("reviewItemId") ?? "", [search]);
  const [selectedId, setSelectedId] = useState(initialReviewItemId);
  const [filters, setFilters] = useState<ReviewItemSearch>({ page: 1, size: 20 });
  const items = useQuery({
    queryKey: ["review-items", reviewId, filters],
    queryFn: () => api.listReviewItems(session?.accessToken ?? "", reviewId, filters),
    enabled: Boolean(reviewId),
    retry: false,
  });
  const detail = useQuery({
    queryKey: ["review-item", reviewId, selectedId],
    queryFn: () => api.getReviewItem(session?.accessToken ?? "", reviewId, selectedId),
    enabled: Boolean(reviewId && selectedId),
    retry: false,
  });

  const reviewProgress = useQuery({
    queryKey: ["review-progress", reviewId],
    queryFn: () => api.getReviewStatus(session?.accessToken ?? "", reviewId),
    enabled: Boolean(reviewId),
    retry: false,
  });
  const advertisement = useQuery({
    queryKey: ["advertisement", reviewProgress.data?.advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", reviewProgress.data?.advertisementId ?? ""),
    enabled: Boolean(reviewProgress.data?.advertisementId),
    retry: false,
  });

  function setFilter(name: keyof ReviewItemSearch, value: string) {
    setFilters((current) => ({ ...current, [name]: value || undefined, page: 1 } as ReviewItemSearch));
  }

  return (
    <section aria-labelledby="review-items-heading">
      <WorkflowSteps current={4} advertisementId={reviewProgress.data?.advertisementId} reviewId={reviewId} />
      <PageHeader headingId="review-items-heading" eyebrow="4단계 · 결과 확인" title="항목별 검토 결과" description="판정 항목을 선택해 수정 권고와 연결된 규정 근거를 확인합니다." />
      <ReviewNavigation reviewId={reviewId} />
      <div className="review-workspace">
      <div>
      <div className="result-filters">
        <label>검토 유형<select value={filters.reviewType ?? ""} onChange={(event) => setFilter("reviewType", event.target.value)}><option value="">전체</option>{Object.entries(REVIEW_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>위험도<select value={filters.riskLevel ?? ""} onChange={(event) => setFilter("riskLevel", event.target.value)}><option value="">전체</option>{Object.entries(RISK_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>판정 결과<select value={filters.resultStatus ?? ""} onChange={(event) => setFilter("resultStatus", event.target.value)}><option value="">전체</option>{Object.entries(RESULT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {items.isPending ? <LoadingState label="상세 검토 결과를 불러오는 중입니다." /> : null}
      {items.isError && isForbidden(items.error) ? <ForbiddenState /> : null}
      {items.isError && !isForbidden(items.error) ? <ErrorState error={items.error} onRetry={() => void items.refetch()} /> : null}
      {items.data?.contents.length === 0 ? <p className="state-message">조건에 맞는 검토 항목이 없습니다.</p> : null}
      {items.data && items.data.contents.length > 0 ? <div className="result-layout"><div className="result-list"><ol>{items.data.contents.map((item) => (
        <li key={item.reviewItemId} data-selected={item.reviewItemId === selectedId}>
          <button type="button" className="result-item-button" onClick={() => setSelectedId(item.reviewItemId)}>
            <strong>{item.targetText}</strong>
            <span className="result-item-chips"><span className="result-chip">{reviewTypeLabel(item.reviewType)}</span><span className="result-chip" data-tone="decision">{RESULT_LABELS[item.resultStatus]}</span><span className="result-chip" data-tone="risk">위험도 {RISK_LABELS[item.riskLevel]}</span></span>
            <span className="result-item-reason">{item.reason}</span>
          </button>
        </li>
      ))}</ol></div><aside className="result-detail" aria-label="선택 검토 항목 상세">
        {!selectedId ? <p>검토 항목을 선택하면 판단 사유와 근거가 표시됩니다.</p> : null}
        {detail.isPending && selectedId ? <LoadingState label="검토 항목 상세를 불러오는 중입니다." /> : null}
        {detail.isError && isForbidden(detail.error) ? <ForbiddenState /> : null}
        {detail.isError && !isForbidden(detail.error) ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : null}
        {detail.data ? <>
          <header className="result-detail-header"><h3>{detail.data.targetText}</h3><div className="result-item-chips"><span className="result-chip">{reviewTypeLabel(detail.data.reviewType)}</span><span className="result-chip" data-tone="decision">{RESULT_LABELS[detail.data.resultStatus]}</span><span className="result-chip" data-tone="risk">위험도 {RISK_LABELS[detail.data.riskLevel]}</span></div></header>
          <p className="result-detail-reason">{detail.data.reason}</p>
          <table className="review-detail-table" aria-label="검토 결과 세부 정보"><tbody><tr><th scope="row">판단 방식</th><td>{decisionRuleLabel(detail.data.riskRationale.scoreDetail.final.decisionRule)}</td></tr><tr><th scope="row">수정 권고</th><td>{detail.data.recommendation ?? "담당자 확인 필요"}</td></tr><tr><th scope="row">근거 상태</th><td><EvidenceNotice status={detail.data.evidenceStatus} /></td></tr></tbody></table>
          <h4>관련 근거</h4>{detail.data.evidences.length === 0 ? <p>연결된 근거가 없습니다.</p> : <ol className="evidence-results">{detail.data.evidences.map((evidence) => <li key={`${evidence.evidenceId}-${evidence.rankNo}`}><strong>{evidence.title}</strong><span>{evidence.matchSource} · {evidence.rankNo}위 · {evidence.relevanceScore.toFixed(4)}</span><p>{evidence.matchedText}</p></li>)}</ol>}
          {detail.data.annotation ? <Link to={`/reviews/${encodeURIComponent(reviewId)}/results/annotations?reviewItemId=${encodeURIComponent(detail.data.reviewItemId)}`}>광고 화면에서 보기</Link> : <p className="panel-note">위치 확인이 필요한 항목입니다.</p>}
        </> : null}
      </aside></div> : null}
      {items.data ? <Pagination page={items.data.page} totalPages={items.data.totalPages} totalElements={items.data.totalElements} onPageChange={(page) => setFilters((current) => ({ ...current, page }))} /> : null}
      <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>요약으로</Link><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/results/annotations`}>광고 화면 보기</Link></div>
      </div>
      {advertisement.data ? <ReviewOriginalPanel accessToken={session?.accessToken ?? ""} advertisement={advertisement.data} focusTarget={detail.data?.annotation?.coordinate ? { normalizedY: detail.data.annotation.coordinate.normalizedY } : undefined} /> : null}
      </div>
    </section>
  );
}

function useObjectUrl(blob: Blob | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return undefined;
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  return url;
}

function AnnotationButton({ annotation, selected, onSelect }: { annotation: ReviewAnnotation; selected: boolean; onSelect: () => void }) {
  return <button type="button" className="annotation-list-button" aria-pressed={selected} onClick={onSelect}><strong>{annotation.targetText}</strong><span>{annotationStatusLabel(annotation.annotationStatus)} · {annotation.locationConfidence?.toFixed(2) ?? "위치 없음"}</span></button>;
}

export function ReviewAnnotationsPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const { search } = useLocation();
  const initialReviewItemId = useMemo(() => new URLSearchParams(search).get("reviewItemId") ?? "", [search]);
  const [selectedId, setSelectedId] = useState(initialReviewItemId);
  const [filters, setFilters] = useState<ReviewAnnotationSearch>({ pageNo: 1 });
  const annotationCanvasRef = useRef<HTMLDivElement>(null);
  const annotations = useQuery({
    queryKey: ["review-annotations", reviewId, filters],
    queryFn: () => api.listReviewAnnotations(session?.accessToken ?? "", reviewId, filters),
    enabled: Boolean(reviewId),
    retry: false,
  });
  const previewSupported = Boolean(annotations.data?.fileId);
  const preview = useQuery({
    queryKey: ["review-annotation-preview", annotations.data?.fileId, filters.pageNo],
    queryFn: () => api.getFilePreviewContent(session?.accessToken ?? "", annotations.data?.fileId ?? "", filters.pageNo ?? 1),
    enabled: previewSupported,
    retry: false,
  });
  const previewUrl = useObjectUrl(preview.data);
  const selected = annotations.data?.annotations.find((annotation) => annotation.reviewItemId === selectedId) ?? null;
  const boxes = annotations.data?.annotations.filter((annotation) => annotation.annotationDisplayMode === "BOX" && annotation.coordinate) ?? [];
  const textHighlights = annotations.data?.annotations.filter((annotation) => annotation.annotationDisplayMode === "TEXT_HIGHLIGHT") ?? [];
  const fallbacks = annotations.data?.annotations.filter((annotation) => annotation.annotationDisplayMode === "LIST_ONLY" || annotation.annotationDisplayMode === "UNAVAILABLE" || (!annotation.coordinate && !annotation.matchedText)) ?? [];
  const lowConfidence = annotations.data?.annotations.filter((annotation) => annotation.annotationStatus === "LOW_CONFIDENCE" || annotation.annotationStatus === "PARTIALLY_LOCATED" || (annotation.locationConfidence !== null && annotation.locationConfidence < 0.8)) ?? [];

  useEffect(() => {
    if (!selected?.coordinate || !previewUrl || !annotationCanvasRef.current) return;
    const canvas = annotationCanvasRef.current;
    const image = canvas.querySelector("img");
    if (!image) return;
    const frame = requestAnimationFrame(() => canvas.scrollTo({ top: Math.max(0, image.scrollHeight * selected.coordinate!.normalizedY - canvas.clientHeight * 0.35), behavior: "smooth" }));
    return () => cancelAnimationFrame(frame);
  }, [previewUrl, selected]);

  function setFilter(name: keyof ReviewAnnotationSearch, value: string) {
    setFilters((current) => ({ ...current, [name]: value ? (name === "pageNo" ? Number(value) : value) : undefined } as ReviewAnnotationSearch));
  }

  return (
    <section aria-labelledby="review-annotations-heading">
      <WorkflowSteps current={4} reviewId={reviewId} />
      <PageHeader headingId="review-annotations-heading" eyebrow="4단계 · 결과 확인" title="검토 위치와 근거 연결" description="광고 원본에서 검토 항목이 발견된 위치를 확인하고 상세 판단으로 이동합니다." />
      <ReviewNavigation reviewId={reviewId} />
      <div className="result-filters"><label>페이지<input type="number" min={1} value={filters.pageNo ?? 1} onChange={(event) => setFilter("pageNo", event.target.value)} /></label><label>검토 유형<select value={filters.reviewType ?? ""} onChange={(event) => setFilter("reviewType", event.target.value)}><option value="">전체</option>{Object.entries(REVIEW_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>위험도<select value={filters.riskLevel ?? ""} onChange={(event) => setFilter("riskLevel", event.target.value)}><option value="">전체</option>{Object.entries(RISK_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      {annotations.isPending ? <LoadingState label="Annotation을 불러오는 중입니다." /> : null}
      {annotations.isError && isForbidden(annotations.error) ? <ForbiddenState /> : null}
      {annotations.isError && !isForbidden(annotations.error) ? <ErrorState error={annotations.error} onRetry={() => void annotations.refetch()} /> : null}
      {annotations.data?.annotations.length === 0 ? <p className="state-message">표시할 Annotation이 없습니다.</p> : null}
      {annotations.data && annotations.data.annotations.length > 0 ? <>
        {lowConfidence.length > 0 ? <aside className="state-message state-warning" aria-label="위치 신뢰도 확인 필요"><strong>위치 확인 필요 {lowConfidence.length}건</strong><ul>{lowConfidence.map((annotation) => <li key={annotation.annotationId}>{annotation.targetText} · {annotation.annotationStatus}</li>)}</ul></aside> : null}
        <div className="annotation-layout"><div className="annotation-preview-panel">
          {preview.isFetching ? <LoadingState label="광고 원본을 불러오는 중입니다." /> : null}
          {preview.isError ? <ErrorState error={preview.error} onRetry={() => void preview.refetch()} /> : null}
          {previewUrl ? <div ref={annotationCanvasRef} className="annotation-canvas" tabIndex={-1} aria-label="광고 원본 위치 미리보기">
            <div className="annotation-media">
              {preview.data?.type === "application/pdf" ? <object data={previewUrl} type="application/pdf" aria-label="PDF 광고 원본 미리보기" /> : <img src={previewUrl} alt="광고 원본 미리보기" />}
              {boxes.map((annotation) => <button key={annotation.annotationId} type="button" className="annotation-box" aria-label={`${annotation.targetText} Annotation`} data-risk={annotation.riskLevel} aria-pressed={annotation.reviewItemId === selectedId} onClick={() => setSelectedId(annotation.reviewItemId)} style={{ left: `${(annotation.coordinate?.normalizedX ?? 0) * 100}%`, top: `${(annotation.coordinate?.normalizedY ?? 0) * 100}%`, width: `${(annotation.coordinate?.normalizedWidth ?? 0) * 100}%`, height: `${(annotation.coordinate?.normalizedHeight ?? 0) * 100}%` }} />)}
            </div>
          </div> : null}
          {textHighlights.length > 0 ? <div className="text-highlight-view"><h3>HWP/HWPX 텍스트 위치</h3>{textHighlights.map((annotation) => <button type="button" key={annotation.annotationId} aria-pressed={annotation.reviewItemId === selectedId} onClick={() => setSelectedId(annotation.reviewItemId)}><mark>{annotation.matchedText ?? annotation.targetText}</mark><span>{annotation.textBlockId} · offset {annotation.normalizedStartOffset}–{annotation.normalizedEndOffset}</span></button>)}</div> : null}
          {!previewSupported ? <p className="state-message">이 파일 형식은 브라우저 미리보기를 지원하지 않습니다. 원본을 다운로드해 확인해 주세요.</p> : null}
          {fallbacks.length > 0 ? <div className="annotation-fallback"><h3>위치 미확정 항목</h3>{fallbacks.map((annotation) => <AnnotationButton key={annotation.annotationId} annotation={annotation} selected={annotation.reviewItemId === selectedId} onSelect={() => setSelectedId(annotation.reviewItemId)} />)}</div> : null}
        </div><aside className="result-detail" aria-label="선택 Annotation 상세">
          {selected ? <><h3>{selected.targetText}</h3><dl className="compact-detail"><div><dt>검토 유형</dt><dd>{selected.reviewType}</dd></div><div><dt>위험도</dt><dd>{RISK_LABELS[selected.riskLevel]}</dd></div><div><dt>표시 상태</dt><dd>{selected.annotationStatus}</dd></div><div><dt>표시 사유</dt><dd>{selected.displayReason}</dd></div></dl><Link to={`/reviews/${encodeURIComponent(reviewId)}/results/items?reviewItemId=${encodeURIComponent(selected.reviewItemId)}`}>판단 사유와 근거 보기</Link></> : <p>Annotation 또는 위치 미확정 항목을 선택하면 상세 정보가 표시됩니다.</p>}
          <h3>전체 Annotation</h3><div className="annotation-list">{annotations.data.annotations.map((annotation) => <AnnotationButton key={annotation.annotationId} annotation={annotation} selected={annotation.reviewItemId === selectedId} onSelect={() => setSelectedId(annotation.reviewItemId)} />)}</div>
        </aside></div>
      </> : null}
      <p className="mobile-review-notice">정밀 Annotation 검토는 PC/노트북 사용을 권장합니다.</p>
      <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>요약으로</Link><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/results/items`}>상세 결과</Link></div>
    </section>
  );
}
