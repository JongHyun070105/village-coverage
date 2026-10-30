import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const baseURL = process.env.PUBLIC_DEMO_LIVE_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "public-demo-live.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 720_000,
  expect: { timeout: 30_000 },
  reporter: "list",
  outputDir: join(tmpdir(), "villagecoverage-public-demo-live-e2e"),
  use: {
    baseURL,
    viewport: { width: 1366, height: 900 },
    trace: "off",
    screenshot: "off",
  },
});
