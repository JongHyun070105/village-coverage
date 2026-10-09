import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const apiBaseUrl = "http://127.0.0.1:8010";
const webBaseUrl = "http://127.0.0.1:3010";
const isolatedStorageId = `${process.pid}-${Date.now()}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "public-demo.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 420_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  outputDir: join(tmpdir(), `villagecoverage-public-demo-e2e-${process.pid}`),
  use: {
    baseURL: webBaseUrl,
    viewport: { width: 1366, height: 768 },
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
        PUBLIC_DEMO_COOKIE_SECURE: "false",
        PUBLIC_DEMO_ALLOW_LOCALHOST: "true",
        VILLAGECOVERAGE_APP_DB: join(tmpdir(), `vc-public-demo-test-${isolatedStorageId}.sqlite`),
        VILLAGECOVERAGE_PUBLIC_DEMO_ROUTE_DB: join(
          tmpdir(),
          `vc-public-demo-routes-test-${isolatedStorageId}.sqlite`,
        ),
        FRONTEND_ORIGINS: webBaseUrl,
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
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_PUBLIC_DEMO_MODE: "true",
        VILLAGE_COVERAGE_PUBLIC_DEMO_API_ORIGIN: apiBaseUrl,
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
