import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { QaAnswer } from "./api/client";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "qa-access-token",
  user: { userId: "USR-QA", userName: "QA 검토자", departmentId: "DPT-QA", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] },
};

const answer: QaAnswer = {
  qaId: "QA-1",
  qaSessionId: "QAS-1",
  question: "우대금리 문구에 함께 표시해야 할 조건은 무엇인가요?",
  answerSummary: "우대 조건과 적용 기간을 함께 표시해야 합니다.",
  answerDetail: "우대금리를 표시할 때에는 조건과 기간을 같은 화면에서 확인할 수 있어야 합니다.",
  evidences: [],
  suggestedPhrases: [],
  needsHumanReview: false,
  createdAt: "2026-07-27T10:00:00+09:00",
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stubQaEndpoints(history: QaAnswer[]): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/reviews/REV-QA/summary")) return response({
      reviewId: "REV-QA", advertisementId: "ADV-QA", standardEffectiveDate: "2026-07-14", standardVersionIds: ["STDV-QA"],
      overallRiskLevel: "MEDIUM", totalItemCount: 1, needsRevisionCount: 0, needsConfirmationCount: 1,
      reviewTypeSummary: [], topRisks: [], completedAt: "2026-07-14T12:00:00+09:00",
    });
    if (url.endsWith("/advertisements/ADV-QA")) return response({
      advertisementId: "ADV-QA", advertisementName: "예금 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER",
      departmentId: "DPT-QA", registeredBy: "USR-QA", registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "REVIEW_COMPLETED", files: [],
    });
    if (url.includes("/qa/questions")) return response(history);
    throw new Error(`Unexpected request: ${url}`);
  }));
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

// 결함 #26: 탭 바가 이 화면에서만 페이지 헤더 그리드 안에 중첩되어 제목과 같은 행으로 밀렸다.
test("keeps the review tab bar as a sibling of the page header like the other result tabs", async () => {
  stubQaEndpoints([]);

  render(<MemoryRouter initialEntries={["/reviews/REV-QA/results/qa"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "광고 규정 Q&A", level: 2 })).toBeInTheDocument();

  const header = document.querySelector(".page-header");
  const navigation = document.querySelector(".review-navigation");
  expect(header).not.toBeNull();
  expect(navigation).not.toBeNull();
  expect(header?.contains(navigation!)).toBe(false);
  expect(navigation?.previousElementSibling).toBe(header);
  expect(document.querySelector(".qa-page-heading")).toBeNull();
});

// 결함 #26: scrollIntoView가 문서까지 스크롤해 sticky가 아닌 탭 바가 화면 밖으로 밀려 올라갔다.
test("scrolls only inside the message list and never on first paint with no messages", async () => {
  stubQaEndpoints([]);
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  const scrollTo = vi.fn();
  Element.prototype.scrollTo = scrollTo as unknown as Element["scrollTo"];

  render(<MemoryRouter initialEntries={["/reviews/REV-QA/results/qa"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "무엇을 확인할까요?" })).toBeInTheDocument();
  // 조회 실패나 미완료 상태로 빈 화면이 렌더되어 통과하는 위양성을 막는다.
  expect(await screen.findByText(/기준 적용일 2026-07-14/)).toBeInTheDocument();
  await waitFor(() => { expect(screen.queryByRole("status")).toBeNull(); });
  expect(screen.queryByRole("alert")).toBeNull();

  expect(scrollIntoView).not.toHaveBeenCalled();
  expect(scrollTo).not.toHaveBeenCalled();
});

test("scrolls the message list container once history arrives", async () => {
  stubQaEndpoints([answer]);
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  const scrollTo = vi.fn();
  Element.prototype.scrollTo = scrollTo as unknown as Element["scrollTo"];

  render(<MemoryRouter initialEntries={["/reviews/REV-QA/results/qa"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();

  expect(scrollIntoView).not.toHaveBeenCalled();
  expect(scrollTo).toHaveBeenCalledTimes(1);
  expect(scrollTo.mock.instances[0]).toBe(document.querySelector(".qa-message-list"));
});

// jsdom은 레이아웃을 계산하지 않으므로 높이 제약은 스타일시트에서 직접 확인한다. 대화 패널의 높이
// 상한이 사라지면 목록이 이력 길이만큼 늘어나 내부 overflow가 생기지 않고, scrollTo가 무력화되면서
// 문서 전체가 스크롤된다. 반응형 구간에서 상한을 제거하는 회귀를 막는다.
// 한계: 텍스트 검사이므로 더 구체적인 selector의 override는 잡지 못한다. 그 범위는 실제 브라우저의
// computed style 확인이 필요하다.
const UNBOUNDED_MAX_HEIGHT = new Set(["none", "initial", "unset", "revert", "revert-layer", "auto"]);

test("keeps a finite height cap on the chat panel at every breakpoint", () => {
  const stylesheet = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
  const declarations = [...stylesheet.matchAll(/\.qa-chat-panel\s*\{([^}]*)\}/g)].map((match) => match[1]);

  expect(declarations.length).toBeGreaterThan(0);
  for (const declaration of declarations) {
    // 기본 규칙과 좁은 폭 재정의 모두 유한한 상한을 선언해야 한다.
    const maxHeight = /max-height\s*:\s*([^;}]+)/.exec(declaration)?.[1].trim();
    expect(maxHeight).toBeDefined();
    expect(UNBOUNDED_MAX_HEIGHT.has(maxHeight!.toLowerCase())).toBe(false);
  }
  expect(/\.qa-message-list\s*\{[^}]*overflow\s*:\s*auto/.test(stylesheet)).toBe(true);
});
