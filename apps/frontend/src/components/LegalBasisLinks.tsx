import { type LegalBasisEntry } from "./operationalResultModel";
import { legalReferenceLink } from "./mappedLegalReferences";

export function LegalBasisLinks({ entries }: { entries: LegalBasisEntry[] }) {
  if (!entries.length) return <p className="review-empty-note">이 항목에 저장된 근거 법령·규정 연결이 없습니다.</p>;
  return <ul className="review-legal-links">{entries.map(entry => {
    const link = legalReferenceLink(entry);
    return <li key={entry.key}><span className="reference-link-icon" aria-hidden="true">↗</span><div><strong>{entry.label}</strong>{link
      ? <a href={link.href} target="_blank" rel="noopener noreferrer">{link.label}</a>
      : <small>협회·내부 기준 · 원문 링크 미등록</small>}</div></li>;
  })}</ul>;
}
