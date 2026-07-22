import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type QaAnswer, type QaQuestionInput } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";
import { ErrorState, LoadingState } from "../components/RequestState";
import { ReviewNavigation } from "../components/ReviewNavigation";
import { ReviewOriginalPanel } from "../components/ReviewOriginalPanel";
import { WorkflowSteps } from "../components/WorkflowSteps";

function QaAnswerMessage({ answer }: { answer: QaAnswer }) {
  return <article className="qa-message qa-message--assistant" aria-label="근거 기반 답변">
    <div className="qa-message-label">규정 안내</div>
    <h3>{answer.answerSummary}</h3>
    <p className="qa-answer-detail">{answer.answerDetail}</p>
    {answer.needsHumanReview ? <p className="state-message state-warning"><strong>담당자 확인이 필요합니다.</strong><br />연결된 기준자료가 충분하지 않아 답변을 최종 판단으로 사용할 수 없습니다.</p> : null}
    <section className="qa-evidence-section" aria-labelledby={`qa-evidence-${answer.qaId}`}>
      <h4 id={`qa-evidence-${answer.qaId}`}>관련 근거</h4>
      {answer.evidences.length > 0 ? <ol className="evidence-results">{answer.evidences.map((evidence) => <li key={evidence.evidenceId}><strong>{evidence.title}</strong>{evidence.articleNo ? <span>{evidence.articleNo}</span> : null}<p>{evidence.matchedText}</p></li>)}</ol> : <p className="qa-inline-empty">연결된 근거가 없습니다.</p>}
    </section>
    {answer.suggestedPhrases.length > 0 ? <section className="qa-evidence-section" aria-labelledby={`qa-phrases-${answer.qaId}`}><h4 id={`qa-phrases-${answer.qaId}`}>참고 문구</h4><ul className="qa-phrase-list">{answer.suggestedPhrases.map((phrase) => <li key={phrase}>{phrase}</li>)}</ul></section> : null}
  </article>;
}

export function ComplianceQaPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const queryClient = useQueryClient();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const summary = useQuery({ queryKey: ["review-summary", reviewId], queryFn: () => api.getReviewSummary(token, reviewId), enabled: Boolean(token && reviewId), retry: false });
  const advertisement = useQuery({ queryKey: ["advertisement", summary.data?.advertisementId], queryFn: () => api.getAdvertisement(token, summary.data?.advertisementId ?? ""), enabled: Boolean(token && summary.data?.advertisementId), retry: false });
  const history = useQuery({ queryKey: ["qa-history", reviewId], queryFn: () => api.listComplianceQuestions(token, reviewId), enabled: Boolean(token && reviewId), retry: false });
  const messages = useMemo(() => {
    const source = history.data ?? [];
    const selectedSession = activeSessionId ?? source.at(-1)?.qaSessionId;
    return selectedSession ? source.filter((message) => message.qaSessionId === selectedSession) : [];
  }, [activeSessionId, history.data]);
  const question = useMutation({
    mutationFn: (input: QaQuestionInput) => api.askComplianceQuestion(token, input),
    onSuccess: async (answer) => {
      setActiveSessionId(answer.qaSessionId);
      await queryClient.invalidateQueries({ queryKey: ["qa-history", reviewId] });
      queryClient.setQueryData<QaAnswer[]>(["qa-history", reviewId], (current) => [
        ...(current ?? []).filter((message) => message.qaId !== answer.qaId),
        answer,
      ]);
    },
  });

  useEffect(() => {
    const scroll = chatEndRef.current?.scrollIntoView;
    if (typeof scroll === "function") scroll.call(chatEndRef.current, { block: "end", behavior: "smooth" });
  }, [messages.length, question.isPending]);

  const hasReviewContext = Boolean(summary.data && advertisement.data);
  const contextLabel = hasReviewContext ? `${productGroupLabel(advertisement.data!.productGroup)} · ${advertisementTypeLabel(advertisement.data!.advertisementType)} · 기준 적용일 ${summary.data!.standardEffectiveDate}` : "검토 맥락을 불러오는 중입니다.";

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const questionText = new FormData(form).get("question")?.toString().trim() ?? "";
    if (!questionText) return;
    form.reset();
    question.mutate({ question: questionText, reviewId, qaSessionId: activeSessionId ?? history.data?.at(-1)?.qaSessionId ?? null, productGroup: advertisement.data?.productGroup ?? null, advertisementType: advertisement.data?.advertisementType ?? null, standardEffectiveDate: summary.data?.standardEffectiveDate ?? null });
  }

  return <section className="compliance-qa-page" aria-labelledby="compliance-qa-heading">
    <WorkflowSteps current={4} advertisementId={summary.data?.advertisementId} reviewId={reviewId} />
    <header className="qa-page-heading"><div><p className="eyebrow">4단계 · 결과 확인</p><h2 id="compliance-qa-heading">광고 규정 Q&A</h2><p>광고 원본을 보며 현재 검토 기준에 대해 질문하고, 근거와 함께 답변을 확인합니다.</p></div><ReviewNavigation reviewId={reviewId} /></header>
    {summary.isPending || advertisement.isPending ? <LoadingState label="검토 맥락을 불러오는 중입니다." /> : null}
    {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
    {advertisement.isError ? <ErrorState error={advertisement.error} onRetry={() => void advertisement.refetch()} /> : null}
    <div className="review-workspace review-workspace--qa">
      {advertisement.data ? <ReviewOriginalPanel accessToken={token} advertisement={advertisement.data} /> : null}
      <section className="qa-chat-panel" aria-label="광고 규정 질의응답">
        <header className="qa-chat-header"><div><p className="eyebrow">현재 검토 기준</p><h3>광고 규정에 질문하기</h3></div><p className="qa-context" aria-live="polite">{contextLabel}</p></header>
        {history.isPending ? <LoadingState label="이전 질의응답을 불러오는 중입니다." /> : null}
        {history.isError ? <ErrorState error={history.error} onRetry={() => void history.refetch()} /> : null}
        <div className="qa-message-list" aria-live="polite">
          {messages.length === 0 && !history.isPending ? <div className="qa-empty-state"><h3>무엇을 확인할까요?</h3><p>예: 우대금리 문구에 함께 표시해야 할 조건은 무엇인가요?</p></div> : null}
          {messages.map((answer) => <div className="qa-turn" key={answer.qaId}><article className="qa-message qa-message--user"><div className="qa-message-label">질문</div><p>{answer.question}</p></article><QaAnswerMessage answer={answer} /></div>)}
          {question.isPending ? <article className="qa-message qa-message--assistant qa-message--pending" aria-label="답변 생성 중"><div className="qa-message-label">규정 안내</div><p>기준자료를 확인하고 답변을 준비하고 있습니다.</p></article> : null}
          <div ref={chatEndRef} />
        </div>
        {question.isError ? <ErrorState error={question.error} /> : null}
        <form onSubmit={submitQuestion} className="qa-composer"><label className="visually-hidden" htmlFor="qa-question">질문</label><textarea id="qa-question" name="question" required placeholder="광고 문구 또는 표시 방법에 대해 질문해 주세요." /><button type="submit" disabled={question.isPending || !hasReviewContext}>{question.isPending ? "답변 생성 중..." : "질문 보내기"}</button></form>
      </section>
    </div>
    <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>결과 요약으로</Link><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/support`}>검토 및 리포트</Link></div>
  </section>;
}
