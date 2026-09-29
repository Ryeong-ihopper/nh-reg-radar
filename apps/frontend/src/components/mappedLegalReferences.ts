import { legalBasisEntries, type LegalBasisEntry } from "./operationalResultModel";

export type MappedCriterion = {
  id: string; label: string; kind: string; scope: string;
  source: { legal_basis?: { statute?: string; association?: string }; source_provenance?: { filename?: string } };
};
export type MappedReference = LegalBasisEntry & { items: Array<{id: string; label: string; scope: string}> };

export function mappedLegalReferences(rows: MappedCriterion[]): MappedReference[] {
  const references = new Map<string, MappedReference>();
  for (const row of rows.filter(item => item.kind === "TEMPLATE")) {
    const basis = row.source.legal_basis;
    for (const entry of legalBasisEntries([basis?.statute ?? "", basis?.association ?? ""])) {
      const existing = references.get(entry.key);
      const item = {id: row.id, label: row.label, scope: row.scope};
      if (existing) { if (!existing.items.some(value => value.id === row.id)) existing.items.push(item); }
      else references.set(entry.key, {...entry, items: [item]});
    }
  }
  return [...references.values()];
}

export function legalReferenceLink(entry: LegalBasisEntry): {href: string; label: string} | null {
  if (!entry.searchQuery) return null;
  const administrative = /(?:감독규정|고시|훈령|예규)$/.test(entry.searchQuery);
  return {href: `https://www.law.go.kr/${administrative ? "admRulSc" : "lsSc"}.do?query=${encodeURIComponent(entry.searchQuery)}`,
    label: administrative ? "국가법령정보센터 규정 검색 ↗" : "국가법령정보센터 법령 검색 ↗"};
}
