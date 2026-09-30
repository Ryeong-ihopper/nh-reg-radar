import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import type { AuthSession } from "./auth/context";

vi.mock("./api/operational", async (original) => ({ ...await original<typeof import("./api/operational")>(), operationalMode: true, localAuthBypass: false }));
const session: AuthSession = { accessToken: "synthetic-token", user: { userId: "U", userName: "검토자", departmentId: "D", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] } };
const base = "투자성상품-퇴직연금 일반";
const isa = "투자성상품-개인종합자산관리계좌(ISA) 일반";
const irpWithoutInvestment = "투자성상품-퇴직연금(IRP) 금융투자상품 미노출";
const irpWithFund = "투자성상품-퇴직연금(IRP) 펀드상품 노출";
const context = { code: "RETIREMENT", label: "퇴직연금", base_template: base, components: [{ code: "FUND", label: "펀드", template: "투자성상품-펀드" }, { code: "ETF", label: "ETF", template: "투자성상품-ETF" }, { code: "ELB", label: "ELB", template: "투자성상품-ELB" }], restricted_standalone_templates: ["투자성상품-펀드", "투자성상품-ETF", "투자성상품-ELB"] };
const irpContext = { code: "RETIREMENT", label: "IRP 펀드상품 노출", base_template: irpWithFund, components: [{ code: "ETF", label: "ETF", template: "투자성상품-ETF" }, { code: "ELB", label: "ELB", template: "투자성상품-ELB" }], restricted_standalone_templates: [] };
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderAdvertisementCreatePage() {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); calls.push({ url, init });
    if (url.endsWith("/codes/product-groups")) return response([{ code: "INVESTMENT", name: "투자성", enabled: true }]);
    if (url.endsWith("/codes/advertisement-types")) return response(["NOTICE", "SMS", "LMS", "MMS", "SEARCH_AD", "POPUP"].map((code) => ({ code, name: code, enabled: true })));
    if (url.endsWith("/operational/capabilities")) return response({ enabled: true, productClassifications: [base, isa, irpWithoutInvestment, irpWithFund, "투자성상품-펀드", "투자성상품-ETF", "투자성상품-ELB"].map((code) => ({ code, label: code, productGroup: "INVESTMENT" })), productContexts: [context, irpContext], sourcePolicy: "template-only" });
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
  expect(screen.queryByRole("option", { name: /퇴직연금 — ETF/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  fireEvent.click(screen.getByRole("checkbox", { name: "ETF" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "ELB" }));
  fireEvent.change(screen.getByLabelText("광고 1 원본 파일"), { target: { files: [new File(["synthetic"], "test.png", { type: "image/png" })] } });
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products).toHaveLength(1);
  expect(intake.products[0]).toMatchObject({ product_classification_code: base, underlying_products: ["ETF", "ELB"], underlying_products_status: "CONFIRMED" });
});

test("IRP without investment exposure remains separate and has no component picker", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  const classification = screen.getByRole("combobox", { name: /상세 상품군/ });
  const irpGroup = Array.from(classification.querySelectorAll("optgroup")).find((group) => group.label === "IRP 전용 심의방법");
  expect(irpGroup).toBeDefined();
  expect(Array.from(irpGroup!.querySelectorAll("option")).map((option) => option.value)).toEqual([irpWithoutInvestment, irpWithFund]);
  fireEvent.change(classification, { target: { value: irpWithoutInvestment } });
  expect(screen.queryByRole("checkbox", { name: "펀드" })).not.toBeInTheDocument();
  expect(screen.queryByRole("checkbox", { name: "ETF" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const routing = JSON.parse(String(calls.find((call) => call.url.endsWith("/routing"))?.init?.body));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(routing.product_classification_code).toBe(irpWithoutInvestment);
  expect(intake.products[0]).toMatchObject({ product_classification_code: irpWithoutInvestment, underlying_products: [], underlying_products_status: "CONFIRMED" });
});

test("IRP fund exposure keeps the fund template and adds ETF and ELB together", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: irpWithFund } });
  expect(screen.queryByRole("checkbox", { name: "펀드" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "ETF" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "ELB" }));
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products[0]).toMatchObject({ product_classification_code: irpWithFund, underlying_products: ["ETF", "ELB"], underlying_products_status: "CONFIRMED" });
});

