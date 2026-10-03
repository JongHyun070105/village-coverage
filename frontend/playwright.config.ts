import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const apiBaseUrl = "http://127.0.0.1:8010";
const webBaseUrl = "http://127.0.0.1:3010";
const databasePath = join(tmpdir(), `village-coverage-playwright-${process.pid}.sqlite`);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  outputDir: "./test-results/e2e",
  use: {
    baseURL: webBaseUrl,
    viewport: { width: 1366, height: 768 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8010",
      cwd: repoRoot,
      url: `${apiBaseUrl}/api/regions`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VILLAGECOVERAGE_APP_DB: databasePath,
        FRONTEND_ORIGINS: "http://127.0.0.1:3010",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3010",
      cwd: process.cwd(),
      url: `${webBaseUrl}/plans`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: apiBaseUrl,
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
