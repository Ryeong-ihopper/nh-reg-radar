import { Outlet, useParams } from "react-router-dom";

/**
 * 검토 단위 화면 경계.
 *
 * `/reviews/:reviewId/...` 경로는 `reviewId`만 바뀔 때 React Router가 같은 컴포넌트를
 * 재사용한다. 서버에서 받는 값은 `queryKey`에 `reviewId`가 들어가 자동으로 갱신되지만,
 * 화면 로컬 상태(입력 중 내용, 선택 항목, 검색 조건, 생성한 리포트, 활성 Q&A 세션)는
 * 그대로 남아 다른 검토의 내용이 보인다.
 *
 * 검토가 바뀌면 다른 검토의 화면이므로 하위 화면을 remount한다. 화면마다 상태를 하나씩
 * 초기화하는 방식과 달리, 새 검토 화면이나 새 상태를 추가할 때 초기화를 빠뜨릴 수 없다.
 * 이 경계를 우회하는 라우트가 생기지 않도록 `App.tsx`의 라우트 구성을
 * `review-scoped-routes.test.tsx`가 고정한다.
 */
export function ReviewScopedBoundary() {
  const { reviewId = "" } = useParams();
  return <Outlet key={reviewId} />;
}
