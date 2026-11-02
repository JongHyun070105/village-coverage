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

test("web and API responses include the intended safe header policies", async ({ page }) => {
  const web = await page.goto("/scenarios");
  expect(web).not.toBeNull();
  const webHeaders = web!.headers();
  expect(webHeaders["x-content-type-options"]).toBe("nosniff");
  expect(webHeaders["x-frame-options"]).toBe("DENY");
  expect(webHeaders["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(webHeaders["content-security-policy"]).toBe("frame-ancestors 'none'");
  expect(webHeaders["permissions-policy"]).toContain("geolocation=()");
  expect(webHeaders["strict-transport-security"]).toBe("max-age=31536000");

  const api = await page.request.get("http://127.0.0.1:8010/health");
  expect(api.status()).toBe(200);
  expect(api.headers()["x-content-type-options"]).toBe("nosniff");
  expect(api.headers()["x-frame-options"]).toBe("DENY");
  expect(api.headers()["permissions-policy"]).toContain("camera=()");
  expect(api.headers()["content-security-policy"]).toBe("frame-ancestors 'none'");
  expect(api.headers()["strict-transport-security"]).toBeUndefined();
});

test("evidence page handles an unavailable home-doctor snapshot", async ({ page }) => {
  await page.route("**/api/evidence/home-doctor", (route) =>
    route.fulfill({ json: { status: "UNAVAILABLE", summary: null } }),
  );
  await page.goto("/evidence");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/제공기관 안내: -/)).toBeVisible();
});

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

