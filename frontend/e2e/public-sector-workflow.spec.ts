import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const REGION_ID = "pilot:홍성군 장곡면";

function seoulToday() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const date = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${date.year}-${date.month}-${date.day}`;
}

test("public planner reviews evidence, compares plans, handles decline, approves and exports", async ({
  page,
  request,
}, testInfo) => {
  const screenshot = (name: string) =>
    page.screenshot({ path: testInfo.outputPath(name), fullPage: true });

  const areasResponse = await request.get(`${API}/api/areas`, { params: { region_id: REGION_ID } });
  expect(areasResponse.ok()).toBeTruthy();
  const { areas } = await areasResponse.json();
  const areaId = areas[0].area_id as string;

  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
  await screenshot("dashboard.png");

  await page.goto(`/villages/${encodeURIComponent(areaId)}`);
  await expect(page.getByRole("heading", { name: "기초조사 등록" })).toBeVisible();
  await screenshot("village-and-survey-form.png");
  await page.getByLabel("조사 방식").selectOption("phone");
  await page.getByLabel("조사일").fill(seoulToday());
  await page.getByLabel("서비스 유형").selectOption("laundry");
  await page.getByLabel("월 희망 횟수").fill("2");
  await page.getByRole("button", { name: "조사 기록 저장" }).click();
  await expect(page.getByText(/저장 완료 ·/)).toBeVisible();
  await screenshot("survey-saved.png");

  await page.goto("/scenarios");
  await page.getByLabel("지역").selectOption(REGION_ID);
  await page.getByLabel("월 예산 (원)").fill("4000000");
  await page.getByRole("button", { name: "3안 비교 실행" }).click();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible({ timeout: 180_000 });
  await expect(page.locator(".scenario-card")).toHaveCount(3);
  await screenshot("scenario-comparison.png");

  const balancedCard = page.locator(".scenario-card").filter({ hasText: "균형" });
  const planHref = await balancedCard.getByRole("link", { name: "계획 상세·승인으로 이동" }).getAttribute("href");
  expect(planHref).toBeTruthy();
  const scheduleId = new URL(planHref!, "http://127.0.0.1:3010").searchParams.get("id");
  expect(scheduleId).toBeTruthy();

  const initialPlanResponse = await request.get(`${API}/api/schedules/${scheduleId}`);
  expect(initialPlanResponse.ok()).toBeTruthy();
  const initialPlan = await initialPlanResponse.json();
  const firstRound = initialPlan.rounds[0];
  expect(firstRound).toBeTruthy();

  await page.goto(`/providers/${encodeURIComponent(firstRound.provider_id)}`);
  await expect(page.getByRole("heading", { name: "참여 가능한 회차" })).toBeVisible();
  await screenshot("provider-participation.png");

  await page.goto(planHref!);
  await expect(page.getByRole("heading", { name: "계획 v1" })).toBeVisible();
  await page.getByRole("button", { name: "검토 요청" }).click();
  await expect(page.getByText("검토 중", { exact: true }).first()).toBeVisible();
  await page.getByLabel("시연 역할").selectOption("REVIEWER");
  await page.getByRole("button", { name: "검토 승인" }).click();
  await expect(page.getByText("승인됨", { exact: true }).first()).toBeVisible();

  const decline = await request.post(
    `${API}/api/providers/${encodeURIComponent(firstRound.provider_id)}/rounds/${encodeURIComponent(firstRound.service_round_id)}/participation`,
    { data: { status: "DECLINED" } },
  );
  expect(decline.ok()).toBeTruthy();

  await page.reload();
  const replanButton = page.getByRole("button", { name: /불참 1건 반영해 새 버전/ });
  await expect(replanButton).toBeVisible();
  await replanButton.click();
  await expect(page.getByRole("heading", { name: "계획 v2" })).toBeVisible({ timeout: 60_000 });
  await screenshot("plan-replanned.png");

  await page.getByRole("button", { name: "검토 요청" }).click();
  await expect(page.getByText("검토 중", { exact: true }).first()).toBeVisible();
  await page.getByLabel("시연 역할").selectOption("REVIEWER");
  await page.getByRole("button", { name: "검토 승인" }).click();
  await expect(page.locator(".plan-version-list").getByRole("button", { name: /v1.*대체됨/ })).toBeVisible();
  await expect(page.getByText("승인됨", { exact: true }).first()).toBeVisible();
  await screenshot("plan-approved-and-versioned.png");

  const [pdf] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "계획 요약 PDF" }).click(),
  ]);
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  await pdf.saveAs(testInfo.outputPath("plan-summary.pdf"));

  const [budgetCsv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "예산 CSV" }).click(),
  ]);
  expect(budgetCsv.suggestedFilename()).toMatch(/\.csv$/);
  await budgetCsv.saveAs(testInfo.outputPath("budget-breakdown.csv"));

  const currentPlanId = new URL(page.url()).searchParams.get("id");
  await page.goto(`/calendar?schedule_id=${encodeURIComponent(currentPlanId ?? "")}`);
  await expect(page.getByRole("heading", { name: /예산과 기준을 정해/ })).toBeVisible();
  await expect(page.getByText(/계획 v2/).first()).toBeVisible();
  await screenshot("schedule.png");

  await page.goto("/evidence");
  await expect(page.getByRole("heading", { name: /어떤 숫자가 실제이고/ })).toBeVisible();
  await expect(page.getByText("한국농촌경제연구원").first()).toBeVisible();
  await screenshot("data-sources.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/plans?id=${encodeURIComponent(currentPlanId ?? "")}`);
  await expect(page.getByRole("heading", { name: "계획 검토와 승인 이력" })).toBeVisible();
  await screenshot("plan-review-mobile.png");
});
