import type { ParserLayout } from "../api/operational";
import type { ExtractionStatus } from "./ExtractionStatusPanel";

export function reviewVerdict(value: string): string {
  return ({위반: "부적정", 판단불가: "확인필요", 충족: "적정", 미해당: "해당없음",
    VIOLATION: "부적정", UNDETERMINED: "확인필요", COMPLIANT: "적정", NOT_APPLICABLE: "해당없음"} as Record<string, string>)[value] ?? value;
}

export type RuleBasis = { item_id: string; source_type: "INTERNAL_TEMPLATE" | "REGULATION_V2"; source_ref: string; source_sha256: string | null; legal_basis_refs: string[]; basis_status: string };
type TemplateSource = { template_section?: string | null; template_requirement?: string | null; template_appropriate_judgment?: string | null; template_violation_guidance?: string | null; template_review_guidance?: string | null; display_checks?: Array<{text: string; status: string; reason: string}> };
export type ResultRow = TemplateSource & { item_title?: string; source_product?: string; template_guidance?: string; manual_review_reasons?: string[]; judgment_scope?: "TEXT_ONLY" | "RULE"; model_assessment?: {verdict: string; reason: string; status: string} | null; row_id?: string; item_id: string; title: string; question: string; criterion: string; template_example?: string; requirement_checks?: {status: string; finding_basis?: string}[]; verdict: string; reason: string; evidence: string; evidence_locations?: EvidenceBox[]; chunk_locations?: EvidenceBox[]; review_locations?: EvidenceBox[]; evidence_location_status?: "MAPPED" | "NO_CITATION" | "SOURCE_GEOMETRY_MISSING" | "UNRESOLVED_REFERENCE"; reading_quality_review?: {policy: string; issues: {location: string; code: string}[]} | null; rule_basis?: RuleBasis | null };
export type HumanReviewDecision = { decision: "APPROVED" | "REJECTED"; comment: string | null; reviewer_id: string; decided_at: string; ai_result_unchanged: true };
export type ResultWorkspace = { extraction_status?: ExtractionStatus; source_policy?: "template-only" | "template-plus-v2"; excluded_rows?: ResultRow[]; execution_omissions?: {scope_id: string; item_id: string; reason: string}[]; template_coverage?: {template_section: string; source_row_count: number; rule_count: number; requested_count: number; manual_review_count: number; missing_count: number}[]; available: boolean; source_type: string; rows: ResultRow[]; review_candidate_rows?: ResultRow[]; deferred_rules?: {item_id: string; reason: string; scope_id?: string; deferred_kind?: string}[]; output_failure_count?: number; output_failure_pairs?: {ad_id: string; scope_id?: string; product_id?: string; item_id: string; reason?: string}[]; partial_result_warning?: string | null; human_decision?: HumanReviewDecision | null };
export type EvidenceBox = { key: string; pageNo: number; bbox: number[]; width: number; height: number; precision?: "LINE" | "REGION" | "CHUNK"; asset_id?: string | null; source_page_no?: number };

export function reviewItemTitle(row: ResultRow): string { return row.item_title || row.title; }
export function reviewSourceCriterion(row: ResultRow): string {
  const saved = row.template_appropriate_judgment;
  if (saved && !["O", "△"].includes(saved.trim())) return saved;
  if (row.template_guidance) return row.template_guidance;
  if (/TRUE\/FALSE\/UNKNOWN|selected_template|\[적용조건\]/.test(row.criterion ?? "")) return row.question || "";
  return row.criterion || row.question || "";
}

export function resultChunkBoxes(row: ResultRow): EvidenceBox[] {
  return row.chunk_locations ?? [];
}

export type LegalBasisEntry = { key: string; label: string; searchQuery: string | null };

function cleanLegalBasisRefs(refs: readonly string[]): string[] {
  return refs.flatMap(ref => ref
    .replace(/(제\d+(?:의\d+)?[조항호목]|\d+)\s*[（(][^()（）]*[)）]/g, "$1")
    .split(/[;\n]+|,\s*(?=(?:동법\s*)?(?:시행령|시행규칙)|[^,]*(?:법|법률|감독규정)\s*제\d)/)
    .map(part => part
      .replace(/[「」『』]/g, "")
      .replace(/(?:실행_점검항목\s*[:：]\s*)?\b(?:[CDRT]-\d+|TPL-[a-f\d]+)\b/g, "")
      .replace(/^[\s·:：,()[\]-]+|[\s·:：,()[\]-]+$/g, "")
      .replace(/\s+/g, " ").trim())
    .filter(Boolean));
}

