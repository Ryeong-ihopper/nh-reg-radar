import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "vitest";

const APP_SOURCE = readFileSync(resolve(process.cwd(), "src/App.tsx"), "utf8");

/**
 * 검토 화면이 경계를 우회하면 그 화면만 조용히 이전 검토의 상태를 이어받는다. 실제로 그런
 * 결함이 화면별로 반복됐으므로(#35, #37) 라우트 구성 자체를 고정한다.
 *
 * 동작은 `review-scoped-boundary.test.tsx`와 `compliance-qa-review-switch.test.tsx`가
 * 검증한다. 이 파일은 새 검토 화면을 경계 밖에 두는 실수만 막는다.
 */
test("declares every review route under the review-scoped boundary", () => {
  const boundaryRoute = /<Route path="\/reviews\/:reviewId" element=\{<ReviewScopedBoundary \/>\}>([\s\S]*?)<\/Route>/.exec(APP_SOURCE);
  expect(boundaryRoute).not.toBeNull();

  const children = [...boundaryRoute![1].matchAll(/<Route path="([^"]+)"/g)].map((match) => match[1]);
  expect(children).toEqual(["status", "results", "results/items", "results/annotations", "results/qa", "support", "suggestions"]);
  // 하위 경로는 상대 경로여야 경계 아래에 놓인다.
  for (const child of children) expect(child.startsWith("/")).toBe(false);
});

test("declares no review route outside the boundary", () => {
  const absoluteReviewRoutes = [...APP_SOURCE.matchAll(/<Route path="(\/reviews\/[^"]*)"[^>]*element=\{<(\w+)/g)]
    .filter((match) => match[2] !== "ReviewScopedBoundary")
    .map((match) => `${match[1]} → ${match[2]}`);

  expect(absoluteReviewRoutes).toEqual([]);
});
