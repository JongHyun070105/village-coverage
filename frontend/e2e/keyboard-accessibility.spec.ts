import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const REGION_ID = "pilot:홍성군 장곡면";
const FOCUSABLE_IN_MAIN =
  "main a[href], main button:not(:disabled), main input:not(:disabled), main select:not(:disabled), main textarea:not(:disabled), main summary, main [tabindex]:not([tabindex='-1'])";

test("keyboard navigation keeps visible focus on intake, area detail and policy comparison", async ({
  page,
  request,
}) => {
  const areasResponse = await request.get(`${API}/api/areas`, { params: { region_id: REGION_ID } });
  expect(areasResponse.ok()).toBeTruthy();
  const { areas } = await areasResponse.json();
  const routes = [
    "/",
    "/feedback",
    `/villages/${encodeURIComponent(areas[0].area_id as string)}`,
    "/scenarios",
  ];

  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator("main")).toBeVisible();
    if (route === "/") {
      await expect(page.getByRole("heading", { name: "어떤 기준으로 나눌까요?" })).toBeVisible({
        timeout: 120_000,
      });
    }
    const focusableCount = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) =>
      items.filter((item) => {
        const style = getComputedStyle(item);
        const rect = item.getBoundingClientRect();
        const closedDetails = item.closest("details:not([open])");
        const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0 && (!closedDetails || visibleSummary);
      }).length,
    );
    let visited = 0;
    let previousIndex = -1;

    for (let step = 0; step < focusableCount + 30; step += 1) {
      await page.keyboard.press("Tab");
      const state = await page.evaluate((selector) => {
        const items = [...document.querySelectorAll<HTMLElement>(selector)].filter((item) => {
          const style = getComputedStyle(item);
          const rect = item.getBoundingClientRect();
          const closedDetails = item.closest("details:not([open])");
          const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
          return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0 && (!closedDetails || visibleSummary);
        });
        const active = document.activeElement as HTMLElement | null;
        return {
          index: active ? items.indexOf(active) : -1,
          visible: Boolean(active && active.getBoundingClientRect().width > 0 && active.getBoundingClientRect().height > 0),
          focusVisible: Boolean(active?.matches(":focus-visible")),
          outlineWidth: active ? Number.parseFloat(getComputedStyle(active).outlineWidth) : 0,
          labels: items.map((item) => `${item.tagName.toLowerCase()}#${item.id}:${item.getAttribute("aria-label") ?? item.textContent?.trim().slice(0, 24) ?? ""}`),
        };
      }, FOCUSABLE_IN_MAIN);

      if (state.index < 0) {
        if (visited > 0) break;
        continue;
      }
      expect(state.index, `tab order on ${route}: ${JSON.stringify(state.labels.slice(previousIndex + 1, state.index + 1))}`).toBe(previousIndex + 1);
      expect(state.visible).toBeTruthy();
      expect(state.focusVisible).toBeTruthy();
      expect(state.outlineWidth).toBeGreaterThanOrEqual(2);
      previousIndex = state.index;
      visited += 1;
    }

    expect(visited, `keyboard focusables visited on ${route}`).toBe(focusableCount);

    if (route === "/") {
      const mapTable = page.getByText("마을별 배정 표로 보기", { exact: true });
      await mapTable.focus();
      await expect(mapTable).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("table", { name: "지도 대체 마을별 서비스 배정" })).toBeVisible();
      const visibleAfterSummary = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) =>
        items.filter((item) => {
          const style = getComputedStyle(item);
          const rect = item.getBoundingClientRect();
          const closedDetails = item.closest("details:not([open])");
          const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
          return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0 && (!closedDetails || visibleSummary);
        }).length,
      );
      const summaryIndex = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) =>
        items.findIndex((item) => item === document.activeElement),
      );
      let lastIndex = summaryIndex;
      let tableLinks = 0;
      for (let step = 0; step < visibleAfterSummary + 30; step += 1) {
        await page.keyboard.press("Tab");
        const state = await page.evaluate((selector) => {
          const items = [...document.querySelectorAll<HTMLElement>(selector)].filter((item) => {
            const style = getComputedStyle(item);
            const rect = item.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
          });
          const active = document.activeElement as HTMLElement | null;
          return {
            index: active ? items.indexOf(active) : -1,
            focusVisible: Boolean(active?.matches(":focus-visible")),
            inAlternativeTable: Boolean(active?.closest(".map-area-alternative table")),
            outlineWidth: active ? Number.parseFloat(getComputedStyle(active).outlineWidth) : 0,
          };
        }, FOCUSABLE_IN_MAIN);
        if (state.index < 0) break;
        expect(state.index).toBe(lastIndex + 1);
        expect(state.focusVisible).toBeTruthy();
        expect(state.outlineWidth).toBeGreaterThanOrEqual(2);
        if (state.inAlternativeTable) tableLinks += 1;
        lastIndex = state.index;
      }
      expect(tableLinks, "the map alternative table's area links are keyboard reachable").toBeGreaterThan(0);
    }
  }
});
