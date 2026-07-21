import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { ReviewAnnotationCollection, ReviewItemDetail, ReviewSummary } from "./api/client";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "m5-access-token",
  user: {
    userId: "USR-M5",
    userName: "M5 검토자",
    departmentId: "DPT-M5",
    departmentName: "상품부",
    roles: ["PRODUCT_DEPARTMENT_USER"],
  },
};

const summary: ReviewSummary = {
  reviewId: "REV-M5",
  advertisementId: "ADV-M5",
  standardEffectiveDate: "2026-07-14",
  standardVersionIds: ["STDV-M5"],
  overallRiskLevel: "HIGH",
  totalItemCount: 3,
  needsRevisionCount: 1,
  needsConfirmationCount: 2,
  reviewTypeSummary: [{ reviewType: "MISLEADING_EXPRESSION", totalCount: 3, needsRevisionCount: 1, needsConfirmationCount: 2 }],
  topRisks: [{
    reviewItemId: "ITEM-M5-1",
    riskLevel: "HIGH",
    riskPolicyVersion: "risk-policy-v1",
    riskReasonCodes: ["RAG_RECOVERY_REQUIRED"],
    targetText: "국내 최고 혜택",
    reason: "객관적 기준이 없어 오인 가능성이 있습니다.",
    evidenceStatus: "SEARCH_UNAVAILABLE",
  }],
  completedAt: "2026-07-14T12:00:00+09:00",
};

const item = {
  reviewItemId: "ITEM-M5-1",
  reviewType: "MISLEADING_EXPRESSION" as const,
  targetText: "국내 최고 혜택",
  resultStatus: "NEEDS_REVISION" as const,
  riskLevel: "HIGH" as const,
  riskPolicyVersion: "risk-policy-v1",
  riskReasonCodes: ["RAG_RECOVERY_REQUIRED"],
  reason: "객관적 기준이 없어 오인 가능성이 있습니다.",
  evidenceStatus: "SEARCH_UNAVAILABLE" as const,
  evidenceFailureCode: "RAG_SEARCH_UNAVAILABLE" as const,
  evidenceCount: 0,
  pageNo: 1,
  hasAnnotation: true,
  sourceEngine: "RULE" as const,
  sourceVersion: "rule-config-v1",
};

const detail: ReviewItemDetail = {
  ...item,
  riskRationale: {
    riskLevel: "HIGH",
    policyVersion: "risk-policy-v1",
    reasonCodes: ["RULE_EXPLICIT_VIOLATION"],
    scoreDetail: {
      rule: { matched: true, ruleIds: ["RULE-M5"], severity: "HIGH" },
      rag: { topRelevanceScore: null, evidenceCount: 0, evidenceSufficient: false, status: "SEARCH_UNAVAILABLE", failureCode: "RAG_SEARCH_UNAVAILABLE" },
      llm: { schemaVersion: "review-structured-output-v1", status: "NOT_RUN", decision: null, confidence: null },
      parser: { confidenceStatus: "READABLE" },
      final: { riskLevel: "HIGH", decisionRule: "RULE_EXPLICIT_VIOLATION" },
    },
  },
  evidences: [],
  recommendation: "조건과 산출 기준을 명시해 주세요.",
  annotation: {
    annotationId: "ANN-M5-BOX",
    reviewItemId: "ITEM-M5-1",
    reviewType: "MISLEADING_EXPRESSION",
    riskLevel: "HIGH",
    targetText: "국내 최고 혜택",
    annotationDisplayMode: "BOX",
    annotationStatus: "LOCATED",
    locationConfidence: 0.8,
    confidencePolicyVersion: "confidence-thresholds-v1",
    displayReason: "MATCHED_BOX",
    pageNo: 1,
    coordinate: { sourceWidth: 1000, sourceHeight: 500, sourceUnit: "px", x: 100, y: 50, width: 400, height: 50, normalizedX: 0.1, normalizedY: 0.1, normalizedWidth: 0.4, normalizedHeight: 0.1, rotation: 0, coordinateConfidence: 0.8 },
    textBlockId: null, textPath: null, rawStartOffset: null, rawEndOffset: null, normalizedStartOffset: null, normalizedEndOffset: null, matchedText: null,
  },
};

