import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AuthSession } from "./auth/context";

const session: AuthSession = {
  accessToken: "boundary-token",
  user: { userId: "USR-B", userName: "검토자", departmentId: "DPT-B", departmentName: "상품부", roles: ["COMPLIANCE_REVIEWER"] },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** 검토 A와 B는 항목·본문이 달라 화면 상태가 섞이면 드러난다. */
function reviewItem(which: "A" | "B") {
  return {
    reviewItemId: `ITEM-${which}`,
    reviewType: "MISLEADING_EXPRESSION",
    resultStatus: "NEEDS_REVISION",
    riskLevel: "HIGH",
    riskPolicyVersion: "risk-policy-v1",
    riskReasonCodes: [],
    targetText: `검토 ${which}의 항목`,
    reason: `검토 ${which}의 사유`,
    evidenceStatus: "MATCHED",
  };
}

function stubTwoReviews(): { urls: string[] } {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    urls.push(`${init?.method ?? "GET"} ${url}`);
    const which: "A" | "B" = url.includes("REV-B") || url.includes("ADV-B") ? "B" : "A";
    const item = reviewItem(which);

    if (url.includes("/summary")) return response({
      reviewId: `REV-${which}`, advertisementId: `ADV-${which}`, standardEffectiveDate: "2026-07-14",
      standardVersionIds: [`STDV-${which}`], overallRiskLevel: "HIGH", totalItemCount: 1, needsRevisionCount: 1,
      needsConfirmationCount: 0, reviewTypeSummary: [], topRisks: [], completedAt: "2026-07-14T12:00:00+09:00",
    });
    if (url.includes("/advertisements/ADV-")) return response({
      advertisementId: `ADV-${which}`, advertisementName: `광고 ${which}`, productGroup: "SAVINGS",
      advertisementType: "MOBILE_BANNER", departmentId: "DPT-B", registeredBy: "USR-B",
      registeredAt: "2026-07-14T10:00:00+09:00", reviewStatus: "REVIEW_COMPLETED", files: [],
    });
    if (url.includes(`/items/ITEM-`)) return response({
      ...item,
      recommendation: `검토 ${which}의 권고`,
      riskRationale: {
        riskLevel: "HIGH", policyVersion: "risk-policy-v1", reasonCodes: ["RULE_EXPLICIT_VIOLATION"],
        scoreDetail: {
          rule: { matched: true, ruleIds: [`RULE-${which}`], severity: "HIGH" },
          rag: { topRelevanceScore: null, evidenceCount: 0, evidenceSufficient: false, status: "SEARCH_UNAVAILABLE", failureCode: "RAG_SEARCH_UNAVAILABLE" },
          llm: { schemaVersion: "review-structured-output-v1", status: "NOT_RUN", decision: null, confidence: null },
          parser: { confidenceStatus: "READABLE" },
          final: { riskLevel: "HIGH", decisionRule: "RULE_EXPLICIT_VIOLATION" },
        },
      },
      evidences: [], suggestedPhrases: [],
    });
    if (url.includes("/items")) return response({ contents: [item], page: 1, size: 20, totalElements: 1, totalPages: 1 });
    if (url.includes("/annotations")) return response({
      reviewId: `REV-${which}`, fileId: `FILE-${which}`, fileType: "IMAGE", pageNo: 1, totalPages: 3,
      annotationPolicyVersion: "annotation-policy-v1",
      annotations: [{
        annotationId: `ANN-${which}`, reviewItemId: `ITEM-${which}`, reviewType: "MISLEADING_EXPRESSION",
        riskLevel: "HIGH", targetText: `검토 ${which}의 항목`, annotationDisplayMode: "LIST_ONLY",
        annotationStatus: "UNLOCATED", locationConfidence: 0, confidencePolicyVersion: "confidence-thresholds-v1",
        displayReason: "NO_MATCH", pageNo: 1, coordinate: null, textBlockId: null, textPath: null,
        rawStartOffset: null, rawEndOffset: null, normalizedStartOffset: null, normalizedEndOffset: null,
        matchedText: null,
      }],
    });
    if (url.includes("/suggestions")) return response([]);
    if (url.includes("/opinion-drafts")) return response([]);
    if (url.includes("/reports") && init?.method === "POST") return response({
      reportId: `RPT-${which}`, reviewId: `REV-${which}`, sourceReportId: null, reportType: "FULL",
      format: "PDF", reportStatus: "CREATED", snapshotHash: `sha256:${which}`, snapshotVersion: "v1",
      createdAt: "2026-07-14T12:30:00+09:00",
    });
    return response({});
  }));
  return { urls };
}

