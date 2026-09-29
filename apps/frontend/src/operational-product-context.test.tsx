import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import type { AuthSession } from "./auth/context";

vi.mock("./api/operational", async (original) => ({ ...await original<typeof import("./api/operational")>(), operationalMode: true, localAuthBypass: false }));
const session: AuthSession = { accessToken: "synthetic-token", user: { userId: "U", userName: "검토자", departmentId: "D", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] } };
const base = "투자성상품-퇴직연금 일반";
const isa = "투자성상품-개인종합자산관리계좌(ISA) 일반";
const context = { code: "RETIREMENT", label: "퇴직연금", base_template: base, components: [{ code: "ETF", label: "ETF", template: "투자성상품-ETF" }, { code: "ELB", label: "ELB", template: "투자성상품-ELB" }], restricted_standalone_templates: ["투자성상품-ETF", "투자성상품-ELB"] };
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderAdvertisementCreatePage() {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url.endsWith("/codes/product-groups")) return response([{ code: "INVESTMENT", name: "투자성", enabled: true }]);
    if (url.endsWith("/codes/advertisement-types")) return response([{ code: "NOTICE", name: "공지", enabled: true }]);
    if (url.endsWith("/operational/capabilities")) return response({ enabled: true, productClassifications: [base, isa, "투자성상품-ETF", "투자성상품-ELB"].map((code) => ({ code, label: code, productGroup: "INVESTMENT" })), productContexts: [context], sourcePolicy: "template-only" });
    if (url.endsWith("/advertisements") && init?.method === "POST") return response({ advertisementId: "ADV-test", advertisementName: "시험 광고", files: [{ fileId: "F", fileName: "test.png", fileType: "ADVERTISEMENT" }] });
    if (url.includes("/operational/advertisements/ADV-test/") && init?.method === "PUT") return response({ saved: true });
    if (url.endsWith("/advertisements/ADV-test/reviews")) return response({ reviewId: "REV-test" });
    if (url.includes("/advertisements?page") || url.endsWith("/advertisements")) return response({ items: [], totalElements: 0, totalPages: 0, page: 0, size: 20 });
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(<MemoryRouter initialEntries={["/advertisements/new"]}><App initialSession={session} /></MemoryRouter>);
  return calls;
}

async function fillAdvertisementDetails() {
  await screen.findByRole("combobox", { name: /^상품군 \*/ });
  fireEvent.change(screen.getByRole("textbox", { name: /광고명/ }), { target: { value: "시험 광고" } });
  fireEvent.change(screen.getByRole("combobox", { name: /^상품군/ }), { target: { value: "INVESTMENT" } });
  fireEvent.change(screen.getByRole("combobox", { name: /광고 형식/ }), { target: { value: "NOTICE" } });
  fireEvent.change(screen.getByLabelText("광고 1 원본 파일"), { target: { files: [new File(["synthetic"], "test.png", { type: "image/png" })] } });
}

test("retirement components are submitted together in one product scope and standalone methods are hidden", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  expect(screen.queryByRole("option", { name: "투자성상품-ETF" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  fireEvent.change(screen.getByRole("combobox", { name: "언급 여부" }), { target: { value: "MENTIONED" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "ETF" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "ELB" }));
  fireEvent.change(screen.getByLabelText("광고 1 원본 파일"), { target: { files: [new File(["synthetic"], "test.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products).toHaveLength(1);
  expect(intake.products[0]).toMatchObject({ product_classification_code: base, underlying_products: ["ETF", "ELB"], underlying_products_status: "CONFIRMED" });
});

test.each(["ETF", "ELB"])("the visible %s retirement option submits the base and component without a standalone route", async (component) => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  const option = screen.getByRole("option", { name: `퇴직연금 — ${component} 운용상품` }) as HTMLOptionElement;
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: option.value } });
  expect(screen.getByRole("checkbox", { name: component })).toBeChecked();
  expect(screen.getByRole("combobox", { name: "언급 여부" })).toHaveValue("MENTIONED");
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const routing = JSON.parse(String(calls.find((call) => call.url.endsWith("/routing"))?.init?.body));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(routing.product_classification_code).toBe(base);
  expect(intake.products).toHaveLength(1);
  expect(intake.products[0]).toMatchObject({ product_classification_code: base, underlying_products: [component], underlying_products_status: "CONFIRMED" });
});

test("changing a retirement preset to ISA clears component selection before submitting", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  const option = screen.getByRole("option", { name: "퇴직연금 — ETF 운용상품" }) as HTMLOptionElement;
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: option.value } });
  fireEvent.click(screen.getByRole("checkbox", { name: "ELB" }));
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: isa } });
  expect(screen.queryByRole("checkbox", { name: "ETF" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products[0]).toMatchObject({ product_classification_code: isa, underlying_products: [], underlying_products_status: "CONFIRMED" });
});

test("the worklist distinguishes current plans, design candidates, and source holds", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ counts: { templates: 239, supplement_32: 32, additional_34: 34 }, rows: [{ id: "synthetic-source", label: "판본 확인 검사", kind: "ADDITIONAL_34", scope: "투자성", status: "SOURCE_VERSION_HOLD", note: "판본 확인 후 구조화", owner: "사람", source: { 판정기준: "원문 보존" } }] })));
  render(<MemoryRouter initialEntries={["/review-criteria"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "판본 확인 검사" })).toBeInTheDocument();
  expect(screen.getByText(/자동 판정에 일괄 활성화되지/)).toBeInTheDocument();
  expect(screen.getAllByText(/판본 확인 보류/).length).toBeGreaterThan(0);
});
