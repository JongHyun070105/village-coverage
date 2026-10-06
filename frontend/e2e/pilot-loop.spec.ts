import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const areaCode = "4480034021";

function csv(headers: string[], rows: string[][]) {
  return [headers.join(","), ...rows.map((row) => row.map((value) => `"${value.replaceAll('"', '""')}"`).join(","))].join("\n");
}

async function uploadPilotCsv(page: Page, type: string, headers: string[], rows: string[][]) {
  await page.getByLabel("CSV 양식").selectOption(type);
  await page.locator("#pilot-csv-file").setInputFiles({
    name: `${type}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from(csv(headers, rows)),
  });
  await page.getByRole("button", { name: "미리보기 만들기" }).click();
  await expect(page.getByText("확정 전 미리보기")).toBeVisible();
  await expect(page.locator(".pilot-preview-row .import-status.error")).toHaveCount(0);
  await page.getByLabel("오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.").check();
  await page.getByRole("button", { name: "확인한 행 가져오기" }).click();
  await expect(page.getByRole("status").filter({ hasText: "확정 입력" })).toBeVisible();
}

test("one pilot context flows from browser intake through optimizer, approval and execution", async ({ page, request }) => {
  const today = new Date();
  const iso = (offset: number) => {
    const date = new Date(today);
    date.setDate(date.getDate() + offset);
    return date.toISOString().slice(0, 10);
  };
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/pilot-setup");
  await page.getByLabel("데이터 모드").selectOption("SYNTHETIC_REHEARSAL");
  await page.getByRole("button", { name: "새 파일럿 데이터셋 만들기" }).click();
  const contextStatus = page.getByRole("status").filter({ hasText: "선택됨:" });
  await expect(contextStatus).toBeVisible();
  const contextId = (await contextStatus.innerText()).match(/pilot-[a-f0-9]+/)?.[0];
  expect(contextId).toBeTruthy();

  await page.goto("/pilot-imports");
  await page.getByLabel("CSV 양식").selectOption("region_areas");
  await page.locator("#pilot-csv-file").setInputFiles({
    name: "synthetic-areas.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv(
      ["area_code", "area_name", "latitude", "longitude", "population_total", "population_65_plus", "households_total", "source_date", "source_type"],
      [[areaCode, "Synthetic rehearsal village", "36.51", "126.61", "420", "160", "210", iso(0), "SIMULATED"]],
    )),
  });
  await page.getByRole("button", { name: "미리보기 만들기" }).click();
  await expect(page.getByText("확정 전 미리보기")).toBeVisible();
  await page.getByLabel("오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.").check();
  await page.getByRole("button", { name: "확인한 행 가져오기" }).click();
  await expect(page.getByText(/1개 행을 확인했고 1개 domain record/)).toBeVisible();

  await page.getByLabel("CSV 양식").selectOption("demand_observations");
  await page.locator("#pilot-csv-file").setInputFiles({
    name: "synthetic-demand.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv(
      ["region_code", "area_code", "observed_date", "service_type", "observed_count", "observation_kind", "note", "source_type"],
      [
        ...Array.from({ length: 5 }, (_, index) => ["홍성군", areaCode, iso(-index), "home_repair", "2", "synthetic observation", "synthetic request", "SIMULATED"]),
        ["홍성군", "9999999999", iso(0), "home_repair", "1", "synthetic observation", "invalid area row", "SIMULATED"],
      ],
    )),
  });
  await page.getByRole("button", { name: "미리보기 만들기" }).click();
  await expect(page.locator(".pilot-preview-row .import-status.error")).toHaveCount(1);
  await expect(page.locator(".pilot-preview-list")).toContainText("region_areas 양식으로 등록");
  await page.getByLabel("오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.").check();
  await page.getByRole("button", { name: "확인한 행 가져오기" }).click();
  await expect(page.getByText(/5개 행을 확인했고 5개 domain record/)).toBeVisible();

  await uploadPilotCsv(page, "surveys",
    ["region_code", "area_code", "survey_date", "service_type", "survey_count", "eligible_population", "source_type", "note"],
    [["홍성군", areaCode, iso(-1), "home_repair", "1", "10", "SIMULATED", "synthetic survey fixture"]]);
  const officialSurvey = await request.post(`${API}/api/villages/${areaCode}/surveys`, {
    data: { survey_type: "phone", survey_date: iso(-1), service_type: "home_repair", frequency_per_month: 1, free_text_note: "synthetic conflict fixture" },
  });
  expect(officialSurvey.ok(), await officialSurvey.text()).toBeTruthy();
  const residentFeedback = await request.post(`${API}/api/feedback`, {
    data: {
      area_id: areaCode,
      service_type: "home_repair",
      feedback_type: "SERVICE_REQUEST",
      description: "synthetic resident feedback fixture",
      claim: { claimed_frequency_per_month: 12 },
    },
  });
  expect(residentFeedback.ok(), await residentFeedback.text()).toBeTruthy();
  const feedbackBody = await residentFeedback.json();
  const residentFeedbackId = feedbackBody.feedback_id as string;
  expect(feedbackBody.conflict_ids).toHaveLength(1);
  await page.goto("/pilot-setup");
  await page.getByLabel("연결할 주민 의견 ID").fill(residentFeedbackId);
  await page.getByRole("button", { name: "법정동 코드로 주민 의견 연결" }).click();
  await expect(page.getByRole("status").filter({ hasText: "주민 의견" })).toContainText("본문·연락처는 pilot snapshot에 복사하지 않습니다");
  await page.goto("/pilot-imports");

  const directoryIngest = await request.post(`${API}/api/provider-directory/ingest`, {
    data: {
      source_id: "DATA_GO_KR_15091502",
      rows: [{
        name: "(주)홍성주거복지센터",
        source_record_id: "DATA_GO_KR_15091502:row-000933",
        organization_type: "지역",
        region_id: "pilot:홍성군",
        region_label: "충청남도 홍성군",
        region_code: "홍성군",
        service_hint: "집수리",
        public_service_description: "집수리",
        reference_date: "2025-12-31",
        public_contact_available: false,
      }],
    },
  });
  expect(directoryIngest.ok(), await directoryIngest.text()).toBeTruthy();

  await uploadPilotCsv(page, "provider_organizations",
    ["provider_org_id", "official_name", "organization_type", "region_code", "public_business_address", "public_contact_available", "source_id", "source_record_id", "source_snapshot", "provenance", "source_type"],
    [
      ["synthetic-org", "(주)홍성주거복지센터", "지역", "홍성군", "", "false", "DATA_GO_KR_15091502", "DATA_GO_KR_15091502:row-000933", "2025-12-31", "REAL_DIRECTORY", "OFFICIAL_DIRECTORY"],
      ["synthetic-org-2", "Synthetic provider B", "협동조합", "홍성군", "", "false", "SYNTHETIC_FIXTURE", "org-2", iso(0), "SIMULATED", "SIMULATED"],
    ]);
  await uploadPilotCsv(page, "provider_services",
    ["provider_org_id", "service_description", "service_type", "mapping_status", "regulation_level", "source_type"],
    [
      ["synthetic-org", "간단 집수리", "home_repair", "MAPPING_SUGGESTED", "UNREGULATED", "SIMULATED"],
      ["synthetic-org-2", "간단 집수리", "home_repair", "MAPPING_SUGGESTED", "UNREGULATED", "SIMULATED"],
    ]);
  for (const providerOrgId of ["synthetic-org", "synthetic-org-2"]) {
    const mapping = await request.post(`${API}/api/pilot-contexts/${contextId}/provider-service-mappings`, {
      data: { provider_org_id: providerOrgId, service_type: "home_repair", decision: "VERIFIED_MAPPING", reviewer_role: "REVIEWER", note: "synthetic rehearsal" },
    });
    expect(mapping.ok(), await mapping.text()).toBeTruthy();
  }
  await uploadPilotCsv(page, "provider_availability",
    ["provider_org_id", "service_type", "available_date", "available", "start_time", "end_time", "source_type"],
    ["synthetic-org", "synthetic-org-2"].flatMap((providerOrgId) =>
      Array.from({ length: 28 }, (_, index) => [providerOrgId, "home_repair", iso(index + 1), "true", "09:00", "17:00", "SIMULATED"]),
    ));
  await uploadPilotCsv(page, "provider_capacity",
    ["provider_org_id", "service_type", "period_start", "period_end", "capacity_count", "capacity_unit", "source_type"],
    ["synthetic-org", "synthetic-org-2"].map((providerOrgId) => [providerOrgId, "home_repair", iso(0), iso(35), "80", "회", "SIMULATED"]));
  await uploadPilotCsv(page, "provider_prices",
    ["provider_org_id", "service_type", "effective_date", "price_won", "price_basis", "source_type"],
    ["synthetic-org", "synthetic-org-2"].map((providerOrgId) => [providerOrgId, "home_repair", iso(0), "25000", "방문 1회", "SIMULATED"]));
  for (const [key, value] of [
    ["provider_base_locations", { "synthetic-org": areaCode, "synthetic-org-2": areaCode }],
    ["service_duration_minutes", { home_repair: 45 }],
    ["route_matrix", [{ origin_id: areaCode, destination_id: areaCode, distance_m: 0, duration_s: 0 }]],
  ] as const) {
    const assumption = await request.post(`${API}/api/pilot-contexts/${contextId}/assumptions`, {
      data: { assumption_key: key, value, reason: "deterministic synthetic rehearsal assumption", provenance: "SIMULATED" },
    });
    expect(assumption.ok(), await assumption.text()).toBeTruthy();
  }

  await page.goto("/pilot-setup");
  await page.getByLabel("시나리오", { exact: true }).selectOption("balanced");
  await page.getByRole("button", { name: "파일럿 계획 만들기" }).click();
  const planSummary = page.locator(".pilot-plan-summary");
  await expect(planSummary).toContainText("V5.1_BASELINE_DECOMPOSED");
  await expect(planSummary).toContainText(contextId!);
  await page.getByText("계획 입력 근거와 재현 정보").click();
  await expect(planSummary).toContainText("provider_prices");
  await expect(planSummary).toContainText("PROVIDER_PRICE_IMPORT");
  await expect(planSummary).toContainText(residentFeedbackId);
  await expect(planSummary).toContainText("미해결 충돌");
  await page.getByRole("button", { name: "검토 요청" }).click();
  await expect(planSummary).toContainText("UNDER_REVIEW");
  const firstPlanId = (await planSummary.innerText()).match(/pilot-plan-[a-f0-9]+/)?.[0];
  expect(firstPlanId).toBeTruthy();
  const firstPlanResponse = await request.get(`${API}/api/pilot-contexts/plans/${firstPlanId}`);
  expect(firstPlanResponse.ok()).toBeTruthy();
  const firstPlan = await firstPlanResponse.json();
  expect(firstPlan.pilot_context_id).toBe(contextId);
  expect(firstPlan.plan.rounds.length).toBeGreaterThan(0);
  const decliningProvider = firstPlan.plan.rounds[0].provider_org_id as string;
  await page.getByRole("button", { name: "변경 요청" }).click();
  await expect(planSummary).toContainText("CHANGES_REQUESTED");
  await page.goto("/pilot-imports");
  await uploadPilotCsv(page, "provider_participation",
    ["provider_org_id", "plan_id", "service_type", "participation_status", "recorded_at", "source_type"],
    [[decliningProvider, firstPlanId!, "home_repair", "DECLINED", iso(0), "PROVIDER_SELF_REPORTED"]]);
  await page.goto("/pilot-setup");
  const changedPlanSummary = page.locator(".pilot-plan-summary");
  await page.getByRole("button", { name: "새 버전 재계획" }).click();
  await expect(changedPlanSummary).toContainText("DRAFT");
  await expect(changedPlanSummary).toContainText(contextId!);
  const replannedId = (await changedPlanSummary.innerText()).match(/pilot-plan-[a-f0-9]+/)?.[0];
  expect(replannedId).toBeTruthy();
  expect(replannedId).not.toBe(firstPlanId);
  const replannedResponse = await request.get(`${API}/api/pilot-contexts/plans/${replannedId}`);
  expect(replannedResponse.ok()).toBeTruthy();
  const replanned = await replannedResponse.json();
  expect(replanned.plan_version).toBe(firstPlan.plan_version + 1);
  expect(replanned.plan.rounds.length).toBeGreaterThan(0);
  expect(replanned.plan.rounds.some((item: { provider_org_id: string }) => item.provider_org_id === decliningProvider)).toBeFalsy();
  await page.getByRole("button", { name: "검토 요청" }).click();
  await expect(changedPlanSummary).toContainText("UNDER_REVIEW");
  await page.getByRole("button", { name: "승인", exact: true }).click();
  await expect(changedPlanSummary).toContainText("APPROVED");
  const planId = (await changedPlanSummary.innerText()).match(/pilot-plan-[a-f0-9]+/)?.[0];
  expect(planId).toBeTruthy();
  const planResponse = await request.get(`${API}/api/pilot-contexts/plans/${planId}`);
  expect(planResponse.ok()).toBeTruthy();
  const plan = await planResponse.json();
  expect(plan.pilot_context_id).toBe(contextId);
  expect(plan.plan.rounds.length).toBeGreaterThan(0);
  const round = plan.plan.rounds[0];
  await page.goto("/pilot-imports");
  await uploadPilotCsv(page, "service_execution_logs",
    ["plan_id", "plan_version", "round_id", "provider_org_id", "region_code", "area_code", "service_type", "scheduled_date", "actual_date", "execution_status", "rounds", "actual_duration_minutes", "actual_cost_won", "completion_percent", "cancel_reason", "source_type"],
    [[planId!, String(plan.plan_version), round.round_id, round.provider_org_id, "홍성군", round.area_code, round.service_type, round.scheduled_date, round.scheduled_date, "COMPLETED", "1", "45", "25000", "100", "", "SERVICE_EXECUTION_LOG"]]);
  const actuals = await request.get(`${API}/api/pilot-contexts/plans/${planId}/actuals`);
  expect(actuals.ok()).toBeTruthy();
  expect((await actuals.json()).actual_served_areas).toBe(1);
  expect((await actuals.json()).execution_log_count).toBe(1);
  const finalReadiness = await request.get(`${API}/api/pilot-setup/readiness?context_id=${contextId}`);
  expect(finalReadiness.ok()).toBeTruthy();
  expect((await finalReadiness.json()).context_id).toBe(contextId);
});
