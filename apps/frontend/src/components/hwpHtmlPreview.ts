/** Highlight only a unique original quote in the live HTML text, never pixel boxes. */
export function hwpHtmlPreview(html: string, quotes: string[], zoom: number) {
  const document = new DOMParser().parseFromString(html, 'text/html');
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let compact = '';
  const positions: Array<{ node: Text; offset: number }> = [];
  let previousBlock: Element | null = null;
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    if (node.parentElement?.closest('script,style,title,mark')) continue;
    const block = node.parentElement?.closest('p,td,th,li,h1,h2,h3,h4') ?? null;
    if (nodes.length && block !== previousBlock) {
      compact += '\u0000';
      positions.push({ node, offset: 0 });
    }
    previousBlock = block;
    nodes.push(node);
    for (let offset = 0; offset < node.data.length; offset += 1) {
      if (/\s/.test(node.data[offset])) continue;
      compact += node.data[offset];
      positions.push({ node, offset });
    }
  }
  const ranges = new Map<Text, Array<[number, number]>>();
  let matched = 0;
  let ambiguous = 0;
  for (const raw of new Set(quotes)) {
    const quote = raw.replace(/\s/g, '');
    if (!quote) continue;
    const first = compact.indexOf(quote);
    if (first < 0) continue;
    if (compact.indexOf(quote, first + 1) >= 0) { ambiguous += 1; continue; }
    matched += 1;
    const start = positions[first];
    const end = positions[first + quote.length - 1];
    const from = nodes.indexOf(start.node);
    const to = nodes.indexOf(end.node);
    for (let index = from; index <= to; index += 1) {
      const node = nodes[index];
      const lo = index === from ? start.offset : 0;
      const hi = index === to ? end.offset + 1 : node.data.length;
      ranges.set(node, [...(ranges.get(node) ?? []), [lo, hi]]);
    }
  }
  for (const [node, values] of ranges) {
    const merged: Array<[number, number]> = [];
    values.sort((a, b) => a[0] - b[0]).forEach(([lo, hi]) => {
      const last = merged.at(-1);
      if (last && lo <= last[1]) last[1] = Math.max(last[1], hi);
      else merged.push([lo, hi]);
    });
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const [lo, hi] of merged) {
      fragment.append(document.createTextNode(node.data.slice(offset, lo)));
      const mark = document.createElement('mark');
      mark.dataset.reviewQuote = 'true';
      mark.textContent = node.data.slice(lo, hi);
      fragment.append(mark);
      offset = hi;
    }
    fragment.append(document.createTextNode(node.data.slice(offset)));
    node.replaceWith(fragment);
  }
  const style = document.createElement('style');
  style.textContent = `@media screen{body{margin:0;padding:8px;zoom:${zoom || 1}}.document-page{max-width:100%;margin:0 auto!important} }`;
  document.head.append(style);
  return { html: '<!doctype html>' + document.documentElement.outerHTML, matched, ambiguous };
}
