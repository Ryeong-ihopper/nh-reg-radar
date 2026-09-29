import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";
import { StatusBadge } from "../components/StatusBadge";
import { productGroupLabel } from "../components/displayLabels";

export function OperationalReviewHubPage({ suggestions = false }: {suggestions?: boolean}) {
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const ads = useQuery({queryKey: ["advertisements", "review-hub", keyword, page], queryFn: () => api.listAdvertisements(token, {keyword: keyword.trim() || undefined, page, size: 10})});
  const active = ads.data?.contents.find(ad => ad.advertisementId === selected) ?? ads.data?.contents[0];
  const adId = active?.advertisementId ?? "";
  const history = useQuery({queryKey: ["advertisement-reviews", adId], queryFn: () => api.listAdvertisementReviews(token, adId), enabled: Boolean(adId)});
  const title = suggestions ? "추천 문구·수정 초안" : "심의 결과";
  return <section className="review-hub-page" aria-labelledby="review-hub-heading">
    <PageHeader headingId="review-hub-heading" eyebrow="광고 심의" title={title} description={suggestions ? "광고와 심의 회차를 선택해 확인·수정할 문구를 살펴보세요." : "광고별 심의 이력을 선택해 항목별 판정과 원문을 확인하세요."} actions={<Link className="button-link" to="/advertisements/new">새 광고 등록</Link>} />
    {suggestions ? <div className="feature-preparation-note"><strong>수정 초안 작업 공간</strong><p>원문·기준표 예시를 참고해 초안을 작성하고 복사할 수 있습니다. AI 자동 추천 생성과 채택 이력 저장은 아직 연결되지 않았습니다.</p></div> : null}
    <label className="review-hub-search">광고 찾기<input type="search" placeholder="광고명으로 검색" value={keyword} onChange={event => {setKeyword(event.target.value); setPage(1);}} /></label>
    {ads.isPending ? <LoadingState label="광고 목록을 불러오는 중입니다." /> : null}{ads.error ? <ErrorState error={ads.error} onRetry={() => void ads.refetch()} /> : null}
    {ads.data ? <div className="review-hub-workspace"><div className="review-hub-ads"><header><h3>등록 광고 <small>{ads.data.totalElements}건</small></h3></header><nav aria-label="심의 대상 광고">{ads.data.contents.map(ad => <button type="button" key={ad.advertisementId} aria-pressed={ad.advertisementId === adId} onClick={() => setSelected(ad.advertisementId)}><strong>{ad.advertisementName}</strong><span>{productGroupLabel(ad.productGroup)} · {new Date(ad.registeredAt).toLocaleDateString("ko-KR")}</span><StatusBadge status={ad.reviewStatus} /></button>)}</nav>{!ads.data.contents.length ? <p className="state-message">등록된 광고가 없습니다.</p> : null}<div className="review-hub-pagination"><button type="button" className="button-secondary" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>이전</button><span>{page} / {Math.max(1, ads.data.totalPages)}</span><button type="button" className="button-secondary" disabled={page >= ads.data.totalPages} onClick={() => setPage(value => value + 1)}>다음</button></div></div>
      <article className="review-hub-history"><header><p className="eyebrow">심의 이력</p><h3>{active?.advertisementName ?? "광고를 선택해 주세요"}</h3>{active ? <Link to={`/advertisements/${encodeURIComponent(adId)}`}>광고 원본·등록 정보 →</Link> : null}</header>{adId && history.isPending ? <LoadingState label="심의 이력을 불러오는 중입니다." /> : null}{history.error ? <ErrorState error={history.error} onRetry={() => void history.refetch()} /> : null}
        {history.data?.length === 0 ? <p className="state-message">아직 요청된 심의가 없습니다.</p> : null}<ol className="review-hub-rounds">{history.data?.map(review => {
          const completed = ["CHECK_REQUIRED", "REVIEW_COMPLETED"].includes(review.reviewStatus);
          const suffix = completed ? suggestions ? "suggestions" : "results" : "status";
          return <li key={review.reviewId}><div><strong>{review.reviewRound}차 심의</strong><StatusBadge status={review.reviewStatus} /><small>{new Date(review.requestedAt).toLocaleString("ko-KR")}</small></div><Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(review.reviewId)}/${suffix}`}>{completed ? suggestions ? "수정 초안 보기" : "결과 확인" : "진행 기록 보기"}</Link></li>;
        })}</ol>
      </article></div> : null}
  </section>;
}
