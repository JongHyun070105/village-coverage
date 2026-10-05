import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const REGION_ID = "pilot:홍성군 장곡면";
const FOCUSABLE_IN_MAIN =
  "main a[href], main button:not(:disabled), main input:not(:disabled), main select:not(:disabled), main textarea:not(:disabled), main summary, main [tabindex]:not([tabindex='-1'])";

async function auditPlanTabOrder(page: Page) {
  const count = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) =>
    items.filter((item) => {
      const style = getComputedStyle(item);
      const rect = item.getBoundingClientRect();
      const closedDetails = item.closest("details:not([open])");
      const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
      return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 &&
        rect.height > 0 && (!closedDetails || visibleSummary);
    }).length,
  );
  let previousIndex = -1;
  let visited = 0;
  for (let step = 0; step < count + 30; step += 1) {
    await page.keyboard.press("Tab");
    const state = await page.locator(FOCUSABLE_IN_MAIN).evaluateAll((items) => {
      const focusable = items.filter((item) => {
        const style = getComputedStyle(item);
        const rect = item.getBoundingClientRect();
        const closedDetails = item.closest("details:not([open])");
        const visibleSummary = closedDetails?.querySelector(":scope > summary") === item;
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 &&
          rect.height > 0 && (!closedDetails || visibleSummary);
      });
      const active = document.activeElement as HTMLElement | null;
      return {
        index: active ? focusable.indexOf(active) : -1,
        focusVisible: Boolean(active?.matches(":focus-visible")),
        outlineWidth: active ? Number.parseFloat(getComputedStyle(active).outlineWidth) : 0,
      };
    });
    if (state.index < 0) {
      if (visited > 0) break;
      continue;
    }
    expect(state.index, "plan page Tab order").toBe(previousIndex + 1);
    expect(state.focusVisible, "plan page focus indicator").toBeTruthy();
    expect(state.outlineWidth, "plan page focus outline width").toBeGreaterThanOrEqual(2);
    previousIndex = state.index;
    visited += 1;
  }
  expect(visited).toBe(count);
  await expect(page.getByRole("link", { name: "검토보고서 PDF" })).toBeVisible();
}

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
  await page.getByText("마을별 배정 표로 보기", { exact: true }).click();
  await expect(page.getByRole("table", { name: "지도 대체 마을별 서비스 배정" })).toBeVisible();
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

  await page.goto("/feedback");
  const feedbackForm = page.locator(".feedback-form");
  await feedbackForm.getByLabel("생활권").selectOption(areaId);
  await feedbackForm.getByLabel("의견 유형").selectOption("SERVICE_REQUEST");
  await feedbackForm.getByLabel("관련 서비스", { exact: true }).selectOption("laundry");
  await feedbackForm.getByLabel("주장하는 월 희망 횟수 (선택)").fill("4");
  await feedbackForm.getByLabel("의견 내용").fill("세탁 서비스가 더 자주 필요하다는 주민 의견");
  await feedbackForm.getByRole("button", { name: "접수" }).click();
  await expect(page.getByText(/접수했습니다\. 검토 전까지 수요·계획에 반영되지 않습니다\./)).toBeVisible();
  await expect(page.getByRole("heading", { name: "공식 근거와의 충돌" })).toBeVisible();
  await page.getByRole("button", { name: "검토 시작" }).click();
  await expect(
    page.locator('section[aria-labelledby="feedback-detail-title"] .feedback-note'),
  ).toContainText("검토 중");
  await page.getByLabel("처리 메모 (반려·추가 확인·채택·충돌 해결 시 필수)").fill("주민 주장과 공식 조사 차이를 추가 확인");
  await page.getByRole("button", { name: "추가 조사" }).click();
  await expect(page.getByText(/해결됨\(FURTHER_SURVEY\)/)).toBeVisible();

  await page.goto(`/villages/${encodeURIComponent(areaId)}`);
  await page.getByLabel("조사 방식").selectOption("phone");
  await page.getByLabel("조사일").fill(seoulToday());
  await page.getByLabel("서비스 유형").selectOption("home_repair");
  await page.getByLabel("월 희망 횟수").fill("1");
  await page.getByRole("button", { name: "조사 기록 저장" }).click();
  await expect(page.getByText(/저장 완료 ·/)).toBeVisible();
  await expect(page.getByLabel("서비스 유형")).toHaveValue("home_repair");

  await page.goto("/feedback");
  const homeRepairFeedbackForm = page.locator(".feedback-form");
  await homeRepairFeedbackForm.getByLabel("생활권").selectOption(areaId);
  await homeRepairFeedbackForm.getByLabel("의견 유형").selectOption("SERVICE_REQUEST");
  await homeRepairFeedbackForm.getByLabel("관련 서비스", { exact: true }).selectOption("home_repair");
  await homeRepairFeedbackForm.getByLabel("주장하는 월 희망 횟수 (선택)").fill("1");
  await homeRepairFeedbackForm.getByLabel("의견 내용").fill("문 손잡이 안전 보수가 필요하다는 주민 의견");
  await homeRepairFeedbackForm.getByRole("button", { name: "접수" }).click();
  await expect(page.getByText(/접수했습니다\. 검토 전까지 수요·계획에 반영되지 않습니다\./)).toBeVisible();
  await page.getByRole("button", { name: "검토 시작" }).click();
  await expect(
    page.locator('section[aria-labelledby="feedback-detail-title"] .feedback-note'),
  ).toContainText("검토 중");
  await page.getByLabel("처리 메모 (반려·추가 확인·채택·충돌 해결 시 필수)").fill("담당자가 확인할 주민 주장 근거");
  await page.getByRole("button", { name: "근거로 채택\(검증 전\)" }).click();
  await expect(
    page.locator('section[aria-labelledby="feedback-detail-title"] .feedback-note'),
  ).toContainText("근거로 채택(검증 전)");
  await screenshot("resident-feedback-reviewed.png");

  await page.goto("/scenarios");
  await page.getByLabel("지역", { exact: true }).selectOption(REGION_ID);
  await page.getByLabel("월 예산 (원)").fill("4000000");
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible({ timeout: 180_000 });
  await expect(page.locator(".scenario-card")).toHaveCount(4);
  await page.getByRole("button", { name: "비교 계산" }).click();
  await expect(page.getByRole("table", { name: "정책별 소외 최소화 시뮬레이션 비교" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "2순위·3순위 후보 계산" }).click();
  await expect(page.getByRole("table", { name: "회차별 공급자 대체 후보" })).toBeVisible({ timeout: 120_000 });
  await page.getByLabel("예비 비율").selectOption("10");
  await page.getByRole("button", { name: "예비 정책 비교" }).click();
  await expect(page.getByRole("table", { name: "공급자 불참 시 예비 정책 비교" })).toBeVisible({ timeout: 120_000 });
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
  await page.getByLabel("수정 요청 사유").fill("추가 재원 범위를 다시 확인");
  await page.getByRole("button", { name: "수정 요청", exact: true }).click();
  await expect(page.getByText("수정 요청", { exact: true }).first()).toBeVisible();
  await page.getByLabel("시연 역할").selectOption("PLANNER");
  await page.getByLabel("수정 후 예산 (원)").fill("3900000");
  await page.getByRole("button", { name: "수정 반영해 새 버전 생성" }).click();
  await expect(page.getByRole("heading", { name: "계획 v3" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "검토 요청" }).click();
  await expect(page.getByText("검토 중", { exact: true }).first()).toBeVisible();
  await page.getByLabel("시연 역할").selectOption("REVIEWER");
  await page.getByRole("button", { name: "검토 승인" }).click();
  await expect(page.locator(".plan-version-list").getByRole("button", { name: /v2.*수정 요청/ })).toBeVisible();
  await expect(page.getByText("승인됨", { exact: true }).first()).toBeVisible();
  await screenshot("plan-approved-and-versioned.png");

  const [pdf] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "계획 요약 PDF" }).click(),
  ]);
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/);
  await pdf.saveAs(testInfo.outputPath("plan-summary.pdf"));

  const [memoPdf] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "검토보고서 PDF" }).click(),
  ]);
  expect(memoPdf.suggestedFilename()).toMatch(/\.pdf$/);
  await memoPdf.saveAs(testInfo.outputPath("decision-memo.pdf"));

  const [budgetCsv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "예산 CSV" }).click(),
  ]);
  expect(budgetCsv.suggestedFilename()).toMatch(/\.csv$/);
  await budgetCsv.saveAs(testInfo.outputPath("budget-breakdown.csv"));

  const currentPlanId = new URL(page.url()).searchParams.get("id");
  await page.goto(`/calendar?schedule_id=${encodeURIComponent(currentPlanId ?? "")}`);
  await expect(page.getByRole("heading", { name: /예산과 기준을 정해/ })).toBeVisible();
  await expect(page.getByText(/계획 v3/).first()).toBeVisible();
  await screenshot("schedule.png");

  await page.goto("/evidence");
  await expect(page.getByRole("heading", { name: /어떤 숫자가 실제이고/ })).toBeVisible();
  await expect(page.getByText("한국농촌경제연구원").first()).toBeVisible();
  await screenshot("data-sources.png");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/plans?id=${encodeURIComponent(currentPlanId ?? "")}`);
  await expect(page.getByRole("heading", { name: "계획 검토와 승인 이력" })).toBeVisible();
  await screenshot("plan-review-mobile.png");
  await auditPlanTabOrder(page);

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /제한된 예산으로/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "의견 검토" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "계획 검토" }).first()).toBeVisible();
  await screenshot("dashboard-operations-attention.png");
});
