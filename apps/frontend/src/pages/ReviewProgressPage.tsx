import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, resolveApiUrl, type ReviewProgress } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { PageHeader } from "../components/PageHeader";
import { ReviewOriginalPanel } from "../components/ReviewOriginalPanel";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { cancelOperationalReview, operationalMode } from "../api/operational";

const TERMINAL_JOB_STATUSES = new Set<ReviewProgress["jobStatus"]>(["COMPLETED", "FAILED", "FAILED_FINAL", "CANCELED"]);

function currentStepLabel(progress: ReviewProgress): string {
  return progress.steps.find((step) => step.stepCode === progress.currentStep)?.stepName
    ?? progress.currentStep
    ?? "준비 중";
}

function StatusNotice({ progress }: { progress: ReviewProgress }) {
  if (progress.failedReasonCode === "OCR_UNREADABLE") {
    return <div role="alert" className="state-message state-warning"><strong>문구 판독 확인이 필요합니다.</strong><p>자동 재시도는 OCR·Parser·저장소·AI 응답의 일시 오류에만 적용됩니다. 현재는 문구를 신뢰성 있게 읽기 어려우므로 원본 품질을 확인하거나 더 선명한 파일을 등록해 재분석해 주세요.</p></div>;
  }
  if (progress.reviewStatus === "CHECK_REQUIRED") {
    return <div role="alert" className="state-message state-warning"><strong>검토 결과 확인이 필요합니다.</strong><p>텍스트 품질, 상품 조건 또는 연결된 기준자료가 충분하지 않을 수 있습니다. 원본과 결과를 함께 확인해 주세요.</p></div>;
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
  if (progress.jobStatus === "CANCELED") {
    return <div role="status" className="state-message state-warning"><strong>검토 중단이 요청되었습니다.</strong><p>현재 호출 중인 파서 또는 모델 작업이 끝난 뒤 결과 저장 없이 종료됩니다.</p></div>;
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
  const queryClient = useQueryClient();
  const [terminalProgress, setTerminalProgress] = useState<ReviewProgress | null>(null);
  const progress = useQuery({
    queryKey: ["review-progress", reviewId],
    queryFn: () => api.getReviewStatus(session?.accessToken ?? "", reviewId),
    enabled: Boolean(reviewId),
    retry: false,
    // SSE delivers normal updates. Keep a slow fallback for proxies or browsers
    // that cannot retain a streaming response.
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && TERMINAL_JOB_STATUSES.has(data.jobStatus) ? false : 30_000;
    },
  });
  useEffect(() => {
    if (!reviewId || !session?.accessToken) return;
    const controller = new AbortController();
    let buffered = "";
    const publish = (payload: string) => {
      try {
        const value = JSON.parse(payload) as ReviewProgress;
        queryClient.setQueryData(["review-progress", reviewId], value);
        if (TERMINAL_JOB_STATUSES.has(value.jobStatus)) controller.abort();
      } catch {
        // Ignore one malformed event; the regular fallback query remains available.
      }
    };
    void fetch(resolveApiUrl(`/reviews/${encodeURIComponent(reviewId)}/events`), {
      headers: { Authorization: `Bearer ${session.accessToken}`, Accept: "text/event-stream" },
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok || !response.body) throw new Error("SSE_CONNECTION_FAILED");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (!controller.signal.aborted) {
        const next = await reader.read();
        if (next.done) break;
        buffered += decoder.decode(next.value, { stream: true });
        const events = buffered.split("\n\n");
        buffered = events.pop() ?? "";
        events.forEach((event) => {
          const data = event.split("\n").find((line) => line.startsWith("data: "));
          if (data) publish(data.slice(6));
        });
      }
    }).catch(() => {
      // Polling remains intentionally silent fallback; the page must work through
      // a buffering proxy or a temporarily unavailable SSE connection.
    });
    return () => controller.abort();
  }, [queryClient, reviewId, session?.accessToken]);
  useEffect(() => {
    setTerminalProgress(null);
  }, [reviewId]);
  useEffect(() => {
    if (!progress.data || !TERMINAL_JOB_STATUSES.has(progress.data.jobStatus)) return;
    setTerminalProgress((current) => current?.reviewId === reviewId ? current : progress.data);
  }, [progress.data, reviewId]);
  const displayedProgress = terminalProgress?.reviewId === reviewId ? terminalProgress : progress.data;
  const advertisement = useQuery({
    queryKey: ["advertisement", displayedProgress?.advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", displayedProgress?.advertisementId ?? ""),
    enabled: Boolean(displayedProgress?.advertisementId),
    retry: false,
  });
  const rerun = useMutation({
    mutationFn: () => api.rerunReview(session?.accessToken ?? "", reviewId, { reason: "사용자 재분석 요청" }),
    onSuccess: ({ newReviewId }) => navigate(`/reviews/${encodeURIComponent(newReviewId)}/status`, { replace: true }),
  });
  const cancel = useMutation({
    mutationFn: () => cancelOperationalReview(session?.accessToken ?? "", reviewId),
    onSuccess: () => void progress.refetch(),
  });

  const forbidden = progress.isError && progress.error instanceof ApiError && progress.error.status === 403;
  const canRerun = Boolean(displayedProgress?.isRetryable && ["FAILED", "FAILED_FINAL", "STALE"].includes(displayedProgress.jobStatus));

  return (
    <section aria-labelledby="review-progress-heading">
      <WorkflowSteps current={3} advertisementId={displayedProgress?.advertisementId} reviewId={reviewId} />
      <PageHeader
        headingId="review-progress-heading"
        eyebrow="3단계 · AI 검토"
        title="AI 검토 진행 상태"
      />
      {progress.isPending ? <LoadingState label="검토 진행 상태를 불러오는 중입니다." /> : null}
      {forbidden ? <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>검토 상태를 볼 수 있는 부서 또는 역할인지 확인해 주세요.</p></div> : null}
      {progress.isError && !forbidden ? <ErrorState error={progress.error} onRetry={() => void progress.refetch()} /> : null}
      {displayedProgress ? (
        <div className="review-workspace review-workspace--execution">
          <div>
          <StatusNotice progress={displayedProgress} />
          {operationalMode ? <p className="fieldset-description">진행률은 완료한 단계 수 기준이며 남은 시간 비율이 아닙니다. 파싱·Gemma 판정 중에는 같은 단계에서 수 분 머무를 수 있습니다.</p> : null}
          <div className="progress-overview">
            <div><strong>현재 단계</strong><span>{currentStepLabel(displayedProgress)}</span></div>
            <div><strong>작업 상태</strong><span><StatusBadge status={displayedProgress.jobStatus} /></span></div>
            <div><strong>진행률</strong><span>{displayedProgress.progressRate}%</span></div>
          </div>
          <progress aria-label="AI 검토 진행률" max={100} value={displayedProgress.progressRate}>{displayedProgress.progressRate}%</progress>
          <ol className="review-steps" aria-label="검토 단계">{displayedProgress.steps.map((step) => (
            <li key={step.stepCode} data-status={step.status}>
              <strong>{step.stepName}</strong><StatusBadge status={step.status} />
              {step.failedReasonCode ? <small>오류 코드: {step.failedReasonCode}</small> : null}
            </li>
          ))}</ol>
          {rerun.isError ? <ErrorState error={rerun.error} /> : null}
          {cancel.isError ? <ErrorState error={cancel.error} /> : null}
          <div className="form-actions">
            <Link className="button-link button-secondary" to="/advertisements">목록으로</Link>
            {!operationalMode ? <button type="button" className="button-secondary" disabled={progress.isFetching} onClick={() => void progress.refetch()}>{progress.isFetching ? "새로고침 중..." : "새로고침"}</button> : null}
            {displayedProgress.jobStatus === "COMPLETED" ? <Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>결과 보기</Link> : null}
            {operationalMode && !TERMINAL_JOB_STATUSES.has(displayedProgress.jobStatus) ? <button className="button-danger" type="button" disabled={cancel.isPending} onClick={() => {
              if (window.confirm("현재 검토를 중단할까요? 현재 호출 중인 파서·모델 작업은 종료 시점까지 남을 수 있지만 결과는 저장하지 않습니다.")) cancel.mutate();
            }}>{cancel.isPending ? "중단 요청 중…" : "검토 중단"}</button> : null}
            {canRerun ? <button type="button" disabled={rerun.isPending} onClick={() => rerun.mutate()}>{rerun.isPending ? "재분석 요청 중..." : "재분석"}</button> : null}
          </div>
          </div>
          {advertisement.data ? <ReviewOriginalPanel accessToken={session?.accessToken ?? ""} advertisement={advertisement.data} /> : null}
        </div>
      ) : null}
    </section>
  );
}
