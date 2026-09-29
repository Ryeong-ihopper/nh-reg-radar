import { Link } from "react-router-dom";
import { legalBasisEntries, missingSourceLabel, reviewVerdict, reviewItemTitle, reviewSourceCriterion, type ResultRow } from "./operationalResultModel";
import { LegalBasisLinks } from "./LegalBasisLinks";

export function VerdictBadge({ value }: { value: string }) {
  return <span className="regulation-verdict" data-verdict={value}>{reviewVerdict(value)}</span>;
}

export function OperationalReviewDetail({ row, reviewId, onLocate, showSuggestionLink = true }: {
  row: ResultRow; reviewId: string; onLocate: () => void; showSuggestionLink?: boolean;
}) {
  const guidance = row.verdict === "위반" ? row.template_violation_guidance : row.template_review_guidance;
  const criteria = reviewSourceCriterion(row);
  const checks = row.display_checks ?? [];
  return <article className="review-selected-detail" aria-label={`선택 항목 상세 ${row.title}`}>
    <header className="review-detail-heading"><div><p className="eyebrow">선택 항목 상세</p><h3>{reviewItemTitle(row)}</h3>{row.source_product ? <small className="review-product-context">{row.source_product}</small> : null}</div><VerdictBadge value={row.verdict} /></header>
    <div className="review-detail-section review-decision-reason"><h4>{row.verdict === "판단불가" ? "확인이 필요한 이유" : "판정 사유"}</h4><p>{row.reason || "저장된 판정 사유가 없습니다."}</p></div>
    <div className="review-detail-section"><div className="review-section-heading"><h4>광고물 내 문구</h4><button type="button" className="button-secondary" onClick={onLocate}>원문 위치 보기 ↗</button></div>
      {row.evidence?.trim() ? <blockquote className="review-source-quote">{row.evidence}</blockquote> : <p className="review-empty-note">{missingSourceLabel(row).replace(/bbox/g, "위치")}</p>}
    </div>
    <div className="review-detail-section"><h4>기준표 조건 대조</h4>
      {criteria ? <p className="review-source-criterion">{criteria}</p> : <p className="review-empty-note">이 결과에 저장된 기준표 조건이 없습니다.</p>}
      {checks.length ? <ul className="review-condition-list">{checks.map((check, index) => <li key={index} data-check-status={check.status}>
        <span aria-hidden="true">{check.status === "SATISFIED" ? "✓" : ["VIOLATED", "MISSING"].includes(check.status) ? "×" : "?"}</span>
        <div><strong>{check.text}</strong><small>{({SATISFIED: "충족", VIOLATED: "불충족", MISSING: "미기재", UNDETERMINED: "확인필요", UNRECORDED: "점검 기록 없음"} as Record<string,string>)[check.status] ?? "확인필요"}{check.reason ? ` · ${check.reason}` : ""}</small></div>
      </li>)}</ul> : null}
      {row.judgment_scope === "TEXT_ONLY" ? <p className="review-empty-note">문구의 내용에 대한 판정입니다. 배치·로고·줄 구조는 추가 확인이 남아 있습니다.</p> : null}
    </div>
    {guidance ? <div className="review-detail-section"><h4>담당자 안내문구 · 기준표</h4><p className="review-guidance">{guidance}</p></div> : null}
    <div className="review-detail-section"><h4>연결된 근거 법령·규정</h4><LegalBasisLinks entries={legalBasisEntries(row.rule_basis?.legal_basis_refs ?? [])} /></div>
    {showSuggestionLink && ["위반", "판단불가"].includes(row.verdict) ? <Link className="button-link review-suggestion-link" to={`/reviews/${encodeURIComponent(reviewId)}/suggestions?item=${encodeURIComponent(row.row_id ?? row.item_id)}`}>추천 문구·수정 초안 보기 →</Link> : null}
    <details className="review-technical-details"><summary>추출·검토 상세 정보</summary>
      <p>{row.evidence_locations?.length ? `저장된 원문 인용 위치 ${row.evidence_locations.length}곳이 연결되어 있습니다.` : missingSourceLabel(row).replace(/bbox/g, "위치")}</p>
      {row.template_section ? <p>적용 기준표: {row.template_section}</p> : null}
      {row.criterion && row.criterion !== criteria ? <details><summary>저장된 실행 조건</summary><p>{row.criterion}</p></details> : null}
      {row.template_example ? <><h4>기준표 참고 예시</h4><p>{row.template_example}</p><small>같은 의미의 표현을 사용할 수 있으며, 예시와 완전히 같아야 한다는 뜻은 아닙니다.</small></> : null}
      {row.model_assessment ? <><h4>확정에 사용하지 않은 AI 관찰</h4><p>{reviewVerdict(row.model_assessment.verdict)} · {row.model_assessment.reason}</p><small>원문 판독 또는 근거 연결 검사에서 보류됐으며 위 판정으로 채택되지 않았습니다.</small></> : null}
    </details>
  </article>;
}
