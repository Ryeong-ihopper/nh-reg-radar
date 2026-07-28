import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type QaAnswer, type QaQuestionInput } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";
import { ReviewNavigation } from "../components/ReviewNavigation";
import { ReviewOriginalPanel } from "../components/ReviewOriginalPanel";
import { WorkflowSteps } from "../components/WorkflowSteps";

type FailedQuestion = { localId: string; question: string };
type OutgoingQuestion = { localId: string; input: QaQuestionInput };

function QaMessageTime({ value }: { value: string }) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return <time className="qa-message-time" dateTime={value}>{parsed.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })}</time>;
}

function QaAnswerMessage({ answer }: { answer: QaAnswer }) {
  return <article className="qa-message qa-message--assistant" aria-label="근거 기반 답변">
    <div className="qa-message-label">규정 안내<QaMessageTime value={answer.createdAt} /></div>
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

// 검토 전환 시 화면 상태를 이어받지 않는 것은 `ReviewScopedBoundary`가 담당한다.
export function ComplianceQaPage() {
  const { reviewId = "" } = useParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const queryClient = useQueryClient();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [failedQuestions, setFailedQuestions] = useState<FailedQuestion[]>([]);
  const messageListRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const outgoingIdRef = useRef(0);
  const summary = useQuery({ queryKey: ["review-summary", reviewId], queryFn: () => api.getReviewSummary(token, reviewId), enabled: Boolean(token && reviewId), retry: false });
  const advertisement = useQuery({ queryKey: ["advertisement", summary.data?.advertisementId], queryFn: () => api.getAdvertisement(token, summary.data?.advertisementId ?? ""), enabled: Boolean(token && summary.data?.advertisementId), retry: false });
  const history = useQuery({ queryKey: ["qa-history", reviewId], queryFn: () => api.listComplianceQuestions(token, reviewId), enabled: Boolean(token && reviewId), retry: false });
  const messages = useMemo(() => {
    const source = history.data ?? [];
    const selectedSession = activeSessionId ?? source.at(-1)?.qaSessionId;
    return selectedSession ? source.filter((message) => message.qaSessionId === selectedSession) : [];
  }, [activeSessionId, history.data]);
  const question = useMutation({
    mutationFn: ({ input }: OutgoingQuestion) => api.askComplianceQuestion(token, input),
    // 진행 중인 이력 조회가 전송 이후에 완료되면 오래된 목록으로 캐시를 덮어써 방금 받은 답변이
    // 사라진다. stale 표시(refetchType: "none")는 이미 떠난 요청을 취소하지 않으므로 먼저 취소한다.
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["qa-history", reviewId] });
    },
    onSuccess: (answer, { localId }) => {
      setActiveSessionId(answer.qaSessionId);
      // 해결된 질문만 지운다. 전체를 비우면 아직 재시도하지 않은 다른 실패 질문이 사라진다.
      setFailedQuestions((current) => current.filter((item) => item.localId !== localId));
      queryClient.setQueryData<QaAnswer[]>(["qa-history", reviewId], (current) => [
        ...(current ?? []).filter((message) => message.qaId !== answer.qaId),
        answer,
      ]);
      // 즉시 refetch하면 위 append와 경쟁해 방금 추가한 답변이 사라져 보일 수 있다. 다음 조회 시점에
      // 서버 이력을 다시 읽도록 stale 표시만 남긴다.
      void queryClient.invalidateQueries({ queryKey: ["qa-history", reviewId], refetchType: "none" });
    },
    // 실패한 질문은 초안을 건드리지 않고 전용 말풍선으로 남긴다. 초안에 되돌리면 그 사이 입력한
    // 내용을 덮어쓰거나, 덮어쓰지 않으려면 실패한 질문을 잃는다. 여러 건이 동시에 미해결일 수
    // 있으므로 식별자로 구분해 누적한다.
    onError: (_error, { localId, input }) => {
      setFailedQuestions((current) => current.some((item) => item.localId === localId)
        ? current
        : [...current, { localId, question: input.question }]);
    },
  });

  // 문서 전체가 아니라 대화 목록 안에서만 스크롤한다. scrollIntoView는 상위 스크롤 컨테이너까지
  // 함께 움직여 상단 탭 바가 밀려 보이므로 사용하지 않는다.
  useEffect(() => {
    if (messages.length === 0 && !question.isPending) return;
    const list = messageListRef.current;
    if (!list) return;
    if (typeof list.scrollTo === "function") list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
    else list.scrollTop = list.scrollHeight;
  }, [messages.length, question.isPending]);

  // 내용에 맞춰 입력창 높이를 늘린다. 상한과 넘침 처리는 CSS(.qa-composer textarea)가 담당한다.
  useEffect(() => {
    const field = draftRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight}px`;
  }, [draft]);

  const hasReviewContext = Boolean(summary.data && advertisement.data);
  const contextLabel = hasReviewContext ? `${productGroupLabel(advertisement.data!.productGroup)} · ${advertisementTypeLabel(advertisement.data!.advertisementType)} · 기준 적용일 ${summary.data!.standardEffectiveDate}` : "검토 맥락을 불러오는 중입니다.";

  // 이력 조회가 끝나기 전에 전송하면 현재 세션을 알 수 없어 불필요한 새 세션이 생기고, 뒤늦게
  // 완료된 조회가 답변을 덮어쓴다.
  const canSend = hasReviewContext && history.isSuccess && !question.isPending;
  // 재시도 중인 질문은 전송 중 말풍선으로 이미 보이므로 실패 목록에서 뺀다.
  const outgoingId = question.isPending ? question.variables?.localId : undefined;
  const pendingFailures = failedQuestions.filter((item) => item.localId !== outgoingId);
  const canSubmit = canSend && draft.trim().length > 0;

  // 재시도는 원래 질문의 식별자를 그대로 쓴다. 성공하면 그 항목만 사라지고, 다시 실패해도
  // 같은 항목이 중복되지 않는다.
  function sendQuestion(questionText: string, localId?: string) {
    if (!canSend || !questionText) return;
    if (localId === undefined) outgoingIdRef.current += 1;
    question.mutate({
      localId: localId ?? `outgoing-${outgoingIdRef.current}`,
      input: { question: questionText, reviewId, qaSessionId: activeSessionId ?? history.data?.at(-1)?.qaSessionId ?? null, productGroup: advertisement.data?.productGroup ?? null, advertisementType: advertisement.data?.advertisementType ?? null, standardEffectiveDate: summary.data?.standardEffectiveDate ?? null },
    });
  }

  function submitDraft() {
    const questionText = draft.trim();
    if (!canSend || !questionText) return;
    setDraft("");
    sendQuestion(questionText);
  }

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitDraft();
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    // 한글 등 IME 조합 중의 Enter는 조합 확정이므로 전송으로 해석하지 않는다.
    if (event.nativeEvent.isComposing) return;
    event.preventDefault();
    submitDraft();
  }

  return <section className="compliance-qa-page" aria-labelledby="compliance-qa-heading">
    <WorkflowSteps current={4} advertisementId={summary.data?.advertisementId} reviewId={reviewId} />
    <PageHeader headingId="compliance-qa-heading" eyebrow="4단계 · 결과 확인" title="광고 규정 Q&A" description="광고 원본을 보며 현재 검토 기준에 대해 질문하고, 근거와 함께 답변을 확인합니다." />
    <ReviewNavigation reviewId={reviewId} />
    {summary.isPending || advertisement.isPending ? <LoadingState label="검토 맥락을 불러오는 중입니다." /> : null}
    {summary.isError ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : null}
    {advertisement.isError ? <ErrorState error={advertisement.error} onRetry={() => void advertisement.refetch()} /> : null}
    <div className="review-workspace review-workspace--qa">
      {advertisement.data ? <ReviewOriginalPanel accessToken={token} advertisement={advertisement.data} /> : null}
      <section className="qa-chat-panel" aria-label="광고 규정 질의응답">
        <header className="qa-chat-header"><div><p className="eyebrow">현재 검토 기준</p><h3>광고 규정에 질문하기</h3></div><p className="qa-context" aria-live="polite">{contextLabel}</p></header>
        {history.isPending ? <LoadingState label="이전 질의응답을 불러오는 중입니다." /> : null}
        {history.isError ? <ErrorState error={history.error} onRetry={() => void history.refetch()} /> : null}
        <div className="qa-message-list" aria-live="polite" ref={messageListRef}>
          {messages.length === 0 && !history.isPending ? <div className="qa-empty-state"><h3>무엇을 확인할까요?</h3><p>예: 우대금리 문구에 함께 표시해야 할 조건은 무엇인가요?</p></div> : null}
          {messages.map((answer) => <div className="qa-turn" key={answer.qaId}><article className="qa-message qa-message--user"><div className="qa-message-label">질문<QaMessageTime value={answer.createdAt} /></div><p>{answer.question}</p></article><QaAnswerMessage answer={answer} /></div>)}
          {question.isPending && question.variables ? <div className="qa-turn">
            <article className="qa-message qa-message--user qa-message--sending" aria-label="전송 중인 질문"><div className="qa-message-label">질문<span className="qa-message-time">전송 중</span></div><p>{question.variables.input.question}</p></article>
            <article className="qa-message qa-message--assistant qa-message--pending" aria-label="답변 생성 중"><div className="qa-message-label">규정 안내</div><p>기준자료를 확인하고 답변을 준비하고 있습니다.</p></article>
          </div> : null}
          {pendingFailures.map((item) => <article className="qa-message qa-message--user qa-message--failed" key={item.localId} aria-label="전송하지 못한 질문">
            <div className="qa-message-label">질문<span className="qa-message-time">전송 실패</span></div>
            <p>{item.question}</p>
            <button type="button" onClick={() => sendQuestion(item.question, item.localId)} disabled={!canSend}>다시 시도</button>
          </article>)}
        </div>
        {question.isError ? <ErrorState error={question.error} /> : null}
        <form onSubmit={submitQuestion} className="qa-composer">
          <label className="visually-hidden" htmlFor="qa-question">질문</label>
          <div className="qa-composer-field">
            <textarea id="qa-question" name="question" ref={draftRef} rows={1} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleDraftKeyDown} aria-describedby="qa-composer-hint" placeholder="광고 문구 또는 표시 방법에 대해 질문해 주세요." />
            <button type="submit" disabled={!canSubmit}>{question.isPending ? "답변 생성 중..." : "질문 보내기"}</button>
          </div>
          <p id="qa-composer-hint" className="qa-composer-hint">Enter로 전송하고 Shift+Enter로 줄을 바꿉니다.{hasReviewContext && history.isSuccess ? "" : " 검토 맥락과 이전 질의응답을 불러온 뒤 질문할 수 있습니다."}</p>
        </form>
      </section>
    </div>
    <div className="form-actions"><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>결과 요약으로</Link><Link className="button-link" to={`/reviews/${encodeURIComponent(reviewId)}/support`}>검토 및 리포트</Link></div>
  </section>;
}