const annotations: ReviewAnnotationCollection = {
  reviewId: "REV-M5",
  fileId: "FILE-M5",
  fileType: "IMAGE",
  pageNo: 1,
  annotations: [
    detail.annotation!,
    {
      annotationId: "ANN-M5-TEXT", reviewItemId: "ITEM-M5-2", reviewType: "REQUIRED_PHRASE", riskLevel: "MEDIUM", targetText: "중도해지 안내", annotationDisplayMode: "TEXT_HIGHLIGHT", annotationStatus: "PARTIALLY_LOCATED", locationConfidence: 0.79, confidencePolicyVersion: "confidence-thresholds-v1", displayReason: "MATCHED_TEXT_SPAN", pageNo: null, coordinate: null, textBlockId: "TEXT-M5", textPath: "body/1", rawStartOffset: 3, rawEndOffset: 11, normalizedStartOffset: 4, normalizedEndOffset: 12, matchedText: "중도해지",
    },
    {
      annotationId: "ANN-M5-LIST", reviewItemId: "ITEM-M5-3", reviewType: "VISIBILITY", riskLevel: "CHECK_REQUIRED", targetText: "문서 전체 시인성", annotationDisplayMode: "LIST_ONLY", annotationStatus: "NOT_LOCATED", locationConfidence: 0.49, confidencePolicyVersion: "confidence-thresholds-v1", displayReason: "NO_TEXT_SPAN", pageNo: null, coordinate: null, textBlockId: null, textPath: null, rawStartOffset: null, rawEndOffset: null, normalizedStartOffset: null, normalizedEndOffset: null, matchedText: null,
    },
    {
      annotationId: "ANN-M5-UNAVAILABLE", reviewItemId: "ITEM-M5-4", reviewType: "OCR_QUALITY", riskLevel: "CHECK_REQUIRED", targetText: "원본 미리보기 불가", annotationDisplayMode: "UNAVAILABLE", annotationStatus: "NOT_LOCATED", locationConfidence: null, confidencePolicyVersion: "confidence-thresholds-v1", displayReason: "PREVIEW_UNAVAILABLE", pageNo: null, coordinate: null, textBlockId: null, textPath: null, rawStartOffset: null, rawEndOffset: null, normalizedStartOffset: null, normalizedEndOffset: null, matchedText: null,
    },
  ],
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("renders S-006 counts and distinguishes RAG failure from insufficient evidence", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/summary")) return response(summary);
    if (url.endsWith("/advertisements/ADV-M5")) return response({
      advertisementId: "ADV-M5", advertisementName: "정기예금 포스터", productGroup: "DEPOSIT",
      advertisementType: "BRANCH_FLYER", departmentId: "DPT-M5", registeredBy: "USR-M5",
      registeredAt: "2026-07-14T00:00:00Z", reviewStatus: "REVIEW_COMPLETED", files: [],
    });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results"]}><App initialSession={session} /></MemoryRouter>);
  expect(screen.getByRole("status")).toHaveTextContent("검토 결과 요약을 불러오는 중입니다.");
  expect(await screen.findByRole("heading", { name: "AI 검토 결과" })).toBeInTheDocument();
  const kpis = await screen.findByLabelText("검토 결과 집계");
  expect(within(kpis).getByText("높음")).toBeInTheDocument();
  expect(within(kpis).getByText("3")).toBeInTheDocument();
  expect(screen.getByText("근거 검색을 완료하지 못했습니다. 기준자료를 확인해 주세요.")).toBeInTheDocument();
  expect(screen.queryByText("근거 부족")).not.toBeInTheDocument();
  const basic = await screen.findByLabelText("광고 기본정보");
  expect(basic).toHaveTextContent("정기예금 포스터");
  expect(basic).toHaveTextContent("예금");
  expect(basic).toHaveTextContent("영업점 전단");
  expect(basic).toHaveTextContent("USR-M5");
  expect(basic.tagName).toBe("TABLE");
  expect(within(basic).getByRole("rowheader", { name: "광고명" })).toBeInTheDocument();
  expect(screen.getByLabelText("광고 원본 병행 검토")).toHaveTextContent("광고 원본");
  const workspace = screen.getByLabelText("AI 검토 결과 작업공간");
  expect(workspace.firstElementChild).toBe(screen.getByLabelText("광고 원본 병행 검토"));
  expect(workspace.lastElementChild).toHaveClass("review-inspection-panel");
  expect(screen.queryByText("위험 항목을 먼저 확인하고 원본·판단 근거·권고 조치를 함께 검토하세요.")).not.toBeInTheDocument();
  expect(screen.queryByText("원본을 보며 검토")).not.toBeInTheDocument();
  expect(screen.queryByText("권한 검증 미리보기")).not.toBeInTheDocument();
  expect(screen.getByText("최종 판단 안내").closest("p")).toHaveClass("state-warning");
  expect(screen.getByRole("link", { name: "수정본 비교·재검토" })).toHaveAttribute(
    "href",
    "/advertisements/ADV-M5/comparisons?reviewId=REV-M5",
  );
  expect(new Headers(calls[0].init?.headers).get("Authorization")).toBe("Bearer m5-access-token");
});

