import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const productSession: AuthSession = {
  accessToken: "access-token-for-test",
  user: {
    userId: "user001",
    userName: "테스트 사용자",
    departmentId: "DPT-001",
    departmentName: "상품부",
    roles: ["PRODUCT_DEPARTMENT_USER"],
  },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function emptyList() {
  return { contents: [], page: 1, size: 20, totalElements: 0, totalPages: 0 };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("rejects passwords shorter than the locked 10-character minimum before calling the API", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><App initialSession={null} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "short123" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  expect(screen.getByRole("alert")).toHaveTextContent("비밀번호는 10자 이상 입력해 주세요.");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("redirects an unauthenticated root route to login and validates required credentials", () => {
  render(<MemoryRouter><App initialSession={null} /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "로그인" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  expect(screen.getByRole("alert")).toHaveTextContent("이메일과 비밀번호를 입력해 주세요.");
});

test("restores an httpOnly refresh-cookie session before rendering a protected deep link", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/auth/refresh")) {
      return response({ accessToken: "restored-token", tokenType: "Bearer", expiresIn: 1800, user: productSession.user });
    }
    if (url.includes("/advertisements?")) return response(emptyList());
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements"]}><App /></MemoryRouter>);

  expect(screen.getByRole("status")).toHaveTextContent("로그인 상태를 확인하는 중입니다.");
  expect(await screen.findByRole("heading", { name: "광고물 목록" })).toBeInTheDocument();
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls.map((call) => new URL(call.url, "http://test").pathname)).toEqual([
    "/api/v1/auth/refresh",
    "/api/v1/advertisements",
  ]);
  expect(calls[0].init?.credentials).toBe("include");
  expect(new Headers(calls[1].init?.headers).get("Authorization")).toBe("Bearer restored-token");
});

test("refreshes once after a 401, retries with the rotated token, and synchronizes the session", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  let listAttempts = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/auth/refresh")) {
      return response({ accessToken: "rotated-token", tokenType: "Bearer", expiresIn: 1800, user: productSession.user });
    }
    if (url.includes("/advertisements?")) {
      listAttempts += 1;
      return listAttempts === 1 ? response({ code: "UNAUTHORIZED" }, 401) : response(emptyList());
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={productSession} /></MemoryRouter>);

  expect(await screen.findByText("등록된 광고물이 없습니다.")).toBeInTheDocument();
  expect(calls.filter((call) => call.url.endsWith("/auth/refresh"))).toHaveLength(1);
  const listCalls = calls.filter((call) => call.url.includes("/advertisements?"));
  expect(listCalls).toHaveLength(2);
  expect(new Headers(listCalls[0].init?.headers).get("Authorization")).toBe("Bearer access-token-for-test");
  expect(new Headers(listCalls[1].init?.headers).get("Authorization")).toBe("Bearer rotated-token");
});

test("logs in with cookie credentials, keeps the bearer token in memory, and renders an empty advertisement list", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.endsWith("/auth/login")) {
      return response({ accessToken: "safe-token", tokenType: "Bearer", expiresIn: 1800, user: productSession.user });
    }
    return response(emptyList());
  }));

  render(<MemoryRouter><App initialSession={null} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "correct-password" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));

  expect(await screen.findByRole("heading", { name: "광고물 목록" })).toBeInTheDocument();
  expect(await screen.findByText("등록된 광고물이 없습니다.")).toBeInTheDocument();
  expect(requests[0].init?.credentials).toBe("include");
  expect(JSON.parse(String(requests[0].init?.body))).toEqual({ email: "user@example.com", password: "correct-password" });
  const listHeaders = requests[1].init?.headers as Headers;
  expect(listHeaders.get("Authorization")).toBe("Bearer safe-token");
});

test("generalizes a rejected login without exposing the server reason", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ code: "UNAUTHORIZED", message: "account locked for internal@example.com", traceId: "req-login" }, 401)));
  render(<MemoryRouter><App initialSession={null} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "wrong-password" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다.");
  expect(alert).not.toHaveTextContent("account locked");
});

