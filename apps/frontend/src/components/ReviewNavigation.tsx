import { NavLink } from "react-router-dom";

export function ReviewNavigation({ reviewId }: { reviewId: string }) {
  const id = encodeURIComponent(reviewId);
  return (
    <nav className="review-navigation" aria-label="검토 결과 메뉴">
      <NavLink end to={`/reviews/${id}/results`}>결과 요약</NavLink>
      <NavLink to={`/reviews/${id}/results/items`}>항목별 검토</NavLink>
      <NavLink to={`/reviews/${id}/results/annotations`}>광고 화면</NavLink>
      <NavLink to={`/reviews/${id}/support`}>담당자 지원</NavLink>
    </nav>
  );
}
