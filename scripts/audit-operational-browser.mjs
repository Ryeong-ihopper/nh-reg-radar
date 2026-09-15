// Browser smoke for the active operational UI. No gold or expected verdicts.
// node scripts/audit-operational-browser.mjs SESSION OUTPUT [SOURCE CLASSIFICATION]
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
const require = createRequire(resolve('apps/frontend/package.json'));
const { chromium } = require('playwright');
const [sessionPath, output, source, classification] = process.argv.slice(2);
const session = JSON.parse(await readFile(sessionPath, 'utf8'));
const base = new URL(session.url).origin;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
const requests = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => {
  if (response.url().includes('/api/') && response.request().method() !== 'GET')
    requests.push({ path: new URL(response.url()).pathname, status: response.status() });
});
try {
  await page.goto(`${base}/login`);
  await page.getByLabel('이메일').fill(session.email);
  await page.getByLabel('비밀번호').fill(session.password);
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await page.waitForURL('**/advertisements');
  if (source?.startsWith('REV-')) {
    const workspacePromise = page.waitForResponse(response => response.url().endsWith(`/operational/reviews/${source}/workspace`));
    await page.goto(`${base}/reviews/${source}/results`);
    const workspace = await (await workspacePromise).json();
    const templateRows = workspace.rows.filter(row => row.rule_basis?.source_type === 'INTERNAL_TEMPLATE');
    if (templateRows.length && !templateRows.some(row => row.template_example))
      throw new Error('Template reference text missing from server projection');
    const downloadButton = page.getByRole('button', { name: '결과 JSON 다운로드', exact: true });
    await downloadButton.waitFor();
    const downloadPromise = page.waitForEvent('download');
    await downloadButton.click();
    const download = await downloadPromise;
    await download.saveAs(resolve(output, 'export.json'));
    const exported = JSON.parse(await readFile(resolve(output, 'export.json'), 'utf8'));
    if (exported.schema_version === 'operational-review-export-v2' &&
        JSON.stringify(exported.results) !== JSON.stringify(workspace.rows))
      throw new Error('Downloaded rows differ from the active result workspace');
    const located = workspace.rows.find(row => row.evidence_locations?.length);
    let highlightChecked = false;
    if (located) {
      await page.locator('.single-regulation').filter({has: page.locator('header strong', {hasText: `${located.item_id} ·`})}).first().hover();
      await page.getByTestId('active-evidence-box').first().waitFor();
      await page.getByAltText('심의 광고 원본').waitFor();
      await page.waitForFunction(() => {
        const image = document.querySelector('.single-advertisement-canvas img');
        return image?.complete && image.naturalWidth > 0;
      });
      highlightChecked = true;
    }
    // Exercise navigation to a different original asset, not just page 1.
    const later = workspace.rows.find(row => row.evidence_locations?.[0]?.pageNo > 1);
    let laterAssetChecked = false;
    if (later) {
      const expected = later.evidence_locations[0];
      const previewRequest = page.waitForResponse(response => response.url().includes(expected.asset_id) && response.status() === 200);
      await page.locator('.single-regulation').filter({has: page.locator('header strong', {hasText: `${later.item_id} ·`})}).first().hover();
      await previewRequest;
      await page.waitForFunction(() => {
        const image = document.querySelector('.single-advertisement-canvas img');
        return image?.complete && image.naturalWidth > 0;
      });
      laterAssetChecked = true;
    }
    const scrollPanel = page.locator('.single-regulations-scroll');
    let independentScrollChecked = false;
    if (await scrollPanel.count()) {
      await page.getByLabel('근거 자동이동', {exact:true}).uncheck();
      await page.getByLabel('원본 확대', {exact:true}).selectOption('1');
      await page.waitForFunction(() => {
        const img = document.querySelector('.single-advertisement-canvas img');
        return img?.naturalWidth > 0 && Math.abs(img.getBoundingClientRect().width - img.naturalWidth) < 2;
      });
      const before = await page.evaluate(() => ({windowY:scrollY,left:document.querySelector('.single-advertisement-scroll').scrollTop}));
      await scrollPanel.evaluate(el => { el.scrollTop = el.scrollHeight; });
      const after = await page.evaluate(() => ({windowY:scrollY,left:document.querySelector('.single-advertisement-scroll').scrollTop,right:document.querySelector('.single-regulations-scroll').scrollTop}));
      if (before.windowY !== after.windowY || before.left !== after.left || after.right <= 0)
        throw new Error(`Original and judgment scrolling are not independent: ${JSON.stringify({before,after})}`);
      const pageSelect = page.getByLabel('원본 페이지', {exact:true});
      const options = await pageSelect.locator('option').evaluateAll(nodes => nodes.map(n => n.value));
      await pageSelect.selectOption(options.at(-1));
      await page.waitForFunction(() => document.querySelector('.single-advertisement-canvas img')?.complete);
      await page.getByRole('button', {name:'이전 원본 페이지',exact:true}).click();
      if (await pageSelect.inputValue() !== options.at(-2)) throw new Error('Manual page navigation failed');
      await pageSelect.selectOption(options.at(-1));
      await page.getByLabel('원본 확대', {exact:true}).selectOption('2');
      await page.waitForFunction(() => {
        const img = document.querySelector('.single-advertisement-canvas img');
        return img?.naturalWidth > 0 && Math.abs(img.getBoundingClientRect().width - img.naturalWidth*2) < 2;
      });
      await page.screenshot({path:resolve(output,'native-zoom.png')});
      await page.getByLabel('원본 확대', {exact:true}).selectOption('0');
      await scrollPanel.evaluate(el => { el.scrollTop = 0; });
      independentScrollChecked = true;
    }
    await page.screenshot({ path: resolve(output, 'viewport.png') });
    await page.screenshot({ path: resolve(output, 'result.png'), fullPage: true });
    if (errors.length) throw new Error(errors.join('\n'));
    await writeFile(resolve(output, 'browser-check.json'), JSON.stringify({ status: 'PASS', review: source, export: 'export.json', rows: workspace.rows.length, source_highlight_checked: highlightChecked, later_asset_preview_checked: laterAssetChecked, independent_scroll_zoom_navigation_checked: independentScrollChecked, page_errors: errors }, null, 2));
    console.log('PASS: result page, saved-row JSON export and available source highlight');
    await browser.close();
    process.exit(0);
  }
  await page.goto(`${base}/advertisements/new`);
  await page.getByLabel('상세 상품군 *', { exact: false }).waitFor();
  const name = `운영연결점검-${new Date().toISOString()}`;
  let accepted = null;
  if (source) {
    await page.getByLabel('광고명 *', { exact: true }).fill(name);
    await page.locator('select[id$="-type"]').selectOption('WEB_PRODUCT_PAGE');
    await page.locator('select[id$="-group"]').selectOption('DEPOSIT');
    await page.locator('select[id$="-classification"]').selectOption(classification);
    await page.getByLabel('광고 1 원본 파일', { exact: true }).setInputFiles(source);
    const response = page.waitForResponse(r => /\/advertisements\/[^/]+\/reviews$/.test(r.url()) && r.request().method() === 'POST');
    await page.getByRole('button', { name: '광고 1개 등록 후 자동심의', exact: true }).click();
    const res = await response;
    accepted = await res.json();
    if (res.status() !== 202) throw new Error(`Review submission: ${res.status()}`);
  }
  await page.screenshot({ path: resolve(output, 'browser.png'), fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  const report = { status: 'PASS', name, accepted, url: page.url(), page_errors: errors };
  await writeFile(resolve(output, 'browser-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
} catch (error) {
  await page.screenshot({ path: resolve(output, 'browser-failure.png'), fullPage: true });
  await writeFile(resolve(output, 'browser-failure.json'), JSON.stringify({
    error: error.message, url: page.url(), requests,
    alerts: await page.locator('[role="alert"]').allTextContents(), page_errors: errors,
  }, null, 2));
  throw error;
} finally {
  await browser.close();
}
