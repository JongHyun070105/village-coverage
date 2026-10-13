import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const liveBaseUrl = process.env.PUBLIC_DEMO_LIVE_BASE_URL;
const liveOrigin = liveBaseUrl ? new URL(liveBaseUrl).origin : "";
const artifactEnabled = process.env.PUBLIC_DEMO_LIVE_EVIDENCE === "true";

type ApiObservation = {
  method: string;
  path: string;
  status: number;
  elapsed_ms: number | null;
  content_type: string | null;
  retry_after_seconds: number | null;
  error_code?: string;
  same_origin: boolean;
};

type JourneyStep = {
  name: string;
  status: "EXEC PASS" | "FAIL";
  elapsed_ms: number;
  page_path: string;
  visible_headings: string[];
  api_responses: ApiObservation[];
  screenshot: string | null;
};

function safeApiPath(pathname: string) {
  return pathname
    .replace(/(\/api\/schedules\/)[^/]+/g, "$1:id")
    .replace(/(\/api\/providers\/)[^/]+/g, "$1:id");
}

function captureApi(page: Page, origin: string) {
  const starts = new WeakMap<object, number>();
  const observations: ApiObservation[] = [];
  const pending: Promise<void>[] = [];
  page.on("request", (request) => {
    try {
      if (new URL(request.url()).pathname.startsWith("/api/")) starts.set(request, Date.now());
    } catch {
      // Ignore browser-internal request URLs.
    }
  });
  page.on("response", (response) => {
    const writeObservation = (async () => {
      const url = new URL(response.url());
      if (!url.pathname.startsWith("/api/")) return;
      const headers = response.headers();
      const item: ApiObservation = {
        method: response.request().method(),
        path: safeApiPath(url.pathname),
        status: response.status(),
        elapsed_ms: starts.has(response.request())
          ? Math.max(0, Date.now() - (starts.get(response.request()) ?? Date.now()))
          : null,
        content_type: headers["content-type"]?.split(";")[0] ?? null,
        retry_after_seconds: Number.parseInt(headers["retry-after"] ?? "", 10) || null,
        same_origin: url.origin === origin,
      };
      if (!response.ok() && item.content_type?.includes("json")) {
        const body = await response.json().catch(() => null) as
          | { code?: unknown; detail?: unknown; error?: { code?: unknown } }
          | null;
        const code = body?.error?.code ?? body?.code ?? body?.detail;
        if (typeof code === "string" && /^[A-Z][A-Z0-9_]{2,79}$/.test(code)) {
          item.error_code = code;
        }
      }
      observations.push(item);
    })();
    pending.push(writeObservation);
  });
  return {
    observations,
    async flush() {
      await Promise.all(pending);
    },
  };
}

test.skip(!liveBaseUrl, "Set PUBLIC_DEMO_LIVE_BASE_URL to run the opt-in public Render journey.");

