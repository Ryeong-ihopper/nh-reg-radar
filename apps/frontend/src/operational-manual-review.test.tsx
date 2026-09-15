import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperationalExecutionNotice } from "./components/OperationalExecutionNotice";

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: { total_seconds: 1, predicted_count: 1, deferred_count: 1,
    deferred_rules: [{ item_id: "SYNTHETIC", input_requirement: "광고물",
      reason: "시인성은 사람 검토 대상입니다. 좌표는 위치 확인용이며 색상·폰트·글자 크기는 자동 판정하지 않습니다." }] } }),
}));

describe("manual visibility review", () => {
  it("shows the human review reason instead of masking it with the input type", () => {
    render(<OperationalExecutionNotice token="test" reviewId="test" />);
    expect(screen.getByText("사람 검토·추가 확인 항목 보기")).toBeTruthy();
    expect(screen.getByText(/시인성은 사람 검토 대상/).textContent).toContain("자동 판정하지 않습니다");
  });
});
