import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const apiBaseUrl = "http://127.0.0.1:8010";
const webBaseUrl = "http://127.0.0.1:3020";
const isolatedRunId = `${process.pid}-${Date.now()}`;
const testPython = process.env.VILLAGECOVERAGE_TEST_PYTHON ?? ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "ui-regression.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  reporter: "list",
  outputDir: join(tmpdir(), `villagecoverage-ui-regression-${isolatedRunId}`),
  use: {
    baseURL: webBaseUrl,
    browserName: "chromium",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${testPython} tests/prepare_playwright_route_cache.py && ${testPython} -m uvicorn backend.main:app --host 127.0.0.1 --port 8010 --workers 1`,
      cwd: repoRoot,
      url: `${apiBaseUrl}/api/regions`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VILLAGE_COVERAGE_PUBLIC_DEMO: "true",
        PUBLIC_DEMO_ALLOW_LOCALHOST: "true",
        VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE: "true",
        VILLAGE_COVERAGE_TEST_MODE: "true",
        DATA_GO_KR_SERVICE_KEY: "",
        GEMINI_API_KEY: "",
        GEMINI_MODEL: "",
        KAKAO_REST_API_KEY: "",
        KOSIS_API_KEY: "",
        VILLAGECOVERAGE_APP_DB: join(tmpdir(), `vc-ui-regression-${isolatedRunId}.sqlite`),
        VILLAGE_COVERAGE_DB: join(tmpdir(), `vc-ui-regression-routes-${isolatedRunId}.sqlite`),
        VILLAGECOVERAGE_PUBLIC_DEMO_ROUTE_DB: join(tmpdir(), `vc-ui-regression-routes-${isolatedRunId}.sqlite`),
        FRONTEND_ORIGINS: webBaseUrl,
      },
    },
    {
      command: "mkdir -p .next/standalone/.next/static .next/standalone/public && cp -R .next/static/. .next/standalone/.next/static/ && cp -R public/. .next/standalone/public/ && node .next/standalone/server.js",
      cwd: process.cwd(),
      url: webBaseUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        HOSTNAME: "127.0.0.1",
        PORT: "3020",
        NEXT_PUBLIC_API_BASE_URL: "",
        NEXT_PUBLIC_KAKAO_MAP_JS_KEY: "",
        NEXT_PUBLIC_PUBLIC_DEMO_MODE: "true",
        VILLAGE_COVERAGE_PUBLIC_DEMO_API_ORIGIN: apiBaseUrl,
        VILLAGE_COVERAGE_TEST_MODE: "true",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
