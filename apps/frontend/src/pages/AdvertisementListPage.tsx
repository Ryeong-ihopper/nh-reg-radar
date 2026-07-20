import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";

const CREATE_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"]);

export function AdvertisementListPage() {
  const { session } = useAuth();
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const token = session?.accessToken ?? "";
  const canCreate = session?.user.roles.some((role) => CREATE_ROLES.has(role)) ?? false;
  const query = useQuery({
    queryKey: ["advertisements", keyword, page],
    queryFn: () => api.listAdvertisements(token, { keyword, page, size: 20 }),
  });

  return (
    <section aria-labelledby="advertisement-list-heading">
      <WorkflowSteps current={1} />
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
        <div className="table-scroll">
          <table className="advertisement-table">
            <thead><tr><th>광고물</th><th>상품군</th><th>광고유형</th><th>등록자</th><th>등록일시</th><th>검토 상태</th><th><span className="visually-hidden">상세</span></th></tr></thead>
            <tbody>{query.data.contents.map((item) => (
              <tr key={item.advertisementId}>
                <td><div className="table-primary"><strong>{item.advertisementName}</strong></div></td>
                <td>{productGroupLabel(item.productGroup)}</td><td>{advertisementTypeLabel(item.advertisementType)}</td>
                <td>{item.registeredBy}</td><td>{new Date(item.registeredAt).toLocaleString("ko-KR")}</td>
                <td><StatusBadge status={item.reviewStatus} /></td>
                <td><Link className="table-row-link" to={`/advertisements/${encodeURIComponent(item.advertisementId)}`}>상세 보기</Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
      {query.data ? <Pagination page={query.data.page} totalPages={query.data.totalPages} totalElements={query.data.totalElements} onPageChange={setPage} /> : null}
    </section>
  );
}
