import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const standardManagerSession: AuthSession = {
  accessToken: "standards-token",
  user: {
    userId: "manager001",
    userName: "기준 관리자",
    departmentId: "DPT-COMPLIANCE",
    departmentName: "준법감시부",
    roles: ["STANDARD_MANAGER"],
  },
};

const productSession: AuthSession = {
  ...standardManagerSession,
  user: { ...standardManagerSession.user, roles: ["PRODUCT_DEPARTMENT_USER"] },
};

const standard = {
  standardId: "STD-SYNTH-001",
  standardVersionId: "STDV-SYNTH-001-V1",
  evidenceId: "EVD-SYNTH-001",
  title: "합성 광고심의 내부 기준",
  evidenceType: "INTERNAL_STANDARD",
  productGroup: "SAVINGS",
  advertisementType: "MOBILE_BANNER",
  ruleType: "REQUIRED",
  importance: "HIGH",
  effectiveDate: "2026-07-01",
  expiredDate: null,
  currentVersion: "1.0",
  version: "1.0",
  isActive: true,
  content: "합성 테스트 기준 본문",
  changeReason: null as string | null,
  metadata: {},
  createdAt: "2026-07-01T00:00:00Z",
  createdBy: "manager001",
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function standardPage(contents = [standard]) {
  return { contents, page: 1, size: 20, totalElements: contents.length, totalPages: contents.length ? 1 : 0 };
}

const validInternalMetadata = {
  inputBoundary: "DIRECT_TEXT_ONLY",
  owningDepartment: "준법부",
  documentName: "광고심의 내규",
  sectionPath: "표현/금지",
  effectiveDate: "2026-07-01",
  version: "1.0",
  productGroup: "SAVINGS",
};

function fillInternalStandardCreateForm(sectionPath = validInternalMetadata.sectionPath) {
  fireEvent.change(screen.getByLabelText(/기준명 \*/), { target: { value: "새 합성 기준" } });
  fireEvent.change(screen.getByLabelText(/상품군 \*/), { target: { value: validInternalMetadata.productGroup } });
  fireEvent.change(screen.getByLabelText(/소관 부서 \*/), { target: { value: validInternalMetadata.owningDepartment } });
  fireEvent.change(screen.getByLabelText(/문서명 \*/), { target: { value: validInternalMetadata.documentName } });
  fireEvent.change(screen.getByLabelText(/섹션 경로 \*/), { target: { value: sectionPath } });
  fireEvent.change(screen.getByLabelText(/문서 버전 \*/), { target: { value: validInternalMetadata.version } });
  fireEvent.change(screen.getByLabelText(/적용일 \*/), { target: { value: validInternalMetadata.effectiveDate } });
  fireEvent.change(screen.getByLabelText(/직접 입력 본문 \*/), { target: { value: "새 합성 기준 본문" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("loads S-014 for a standard manager, searches deterministically, and keeps bearer scope", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return response(standardPage());
  }));

  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={standardManagerSession} /></MemoryRouter>);

  expect(screen.getByRole("status")).toHaveTextContent("기준자료 목록을 불러오는 중입니다.");
  expect(await screen.findByRole("heading", { name: "기준자료 관리" })).toBeInTheDocument();
  expect(await screen.findByText(standard.title)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("기준명"), { target: { value: "합성 기준" } });
  fireEvent.change(screen.getByLabelText("기준 유형"), { target: { value: "INTERNAL_STANDARD" } });
  fireEvent.click(screen.getByRole("button", { name: "조회" }));

  await waitFor(() => expect(calls.length).toBe(2));
  expect(calls[1].url).toContain("/standards?");
  expect(calls[1].url).toContain("keyword=%ED%95%A9%EC%84%B1+%EA%B8%B0%EC%A4%80");
  expect(calls[1].url).toContain("evidenceType=INTERNAL_STANDARD");
  expect(new Headers(calls[1].init?.headers).get("Authorization")).toBe("Bearer standards-token");
});

