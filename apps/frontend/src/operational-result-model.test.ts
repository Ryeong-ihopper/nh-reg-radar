import { describe, expect, it } from "vitest";
import { evidenceBoxes, resultEvidenceBoxes, resultCounts, missingSourceLabel, type ResultRow } from "./components/operationalResultModel";
import type { ParserLayout } from "./api/operational";

const layout: ParserLayout = {schema_version: "operational-parser-layout-v1", source: "test", coordinate_basis: "rendered_original_200dpi",
  counts: {pages:1, regions:1, lines:1}, pages: [{page_no:1,canvas_w:100,canvas_h:200,regions:[{region_id:"R",bbox:[0,0,100,100],layout_label:null,text:"",lines:[{line_ref:"new-ref",text:"가입 전 상품설명서를 읽어주세요",bbox:[10,20,90,30],text_source:"ocr",confidence:null}]}]}]};

describe("single operational result", () => {
  it("distinguishes a missing-content assertion from a broken source reference without certifying coverage", () => {
    const row = {verdict: "위반", evidence: ""} as ResultRow;
    expect(missingSourceLabel(row)).toBe("판정 응답에 원문 줄 참조 없음");
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
});
