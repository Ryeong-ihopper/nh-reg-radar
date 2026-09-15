import type { ParserLayout } from "../api/operational";

export type RuleBasis = { item_id: string; source_type: "INTERNAL_TEMPLATE" | "REGULATION_V2"; source_ref: string; source_sha256: string | null; legal_basis_refs: string[]; basis_status: string };
export type ResultRow = { row_id?: string; item_id: string; title: string; question: string; criterion: string; template_example?: string; requirement_checks?: {status: string; finding_basis?: string}[]; verdict: string; reason: string; evidence: string; evidence_locations?: EvidenceBox[]; rule_basis?: RuleBasis | null };
export type HumanReviewDecision = { decision: "APPROVED" | "REJECTED"; comment: string | null; reviewer_id: string; decided_at: string; ai_result_unchanged: true };
export type ResultWorkspace = { available: boolean; source_type: string; rows: ResultRow[]; review_candidate_rows?: ResultRow[]; deferred_rules?: {item_id: string; reason: string; scope_id?: string; deferred_kind?: string}[]; output_failure_count?: number; output_failure_pairs?: {ad_id: string; scope_id?: string; product_id?: string; item_id: string; reason?: string}[]; partial_result_warning?: string | null; human_decision?: HumanReviewDecision | null };
export type EvidenceBox = { key: string; pageNo: number; bbox: number[]; width: number; height: number; precision?: "LINE" | "REGION"; asset_id?: string | null; source_page_no?: number };

export function resultEvidenceBoxes(row: ResultRow, layout?: ParserLayout): EvidenceBox[] {
  // An explicitly empty authoritative mapping must not fall back to matching
  // another product/asset's identical wording. Legacy saved workbooks only
  // retain the text-only path below.
  if (row.evidence_locations !== undefined) return row.evidence_locations;
  return evidenceBoxes(row.evidence, layout);
}

export function missingSourceLabel(row: ResultRow): string {
  if (row.evidence.trim()) return "원문은 연결됐으나 bbox 매핑 없음";
  if (row.verdict === "미해당") return "미해당 판정으로 원문 위치 불필요";
  if (row.requirement_checks?.some(check => check.status === "MISSING" && check.finding_basis === "ABSENCE"))
    return "미기재로 판정한 항목 — 특정 원문 위치 없음 (원본 대조 필요)";
  return "판정 응답에 원문 줄 참조 없음";
}

export function resultCounts(rows: ResultRow[]) {
  return {
    total: rows.length,
    violation: rows.filter((row) => row.verdict === "위반").length,
    unknown: rows.filter((row) => row.verdict === "판단불가").length,
    compliant: rows.filter((row) => row.verdict === "충족").length,
    notApplicable: rows.filter((row) => row.verdict === "미해당").length,
  };
}

function normalized(text: string): string {
  return text.normalize("NFKC").replace(/[^\p{L}\p{N}]/gu, "");
}

export function evidenceBoxes(evidence: string, layout?: ParserLayout): EvidenceBox[] {
  if (!layout || !evidence) return [];
  // Old workbook references are not coordinates in the current parser version.
  const fragments = evidence.replace(/\\n/g, "\n").replace(/\[[^\]]*\]/g, "")
    .split("\n").map(normalized).filter(text => text.length >= 8);
  const stream = fragments.join("");
  const boxes: EvidenceBox[] = [];
  for (const page of layout.pages) {
    if (page.canvas_w <= 0 || page.canvas_h <= 0) continue;
    for (const region of page.regions) {
      for (const [index, line] of region.lines.entries()) {
        const text = normalized(line.text);
        // Only actual parser boxes with literal normalized text matches; no guessed rectangle.
        if (text.length >= 8 && (stream.includes(text) || fragments.some(f => text.includes(f)))) {
          boxes.push({key: `${page.page_no}/${region.region_id}/${line.line_ref ?? index}`,
            pageNo: page.page_no, bbox: line.bbox, width: page.canvas_w, height: page.canvas_h});
        }
      }
    }
  }
  return boxes;
}
