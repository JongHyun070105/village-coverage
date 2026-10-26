import { expect, test } from "@playwright/test";

const demandRequest = {
  service_type: "laundry",
  requested_period: "겨울",
  frequency_per_month: 2,
  desired_date: null,
  desired_time: null,
  recurring_pattern: "monthly",
  urgency: null,
  urgency_evidence: null,
  preferred_days: [],
  excluded_days: [],
  constraints: [],
  service_policy: {
    service_type_id: "laundry",
    label_ko: "세탁",
    policy_status: "ALLOWED",
    policy_reason: "초기 지원 허용",
    provenance: "LOCAL_POLICY",
  },
};

test("navigation labels demo and pilot data separately", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".sidebar-bottom")).toContainText("데모 데이터");
  await page.goto("/pilot-setup");
  await expect(page.locator(".sidebar-bottom")).toContainText("파일럿 데이터");
  await expect(page.locator(".sidebar-bottom")).toContainText("시나리오");
  await expect(page.locator(".sidebar-bottom")).toContainText("UNKNOWN");
});

test("demand draft and approval move focus to the resulting status", async ({ page }) => {
  await page.route("**/api/demand/drafts", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const input = route.request().postDataJSON() as { area_id: string; survey_date: string };
    await route.fulfill({
      status: 201,
      json: {
        draft_id: "focus-transition-draft",
        area_id: input.area_id,
        survey_type: "phone",
        survey_date: input.survey_date,
        source_text_redacted: "겨울철 세탁 서비스를 월 2회 요청함.",
        source_text_was_redacted: false,
        status: "DRAFT",
        provenance: "SYNTHETIC_TEST_FIXTURE",
        structured: {
          requests: [demandRequest],
          service_registry: [demandRequest.service_policy],
          requires_service_scope_review: false,
          confidence: null,
          needs_followup_survey: false,
          followup_reason: null,
          source_text_was_redacted: false,
          method: "deterministic_fallback",
          evidence_assessment: {
            observation_count: 1,
            fresh_evidence_count: 1,
            aging_evidence_count: 0,
            stale_evidence_count: 0,
            model_confidence: null,
            deterministic_confidence: 0.2,
            combined_confidence: 0.2,
            status: "LIMITED",
            needs_survey: true,
            evidence_reasons: [],
          },
        },
      },
    });
  });
  await page.route("**/api/demand/drafts/focus-transition-draft/approve", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        draft_id: "focus-transition-draft",
        status: "APPROVED",
        approved_requests: [demandRequest],
        survey_ids: ["focus-transition-survey"],
        evidence_assessments: {},
        provenance: "SYNTHETIC_TEST_FIXTURE",
      },
    });
  });

  await page.goto("/demand");
  await expect.poll(() => page.getByLabel("서비스 권역").locator("option").count()).toBeGreaterThan(1);
  await page.getByLabel("조사일").fill(new Date().toISOString().slice(0, 10));
  await page.getByRole("button", { name: "구조화 초안 저장" }).click();
  const reviewHeading = page.getByRole("heading", { name: "구조화 요청 검토" });
  await expect(reviewHeading).toBeFocused();

  await page.getByRole("button", { name: "검토 결과 승인" }).click();
  const approvalStatus = page.getByRole("status").filter({ hasText: "요청 승인 상태" });
  await expect(approvalStatus).toBeFocused();
});

