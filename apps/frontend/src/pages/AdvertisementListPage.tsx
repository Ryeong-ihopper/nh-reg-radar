import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { deleteLatestOperationalReview, operationalMode } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";

const CREATE_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"]);
const SYSTEM_ADMIN_ROLE = "SYSTEM_ADMIN";
const REVIEW_DELETE_ROLES = new Set(["COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"]);
const DELETABLE_REVIEW_STATUSES = new Set(["CHECK_REQUIRED", "REVIEW_COMPLETED", "REVIEW_FAILED"]);

export function AdvertisementListPage() {
  const { session } = useAuth();
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const selectAllRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const token = session?.accessToken ?? "";
  const canCreate = session?.user.roles.some((role) => CREATE_ROLES.has(role)) ?? false;
  const isSystemAdmin = session?.user.roles.includes(SYSTEM_ADMIN_ROLE) ?? false;
  const canDeleteReview = operationalMode && (session?.user.roles.some((role) => REVIEW_DELETE_ROLES.has(role)) ?? false);
  const query = useQuery({
    queryKey: ["advertisements", keyword, page],
    queryFn: () => api.listAdvertisements(token, { keyword, page, size: 20 }),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });
  const visibleIds = useMemo(
    () => query.data?.contents.map((item) => item.advertisementId) ?? [],
    [query.data],
  );
  const selectedVisibleCount = visibleIds.filter((id) => selectedIds.has(id)).length;
  const allVisibleSelected = visibleIds.length > 0 && selectedVisibleCount === visibleIds.length;

  useEffect(() => {
    setSelectedIds((current) => new Set([...current].filter((id) => visibleIds.includes(id))));
  }, [visibleIds]);

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedVisibleCount > 0 && !allVisibleSelected;
    }
  }, [allVisibleSelected, selectedVisibleCount]);

  useEffect(() => {
    if (query.data && page < query.data.totalPages) {
      void queryClient.prefetchQuery({
        queryKey: ["advertisements", keyword, page + 1],
        queryFn: () => api.listAdvertisements(token, { keyword, page: page + 1, size: 20 }),
        staleTime: 15_000,
      });
    }
  }, [keyword, page, query.data, queryClient, token]);

  const deleteSelected = useMutation({
    mutationFn: async (advertisementIds: string[]) => {
      const results = await Promise.allSettled(
        advertisementIds.map((advertisementId) => api.deleteAdvertisement(token, advertisementId)),
      );
      const failed = results.find((result) => result.status === "rejected");
      if (failed?.status === "rejected") throw failed.reason;
    },
    onSuccess: () => setSelectedIds(new Set()),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["advertisements"] }),
  });
  const deleteLatestReview = useMutation({
    mutationFn: (advertisementId: string) => deleteLatestOperationalReview(token, advertisementId),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["advertisements"] }),
  });

  function toggleAdvertisement(advertisementId: string, checked: boolean) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) next.add(advertisementId);
      else next.delete(advertisementId);
      return next;
    });
  }

  function toggleAllVisible(checked: boolean) {
    setSelectedIds((current) => checked
      ? new Set([...current, ...visibleIds])
      : new Set([...current].filter((id) => !visibleIds.includes(id))));
  }

  return (
    <section aria-labelledby="advertisement-list-heading">
      <PageHeader
        headingId="advertisement-list-heading"
        eyebrow="광고 심의 업무"
        title="광고물 목록"
        description="등록된 광고물의 검토 상태를 확인하거나 새로운 광고 심의를 시작합니다."
        actions={canCreate ? <Link className="button-link" to="/advertisements/new">광고물 등록</Link> : null}
      />
      <form className="search-bar" onSubmit={(event) => { event.preventDefault(); setPage(1); setKeyword(keywordInput.trim()); }}>
        <label htmlFor="keyword">광고명</label>
        <input id="keyword" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} />
        <button type="submit">조회</button>
        <button type="button" className="button-secondary" onClick={() => { setKeywordInput(""); setKeyword(""); setPage(1); }}>초기화</button>
      </form>

      {query.isPending ? <LoadingState label="광고물 목록을 불러오는 중입니다." /> : null}
      {query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data?.contents.length === 0 ? <p className="state-message">등록된 광고물이 없습니다.</p> : null}
      {query.data && query.data.contents.length > 0 ? (
        <>
          {isSystemAdmin ? <div className="bulk-action-bar" aria-live="polite">
            <span><strong>{selectedVisibleCount}건</strong> 선택됨</span>
            <button
              type="button"
              className="button-danger"
              disabled={selectedVisibleCount === 0 || deleteSelected.isPending}
              onClick={() => {
                if (window.confirm(`선택한 광고물 ${selectedVisibleCount}건과 연결된 검토 결과를 목록에서 삭제합니다. 계속하시겠습니까?`)) {
                  deleteSelected.mutate(visibleIds.filter((id) => selectedIds.has(id)));
                }
              }}
            >
              {deleteSelected.isPending ? "삭제 중..." : "선택 항목 삭제"}
            </button>
          </div> : null}
          {deleteSelected.isError ? <ErrorState error={deleteSelected.error} onRetry={() => deleteSelected.mutate(visibleIds.filter((id) => selectedIds.has(id)))} /> : null}
          {deleteLatestReview.isError ? <ErrorState error={deleteLatestReview.error} /> : null}
          <div className="table-scroll">
          <table className="advertisement-table">
            <thead><tr>{isSystemAdmin ? <th className="selection-column"><input ref={selectAllRef} type="checkbox" aria-label="현재 페이지 전체 선택" checked={allVisibleSelected} onChange={(event) => toggleAllVisible(event.target.checked)} /></th> : null}<th>광고물</th><th>상품군</th><th>형식·매체</th><th>등록자</th><th>등록일시</th><th>검토 상태</th><th><span className="visually-hidden">상세</span></th></tr></thead>
            <tbody>{query.data.contents.map((item) => (
              <tr key={item.advertisementId}>
                {isSystemAdmin ? <td className="selection-column"><input type="checkbox" aria-label={`${item.advertisementName} 선택`} checked={selectedIds.has(item.advertisementId)} onChange={(event) => toggleAdvertisement(item.advertisementId, event.target.checked)} /></td> : null}
                <td><div className="table-primary"><strong>{item.advertisementName}</strong></div></td>
                <td>{productGroupLabel(item.productGroup)}</td><td>{advertisementTypeLabel(item.advertisementType)}</td>
                <td>{item.registeredBy}</td><td>{new Date(item.registeredAt).toLocaleString("ko-KR")}</td>
                <td><StatusBadge status={item.reviewStatus} /></td>
                <td><div className="advertisement-row-actions"><Link className="table-row-link" to={`/advertisements/${encodeURIComponent(item.advertisementId)}`}>상세 보기</Link>{canDeleteReview && DELETABLE_REVIEW_STATUSES.has(item.reviewStatus) ? <button type="button" className="table-row-link table-row-delete" disabled={deleteLatestReview.isPending} onClick={() => {
                  if (window.confirm("이 광고의 최신 심의 결과를 삭제하시겠습니까? 삭제 후 되돌릴 수 없습니다.")) deleteLatestReview.mutate(item.advertisementId);
                }}>{deleteLatestReview.isPending ? "삭제 중..." : "심의 결과 삭제"}</button> : null}</div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        </>
      ) : null}
      {query.data ? <Pagination page={query.data.page} totalPages={query.data.totalPages} totalElements={query.data.totalElements} onPageChange={setPage} /> : null}
    </section>
  );
}