test("filters S-008, opens deterministic detail, and preserves rule result during RAG failure", async () => {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    if (url.endsWith("/items/ITEM-M5-1")) return response(detail);
    return response({ contents: [item], page: 1, size: 20, totalElements: 1, totalPages: 1 });
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/items"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText("국내 최고 혜택")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("위험도"), { target: { value: "HIGH" } });
  await waitFor(() => expect(urls.some((url) => url.includes("riskLevel=HIGH"))).toBe(true));
  fireEvent.click(await screen.findByRole("button", { name: /국내 최고 혜택/ }));
  expect(await screen.findByText("조건과 산출 기준을 명시해 주세요.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /국내 최고 혜택/ })).toHaveTextContent("과장·오인 표현");
  expect(screen.getByRole("button", { name: /국내 최고 혜택/ })).toHaveTextContent("수정 필요");
  expect(screen.getByRole("button", { name: /국내 최고 혜택/ })).toHaveTextContent("위험도 높음");
  expect(screen.getAllByText("근거 검색을 완료하지 못했습니다. 기준자료를 확인해 주세요.").length).toBeGreaterThan(0);
  expect(screen.getByLabelText("검토 결과 세부 정보")).toHaveTextContent("규칙 기반 판단");
  expect(screen.queryByText("RULE_EXPLICIT_VIOLATION")).not.toBeInTheDocument();
});

test("navigates paged review items without losing filters", async () => {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    const params = new URL(url, "http://test").searchParams;
    return response({ contents: [{ ...item, reviewItemId: `ITEM-${params.get("page")}` }], page: Number(params.get("page")), size: 20, totalElements: 40, totalPages: 2 });
  }));
  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/items"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText("국내 최고 혜택")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("위험도"), { target: { value: "HIGH" } });
  await waitFor(() => expect(urls.at(-1)).toContain("riskLevel=HIGH"));
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "다음 페이지" }));
  await waitFor(() => expect(urls.at(-1)).toContain("page=2"));
  expect(urls.at(-1)).toContain("riskLevel=HIGH");
});

test("renders verified original boxes and keeps coordinate-less text out of the preview", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:m5-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/annotations")) return response(annotations);
    if (url.includes("/preview/content")) return new Response(new Blob(["preview"], { type: "image/png" }), { status: 200 });
    if (url.includes("/preview?")) return response({ fileId: "FILE-M5", pageNo: 1, totalPages: 1, previewPath: "/api/v1/files/FILE-M5/preview/content", width: 1000, height: 500 });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/annotations"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "검토 위치와 근거 연결" })).toBeInTheDocument();
  const preview = await screen.findByRole("img", { name: "광고 원본 미리보기" });
  expect(preview).toHaveAttribute("src", "blob:m5-preview");
  const box = screen.getByRole("button", { name: "국내 최고 혜택 Annotation" });
  expect(box).toHaveStyle({ left: "10%", top: "10%", width: "40%", height: "10%" });
  expect(preview.closest(".annotation-media")).toContainElement(box);
  expect(screen.queryByRole("heading", { name: "HWP/HWPX 텍스트 위치" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "원본 위치 미확정 항목" })).toBeInTheDocument();
  expect(screen.getByLabelText("위치 신뢰도 확인 필요")).toHaveTextContent("위치 확인 필요 2건");
  const fallback = screen.getByRole("heading", { name: "원본 위치 미확정 항목" }).parentElement;
  expect(fallback).not.toBeNull();
  const unavailable = within(fallback!).getByRole("button", { name: /원본 미리보기 불가/ });
  expect(unavailable).toHaveTextContent("위치 확인 필요 · 위치 없음");
  fireEvent.click(unavailable);
  expect(screen.getByLabelText("선택 Annotation 상세")).toHaveTextContent("PREVIEW_UNAVAILABLE");
  fireEvent.click(box);
  expect(screen.getByLabelText("선택 Annotation 상세")).toHaveTextContent("MATCHED_BOX");
});

test("loads a PNG Annotation preview even when the API returns the business file classification", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:m5-advertisement-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/annotations")) return response({ ...annotations, fileType: "ADVERTISEMENT" });
    if (url.includes("/preview/content")) return new Response(new Blob(["preview"], { type: "image/png" }), { status: 200 });
    if (url.includes("/preview?")) return response({ fileId: "FILE-M5", pageNo: 1, totalPages: 1, previewPath: "/api/v1/files/FILE-M5/preview/content", width: 1000, height: 500 });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/annotations"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("img", { name: "광고 원본 미리보기" })).toHaveAttribute("src", "blob:m5-advertisement-preview");
  expect(screen.queryByText("이 파일 형식은 브라우저 미리보기를 지원하지 않습니다. 원본을 다운로드해 확인해 주세요.")).not.toBeInTheDocument();
});