test("scenario planning moves focus to the completed result heading", async ({ page }) => {
  const minimumAnalysisRequests: Array<{ body: Record<string, unknown>; requestId?: string }> = [];
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const input = route.request().postDataJSON() as { scenario: string; budget_won: number };
    await route.fulfill({
      status: 201,
      json: {
        schedule_id: `focus-${input.scenario}`,
        scenario_key: input.scenario,
        budget_won: input.budget_won,
        summary: {
          scenario: input.scenario,
          solver_status: "OPTIMAL",
          optimality_scope: "INTEGRATED_MODEL",
          strategy_used: "BASELINE_MONOLITHIC",
          fallback_used: false,
          fallback_reason: null,
          solve_time_ms: 1,
          served_units: 2,
          total_demand_units: 2,
          covered_areas: 1,
          uncovered_areas: 0,
          total_cost_won: 25000,
          travel_time_s: 60,
          required_budget_won: 25000,
        },
      },
    });
  });
  await page.route("**/api/schedules/*/explanations", async (route) => {
    await route.fulfill({ status: 200, json: { areas: [], fairness: {}, method: "test fixture" } });
  });
  await page.route("**/api/minimum-coverage/analysis", async (route) => {
    minimumAnalysisRequests.push({
      body: route.request().postDataJSON() as Record<string, unknown>,
      requestId: route.request().headers()["x-request-id"],
    });
    await route.fulfill({
      status: 200,
      json: {
        schedule_id: "focus-minimum-analysis",
        comparison: {
          theoretical_minimum_cost: { value_won: 25000, status: "CALCULATED", label: "이론 최소 비용" },
          schedule_feasible_minimum_cost: { value_won: 25000, status: "CALCULATED", label: "일정 가능 최소 비용" },
          legacy_monthly_estimate: { value_won: 25000, status: "CALCULATED", label: "기존 월 추정" },
          difference_won: 0,
          additional_budget_needed_won: 0,
          money_alone_insufficient: false,
          money_alone_message: "테스트용 분석 결과입니다.",
          non_monetary_scope: "BINDING_AT_CURRENT_BUDGET",
          non_monetary_failures: [],
        },
      },
    });
  });

  await page.goto("/scenarios");
  const region = page.getByLabel("지역", { exact: true });
  await expect.poll(() => region.locator("option").count()).toBeGreaterThan(1);
  await expect(region).toHaveValue(/.+/);
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.getByRole("heading", { name: "시나리오 결과" })).toBeFocused({ timeout: 60_000 });
  expect(minimumAnalysisRequests[0]?.body.schedule_id).toBe("focus-minimum_coverage");
  expect(minimumAnalysisRequests[0]?.body.planning_policy).toMatchObject({
    minimum_services_per_area: 1,
  });
  expect(minimumAnalysisRequests[0]?.requestId).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});

test("scenario planning blocks a duplicate write after an ambiguous 504", async ({ page }) => {
  let schedulePosts = 0;
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    schedulePosts += 1;
    await route.fulfill({ status: 504, json: { detail: "gateway timeout" } });
  });

  await page.goto("/scenarios");
  await expect.poll(() => page.locator("#scenario-region option").count()).toBeGreaterThan(1);
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.locator(".api-error")).toContainText("계획 목록에서 저장 여부를 확인하세요.");
  await expect(page.getByRole("button", { name: "계획 생성 여부 확인" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "다시 시도" })).toHaveCount(0);
  expect(schedulePosts).toBe(1);
});

test("scenario planning keeps a plan when its explanation request fails", async ({ page }) => {
  let explanationRequests = 0;
  let schedulePosts = 0;
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    schedulePosts += 1;
    const input = route.request().postDataJSON() as { scenario: string; budget_won: number };
    await route.fulfill({
      status: 201,
      json: {
        schedule_id: `explanation-${input.scenario}`,
        scenario_key: input.scenario,
        budget_won: input.budget_won,
        summary: {
          scenario: input.scenario,
          solver_status: "OPTIMAL",
          optimality_scope: "INTEGRATED_MODEL",
          strategy_used: "BASELINE_MONOLITHIC",
          fallback_used: false,
          fallback_reason: null,
          solve_time_ms: 1,
          served_units: 2,
          total_demand_units: 2,
          covered_areas: 1,
          uncovered_areas: 0,
          total_cost_won: 25000,
          travel_time_s: 60,
        },
      },
    });
  });
  await page.route("**/api/schedules/*/explanations", async (route) => {
    explanationRequests += 1;
    if (explanationRequests === 1) {
      await route.fulfill({ status: 503, json: { detail: "temporarily unavailable" } });
      return;
    }
    await route.fulfill({ status: 200, json: { areas: [], fairness: {}, method: "test fixture" } });
  });
  await page.route("**/api/minimum-coverage/analysis", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        schedule_id: "explanation-minimum-analysis",
        comparison: {
          theoretical_minimum_cost: { value_won: 25000, status: "CALCULATED", label: "이론 최소 비용" },
          schedule_feasible_minimum_cost: { value_won: 25000, status: "CALCULATED", label: "일정 가능 최소 비용" },
          legacy_monthly_estimate: { value_won: 25000, status: "CALCULATED", label: "기존 월 추정" },
          difference_won: 0,
          additional_budget_needed_won: 0,
          money_alone_insufficient: false,
          money_alone_message: "테스트용 분석 결과입니다.",
          non_monetary_scope: "BINDING_AT_CURRENT_BUDGET",
          non_monetary_failures: [],
        },
      },
    });
  });

  await page.goto("/scenarios");
  await expect.poll(() => page.locator("#scenario-region option").count()).toBeGreaterThan(1);
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.locator(".scenario-grid .scenario-card .metric-list")).toHaveCount(4);
  await expect(page.locator(".scenario-card .api-error")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible();
  expect(schedulePosts).toBe(4);
  expect(explanationRequests).toBe(4);
});
