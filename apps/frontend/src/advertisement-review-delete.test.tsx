import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

vi.mock("./api/operational", async (importOriginal) => ({
  ...await importOriginal<typeof import("./api/operational")>(),
  operationalMode: true,
}));

const reviewerSession: AuthSession = {
  accessToken: "reviewer-token",
  user: {
    userId: "reviewer",
    userName: "준법 검토자",
    departmentId: "DPT-COMPLIANCE",
    departmentName: "준법감시",
    roles: ["COMPLIANCE_REVIEWER"],
  },
};

function response(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("review deletion is next to detail on the advertisement list and requires confirmation", async () => {
  const deleted: string[] = [];
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
  vi.stubGlobal("confirm", confirm);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/advertisements?") || url.endsWith("/advertisements")) {
      return response({
        contents: [
          { advertisementId: "ADV-DONE", advertisementName: "완료 광고", productGroup: "DEPOSIT", advertisementType: "SMS", registeredBy: "reviewer", registeredAt: "2026-09-17T10:00:00+09:00", reviewStatus: "REVIEW_COMPLETED" },
          { advertisementId: "ADV-NEW", advertisementName: "미심의 광고", productGroup: "DEPOSIT", advertisementType: "NOTICE", registeredBy: "reviewer", registeredAt: "2026-09-17T10:01:00+09:00", reviewStatus: "UPLOADED" },
        ],
        page: 1,
        size: 20,
        totalElements: 2,
        totalPages: 1,
      });
    }
    if (init?.method === "DELETE") {
      deleted.push(url);
      return response(null, 204);
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={reviewerSession} /></MemoryRouter>);
  const completedRow = (await screen.findByText("완료 광고")).closest("tr");
  const newRow = screen.getByText("미심의 광고").closest("tr");
  expect(completedRow).not.toBeNull();
  expect(newRow).not.toBeNull();
  expect(within(completedRow!).getByRole("link", { name: "상세 보기" })).toBeInTheDocument();
  const deleteButton = within(completedRow!).getByRole("button", { name: "심의 결과 삭제" });
  expect(within(newRow!).queryByRole("button", { name: "심의 결과 삭제" })).not.toBeInTheDocument();

  fireEvent.click(deleteButton);
  expect(confirm).toHaveBeenCalledWith("이 광고의 최신 심의 결과를 삭제하시겠습니까? 삭제 후 되돌릴 수 없습니다.");
  expect(deleted).toEqual([]);

  fireEvent.click(deleteButton);
  await waitFor(() => expect(deleted).toEqual([
    "/api/v1/operational/advertisements/ADV-DONE/latest-review",
  ]));
});
