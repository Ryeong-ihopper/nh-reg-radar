import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewScopedBoundary } from "./components/ReviewScopedBoundary";
import { OperationalReviewDetail } from "./components/OperationalReviewDetail";
import type { ResultRow } from "./components/operationalResultModel";
import { LegalReferencePage } from "./pages/LegalReferencePage";
import { OperationalSuggestionsPage } from "./pages/OperationalSuggestionsPage";

vi.mock("./auth/useAuth", () => ({useAuth: () => ({session: {accessToken: "synthetic-token"}})}));
vi.mock("./components/OperationalOriginalPanel", () => ({OperationalOriginalPanel: () => <aside aria-label="원문 위치" />}));
const row = {item_id:"SYNTHETIC", row_id:"SCOPE::SYNTHETIC", title:"Synthetic disclosure", verdict:"판단불가", reason:"Reading uncertainty",
  evidence:"Original advertisement quotation", template_appropriate_judgment:"Frozen source criterion", template_example:"Synthetic source example",
  display_checks:[{text:"Source obligation wording",status:"UNDETERMINED",reason:"Unclear source"}],
  rule_basis:{legal_basis_refs:["예금자보호법 제32조"]}, model_assessment:{verdict:"충족",reason:"Withheld model opinion"}} as unknown as ResultRow;
afterEach(() => {vi.restoreAllMocks(); vi.unstubAllGlobals();});
function wrapper(node: React.ReactNode) {
  return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>;
}

describe("showcase review workspace", () => {
  it("separates quotation, frozen criterion and decision from a withheld model opinion", () => {
    render(wrapper(<OperationalReviewDetail row={row} reviewId="R1" onLocate={() => {}} />));
    expect(screen.getByText("Original advertisement quotation").tagName).toBe("BLOCKQUOTE");
    expect(screen.getByText("Frozen source criterion")).toBeVisible();
    expect(screen.getByText("확인필요", {selector:".regulation-verdict"})).toBeVisible();
    const advanced = screen.getByText("추출·검토 상세 정보").closest("details")!;
    expect(advanced).not.toHaveAttribute("open");
    expect(within(advanced).getByText(/Withheld model opinion/)).toBeInTheDocument();
    expect(screen.getByRole("link", {name:/국가법령정보센터/})).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", {name:/추천 문구·수정 초안 보기/})).toHaveAttribute("href", "/reviews/R1/suggestions?item=SCOPE%3A%3ASYNTHETIC");
  });
  it("searches mapped laws and links their original template without executing disabled rules", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({rows:[
      {id:"T1",label:"Synthetic eligibility",scope:"Synthetic deposit",kind:"TEMPLATE",source:{legal_basis:{statute:"예금자보호법 제32조"}}},
      {id:"S1",label:"Disabled rule",scope:"Synthetic",kind:"SUPPLEMENT_32",source:{legal_basis:{statute:"금융지주회사법 제48조"}}},
    ]}), {status:200}));
    vi.stubGlobal("fetch", fetcher);
    render(wrapper(<LegalReferencePage />));
    expect(await screen.findByRole("link", {name:"기준표 보기 →"})).toHaveAttribute("href", "/review-criteria?item=T1");
    expect(screen.queryByText(/금융지주회사법/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), {target:{value:"no such law"}});
    expect(screen.getByText("검색 조건에 맞는 연결 근거가 없습니다.")).toBeVisible();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("starts with an empty editable draft, copies only on request, and resets across reviews", async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({rows:[row]}), {status:200}));
    vi.stubGlobal("fetch", fetcher);
    const copy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", {...navigator, clipboard:{writeText:copy}});
    render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={["/reviews/R1/suggestions"]}><Link to="/reviews/R2/suggestions">Switch review</Link><Routes><Route path="/reviews/:reviewId" element={<ReviewScopedBoundary />}><Route path="suggestions" element={<OperationalSuggestionsPage />} /></Route></Routes></MemoryRouter></QueryClientProvider>);
    const draft = await screen.findByRole("textbox");
    expect(draft).toHaveValue("");
    expect(screen.getByRole("button", {name:"초안 복사"})).toBeDisabled();
    expect(screen.queryByRole("button", {name:/채택|승인/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("기준표 참고 예시 보기"));
    fireEvent.click(screen.getByRole("button", {name:"예시를 초안에 가져오기"}));
    expect(draft).toHaveValue("Synthetic source example");
    fireEvent.change(draft, {target:{value:"Reviewed synthetic wording"}});
    fireEvent.click(screen.getByRole("button", {name:"초안 복사"}));
    await waitFor(() => expect(copy).toHaveBeenCalledWith("Reviewed synthetic wording"));
    fireEvent.click(screen.getByRole("link", {name:"Switch review"}));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
    expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});