test("renders empty and redacted failure states without leaking server or index details", async () => {
  let requestNo = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    requestNo += 1;
    if (requestNo === 1) return response(standardPage([]));
    return response({ code: "SEARCH_UNAVAILABLE", message: "qdrant collection private-vectors failed", traceId: "req-search-safe" }, 503);
  }));

  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={standardManagerSession} /></MemoryRouter>);
  expect(await screen.findByText("등록된 기준자료가 없습니다.")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("근거 검색어"), { target: { value: "우대금리" } });
  fireEvent.click(screen.getByRole("button", { name: "근거 검색" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("검색 인프라를 사용할 수 없습니다.");
  expect(alert).toHaveTextContent("req-search-safe");
  expect(alert).not.toHaveTextContent("qdrant");
  expect(alert).not.toHaveTextContent("private-vectors");
});

test("shows version history, redacted chunk metadata, evidence ranking, and reindex state", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.includes("/histories")) return response(standardPage([{ ...standard, currentVersion: "2.0", version: "2.0", standardVersionId: "STDV-SYNTH-001-V2", changeReason: "합성 개정" }]));
    if (url.includes("/chunks")) return response({ contents: [{ evidenceChunkId: "ECH-SYNTH-001", evidenceId: standard.evidenceId, standardId: standard.standardId, standardVersionId: standard.standardVersionId, chunkNo: 1, chunkText: "합성 우대금리 근거", tokenCount: 7, sectionPath: "제1장", articleNo: "제3조", chunkingPolicyVersion: "direct-text-v1", searchSchemaVersion: "m3-v1", qdrantIndexStatus: "ACTIVE", opensearchIndexStatus: "ACTIVE", createdAt: "2026-07-01T00:00:00Z", qdrantPointId: "secret-point", opensearchDocId: "secret-doc" }], page: 1, size: 20, totalElements: 1, totalPages: 1 });
    if (url.includes("/evidences/search")) return response([{ evidenceId: standard.evidenceId, evidenceChunkId: "ECH-SYNTH-001", standardVersionId: standard.standardVersionId, evidenceType: standard.evidenceType, title: standard.title, ruleType: standard.ruleType, contentSummary: "합성 우대금리 근거", version: standard.version, rankNo: 1, relevanceScore: 0.91, matchSource: "HYBRID" }]);
    if (url.includes("/reindex") && init?.method === "POST") return response({ jobId: "RJ-SYNTH-001", standardId: standard.standardId, standardVersionId: standard.standardVersionId, reindexScope: "INDEX_ONLY", jobStatus: "QUEUED", targetIndexes: ["QDRANT", "OPENSEARCH"], createdChunkCount: 1, indexedChunkCount: 0, requestedBy: "manager001", requestedAt: "2026-07-01T00:00:00Z" }, 202);
    if (url.includes("/standard-reindex-jobs/")) return response({ jobId: "RJ-SYNTH-001", standardId: standard.standardId, standardVersionId: standard.standardVersionId, reindexScope: "INDEX_ONLY", jobStatus: "SUCCEEDED", targetIndexes: ["QDRANT", "OPENSEARCH"], createdChunkCount: 1, indexedChunkCount: 1, qdrantStatus: "ACTIVE", opensearchStatus: "ACTIVE", failedReasonCode: null, requestedBy: "manager001", requestedAt: "2026-07-01T00:00:00Z" });
    if (url.endsWith(`/standards/${standard.standardId}`)) return response(standard);
    return response(standardPage());
  }));

  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={standardManagerSession} /></MemoryRouter>);
  expect(await screen.findByText(standard.title)).toBeInTheDocument();

  const row = screen.getByRole("row", { name: new RegExp(standard.standardId) });
  fireEvent.click(within(row).getByRole("button", { name: "이력 보기" }));
  expect(await screen.findByText("합성 개정")).toBeInTheDocument();

  fireEvent.click(within(row).getByRole("button", { name: "Chunk 확인" }));
  expect(await screen.findByText("합성 우대금리 근거")).toBeInTheDocument();
  expect(screen.queryByText("secret-point")).not.toBeInTheDocument();
  expect(screen.queryByText("secret-doc")).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("근거 검색어"), { target: { value: "우대금리" } });
  fireEvent.click(screen.getByRole("button", { name: "근거 검색" }));
  expect(await screen.findByText("HYBRID · 1위 · 0.9100")).toBeInTheDocument();

  fireEvent.click(within(row).getByRole("button", { name: "재색인" }));
  fireEvent.change(await screen.findByLabelText(/재색인 사유/), { target: { value: "정기 합성 검증" } });
  fireEvent.click(screen.getByRole("button", { name: "재색인 요청" }));
  expect(await screen.findByText("SUCCEEDED")).toBeInTheDocument();
  const reindex = requests.find((request) => request.url.includes("/reindex") && request.init?.method === "POST");
  expect(JSON.parse(String(reindex?.init?.body))).toMatchObject({
    reindexScope: "INDEX_ONLY",
    reason: "정기 합성 검증",
    chunkingPolicyVersion: "direct-text-v1",
    searchSchemaVersion: "m3-v1",
    targetIndexes: ["QDRANT", "OPENSEARCH"],
  });
});

test("blocks roles outside the frozen standard-manager boundary before fetching", () => {
  const productFetch = vi.fn();
  vi.stubGlobal("fetch", productFetch);
  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(screen.getByRole("alert")).toHaveTextContent("접근 권한이 없습니다.");
  expect(productFetch).not.toHaveBeenCalled();
});

