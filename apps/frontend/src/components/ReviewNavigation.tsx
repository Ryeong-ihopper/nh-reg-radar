import { NavLink } from "react-router-dom";
import { operationalMode } from "../api/operational";

export function ReviewNavigation({ reviewId }: { reviewId: string }) {
  if (operationalMode) return null;
  const id = encodeURIComponent(reviewId);
  return (
    <nav className="review-navigation" aria-label="검토 결과 메뉴">
      <NavLink end to={`/reviews/${id}/results`}>결과 요약</NavLink>
      <NavLink to={`/reviews/${id}/results/items`}>항목별 검토</NavLink>
      <NavLink to={`/reviews/${id}/results/annotations`}>광고 화면</NavLink>
      {!operationalMode ? <NavLink to={`/reviews/${id}/results/qa`}>광고 규정 Q&A</NavLink> : null}
      {!operationalMode ? <NavLink to={`/reviews/${id}/support`}>검토 및 리포트</NavLink> : null}
    </nav>
  );
}
