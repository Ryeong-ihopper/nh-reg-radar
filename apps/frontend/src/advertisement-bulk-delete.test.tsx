import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const adminSession: AuthSession = {
  accessToken: "admin-token",
  user: {
    userId: "admin",
    userName: "시스템 관리자",
    departmentId: "DPT-ADMIN",
    departmentName: "시스템관리",
    roles: ["SYSTEM_ADMIN"],
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

test("system administrators can select the visible advertisement rows and delete them together", async () => {
  const deleted: string[] = [];
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/advertisements?") || url.endsWith("/advertisements")) {
      return response({
        contents: [
          { advertisementId: "ADV-ONE", advertisementName: "첫 번째 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", registeredBy: "admin", registeredAt: "2026-07-22T10:00:00+09:00", reviewStatus: "UPLOADED" },
          { advertisementId: "ADV-TWO", advertisementName: "두 번째 광고", productGroup: "LOAN", advertisementType: "NOTICE", registeredBy: "admin", registeredAt: "2026-07-22T10:00:00+09:00", reviewStatus: "UPLOADED" },
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

  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={adminSession} /></MemoryRouter>);
  const selectAll = await screen.findByRole("checkbox", { name: "현재 페이지 전체 선택" });
  fireEvent.click(selectAll);

  expect(screen.getByText("2건")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "선택 항목 삭제" }));

  await waitFor(() => expect(deleted).toEqual([
    "/api/v1/advertisements/ADV-ONE",
    "/api/v1/advertisements/ADV-TWO",
  ]));
});
