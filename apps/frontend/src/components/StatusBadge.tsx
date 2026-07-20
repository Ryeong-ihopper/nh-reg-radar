const STATUS_LABELS: Record<string, string> = {
  DRAFT: "작성 중",
  UPLOADED: "등록 완료",
  ANALYSIS_REQUESTED: "검토 대기",
  EXTRACTING: "전처리 중",
  ANALYZING: "분석 중",
  CHECK_REQUIRED: "확인 필요",
  REVIEW_COMPLETED: "검토 완료",
  REVIEW_FAILED: "검토 실패",
  REVISED: "수정본 등록",
  COMPARED: "비교 완료",
  REPORT_CREATED: "리포트 생성",
  PENDING: "대기",
  RUNNING: "처리 중",
  RETRY_PENDING: "재시도 대기",
  STALE: "처리 지연",
  COMPLETED: "완료",
  FAILED: "실패",
  FAILED_FINAL: "최종 실패",
  CANCELED: "취소",
  HIGH: "높음",
  MEDIUM: "중간",
  LOW: "낮음",
};

const WARNING = new Set(["CHECK_REQUIRED", "RETRY_PENDING", "STALE", "MEDIUM"]);
const DANGER = new Set(["REVIEW_FAILED", "FAILED", "FAILED_FINAL", "HIGH"]);
const SUCCESS = new Set(["UPLOADED", "REVIEW_COMPLETED", "COMPLETED", "LOW"]);

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? "상태 확인 필요";
}

export function StatusBadge({ status }: { status: string }) {
  const tone = DANGER.has(status) ? "danger" : WARNING.has(status) ? "warning" : SUCCESS.has(status) ? "success" : "info";
  return <span className="status-badge" data-tone={tone}>{statusLabel(status)}</span>;
}