function authorityName(label: string): string | null {
  const match = label.match(/^(.+?(?:법률|법|시행령|시행규칙|감독규정|규정|기준))(?=\s*제\d|$)/);
  return match?.[1].trim() ?? null;
}

export function legalBasisEntries(refs: readonly string[]): LegalBasisEntry[] {
  let baseStatute: string | null = null;
  const entries: LegalBasisEntry[] = [];
  const seen = new Set<string>();
  for (let label of cleanLegalBasisRefs(refs)) {
    const namedBase = label.startsWith("동법") ? undefined : label.match(/^(.+?(?:법률|법))(?=\s*제\d|\s*(?:시행령|시행규칙))/)?.[1]?.trim();
    if (namedBase) baseStatute = namedBase;
    label = label.replace(/^동법\s*(시행령|시행규칙)/, (_, child: string) => baseStatute ? `${baseStatute} ${child}` : `동법 ${child}`);
    if (/^시행령\s*제/.test(label) && baseStatute) label = `${baseStatute} 시행령 ${label.replace(/^시행령\s*/, "")}`;
    if (/^시행규칙\s*제/.test(label) && baseStatute) label = `${baseStatute} 시행규칙 ${label.replace(/^시행규칙\s*/, "")}`;
    if (/^감독규정\s*제/.test(label) && baseStatute) label = `${baseStatute.replace(/(?:법률|법)$/, "")}감독규정 ${label.replace(/^감독규정\s*/, "")}`;
    const key = label.normalize("NFKC").replace(/[^\p{L}\p{N}]/gu, "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const authority = authorityName(label);
    const internal = /(?:광고심의\s*기준|내부통제기준)/.test(label);
    entries.push({ key, label, searchQuery: internal ? null : authority });
  }
  return entries;
}

export function legalBasisLines(refs: readonly string[]): string[] {
  return legalBasisEntries(refs).map(entry => entry.label);
}

export function resultEvidenceBoxes(row: ResultRow, layout?: ParserLayout): EvidenceBox[] {
  // An explicitly empty authoritative mapping must not fall back to matching
  // another product/asset's identical wording. Legacy saved workbooks only
  // retain the text-only path below.
  if (row.evidence_locations?.length) return row.evidence_locations;
  if (row.verdict === "판단불가" && row.review_locations?.length) return row.review_locations;
  if (row.evidence_locations !== undefined) return row.evidence_locations;
  return evidenceBoxes(row.evidence, layout);
}

export function missingSourceLabel(row: ResultRow): string {
  if (row.manual_review_reasons?.length && !row.evidence.trim()) return "사람 검토 항목 · 원문 직접 확인 필요";
  if (row.model_assessment?.status === "WITHHELD_BY_GROUNDING_GUARD")
    return "판정 설명과 인용 원문의 일치를 확인하지 못해 위치 표시를 보류했습니다. 문구 누락으로 확정한 것은 아닙니다.";
  if (row.evidence_location_status === "SOURCE_GEOMETRY_MISSING")
    return "판정용 원문에 좌표 없음 · 미리보기와의 위치 연결 필요";
  if (row.evidence_location_status === "UNRESOLVED_REFERENCE")
    return "인용 원문의 위치 연결 미완료 · 광고 전체 판정이라는 뜻은 아님";
  if (row.evidence.trim()) return "원문은 연결됐으나 bbox 매핑 없음";
  if (row.reading_quality_review?.issues?.length)
    return "판독 불확실성으로 근거 인용 보류 · 원본 확인 필요";
  if (row.verdict === "미해당") return "미해당 판정으로 원문 위치 불필요";
  if (row.verdict === "위반" && row.requirement_checks?.some(check => check.status === "MISSING" && check.finding_basis === "ABSENCE"))
    return "필수 문구 누락으로 판정되어 해당 문구의 원문 위치가 없습니다. 원본 대조 필요";
  return "판정 근거 원문을 확인하지 못해 위치를 표시할 수 없습니다. 누락 여부는 원본 확인이 필요합니다.";
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
