import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, type ReviewRequestInput, type ReviewType } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { PageHeader } from "../components/PageHeader";
import { ReviewOriginalPanel } from "../components/ReviewOriginalPanel";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { advertisementTypeLabel, productGroupLabel } from "../components/displayLabels";

const REVIEW_TYPES: ReadonlyArray<{ value: ReviewType; label: string }> = [
  { value: "REQUIRED_PHRASE", label: "필수 문구 누락" },
  { value: "INTEREST_RATE", label: "금리·수익률·조건 표시" },
  { value: "MISLEADING_EXPRESSION", label: "과장·오인 표현" },
  { value: "PRODUCT_CONSISTENCY", label: "상품설명서·약관 정합성" },
  { value: "VISIBILITY", label: "위치·크기·강조·시인성" },
];

function localDateInputValue(now = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function ReviewRequestPage() {
  const { advertisementId = "" } = useParams();
  const { session } = useAuth();
  const navigate = useNavigate();
  const [reviewTypes, setReviewTypes] = useState<ReviewType[]>(REVIEW_TYPES.map(({ value }) => value));
  const [standardEffectiveDate, setStandardEffectiveDate] = useState(() => localDateInputValue());
  const [includeSuggestion, setIncludeSuggestion] = useState(true);
  const [includeOpinionDraft, setIncludeOpinionDraft] = useState(false);
  const [requestMemo, setRequestMemo] = useState("");
  const [validationError, setValidationError] = useState("");

  const advertisement = useQuery({
    queryKey: ["advertisement", advertisementId],
    queryFn: () => api.getAdvertisement(session?.accessToken ?? "", advertisementId),
    enabled: Boolean(advertisementId),
    retry: false,
  });
  const requestReview = useMutation({
    mutationFn: (input: ReviewRequestInput) => api.requestAdvertisementReview(
      session?.accessToken ?? "",
      advertisementId,
      input,
    ),
    onSuccess: ({ reviewId }) => navigate(`/reviews/${encodeURIComponent(reviewId)}/status`),
  });

  function toggleReviewType(value: ReviewType) {
    setReviewTypes((current) => current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (reviewTypes.length === 0) {
      setValidationError("검토 항목을 하나 이상 선택해 주세요.");
      return;
    }
    setValidationError("");
    requestReview.mutate({
      standardEffectiveDate: standardEffectiveDate || null,
      reviewTypes,
      includeSuggestion,
      includeOpinionDraft,
      requestMemo: requestMemo.trim() || null,
    });
  }

  return (
    <section aria-labelledby="review-request-heading">
      <WorkflowSteps current={3} advertisementId={advertisementId} />
      <PageHeader
        headingId="review-request-heading"
        eyebrow="3단계 · AI 검토"
        title="검토 항목과 기준 선택"
        description="광고 원본을 보면서 적용할 검토 범위와 기준일을 확인한 뒤 분석을 요청합니다."
      />
      {advertisement.isPending ? <LoadingState label="광고물 정보를 불러오는 중입니다." /> : null}
      {advertisement.isError && advertisement.error instanceof ApiError && advertisement.error.status === 403 ? (
        <div role="alert" className="state-message state-error"><strong>접근 권한이 없습니다.</strong><p>소속 부서와 광고물 접근 범위를 확인해 주세요.</p></div>
      ) : null}
      {advertisement.isError && (!(advertisement.error instanceof ApiError) || advertisement.error.status !== 403) ? (
        <ErrorState error={advertisement.error} onRetry={() => void advertisement.refetch()} />
      ) : null}
      {advertisement.data ? (
        <div className="review-workspace">
          <div>
          <dl className="review-summary" aria-label="검토 대상 광고 정보">
            <div><dt>광고명</dt><dd>{advertisement.data.advertisementName}</dd></div>
            <div><dt>상품군</dt><dd>{productGroupLabel(advertisement.data.productGroup)}</dd></div>
            <div><dt>광고유형</dt><dd>{advertisementTypeLabel(advertisement.data.advertisementType)}</dd></div>
          </dl>
          <form className="review-form review-request-form" onSubmit={submit}>
            <fieldset>
              <legend><span>01</span> 검토 범위</legend>
              <p className="fieldset-description">자동 검토할 항목을 하나 이상 선택하세요.</p>
              <div className="checkbox-grid">{REVIEW_TYPES.map(({ value, label }) => (
                <label key={value}><input type="checkbox" checked={reviewTypes.includes(value)} onChange={() => toggleReviewType(value)} />{label}</label>
              ))}</div>
            </fieldset>
            <div className="review-options"><label>기준 적용일<input type="date" value={standardEffectiveDate} onChange={(event) => setStandardEffectiveDate(event.target.value)} /></label><p>선택한 날짜에 유효한 규정과 가이드라인을 기준으로 검토합니다.</p></div>
            <label>요청 메모<textarea value={requestMemo} onChange={(event) => setRequestMemo(event.target.value)} maxLength={1000} placeholder="중점적으로 확인할 상품 조건이나 표현을 입력해 주세요." /></label>
            <div className="review-output-options" aria-label="추가 산출물"><strong>추가 산출물</strong><label className="inline-check"><input type="checkbox" checked={includeSuggestion} onChange={(event) => setIncludeSuggestion(event.target.checked)} />문구 추천 포함</label><label className="inline-check"><input type="checkbox" checked={includeOpinionDraft} onChange={(event) => setIncludeOpinionDraft(event.target.checked)} />심의 의견 초안 포함</label></div>
            {validationError ? <p role="alert" className="field-error">{validationError}</p> : null}
            {requestReview.isError ? <ErrorState error={requestReview.error} /> : null}
            <div className="form-actions">
              <Link className="button-link button-secondary" to={`/advertisements/${encodeURIComponent(advertisementId)}`}>이전</Link>
              <button type="submit" disabled={requestReview.isPending}>{requestReview.isPending ? "검토를 요청하는 중..." : "AI 검토 시작"}</button>
            </div>
          </form>
          </div>
          <ReviewOriginalPanel accessToken={session?.accessToken ?? ""} advertisement={advertisement.data} />
        </div>
      ) : null}
    </section>
  );
}
