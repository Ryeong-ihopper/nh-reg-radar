import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OperationalResultsPage } from "./pages/OperationalReviewReportPage";

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
      { item_id: "C-997", title: "추가 확인 항목", verdict: "판단불가", evidence: "", reason: "원문 확인 필요" },
      { item_id: "TPL-review", title: "선택 템플릿 확인 항목", verdict: "판단불가", evidence: "", reason: "원문 확인 필요" },
      { item_id: "TPL-synthetic", title: "예시 상품 · 안내", verdict: "충족", evidence: "", reason: "안내 확인" },
    ],
    excluded_rows: [
      { item_id: "C-EXCLUDED", title: "적용 제외 예시", verdict: "미해당", evidence: "", reason: "상품 범위 불일치" },
    ],
    output_failure_count: 1,
    output_failure_pairs: [{ ad_id: "synthetic-ad", item_id: "C-998" }],
  } : undefined }),
}));

describe("operational result titles", () => {
  it("hides internal IDs while keeping equally named rules selectable and filterable", () => {
    const { container } = render(<MemoryRouter><OperationalResultsPage /></MemoryRouter>);
    const cards = container.querySelectorAll(".review-result-card");
    expect(cards).toHaveLength(4);
    const filters = screen.getByRole("group", { name: "판정별 보기" });
    expect(within(filters).getByRole("button", { name: "전체 4" })).toHaveAttribute("aria-pressed", "true");
    expect(within(filters).getByRole("button", { name: "전체 4" }).childElementCount).toBe(0);
    expect(screen.queryByRole("button", { name: /우선 검토|규제목록/ })).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("항목별 판정 목록")).getAllByText("예시 상품 · 안내")).toHaveLength(2);
    expect(container.textContent).not.toMatch(/C-999|TPL-synthetic|C-998|C-EXCLUDED/);
    expect(screen.queryByText("적용 제외 내역 1건")).not.toBeInTheDocument();
    expect(screen.getByText("항목 1 · 모델 응답 형식 또는 원문 근거 연결 실패")).toBeTruthy();
    fireEvent.click(within(filters).getByRole("button", { name: "확인필요 2" }));
    expect(container.querySelectorAll(".review-result-card")).toHaveLength(2);
    expect(within(screen.getByLabelText("항목별 판정 목록")).getByText("추가 확인 항목")).toBeInTheDocument();
    fireEvent.click(within(filters).getByRole("button", { name: "적정 1" }));
    expect(container.querySelectorAll(".review-result-card")).toHaveLength(1);
    expect(container.querySelector(".review-result-card")?.textContent).toContain("적정");
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
    expect(screen.getByRole("button", { name: "PDF 저장·인쇄" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "추천 문구·수정 초안" })).toBeInTheDocument();
  });
});
