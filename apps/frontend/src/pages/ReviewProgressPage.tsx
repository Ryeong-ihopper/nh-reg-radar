import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, type ReviewProgress } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";

const TERMINAL_JOB_STATUSES = new Set<ReviewProgress["jobStatus"]>(["COMPLETED", "FAILED", "FAILED_FINAL", "CANCELED"]);

function isQualityWarning(progress: ReviewProgress): boolean {
  return progress.reviewStatus === "CHECK_REQUIRED" || progress.failedReasonCode === "OCR_UNREADABLE";
}

function StatusNotice({ progress }: { progress: ReviewProgress }) {
  if (isQualityWarning(progress)) {
    return <div role="alert" className="state-message state-warning"><strong>담당자 확인이 필요합니다.</strong><p>문구 판독 신뢰도가 낮아 자동 재시도하지 않습니다.</p></div>;
  }
  if (progress.jobStatus === "RETRY_PENDING") {
    return <div role="status" className="state-message state-warning"><strong>자동 재시도 대기 중입니다.</strong><p>{progress.retryCount}/{progress.maxRetries}회 실패 · 다음 시도 {progress.nextRetryAt ? new Date(progress.nextRetryAt).toLocaleString("ko-KR") : "예약 중"}</p></div>;
  }
  if (progress.jobStatus === "STALE") {
    return <div role="alert" className="state-message state-warning"><strong>작업 응답이 지연되고 있습니다.</strong><p>복구 상태를 확인하거나 재분석할 수 있습니다.</p></div>;
  }
  if (progress.jobStatus === "FAILED_FINAL") {
    return <div role="alert" className="state-message state-error"><strong>검토 작업이 최종 실패했습니다.</strong><p>{progress.failedReason ?? "관리자에게 문의해 주세요."}</p></div>;
  }
  if (progress.jobStatus === "FAILED") {
    return <div role="alert" className="state-message state-error"><strong>검토 작업이 실패했습니다.</strong><p>{progress.failedReason ?? "상태를 새로고침해 주세요."}</p></div>;
  }
  if (progress.jobStatus === "COMPLETED") {
    return <div role="status" className="state-message state-success"><strong>검토가 완료되었습니다.</strong><p>진행률 100% · 결과를 확인할 수 있습니다.</p></div>;
  }
  return <div role="status" className="state-message"><strong>AI 검토가 진행 중입니다.</strong><p>상태는 자동으로 갱신됩니다.</p></div>;
}

export function ReviewProgressPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const navigate = useNavigate();
  const progress = useQuery({
    queryKey: ["review-progress", reviewId],
    queryFn: () => api.getReviewStatus(session?.accessToken ?? "", reviewId),
    enabled: Boolean(reviewId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && TERMINAL_JOB_STATUSES.has(data.jobStatus) ? false : 5_000;
    },
  });
  const rerun = useMutation({
    mutationFn: () => api.rerunReview(session?.accessToken ?? "", reviewId, { reason: "사용자 재분석 요청" }),
    onSuccess: ({ newReviewId }) => navigate(`/reviews/${encodeURIComponent(newReviewId)}/status`, { replace: true }),
  });

  const forbidden = progress.isError && progress.error instanceof ApiError && progress.error.status === 403;
  const canRerun = Boolean(progress.data?.isRetryable && ["FAILED", "FAILED_FINAL", "STALE"].includes(progress.data.jobStatus));

  return (
    <section aria-labelledby="review-progress-heading">
      <p className="eyebrow">검토 진행 상태</p>
      <h2 id="review-progress-heading">AI 분석 진행 상태</h2>
      {progress.isPending ? <LoadingState label="검토 진행 상태를 불러오는 중입니다." /> : null}
      {forbidden ? <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>검토 상태를 볼 수 있는 부서 또는 역할인지 확인해 주세요.</p></div> : null}
      {progress.isError && !forbidden ? <ErrorState error={progress.error} onRetry={() => void progress.refetch()} /> : null}
      {progress.data ? (
        <>
          <StatusNotice progress={progress.data} />
          <div className="progress-overview">
            <div><strong>현재 단계</strong><span>{progress.data.currentStep ?? "준비 중"}</span></div>
            <div><strong>작업 상태</strong><span>{progress.data.jobStatus}</span></div>
            <div><strong>진행률</strong><span>{progress.data.progressRate}%</span></div>
          </div>
          <progress aria-label="AI 검토 진행률" max={100} value={progress.data.progressRate}>{progress.data.progressRate}%</progress>
          <ol className="review-steps" aria-label="검토 단계">{progress.data.steps.map((step) => (
            <li key={step.stepCode} data-status={step.status}>
              <strong>{step.stepName}</strong><span>{step.status}</span>
              {step.failedReasonCode ? <small>오류 코드: {step.failedReasonCode}</small> : null}
            </li>
          ))}</ol>
          {rerun.isError ? <ErrorState error={rerun.error} /> : null}
          <div className="form-actions">
            <Link className="button-link button-secondary" to="/advertisements">목록으로</Link>
            <button type="button" className="button-secondary" disabled={progress.isFetching} onClick={() => void progress.refetch()}>{progress.isFetching ? "새로고침 중..." : "새로고침"}</button>
            {canRerun ? <button type="button" disabled={rerun.isPending} onClick={() => rerun.mutate()}>{rerun.isPending ? "재분석 요청 중..." : "재분석"}</button> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
