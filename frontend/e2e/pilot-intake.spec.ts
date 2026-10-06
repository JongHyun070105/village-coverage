import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8010";

test("pilot setup keeps uploads staged until confirmation and exposes row errors", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pilot-setup");
  await expect(page.getByRole("heading", { name: "지역 파일럿 준비 현황" })).toBeVisible();
  await expect(page.getByText(/데모 공급자·합성 수요는 자동으로 섞이지 않습니다/)).toBeVisible();
  await expect(page.getByLabel("지역", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "새 파일럿 데이터셋 만들기" }).click();
  const contextStatus = page.getByRole("status").filter({ hasText: "선택됨:" });
  await expect(contextStatus).toBeVisible();
  const contextId = (await contextStatus.innerText()).match(/pilot-[a-f0-9]+/)?.[0];
  expect(contextId).toBeTruthy();

  await page.goto("/pilot-imports");
  await expect(page.getByRole("heading", { name: "자료를 검토한 뒤 가져옵니다" })).toBeVisible();
  await page.getByLabel("CSV 양식").selectOption("region_areas");
  const areaHeaders = "area_code,area_name,latitude,longitude,population_total,population_65_plus,households_total,source_date,source_type";
  const uniqueCode = `998${String(Date.now()).slice(-7)}`;
  const areaCsv = `${areaHeaders}\n${uniqueCode},QA 마을,36.5,126.6,100,40,50,2026-09-30,PUBLIC_DATA\n`;
  await page.locator("#pilot-csv-file").setInputFiles({
    name: "pilot-region.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(areaCsv),
  });
  await page.getByRole("button", { name: "미리보기 만들기" }).click();
  await expect(page.getByText("확정 전 미리보기")).toBeVisible();
  await expect(page.locator(".pilot-preview-row")).toHaveCount(1);
  const beforeConfirm = await request.get(`${API}/api/pilot-setup/readiness`);
  expect((await beforeConfirm.json()).dimensions.find((item: { id: string }) => item.id === "REGION_DATA").records).toBe(0);
  await page.getByLabel("오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.").check();
  await page.getByRole("button", { name: "확인한 행 가져오기" }).click();
  await expect(page.getByText(/1개 행을 확인했고 1개 domain record/)).toBeVisible();

  await page.getByLabel("CSV 양식").selectOption("demand_observations");
  const demandHeaders = "region_code,area_code,observed_date,service_type,observed_count,observation_kind,note,source_type";
  const demandCsv = [
    demandHeaders,
    `홍성군,${uniqueCode},2026-09-30,laundry,2,전화,010-1234-5678 주민 요청,SURVEY_INPUT`,
    "홍성군,9999999999,2026-09-30,laundry,1,전화,오류 행,SURVEY_INPUT",
  ].join("\n");
  await page.locator("#pilot-csv-file").setInputFiles({
    name: "pilot-demand.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(demandCsv),
  });
  await page.getByRole("button", { name: "미리보기 만들기" }).click();
  await expect(page.getByText("경고 검토")).toBeVisible();
  await expect(page.locator(".pilot-preview-row .import-status.error")).toHaveText("가져오기 불가");
  await expect(page.locator(".pilot-preview-list")).not.toContainText("010-1234-5678");
  const demandBeforeConfirm = await request.get(`${API}/api/pilot-setup/readiness`);
  expect((await demandBeforeConfirm.json()).dimensions.find((item: { id: string }) => item.id === "DEMAND_EVIDENCE").records).toBe(0);
  const [failedRows] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "실패 행 다운로드" }).click(),
  ]);
  expect(failedRows.suggestedFilename()).toContain("failed.csv");
  await page.getByLabel("오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.").check();
  await page.getByRole("button", { name: "확인한 행 가져오기" }).click();
  await expect(page.getByText(/1개 행을 확인했고 1개 domain record.*오류 1개/)).toBeVisible();

  const scopedReadiness = await request.get(`${API}/api/pilot-setup/readiness?context_id=${contextId}`);
  expect(scopedReadiness.ok()).toBeTruthy();
  expect((await scopedReadiness.json()).dimensions.find((item: { id: string }) => item.id === "REGION_DATA").records).toBe(1);
  expect((await scopedReadiness.json()).dimensions.find((item: { id: string }) => item.id === "DEMAND_EVIDENCE").records).toBe(1);

  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(layout.content).toBeLessThanOrEqual(layout.viewport);
});

test("data quality issues lead to the matching intake or provider review task", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/data-quality");
  await expect(page.getByRole("heading", { name: "무슨 데이터로 계산했는지 공개합니다" })).toBeVisible();
  await expect(page.getByRole("link", { name: "지역·좌표 자료 가져오기" })).toHaveAttribute("href", "/pilot-imports");
  await expect(page.getByRole("link", { name: "조사 자료 검토하기" })).toHaveAttribute("href", "/pilot-imports");
  await expect(page.getByRole("link", { name: "공급자 매핑·중복 검토" })).toHaveAttribute("href", "/providers");
  await expect(page.getByText(/처리 대기 건수나 자동 수정 상태를 뜻하지 않습니다/)).toBeVisible();
  const layout = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(layout.content).toBeLessThanOrEqual(layout.viewport);
});

test("Buyeo survey-needed areas are findable from the dashboard table", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /제한된 예산으로/ })).toBeVisible();
  await page.getByLabel("시군구 선택").selectOption({ label: "부여군" });
  await page.getByLabel("읍면 선택").selectOption({ label: "부여읍" });
  await page.getByText("마을별 배정 표로 보기", { exact: true }).click();
  const surveyNeededRow = page.getByRole("row").filter({ hasText: "조사 필요" }).first();
  await expect(surveyNeededRow).toBeVisible();
  const areaName = (await surveyNeededRow.getByRole("rowheader").innerText()).trim();
  await surveyNeededRow.getByRole("link", { name: "권역 상세" }).click();
  await expect(page.getByRole("heading", { name: areaName })).toBeVisible();
  await expect(page.locator(".content-hero p")).toContainText("법정동 코드");
});

test("pilot intake and review pages fit desktop, tablet, and mobile widths", async ({ page }) => {
  const routes = [
    { path: "/pilot-setup", marker: "지역 파일럿 준비 현황" },
    { path: "/pilot-imports", marker: "자료를 검토한 뒤 가져옵니다" },
    { path: "/data-quality", marker: "무슨 데이터로 계산했는지 공개합니다" },
    { path: "/providers", marker: "공식 디렉터리 등록 조직" },
  ];
  for (const width of [1440, 1280, 1024, 390]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
    for (const route of routes) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { name: route.marker, exact: false })).toBeVisible();
      if (route.path === "/providers") {
        await expect(page.getByRole("link", { name: "행정안전부 전국 마을기업 현황" })).toBeVisible();
      }
      const layout = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        content: document.documentElement.scrollWidth,
        overflowing: [...document.querySelectorAll<HTMLElement>("body *")]
          .map((element) => ({
            element: `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}.${String(element.className ?? "").toString().trim().replace(/\s+/g, ".")}`,
            right: Math.round(element.getBoundingClientRect().right),
            width: Math.round(element.getBoundingClientRect().width),
          }))
          .filter((item) => item.right > document.documentElement.clientWidth + 1)
          .slice(0, 8),
      }));
      expect(layout.content, `${route.path} overflows at ${width}px: ${JSON.stringify(layout.overflowing)}`).toBeLessThanOrEqual(layout.viewport);
    }
  }
});
