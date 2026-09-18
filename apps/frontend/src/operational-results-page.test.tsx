import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OperationalResultsPage } from "./pages/OperationalResultsPage";

vi.mock("./auth/useAuth", () => ({ useAuth: () => ({ session: {
  accessToken: "test",
  user: { roles: ["COMPLIANCE_REVIEWER"] },
} }) }));
vi.mock("@tanstack/react-query", () => ({
  useMutation: (options: { mutationFn: () => Promise<unknown>; onSuccess?: () => void }) => ({
    isPending: false,
    isError: false,
    mutate: () => void options.mutationFn().then(() => options.onSuccess?.()),
  }),
  useQuery: ({ queryKey }: { queryKey: string[] }) => ({ data: queryKey[0] === "operational-workspace" ? {
    rows: [
      { item_id: "C-999", title: "예시 상품 · 안내", verdict: "위반", evidence: "", reason: "안내 확인 필요" },
      { item_id: "TPL-synthetic", title: "예시 상품 · 안내", verdict: "충족", evidence: "", reason: "안내 확인" },
    ],
    output_failure_count: 1,
    output_failure_pairs: [{ ad_id: "synthetic-ad", item_id: "C-998" }],
  } : undefined }),
}));

describe("operational result titles", () => {
  it("hides internal IDs while keeping equally named rules selectable and filterable", () => {
    const { container } = render(<MemoryRouter><OperationalResultsPage /></MemoryRouter>);
    const cards = container.querySelectorAll("article.single-regulation");
    expect(cards).toHaveLength(2);
    expect(screen.getAllByText("예시 상품 · 안내")).toHaveLength(2);
    expect(container.textContent).not.toMatch(/C-999|TPL-synthetic|C-998/);
    expect(screen.getByText("항목 1 · 모델 응답 형식 또는 원문 근거 연결 실패")).toBeTruthy();
    fireEvent.focus(cards[0]);
    expect(cards[0].getAttribute("data-active")).toBe("true");
    fireEvent.focus(cards[1]);
    expect(cards[0].getAttribute("data-active")).toBe("false");
    expect(cards[1].getAttribute("data-active")).toBe("true");
    fireEvent.click(within(screen.getByLabelText("판정 상태 필터")).getByRole("button", { name: "충족 1" }));
    expect(container.querySelectorAll("article.single-regulation")).toHaveLength(1);
    expect(container.querySelector("article.single-regulation")?.textContent).toContain("충족");
  });

  it("does not place deletion controls on the result page", () => {
    render(<MemoryRouter><OperationalResultsPage /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "심의 결과 삭제" })).not.toBeInTheDocument();
  });

  it("uses the compact result toolbar without repeating the four-step workflow", () => {
    render(<MemoryRouter><OperationalResultsPage /></MemoryRouter>);
    expect(screen.queryByRole("navigation", { name: "광고 심의 업무 단계" })).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "검토 진행 상황" })).toHaveTextContent("결과 확인");
    expect(screen.getByRole("link", { name: "진행 기록" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "결과 JSON 다운로드" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PDF 저장·인쇄" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "광고물 목록" })).toBeInTheDocument();
  });
});
