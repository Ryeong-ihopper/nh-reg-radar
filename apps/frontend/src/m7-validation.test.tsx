import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const complianceSession: AuthSession = {
  accessToken: "m7-token",
  user: { userId: "USR-M7", userName: "검증 담당자", departmentId: "DPT-C", departmentName: "준법감시", roles: ["COMPLIANCE_REVIEWER"] },
};
const productSession: AuthSession = {
  accessToken: "product-token",
  user: { userId: "USR-P", userName: "상품 담당자", departmentId: "DPT-P", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] },
};

const dataset = {
  datasetId: "VAL-001", datasetName: "예금 검증셋", productGroup: "DEPOSIT", advertisementType: "BRANCH_FLYER",
  datasetVersion: 2, excluded: false, createdAt: "2026-07-15T00:00:00Z",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("registers a versioned validation dataset and golden judgment through the generated contract", async () => {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url.includes("/validation/datasets?") && (!init?.method || init.method === "GET")) return json({ items: [dataset], page: 1, size: 20, totalElements: 1, totalPages: 1 });
    if (url.endsWith("/validation/datasets") && init?.method === "POST") return json({ ...dataset, datasetId: "VAL-002", datasetVersion: 1 }, 201);
    if (url.endsWith("/validation/datasets/VAL-001/judgments")) return json({ datasetId: "VAL-001", judgments: [{ judgmentId: "JDG-1", datasetId: "VAL-001", targetText: "원금 보장", reviewType: "REQUIRED_PHRASE", expectedStatus: "APPROPRIATE", riskLevel: "LOW", excluded: false, judgmentVersion: 1, judgedBy: "USR-M7", judgedAt: "2026-07-15T00:01:00Z" }] }, 201);
    throw new Error(`Unexpected request: ${url}`);
  }));

  render(<MemoryRouter initialEntries={["/validation/datasets"]}><App initialSession={complianceSession} /></MemoryRouter>);
  expect((await screen.findAllByText("예금 검증셋")).length).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText("데이터셋명"), { target: { value: "신규 검증셋" } });
  fireEvent.change(screen.getByLabelText("샘플 광고물"), { target: { files: [new File(["fixture"], "sample.pdf", { type: "application/pdf" })] } });
  fireEvent.submit(screen.getByRole("button", { name: "검증 데이터 등록" }).closest("form")!);
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/validation/datasets") && call.init?.method === "POST")).toBe(true));
  const multipart = calls.find((call) => call.url.endsWith("/validation/datasets") && call.init?.method === "POST")?.init?.body as FormData;
  expect(multipart.get("datasetName")).toBe("신규 검증셋");
  expect(multipart.get("excluded")).toBe("false");

  fireEvent.change(screen.getByLabelText("대상 문구"), { target: { value: "원금 보장" } });
  fireEvent.click(screen.getByRole("button", { name: "담당자 판단 등록" }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/validation/datasets/VAL-001/judgments"))).toBe(true));
  const judgment = calls.find((call) => call.url.endsWith("/validation/datasets/VAL-001/judgments"));
  expect(JSON.parse(String(judgment?.init?.body)).judgments[0]).toMatchObject({ targetText: "원금 보장", expectedStatus: "APPROPRIATE", excluded: false });
});

test("displays immutable server KPI values, exclusions, and zero-denominator state without recalculation", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/validation/datasets?")) return json({ items: [dataset], page: 1, size: 20, totalElements: 1, totalPages: 1 });
    if (url.endsWith("/validation/evaluations") && init?.method === "POST") return json({ evaluationId: "EVAL-001", evaluationStatus: "COMPLETED", snapshotHash: "sha256:frozen", snapshotCreatedAt: "2026-07-15T00:02:00Z", datasetSnapshotCount: 1, reviewSelectionPolicy: "LATEST_COMPLETED", versionSnapshot: { standardVersionIds: ["STD-V1"], modelVersion: "model-v1", promptVersion: "prompt-v1", parserOcrPolicy: "parser-v1", ragSearchPolicy: "rag-v1" }, exclusionSummary: [{ excludeReasonCode: "OCR_UNREADABLE", count: 1 }], metrics: [{ metricCode: "REQUIRED_PHRASE_ACCURACY", metricName: "필수 문구 검토 정확도", score: 87.5, numerator: 7, denominator: 8, excludedCount: 1, partialCount: 1, notApplicable: false, targetScore: 80, achieved: true }, { metricCode: "EVIDENCE_PRECISION", metricName: "근거 매칭 적정성", score: null, numerator: 0, denominator: 0, excludedCount: 1, partialCount: 0, notApplicable: true, targetScore: 85, achieved: false }] }, 201);
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<MemoryRouter initialEntries={["/validation/evaluations"]}><App initialSession={complianceSession} /></MemoryRouter>);
  fireEvent.click(await screen.findByLabelText("예금 검증셋 선택"));
  fireEvent.click(screen.getByRole("button", { name: "선택 데이터셋 평가 실행" }));
  expect(await screen.findByText("87.5%")).toBeInTheDocument();
  expect(screen.getByText("미적용")).toBeInTheDocument();
  expect(screen.getByText("분모 0 · 목표 판단 제외")).toBeInTheDocument();
  expect(screen.getByText("OCR_UNREADABLE: 1건")).toBeInTheDocument();
  expect(screen.getByText("sha256:frozen")).toBeInTheDocument();
});

test("renders empty and safe error states", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ items: [], page: 1, size: 20, totalElements: 0, totalPages: 0 })));
  const view = render(<MemoryRouter initialEntries={["/validation/datasets"]}><App initialSession={complianceSession} /></MemoryRouter>);
  expect(await screen.findByText("등록된 검증 데이터셋이 없습니다.")).toBeInTheDocument();
  view.unmount();
  vi.stubGlobal("fetch", vi.fn(async () => json({ code: "INTERNAL_ERROR", message: "internal stack", traceId: "trace-safe" }, 500)));
  render(<MemoryRouter initialEntries={["/validation/datasets"]}><App initialSession={complianceSession} /></MemoryRouter>);
  expect(await screen.findByText("일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
  expect(screen.queryByText("internal stack")).not.toBeInTheDocument();
  expect(screen.getByText(/trace-safe/)).toBeInTheDocument();
});

test("blocks an unauthorized product user before any validation request", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter initialEntries={["/validation/evaluations"]}><App initialSession={productSession} /></MemoryRouter>);
  expect(screen.getByRole("alert")).toHaveTextContent("접근 권한이 없습니다.");
  expect(fetchMock).not.toHaveBeenCalled();
});
