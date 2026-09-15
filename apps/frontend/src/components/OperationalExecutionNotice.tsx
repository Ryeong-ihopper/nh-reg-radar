import { useQuery } from "@tanstack/react-query";
import { operationalRequest } from "../api/operational";

type Execution = {
  total_seconds?: number;
  parse_seconds?: number;
  predicted_count?: number;
  deferred_count?: number;
  deferred_rules?: {item_id: string; reason: string; input_requirement?: string}[];
};
export function OperationalExecutionNotice({token, reviewId}: {token: string; reviewId: string}) {
  const execution = useQuery({
    queryKey: ["operational-execution", reviewId],
    queryFn: () => operationalRequest<Execution>(token, `reviews/${reviewId}/execution`),
    retry: false,
  });
  const data = execution.data;
  if (!data?.total_seconds) return null;
  return <div className="state-message state-warning">
    <strong>자동심의 완료 · {(data.total_seconds / 60).toFixed(1)}분</strong>
    <p>판정 {data.predicted_count}개 · 추가 확인 {data.deferred_count}개</p>
    {data.deferred_rules?.length ? <details><summary>사람 검토·추가 확인 항목 보기</summary><ul>{data.deferred_rules.map(r => <li key={r.item_id}>{r.item_id}: {r.reason.startsWith("시인성은 사람 검토") ? r.reason : r.input_requirement ?? (r.reason.includes("template") ? "선택 템플릿에 속하지 않거나 템플릿 미확정" : "외부자료·원문 확인 필요")}</li>)}</ul></details> : null}
  </div>;
}
