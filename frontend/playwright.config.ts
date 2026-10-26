import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const apiBaseUrl = "http://127.0.0.1:8010";
const webBaseUrl = "http://127.0.0.1:3010";
const isolatedRunId = `${process.pid}-${Date.now()}`;
const testPython = process.env.VILLAGECOVERAGE_TEST_PYTHON ?? ".venv/bin/python";
const databasePath = join(tmpdir(), `village-coverage-playwright-${isolatedRunId}.sqlite`);
const routeDatabasePath = join(
  tmpdir(),
  `village-coverage-playwright-routes-${isolatedRunId}.sqlite`,
);

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["public-demo.spec.ts", "ui-regression.spec.ts"],
  fullyParallel: false,
  workers: 1,
  timeout: 420_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  outputDir: join(tmpdir(), `villagecoverage-e2e-${process.pid}`),
  use: {
    baseURL: webBaseUrl,
    viewport: { width: 1366, height: 768 },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${testPython} tests/prepare_playwright_route_cache.py && ${testPython} -m uvicorn backend.main:app --host 127.0.0.1 --port 8010`,
      cwd: repoRoot,
      url: `${apiBaseUrl}/api/regions`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VILLAGECOVERAGE_APP_DB: databasePath,
        VILLAGE_COVERAGE_DB: routeDatabasePath,
        VILLAGE_COVERAGE_TEST_ROUTE_FIXTURE: "true",
        VILLAGE_COVERAGE_TEST_MODE: "true",
        VILLAGE_COVERAGE_PUBLIC_DEMO: "false",
        VILLAGECOVERAGE_PUBLIC_DEMO_ROUTE_DB: "",
        DATA_GO_KR_SERVICE_KEY: "",
        GEMINI_API_KEY: "",
        GEMINI_MODEL: "",
        KAKAO_REST_API_KEY: "",
        KOSIS_API_KEY: "",
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
        NEXT_PUBLIC_KAKAO_MAP_JS_KEY: "",
        NEXT_PUBLIC_PUBLIC_DEMO_MODE: "false",
        VILLAGE_COVERAGE_TEST_MODE: "true",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
