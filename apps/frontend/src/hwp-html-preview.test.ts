import { expect, test } from 'vitest';
import { hwpHtmlPreview } from './components/hwpHtmlPreview';

test('HTML citation uses one original text match across formatting without pixel boxes', () => {
  const result = hwpHtmlPreview('<html><head></head><body><p>기본금리 <strong>연 3.5%</strong> 적용</p><p>우대금리 연 0.5%</p></body></html>', ['기본금리 연 3.5% 적용'], 1);
  const document = new DOMParser().parseFromString(result.html, 'text/html');
  expect(result.matched).toBe(1);
  expect(Array.from(document.querySelectorAll('mark')).map(node => node.textContent).join('')).toBe('기본금리 연 3.5% 적용');
  expect(document.body.textContent).toBe('기본금리 연 3.5% 적용우대금리 연 0.5%');
  expect(document.querySelector('[data-testid="active-evidence-box"]')).toBeNull();
});

test('repeated or absent citations do not invent an HTML location', () => {
  const result = hwpHtmlPreview('<p>우대금리 연 0.5%</p><p>우대금리 연 0.5%</p>', ['우대금리 연 0.5%', '최대 연 9%'], 1);
  expect(result.matched).toBe(0);
  expect(result.ambiguous).toBe(1);
  expect(result.html).not.toContain('<mark');
});

test('phrases from different table cells cannot form a false citation', () => {
  const result = hwpHtmlPreview('<table><tr><td>최대금리</td><td>연 3%</td></tr></table>', ['최대금리연3%'], 1);
  expect(result.matched).toBe(0);
});
