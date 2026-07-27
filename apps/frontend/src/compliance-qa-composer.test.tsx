import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { QaAnswer } from "./api/client";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "qa-composer-token",
  user: { userId: "USR-QA", userName: "QA 검토자", departmentId: "DPT-QA", departmentName: "상품부", roles: ["PRODUCT_DEPARTMENT_USER"] },
};

const answer: QaAnswer = {
  qaId: "QA-1",
  qaSessionId: "QAS-1",
  question: "우대금리 조건을 어떻게 표시해야 하나요?",
  answerSummary: "우대 조건과 적용 기간을 함께 표시해야 합니다.",
  answerDetail: "조건과 기간을 같은 화면에서 확인할 수 있어야 합니다.",
  evidences: [],
  suggestedPhrases: [],
  needsHumanReview: false,
  createdAt: "2026-07-27T10:00:00+09:00",
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Ask = { resolve: (value: QaAnswer) => void; reject: (reason: Error) => void };
type HistoryRead = { resolve: (value: QaAnswer[]) => void };

/** POST /qa/questions와 이력 GET의 응답 시점을 테스트가 직접 제어한다. */
function stubEndpoints(history: QaAnswer[], options: { holdHistoryFrom?: number } = {}): { calls: string[]; pending: Ask[]; historyReads: HistoryRead[] } {
  const calls: string[] = [];
  const pending: Ask[] = [];
  const historyReads: HistoryRead[] = [];
  let historyCallCount = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url.endsWith("/reviews/REV-QA/summary")) return response({
      reviewId: "REV-QA", advertisementId: "ADV-QA", standardEffectiveDate: "2026-07-14", standardVersionIds: ["STDV-QA"],
      overallRiskLevel: "MEDIUM", totalItemCount: 1, needsRevisionCount: 0, needsConfirmationCount: 1,
      reviewTypeSummary: [], topRisks: [], completedAt: "2026-07-14T12:00:00+09:00",
    });
    if (url.endsWith("/advertisements/ADV-QA")) return response({
      advertisementId: "ADV-QA", advertisementName: "예금 광고", productGroup: "SAVINGS", advertisementType: "MOBILE_BANNER",
      departmentId: "DPT-QA", registeredBy: "USR-QA", registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "REVIEW_COMPLETED", files: [],
    });
    if (url.includes("/qa/questions") && init?.method === "POST") {
      return new Promise<Response>((resolve, reject) => {
        pending.push({ resolve: (value) => resolve(response(value)), reject });
      });
    }
    if (url.includes("/qa/questions")) {
      historyCallCount += 1;
      // holdHistoryFrom번째 이력 조회부터는 테스트가 완료 시점을 정한다.
      if (options.holdHistoryFrom !== undefined && historyCallCount >= options.holdHistoryFrom) {
        return new Promise<Response>((resolve) => {
          historyReads.push({ resolve: (value) => resolve(response(value)) });
        });
      }
      return response(history);
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
  return { calls, pending, historyReads };
}

async function renderQaPage(): Promise<HTMLTextAreaElement> {
  render(<MemoryRouter initialEntries={["/reviews/REV-QA/results/qa"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText(/기준 적용일 2026-07-14/)).toBeInTheDocument();
  const field = await screen.findByLabelText("질문");
  await waitFor(() => { expect(screen.getByRole("button", { name: /질문 보내기/ })).toBeInTheDocument(); });
  return field as HTMLTextAreaElement;
}

function postCount(calls: string[]): number {
  return calls.filter((call) => call.startsWith("POST")).length;
}

/** fetch는 마이크로태스크에서 호출되므로 전송 기록을 기다린다. */
async function waitForPost(calls: string[], expected: number): Promise<void> {
  await waitFor(() => { expect(postCount(calls)).toBe(expected); });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test("sends on Enter, inserts a newline on Shift+Enter, and ignores Enter during IME composition", async () => {
  const { calls } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: "줄바꿈 시도" } });
  // preventDefault를 호출하지 않아야 브라우저가 줄바꿈을 넣는다. fireEvent는 기본 동작이
  // 유지되면 true를 반환한다.
  expect(fireEvent.keyDown(field, { key: "Enter", shiftKey: true })).toBe(true);
  // IME 조합 중 Enter는 조합 확정이므로 전송하지 않는다.
  fireEvent.keyDown(field, { key: "Enter", isComposing: true });
  await waitForPost(calls, 0);
  expect(field).toHaveValue("줄바꿈 시도");

  fireEvent.keyDown(field, { key: "Enter" });
  await waitForPost(calls, 1);
});

test("shows the question immediately while the answer is still in flight", async () => {
  const { pending } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: answer.question } });
  fireEvent.keyDown(field, { key: "Enter" });

  // 서버 응답 전에도 사용자 말풍선이 보이고 입력창은 비워진다.
  const sending = await screen.findByRole("article", { name: "전송 중인 질문" });
  expect(within(sending).getByText(answer.question)).toBeInTheDocument();
  expect(field).toHaveValue("");
  expect(screen.getByRole("article", { name: "답변 생성 중" })).toBeInTheDocument();

  pending[0].resolve(answer);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();
  expect(screen.queryByRole("article", { name: "전송 중인 질문" })).toBeNull();
});