test("creates direct-text standards, appends immutable versions, and soft-deactivates", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const versionTwo = { ...standard, currentVersion: "2.0", version: "2.0", standardVersionId: "STDV-SYNTH-001-V2", changeReason: "합성 개정" };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.endsWith("/standards") && init?.method === "POST") {
      const body = init.body as FormData;
      const metadata = JSON.parse(String(body.get("metadata"))) as Record<string, unknown>;
      if (Object.entries(validInternalMetadata).some(([key, value]) => metadata[key] !== value)) {
        return response({ code: "REFERENCE_METADATA_INVALID", traceId: "req-create-invalid" }, 400);
      }
      return response({ standardId: standard.standardId, evidenceId: standard.evidenceId, standardVersionId: standard.standardVersionId, version: "1.0", isActive: true }, 201);
    }
    if (url.endsWith(`/standards/${standard.standardId}/deactivate`) && init?.method === "PATCH") return response({ ...versionTwo, isActive: false });
    if (url.endsWith(`/standards/${standard.standardId}`) && init?.method === "PATCH") return response(versionTwo);
    if (url.endsWith(`/standards/${standard.standardId}`)) return response(standard);
    return response(standardPage());
  }));

  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={standardManagerSession} /></MemoryRouter>);
  expect(await screen.findByText(standard.title)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "신규 등록" }));
  fillInternalStandardCreateForm();
  fireEvent.click(screen.getByRole("button", { name: "등록" }));
  await waitFor(() => expect(requests.some((request) => request.url.endsWith("/standards") && request.init?.method === "POST")).toBe(true));
  const createBody = requests.find((request) => request.url.endsWith("/standards") && request.init?.method === "POST")?.init?.body as FormData;
  expect(createBody.get("content")).toBe("새 합성 기준 본문");
  expect(createBody.get("productGroup")).toBe(validInternalMetadata.productGroup);
  expect(createBody.get("effectiveDate")).toBe(validInternalMetadata.effectiveDate);
  expect(JSON.parse(String(createBody.get("metadata")))).toEqual(validInternalMetadata);

  const row = await screen.findByRole("row", { name: new RegExp(standard.standardId) });
  fireEvent.click(within(row).getByRole("button", { name: "수정" }));
  fireEvent.change(await screen.findByLabelText(/변경 사유/), { target: { value: "합성 개정" } });
  fireEvent.change(screen.getByLabelText(/직접 입력 본문/), { target: { value: "개정된 합성 기준 본문" } });
  fireEvent.click(screen.getByRole("button", { name: "새 버전 저장" }));
  await waitFor(() => expect(requests.some((request) => request.url.endsWith(`/standards/${standard.standardId}`) && request.init?.method === "PATCH")).toBe(true));
  const update = requests.find((request) => request.url.endsWith(`/standards/${standard.standardId}`) && request.init?.method === "PATCH");
  expect(JSON.parse(String(update?.init?.body))).toMatchObject({ content: "개정된 합성 기준 본문", changeReason: "합성 개정" });

  fireEvent.click(within(screen.getByRole("row", { name: new RegExp(standard.standardId) })).getByRole("button", { name: "비활성화" }));
  fireEvent.change(await screen.findByLabelText(/비활성화 사유/), { target: { value: "합성 만료" } });
  fireEvent.click(screen.getByRole("button", { name: "비활성화 확인" }));
  await waitFor(() => expect(requests.some((request) => request.url.includes("/deactivate") && request.init?.method === "PATCH")).toBe(true));
  const deactivate = requests.find((request) => request.url.includes("/deactivate") && request.init?.method === "PATCH");
  expect(JSON.parse(String(deactivate?.init?.body))).toEqual({ reason: "합성 만료" });
});

test("shows the backend metadata validation failure without echoing its internal message", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.endsWith("/standards") && init?.method === "POST") {
      const metadata = JSON.parse(String((init.body as FormData).get("metadata"))) as Record<string, unknown>;
      if (!metadata.sectionPath) {
        return response({ code: "REFERENCE_METADATA_INVALID", message: "section_path column rejected", traceId: "req-metadata-safe" }, 400);
      }
    }
    return response(standardPage());
  }));

  render(<MemoryRouter initialEntries={["/standards"]}><App initialSession={standardManagerSession} /></MemoryRouter>);
  expect(await screen.findByText(standard.title)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "신규 등록" }));
  fillInternalStandardCreateForm(" ");
  fireEvent.click(screen.getByRole("button", { name: "등록" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("기준 유형에 필요한 메타데이터를 확인해 주세요.");
  expect(alert).toHaveTextContent("req-metadata-safe");
  expect(alert).not.toHaveTextContent("section_path");
  const createBody = requests.find((request) => request.url.endsWith("/standards") && request.init?.method === "POST")?.init?.body as FormData;
  expect(JSON.parse(String(createBody.get("metadata")))).toEqual({ ...validInternalMetadata, sectionPath: "" });
});
