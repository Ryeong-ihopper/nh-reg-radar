import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "m6-access-token",
  user: { userId: "USR-M6", userName: "M6 담당자", departmentId: "DPT-M6", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("uses the generated M6 client for suggestion decision and immutable report creation", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url.endsWith("/reviews/REV-M6/suggestions")) return response([
      { suggestionId: "SUG-1", reviewItemId: "ITEM-1", originalText: "국내 최고", suggestedText: "경쟁력 있는", suggestionReason: "근거 확인 필요", decisionStatus: "PENDING" },
      { suggestionId: "SUG-2", reviewItemId: "ITEM-2", originalText: "무조건 이득", suggestedText: "조건 충족 시 혜택", suggestionReason: "조건 명시 필요", decisionStatus: "PENDING" },
    ]);
    if (url.endsWith("/reviews/REV-M6/opinion-drafts")) return response([{ draftId: "OPN-1", reviewId: "REV-M6", draftContent: "초안", includedReviewItemIds: [], createdAt: "2026-07-14T10:00:00Z" }]);
    if (url.endsWith("/suggestions/SUG-2/decision")) return response({ suggestionId: "SUG-2", decisionStatus: "MODIFIED_AND_USED", finalText: "수정 문구", updatedAt: "2026-07-14T10:01:00Z" });
    if (url.endsWith("/reviews/REV-M6/reports")) return response({ reportId: "RPT-1", reviewId: "REV-M6", sourceReportId: null, reportType: "FULL", format: "HWPX", reportStatus: "CREATED", snapshotHash: "sha256:test", snapshotVersion: "v1", createdAt: "2026-07-14T10:02:00Z" });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M6/support"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "검토 및 리포트" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "검토 및 리포트" })).toHaveAttribute("href", "/reviews/REV-M6/support");
  expect(await screen.findByText("국내 최고")).toBeInTheDocument();
  expect(screen.getByText("무조건 이득")).toBeInTheDocument();
  const secondSuggestion = screen.getByRole("article", { name: "추천 문구 무조건 이득" });
  expect(within(secondSuggestion).getByText("검토 문구")).toBeInTheDocument();
  expect(within(secondSuggestion).getByText("권고 문구")).toBeInTheDocument();
  expect(within(secondSuggestion).getByText("무조건 이득")).toBeInTheDocument();
  expect(within(secondSuggestion).getByText("조건 충족 시 혜택")).toBeInTheDocument();
  fireEvent.change(within(secondSuggestion).getByLabelText("판단"), { target: { value: "MODIFIED_AND_USED" } });
  fireEvent.change(within(secondSuggestion).getByLabelText("최종 문구"), { target: { value: "수정 문구" } });
  fireEvent.click(within(secondSuggestion).getByRole("button", { name: "담당자 판단 저장" }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/suggestions/SUG-2/decision"))).toBe(true));
  const decision = calls.find((call) => call.url.endsWith("/suggestions/SUG-2/decision"));
  expect(JSON.parse(String(decision?.init?.body))).toEqual({ decisionStatus: "MODIFIED_AND_USED", finalText: "수정 문구" });

  fireEvent.click(screen.getByRole("button", { name: "HWPX 리포트 생성" }));
  expect(await screen.findByText(/리포트가 준비되었습니다/)).toBeInTheDocument();
  expect(screen.queryByText("sha256:test")).not.toBeInTheDocument();
  expect(new Headers(decision?.init?.headers).get("Authorization")).toBe("Bearer m6-access-token");
});

test("provides evidence-backed Q&A as a dedicated fourth-step tab with the current review context", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/reviews/REV-M6/summary")) {
      return response({
        reviewId: "REV-M6", advertisementId: "ADV-M6", standardEffectiveDate: "2026-07-21", standardVersionIds: ["STDV-M6"],
        overallRiskLevel: "LOW", totalItemCount: 1, needsRevisionCount: 0, needsConfirmationCount: 0,
        reviewTypeSummary: [], topRisks: [], completedAt: "2026-07-21T09:00:00Z",
      });
    }
    if (url.endsWith("/advertisements/ADV-M6")) {
      return response({
        advertisementId: "ADV-M6", advertisementName: "예금 광고", productGroup: "DEPOSIT", advertisementType: "BRANCH_FLYER",
        departmentId: "DPT-M6", registeredBy: "USR-M6", registeredAt: "2026-07-21T09:00:00Z", reviewStatus: "REVIEW_COMPLETED", files: [],
      });
    }
    if (url.endsWith("/qa/questions?reviewId=REV-M6")) return response([]);
    if (url.endsWith("/qa/questions")) {
      return response({
        qaId: "QA-1", qaSessionId: "QAS-1", question: "우대금리 문구를 사용할 수 있나요?", createdAt: "2026-07-21T09:01:00Z",
        answerSummary: "조건을 함께 표시해야 합니다.", answerDetail: "우대 조건과 적용 기준을 광고물에 명확히 기재해 주세요.",
        evidences: [{ evidenceId: "EVD-1", standardVersionId: "STDV-M6", title: "예금상품 광고 기준", matchedText: "우대 조건을 명시한다." }],
        suggestedPhrases: ["조건 충족 시 우대 혜택을 제공받을 수 있습니다."], needsHumanReview: false,
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M6/results/qa"]}><App initialSession={session} /></MemoryRouter>);

  expect(await screen.findByRole("heading", { name: "광고 규정 Q&A" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "광고 규정 Q&A" })).toHaveAttribute("href", "/reviews/REV-M6/results/qa");
  expect(await screen.findByText("예금 · 영업점 전단 · 기준 적용일 2026-07-21")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("질문"), { target: { value: "우대금리 문구를 사용할 수 있나요?" } });
  fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

  expect(await screen.findByText("조건을 함께 표시해야 합니다.")).toBeInTheDocument();
  expect(screen.getByText("예금상품 광고 기준")).toBeInTheDocument();
  expect(screen.getByText("조건 충족 시 우대 혜택을 제공받을 수 있습니다.")).toBeInTheDocument();
  const request = calls.find((call) => call.url.endsWith("/qa/questions"));
  expect(JSON.parse(String(request?.init?.body))).toEqual({
    question: "우대금리 문구를 사용할 수 있나요?",
    productGroup: "DEPOSIT",
    advertisementType: "BRANCH_FLYER",
    standardEffectiveDate: "2026-07-21",
    reviewId: "REV-M6",
    qaSessionId: null,
  });
});

test("requires final text for a modified suggestion before mutating the contract", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-M6/suggestions")) return response([{ suggestionId: "SUG-1", reviewItemId: "ITEM-1", originalText: "국내 최고", suggestedText: "경쟁력 있는", decisionStatus: "PENDING" }]);
    if (url.endsWith("/reviews/REV-M6/opinion-drafts")) return response([{ draftId: "OPN-1", reviewId: "REV-M6", draftContent: "초안", includedReviewItemIds: [], createdAt: "2026-07-14T10:00:00Z" }]);
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter initialEntries={["/reviews/REV-M6/support"]}><App initialSession={session} /></MemoryRouter>);
  await screen.findByText("국내 최고");
  fireEvent.change(screen.getByLabelText("판단"), { target: { value: "MODIFIED_AND_USED" } });
  fireEvent.click(screen.getByRole("button", { name: "담당자 판단 저장" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("수정 후 사용에는 최종 문구가 필요합니다.");
  expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/decision"))).toBe(false);
});

test("explains how to continue when a completed review has no prepared suggestions", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-M6/suggestions")) return response([]);
    if (url.endsWith("/reviews/REV-M6/opinion-drafts")) return response([]);
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M6/support"]}><App initialSession={session} /></MemoryRouter>);

  expect(await screen.findByText(/현재 검토에 준비된 추천 문구가 없습니다/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "항목별 검토 결과로 이동" })).toHaveAttribute("href", "/reviews/REV-M6/results/items");
});

test("registers an uploaded revision before comparison and reanalysis", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/advertisements/ADV-M6/revisions")) {
      return response({ advertisementId: "ADV-M6", revisionId: "REVISION-M6-2", reviewStatus: "REVISED" }, 201);
    }
    if (url.endsWith("/advertisements/ADV-M6/comparisons")) {
      return response({ comparisonId: "CMP-M6", advertisementId: "ADV-M6", comparisonStatus: "COMPLETED", resolvedIssueCount: 1, unresolvedIssueCount: 0, newIssueCount: 0, items: [] });
    }
    if (url.endsWith("/reviews/REV-M6/rerun")) {
      return response({ newReviewId: "REV-M6-2", previousReviewId: "REV-M6", reviewStatus: "ANALYSIS_REQUESTED", jobId: "JOB-M6-2" }, 202);
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements/ADV-M6/comparisons?reviewId=REV-M6"]}><App initialSession={session} /></MemoryRouter>);
  expect(document.querySelector<HTMLInputElement>("input[name=baseReviewId]")?.value).toBe("REV-M6");
  fireEvent.change(screen.getByLabelText("수정 메모"), { target: { value: "확정 표현 완화" } });
  const file = new File(["png"], "revised.png", { type: "image/png" });
  fireEvent.change(screen.getByLabelText("수정 광고 파일"), { target: { files: [file] } });
  const submit = screen.getByRole("button", { name: "수정본 등록 후 비교·재검토" });
  fireEvent.submit(submit.closest("form") as HTMLFormElement);

  expect(await screen.findByText("수정본 등록과 재검토 요청이 완료되었습니다.")).toBeInTheDocument();
  expect(screen.queryByText("REVISION-M6-2")).not.toBeInTheDocument();
  expect(screen.queryByText("REV-M6-2")).not.toBeInTheDocument();
  expect(calls.map((call) => new URL(call.url, "http://test").pathname)).toEqual([
    "/api/v1/advertisements/ADV-M6/revisions",
    "/api/v1/advertisements/ADV-M6/comparisons",
    "/api/v1/reviews/REV-M6/rerun",
  ]);
  const revisionBody = calls[0]?.init?.body;
  expect(revisionBody).toBeInstanceOf(FormData);
  expect((revisionBody as FormData).get("revisionMemo")).toBe("확정 표현 완화");
  expect((revisionBody as FormData).get("revisedAdvertisementFile")).toBe(file);
  expect(JSON.parse(String(calls[1]?.init?.body))).toEqual({ baseReviewId: "REV-M6", revisionId: "REVISION-M6-2" });
  expect(JSON.parse(String(calls[2]?.init?.body))).toEqual({ reason: "수정본 REVISION-M6-2 등록 후 재검토" });
});
