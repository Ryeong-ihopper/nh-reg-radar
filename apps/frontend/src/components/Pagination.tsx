interface PaginationProps {
  page: number;
  totalPages: number;
  totalElements: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, totalElements, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <nav className="pagination" aria-label="페이지 탐색">
      <button type="button" className="button-secondary" aria-label="이전 페이지" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>이전</button>
      <span><strong>{page}</strong> / {totalPages} 페이지 · 총 {totalElements}건</span>
      <button type="button" className="button-secondary" aria-label="다음 페이지" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>다음</button>
    </nav>
  );
}
