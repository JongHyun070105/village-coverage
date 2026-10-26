import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const webBaseUrl = "http://127.0.0.1:3020";
const screenshotRoot = join(tmpdir(), "ui-regression-screenshots");
const screenshotRoutes = new Set(["home", "scenarios", "plans", "providers", "evidence"]);
const publicRoutes = [
  { path: "/", name: "home" },
  { path: "/scenarios", name: "scenarios" },
  { path: "/plans", name: "plans" },
  { path: "/providers", name: "providers" },
  { path: "/calendar", name: "calendar" },
  { path: "/evidence", name: "evidence" },
  { path: "/data-quality", name: "data-quality" },
  { path: "/region-comparison", name: "region-comparison" },
  { path: "/methodology", name: "methodology" },
];
const restrictedRoutes = ["/demand", "/feedback", "/imports", "/pilot-imports", "/pilot-setup"];
const viewports = [
  { name: "desktop", width: 1440, height: 900, columns: 4 },
  { name: "laptop", width: 1280, height: 800, columns: 4 },
  { name: "tablet", width: 768, height: 1024, columns: 2 },
  { name: "mobile", width: 390, height: 844, columns: 1 },
];

test("public and guarded routes keep the shared layout at target viewports", async ({ page }) => {
  const consoleErrors: string[] = [];
  const cssFailures: string[] = [];
  const staticAssetFailures: string[] = [];
  const successfulStaticAssets = new Set<string>();
  const apiRequestUrls: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) apiRequestUrls.push(request.url());
  });
  page.on("response", (response) => {
    const resourceType = response.request().resourceType();
    if (resourceType === "stylesheet" && response.status() >= 400) {
      cssFailures.push(`${response.status()} ${response.url()}`);
    }
    if (resourceType === "stylesheet" || resourceType === "script") {
      if (response.status() === 200) successfulStaticAssets.add(response.url());
      else if (response.status() >= 400) staticAssetFailures.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    if (request.resourceType() === "stylesheet") {
      cssFailures.push(`${request.failure()?.errorText ?? "request failed"} ${request.url()}`);
    }
    if (request.resourceType() === "stylesheet" || request.resourceType() === "script") {
      staticAssetFailures.push(`${request.failure()?.errorText ?? "request failed"} ${request.url()}`);
    }
  });

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const route of publicRoutes) {
      const response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
      expect(response?.status(), `${route.path} should return a page`).toBe(200);
      await expect(page.locator("main h1").first(), `${route.path} should expose its page heading`).toBeVisible();

      const expectedContentMargin = viewport.width > 940 ? "232px" : viewport.width > 670 ? "68px" : "0px";
      await expect.poll(
        () => page.locator(".app-content").evaluate((element) => getComputedStyle(element).marginLeft),
        { message: `${route.path} should finish loading its responsive CSS` },
      ).toBe(expectedContentMargin);

      if (route.path === "/") {
        await expect(page.getByLabel("시군구 선택")).toBeEnabled();
      } else if (route.path === "/scenarios") {
        await expect(page.locator("#scenario-region")).toBeEnabled();
      } else if (route.path === "/plans") {
        await expect(page.locator(".plans-empty, .plans-list").first()).toBeVisible();
      } else if (route.path === "/providers") {
        await expect(page.locator(".provider-grid .provider-card").first()).toBeVisible();
      }

      if (["/", "/scenarios", "/plans", "/providers", "/evidence"].includes(route.path)) {
        await expect(page.locator(".api-error"), `${route.path} should not show an API error`).toHaveCount(0);
      }

      if (route.path === "/evidence") {
        const sourceRows = page.getByRole("row");
        const kreiRow = sourceRows.filter({ hasText: "KREI 농촌 주민 생활서비스 필요·이용" });
        await expect(kreiRow, "the external survey source should be present").toHaveCount(1);
        await expect(kreiRow.locator(".reality-reference")).toHaveText("참고");
        await expect(kreiRow.locator(".provenance-badge")).toHaveAttribute(
          "aria-label",
          /^외부 조사 기준값:/,
        );

        const publicDataRow = sourceRows.filter({ hasText: "전국협동조합표준데이터 (공급 후보 출처)" });
        await expect(publicDataRow, "the public-data source should be present").toHaveCount(1);
        await expect(publicDataRow.locator(".reality-real")).toHaveText("실제");
        await expect(publicDataRow.locator(".provenance-badge")).toHaveAttribute(
          "aria-label",
          /^공공데이터:/,
        );
      }

      const layout = await page.evaluate(() => {
        const visible = (element: Element | null) => {
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return {
            x: rect.x,
            y: rect.y,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
            display: style.display,
            padding: style.padding,
            border: style.border,
            background: style.backgroundColor,
          };
        };
        const sidebar = visible(document.querySelector(".sidebar"));
        const shell = visible(document.querySelector(".page-shell, .main-content, .page-main, .content-page"));
        const banner = visible(document.querySelector(".public-demo-banner"));
        const stylesheets = [...document.styleSheets].map((sheet) => sheet.href).filter(Boolean);
        return {
          viewport: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          stylesheets,
          sidebar,
          shell,
          banner,
          scenarioGrid: visible(document.querySelector(".scenario-grid")),
          scenarioCards: [...document.querySelectorAll(".scenario-card")].map(visible),
          toolbar: visible(document.querySelector(".toolbar-form")),
          provenance: visible(document.querySelector(".provenance-badge")),
          clippedText: [...document.querySelectorAll("h1, h2, p, label, button")]
            .filter((element) => {
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              return !element.closest(".sr-only") && rect.width > 0 && rect.height > 0 &&
                (rect.left < -1 || rect.right > innerWidth + 1 ||
                  ((style.overflowX === "hidden" || style.overflowX === "clip") && element.scrollWidth > element.clientWidth + 1));
            })
            .map((element) => element.textContent?.trim().slice(0, 80) ?? element.tagName),
        };
      });

      expect(layout.stylesheets.length, `${route.path} should load its CSS asset`).toBeGreaterThan(0);
      expect(layout.documentWidth, `${route.path} should not overflow at ${viewport.width}px`).toBeLessThanOrEqual(viewport.width);
      expect(layout.clippedText, `${route.path} should not clip visible text at ${viewport.width}px`).toEqual([]);
      if (layout.sidebar && layout.shell && viewport.width > 670) {
        expect(layout.shell.x, `${route.path} content should begin after the sidebar`).toBeGreaterThanOrEqual(layout.sidebar.right - 1);
      }
      if (layout.banner && layout.sidebar) {
        if (viewport.width > 670) {
          expect(layout.banner.x, "the public demo banner should clear the sidebar").toBeGreaterThanOrEqual(layout.sidebar.right - 1);
        } else {
          expect(layout.banner.bottom, "the mobile banner should remain above the bottom navigation").toBeLessThanOrEqual(layout.sidebar.y + 1);
        }
      }

      if (route.path === "/scenarios") {
        expect(layout.scenarioGrid?.display).toBe("grid");
        expect(layout.scenarioCards).toHaveLength(4);
        const columnCount = (layout.scenarioGrid?.display === "grid" ?
          await page.locator(".scenario-grid").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length) : 0);
        expect(columnCount, `scenario cards should use ${viewport.columns} columns at ${viewport.width}px`).toBe(viewport.columns);
        for (const card of layout.scenarioCards) {
          expect(card?.padding).not.toBe("0px");
          expect(card?.border).toContain("solid");
          expect(card?.background).not.toBe("rgba(0, 0, 0, 0)");
        }
        expect(layout.toolbar?.display).toBe("grid");
        await expect(page.locator("#scenario-region")).toBeVisible();
        await expect(page.locator("#scenario-budget")).toBeVisible();
        await expect(page.locator("#scenario-preset")).toBeVisible();
        await expect(page.getByRole("button", { name: "4안 비교 실행" })).toBeVisible();
      }

      if (route.path === "/evidence") {
        await expect(page.locator(".provenance-badge").first()).toBeVisible();
        expect(layout.provenance?.display).toBe("inline-flex");
        expect(layout.provenance?.border).toContain("solid");
      }

      if (screenshotRoutes.has(route.name)) {
        await mkdir(join(screenshotRoot, viewport.name), { recursive: true });
        await page.screenshot({ path: join(screenshotRoot, viewport.name, `${route.name}.png`), fullPage: true });
      }
    }

    for (const route of restrictedRoutes) {
      const response = await page.goto(route, { waitUntil: "domcontentloaded" });
      expect(response?.status(), `${route} should remain reachable to its demo guard`).toBe(200);
      await expect(page.getByLabel("공개 데모 경로 제한")).toBeVisible();
      await expect(page.locator("form")).toHaveCount(0);
      const dimensions = await page.evaluate(() => ({
        viewport: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
      }));
      expect(dimensions.documentWidth, `${route} should not overflow`).toBeLessThanOrEqual(dimensions.viewport);
    }
  }

  expect(cssFailures, "production CSS requests should succeed").toEqual([]);
  expect(staticAssetFailures, "production CSS and JavaScript assets should succeed").toEqual([]);
  expect(successfulStaticAssets.size, "the standalone server should return CSS/JavaScript assets").toBeGreaterThan(0);
  expect(apiRequestUrls.length, "the browser should make API requests through the app origin").toBeGreaterThan(0);
  expect(apiRequestUrls.every((url) => url.startsWith(`${webBaseUrl}/api/`))).toBeTruthy();
  const sessionCookie = (await page.context().cookies(`${webBaseUrl}/api`)).find((cookie) => cookie.name === "vc_demo_session");
  expect(sessionCookie, "the same-origin API should issue a demo session cookie").toMatchObject({
    httpOnly: true,
    path: "/api",
    sameSite: "Lax",
  });
  expect(consoleErrors, "browser and hydration errors should be absent").toEqual([]);
});

