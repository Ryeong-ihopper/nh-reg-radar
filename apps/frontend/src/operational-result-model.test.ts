import { describe, expect, it } from "vitest";
import { legalBasisEntries, legalBasisLines, evidenceBoxes, resultChunkBoxes, resultEvidenceBoxes, resultCounts, missingSourceLabel, type ResultRow } from "./components/operationalResultModel";
import type { ParserLayout } from "./api/operational";

const layout: ParserLayout = {schema_version: "operational-parser-layout-v1", source: "test", coordinate_basis: "rendered_original_200dpi",
  counts: {pages:1, regions:1, lines:1}, pages: [{page_no:1,canvas_w:100,canvas_h:200,regions:[{region_id:"R",bbox:[0,0,100,100],layout_label:null,text:"",lines:[{line_ref:"new-ref",text:"가입 전 상품설명서를 읽어주세요",bbox:[10,20,90,30],text_source:"ocr",confidence:null}]}]}]};

describe("single operational result", () => {
  it("explains human review without implying a missing model response", () => {
    const row = {evidence: '', manual_review_reasons: ['시각 확인']} as unknown as ResultRow;
    expect(missingSourceLabel(row)).toBe('사람 검토 항목 · 원문 직접 확인 필요');
  });
  it("deduplicates citation text but preserves distinct article spellings", () => {
    const refs = ["C-052", "R-1583", "은행 광고심의 기준 제16조 제1항 제4호; 은행 광고심의 기준 제16조 제1항 4",
      "은행 광고심의 기준 제16조 제1항 제4호(표시 기준)", "은행 광고심의 기준 제16조 제1항 4"];
    const original = [...refs];
    expect(legalBasisLines(refs)).toEqual(["은행 광고심의 기준 제16조 제1항 제4호", "은행 광고심의 기준 제16조 제1항 4"]);
    expect(refs).toEqual(original);
  });
  it("preserves names and different provisions while removing internal reference metadata", () => {
    expect(legalBasisLines(["실행_점검항목:C-052", "R-1583 · 금융소비자 보호에 관한 법률 제22조 제2항(명확·공정 전달)",
      "금융소비자 보호에 관한 법률 제22조 제3항\n가상 기준(특례) 제2조", ""])).toEqual([
      "금융소비자 보호에 관한 법률 제22조 제2항", "금융소비자 보호에 관한 법률 제22조 제3항", "가상 기준(특례) 제2조"]);
  });
  it("splits, expands, and deduplicates combined legal bases with explicit link targets", () => {
    expect(legalBasisEntries([
      "금융지주회사법 제48조 제4항, 동법 시행령 제27조 제9항, 금융지주회사감독규정 제24조",
      "은행 광고심의 기준 제4장 공동광고시 준수사항",
      "금융지주회사법 제48조 제4항", "동법 시행령 제27조 제9항", "감독규정 제24조",
    ])).toEqual([
      {key:"금융지주회사법제48조제4항",label:"금융지주회사법 제48조 제4항",searchQuery:"금융지주회사법"},
      {key:"금융지주회사법시행령제27조제9항",label:"금융지주회사법 시행령 제27조 제9항",searchQuery:"금융지주회사법 시행령"},
      {key:"금융지주회사감독규정제24조",label:"금융지주회사감독규정 제24조",searchQuery:"금융지주회사감독규정"},
      {key:"은행광고심의기준제4장공동광고시준수사항",label:"은행 광고심의 기준 제4장 공동광고시 준수사항",searchQuery:null},
    ]);
  });
  it("keeps chunk context separate from exact judgment evidence", () => {
    const chunk = {key:"chunk",pageNo:1,bbox:[1,2,90,40],width:100,height:200,precision:"CHUNK" as const};
    const line = {key:"line",pageNo:1,bbox:[3,4,80,20],width:100,height:200,precision:"LINE" as const};
    const row = {evidence_locations:[line],chunk_locations:[chunk]} as unknown as ResultRow;
    expect(resultChunkBoxes(row)).toEqual([chunk]);
    expect(resultEvidenceBoxes(row, layout)).toEqual([line]);
  });
  it("withholds mismatched saved source quotations instead of displaying a valid bbox", () => {
    const row = {evidence: "", evidence_locations: [], model_assessment: {status: "WITHHELD_BY_GROUNDING_GUARD", verdict: "COMPLIANT", reason: "old result"}} as unknown as ResultRow;
    expect(missingSourceLabel(row)).toContain("문구 누락으로 확정한 것은 아닙니다");
    expect(resultEvidenceBoxes(row, layout)).toEqual([]);
  });
  it("distinguishes missing source geometry from whole-ad assessment", () => {
    const row = {evidence: "specific source", evidence_locations: [], evidence_location_status: "SOURCE_GEOMETRY_MISSING"} as unknown as ResultRow;
    expect(missingSourceLabel(row)).toContain("판정용 원문에 좌표 없음");
    expect(missingSourceLabel({...row, evidence_location_status: "UNRESOLVED_REFERENCE"})).toContain("광고 전체 판정이라는 뜻은 아님");
    expect(resultEvidenceBoxes(row, layout)).toEqual([]);
  });
  it("explains revoked reading citations without hiding unrelated unknown evidence", () => {
    const row = {verdict: "판단불가", evidence: "", evidence_locations: [],
      reading_quality_review: {policy:"reading-quality-gate-v1",issues:[{location:"applicability",code:"UNCERTAIN_READING_EVIDENCE"}]}} as unknown as ResultRow;
    expect(missingSourceLabel(row)).toContain("근거 인용 보류");
    expect(resultEvidenceBoxes(row, layout)).toEqual([]);
    expect(missingSourceLabel({...row,evidence:"독립 근거"})).toContain("bbox 매핑 없음");
    expect(missingSourceLabel({...row,reading_quality_review:null})).toBe("판정 근거 원문을 확인하지 못해 위치를 표시할 수 없습니다. 누락 여부는 원본 확인이 필요합니다.");
  });
  it("distinguishes a missing-content assertion from a broken source reference without certifying coverage", () => {
    const row = {verdict: "위반", evidence: ""} as ResultRow;
    expect(missingSourceLabel(row)).toBe("판정 근거 원문을 확인하지 못해 위치를 표시할 수 없습니다. 누락 여부는 원본 확인이 필요합니다.");
    expect(missingSourceLabel({...row, requirement_checks: [{status:"MISSING",finding_basis:"ABSENCE"}]})).toContain("원본 대조 필요");
    expect(missingSourceLabel({...row,evidence:"실제 원문"})).toContain("bbox 매핑 없음");
    expect(missingSourceLabel({...row,verdict:"미해당"})).toContain("원문 위치 불필요");
  });
  it("uses the same visible rows for all KPI counts", () => {
    const rows = ["충족","위반","미해당","판단불가"].map(verdict => ({verdict} as ResultRow));
    expect(resultCounts(rows)).toEqual({total:4,violation:1,unknown:1,compliant:1,notApplicable:1});
  });
  it("matches text, not stale workbook line references", () => {
    expect(evidenceBoxes("[old/L99] 가입전상품설명서를읽어주세요", layout)).toHaveLength(1);
    expect(evidenceBoxes("[new-ref] 없는 광고 문장입니다", layout)).toHaveLength(0);
  });
  it("does not fabricate a box for absent or insufficient evidence", () => {
    expect(evidenceBoxes("가입", layout)).toHaveLength(0);
    expect(evidenceBoxes("", layout)).toHaveLength(0);
    expect(evidenceBoxes("가입 전 상품설명서를 읽어주세요", {...layout,pages:[]})).toHaveLength(0);
  });
  it("does not text-match another asset when authoritative refs have no geometry", () => {
    const row = {evidence: "가입 전 상품설명서를 읽어주세요", evidence_locations: []} as unknown as ResultRow;
    expect(resultEvidenceBoxes(row, layout)).toEqual([]);
    const region = {key:"R",pageNo:2,bbox:[0,0,100,100],width:100,height:200,precision:"REGION" as const};
    expect(resultEvidenceBoxes({...row,evidence_locations:[region]}, layout)).toEqual([region]);
  });
  it("shows an uncertain region as a review target without calling it judgment evidence", () => {
    const review = {key:"review",pageNo:1,bbox:[1,2,3,4],width:100,height:200,precision:"LINE" as const};
    const row = {verdict:"판단불가", evidence:"", evidence_locations:[], review_locations:[review]} as unknown as ResultRow;
    expect(resultEvidenceBoxes(row, layout)).toEqual([review]);
  });
});