test("renders a converted HWP preview with verified text locations over the original", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:m5-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const hwpAnnotations: ReviewAnnotationCollection = {
    ...annotations,
    fileType: "HWP",
    annotations: [
      annotations.annotations[0],
      {
        ...annotations.annotations[1],
        annotationId: "ANN-M5-HWP-BOX",
        annotationDisplayMode: "BOX",
        annotationStatus: "LOCATED",
        locationConfidence: 0.9,
        displayReason: "STRUCTURE_LAYOUT_COORDINATE",
        coordinate: { sourceWidth: 1240, sourceHeight: 1754, sourceUnit: "point", x: 96, y: 120, width: 320, height: 34, normalizedX: 96 / 1240, normalizedY: 120 / 1754, normalizedWidth: 320 / 1240, normalizedHeight: 34 / 1754, rotation: 0, coordinateConfidence: 0.9 },
      },
    ],
  };
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    if (url.includes("/annotations")) return response(hwpAnnotations);
    if (url.includes("/preview/content")) {
      return new Response(new Blob(["<svg><text>한글 광고</text></svg>"], { type: "image/svg+xml" }), {
        status: 200,
      });
    }
    if (url.includes("/preview?")) {
      return response({
        fileId: "FILE-M5",
        pageNo: 1,
        totalPages: 2,
        previewPath: "/api/v1/files/FILE-M5/preview/content",
        width: null,
        height: null,
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/annotations"]}><App initialSession={session} /></MemoryRouter>);
  const preview = await screen.findByRole("img", { name: "광고 원본 미리보기" });
  expect(preview).toHaveAttribute(
    "src",
    "blob:m5-preview",
  );
  const hwpBox = screen.getByRole("button", { name: "중도해지 안내 Annotation" });
  expect(preview.closest(".annotation-media")).toContainElement(hwpBox);
  expect(hwpBox).toHaveStyle({ left: `${(96 / 1240) * 100}%`, top: `${(120 / 1754) * 100}%` });
  expect(screen.queryByRole("heading", { name: "HWP/HWPX 텍스트 위치" })).not.toBeInTheDocument();
  expect(screen.queryByText("광고 원본을 불러오는 중입니다.")).not.toBeInTheDocument();
  expect(urls.some((url) => url.includes("/preview?"))).toBe(true);
  expect(urls.some((url) => url.includes("/preview/content"))).toBe(true);
});

test("continues advertisement analysis polling into summary and Annotation without exposing forbidden details", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:m5-e2e") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/status")) return response({ reviewId: "REV-M5", advertisementId: "ADV-M5", reviewStatus: "REVIEW_COMPLETED", jobId: "JOB-M5", jobStatus: "COMPLETED", currentStep: "COMPLETED", progressRate: 100, retryCount: 0, maxRetries: 3, nextRetryAt: null, isRetryable: false, failedReasonCode: null, failedReason: null, timeoutAt: null, steps: [{ stepCode: "COMPLETED", stepName: "완료", status: "COMPLETED", timeoutAt: null }], updatedAt: "2026-07-14T12:00:00+09:00" });
    if (url.endsWith("/summary")) return response(summary);
    if (url.endsWith("/advertisements/ADV-M5")) return response({ advertisementId: "ADV-M5", advertisementName: "정기예금 포스터", productGroup: "DEPOSIT", advertisementType: "BRANCH_FLYER", departmentId: "DPT-M5", registeredBy: "USR-M5", registeredAt: "2026-07-14T00:00:00Z", reviewStatus: "REVIEW_COMPLETED", files: [] });
    if (url.includes("/annotations")) return response(annotations);
    if (url.includes("/preview/content")) return new Response(new Blob(["preview"], { type: "image/png" }), { status: 200 });
    if (url.includes("/preview?")) return response({ fileId: "FILE-M5", pageNo: 1, totalPages: 1, previewPath: "/api/v1/files/FILE-M5/preview/content", width: 1000, height: 500 });
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/reviews/REV-M5/status"]}><App initialSession={session} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("link", { name: "결과 보기" }));
  expect(await screen.findByRole("heading", { name: "AI 검토 결과" })).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("link", { name: "광고 화면 보기" }));
  expect(await screen.findByRole("heading", { name: "검토 위치와 근거 연결" })).toBeInTheDocument();
});

test("renders redacted permission and empty states for result routes", async () => {
  let requestNo = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    requestNo += 1;
    if (requestNo === 1) return response({ code: "FORBIDDEN", message: "parser-artifacts/private/key", traceId: "req-m5-403" }, 403);
    return response({ contents: [], page: 1, size: 20, totalElements: 0, totalPages: 0 });
  }));

  const first = render(<MemoryRouter initialEntries={["/reviews/REV-M5/results"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("접근 권한이 없습니다.");
  expect(screen.queryByText(/parser-artifacts/)).not.toBeInTheDocument();
  first.unmount();
  render(<MemoryRouter initialEntries={["/reviews/REV-M5/results/items"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText("조건에 맞는 검토 항목이 없습니다.")).toBeInTheDocument();
});
