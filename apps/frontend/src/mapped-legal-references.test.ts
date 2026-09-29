import { describe, expect, it } from "vitest";
import { legalBasisEntries } from "./components/operationalResultModel";
import { legalReferenceLink, mappedLegalReferences } from "./components/mappedLegalReferences";

describe("mapped law links", () => {
  it("recognizes quoted statutory names and keeps article references separate", () => {
    const entries = legalBasisEntries(['「금융소비자 보호에 관한 법률」 제22조; 「금융소비자 보호에 관한 법률」 제21조']);
    expect(entries).toHaveLength(2);
    expect(entries[0].searchQuery).toBe("금융소비자 보호에 관한 법률");
    expect(legalReferenceLink(entries[0])?.href).toBe(`https://www.law.go.kr/lsSc.do?query=${encodeURIComponent(entries[0].searchQuery!)}`);
    expect(entries[1].label).toContain("제21조");
  });
  it("does not activate supplements or invent URLs for association and internal manuals", () => {
    const refs = mappedLegalReferences([
      {id: "T1", label: "Disclosure", kind: "TEMPLATE", scope: "Synthetic", source: {legal_basis: {statute: "예금자보호법 제32조", association: "은행 광고심의 기준 제16조"}}},
      {id: "T2", label: "Another disclosure", kind: "TEMPLATE", scope: "Synthetic", source: {legal_basis: {statute: "예금자보호법 제32조"}}},
      {id: "S1", label: "Disabled", kind: "SUPPLEMENT_32", scope: "Synthetic", source: {legal_basis: {statute: "금융지주회사법 제48조"}}},
    ]);
    expect(refs).toHaveLength(2);
    expect(refs[0].items.map(item => item.id)).toEqual(["T1", "T2"]);
    expect(legalReferenceLink(refs[1])).toBeNull();
    expect(refs.flatMap(ref => ref.items).some(item => item.id === "S1")).toBe(false);
  });
  it("uses official administrative-rule search for supervision rules", () => {
    const entry = legalBasisEntries(["금융지주회사감독규정 제24조"])[0];
    expect(legalReferenceLink(entry)?.href).toContain("https://www.law.go.kr/admRulSc.do?");
  });
});
