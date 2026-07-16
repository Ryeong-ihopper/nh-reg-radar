import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.LOCAL_UI_BASE_URL ?? "http://localhost:5173";
const email = process.env.LOCAL_UI_EMAIL;
const password = process.env.LOCAL_UI_PASSWORD;
const outputDir = process.env.VISUAL_OUTPUT_DIR ?? "/tmp/nh-ad-compliance-visual";

if (!email || !password) {
  throw new Error("LOCAL_UI_EMAIL and LOCAL_UI_PASSWORD are required; do not commit credentials.");
}

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 }, deviceScaleFactor: 1 });
try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.screenshot({ path: path.join(outputDir, "01-login.png"), fullPage: true });
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(/\/advertisements|\/standards/);
  await page.getByRole("navigation", { name: "주 탐색" }).waitFor();
  await page.screenshot({ path: path.join(outputDir, "02-workspace.png"), fullPage: true });
  const createLink = page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "광고물 등록" });
  if (await createLink.count()) {
    await createLink.click();
    await page.waitForURL(/\/advertisements\/new$/);
    await page.getByRole("heading", { name: "광고물 등록" }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "03-advertisement-create.png"), fullPage: true });
  }
  console.log(`Visual screenshots written to ${outputDir}`);
} finally {
  await browser.close();
}