test("keeps a failed question as its own message with a retry action", async () => {
  const { pending, calls } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: "실패할 질문" } });
  fireEvent.keyDown(field, { key: "Enter" });
  expect(field).toHaveValue("");
  await waitFor(() => { expect(pending).toHaveLength(1); });

  pending[0].reject(new Error("network down"));
  const failed = await screen.findByRole("article", { name: "전송하지 못한 질문" });
  expect(within(failed).getByText("실패할 질문")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toBeInTheDocument();

  fireEvent.click(within(failed).getByRole("button", { name: "다시 시도" }));
  await waitForPost(calls, 2);
  await waitFor(() => { expect(pending).toHaveLength(2); });
  pending[1].resolve(answer);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();
  expect(screen.queryByRole("article", { name: "전송하지 못한 질문" })).toBeNull();
});

// MEDIUM 2: A 전송 -> B 입력 -> A 실패. B를 지키려고 A를 버리면 재시도 경로가 사라진다.
test("preserves a new draft and the failed question at the same time", async () => {
  const { pending } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: "질문 A" } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(1); });
  fireEvent.change(field, { target: { value: "질문 B" } });

  pending[0].reject(new Error("network down"));
  const failed = await screen.findByRole("article", { name: "전송하지 못한 질문" });
  expect(within(failed).getByText("질문 A")).toBeInTheDocument();
  expect(field).toHaveValue("질문 B");
});

// 미해결 실패 질문은 다른 질문의 성공·실패에 영향받지 않아야 한다.
test("keeps an unresolved failed question when a different question succeeds", async () => {
  const { pending } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: "질문 A" } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].reject(new Error("network down"));
  expect(await screen.findByRole("article", { name: "전송하지 못한 질문" })).toBeInTheDocument();

  fireEvent.change(field, { target: { value: "질문 B" } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(2); });
  pending[1].resolve(answer);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();

  const failures = screen.getAllByRole("article", { name: "전송하지 못한 질문" });
  expect(failures).toHaveLength(1);
  expect(within(failures[0]).getByText("질문 A")).toBeInTheDocument();
});

