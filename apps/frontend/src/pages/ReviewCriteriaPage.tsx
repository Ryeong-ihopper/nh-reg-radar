import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { operationalRequest } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { ErrorState, LoadingState } from "../components/RequestState";
import { PageHeader } from "../components/PageHeader";
import { ReviewFlowGuide } from "../components/ReviewFlowGuide";

type WorkRow = {
  id: string; label: string; kind: string; scope: string; status: string; note: string;
  owner?: string; required_inputs?: string; source: { source_fields?: Record<string, unknown>; [key: string]: unknown };
  obligations?: Array<{ obligation_id: string; text: string; owners: Record<string, boolean> }>;
  obligation_logic?: unknown; review_program?: { kinds: string[]; evidence_policy?: { mode: string } };
};
type Worklist = { counts: { templates: number; supplement_32: number; additional_34: number }; rows: WorkRow[] };
const STATUS: Record<string, string> = { CURRENT_TEMPLATE: "현행 템플릿", RESIDUAL_CHECK: "잔여 검사 구조화", SHARED_WITH_RESIDUAL: "공유 검사 + 잔여", HUMAN_VISUAL: "사람 시각 검토", POLICY: "결합·허용 정책", SCOPE_HOLD: "지원 범위 보류", SOURCE_VERSION_HOLD: "판본 확인 보류" };
const FIELD: Record<string, string> = { label: "점검항목", example: "예시 · 완전일치 의무 아님", satisfied: "적정 기준 / 필수 여부", violated: "부적정 기준 / 기재요령", violation_guidance: "부적정 안내", review: "확인필요 기준", review_guidance: "확인필요 안내" };

export function ReviewCriteriaPage() {
  const { session } = useAuth();
  const [params] = useSearchParams();
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("ALL");
  const [selected, setSelected] = useState<string | null>(params.get("item"));
  const query = useQuery({ queryKey: ["review-worklist"], queryFn: () => operationalRequest<Worklist>(session?.accessToken ?? "", "review-worklist") });
  const rows = query.data?.rows.filter((row) => (kind === "ALL" || row.kind === kind) && `${row.id} ${row.label} ${row.scope} ${row.note}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  const row = rows.find((item) => item.id === selected) ?? rows[0];
  return <section>
    <PageHeader headingId="review-criteria-heading" eyebrow="심의 기준 검토" title="템플릿·보완 규정 구조화" description="원문을 확인하고, 공유할 검사와 추가할 검사를 구분하는 작업대장입니다." />
    <p><Link to="/advertisements/new">광고 등록</Link> · <Link to="/advertisements">광고 목록</Link></p>
    <ReviewFlowGuide />
    {query.isPending ? <LoadingState label="심의 기준을 불러오는 중입니다." /> : null}
    {query.error ? <ErrorState error={query.error} /> : null}
    {query.data ? <>
      <p className="panel-note">현행 템플릿 {query.data.counts.templates}개 · 보완 {query.data.counts.supplement_32}행 · 추가 {query.data.counts.additional_34}행. 보완·추가 행은 작업 대상으로 정리한 상태이며 자동 판정에 일괄 활성화되지 않습니다. 전체 템플릿의 의미 검증도 진행 중입니다.</p>
      <div className="criteria-filters"><label>구분<select value={kind} onChange={(event) => setKind(event.target.value)}><option value="ALL">전체</option><option value="TEMPLATE">현행 템플릿</option><option value="SUPPLEMENT_32">기존 보완 32행</option><option value="ADDITIONAL_34">추가 후보 34행</option></select></label><label>항목 찾기<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="상품·항목·ID" /></label></div>
      <div className="criteria-workbench">
        <nav aria-label="심의 기준 목록"><p>{rows.length}행</p>{rows.map((item) => <button type="button" key={item.id} aria-pressed={row?.id === item.id} onClick={() => setSelected(item.id)}><strong>{item.label}</strong><span>{item.scope} · {STATUS[item.status]}</span><small>{item.id}</small></button>)}</nav>
        {row ? <article className="criteria-detail"><h3>{row.label}</h3><p>{row.scope} · {STATUS[row.status]}</p><p>{row.note}</p>{row.owner ? <p><strong>담당:</strong> {row.owner}</p> : null}{row.required_inputs ? <p><strong>필요 입력:</strong> {row.required_inputs}</p> : null}
          <dl>{Object.entries(row.source.source_fields ?? row.source).filter(([key, value]) => value && !key.startsWith("_")).map(([key, value]) => <div key={key}><dt>{FIELD[key] ?? key}</dt><dd>{String(value)}</dd></div>)}</dl>
          {row.obligations ? <><h4>현행 검사와 담당</h4><ul>{row.obligations.map((check) => <li key={check.obligation_id}><strong>{check.obligation_id}</strong> {check.text}<small> · {Object.entries(check.owners).filter(([, enabled]) => enabled).map(([owner]) => ({ rule: "코드", llm: "LLM", human: "사람", external_input: "외부자료" })[owner] ?? owner).join(" + ")}</small></li>)}</ul><details><summary>종합식 보기</summary><pre>{JSON.stringify(row.obligation_logic, null, 2)}</pre></details></> : null}
        </article> : <p>조건에 맞는 항목이 없습니다.</p>}
      </div>
    </> : null}
  </section>;
}