test("demand provenance describes Gemini as a local service-ID check", async ({ page }) => {
  let method: "gemini_structured_output" | "deterministic_fallback" = "gemini_structured_output";
  await page.route("**/api/demand/drafts", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const input = route.request().postDataJSON() as { area_id: string; survey_date: string };
    await route.fulfill({
      status: 201,
      json: {
        draft_id: "gemini-provenance-draft",
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
          confidence: 0.76,
          needs_followup_survey: false,
          followup_reason: null,
          source_text_was_redacted: false,
          method,
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

  await page.goto("/demand");
  await expect.poll(() => page.getByLabel("서비스 권역").locator("option").count()).toBeGreaterThan(1);
  await page.getByLabel("조사일").fill(new Date().toISOString().slice(0, 10));
  await page.locator("#demand-note").fill("겨울철 세탁 서비스를 월 2회 요청함.");
  await page.getByRole("button", { name: "구조화 초안 저장" }).click();

  const provenance = page.locator(".demand-provenance");
  await expect(provenance).toContainText("규칙 기반 추출 · Gemini 서비스 ID 확인");
  await expect(page.locator(".privacy-confirm")).toContainText("Gemini 서비스 ID 확인 보조 신호");
  await expect(provenance).not.toContainText("Gemini 초안");
  await expect(page.locator(".content-hero")).toContainText("Gemini가 호출되는 경우에도 주민 원문 없이");

  method = "deterministic_fallback";
  await page.reload();
  await expect.poll(() => page.getByLabel("서비스 권역").locator("option").count()).toBeGreaterThan(1);
  await page.getByLabel("조사일").fill(new Date().toISOString().slice(0, 10));
  await page.locator("#demand-note").fill("겨울철 세탁 서비스를 월 2회 요청함.");
  await page.getByRole("button", { name: "구조화 초안 저장" }).click();
  await expect(page.locator(".privacy-confirm")).toContainText("규칙 기반 추출 참고값");
  await expect(page.locator(".privacy-confirm")).not.toContainText("Gemini 서비스 ID 확인 보조 신호");
  await expect(page.locator(".demand-provenance")).toContainText("규칙 기반 초안");
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

test("scenario region changes clear all region-bound comparison results", async ({ page }) => {
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const input = route.request().postDataJSON() as { scenario: string; budget_won: number };
    await route.fulfill({
      status: 201,
      json: {
        schedule_id: `region-${input.scenario}-${Math.random()}`,
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
    await route.fulfill({
      status: 200,
      json: {
        schedule_id: "region-minimum-analysis",
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
  const firstRegion = await region.inputValue();
  const secondRegion = await region.locator("option").evaluateAll((options, current) =>
    (options as HTMLOptionElement[]).find((option) => option.value !== current)?.value ?? "",
    firstRegion,
  );
  const runButton = page.getByRole("button", { name: "4안 비교 실행" });
  await runButton.click();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible();

  const preset = page.getByLabel("정책 시작 설정");
  await expect.poll(() => preset.locator("option").count()).toBeGreaterThan(1);
  const nextPreset = await preset.locator("option").nth(1).getAttribute("value");
  await preset.selectOption(nextPreset!);
  await runButton.click();
  await expect(page.getByRole("heading", { name: /무엇이 바뀌었나/ })).toBeVisible();

  await region.selectOption(secondRegion);
  await expect(region).toHaveValue(secondRegion);
  await expect(page.locator(".scenario-card .empty-line")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /무엇이 바뀌었나/ })).toHaveCount(0);

  await region.selectOption(firstRegion);
  await expect(region).toHaveValue(firstRegion);
  await expect(page.locator(".scenario-card .empty-line")).toHaveCount(4);
});

test("scenario area responses that arrive after a region switch are ignored", async ({ page }) => {
  let delayedRegionId = "";
  let releaseDelayedArea!: () => void;
  let delayedAreaFinished!: () => void;
  let areaBResponses = 0;
  const delayedAreaGate = new Promise<void>((resolve) => { releaseDelayedArea = resolve; });
  const delayedAreaResponse = new Promise<void>((resolve) => { delayedAreaFinished = resolve; });
  await page.route((url) => url.pathname === "/api/areas", async (route) => {
    const url = new URL(route.request().url());
    const regionId = url.searchParams.get("region_id") ?? "";
    const area = (id: string, needsSurvey: boolean) => ({
      area_id: id,
      name: id,
      legal_code: id === "synthetic-area-a" ? "0000000001" : "0000000002",
      region_id: regionId,
      needs_survey: needsSurvey,
      population_total: 10,
      population_65_plus: 5,
      single_households_65_plus: 3,
      facility_count: 1,
      anchor_lat: 36,
      anchor_lng: 126,
      simulated_monthly_demand: 2,
    });
    if (!delayedRegionId) {
      delayedRegionId = regionId;
      await delayedAreaGate;
      await route.fulfill({ status: 200, json: { areas: [area("synthetic-area-a", false)], field_provenance: {} } });
      delayedAreaFinished();
      return;
    }
    if (regionId !== delayedRegionId) {
      areaBResponses += 1;
      await route.fulfill({ status: 200, json: { areas: [area("synthetic-area-b", true)], field_provenance: {} } });
      return;
    }
    await route.fulfill({ status: 200, json: { areas: [area("synthetic-area-a", false)], field_provenance: {} } });
  });
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const input = route.request().postDataJSON() as { scenario: string; budget_won: number };
    await route.fulfill({
      status: 201,
      json: {
        schedule_id: `stale-area-${input.scenario}-${Math.random()}`,
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
    await route.fulfill({
      status: 200,
      json: { areas: [{ area_id: "synthetic-area-b", included: true }], fairness: {}, method: "test fixture" },
    });
  });
  await page.route("**/api/minimum-coverage/analysis", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        schedule_id: "stale-area-minimum-analysis",
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
  const secondRegion = await region.locator("option").evaluateAll((options, current) =>
    (options as HTMLOptionElement[]).find((option) => option.value !== current)?.value ?? "",
    await region.inputValue(),
  );
  await region.selectOption(secondRegion);
  await expect.poll(() => areaBResponses).toBeGreaterThan(0);

  const runButton = page.getByRole("button", { name: "4안 비교 실행" });
  await runButton.click();
  await expect(page.getByRole("heading", { name: "최소보장 비용 분석" })).toBeVisible();
  releaseDelayedArea();
  await delayedAreaResponse;

  const preset = page.getByLabel("정책 시작 설정");
  const nextPreset = await preset.locator("option").nth(1).getAttribute("value");
  await preset.selectOption(nextPreset!);
  await runButton.click();
  await expect(page.getByRole("heading", { name: /무엇이 바뀌었나/ })).toBeVisible();
  await expect(page.getByText("조사필요 권역 포함 ±0곳", { exact: true })).toBeVisible();
});

test("dashboard stops later plan writes after navigation and requires checking saved plans", async ({ page }) => {
  let schedulePosts = 0;
  let beginFirstPost!: () => void;
  let finishFirstPost!: () => void;
  let releaseFirstPost!: () => void;
  const firstPostStarted = new Promise<void>((resolve) => { beginFirstPost = resolve; });
  const firstPostFinished = new Promise<void>((resolve) => { finishFirstPost = resolve; });
  const firstPostGate = new Promise<void>((resolve) => { releaseFirstPost = resolve; });
  await page.route("**/api/schedules", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    schedulePosts += 1;
    if (schedulePosts === 1) {
      beginFirstPost();
      await firstPostGate;
    }
    await route.fulfill({ status: 201, json: { schedule_id: `pending-${schedulePosts}` } });
    if (schedulePosts === 1) finishFirstPost();
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible();
  await page.getByRole("button", { name: "4안 나란히 비교" }).click();
  const generate = page.getByRole("button", { name: "공급 일정 4안 생성" });
  await generate.evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });
  await firstPostStarted;
  expect(schedulePosts).toBe(1);

  await page.goto("/methodology");
  releaseFirstPost();
  await firstPostFinished;
  await page.waitForTimeout(300);
  expect(schedulePosts).toBe(1);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "마을별 서비스 계획" })).toBeVisible();
  await page.getByRole("button", { name: "4안 나란히 비교" }).click();
  await expect(page.locator(".provider-scenario-write-guard")).toContainText("계획 목록에서 저장 여부를 확인");
  await expect(page.getByRole("link", { name: "계획 목록 확인" })).toHaveAttribute("href", "/plans");
  await expect(page.getByRole("button", { name: "공급 일정 4안 생성" })).toBeDisabled();
  expect(schedulePosts).toBe(1);
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
