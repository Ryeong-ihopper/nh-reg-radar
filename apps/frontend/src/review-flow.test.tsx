import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { ReviewProgress } from "./api/client";
import type { AuthSession } from "./auth/context";

const productSession: AuthSession = {
  accessToken: "review-access-token",
  user: {
    userId: "user001",
    userName: "검토 담당자",
    departmentId: "DPT-001",
    departmentName: "상품부",
    roles: ["PRODUCT_DEPARTMENT_USER"],
  },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function progress(overrides: Partial<ReviewProgress> = {}): ReviewProgress {
  return {
    reviewId: "REV-001",
    advertisementId: "ADV-001",
    reviewStatus: "ANALYZING",
    jobId: "JOB-001",
    jobStatus: "RUNNING",
    currentStep: "OCR_TEXT_EXTRACTION",
    progressRate: 35,
    retryCount: 0,
    maxRetries: 3,
    nextRetryAt: null,
    isRetryable: false,
    failedReasonCode: null,
    failedReason: null,
    timeoutAt: "2026-07-14T11:00:00+09:00",
    steps: [
      { stepCode: "FILE_PREPROCESSING", stepName: "파일 전처리", status: "COMPLETED", timeoutAt: null },
      { stepCode: "OCR_TEXT_EXTRACTION", stepName: "OCR 텍스트 추출", status: "RUNNING", timeoutAt: "2026-07-14T10:40:00+09:00" },
    ],
    updatedAt: "2026-07-14T10:36:00+09:00",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("loads advertisement data, submits the frozen review contract, and opens progress", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/advertisements/ADV-001") && !url.endsWith("/reviews")) {
      return response({
        advertisementId: "ADV-001", advertisementName: "예금 광고", productGroup: "SAVINGS",
        advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001",
        registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "UPLOADED", files: [],
      });
    }
    if (url.endsWith("/advertisements/ADV-001/reviews") && init?.method === "POST") {
      return response({
        reviewId: "REV-001", advertisementId: "ADV-001", reviewStatus: "ANALYSIS_REQUESTED",
        jobId: "JOB-001", standardEffectiveDate: "2026-07-14", standardVersionIds: [],
        requestedAt: "2026-07-14T10:36:00+09:00",
      }, 202);
    }
    if (url.endsWith("/reviews/REV-001/status")) return response(progress());
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements/ADV-001/reviews/new"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(screen.getByRole("status")).toHaveTextContent("광고물 정보를 불러오는 중입니다.");
  expect(await screen.findByText("예금 광고")).toBeInTheDocument();
  const today = new Date();
  const localToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  expect(screen.getByLabelText("기준 적용일")).toHaveValue(localToday);
  fireEvent.change(screen.getByLabelText("기준 적용일"), { target: { value: "2026-07-14" } });
  fireEvent.change(screen.getByLabelText("요청 메모"), { target: { value: "우대금리 확인" } });
  fireEvent.click(screen.getByRole("button", { name: "AI 검토 시작" }));

  expect(await screen.findByRole("heading", { name: "AI 검토 진행 상태" })).toBeInTheDocument();
  const post = calls.find((call) => call.url.endsWith("/advertisements/ADV-001/reviews") && call.init?.method === "POST");
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    standardEffectiveDate: "2026-07-14",
    includeSuggestion: true,
    includeOpinionDraft: false,
    requestMemo: "우대금리 확인",
  });
  expect(JSON.parse(String(post?.init?.body)).reviewTypes).toHaveLength(5);
  expect(new Headers(post?.init?.headers).get("Authorization")).toBe("Bearer review-access-token");
});

test("refreshes running progress and stops on completion", async () => {
  let statusCalls = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-001/status")) {
      statusCalls += 1;
      return response(statusCalls === 1 ? progress() : progress({
        reviewStatus: "REVIEW_COMPLETED",
        jobStatus: "COMPLETED",
        currentStep: "COMPLETED",
        progressRate: 100,
        steps: [{ stepCode: "COMPLETED", stepName: "완료", status: "COMPLETED", timeoutAt: null }],
      }));
    }
    if (url.endsWith("/advertisements/ADV-001")) {
      return response({
        advertisementId: "ADV-001", advertisementName: "예금 광고", productGroup: "SAVINGS",
        advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001",
        registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "ANALYZING", files: [],
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(screen.queryByText("화면을 벗어나도 분석은 계속되며, 다시 돌아오면 서버에 저장된 최신 단계부터 확인할 수 있습니다.")).not.toBeInTheDocument();
  expect(await screen.findByRole("progressbar", { name: "AI 검토 진행률" })).toHaveAttribute("value", "35");
  expect(screen.getAllByText("OCR 텍스트 추출")).toHaveLength(2);
  expect(await screen.findByLabelText("광고 원본 병행 검토")).toBeInTheDocument();
  expect(screen.queryByText("다른 화면으로 이동해도 검토는 중단되지 않습니다.")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "AI 검토 진행률" })).toHaveAttribute("value", "35");
  fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
  expect(await screen.findByText("검토가 완료되었습니다.")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "AI 검토 진행률" })).toHaveAttribute("value", "100");
  expect(statusCalls).toBe(2);
});

