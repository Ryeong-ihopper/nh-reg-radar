import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

test("renders the M1 root route", () => {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: "광고심의 적정성 검토 플랫폼" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "주 탐색" })).toBeInTheDocument();
});

test("renders the not-found route", () => {
  render(
    <MemoryRouter initialEntries={["/missing"]}>
      <App />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: "페이지를 찾을 수 없습니다." })).toBeInTheDocument();
});
