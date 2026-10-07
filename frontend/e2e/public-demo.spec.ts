import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8010";

test("public demo keeps core flows inside the synthetic sandbox", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByLabel("공개 데모 안내")).toContainText("합성/공개 데이터");
  await expect(page.getByLabel("공개 데모 안내")).toContainText("실제 주민·공급자 운영정보");
  await expect(page.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible();
  await expect(page.locator(".map-canvas")).toBeVisible();
  await expect(page.getByRole("link", { name: "주민 의견·정정" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "파일럿 자료 검토" })).toHaveCount(0);

  const areaHref = await page.locator('a[href^="/villages/"]').first().getAttribute("href");
  expect(areaHref).toBeTruthy();
  await page.goto(areaHref!);
  await expect(page.getByRole("heading", { name: "공개 인구 자료" })).toBeVisible();
  await expect(page.getByText("MODEL ESTIMATE", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "기초조사 등록" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "주민 의견" })).toHaveCount(0);

  for (const privatePath of ["/feedback", "/pilot-imports", "/demand", "/imports"]) {
    await page.goto(privatePath);
    await expect(page.getByLabel("공개 데모 경로 제한")).toBeVisible();
    await expect(page.locator("form")).toHaveCount(0);
  }

  const blockedContact = await request.get(
    `${API}/api/feedback/private-id/contact?role=PLANNER`,
  );
  expect(blockedContact.status()).toBe(404);
  expect((await blockedContact.json()).code).toBe("DEMO_MODE_RESTRICTED");
  const blockedImport = await request.post(`${API}/api/pilot-imports/provider_capacity/preview`);
  expect(blockedImport.status()).toBe(404);
  const blockedRevision = await request.post(`${API}/api/schedules/private-id/revision`, {
    data: { scenario: "efficiency", budget_won: 4_000_000 },
  });
  expect(blockedRevision.status()).toBe(404);
  expect((await request.get(`${API}/openapi.json`)).status()).toBe(404);

  await page.goto("/scenarios");
  const compareButton = page.locator('.toolbar-form button[type="submit"]');
  await compareButton.click();
  await expect(compareButton).toBeEnabled({
    timeout: 240_000,
  });
  await expect(page.locator(".scenario-grid article")).toHaveCount(4);
  await expect(page.locator(".scenario-card .empty-line")).toHaveCount(0);

  const createdResponse = await request.post(`${API}/api/schedules`, {
    data: {
      scenario: "balanced",
      budget_won: 4_000_000,
      region_id: "pilot:홍성군 장곡면",
    },
  });
  expect(createdResponse.status()).toBe(201);
  const initialPlan = await createdResponse.json();
  expect(initialPlan.rounds.length).toBeGreaterThan(0);
  const firstRound = initialPlan.rounds[0];

  await page.goto(`/providers/${encodeURIComponent(firstRound.provider_id)}`);
  const roundCard = page.locator(`[data-demo-round-id="${firstRound.service_round_id}"]`);
  await expect(page.getByRole("heading", { name: "참여 가능한 회차" })).toBeVisible();
  await expect(roundCard).toBeVisible();
  await roundCard.getByRole("button", { name: "데모 불참" }).click();
  await expect(roundCard.getByText("이번 회차 불참")).toBeVisible();

  await page.goto(`/plans?id=${encodeURIComponent(initialPlan.schedule_id)}`);
  await expect(page.getByRole("heading", { name: "계획 v1" })).toBeVisible();
  await page.getByRole("button", { name: "검토 요청" }).click();
  await page.getByLabel("시연 역할").selectOption("REVIEWER");
  const demoApproveButton = page.getByRole("button", { name: "데모 승인" });
  await expect(demoApproveButton).toBeEnabled();
  await demoApproveButton.click();
  await expect(page.getByText("데모 승인됨", { exact: true }).first()).toBeVisible();

  await page.reload();
  const replan = page.getByRole("button", { name: /불참 1건 반영해 새 버전/ });
  await expect(replan).toBeVisible();
  await replan.click();
  await expect(page.getByRole("heading", { name: "계획 v2" })).toBeVisible({
    timeout: 120_000,
  });

  const memoResponse = await request.get(
    `${API}/api/schedules/${encodeURIComponent(initialPlan.schedule_id)}/decision-memo`,
  );
  expect(memoResponse.status()).toBe(200);
  expect(await memoResponse.text()).toMatch(/SIMULATED|시뮬레이션|모의/);

  await page.goto("/evidence");
  await expect(
    page.getByRole("heading", { name: "어떤 숫자가 실제이고, 무엇이 참고·모의인가" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "데이터 출처별 구분, 기준일, 범위, 사용목적과 한계" }),
  ).toBeVisible();
});

test("public demo dashboard fits a phone-sized viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("공개 데모 안내")).toBeVisible();
  await expect(page.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    bodyWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
});
