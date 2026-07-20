import { Link } from "react-router-dom";

const STEPS = [
  { number: 1, label: "광고 등록", description: "광고와 참고자료 등록" },
  { number: 2, label: "원본 확인", description: "파일·기본정보 확인" },
  { number: 3, label: "AI 검토", description: "검토 요청과 진행 확인" },
  { number: 4, label: "결과 확인", description: "위험·근거·조치 검토" },
] as const;

export function WorkflowSteps({
  current,
  advertisementId,
  reviewId,
}: {
  current: 1 | 2 | 3 | 4;
  advertisementId?: string;
  reviewId?: string;
}) {
  const links: Partial<Record<number, string>> = {
    1: "/advertisements/new",
    ...(advertisementId ? { 2: `/advertisements/${encodeURIComponent(advertisementId)}` } : {}),
    ...(reviewId ? {
      3: `/reviews/${encodeURIComponent(reviewId)}/status`,
      4: `/reviews/${encodeURIComponent(reviewId)}/results`,
    } : advertisementId ? { 3: `/advertisements/${encodeURIComponent(advertisementId)}/reviews/new` } : {}),
  };

  return (
    <nav className="workflow-steps" aria-label="광고 심의 업무 단계">
      <ol>{STEPS.map((step) => {
        const state = step.number === current ? "current" : step.number < current ? "complete" : "upcoming";
        const content = <><span className="workflow-step-number" aria-hidden="true">{state === "complete" ? "✓" : step.number}</span><span><strong>{step.label}</strong><small>{step.description}</small></span></>;
        const href = step.number <= current ? links[step.number] : undefined;
        return <li key={step.number} data-state={state} aria-current={state === "current" ? "step" : undefined}>{href ? <Link to={href}>{content}</Link> : <div>{content}</div>}</li>;
      })}</ol>
    </nav>
  );
}