test("remote public demo completes the browser journey and isolates visitor sessions", async ({ browser }, testInfo) => {
  test.setTimeout(720_000);
  const contexts: BrowserContext[] = [];
  const steps: JourneyStep[] = [];
  const api: ApiObservation[] = [];
  let lastStep = "open dashboard";
  let status: "EXEC PASS" | "FAIL" = "FAIL";
  let failureCategory: string | null = null;
  let captureB: ReturnType<typeof captureApi> | null = null;
  const contextA = await browser.newContext({ acceptDownloads: true });
  contexts.push(contextA);
  const pageA = await contextA.newPage();
  const captureA = captureApi(pageA, liveOrigin);
  const repositoryRoot = resolve(process.cwd(), "..");
  const screenshotDirectory = resolve(repositoryRoot, "artifacts/qa/render_public_demo_journey_20261013");
  const artifactPath = resolve(repositoryRoot, "artifacts/qa/public_demo_browser_journey_20261013.json");
  let planId = "";
  let replannedId = "";
  let regionId = "pilot:홍성군 장곡면";
  let round: { provider_id: string; service_round_id: string } | undefined;
  const screenshots: string[] = [];

  const runStep = async (
    name: string,
    action: () => Promise<void>,
    options: { page?: Page; capture?: ReturnType<typeof captureApi>; screenshotName?: string } = {},
  ) => {
    lastStep = name;
    const started = Date.now();
    const stepPage = options.page ?? pageA;
    const stepCapture = options.capture ?? captureA;
    const firstObservation = stepCapture.observations.length;
    let stepStatus: JourneyStep["status"] = "EXEC PASS";
    try {
      await action();
    } catch (error) {
      stepStatus = "FAIL";
      throw error;
    } finally {
      await stepCapture.flush();
      let pagePath = "unknown";
      try {
        pagePath = new URL(stepPage.url()).pathname;
      } catch {
        // The page may still be at about:blank if the first navigation failed.
      }
      const visibleHeadings = await stepPage.locator("h1, h2").allInnerTexts().catch(() => []);
      let screenshot: string | null = null;
      if (options.screenshotName) {
        await mkdir(screenshotDirectory, { recursive: true });
        const screenshotPath = `artifacts/qa/render_public_demo_journey_20261013/${options.screenshotName}.png`;
        try {
          await stepPage.screenshot({
            path: resolve(repositoryRoot, screenshotPath),
            fullPage: true,
            animations: "disabled",
          });
          screenshot = screenshotPath;
          screenshots.push(screenshotPath);
        } catch {
          screenshot = null;
        }
      }
      steps.push({
        name,
        status: stepStatus,
        elapsed_ms: Date.now() - started,
        page_path: pagePath,
        visible_headings: visibleHeadings,
        api_responses: stepCapture.observations.slice(firstObservation),
        screenshot,
      });
    }
  };

  try {
    await runStep("open a fresh browser and verify dashboard data", async () => {
      const response = await pageA.goto("/", { waitUntil: "domcontentloaded", timeout: 120_000 });
      expect(response?.status()).toBe(200);
      await expect(pageA.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible({ timeout: 60_000 });
      await expect(pageA.getByLabel("공개 데모 안내")).toContainText("합성/공개 데이터");
      const apiCookie = (await contextA.cookies(`${liveOrigin}/api`))
        .find((cookie) => cookie.name === "vc_demo_session");
      expect(apiCookie).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/api" });
    }, { screenshotName: "01-dashboard" });

    await runStep("select Hongseong Janggok from the region selector", async () => {
      await pageA.getByRole("link", { name: "시나리오 비교" }).click();
      await expect(pageA.getByRole("heading", { name: "네 가지 계획안을 같은 조건으로 나란히 비교" })).toBeVisible();
      const regionSelect = pageA.getByLabel("지역", { exact: true });
      await expect(pageA.locator('#scenario-region option[value="pilot:홍성군 장곡면"]'))
        .toHaveCount(1, { timeout: 60_000 });
      await regionSelect.selectOption("pilot:홍성군 장곡면");
      await expect(regionSelect).toHaveValue("pilot:홍성군 장곡면");
      regionId = await regionSelect.inputValue();
    });

    await runStep("compare four policies under the same conditions", async () => {
      const compareButton = pageA.getByRole("button", { name: "4안 비교 실행" });
      await compareButton.click();
      await expect(compareButton).toBeEnabled({ timeout: 480_000 });
      await expect(pageA.locator(".scenario-grid article")).toHaveCount(4);
      await expect(pageA.locator(".scenario-card .empty-line")).toHaveCount(0);
      await expect(pageA.getByRole("link", { name: "계획 상세·승인으로 이동" })).toHaveCount(4);
    }, { screenshotName: "02-scenario-compare" });

    await runStep("create a plan from the visible UI and open its detail", async () => {
      await pageA.getByRole("link", { name: "계획 상세·승인으로 이동" }).first().click();
      await expect(pageA.getByRole("heading", { name: "계획 v1" })).toBeVisible({ timeout: 60_000 });
      const planUrl = new URL(pageA.url());
      planId = planUrl.searchParams.get("id") ?? "";
      expect(planId).toBeTruthy();
    }, { screenshotName: "03-plan-v1" });

    await runStep("reload and verify the same session retains its plan", async () => {
      await pageA.reload({ waitUntil: "domcontentloaded" });
      await expect(pageA.getByRole("heading", { name: "계획 v1" })).toBeVisible({ timeout: 60_000 });
    });

    await runStep("open the provider participation screen for a plan round", async () => {
      const requestStarted = Date.now();
      const planResponse = await contextA.request.get(`${liveOrigin}/api/schedules/${encodeURIComponent(planId)}`);
      const planHeaders = planResponse.headers();
      captureA.observations.push({
        method: "GET",
        path: "/api/schedules/:id",
        status: planResponse.status(),
        elapsed_ms: Date.now() - requestStarted,
        content_type: planHeaders["content-type"]?.split(";")[0] ?? null,
        retry_after_seconds: Number.parseInt(planHeaders["retry-after"] ?? "", 10) || null,
        same_origin: new URL(`${liveOrigin}/api/schedules`).origin === liveOrigin,
      });
      expect(planResponse.status()).toBe(200);
      const plan = await planResponse.json() as { rounds: Array<{ provider_id: string; service_round_id: string }> };
      round = plan.rounds[0];
      expect(round).toBeTruthy();
      await pageA.goto(`/providers/${encodeURIComponent(round!.provider_id)}`, { waitUntil: "domcontentloaded" });
      const roundCard = pageA.locator(`[data-demo-round-id="${round!.service_round_id}"]`);
      await expect(roundCard).toBeVisible({ timeout: 60_000 });
    });

    await runStep("click the visible demo decline button and verify saved state", async () => {
      const roundCard = pageA.locator(`[data-demo-round-id="${round!.service_round_id}"]`);
      await roundCard.getByRole("button", { name: "데모 불참" }).click();
      await expect(roundCard.getByText("이번 회차 불참")).toBeVisible();
      await expect(roundCard.getByRole("button", { name: "불참 되돌리기" })).toBeVisible();
    }, { screenshotName: "04-provider-decline" });

    await runStep("replan from the visible UI after the provider decline", async () => {
      await pageA.goto(`/plans?id=${encodeURIComponent(planId)}`, { waitUntil: "domcontentloaded" });
      await pageA.reload({ waitUntil: "domcontentloaded" });
      const replanButton = pageA.getByRole("button", { name: /불참 1건 반영해 새 버전/ });
      await expect(replanButton).toBeVisible({ timeout: 60_000 });
      await replanButton.click();
      await expect(pageA.getByRole("heading", { name: "계획 v2" })).toBeVisible({ timeout: 180_000 });
      replannedId = new URL(pageA.url()).searchParams.get("id") ?? "";
      expect(replannedId).toBeTruthy();
      expect(replannedId).not.toBe(planId);
    }, { screenshotName: "05-plan-v2" });

    await runStep("compare plan versions and reload the replan", async () => {
      await expect(pageA.getByRole("heading", { name: "같은 계획 계보의 버전" })).toBeVisible();
      await expect(pageA.getByRole("button", { name: /^v1 ·/ })).toBeVisible();
      await pageA.reload({ waitUntil: "domcontentloaded" });
      await expect(pageA.getByRole("heading", { name: "계획 v2" })).toBeVisible({ timeout: 60_000 });
    });

    await runStep("verify the Decision Memo for the new plan version", async () => {
      const requestStarted = Date.now();
      const memoResponse = await contextA.request.get(
        `${liveOrigin}/api/schedules/${encodeURIComponent(replannedId)}/decision-memo`,
      );
      const memoHeaders = memoResponse.headers();
      captureA.observations.push({
        method: "GET",
        path: "/api/schedules/:id/decision-memo",
        status: memoResponse.status(),
        elapsed_ms: Date.now() - requestStarted,
        content_type: memoHeaders["content-type"]?.split(";")[0] ?? null,
        retry_after_seconds: Number.parseInt(memoHeaders["retry-after"] ?? "", 10) || null,
        same_origin: new URL(`${liveOrigin}/api/schedules`).origin === liveOrigin,
      });
      expect(memoResponse.status()).toBe(200);
      const memo = await memoResponse.json() as { provenance?: string; simulation_notice?: string };
      expect(JSON.stringify(memo)).toMatch(/SIMULATED|시뮬레이션|모의/);
    });

    await runStep("download the CSV export from the visible plan link", async () => {
      const [csv] = await Promise.all([
        pageA.waitForEvent("download"),
        pageA.getByRole("link", { name: "회차 CSV" }).click(),
      ]);
      expect(csv.suggestedFilename()).toMatch(/\.csv$/);
    });

    await runStep("download the PDF export from the visible plan link", async () => {
      const [pdf] = await Promise.all([
        pageA.waitForEvent("download"),
        pageA.getByRole("link", { name: "검토보고서 PDF" }).click(),
      ]);
      expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
    });

    await runStep("refresh the plan after exports", async () => {
      await pageA.goto(`/plans?id=${encodeURIComponent(replannedId)}`, { waitUntil: "domcontentloaded" });
      await expect(pageA.getByRole("heading", { name: "계획 v2" })).toBeVisible({ timeout: 60_000 });
    });

    const contextB = await browser.newContext();
    contexts.push(contextB);
    const pageB = await contextB.newPage();
    const visitorBCapture = captureApi(pageB, liveOrigin);
    captureB = visitorBCapture;
    await runStep("open a separate browser B session", async () => {
      await pageB.goto("/", { waitUntil: "domcontentloaded", timeout: 120_000 });
      await expect(pageB.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible({ timeout: 60_000 });
      const cookieA = (await contextA.cookies(`${liveOrigin}/api`)).find((cookie) => cookie.name === "vc_demo_session");
      const cookieB = (await contextB.cookies(`${liveOrigin}/api`)).find((cookie) => cookie.name === "vc_demo_session");
      expect(cookieA).toBeTruthy();
      expect(cookieB).toBeTruthy();
      if (cookieA!.value === cookieB!.value) throw new Error("Visitor A and B shared a demo session cookie");
    }, { page: pageB, capture: visitorBCapture, screenshotName: "06-visitor-b-session" });

    await runStep("verify B sees the provider as available despite A's decline", async () => {
      await pageB.goto(`/providers/${encodeURIComponent(round!.provider_id)}`, { waitUntil: "domcontentloaded" });
      const bRoundCard = pageB.locator(`[data-demo-round-id="${round!.service_round_id}"]`);
      await expect(bRoundCard.getByRole("button", { name: "데모 불참" })).toBeVisible({ timeout: 60_000 });
      await expect(bRoundCard.getByRole("button", { name: "불참 되돌리기" })).toHaveCount(0);
    }, { page: pageB, capture: visitorBCapture });

    await runStep("verify B cannot read A's plan and has no plan history", async () => {
      await pageB.goto(`/plans?id=${encodeURIComponent(replannedId)}`, { waitUntil: "domcontentloaded" });
      await expect(pageB.locator(".api-error")).toContainText("요청한 자료를 찾을 수 없습니다.");
      await expect(pageB.locator(".api-error")).not.toContainText("세션이 만료");
      await pageB.goto("/plans", { waitUntil: "domcontentloaded" });
      await expect(pageB.locator(".plans-empty")).toContainText("저장된 계획이 없습니다.");
    }, { page: pageB, capture: visitorBCapture, screenshotName: "07-visitor-b-isolation" });

    status = "EXEC PASS";
  } catch (error) {
    failureCategory = error instanceof Error ? error.name : "UnknownError";
    throw error;
  } finally {
    await captureA.flush();
    api.push(...captureA.observations);
    if (captureB) {
      await captureB.flush();
      api.push(...captureB.observations);
    }
    if (artifactEnabled) {
      await mkdir(resolve(process.cwd(), "..", "artifacts/qa"), { recursive: true });
      await writeFile(artifactPath, `${JSON.stringify({
        source_sha: process.env.PUBLIC_DEMO_SOURCE_SHA ?? null,
        tested_sha: "NOT_VERIFIABLE",
        environment: "public_render_demo",
        timestamp: new Date().toISOString(),
        test_method: "Playwright Chromium against public Render web origin; browser cookies and request payloads were not persisted",
        actual_result: { status, steps, api_responses: api, screenshots },
        evidence: { expected_deployment_branch_sha: process.env.PUBLIC_DEMO_EXPECTED_DEPLOYMENT_SHA ?? null, deployed_sha: "NOT_VERIFIABLE" },
        limitation: ["Render dashboard deploy metadata and logs were unavailable.", "A single low-volume synthetic browser journey is not a load test or field-accuracy study."],
        failure_category: failureCategory,
        last_step: lastStep,
        region_id: regionId,
      }, null, 2)}\n`, "utf8");
    }
    await Promise.all(contexts.map((context) => context.close()));
    await testInfo.attach("public-demo-browser-journey.json", { path: artifactPath, contentType: "application/json" }).catch(() => undefined);
  }
  expect(status).toBe("EXEC PASS");
});