test("IRP fund only confirms no additional ETF or ELB", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: irpWithFund } });
  fireEvent.click(screen.getByRole("radio", { name: "ETF·ELB 언급 없음" }));
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products[0]).toMatchObject({ product_classification_code: irpWithFund, underlying_products: [], underlying_products_status: "CONFIRMED" });
});

test.each(["펀드", "ETF", "ELB"])("the %s retirement checkbox submits the base and component without a standalone route", async (component) => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  fireEvent.click(screen.getByRole("checkbox", { name: component }));
  expect(screen.getByRole("checkbox", { name: component })).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const routing = JSON.parse(String(calls.find((call) => call.url.endsWith("/routing"))?.init?.body));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(routing.product_classification_code).toBe(base);
  expect(intake.products).toHaveLength(1);
  expect(intake.products[0]).toMatchObject({ product_classification_code: base, underlying_products: [component === "펀드" ? "FUND" : component], underlying_products_status: "CONFIRMED" });
});

test("changing retirement to ISA clears component selection before submitting", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  fireEvent.click(screen.getByRole("checkbox", { name: "ETF" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "ELB" }));
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: isa } });
  expect(screen.queryByRole("checkbox", { name: "ETF" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products[0]).toMatchObject({ product_classification_code: isa, underlying_products: [], underlying_products_status: "CONFIRMED" });
});

test("other retirement products retain incomplete scope instead of reusing a supported template", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  fireEvent.click(screen.getByRole("radio", { name: /기타 운용상품.*정기예금/ }));
  expect(screen.getByRole("radio", { name: /기타 운용상품.*정기예금/ })).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.products[0]).toMatchObject({ product_classification_code: base, underlying_products: [], underlying_products_status: "UNCONFIRMED" });
});

test("choosing a known retirement product clears the no-product choice", async () => {
  renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: base } });
  const none = screen.getByRole("radio", { name: /모두 언급 없음/ });
  fireEvent.click(none);
  expect(none).toBeChecked();
  fireEvent.click(screen.getByRole("checkbox", { name: "ETF" }));
  expect(none).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "ETF" })).toBeChecked();
});

test("explicit LMS selection is preserved in the registered media metadata", async () => {
  const calls = renderAdvertisementCreatePage();
  await fillAdvertisementDetails();
  expect(screen.getByRole("option", { name: "장문 문자(LMS)" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "멀티미디어 문자(MMS)" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "검색 광고" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "팝업 광고" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: /광고 형식/ }), { target: { value: "LMS" } });
  fireEvent.change(screen.getByRole("combobox", { name: /상세 상품군/ }), { target: { value: isa } });
  fireEvent.click(screen.getByRole("button", { name: /등록.*자동심의/ }));
  await waitFor(() => expect(calls.some((call) => call.url.endsWith("/intake"))).toBe(true));
  const intake = JSON.parse(String(calls.find((call) => call.url.endsWith("/intake"))?.init?.body));
  expect(intake.media_codes).toEqual(["LMS"]);
});

test("the worklist distinguishes current plans, design candidates, and source holds", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ counts: { templates: 239, supplement_32: 32, additional_34: 34 }, rows: [{ id: "synthetic-source", label: "판본 확인 검사", kind: "ADDITIONAL_34", scope: "투자성", status: "SOURCE_VERSION_HOLD", note: "판본 확인 후 구조화", owner: "사람", source: { 판정기준: "원문 보존" } }] })));
  render(<MemoryRouter initialEntries={["/review-criteria"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "판본 확인 검사" })).toBeInTheDocument();
  expect(screen.getByText(/자동 판정에 일괄 활성화되지/)).toBeInTheDocument();
  expect(screen.getAllByText(/판본 확인 보류/).length).toBeGreaterThan(0);
});
