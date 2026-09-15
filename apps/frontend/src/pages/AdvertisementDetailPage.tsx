import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { FileActions } from "../components/FileActions";
import { ErrorState, LoadingState } from "../components/RequestState";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { advertisementTypeLabel, channelLabel, productGroupLabel, riskLevelLabel } from "../components/displayLabels";
import { operationalMode } from "../api/operational";

function reviewDestination(reviewId: string, status: string): string {
  return ["CHECK_REQUIRED", "REVIEW_COMPLETED"].includes(status)
    ? `/reviews/${encodeURIComponent(reviewId)}/results`
    : `/reviews/${encodeURIComponent(reviewId)}/status`;
}

export function AdvertisementDetailPage() {
  const { advertisementId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { session } = useAuth();
  const query = useQuery({
    queryKey: ["advertisement", advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", advertisementId),
    enabled: Boolean(advertisementId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 403) && count < 1,
  });
  const reviews = useQuery({
    queryKey: ["advertisement-reviews", advertisementId],
    queryFn: () => api.listAdvertisementReviews(session?.accessToken ?? "", advertisementId),
    enabled: Boolean(advertisementId && query.data),
    retry: false,
  });
  const reviewHistory = Array.isArray(reviews.data) ? reviews.data : [];
  const activeReview = reviewHistory.find((review) => ["ANALYSIS_REQUESTED", "ANALYZING"].includes(review.reviewStatus));
  const deleteAdvertisement = useMutation({
    mutationFn: () => api.deleteAdvertisement(session?.accessToken ?? "", advertisementId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["advertisements"] });
      navigate("/advertisements", { replace: true });
    },
  });
  const isSystemAdmin = session?.user.roles.includes("SYSTEM_ADMIN") ?? false;

  return (
    <section className="advertisement-detail-page" aria-labelledby="advertisement-detail-heading">
      {query.isPending ? <LoadingState label="광고물 상세를 불러오는 중입니다." /> : null}
      {query.isError && query.error instanceof ApiError && query.error.status === 403 ? (
        <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>소속 부서와 광고물 접근 범위를 확인해 주세요.</p></div>
      ) : null}
      {query.isError && (!(query.error instanceof ApiError) || query.error.status !== 403) ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data ? <>
        <WorkflowSteps current={2} advertisementId={advertisementId} />
        <header className="advertisement-detail-hero">
          <div><p className="eyebrow">2단계 · 원본 확인</p><h2 id="advertisement-detail-heading">{query.data.advertisementName}</h2></div>
          <div className="detail-hero-actions"><Link className="button-link button-secondary" to="/advertisements">목록으로</Link>{activeReview ? <Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(activeReview.reviewId)}/status`}>AI 검토 진행 중</Link> : <Link className="button-link" to={`/advertisements/${encodeURIComponent(advertisementId)}/reviews/new`}>AI 검토 요청</Link>}{isSystemAdmin ? <button className="button-danger" type="button" disabled={deleteAdvertisement.isPending} onClick={() => {
            if (window.confirm("광고 원본과 연결된 검토 결과를 목록에서 삭제합니다. 계속하시겠습니까?")) {
              deleteAdvertisement.mutate();
            }
          }}>{deleteAdvertisement.isPending ? "삭제 중..." : "광고물 삭제"}</button> : null}</div>
        </header>
        <div className="advertisement-detail-workspace">
          <div className="detail-document-panel"><div className="detail-panel-heading"><h3>광고 원본</h3></div>
            {query.data.files.length === 0 ? <p className="state-message">등록된 파일이 없습니다.</p> : <div className="file-list">{query.data.files.map((file) => <FileActions key={file.fileId} accessToken={session?.accessToken ?? ""} file={file} autoPreview={file.fileType === "ADVERTISEMENT"} />)}</div>}
          </div>
          <aside className="detail-metadata-panel" aria-label="광고물 기본 정보"><h3>기본 정보</h3><dl className="detail-metadata">
            <div><dt>상품군</dt><dd>{productGroupLabel(query.data.productGroup)}</dd></div>
            <div><dt>광고유형</dt><dd>{advertisementTypeLabel(query.data.advertisementType)}</dd></div>
            <div><dt>검토 상태</dt><dd><StatusBadge status={query.data.reviewStatus} /></dd></div>
            {query.data.channelType ? <div><dt>광고채널</dt><dd>{channelLabel(query.data.channelType)}</dd></div> : null}
            {query.data.memo ? <div className="metadata-memo"><dt>메모</dt><dd>{query.data.memo}</dd></div> : null}
          </dl>
          <div className="review-history" aria-labelledby="review-history-heading"><div className="aside-section-heading"><h3 id="review-history-heading">검토 이력</h3><span>{reviewHistory.length}회</span></div>
            {reviews.isPending ? <LoadingState label="검토 이력을 불러오는 중입니다." /> : null}
            {reviews.isError ? <ErrorState error={reviews.error} onRetry={() => void reviews.refetch()} /> : null}
            {!reviews.isPending && !reviews.isError && reviewHistory.length === 0 ? <p className="state-message">아직 요청된 검토가 없습니다.</p> : null}
            {reviewHistory.length > 0 ? <ol>{reviewHistory.slice(0, 5).map((review) => <li key={review.reviewId}><div><strong>{review.reviewRound}차 검토</strong><StatusBadge status={review.reviewStatus} /></div><small>{new Date(review.requestedAt).toLocaleString("ko-KR")}{review.overallRiskLevel ? ` · 위험도 ${riskLevelLabel(review.overallRiskLevel)}` : ""}</small><Link to={reviewDestination(review.reviewId, review.reviewStatus)}>{["CHECK_REQUIRED", "REVIEW_COMPLETED"].includes(review.reviewStatus) ? "결과 확인" : "진행 상태 확인"}</Link></li>)}</ol> : null}
          </div>
          {!operationalMode ? <div className="detail-next-step"><strong>새로운 검토가 필요한가요?</strong><p>원본과 기본 정보를 확인한 뒤 검토 항목과 기준일을 선택합니다.</p><Link to={`/advertisements/${encodeURIComponent(advertisementId)}/reviews/new`}>새 AI 검토 요청</Link></div> : null}</aside>
          {deleteAdvertisement.isError ? <ErrorState error={deleteAdvertisement.error} onRetry={() => deleteAdvertisement.mutate()} /> : null}
        </div>
      </> : null}
    </section>
  );
}