function SwitchHarness({ to }: { to: string }) {
  const navigate = useNavigate();
  return <button type="button" onClick={() => void navigate(to)}>검토 B로</button>;
}

function renderAt(path: string, switchTo: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App initialSession={session} />
      <SwitchHarness to={switchTo} />
    </MemoryRouter>,
  );
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

// 검토 A에서 만든 리포트가 검토 B의 결과로 보이면 다른 검토 기록을 현재 검토로 오인한다.
test("does not keep a report created in another review", async () => {
  stubTwoReviews();
  renderAt("/reviews/REV-A/support", "/reviews/REV-B/support");

  expect(await screen.findByRole("heading", { name: "검토 리포트" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "PDF 리포트 생성" }));
  expect(await screen.findByText(/리포트가 준비되었습니다/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  await waitFor(() => { expect(screen.queryByText(/리포트가 준비되었습니다/)).toBeNull(); });
  expect(screen.getByRole("heading", { name: "검토 리포트" })).toBeInTheDocument();
});

test("does not keep the selected item and filters of another review on the items tab", async () => {
  stubTwoReviews();
  renderAt("/reviews/REV-A/results/items", "/reviews/REV-B/results/items");

  expect(await screen.findByText("검토 A의 항목")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("적정 항목도 보기"));
  fireEvent.click(await screen.findByRole("button", { name: /검토 A의 항목/ }));
  // 목록 행도 사유를 표시하므로 상세 패널에만 있는 권고 문구로 선택을 확인한다.
  expect(await screen.findByText("검토 A의 권고")).toBeInTheDocument();
  expect(screen.getByLabelText("적정 항목도 보기")).toBeChecked();

  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  expect(await screen.findByText("검토 B의 항목")).toBeInTheDocument();
  expect(screen.getByLabelText("적정 항목도 보기")).not.toBeChecked();
  expect(screen.queryByText("검토 A의 권고")).toBeNull();
  expect(screen.getByText("검토 항목을 선택하면 판단 사유와 근거가 표시됩니다.")).toBeInTheDocument();
});

// 좌표 화면은 선택 항목이 남아도 다른 검토의 목록과 대조되지 않아 화면에 드러나지 않는다.
// 관찰 가능한 누출은 페이지 조건이므로 그것으로 고정한다.
// 경계가 remount하면 새 URL의 `reviewItemId`로 초기 선택이 다시 계산돼야 한다. 초기값을
// 잃으면 항목 링크로 진입한 검토가 아무것도 선택하지 않은 화면을 보여준다.
test("re-applies the reviewItemId query on the next review after remount", async () => {
  stubTwoReviews();
  renderAt(
    "/reviews/REV-A/results/items?reviewItemId=ITEM-A",
    "/reviews/REV-B/results/items?reviewItemId=ITEM-B",
  );

  // 검토 A는 URL이 지정한 항목이 선택된 채로 열린다.
  expect(await screen.findByText("검토 A의 권고")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  expect(await screen.findByText("검토 B의 권고")).toBeInTheDocument();
  expect(screen.queryByText("검토 A의 권고")).toBeNull();
  expect(screen.queryByText("검토 항목을 선택하면 판단 사유와 근거가 표시됩니다.")).toBeNull();
});

test("does not keep the page filter of another review on the annotations tab", async () => {
  // jsdom에는 objectURL이 없다. 좌표 미리보기가 이를 사용하므로 기존 테스트와 같이 대체한다.
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:annotation-preview") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const { urls } = stubTwoReviews();
  renderAt("/reviews/REV-A/results/annotations", "/reviews/REV-B/results/annotations");

  expect(await screen.findAllByRole("button", { name: /검토 A의 항목/ })).not.toHaveLength(0);
  fireEvent.change(screen.getByLabelText("페이지"), { target: { value: "3" } });
  await waitFor(() => { expect(urls.some((url) => url.includes("REV-A") && url.includes("pageNo=3"))).toBe(true); });

  fireEvent.click(screen.getByRole("button", { name: "검토 B로" }));
  expect(await screen.findAllByRole("button", { name: /검토 B의 항목/ })).not.toHaveLength(0);

  expect(screen.getByLabelText("페이지")).toHaveValue(1);
  const requestsForB = urls.filter((url) => url.includes("REV-B") && url.includes("/annotations"));
  expect(requestsForB).not.toHaveLength(0);
  for (const url of requestsForB) expect(url).not.toContain("pageNo=3");
});