test("revokes the refresh cookie session before clearing the in-memory login", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    if (String(input).endsWith("/auth/logout")) return new Response(null, { status: 204 });
    return response(emptyList());
  }));
  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={productSession} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));
  expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
  const logout = calls.find((call) => call.url.endsWith("/auth/logout"));
  expect(logout?.init?.method).toBe("POST");
  expect(logout?.init?.credentials).toBe("include");
});

test("shows loading then a redacted error and safe trace id for list failures", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({
    code: "INTERNAL_ERROR",
    message: "secret at /app/minio/internal-object-key",
    traceId: "req-safe-001",
  }, 500)));

  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(screen.getByRole("status")).toHaveTextContent("광고물 목록을 불러오는 중입니다.");
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("일시적인 오류가 발생했습니다.");
  expect(alert).toHaveTextContent("req-safe-001");
  expect(alert).not.toHaveTextContent("internal-object-key");
});

test("navigates advertisement result pages using server pagination metadata", async () => {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    const page = new URL(url, "http://test").searchParams.get("page");
    return response({
      contents: [{ advertisementId: `ADV-${page}`, advertisementName: `광고 ${page}`, productGroup: "DEPOSIT", advertisementType: "BRANCH_FLYER", departmentId: "DPT-001", registeredBy: "USR-001", registeredAt: "2026-07-16T00:00:00Z", reviewStatus: "UPLOADED" }],
      page: Number(page), size: 20, totalElements: 40, totalPages: 2,
    });
  }));

  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(await screen.findByText("광고 1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "다음 페이지" }));
  expect(await screen.findByText("광고 2")).toBeInTheDocument();
  expect(urls.at(-1)).toContain("page=2");
  expect(screen.getByRole("button", { name: "다음 페이지" })).toBeDisabled();
});

test("blocks roles without advertisement permission before any API request", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const restrictedSession: AuthSession = { ...productSession, user: { ...productSession.user, roles: ["STANDARD_MANAGER"] } };
  render(<MemoryRouter initialEntries={["/advertisements"]}><App initialSession={restrictedSession} /></MemoryRouter>);
  expect(screen.getByRole("alert")).toHaveTextContent("접근 권한이 없습니다.");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("shows registration validation for required and unsupported file inputs", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/codes/product-groups")) return response([{ code: "SAVINGS", name: "적금", sortOrder: 1, enabled: true }]);
    if (url.endsWith("/codes/advertisement-types")) return response([{ code: "MOBILE_BANNER", name: "모바일 배너", sortOrder: 1, enabled: true }]);
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements/new"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "광고물 등록" })).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("등록 선택값을 불러오는 중입니다.")).not.toBeInTheDocument());
  const oversizedTerms = new File(["terms"], "terms.pdf", { type: "application/pdf" });
  Object.defineProperty(oversizedTerms, "size", { value: 50 * 1024 * 1024 + 1 });
  fireEvent.change(screen.getByLabelText("광고 파일 *"), { target: { files: [new File(["bad"], "malware.exe", { type: "application/octet-stream" })] } });
  fireEvent.change(screen.getByLabelText("상품설명서"), { target: { files: [new File(["bad"], "description.exe", { type: "application/octet-stream" })] } });
  fireEvent.change(screen.getByLabelText("약관"), { target: { files: [oversizedTerms] } });
  fireEvent.change(screen.getByLabelText("추가 첨부파일"), { target: { files: Array.from({ length: 11 }, (_, index) => new File(["file"], `extra-${index}.png`, { type: "image/png" })) } });
  fireEvent.click(screen.getByRole("button", { name: "저장" }));
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("광고명을 입력해 주세요.");
  expect(alert).toHaveTextContent("상품군을 선택해 주세요.");
  expect(alert).toHaveTextContent("지원하지 않는 파일 형식입니다.");
  expect(alert).toHaveTextContent("상품설명서: 지원하지 않는 파일 형식입니다.");
  expect(alert).toHaveTextContent("약관: 파일 용량이 50MB를 초과했습니다.");
  expect(alert).toHaveTextContent("추가 첨부파일은 최대 10개까지 선택할 수 있습니다.");
});

