import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

function BrokenChild(): never {
  throw new Error("synthetic render failure");
}

test("renders a safe fallback when a child fails", () => {
  const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

  render(
    <AppErrorBoundary>
      <BrokenChild />
    </AppErrorBoundary>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("화면을 불러오지 못했습니다.");
  expect(document.querySelector(".fatal-error-content")).toBeInTheDocument();
  consoleSpy.mockRestore();
});
