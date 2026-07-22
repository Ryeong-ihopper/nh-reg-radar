import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("allows the approved development ingress hostname without weakening host validation", () => {
  const config = readFileSync(resolve(process.cwd(), "vite.config.ts"), "utf8");
  expect(config).toContain('allowedHosts: ["nh-compliance.ihopper.co.kr"]');
});
