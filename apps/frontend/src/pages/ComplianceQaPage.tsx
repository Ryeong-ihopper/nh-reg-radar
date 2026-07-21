import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type QaAnswer, type QaQuestionInput } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";
import { ReviewNavigation } from "../components/ReviewNavigation";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";

function QaAnswerPanel({ answer }: { answer: QaAnswer }) {
  return <section className="qa-answer" aria-labelledby="qa-answer-heading">
    <div className="qa-answer-heading"><p className="eyebrow">근거 기반 답변</p><h3 id="qa-answer-heading">{answer.answerSummary}</h3></div>
    <p className="qa-answer-detail">{answer.answerDetail}</p>
    {answer.needsHumanReview ? <p className="state-message state-warning"><strong>담당자 확인이 필요합니다.</strong><br />연결된 기준자료가 충분하지 않아 답변을 최종 판단으로 사용할 수 없습니다.</p> : null}
    <div className="qa-evidence-grid">
      <section aria-labelledby="qa-evidence-heading"><h4 id="qa-evidence-heading">관련 근거</h4>
        {answer.evidences.length > 0 ? <ol className="evidence-results">{answer.evidences.map((evidence) => <li key={evidence.evidenceId}><strong>{evidence.title}</strong>{evidence.articleNo ? <span>{evidence.articleNo}</span> : null}<p>{evidence.matchedText}</p></li>)}</ol> : <p className="state-message">연결된 근거가 없습니다.</p>}
      </section>
      <section aria-labelledby="qa-phrases-heading"><h4 id="qa-phrases-heading">참고 문구</h4>
        {answer.suggestedPhrases.length > 0 ? <ul className="qa-phrase-list">{answer.suggestedPhrases.map((phrase) => <li key={phrase}>{phrase}</li>)}</ul> : <p className="state-message">제안할 참고 문구가 없습니다.</p>}
      </section>
    </div>
  </section>;
}

export function ComplianceQaPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [answer, setAnswer] = useState<QaAnswer | null>(null);
  const summary = useQuery({
    queryKey: ["review-summary", reviewId],
    queryFn: () => api.getReviewSummary(token, reviewId),
    enabled: Boolean(token && reviewId),
    retry: false,
  });
  const advertisement = useQuery({
    queryKey: ["advertisement", summary.data?.advertisementId],
    queryFn: () => api.getAdvertisement(token, summary.data?.advertisementId ?? ""),
    enabled: Boolean(token && summary.data?.advertisementId),
    retry: false,
  });
  const question = useMutation({
    mutationFn: (input: QaQuestionInput) => api.askComplianceQuestion(token, input),
    onSuccess: setAnswer,
  });

  const hasReviewContext = Boolean(summary.data && advertisement.data);
  const contextLabel = hasReviewContext
    ? `${productGroupLabel(advertisement.data!.productGroup)} · ${advertisementTypeLabel(advertisement.data!.advertisementType)} · 기준 적용일 ${summary.data!.standardEffectiveDate}`
    : "검토 맥락을 불러오는 중입니다.";

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const questionText = new FormData(event.currentTarget).get("question")?.toString().trim() ?? "";
    if (!questionText) return;
    question.mutate({
      question: questionText,
      productGroup: advertisement.data?.productGroup ?? null,
      advertisementType: advertisement.data?.advertisementType ?? null,
      standardEffectiveDate: summary.data?.standardEffectiveDate ?? null,
    });
  }

  return <section className="compliance-qa-page" aria-labelledby="compliance-qa-heading">
    <WorkflowSteps current={4} advertisementId={summary.data?.advertisementId} reviewId={reviewId} />
    <PageHeader headingId="compliance-qa-heading" eyebrow="4단계 · 결과 확인" title="광고 규정 Q&A" />
    <ReviewNavigation reviewId={reviewId} />
    <div className="compliance-qa-layout">
      <section className="qa-question-panel" aria-labelledby="qa-question-heading">
        <div><p className="eyebrow">현재 검토 기준</p><h3 id="qa-question-heading">광고 규정에 질문하기</h3></div>
        {summary.isPending || advertisement.isPending ? <LoadingState label="검토 맥락을 불러오는 중입니다." /> : null}
        {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
        {advertisement.isError ? <ErrorState error={advertisement.error} onRetry={() => void advertisement.refetch()} /> : null}
        <p className="qa-context" aria-live="polite">{contextLabel}</p>
        <form onSubmit={submitQuestion} className="qa-question-form">
          <label>질문<textarea name="question" required placeholder="예: 우대금리 문구를 사용할 때 함께 안내해야 할 조건은 무엇인가요?" /></label>
          <button type="submit" disabled={question.isPending}>{question.isPending ? "답변 생성 중..." : "질문하기"}</button>
        </form>
        <p className="panel-note">현재 검토의 상품군·광고유형·기준 적용일을 질문 범위에 자동으로 적용합니다.</p>
      </section>
      <div className="qa-answer-panel">
        {question.isError ? <ErrorState error={question.error} /> : null}
        {answer ? <QaAnswerPanel answer={answer} /> : <section className="qa-empty-state" aria-label="질문 답변 대기"><h3>답변과 근거</h3><p>질문을 입력하면 적용 가능한 기준자료와 함께 답변을 확인할 수 있습니다.</p></section>}
      </div>
    </div>
    <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>결과 요약으로</Link><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/support`}>검토 및 리포트</Link></div>
  </section>;
}
