import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";

const repoRoot = resolve(process.cwd(), "..");
const screenshotRoot = join(repoRoot, "artifacts", "ui_regression", "after");
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
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("response", (response) => {
    if (response.request().resourceType() === "stylesheet" && response.status() >= 400) {
      cssFailures.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    if (request.resourceType() === "stylesheet") {
      cssFailures.push(`${request.failure()?.errorText ?? "request failed"} ${request.url()}`);
    }
  });

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const route of publicRoutes) {
      const response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
      expect(response?.status(), `${route.path} should return a page`).toBe(200);
      await expect(page.locator("main h1").first(), `${route.path} should expose its page heading`).toBeVisible();

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

      if (route.path === "/" || route.path === "/scenarios") {
        const size = viewport.name === "desktop" ? "desktop" : viewport.name === "mobile" ? "mobile" : null;
        if (size) {
          await mkdir(join(screenshotRoot, size), { recursive: true });
          await page.screenshot({ path: join(screenshotRoot, size, `${route.name}.png`), fullPage: true });
        }
      }
      if (route.path !== "/" && route.path !== "/scenarios") {
        const size = viewport.name === "desktop" ? "desktop" : viewport.name === "mobile" ? "mobile" : null;
        if (size) {
          await mkdir(join(screenshotRoot, size), { recursive: true });
          await page.screenshot({ path: join(screenshotRoot, size, `${route.name}.png`), fullPage: true });
        }
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
  const runButton = page.getByRole("button", { name: "4안 비교 실행" });
  await runButton.click();
  await expect(page.locator(".scenario-grid .scenario-card .metric-list")).toHaveCount(4, { timeout: 210_000 });
  await expect(page.getByRole("heading", { name: "차이 설명 (규칙 기반)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "공급자 불참 대비" })).toBeVisible();
  await expect(runButton).toBeEnabled();
  expect(consoleErrors, "the scenario flow should not raise runtime or hydration errors").toEqual([]);
});
