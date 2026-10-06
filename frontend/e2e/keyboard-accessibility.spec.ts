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
    "/demand",
    `/villages/${encodeURIComponent(areas[0].area_id as string)}`,
    "/scenarios",
    "/calendar",
    "/plans",
    "/pilot-setup",
    "/pilot-imports",
    "/data-quality",
    "/providers",
    "/evidence",
  ];

  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator("main")).toBeVisible();
    if (route === "/") {
      await expect(page.getByRole("heading", { name: "어떤 기준으로 나눌까요?" })).toBeVisible({
        timeout: 120_000,
      });
    } else if (route === "/pilot-setup") {
      await expect(page.getByRole("heading", { name: "초기 설정 업무 흐름" })).toBeVisible();
      await expect(page.getByLabel("지역", { exact: true })).toBeVisible();
    } else if (route === "/pilot-imports") {
      await expect(page.getByRole("heading", { name: "자료를 검토한 뒤 가져옵니다" })).toBeVisible();
    } else if (route === "/demand") {
      await expect(page.getByRole("heading", { name: "조사 기록을 검토하고 근거로 승인" })).toBeVisible();
      await expect.poll(() => page.getByLabel("서비스 권역").locator("option").count()).toBeGreaterThan(1);
      await page.waitForLoadState("networkidle");
    } else if (route === "/data-quality") {
      await expect(page.getByRole("heading", { name: "무슨 데이터로 계산했는지 공개합니다" })).toBeVisible();
      await expect(page.getByRole("link", { name: "공급자 매핑·중복 검토" })).toBeVisible();
    } else if (route === "/providers") {
      await expect(page.getByRole("heading", { name: /공급자 참여/ })).toBeVisible();
      await expect(page.getByRole("link", { name: "행정안전부 전국 마을기업 현황" })).toBeVisible();
    } else if (route === "/calendar") {
      await expect(page.getByRole("heading", { name: /실제 회차 일정으로 확인합니다/ })).toBeVisible();
    } else if (route === "/plans") {
      await expect(page.getByRole("heading", { name: "계획 검토와 승인 이력" })).toBeVisible();
    } else if (route === "/evidence") {
      await expect(page.getByRole("heading", { name: "어떤 숫자가 실제이고, 무엇이 참고·모의인가" })).toBeVisible();
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
    let repeatedFocusCount = 0;

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
      if (state.index === previousIndex) {
        // Chromium exposes date input segments as internal Tab stops while the
        // owning input remains document.activeElement.
        repeatedFocusCount += 1;
        expect(repeatedFocusCount, `keyboard did not leave ${route} focus target`).toBeLessThanOrEqual(10);
        continue;
      }
      repeatedFocusCount = 0;
      expect(state.index, `tab order on ${route}: ${JSON.stringify(state.labels.slice(previousIndex + 1, state.index + 1))}`).toBe(previousIndex + 1);
      expect(state.visible).toBeTruthy();
      expect(state.focusVisible).toBeTruthy();
      expect(state.outlineWidth).toBeGreaterThanOrEqual(2);
      previousIndex = state.index;
      visited += 1;
    }

    const finalFocusableCount = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) =>
      items.filter((item) => {
        const style = getComputedStyle(item);
        const rect = item.getBoundingClientRect();
        const closedDetails = item.closest("details:not([open])");
        const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0 && (!closedDetails || visibleSummary);
      }).length,
    );
    expect(visited, `keyboard focusables visited on ${route}`).toBe(finalFocusableCount);

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
