import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { operationalRequest } from "../api/operational";
import { useAuth } from "../auth/useAuth";
import { LegalBasisLinks } from "../components/LegalBasisLinks";
import { mappedLegalReferences, type MappedCriterion } from "../components/mappedLegalReferences";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, LoadingState } from "../components/RequestState";

export function LegalReferencePage() {
  const { session } = useAuth();
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("ALL");
  const [selected, setSelected] = useState("");
  const query = useQuery({queryKey: ["review-worklist"], queryFn: () => operationalRequest<{rows: MappedCriterion[]}>(session?.accessToken ?? "", "review-worklist")});
  const references = useMemo(() => mappedLegalReferences(query.data?.rows ?? []), [query.data]);
  const scopes = [...new Set(references.flatMap(reference => reference.items.map(item => item.scope)))].sort();
  const term = search.trim().toLocaleLowerCase();
  const visible = references.filter(reference => (scope === "ALL" || reference.items.some(item => item.scope === scope)) && `${reference.label} ${reference.items.map(item => `${item.label} ${item.scope}`).join(" ")}`.toLocaleLowerCase().includes(term));
  const active = visible.find(reference => reference.key === selected) ?? visible[0];
  return <section className="legal-reference-page" aria-labelledby="legal-reference-heading">
    <PageHeader headingId="legal-reference-heading" eyebrow="심의 참고자료" title="법령·규정 검색" description="현재 템플릿에 연결된 근거를 찾아보고, 해당 심의 기준과 공식 법령 검색으로 이동합니다." />
    <div className="feature-preparation-note"><strong>템플릿에 매핑된 근거 검색</strong><p>현재 연결된 자료 범위에서 검색합니다. 법령 전체의 조문 검색과 개정 이력 연동은 준비 중입니다. 과거 심의에 사용된 근거는 해당 결과 화면에서 확인해 주세요.</p></div>
    <div className="legal-search-tools"><label>법령·규정 또는 점검항목<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="예: 광고, 금융소비자보호, 예금자보호" /></label><label>적용 템플릿<select value={scope} onChange={event => setScope(event.target.value)}><option value="ALL">전체 템플릿</option>{scopes.map(value => <option key={value} value={value}>{value}</option>)}</select></label></div>
    {query.isPending ? <LoadingState label="연결된 법령·규정을 불러오는 중입니다." /> : null}
    {query.error ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
    {query.data ? <div className="legal-reference-workspace"><div className="legal-reference-list"><header><h3>연결된 근거 <small>{visible.length}건</small></h3></header><nav aria-label="법령·규정 검색 결과">{visible.map(reference => <button type="button" key={reference.key} aria-pressed={reference.key === active?.key} onClick={() => setSelected(reference.key)}><strong>{reference.label}</strong><span>{reference.items.length}개 점검항목에 연결</span></button>)}</nav>{!visible.length ? <p className="state-message">검색 조건에 맞는 연결 근거가 없습니다.</p> : null}</div>
      {active ? <article className="legal-reference-detail"><p className="eyebrow">연결 근거 상세</p><h3>{active.label}</h3><LegalBasisLinks entries={[active]} /><p className="panel-note">외부 링크는 공식 사이트에서 법령명으로 검색합니다. 심의 당시의 특정 판본·조문을 확정하는 링크는 아닙니다.</p><h4>이 근거를 사용하는 점검항목</h4><ul className="linked-criteria-list">{active.items.map(item => <li key={item.id}><div><strong>{item.label}</strong><small>{item.scope}</small></div><Link to={`/review-criteria?item=${encodeURIComponent(item.id)}`}>기준표 보기 →</Link></li>)}</ul></article> : null}</div> : null}
  </section>;
}
