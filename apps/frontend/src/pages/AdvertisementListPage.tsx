import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";

const CREATE_ROLES = new Set(["PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"]);

export function AdvertisementListPage() {
  const { session } = useAuth();
  const [keywordInput, setKeywordInput] = useState("");
  const [keyword, setKeyword] = useState("");
  const token = session?.accessToken ?? "";
  const canCreate = session?.user.roles.some((role) => CREATE_ROLES.has(role)) ?? false;
  const query = useQuery({
    queryKey: ["advertisements", keyword],
    queryFn: () => api.listAdvertisements(token, { keyword, page: 1, size: 20 }),
  });

  return (
    <section aria-labelledby="advertisement-list-heading">
      <div className="page-heading">
        <div><p className="eyebrow">S-002</p><h2 id="advertisement-list-heading">광고물 목록</h2></div>
        {canCreate ? <Link className="button-link" to="/advertisements/new">광고물 등록</Link> : null}
      </div>
      <form className="search-bar" onSubmit={(event) => { event.preventDefault(); setKeyword(keywordInput.trim()); }}>
        <label htmlFor="keyword">광고명</label>
        <input id="keyword" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} />
        <button type="submit">조회</button>
        <button type="button" className="button-secondary" onClick={() => { setKeywordInput(""); setKeyword(""); }}>초기화</button>
      </form>

      {query.isPending ? <LoadingState label="광고물 목록을 불러오는 중입니다." /> : null}
      {query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data?.contents.length === 0 ? <p className="state-message">등록된 광고물이 없습니다.</p> : null}
      {query.data && query.data.contents.length > 0 ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>광고물 ID</th><th>광고명</th><th>상품군</th><th>광고유형</th><th>담당부서</th><th>등록자</th><th>등록일시</th><th>검토 상태</th></tr></thead>
            <tbody>{query.data.contents.map((item) => (
              <tr key={item.advertisementId}>
                <td><Link to={`/advertisements/${encodeURIComponent(item.advertisementId)}`}>{item.advertisementId}</Link></td>
                <td>{item.advertisementName}</td><td>{item.productGroup}</td><td>{item.advertisementType}</td>
                <td>{item.departmentId}</td><td>{item.registeredBy}</td><td>{new Date(item.registeredAt).toLocaleString("ko-KR")}</td>
                <td>{item.reviewStatus}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
