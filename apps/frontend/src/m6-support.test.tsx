import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("uses the generated M6 client for suggestion decision, evidence-backed Q&A, and immutable report creation", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url.endsWith("/reviews/REV-M6/suggestions")) return response({ suggestionId: "SUG-1", reviewItemId: "ITEM-1", originalText: "국내 최고", suggestedText: "경쟁력 있는", suggestionReason: "근거 확인 필요", decisionStatus: "PENDING" });
    if (url.endsWith("/reviews/REV-M6/opinion-drafts")) return response({ draftId: "OPN-1", reviewId: "REV-M6", draftContent: "초안", includedReviewItemIds: [], createdAt: "2026-07-14T10:00:00Z" });
    if (url.endsWith("/suggestions/SUG-1/decision")) return response({ suggestionId: "SUG-1", decisionStatus: "MODIFIED_AND_USED", finalText: "수정 문구", updatedAt: "2026-07-14T10:01:00Z" });
    if (url.endsWith("/qa/questions")) return response({ qaId: "QA-1", answerSummary: "확인이 필요합니다", answerDetail: "기준 근거를 확인하세요.", evidences: [], suggestedPhrases: [], needsHumanReview: true });
    if (url.endsWith("/reviews/REV-M6/reports")) return response({ reportId: "RPT-1", reviewId: "REV-M6", sourceReportId: null, reportType: "FULL", format: "HWPX", reportStatus: "CREATED", snapshotHash: "sha256:test", snapshotVersion: "v1", createdAt: "2026-07-14T10:02:00Z" });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M6/support"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText("국내 최고")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("판단"), { target: { value: "MODIFIED_AND_USED" } });
  fireEvent.change(screen.getByLabelText("최종 문구"), { target: { value: "수정 문구" } });
  fireEvent.click(screen.getByRole("button", { name: "담당자 판단 저장" }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/suggestions/SUG-1/decision"))).toBe(true));
  const decision = calls.find((call) => call.url.endsWith("/suggestions/SUG-1/decision"));
  expect(JSON.parse(String(decision?.init?.body))).toEqual({ decisionStatus: "MODIFIED_AND_USED", finalText: "수정 문구" });

  fireEvent.change(screen.getByLabelText("질문"), { target: { value: "표현을 사용할 수 있나요?" } });
  fireEvent.click(screen.getByRole("button", { name: "근거 기반 질문" }));
  expect(await screen.findByText("근거가 부족하여 담당자 확인이 필요합니다.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "HWPX 리포트 생성" }));
  expect(await screen.findByText("sha256:test")).toBeInTheDocument();
  expect(new Headers(decision?.init?.headers).get("Authorization")).toBe("Bearer m6-access-token");
});

test("requires final text for a modified suggestion before mutating the contract", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-M6/suggestions")) return response({ suggestionId: "SUG-1", reviewItemId: "ITEM-1", originalText: "국내 최고", suggestedText: "경쟁력 있는", decisionStatus: "PENDING" });
    if (url.endsWith("/reviews/REV-M6/opinion-drafts")) return response({ draftId: "OPN-1", reviewId: "REV-M6", draftContent: "초안", includedReviewItemIds: [], createdAt: "2026-07-14T10:00:00Z" });
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
