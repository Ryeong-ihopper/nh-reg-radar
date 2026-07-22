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

const productSession: AuthSession = {
  ...adminSession,
  user: { ...adminSession.user, roles: ["PRODUCT_DEPARTMENT_USER"] },
};

function response(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(deleteCalls: string[]): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/advertisements/ADV-DELETE")) {
      if (init?.method === "DELETE") {
        deleteCalls.push(url);
        return response(null, 204);
      }
      return response({
        advertisementId: "ADV-DELETE",
        advertisementName: "삭제 대상 광고",
        productGroup: "SAVINGS",
        advertisementType: "MOBILE_BANNER",
        departmentId: "DPT-ADMIN",
        registeredBy: "admin",
        registeredAt: "2026-07-22T10:00:00+09:00",
        reviewStatus: "REVIEW_COMPLETED",
        files: [],
      });
    }
    if (url.endsWith("/advertisements/ADV-DELETE/reviews")) return response([]);
    if (url.endsWith("/advertisements")) return response({ contents: [], totalElements: 0, totalPages: 0, page: 0, size: 20 });
    throw new Error(`Unexpected request: ${url}`);
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("shows the delete action only to a system administrator and deletes after confirmation", async () => {
  const deleteCalls: string[] = [];
  installFetch(deleteCalls);
  vi.stubGlobal("confirm", vi.fn(() => true));

  render(<MemoryRouter initialEntries={["/advertisements/ADV-DELETE"]}><App initialSession={adminSession} /></MemoryRouter>);
  const deleteButton = await screen.findByRole("button", { name: "광고물 삭제" });
  fireEvent.click(deleteButton);

  await waitFor(() => expect(deleteCalls).toEqual(["/api/v1/advertisements/ADV-DELETE"]));
  expect(window.confirm).toHaveBeenCalledOnce();
});

test("does not show the delete action to a non-administrator", async () => {
  const deleteCalls: string[] = [];
  installFetch(deleteCalls);

  render(<MemoryRouter initialEntries={["/advertisements/ADV-DELETE"]}><App initialSession={productSession} /></MemoryRouter>);
  await screen.findByRole("heading", { name: "삭제 대상 광고" });
  expect(screen.queryByRole("button", { name: "광고물 삭제" })).not.toBeInTheDocument();
});