test("scenario comparison renders four computed policy results in production", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/scenarios", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#scenario-region option").first()).toBeAttached();
  await page.locator("#scenario-budget").fill("5000000");
  const runButton = page.getByRole("button", { name: "4안 비교 실행" });
  await runButton.click();
  await expect.poll(async () => {
    const cardCount = await page.locator(".scenario-grid .scenario-card .metric-list").count();
    if (cardCount === 4) return "4/4 cards";
    if (await page.locator(".api-error").count()) {
      return `API failure: ${(await page.locator(".api-error").innerText()).slice(0, 180)}`;
    }
    return `${cardCount}/4 cards pending`;
  }, { timeout: 210_000, message: "four computed policy cards should finish, or report the API error promptly" }).toBe("4/4 cards");
  await expect(page.getByRole("heading", { name: "차이 설명 (규칙 기반)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "공급자 불참 대비" })).toBeVisible();
  await expect(runButton).toBeEnabled();
  await expect(page.locator(".loading-line")).toHaveCount(0);
  await expect(page.locator(".api-error")).toHaveCount(0);
  expect(consoleErrors, "the scenario flow should not raise runtime or hydration errors").toEqual([]);

  const balancedCard = page.locator(".scenario-card").filter({ hasText: "균형" });
  const planHref = await balancedCard.getByRole("link", { name: "계획 상세·승인으로 이동" }).getAttribute("href");
  expect(planHref).toBeTruthy();

  await page.goto(planHref!, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "계획 검토와 승인 이력" })).toBeVisible();
  const [csvDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "회차 CSV" }).click(),
  ]);
  expect(csvDownload.suggestedFilename()).toMatch(/\.csv$/);
  const [pdfDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "검토보고서 PDF" }).click(),
  ]);
  expect(pdfDownload.suggestedFilename()).toMatch(/\.pdf$/);

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(planHref!, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "계획 검토와 승인 이력" })).toBeVisible();
    await expect(page.getByRole("link", { name: "인쇄용 검토보고서" })).toBeVisible();
    await expect(page.locator(".loading-line")).toHaveCount(0);
    await expect(page.locator(".api-error")).toHaveCount(0);
    const planLayout = await page.evaluate(() => ({
      viewport: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      clippedText: [...document.querySelectorAll("main h1, main h2, main p, main label, main button, main a[href]")]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0 && (rect.left < -1 || rect.right > innerWidth + 1);
        })
        .map((element) => element.textContent?.trim().slice(0, 80) ?? element.tagName),
    }));
    expect(planLayout.documentWidth, `Plans should not overflow at ${viewport.width}px`).toBeLessThanOrEqual(viewport.width);
    expect(planLayout.clippedText, `Plans should not clip text at ${viewport.width}px`).toEqual([]);
    await mkdir(join(screenshotRoot, viewport.name), { recursive: true });
    await page.screenshot({ path: join(screenshotRoot, viewport.name, "plans-with-generated-plan.png"), fullPage: true });

    const memoHref = await page.getByRole("link", { name: "인쇄용 검토보고서" }).getAttribute("href");
    expect(memoHref).toBeTruthy();
    const memoResponse = await page.goto(memoHref!, { waitUntil: "domcontentloaded" });
    expect(memoResponse?.status(), "Decision Memo should return HTML").toBe(200);
    await expect(page.getByRole("heading", { name: "의사결정 메모" })).toBeVisible();
    const memoLayout = await page.evaluate(() => ({
      viewport: innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      overflowingElements: [...document.querySelectorAll("body *")]
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return {
            tag: element.tagName.toLowerCase(),
            className: typeof element.className === "string" ? element.className : "",
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            width: Math.round(rect.width),
            scrollWidth: element.scrollWidth,
            clientWidth: element.clientWidth,
          };
        })
        .filter((element) => element.left < -1 || element.right > innerWidth + 1)
        .slice(0, 12),
      tables: [...document.querySelectorAll("table")].map((table) => {
        const rect = table.getBoundingClientRect();
        return {
          className: table.className,
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
          scrollWidth: table.scrollWidth,
          headers: [...table.querySelectorAll("thead th")].map((cell) => Math.round(cell.getBoundingClientRect().width)),
        };
      }),
      clippedText: [...document.querySelectorAll("h1, h2, p, th, td")]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width > 0 && rect.height > 0 &&
            (rect.left < -1 || rect.right > innerWidth + 1 ||
              ((style.overflowX === "hidden" || style.overflowX === "clip") && element.scrollWidth > element.clientWidth + 1));
        })
        .map((element) => element.textContent?.trim().slice(0, 80) ?? element.tagName),
    }));
    expect(
      memoLayout.documentWidth,
      `Decision Memo should not overflow at ${viewport.width}px; geometry=${JSON.stringify({
        overflowingElements: memoLayout.overflowingElements,
        tables: memoLayout.tables,
      })}`,
    ).toBeLessThanOrEqual(viewport.width);
    expect(memoLayout.clippedText, `Decision Memo should not clip text at ${viewport.width}px`).toEqual([]);
    await page.screenshot({ path: join(screenshotRoot, viewport.name, "decision-memo.png"), fullPage: true });
  }
});