test("completes login, allowed multipart upload, list/detail, authorized preview, and download", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:authorized-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/auth/login")) return response({ accessToken: "safe-token", tokenType: "Bearer", expiresIn: 1800, user: productSession.user });
    if (url.endsWith("/codes/product-groups")) return response([{ code: "SAVINGS", name: "적금", sortOrder: 1, enabled: true }]);
    if (url.endsWith("/codes/advertisement-types")) return response([{ code: "MOBILE_BANNER", name: "모바일 배너", sortOrder: 1, enabled: true }]);
    if (url.includes("/files/FILE-001/preview/content")) return new Response(new Blob(["preview"], { type: "image/png" }), { status: 200, headers: { "Content-Type": "image/png" } });
    if (url.includes("/files/FILE-001/preview?")) return response({ fileId: "FILE-001", pageNo: 1, totalPages: 1, previewPath: "/api/v1/files/FILE-001/preview/content", width: 1080, height: 1920 });
    if (url.endsWith("/files/FILE-001/download")) return new Response(new Blob(["download"], { type: "image/png" }), { status: 200 });
    const advertisementFile = { fileId: "FILE-001", fileType: "ADVERTISEMENT", fileName: "banner.png", mimeType: "image/png", fileSize: 3 };
    if (url.endsWith("/advertisements") && init?.method === "POST") return response({ advertisementId: "ADV-001", advertisementName: "안전한 광고", reviewStatus: "UPLOADED", files: [advertisementFile], createdAt: "2026-07-14T10:00:00+09:00" }, 201);
    if (url.endsWith("/advertisements/ADV-001")) return response({ advertisementId: "ADV-001", advertisementName: "안전한 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001", registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "UPLOADED", files: [advertisementFile], channelType: null, memo: null });
    return response(emptyList());
  }));

  render(<MemoryRouter><App initialSession={null} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "user@example.com" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "correct-password" } });
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
  expect(await screen.findByRole("heading", { name: "광고물 목록" })).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("link", { name: "광고물 등록" })[1]);
  await waitFor(() => expect(screen.queryByText("등록 선택값을 불러오는 중입니다.")).not.toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("광고명 *"), { target: { value: "안전한 광고" } });
  fireEvent.change(screen.getByLabelText("상품군 *"), { target: { value: "SAVINGS" } });
  fireEvent.change(screen.getByLabelText("광고유형 *"), { target: { value: "MOBILE_BANNER" } });
  fireEvent.change(screen.getByLabelText("광고 파일 *"), { target: { files: [new File(["png"], "banner.png", { type: "image/png" })] } });
  fireEvent.change(screen.getByLabelText("추가 첨부파일"), { target: { files: [new File(["more"], "extra.pdf", { type: "application/pdf" })] } });
  fireEvent.click(screen.getByRole("button", { name: "저장" }));

  expect(await screen.findByRole("heading", { name: "광고물 상세 조회" })).toBeInTheDocument();
  expect(await screen.findByText("안전한 광고")).toBeInTheDocument();
  expect(screen.getByText(/banner\.png/)).toBeInTheDocument();
  const upload = calls.find((call) => call.url.endsWith("/advertisements") && call.init?.method === "POST");
  expect(upload?.init?.body).toBeInstanceOf(FormData);
  expect((upload?.init?.body as FormData).get("departmentId")).toBe("DPT-001");
  expect((upload?.init?.body as FormData).getAll("additionalFiles")).toHaveLength(1);
  expect((upload?.init?.headers as Headers).has("Content-Type")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
  expect(await screen.findByRole("img", { name: "banner.png 미리보기" })).toHaveAttribute("src", "blob:authorized-preview");
  fireEvent.click(screen.getByRole("button", { name: "다운로드" }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/files/FILE-001/download"))).toBe(true));
  const protectedFileCalls = calls.filter((call) => call.url.includes("/files/FILE-001/"));
  expect(protectedFileCalls).toHaveLength(3);
  for (const call of protectedFileCalls) expect(new Headers(call.init?.headers).get("Authorization")).toBe("Bearer safe-token");
});

test("renders a dedicated forbidden state for an unauthorized file preview", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/preview?")) return response({ code: "FORBIDDEN", message: "bucket/object-key", traceId: "req-file-403" }, 403);
    return response({ advertisementId: "ADV-001", advertisementName: "광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001", registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "UPLOADED", files: [{ fileId: "FILE-001", fileType: "ADVERTISEMENT", fileName: "banner.png", mimeType: "image/png", fileSize: 3 }] });
  }));
  render(<MemoryRouter initialEntries={["/advertisements/ADV-001"]}><App initialSession={productSession} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "미리보기" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("파일 미리보기 권한이 없습니다.");
  expect(alert).not.toHaveTextContent("object-key");
});

