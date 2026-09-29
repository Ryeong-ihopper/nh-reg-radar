import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { operationalRequest } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import {type ResultWorkspace, reviewItemTitle, reviewSourceCriterion} from "../components/operationalResultModel";
import { OperationalOriginalPanel } from "../components/OperationalOriginalPanel";
import { VerdictBadge } from "../components/OperationalReviewDetail";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";

export function OperationalSuggestionsPage() {
  const { reviewId = "" } = useParams();
  const [params] = useSearchParams();
  const { session } = useAuth();
  const token = session?.accessToken ?? "";
  const [selected, setSelected] = useState(params.get("item") ?? "");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const query = useQuery({queryKey: ["operational-workspace", reviewId], queryFn: () => operationalRequest<ResultWorkspace>(token, `reviews/${encodeURIComponent(reviewId)}/workspace`)});
  const rows = query.data?.rows.filter(row => ["위반", "판단불가"].includes(row.verdict)) ?? [];
  const row = rows.find(item => (item.row_id ?? item.item_id) === selected) ?? rows[0];
  const id = row?.row_id ?? row?.item_id ?? "";
  const draft = drafts[id] ?? "";
  async function copyDraft() {
    if (!draft.trim()) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(draft);
      else {
        input.current?.focus(); input.current?.select();
        if (!document.execCommand("copy")) throw new Error("copy unavailable");
      }
      setMessage("초안을 복사했습니다. 채택 또는 최종 승인을 의미하지 않습니다.");
    } catch { input.current?.focus(); input.current?.select(); setMessage("복사를 완료하지 못했습니다. 선택된 초안을 직접 복사해 주세요."); }
  }
  return <section className="suggestion-workspace-page" aria-labelledby="suggestion-heading">
    <PageHeader headingId="suggestion-heading" eyebrow="문구 수정 지원" title="추천 문구·수정 초안" description="광고 원문과 기준표를 참고해 확인하거나 수정할 문구를 정리합니다." actions={<Link className="button-link button-secondary" to={`/reviews/${encodeURIComponent(reviewId)}/results`}>심의 결과로 돌아가기</Link>} />
    <div className="feature-preparation-note"><strong>AI 자동 추천 연결 예정</strong><p>현재는 기준표 예시를 참고하는 초안 편집 화면입니다. 초안은 이 화면에서만 유지되며, 저장된 광고와 판정은 변경되지 않습니다. 페이지를 떠나기 전에 필요한 문구를 복사해 주세요.</p></div>
    {query.isPending ? <LoadingState label="수정 검토 항목을 불러오는 중입니다." /> : null}{query.error ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
    {query.data?.output_failure_count ? <p className="state-message" role="alert">판정 처리 실패 {query.data.output_failure_count}건은 문구 수정 대상과 별개로 재처리가 필요합니다.</p> : null}
    {query.data && !rows.length ? <p className="state-message">저장된 판정에 부적정·확인필요 항목이 없습니다.</p> : null}
    {row ? <><label className="suggestion-item-picker">수정·확인할 항목<select value={id} onChange={event => {setSelected(event.target.value); setMessage("");}}>{rows.map((item, index) => <option key={item.row_id ?? item.item_id} value={item.row_id ?? item.item_id}>{index + 1}. {reviewItemTitle(item)} · {item.verdict === "위반" ? "부적정" : "확인필요"}</option>)}</select></label>
      <div className="suggestion-workspace"><OperationalOriginalPanel reviewId={reviewId} token={token} row={row} /><article className="suggestion-draft-panel"><header><div><p className="eyebrow">선택 항목</p><h3>{reviewItemTitle(row)}</h3></div><VerdictBadge value={row.verdict} /></header>
        <div className="review-detail-section"><h4>{row.verdict === "위반" ? "수정 검토 이유" : "확인이 필요한 이유"}</h4><p>{row.reason}</p>{row.verdict === "판단불가" ? <p className="review-empty-note">확인필요 항목은 위반이 확정된 상태가 아닙니다. 원문 판독·적용 조건을 먼저 확인해 주세요.</p> : null}</div>
        <div className="review-detail-section"><h4>현재 광고 문구</h4>{row.evidence ? <blockquote className="review-source-quote">{row.evidence}</blockquote> : <p className="review-empty-note">연결된 광고 문구가 없습니다. 원문에서 확인해 주세요.</p>}</div>
        <div className="review-detail-section"><h4>기준표 조건</h4><p className="review-source-criterion">{reviewSourceCriterion(row) || "저장된 기준표 조건이 없습니다."}</p>
          {row.template_example ? <details className="suggestion-reference-example"><summary>기준표 참고 예시 보기</summary><p>{row.template_example}</p><small>예시는 표현과 의미를 참고하는 자료입니다. 상품의 수치·대상·예외를 그대로 복사하지 말고 확인해 주세요.</small><button type="button" className="button-secondary" onClick={() => {if (draft.trim() && !window.confirm("작성 중인 초안을 기준표 예시로 바꿀까요?")) return; setDrafts(values => ({...values, [id]: row.template_example ?? ""})); setMessage("기준표 예시를 가져왔습니다. 광고에 맞게 검토·수정해 주세요.");}}>예시를 초안에 가져오기</button></details> : null}
        </div>
        <div className="review-detail-section"><label className="suggestion-draft-label">수정 초안 <span>담당자 검토용</span><textarea ref={input} value={draft} onChange={event => {setDrafts(values => ({...values, [id]: event.target.value})); setMessage("");}} placeholder="원문과 기준표를 확인해 문구를 작성하세요. AI가 생성한 추천문구는 아직 제공되지 않습니다." rows={7} /></label><div className="form-actions"><button type="button" disabled={!draft.trim()} onClick={() => void copyDraft()}>초안 복사</button></div>{message ? <p role="status" className="suggestion-copy-status">{message}</p> : null}</div>
      </article></div></> : null}
  </section>;
}
