import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const routes = [
  "/pilot-setup",
  "/pilot-imports",
  "/providers",
  "/feedback",
  "/scenarios",
  "/calendar",
  "/plans",
  "/data-quality",
  "/evidence",
];

async function workflowRoutes(request: APIRequestContext) {
  const response = await request.get(`${API}/api/areas`, {
    params: { region_id: "pilot:홍성군 장곡면" },
  });
  expect(response.ok()).toBeTruthy();
  const { areas } = await response.json();
  expect(areas.length).toBeGreaterThan(0);
  return [...routes, `/villages/${encodeURIComponent(areas[0].area_id as string)}`];
}

test("pilot workflow pages expose readable landmarks, labels and data tables", async ({ page, request }) => {
  for (const route of await workflowRoutes(request)) {
    await page.goto(route);
    const main = page.locator("main");
    await expect(main, `main landmark on ${route}`).toBeVisible();
    await expect(main.getByRole("heading", { level: 1 }), `page heading on ${route}`).toHaveCount(1);
    const issues = await main.evaluate((root) => {
      const unlabeledControls = [...root.querySelectorAll<HTMLElement>(
        "input:not([type=hidden]), select, textarea, button",
      )].filter((element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        if (style.display === "none" || style.visibility === "hidden" || rect.width === 0 || rect.height === 0) {
          return false;
        }
        const labelled = Boolean(
          element.getAttribute("aria-label")?.trim()
          || element.getAttribute("aria-labelledby")?.trim()
          || element.closest("label")?.textContent?.trim()
          || (element instanceof HTMLInputElement && element.labels?.length)
          || (element instanceof HTMLSelectElement && element.labels?.length)
          || (element instanceof HTMLTextAreaElement && element.labels?.length)
          || element.textContent?.trim(),
        );
        return !labelled;
      }).map((element) => `${element.tagName.toLowerCase()}#${element.id}`);
      const tablesWithoutHeaders = [...root.querySelectorAll("table")]
        .filter((table) => table.querySelectorAll("thead th").length === 0)
        .map((table) => table.getAttribute("aria-label") ?? table.querySelector("caption")?.textContent ?? "unnamed table");
      return { unlabeledControls, tablesWithoutHeaders };
    });
    expect(issues.unlabeledControls, `named controls on ${route}`).toEqual([]);
    expect(issues.tablesWithoutHeaders, `table headers on ${route}`).toEqual([]);
  }
});

test("pilot workflow pages fit the target mobile, tablet and desktop viewports", async ({ page, request }) => {
  const viewports = [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ];
  for (const route of await workflowRoutes(request)) {
    await page.goto(route);
    for (const viewport of viewports) {
      const { width, height } = viewport;
      await page.setViewportSize(viewport);
      await expect(page.locator("main"), `main at ${width}x${height} on ${route}`).toBeVisible();
      const layout = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        content: document.documentElement.scrollWidth,
      }));
      expect(layout.content, `horizontal overflow at ${width}x${height} on ${route}`).toBeLessThanOrEqual(layout.viewport);
    }
  }
});