test("renders an authorized PDF preview as a browser PDF object", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:pdf-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/preview/content")) return new Response(new Blob(["%PDF-1.4"], { type: "application/pdf" }), { status: 200, headers: { "Content-Type": "application/pdf" } });
    if (url.includes("/preview?")) return response({ fileId: "FILE-PDF", pageNo: 1, totalPages: 1, previewPath: "/api/v1/files/FILE-PDF/preview/content", width: null, height: null });
    if (url.endsWith("/advertisements/ADV-PDF")) return response({ advertisementId: "ADV-PDF", advertisementName: "PDF 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001", registeredAt: "2026-07-16T10:00:00+09:00", reviewStatus: "UPLOADED", files: [{ fileId: "FILE-PDF", fileType: "ADVERTISEMENT", fileName: "banner.pdf", mimeType: "application/pdf", fileSize: 10 }] });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/advertisements/ADV-PDF"]}><App initialSession={productSession} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "미리보기" }));

  expect(await screen.findByLabelText("banner.pdf 미리보기")).toHaveAttribute("data", "blob:pdf-preview");
});

test("does not request an unsupported HWP browser preview", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/advertisements/ADV-HWP")) return response({ advertisementId: "ADV-HWP", advertisementName: "HWP 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001", registeredAt: "2026-07-16T10:00:00+09:00", reviewStatus: "UPLOADED", files: [{ fileId: "FILE-HWP", fileType: "ADVERTISEMENT", fileName: "banner.hwp", mimeType: "application/x-hwp", fileSize: 10 }] });
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<MemoryRouter initialEntries={["/advertisements/ADV-HWP"]}><App initialSession={productSession} /></MemoryRouter>);

  expect(await screen.findByText("HWP/HWPX는 원본 다운로드 또는 검토 결과의 텍스트 위치에서 확인할 수 있습니다.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "미리보기" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("rejects an untrusted preview path without requesting storage or foreign URLs", async () => {
  const requestedUrls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    requestedUrls.push(url);
    if (url.includes("/preview?")) {
      return response({ fileId: "FILE-001", pageNo: 1, totalPages: 1, previewPath: "https://storage.invalid/private-object", width: 1, height: 1 });
    }
    return response({ advertisementId: "ADV-001", advertisementName: "광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", departmentId: "DPT-001", registeredBy: "user001", registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "UPLOADED", files: [{ fileId: "FILE-001", fileType: "ADVERTISEMENT", fileName: "banner.png", mimeType: "image/png", fileSize: 3 }] });
  }));
  render(<MemoryRouter initialEntries={["/advertisements/ADV-001"]}><App initialSession={productSession} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "미리보기" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("일시적인 오류가 발생했습니다.");
  expect(requestedUrls).toHaveLength(2);
  expect(requestedUrls).not.toContain("https://storage.invalid/private-object");
});

test("renders a dedicated forbidden state for cross-department detail access", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ code: "FORBIDDEN", message: "internal reason", traceId: "req-403" }, 403)));
  render(<MemoryRouter initialEntries={["/advertisements/ADV-OTHER"]}><App initialSession={productSession} /></MemoryRouter>);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("접근 권한이 없습니다.");
  expect(alert).toHaveTextContent("소속 부서와 광고물 접근 범위를 확인해 주세요.");
  expect(alert).not.toHaveTextContent("internal reason");
});

test("renders the not-found route", () => {
  render(<MemoryRouter initialEntries={["/missing"]}><App initialSession={null} /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "페이지를 찾을 수 없습니다." })).toBeInTheDocument();
});
