import { expect, test, type Page } from "@playwright/test";

const writeGuardKey = "vc:provider-scenario-write-guard";

async function openProviderScenarioComparison(page: Page) {
  await expect(page.getByRole("button", { name: "4안 나란히 비교" })).toBeVisible();
  await page.getByRole("button", { name: "4안 나란히 비교" }).click();
  const runButton = page.getByRole("button", { name: "공급 일정 4안 생성" });
  await expect(runButton).toBeVisible();
  return runButton;
}

function collectHydrationErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /hydration|hydrated|server rendered|client rendered/i.test(message.text())) {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    if (/hydration|hydrated/i.test(error.message)) errors.push(error.message);
  });
  return errors;
}

test("first visit renders and hydrates without a stored write guard", async ({ page }) => {
  const hydrationErrors = collectHydrationErrors(page);
  await page.addInitScript((key) => window.sessionStorage.removeItem(key), writeGuardKey);

  await page.goto("/");
  const runButton = await openProviderScenarioComparison(page);
  await expect(runButton).toBeEnabled();
  expect(hydrationErrors).toEqual([]);
});

for (const [storedGuard, expectedMessage] of [
  ["ambiguous-write", "계획 요청이 서버에 도달했을 수 있어 저장 여부를 단정할 수 없습니다."],
  ["plans-created", "일부 계획이 저장되었습니다."],
] as const) {
  test(`restores ${storedGuard} after refresh and navigation without hydration errors`, async ({ page }) => {
    const hydrationErrors = collectHydrationErrors(page);
    let planPosts = 0;
    page.on("request", (request) => {
      if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/api/schedules")) {
        planPosts += 1;
      }
    });
    await page.addInitScript(({ key, value }) => window.sessionStorage.setItem(key, value), {
      key: writeGuardKey,
      value: storedGuard,
    });

    await page.goto("/");
    let runButton = await openProviderScenarioComparison(page);
    await expect(runButton).toBeDisabled();
    await expect(page.locator(".provider-scenario-write-guard")).toContainText(expectedMessage);
    await expect(page.getByRole("link", { name: "계획 목록 확인" })).toBeVisible();

    const regionSelect = page.getByRole("combobox", { name: "읍면 선택" });
    const regionOptions = await regionSelect.locator("option").count();
    if (regionOptions > 1) {
      await regionSelect.selectOption({ index: 1 });
      await expect(runButton).toBeDisabled();
    }

    await page.reload();
    runButton = await openProviderScenarioComparison(page);
    await expect(runButton).toBeDisabled();
    await expect(page.locator(".provider-scenario-write-guard")).toContainText(expectedMessage);

    await page.getByRole("link", { name: "계획 목록 확인" }).click();
    await expect(page).toHaveURL(/\/plans$/);
    await page.goBack();
    runButton = await openProviderScenarioComparison(page);
    await expect(runButton).toBeDisabled();

    const popupPromise = page.waitForEvent("popup");
    await page.evaluate(() => window.open(`${window.location.origin}/`, "_blank"));
    const popup = await popupPromise;
    await popup.waitForLoadState("domcontentloaded");
    runButton = await openProviderScenarioComparison(popup);
    await expect(runButton).toBeDisabled();

    expect(planPosts).toBe(0);
    expect(hydrationErrors).toEqual([]);
  });
}

test("blocks provider scenario writes when sessionStorage cannot be read", async ({ page }) => {
  let planPosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/api/schedules")) {
      planPosts += 1;
    }
  });
  await page.addInitScript((key) => {
    const originalGet = Storage.prototype.getItem;
    const originalSet = Storage.prototype.setItem;
    const originalRemove = Storage.prototype.removeItem;
    Storage.prototype.getItem = function (name) {
      if (name === key || name === `${key}:probe`) throw new DOMException("blocked", "SecurityError");
      return originalGet.call(this, name);
    };
    Storage.prototype.setItem = function (name, value) {
      if (name === key || name === `${key}:probe`) throw new DOMException("blocked", "SecurityError");
      return originalSet.call(this, name, value);
    };
    Storage.prototype.removeItem = function (name) {
      if (name === key || name === `${key}:probe`) throw new DOMException("blocked", "SecurityError");
      return originalRemove.call(this, name);
    };
  }, writeGuardKey);

  await page.goto("/");
  const runButton = await openProviderScenarioComparison(page);
  await expect(runButton).toBeDisabled();
  await expect(page.locator(".provider-scenario-write-guard")).toContainText("브라우저 저장소");
  await page.evaluate(() => {
    document.querySelector<HTMLButtonElement>(".provider-scenario-compare button.button-dark")?.dispatchEvent(
      new MouseEvent("click", { bubbles: true }),
    );
  });
  await page.waitForTimeout(100);
  expect(planPosts).toBe(0);
});
