import { ApiError, userMessage } from "../api/client";

export function LoadingState({ label = "불러오는 중입니다." }: { label?: string }) {
  return <p role="status" className="state-message">{label}</p>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const traceId = error instanceof ApiError ? error.traceId : undefined;
  return (
    <div role="alert" className="state-message state-error">
      <strong>{userMessage(error)}</strong>
      {traceId ? <small>문의 추적 번호: {traceId}</small> : null}
      {onRetry ? <button type="button" onClick={onRetry}>다시 시도</button> : null}
    </div>
  );
}
