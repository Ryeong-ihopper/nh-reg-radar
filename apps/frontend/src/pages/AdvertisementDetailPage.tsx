import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { FileActions } from "../components/FileActions";

export function AdvertisementDetailPage() {
  const { advertisementId = "" } = useParams();
  const { session } = useAuth();
  const query = useQuery({
    queryKey: ["advertisement", advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", advertisementId),
    enabled: Boolean(advertisementId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 403) && count < 1,
  });

  return (
    <section aria-labelledby="advertisement-detail-heading">
      <p className="eyebrow">광고물 상세</p>
      <h2 id="advertisement-detail-heading">광고물 상세 조회</h2>
      {query.isPending ? <LoadingState label="광고물 상세를 불러오는 중입니다." /> : null}
      {query.isError && query.error instanceof ApiError && query.error.status === 403 ? (
        <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>소속 부서와 광고물 접근 범위를 확인해 주세요.</p></div>
      ) : null}
      {query.isError && (!(query.error instanceof ApiError) || query.error.status !== 403) ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data ? (
        <div className="detail-grid">
          <dl>
            <div><dt>광고물 ID</dt><dd>{query.data.advertisementId}</dd></div>
            <div><dt>광고명</dt><dd>{query.data.advertisementName}</dd></div>
            <div><dt>상품군</dt><dd>{query.data.productGroup}</dd></div>
            <div><dt>광고유형</dt><dd>{query.data.advertisementType}</dd></div>
            <div><dt>담당부서</dt><dd>{query.data.departmentId}</dd></div>
            <div><dt>검토 상태</dt><dd>{query.data.reviewStatus}</dd></div>
          </dl>
          <div><h3>등록 파일</h3>{query.data.files.length === 0 ? <p>등록된 파일이 없습니다.</p> : <ul className="file-list">{query.data.files.map((file) => <li key={file.fileId}><FileActions accessToken={session?.accessToken ?? ""} file={file} /></li>)}</ul>}</div>
        </div>
      ) : null}
      <Link to="/advertisements">목록으로</Link>
    </section>
  );
}
