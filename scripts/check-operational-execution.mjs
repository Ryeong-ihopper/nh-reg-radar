import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(resolve("apps/frontend/package.json"));
const { chromium } = require("playwright");
const manifest = JSON.parse(await readFile(process.argv[2], "utf8"));
const output = process.argv[3];
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({viewport:{width:1500,height:1050}});
const errors = [];
page.on("pageerror", e => errors.push(e.message));
try {
  const base = new URL(manifest.url).origin;
  await page.goto(`${base}/login`);
  await page.getByLabel("이메일").fill(manifest.email);
  await page.getByLabel("비밀번호").fill(manifest.password);
  await page.getByRole("button", {name:"로그인",exact:true}).click();
  await page.waitForURL("**/advertisements");
  const routing = await page.request.put(
    `${base}/api/v1/operational/advertisements/${manifest.advertisement_id}/routing`,
    {data:{product_classification_code:process.argv[4]}},
  );
  if (!routing.ok()) throw new Error(`상세 상품군 저장 실패: ${routing.status()} ${await routing.text()}`);
  await page.goto(`${base}/advertisements/${manifest.advertisement_id}/review-request`);
  // Locate request route via the original detail page if route spelling differs.
  if (!await page.getByRole("button",{name:"AI 검토 시작",exact:true}).count()) {
    await page.goto(`${base}/advertisements/${manifest.advertisement_id}`);
    await page.getByRole("link",{name:/AI 검토/}).first().click();
  }
  await page.screenshot({path:`${output}/request.png`,fullPage:true});
  const responsePromise = page.waitForResponse(r => /\/advertisements\/[^/]+\/reviews$/.test(r.url()) && r.request().method()==="POST");
  await page.getByRole("button",{name:"AI 검토 시작",exact:true}).click();
  const response = await responsePromise;
  const accepted = await response.json();
  if (response.status()!==202) throw new Error(JSON.stringify(accepted));
  await page.waitForURL("**/status");
  await page.getByRole("heading",{name:"AI 검토 진행 상태",exact:true}).waitFor();
  await page.screenshot({path:`${output}/progress.png`,fullPage:true});
  if (errors.length) throw new Error(JSON.stringify(errors));
  const result = {status:"STARTED",...accepted,url:page.url(),page_errors:errors};
  await writeFile(`${output}/execution-check.json`,JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
} finally {await browser.close();}
