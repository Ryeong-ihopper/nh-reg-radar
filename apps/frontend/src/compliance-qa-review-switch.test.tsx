import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { QaAnswer } from "./api/client";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "qa-switch-token",
  user: { userId: "USR-QA", userName: "QA 검토자", departmentId: "DPT-QA", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] },
};

/** 검토 A와 B는 상품군·광고유형·기준 적용일이 달라 요청이 섞이면 드러난다. */
const REVIEWS = {
  A: { productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER", effectiveDate: "2026-07-14" },
  B: { productGroup: "LOAN", advertisementType: "PRINT", effectiveDate: "2026-07-20" },
} as const;

const answerInReviewA: QaAnswer = {
  qaId: "QA-A1",
  qaSessionId: "QAS-A",
  question: "검토 A의 질문",
  answerSummary: "검토 A의 답변",
  answerDetail: "검토 A 상세",
  evidences: [],
  suggestedPhrases: [],
  needsHumanReview: false,
  createdAt: "2026-07-27T10:00:00+09:00",
};

const historyInReviewB: QaAnswer = {
  qaId: "QA-B1",
  qaSessionId: "QAS-B",
  question: "검토 B의 기존 질문",
  answerSummary: "검토 B의 저장된 답변",
  answerDetail: "검토 B 상세",
  evidences: [],
  suggestedPhrases: [],
  needsHumanReview: false,
  createdAt: "2026-07-27T11:00:00+09:00",
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Ask = { resolve: (value: QaAnswer) => void; reject: (reason: Error) => void };

/** 검토 A/B를 구분해 응답한다. 광고물 경로는 `ADV-*`로도 판별해야 A 응답이 B에 새지 않는다. */
function stubTwoReviews(): { pending: Ask[]; posts: Array<Record<string, unknown>> } {
  const pending: Ask[] = [];
  const posts: Array<Record<string, unknown>> = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const which: "A" | "B" = url.includes("REV-B") || url.includes("ADV-B") ? "B" : "A";
    const review = REVIEWS[which];
    if (url.includes("/summary")) return response({
      reviewId: `REV-${which}`, advertisementId: `ADV-${which}`, standardEffectiveDate: review.effectiveDate,
      standardVersionIds: [`STDV-${which}`], overallRiskLevel: "MEDIUM", totalItemCount: 1,
      needsRevisionCount: 0, needsConfirmationCount: 1, reviewTypeSummary: [], topRisks: [],
      completedAt: "2026-07-14T12:00:00+09:00",
    });
    if (url.includes("/advertisements/ADV-")) return response({
      advertisementId: `ADV-${which}`, advertisementName: `광고 ${which}`, productGroup: review.productGroup,
      advertisementType: review.advertisementType, departmentId: "DPT-QA", registeredBy: "USR-QA",
      registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "REVIEW_COMPLETED", files: [],
    });
    if (url.includes("/qa/questions") && init?.method === "POST") {
      posts.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      return new Promise<Response>((resolve, reject) => {
        pending.push({ resolve: (value) => resolve(response(value)), reject });
      });
    }
    if (url.includes("/qa/questions")) return response(which === "B" ? [historyInReviewB] : []);
    throw new Error(`Unexpected request: ${url}`);
  }));
  return { pending, posts };
}

function SwitchHarness() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => void navigate("/reviews/REV-B/results/qa")}>검토 B로</button>;
}

function renderAtReviewA(): void {
  render(
    <MemoryRouter initialEntries={["/reviews/REV-A/results/qa"]}>
      <App initialSession={session} />
      <SwitchHarness />
    </MemoryRouter>,
  );
}

async function draftField(): Promise<HTMLTextAreaElement> {
  return (await screen.findByLabelText("질문")) as HTMLTextAreaElement;
}

/** 초안을 넣고 전송이 열릴 때까지 기다린 뒤 Enter로 보낸다. */
async function sendQuestion(field: HTMLTextAreaElement, text: string): Promise<void> {
  fireEvent.change(field, { target: { value: text } });
  await waitFor(() => { expect(screen.getByRole("button", { name: /질문 보내기/ })).toBeEnabled(); });
  fireEvent.keyDown(field, { key: "Enter" });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

// 같은 라우트가 reviewId만 바뀌며 재사용되면 이전 검토의 화면 상태가 남는다.
test("does not carry the draft or failed questions across a reviewId change", async () => {
  const { pending } = stubTwoReviews();
  renderAtReviewA();

  const field = await draftField();
  expect(await screen.findByText(/기준 적용일 2026-07-14/)).toBeInTheDocument();

  // 검토 A에서 질문을 실패시켜 실패 말풍선을 만들고, 새 초안도 남긴다.
  await sendQuestion(field, "검토 A의 실패 질문");
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].reject(new Error("network down"));
  expect(await screen.findByRole("article", { name: "전송하지 못한 질문" })).toBeInTheDocument();
  fireEvent.change(field, { target: { value: "검토 A의 남은 초안" } });

  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  expect(await screen.findByText(historyInReviewB.answerSummary)).toBeInTheDocument();

  expect(screen.queryByRole("article", { name: "전송하지 못한 질문" })).toBeNull();
  expect(screen.getByLabelText("질문")).toHaveValue("");
});

// 활성 Q&A 세션이 남으면 다음 검토의 질문이 이전 검토 세션으로 전송된다.
test("sends the next review's own session and context after a reviewId change", async () => {
  const { pending, posts } = stubTwoReviews();
  renderAtReviewA();

  const field = await draftField();
  expect(await screen.findByText(/기준 적용일 2026-07-14/)).toBeInTheDocument();

  // 검토 A에서 질문을 성공시켜 활성 세션을 QAS-A로 만든다.
  await sendQuestion(field, answerInReviewA.question);
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].resolve(answerInReviewA);
  expect(await screen.findByText(answerInReviewA.answerSummary)).toBeInTheDocument();
  expect(posts[0]).toMatchObject({ reviewId: "REV-A", productGroup: "SAVINGS", qaSessionId: null });

  // 검토 B로 이동하면 B의 이력과 B의 검토 맥락이 보인다.
  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  expect(await screen.findByText(historyInReviewB.answerSummary)).toBeInTheDocument();
  expect(screen.queryByText(answerInReviewA.answerSummary)).toBeNull();
  expect(await screen.findByText(/기준 적용일 2026-07-20/)).toBeInTheDocument();

  // 검토 B에서 보낸 질문은 B의 세션과 맥락을 써야 한다.
  const fieldInB = await draftField();
  await sendQuestion(fieldInB, "검토 B의 새 질문");
  await waitFor(() => { expect(posts).toHaveLength(2); });

  expect(posts[1]).toMatchObject({
    question: "검토 B의 새 질문",
    reviewId: "REV-B",
    qaSessionId: "QAS-B",
    productGroup: "LOAN",
    advertisementType: "PRINT",
    standardEffectiveDate: "2026-07-20",
  });
});