test("keeps the completed state when a delayed running response follows it", async () => {
  let statusCalls = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-001/status")) {
      statusCalls += 1;
      if (statusCalls === 1) return response(progress());
      if (statusCalls === 2) return response(progress({
        reviewStatus: "REVIEW_COMPLETED",
        jobStatus: "COMPLETED",
        currentStep: "COMPLETED",
        progressRate: 100,
        steps: [{ stepCode: "COMPLETED", stepName: "완료", status: "COMPLETED", timeoutAt: null }],
      }));
      return response(progress());
    }
    if (url.endsWith("/advertisements/ADV-001")) {
      return response({
        advertisementId: "ADV-001", advertisementName: "예금 광고", productGroup: "SAVINGS",
        advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001",
        registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "ANALYZING", files: [],
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);
  await screen.findByRole("progressbar", { name: "AI 검토 진행률" });
  fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
  expect(await screen.findByRole("link", { name: "결과 보기" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
  await waitFor(() => expect(statusCalls).toBe(3));
  expect(screen.getByRole("link", { name: "결과 보기" })).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "AI 검토 진행률" })).toHaveAttribute("value", "100");
  const actions = screen.getByRole("link", { name: "목록으로" }).parentElement;
  expect(actions?.children[0]).toHaveTextContent("목록으로");
  expect(actions?.children[1]).toHaveTextContent("새로고침");
  expect(actions?.children[2]).toHaveTextContent("결과 보기");
});

test.each([
  ["RETRY_PENDING", "자동 재시도 대기 중입니다."],
  ["STALE", "작업 응답이 지연되고 있습니다."],
] as const)("renders the %s recovery state", async (jobStatus, message) => {
  vi.stubGlobal("fetch", vi.fn(async () => response(progress({
    jobStatus,
    retryCount: 1,
    isRetryable: jobStatus === "STALE",
    nextRetryAt: jobStatus === "RETRY_PENDING" ? "2026-07-14T10:40:00+09:00" : null,
  }))));
  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(await screen.findByText(message)).toBeInTheDocument();
  if (jobStatus === "STALE") expect(screen.getByRole("button", { name: "재분석" })).toBeEnabled();
  else expect(screen.queryByRole("button", { name: "재분석" })).not.toBeInTheDocument();
});

test("renders the final failure as a terminal error without exposing result navigation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response(progress({
    reviewStatus: "REVIEW_FAILED",
    jobStatus: "FAILED_FINAL",
    currentStep: "LLM_REVIEW",
    progressRate: 70,
    isRetryable: false,
    failedReasonCode: "LLM_TIMEOUT",
    failedReason: "허용된 재시도 횟수를 초과했습니다.",
  }))));

  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("검토 작업이 최종 실패했습니다.");
  expect(alert).toHaveTextContent("허용된 재시도 횟수를 초과했습니다.");
  expect(screen.queryByRole("link", { name: "결과 보기" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "재분석" })).not.toBeInTheDocument();
});

test("explains unreadable content and automatic retry scope without leaking raw artifact data", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({
    ...progress({ reviewStatus: "CHECK_REQUIRED", jobStatus: "COMPLETED", progressRate: 100, failedReasonCode: "OCR_UNREADABLE" }),
    rawArtifactRef: "parser-artifacts/private/object-key",
    presignedUrl: "https://storage.invalid/secret",
  })));
  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(await screen.findByText("문구 판독 확인이 필요합니다.")).toBeInTheDocument();
  expect(screen.getByText(/자동 재시도는 OCR·Parser·저장소·AI 응답의 일시 오류에만 적용됩니다/)).toBeInTheDocument();
  expect(screen.getByText(/더 선명한 파일을 등록해 재분석해 주세요/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "재분석" })).not.toBeInTheDocument();
  expect(screen.queryByText(/object-key|storage\.invalid/)).not.toBeInTheDocument();
});

test("does not mislabel every check-required result as unreadable content", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response(progress({ reviewStatus: "CHECK_REQUIRED", jobStatus: "COMPLETED", progressRate: 100, failedReasonCode: "REFERENCE_NOT_PROVIDED" }))));

  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);

  expect(await screen.findByText("검토 결과 확인이 필요합니다.")).toBeInTheDocument();
  expect(screen.getByText(/텍스트 품질, 상품 조건 또는 연결된 기준자료가 충분하지 않을 수 있습니다/)).toBeInTheDocument();
  expect(screen.queryByText("문구 판독 확인이 필요합니다.")).not.toBeInTheDocument();
});

test("enables rerun only from isRetryable and follows the immutable new review id", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/reviews/REV-001/rerun")) {
      return response({ newReviewId: "REV-002", previousReviewId: "REV-001", reviewStatus: "ANALYSIS_REQUESTED", jobId: "JOB-002" }, 202);
    }
    if (url.endsWith("/reviews/REV-002/status")) return response(progress({ reviewId: "REV-002", jobId: "JOB-002" }));
    return response(progress({ jobStatus: "FAILED_FINAL", reviewStatus: "REVIEW_FAILED", progressRate: 70, isRetryable: true, failedReason: "처리 시간 초과" }));
  }));
  render(<MemoryRouter initialEntries={["/reviews/REV-001/status"]}><App initialSession={productSession} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "재분석" }));
  expect(await screen.findByText("AI 검토가 진행 중입니다.")).toBeInTheDocument();
  const rerun = calls.find((call) => call.url.endsWith("/reviews/REV-001/rerun"));
  expect(JSON.parse(String(rerun?.init?.body))).toEqual({ reason: "사용자 재분석 요청" });
  expect(calls.some((call) => call.url.endsWith("/reviews/REV-002/status"))).toBe(true);
});

test("renders a redacted permission state for cross-department progress", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ code: "FORBIDDEN", message: "parser-artifacts/private/key", traceId: "req-review-403" }, 403)));
  render(<MemoryRouter initialEntries={["/reviews/REV-OTHER/status"]}><App initialSession={productSession} /></MemoryRouter>);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("접근 권한이 없습니다.");
  expect(alert).not.toHaveTextContent("parser-artifacts");
});