test("keeps every failed question retryable when two sends fail", async () => {
  const { pending } = stubEndpoints([]);
  const field = await renderQaPage();

  fireEvent.change(field, { target: { value: "질문 A" } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].reject(new Error("network down"));
  expect(await screen.findByRole("article", { name: "전송하지 못한 질문" })).toBeInTheDocument();

  fireEvent.change(field, { target: { value: "질문 B" } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(2); });
  pending[1].reject(new Error("network down"));

  await waitFor(() => { expect(screen.getAllByRole("article", { name: "전송하지 못한 질문" })).toHaveLength(2); });
  const failures = screen.getAllByRole("article", { name: "전송하지 못한 질문" });
  expect(failures.map((node) => node.querySelector("p")?.textContent)).toEqual(["질문 A", "질문 B"]);
  for (const failure of failures) expect(within(failure).getByRole("button", { name: "다시 시도" })).toBeEnabled();

  // A만 재시도해 성공시키면 A만 사라지고 B는 남는다.
  fireEvent.click(within(failures[0]).getByRole("button", { name: "다시 시도" }));
  await waitFor(() => { expect(pending).toHaveLength(3); });
  pending[2].resolve(answer);
  await waitFor(() => { expect(screen.getAllByRole("article", { name: "전송하지 못한 질문" })).toHaveLength(1); });
  expect(within(screen.getByRole("article", { name: "전송하지 못한 질문" })).getByText("질문 B")).toBeInTheDocument();
});

// MEDIUM 1: 이력 조회가 끝나기 전에는 현재 세션을 알 수 없고, 늦게 끝난 조회가 답변을 덮어쓴다.
test("blocks sending until the first history read completes", async () => {
  const { calls } = stubEndpoints([], { holdHistoryFrom: 1 });
  render(<MemoryRouter initialEntries={["/reviews/REV-QA/results/qa"]}><App initialSession={session} /></MemoryRouter>);
  expect(await screen.findByText(/기준 적용일 2026-07-14/)).toBeInTheDocument();
  const field = await screen.findByLabelText("질문");

  fireEvent.change(field, { target: { value: "이력 조회 중 질문" } });
  expect(screen.getByRole("button", { name: /질문 보내기/ })).toBeDisabled();
  fireEvent.keyDown(field, { key: "Enter" });
  await waitForPost(calls, 0);
  expect(field).toHaveValue("이력 조회 중 질문");
});

// MEDIUM 1: 전송 뒤에 완료되는 이력 조회가 방금 받은 답변을 지우면 안 된다.
test("keeps the new answer when an in-flight history read finishes after the send", async () => {
  const { pending, historyReads } = stubEndpoints([], { holdHistoryFrom: 2 });
  const field = await renderQaPage();

  // 탭 복귀(visibilitychange)로 배경 재조회를 일으켜 진행 중인 이력 조회를 만든다.
  // TanStack Query v5의 focusManager는 window focus가 아니라 이 이벤트를 구독한다.
  window.dispatchEvent(new Event("visibilitychange"));
  await waitFor(() => { expect(historyReads).toHaveLength(1); });

  fireEvent.change(field, { target: { value: answer.question } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].resolve(answer);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();

  // 뒤늦게 완료된 조회는 새 답변이 없는 오래된 목록을 담고 있다.
  const staleAnswer: QaAnswer = { ...answer, qaId: "QA-STALE", answerSummary: "오래된 목록의 답변" };
  historyReads[0].resolve([staleAnswer]);

  // 지연 응답이 처리된 뒤에 단정해야 한다. 다음 재조회가 시작되는 시점을 순서 기준으로 삼는다.
  // (이 기준점 없이 곧바로 단정하면 아직 반영되지 않은 상태를 보고 통과한다.)
  window.dispatchEvent(new Event("visibilitychange"));
  await waitFor(() => { expect(historyReads).toHaveLength(2); });

  expect(screen.getByText(answer.answerSummary)).toBeInTheDocument();
  expect(screen.queryByText(staleAnswer.answerSummary)).toBeNull();
});

test("does not refetch the history right after appending the answer", async () => {
  const { pending, calls } = stubEndpoints([]);
  const field = await renderQaPage();
  const historyReadsBefore = calls.filter((call) => call === "GET /api/qa/questions?reviewId=REV-QA").length;

  fireEvent.change(field, { target: { value: answer.question } });
  fireEvent.keyDown(field, { key: "Enter" });
  await waitFor(() => { expect(pending).toHaveLength(1); });
  pending[0].resolve(answer);
  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();

  // 즉시 refetch하면 append와 경쟁해 방금 받은 답변이 사라져 보일 수 있다.
  await waitFor(() => { expect(screen.getByText(answer.answerSummary)).toBeInTheDocument(); });
  const historyReadsAfter = calls.filter((call) => call === "GET /api/qa/questions?reviewId=REV-QA").length;
  expect(historyReadsAfter).toBe(historyReadsBefore);
});

test("renders a machine-readable timestamp on stored messages", async () => {
  stubEndpoints([answer]);
  await renderQaPage();

  expect(await screen.findByText(answer.answerSummary)).toBeInTheDocument();
  const timestamps = [...document.querySelectorAll("time.qa-message-time")];
  expect(timestamps.length).toBeGreaterThanOrEqual(2);
  for (const timestamp of timestamps) {
    expect(timestamp.getAttribute("dateTime")).toBe(answer.createdAt);
    expect(timestamp.textContent?.trim()).not.toBe("");
  }
});

// 비차단 보강: 자동 높이가 실제로 내용 높이를 따라가고, 상한·넘침 처리는 CSS가 유지한다.
test("grows the input to fit its content and caps the height in the stylesheet", async () => {
  stubEndpoints([]);
  const field = await renderQaPage();

  // jsdom은 레이아웃을 계산하지 않으므로 내용 높이를 대신 제공한다.
  Object.defineProperty(field, "scrollHeight", { configurable: true, get: () => 132 });
  fireEvent.change(field, { target: { value: "여러\n줄\n질문" } });
  await waitFor(() => { expect(field.style.height).toBe("132px"); });

  const stylesheet = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
  const rule = /\.qa-composer textarea \{([^}]*)\}/.exec(stylesheet)?.[1] ?? "";
  const maxHeight = /max-height\s*:\s*([^;}]+)/.exec(rule)?.[1].trim();
  expect(maxHeight).toBeDefined();
  expect(["none", "initial", "unset", "revert", "auto"]).not.toContain(maxHeight!.toLowerCase());
  expect(rule).toMatch(/overflow-y\s*:\s*auto/);
});

test("keeps the send button disabled until the draft has content", async () => {
  stubEndpoints([]);
  const field = await renderQaPage();
  const send = screen.getByRole("button", { name: /질문 보내기/ });

  expect(send).toBeDisabled();
  fireEvent.change(field, { target: { value: "   " } });
  expect(send).toBeDisabled();
  fireEvent.change(field, { target: { value: "실제 질문" } });
  expect(send).toBeEnabled();
});
