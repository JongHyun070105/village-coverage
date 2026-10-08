import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const apiBaseUrl = "http://127.0.0.1:8010";
const webBaseUrl = "http://127.0.0.1:3020";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "ui-regression.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  outputDir: join(tmpdir(), `villagecoverage-ui-regression-${process.pid}`),
  use: {
    baseURL: webBaseUrl,
    browserName: "chromium",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8010 --workers 1",
      cwd: repoRoot,
      url: `${apiBaseUrl}/api/regions`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VILLAGE_COVERAGE_PUBLIC_DEMO: "true",
        PUBLIC_DEMO_ALLOW_LOCALHOST: "true",
        VILLAGECOVERAGE_APP_DB: join(tmpdir(), `vc-ui-regression-${process.pid}.sqlite`),
        VILLAGE_COVERAGE_DB: join(tmpdir(), `vc-ui-regression-routes-${process.pid}.sqlite`),
        FRONTEND_ORIGINS: webBaseUrl,
      },
    },
    {
      command: "node .next/standalone/server.js",
      cwd: process.cwd(),
      url: webBaseUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        HOSTNAME: "127.0.0.1",
        PORT: "3020",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
