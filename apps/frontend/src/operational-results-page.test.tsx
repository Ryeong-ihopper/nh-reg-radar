import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OperationalResultsPage } from "./pages/OperationalResultsPage";

vi.mock("./auth/useAuth", () => ({ useAuth: () => ({ session: { accessToken: "test" } }) }));
vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({}),
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
});
