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
async function waitForPreview() {
  await page.locator(".file-preview, .file-actions [role='alert']").first().waitFor({ timeout: 10_000 }).catch(() => undefined);
}
try {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.screenshot({ path: path.join(outputDir, "01-login.png"), fullPage: true });
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(/\/advertisements|\/standards/);
  await page.getByRole("navigation", { name: "주 탐색" }).waitFor();
  await page.screenshot({ path: path.join(outputDir, "02-workspace.png"), fullPage: true });

  const standardsLink = page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "기준자료 관리" });
  if (await standardsLink.count()) {
    await standardsLink.click();
    await page.waitForURL(/\/standards$/);
    await page.getByRole("heading", { name: "검토 기준자료 관리" }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "03-standards.png"), fullPage: true });
    await page.getByRole("button", { name: "기준자료 등록" }).click();
    await page.getByRole("heading", { name: "규정·가이드라인 등록" }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "04-standard-registration.png"), fullPage: true });
  }

  const validationLink = page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "검토 품질 관리" });
  if (await validationLink.count()) {
    await validationLink.click();
    await page.waitForURL(/\/validation\/datasets$/);
    await page.getByRole("heading", { name: "검증 데이터 및 담당자 판단" }).waitFor();
    await page.getByText("검증 데이터를 불러오는 중입니다.").waitFor({ state: "hidden", timeout: 10_000 }).catch(() => undefined);
    await page.screenshot({ path: path.join(outputDir, "05-validation-datasets.png"), fullPage: true });
  }

  const advertisementsLink = page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "광고물 목록" });
  if (await advertisementsLink.count()) {
  const detailLink = page.getByRole("link", { name: "상세 보기" }).first();
  if (await detailLink.count()) {
    await detailLink.click();
    await page.waitForURL(/\/advertisements\/[^/]+$/);
    await page.locator(".advertisement-detail-hero h2").waitFor();
    await waitForPreview();
    await page.screenshot({ path: path.join(outputDir, "03-advertisement-detail.png"), fullPage: true });

    const resultLink = page.getByRole("link", { name: "결과 확인" }).first();
    if (await resultLink.count()) {
      await resultLink.click();
      await page.waitForURL(/\/reviews\/[^/]+\/results$/);
      await page.getByRole("heading", { name: "AI 검토 결과" }).waitFor();
      await page.getByText("검토 결과 요약을 불러오는 중입니다.").waitFor({ state: "hidden", timeout: 10_000 }).catch(() => undefined);
      await page.screenshot({ path: path.join(outputDir, "04-review-results.png"), fullPage: true });
      await page.goBack({ waitUntil: "domcontentloaded" });
      await page.locator(".advertisement-detail-hero h2").waitFor();
    }

    await page.getByRole("link", { name: "AI 검토 요청", exact: true }).click();
    await page.waitForURL(/\/advertisements\/[^/]+\/reviews\/new$/);
    await page.getByRole("heading", { name: "검토 항목과 기준 선택" }).waitFor();
    await waitForPreview();
    await page.screenshot({ path: path.join(outputDir, "05-review-request.png"), fullPage: true });
  }

  await advertisementsLink.click();
  await page.waitForURL(/\/advertisements$/);
  await page.getByRole("heading", { name: "광고물 목록" }).waitFor();
  const createLink = page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "광고물 등록" });
  if (await createLink.count()) {
    await createLink.click();
    await page.waitForURL(/\/advertisements\/new$/);
    await page.getByRole("heading", { name: "광고물 등록" }).waitFor();
    await page.screenshot({ path: path.join(outputDir, "06-advertisement-create.png"), fullPage: true });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("navigation", { name: "주 탐색" }).getByRole("link", { name: "광고물 목록" }).click();
  await page.waitForURL(/\/advertisements$/);
  await page.getByRole("heading", { name: "광고물 목록" }).waitFor();
  await page.screenshot({ path: path.join(outputDir, "07-mobile-workspace.png"), fullPage: true });
  const mobileDetailLink = page.getByRole("link", { name: "상세 보기" }).first();
  if (await mobileDetailLink.count()) {
    await mobileDetailLink.click();
    await page.waitForURL(/\/advertisements\/[^/]+$/);
    await page.locator(".advertisement-detail-hero h2").waitFor();
    await waitForPreview();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(outputDir, "08-mobile-advertisement-detail.png"), fullPage: true });
  }
  }
  console.log(`Visual screenshots written to ${outputDir}`);
} finally {
  await browser.close();
}