test("scenario comparison preserves a created plan and blocks rerun after an ambiguous HTTP 520", async ({ page }) => {
  let schedulePosts = 0;
  await page.route("**/api/schedules", async (route) => {
    schedulePosts += 1;
    if (schedulePosts === 2) {
      await route.fulfill({
        status: 520,
        contentType: "text/html; charset=UTF-8",
        body: "<html><body>origin connection interrupted</body></html>",
      });
      return;
    }
    await route.continue();
  });

  await page.goto("/scenarios", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#scenario-region option").first()).toBeAttached();
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.locator(".api-error")).toContainText("응답이 끊겼습니다.");
  await expect(page.getByRole("status").filter({ hasText: "실패 단계: 균형 · 계획 생성" })).toContainText("생성 확인된 계획 1/4");
  await expect(page.locator(".scenario-grid .scenario-card .metric-list")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "계획 생성 여부 확인" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);
  expect(schedulePosts, "the failed POST must not be retried automatically").toBe(2);
});

test("minimum coverage analysis failure keeps all four computed policy plans visible", async ({ page }) => {
  let schedulePosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/schedules") {
      schedulePosts += 1;
    }
  });
  await page.route("**/api/minimum-coverage/analysis", (route) => route.fulfill({
    status: 520,
    contentType: "text/html; charset=UTF-8",
    body: "<html><body>origin connection interrupted</body></html>",
  }));

  await page.goto("/scenarios", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#scenario-region option").first()).toBeAttached();
  await page.locator("#scenario-budget").fill("5000000");
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect.poll(async () => {
    if (await page.locator(".scenario-grid .scenario-card .metric-list").count() === 4) return "4/4 plans";
    if (await page.locator(".api-error").count()) return "error before four plans";
    return "calculating";
  }, { timeout: 210_000 }).toBe("4/4 plans");
  await expect(page.locator(".api-error")).toContainText("응답이 끊겼습니다.");
  await expect(page.getByRole("status").filter({ hasText: "실패 단계: 최소보장 비용 분석" })).toContainText("생성 확인된 계획 4/4");
  await expect(page.locator(".scenario-grid .scenario-card .metric-list")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toHaveCount(0);
  expect(schedulePosts, "the optional analysis failure follows exactly four policy plan writes").toBe(4);
});
