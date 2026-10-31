import { expect, test } from "@playwright/test";

const API = "http://127.0.0.1:8010";
const WEB_API = "http://127.0.0.1:3010/api";

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

test("dashboard hides prior-region results when the selected region cannot be loaded", async ({ page }) => {
  let failedRegionRequests = 0;
  await page.route((url) => url.pathname === "/api/overview", async (route) => {
    const requestUrl = new URL(route.request().url());
    if (requestUrl.searchParams.get("region_id") !== "pilot:부여군 부여읍") {
      await route.continue();
      return;
    }
    failedRegionRequests += 1;
    await route.fulfill({
      status: 503,
      json: {
        error: {
          code: "ROUTE_UNAVAILABLE",
          message: "실제 도로 이동 캐시가 없습니다. 먼저 scripts/build_travel_matrix.py 를 실행해 주세요.",
          details: {},
          retryable: false,
        },
      },
    });
  });

  await page.goto("/");
  await expect(page.locator(".metrics-grid")).toBeVisible();
  await page.getByLabel("시군구 선택").selectOption({ label: "부여군" });
  await page.getByLabel("읍면 선택").selectOption({ label: "부여읍" });

  await expect.poll(() => failedRegionRequests).toBe(1);
  await expect(page.locator(".api-unavailable")).toContainText("도로 경로 정보가 준비되지 않아 이 지역의 계획을 계산하지 못했습니다.");
  await expect(page.locator(".api-unavailable")).toContainText("다른 시범 지역을 선택하거나");
  await expect(page.locator(".api-unavailable")).not.toContainText("503");
  await expect(page.locator(".metrics-grid")).toHaveCount(0);
  await expect(page.locator(".map-canvas")).toHaveCount(0);
  await expect(page.getByLabel("시군구 선택")).toBeEnabled();
  await page.screenshot({ path: test.info().outputPath("buyeo-route-unavailable.png"), fullPage: true });
  await page.getByLabel("시군구 선택").selectOption({ label: "홍성군" });
  await expect(page.locator(".metrics-grid")).toBeVisible();
});

test("public demo keeps core flows inside the synthetic sandbox", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByLabel("공개 데모 안내")).toContainText("합성/공개 데이터");
  await expect(page.getByLabel("공개 데모 안내")).toContainText("실제 주민·공급자 운영정보");
  await expect(page.getByLabel("공개 데모 안내")).toContainText("브라우저 세션별로 격리");
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

  const scheduleEndpoint = (url: URL) => url.pathname === "/api/schedules";
  let failedComparisonRequests = 0;
  await page.route(scheduleEndpoint, async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    failedComparisonRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fulfill({ status: 503, json: { detail: "internal local failure" } });
  });
  await page.getByLabel("월 예산 (원)").fill("5000000");
  await compareButton.click();
  await expect(page.getByRole("status")).toContainText("효율 중심 계산 중");
  await expect(compareButton).toBeDisabled();
  await expect(page.getByLabel("월 예산 (원)")).toBeDisabled();
  await compareButton.evaluate((button: HTMLButtonElement) => button.click());
  await expect(page.locator(".api-error")).toContainText("데모 서버가 일시적으로 응답하지 않습니다.");
  await expect(page.locator(".api-error")).not.toContainText("internal local failure");
  await expect(page.locator(".scenario-card .empty-line")).toHaveCount(4);
  expect(failedComparisonRequests).toBe(1);
  await page.unroute(scheduleEndpoint);

  const createdResponse = await page.context().request.post(`${WEB_API}/schedules`, {
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
  await roundCard.getByRole("button", { name: "불참 되돌리기" }).click();
  await expect(roundCard.getByText("미정")).toBeVisible();
  await roundCard.getByRole("button", { name: "데모 불참" }).click();
  await expect(roundCard.getByText("이번 회차 불참")).toBeVisible();

  await page.goto(`/plans?id=${encodeURIComponent(initialPlan.schedule_id)}`);
  await expect(page.getByRole("heading", { name: "계획 v1" })).toBeVisible();
  const replan = page.getByRole("button", { name: /불참 1건 반영해 새 버전/ });
  await expect(replan).toBeVisible();
  await replan.click();
  await expect(page.getByRole("heading", { name: "계획 v2" })).toBeVisible({
    timeout: 120_000,
  });

  await page.getByRole("button", { name: "검토 요청" }).click();
  await page.getByLabel("시연 역할").selectOption("REVIEWER");
  const demoApproveButton = page.getByRole("button", { name: "데모 승인" });
  await expect(demoApproveButton).toBeEnabled();
  await demoApproveButton.click();
  await expect(page.getByText("데모 승인됨", { exact: true }).first()).toBeVisible();

  const memoResponse = await page.context().request.get(
    `${WEB_API}/schedules/${encodeURIComponent(initialPlan.schedule_id)}/decision-memo`,
  );
  expect(memoResponse.status()).toBe(200);
  expect(await memoResponse.text()).toMatch(/SIMULATED|시뮬레이션|모의/);
  const [exportedRounds] = await Promise.all([
    page.waitForEvent("download"),
    page.goto(`/plans?id=${encodeURIComponent(initialPlan.schedule_id)}`).then(async () => {
      await expect(page.getByRole("link", { name: "회차 CSV" })).toBeVisible();
      await page.getByRole("link", { name: "회차 CSV" }).click();
    }),
  ]);
  expect(exportedRounds.suggestedFilename()).toMatch(/\.csv$/);

  await page.goto("/evidence");
  await expect(
    page.getByRole("heading", { name: "어떤 숫자가 실제이고, 무엇이 참고·모의인가" }),
  ).toBeVisible();
  await expect(
    page.getByRole("table", { name: "데이터 출처별 구분, 기준일, 범위, 사용목적과 한계" }),
  ).toBeVisible();
});

test("plan detail manual retry reloads the selected plan after a machine-coded temporary failure", async ({ page }) => {
  const created = await page.context().request.post(`${WEB_API}/schedules`, {
    data: { scenario: "balanced", budget_won: 4_000_000, region_id: "pilot:홍성군 장곡면" },
  });
  expect(created.status()).toBe(201);
  const plan = await created.json();
  const detailPath = `/api/schedules/${plan.schedule_id}`;
  let detailReads = 0;
  await page.route((url) => url.pathname === detailPath, async (route) => {
    detailReads += 1;
    if (detailReads === 1) {
      await route.fulfill({
        status: 503,
        json: { detail: "DEMO_SESSION_UNAVAILABLE", code: "DEMO_SESSION_UNAVAILABLE" },
        headers: { "Retry-After": "5" },
      });
      return;
    }
    await route.continue();
  });

  await page.goto(`/plans?id=${encodeURIComponent(plan.schedule_id)}`);
  await expect(page.locator(".api-error")).toContainText("공개 데모 세션을 확인할 수 없습니다.");
  await page.getByRole("button", { name: "최신 상태 다시 불러오기" }).click();
  await expect(page.getByRole("heading", { name: "계획 v1" })).toBeVisible();
  expect(detailReads).toBeGreaterThanOrEqual(2);
});

test("GET retries one HTML upstream failure but does not retry capacity errors", async ({ page }) => {
  const created = await page.context().request.post(`${WEB_API}/schedules`, {
    data: { scenario: "balanced", budget_won: 4_000_000, region_id: "pilot:홍성군 장곡면" },
  });
  expect(created.status()).toBe(201);
  const plan = await created.json();
  const detailPath = `/api/schedules/${plan.schedule_id}`;
  let mode: "upstream" | "capacity" | "timeout" | "contract" = "upstream";
  let detailReads = 0;
  await page.route((url) => url.pathname === detailPath, async (route) => {
    detailReads += 1;
    if (mode === "upstream" && detailReads === 1) {
      await route.fulfill({ status: 502, contentType: "text/html", body: "gateway internal details" });
      return;
    }
    if (mode === "capacity") {
      await route.fulfill({
        status: 503,
        json: { detail: "DEMO_SESSION_CAPACITY", code: "DEMO_SESSION_CAPACITY" },
        headers: { "Retry-After": "60" },
      });
      return;
    }
    if (mode === "timeout") {
      await route.fulfill({ status: 504, contentType: "text/html", body: "proxy timeout details" });
      return;
    }
    if (mode === "contract") {
      await route.fulfill({ status: 200, contentType: "text/html", body: "unexpected HTML response" });
      return;
    }
    await route.continue();
  });

  await page.goto(`/plans?id=${encodeURIComponent(plan.schedule_id)}`);
  await expect(page.getByRole("heading", { name: "계획 v1" })).toBeVisible();
  expect(detailReads).toBe(2);
  await expect(page.locator("body")).not.toContainText("gateway internal details");

  mode = "capacity";
  detailReads = 0;
  await page.reload();
  await expect(page.locator(".api-error")).toContainText("공개 데모가 현재 사용할 수 있는 세션 수에 도달했습니다.");
  expect(detailReads).toBe(1);

  mode = "timeout";
  detailReads = 0;
  await page.reload();
  await expect(page.locator(".api-error")).toContainText("데모 서버 응답 시간이 초과되었습니다.");
  await expect(page.locator(".api-error")).toContainText("REQUEST_TIMEOUT");
  await expect(page.locator("body")).not.toContainText("proxy timeout details");
  expect(detailReads).toBe(4);

  mode = "contract";
  detailReads = 0;
  await page.reload();
  await expect(page.locator(".api-error")).toContainText("예상한 형식의 응답을 보내지 않았습니다.");
  await expect(page.locator(".api-error")).toContainText("API_CONTRACT_ERROR");
  await expect(page.locator("body")).not.toContainText("unexpected HTML response");
  expect(detailReads).toBe(1);
});

test("three independent browser contexts isolate plans, provider declines and approvals", async ({ browser }) => {
  const contexts = await Promise.all([browser.newContext(), browser.newContext(), browser.newContext()]);
  const [visitorA, visitorB, visitorC] = contexts;
  try {
    const pageA = await visitorA.newPage();
    const pageB = await visitorB.newPage();
    const pageC = await visitorC.newPage();
    const regionId = "pilot:홍성군 장곡면";

    const visitorCookies: string[] = [];
    for (const visitor of [visitorA, visitorB, visitorC]) {
      const session = await visitor.request.get(`${WEB_API}/regions`);
      expect(session.status()).toBe(200);
      expect(session.headers()["set-cookie"]).toContain("vc_demo_session=");
      const cookie = (await visitor.cookies("http://127.0.0.1:3010/api"))
        .find((item) => item.name === "vc_demo_session");
      expect(cookie).toMatchObject({ httpOnly: true, sameSite: "Lax", path: "/api", secure: false });
      visitorCookies.push(cookie!.value);
    }
    expect(new Set(visitorCookies).size).toBe(3);

    const createdAResponse = await visitorA.request.post(`${WEB_API}/schedules`, {
      data: { scenario: "balanced", budget_won: 4_000_000, region_id: regionId },
    });
    expect(createdAResponse.status()).toBe(201);
    const planA = await createdAResponse.json();
    expect(planA.provenance).toContain("SIMULATED");
    const declinedRound = planA.rounds[0];
    expect(declinedRound).toBeTruthy();

    await pageB.goto("/");
    await expect(pageB.getByLabel("공개 데모 안내")).toContainText("브라우저 세션별로 격리");
    const bHistory = await visitorB.request.get(`${WEB_API}/schedules`, { params: { region_id: regionId } });
    expect((await bHistory.json()).plans).toHaveLength(0);
    const bForeignRead = await visitorB.request.get(`${WEB_API}/schedules/${encodeURIComponent(planA.schedule_id)}`);
    expect(bForeignRead.status()).toBe(404);
    const bForeignWrite = await visitorB.request.post(
      `${WEB_API}/schedules/${encodeURIComponent(planA.schedule_id)}/approval`,
      { data: { action: "submit", role: "PLANNER", expected_plan_version: 1 } },
    );
    expect(bForeignWrite.status()).toBe(404);

    await pageA.goto(`/providers/${encodeURIComponent(declinedRound.provider_id)}`);
    const declinedCard = pageA.locator(`[data-demo-round-id="${declinedRound.service_round_id}"]`);
    await expect(declinedCard).toBeVisible();
    await declinedCard.getByRole("button", { name: "데모 불참" }).click();
    await expect(declinedCard.getByText("이번 회차 불참")).toBeVisible();

    const createdBResponse = await visitorB.request.post(`${WEB_API}/schedules`, {
      data: { scenario: "balanced", budget_won: 4_000_000, region_id: regionId },
    });
    expect(createdBResponse.status()).toBe(201);
    const planB = await createdBResponse.json();
    expect(planB.rounds.every((round: { participation_status: string }) =>
      round.participation_status !== "DECLINED",
    )).toBeTruthy();
    const bHistoryAfterDecline = await visitorB.request.get(`${WEB_API}/schedules`, {
      params: { region_id: regionId },
    });
    expect((await bHistoryAfterDecline.json()).plans).toHaveLength(1);
    expect((await bHistoryAfterDecline.json()).plans[0].replan_available).toBeFalsy();

    await pageA.goto(`/plans?id=${encodeURIComponent(planA.schedule_id)}`);
    await expect(pageA.getByRole("button", { name: /불참 1건 반영해 새 버전/ })).toBeVisible();
    await pageA.getByRole("button", { name: /불참 1건 반영해 새 버전/ }).click();
    await expect(pageA.getByRole("heading", { name: "계획 v2" })).toBeVisible({ timeout: 120_000 });
    await expect.poll(() => new URL(pageA.url()).searchParams.get("id"))
      .not.toBe(planA.schedule_id);
    const planA2Id = new URL(pageA.url()).searchParams.get("id");
    expect(planA2Id).toBeTruthy();
    const planA2Response = await visitorA.request.get(`${WEB_API}/schedules/${encodeURIComponent(planA2Id!)}`);
    expect(planA2Response.ok()).toBeTruthy();
    const planA2 = await planA2Response.json();
    expect(planA2.rounds.some((round: { provider_id: string; area_id: string; service_type: string; scheduled_date: string }) =>
      round.provider_id === declinedRound.provider_id
      && round.area_id === declinedRound.area_id
      && round.service_type === declinedRound.service_type
      && round.scheduled_date === declinedRound.scheduled_date,
    )).toBeFalsy();

    const cPlanResponse = await visitorC.request.post(`${WEB_API}/schedules`, {
      data: { scenario: "efficiency", budget_won: 4_000_000, region_id: regionId },
    });
    expect(cPlanResponse.status()).toBe(201);
    const planC = await cPlanResponse.json();
    await pageC.goto(`/plans?id=${encodeURIComponent(planC.schedule_id)}`);
    await expect(pageC.getByRole("heading", { name: "계획 v1" })).toBeVisible();
    await pageC.getByRole("button", { name: "검토 요청" }).click();
    await pageC.getByLabel("시연 역할").selectOption("REVIEWER");
    await pageC.getByRole("button", { name: "데모 승인", exact: true }).click();
    await expect(pageC.getByText("데모 승인됨", { exact: true }).first()).toBeVisible();

    const foreignApproval = await visitorA.request.get(`${WEB_API}/schedules/${encodeURIComponent(planC.schedule_id)}`);
    expect(foreignApproval.status()).toBe(404);
    const aHistory = await visitorA.request.get(`${WEB_API}/schedules`, { params: { region_id: regionId } });
    expect((await aHistory.json()).plans.map((plan: { schedule_id: string }) => plan.schedule_id).includes(planC.schedule_id)).toBeFalsy();
    const stalePlan = await visitorB.request.get(`${WEB_API}/schedules/not-a-real-schedule-id`);
    expect(stalePlan.status()).toBe(404);
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test("public demo API errors give bounded retry and network guidance", async ({ page }) => {
  const cases = [
    { status: 403, expected: "이 요청을 처리할 권한이 없습니다." },
    { status: 404, expected: "요청한 자료를 찾을 수 없습니다." },
    { status: 409, expected: "다른 요청으로 상태가 바뀌었습니다." },
    { status: 410, expected: "이 브라우저 세션이 만료되었습니다." },
    { status: 422, expected: "입력값을 처리할 수 없습니다." },
    { status: 429, expected: "잠시 요청이 많습니다." },
    { status: 500, expected: "서버에서 요청을 처리하지 못했습니다." },
    { status: 503, expected: "데모 서버가 일시적으로 응답하지 않습니다." },
  ];
  const scheduleEndpoint = (url: URL) => url.pathname === "/api/schedules";
  let requestCount = 0;
  let nextFailure: { status: number; expected: string } | null = null;
  await page.route(scheduleEndpoint, async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    requestCount += 1;
    const failure = nextFailure;
    if (!failure) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: failure.status,
      json: failure.status === 429
        ? { detail: "DEMO_RATE_LIMITED", code: "DEMO_RATE_LIMITED" }
        : { detail: `mock ${failure.status}` },
      headers: failure.status === 429
        ? {
          "Retry-After": "8",
          "Access-Control-Allow-Origin": "http://127.0.0.1:3010",
          "Access-Control-Expose-Headers": "Retry-After",
        }
        : undefined,
    });
  });

  for (const failure of cases) {
    nextFailure = failure;
    await page.goto("/scenarios");
    await page.getByRole("button", { name: "4안 비교 실행" }).click();
    await expect(page.locator(".api-error")).toContainText(failure.expected);
    await expect(page.locator(".api-error")).not.toContainText("포트 8000");
    expect(requestCount).toBe(cases.indexOf(failure) + 1);
    if (failure.status === 429) {
      await expect(page.locator(".api-error")).toContainText("약 8초 기다린 뒤 다시 시도해 주세요.");
    }
  }

  nextFailure = null;
  await page.route(scheduleEndpoint, (route) => route.abort("timedout"));
  await page.goto("/scenarios");
  await page.getByRole("button", { name: "4안 비교 실행" }).click();
  await expect(page.locator(".api-error")).toContainText("데모 서버에 연결할 수 없습니다.");
});


test("cold start waits for verified health and automatically loads once ready", async ({ page }) => {
  let probes = 0;
  let reads = 0;
  await page.route("**/api/health", async route => {
    probes++;
    if (probes < 3) await route.fulfill({status:503,contentType:"text/html",body:"preparing"});
    else await route.fulfill({json:{status:"ok"}});
  });
  page.on("request", request => { if(new URL(request.url()).pathname === "/api/overview") reads++; });
  await page.goto("/");
  await expect(page.getByRole("heading", {name:"데모 서버 연결을 준비하고 있습니다"})).toBeVisible();
  expect(reads).toBe(0);
  await expect(page.locator(".metrics-grid")).toBeVisible();
  expect(probes).toBe(3);
  expect(reads).toBe(1);
});

test("healthy API 500 and rate limit remain real errors without repeating solver GET", async ({ page }) => {
  let mode = 500;
  let reads = 0;
  await page.route("**/api/health", route=>route.fulfill({json:{status:"ok"}}));
  await page.route("**/api/overview?**", route=>{
    reads++;
    return route.fulfill({status:mode,json:mode===429?{code:"DEMO_RATE_LIMITED"}:{},headers:mode===429?{"Retry-After":"8"}:{}});
  });
  await page.goto("/");
  await expect(page.locator(".api-unavailable")).toContainText("서버에서 요청을 처리하지 못했습니다.");
  await expect(page.locator(".api-unavailable")).not.toContainText("절전");
  expect(reads).toBe(1);
  mode=429;
  await page.getByRole("button",{name:"다시 불러오기"}).click();
  await expect(page.locator(".api-unavailable")).toContainText("약 8초");
  expect(reads).toBe(2);
});

test("cold start status fits four viewports and offers bounded manual recovery", async ({ page }) => {
  await page.clock.install();
  let ready = false;
  await page.route("**/api/health", route=>ready
    ? route.fulfill({json:{status:"ok"}})
    : route.fulfill({status:503,contentType:"text/html",body:"preparing"}));
  await page.goto("/");
  await expect(page.locator(".api-readiness")).toBeVisible();
  for (const [width,height] of [[390,844],[768,1024],[1440,900],[1920,1080]]) {
    await page.setViewportSize({width,height});
    await expect(page.locator('.api-readiness')).toHaveAttribute('aria-live','polite');
    await expect(page.locator('.api-readiness h2')).toBeInViewport({ ratio: 1 });
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:test.info().outputPath(`cold-start-${width}.png`),fullPage:true});
  }
  await page.clock.fastForward(16_000);
  await expect(page.locator('.api-readiness button')).toBeVisible();
  // Advance incrementally so each scheduled probe settles before the next interval.
  for(let n=0;n<9;n++) {
    await page.clock.fastForward(15_000);
    await page.waitForTimeout(1);
  }
  await expect(page.locator('.api-unavailable')).toContainText('연결 준비 시간이 초과되었습니다');
  ready=true;
  await page.getByRole('button',{name:'다시 불러오기'}).click();
  await page.clock.resume();
  await expect(page.locator('.metrics-grid')).toBeVisible();
});

for (const kind of ["json", "html", "render"] as const) {
  test(`first region ${kind} 429 automatically recovers and preserves first-session isolation`, async ({ page }) => {
    let reads = 0;
    let blocked = true;
    await page.route("**/api/regions", async route => {
      reads++;
      if (!blocked) { await route.continue(); return; }
      blocked = false;
      await route.fulfill(kind === "json"
        ? { status: 429, json: {code: "DEMO_SESSION_RATE_LIMITED"}, headers: {"Retry-After": "2"} }
        : { status: 429, contentType: "text/html", body: "private upstream body",
            headers: {"Retry-After": "2", ...(kind === "render" ? {"x-render-routing": "hibernate-rate-limited"} : {})} });
    });
    await page.goto("/");
    await expect(page.getByRole("heading", {name: "데모 서버 연결을 준비하고 있습니다"})).toBeVisible();
    await expect(page.locator(".api-readiness")).toContainText("연결 상태를 확인하는 중입니다.");
    await expect(page.locator(".metrics-grid")).toBeVisible();
    expect(reads).toBe(2);
    await expect(page.locator("body")).not.toContainText("private upstream body");
    const cookies = await page.context().cookies();
    expect(cookies.filter(cookie => cookie.name === "vc_demo_session")).toHaveLength(1);
  });
}

test("first cheap GET 500 is a real error and POST 429 is never repeated", async ({page}) => {
  let reads = 0;
  await page.route("**/api/regions", route=>{reads++;return route.fulfill({status:500,json:{code:"INTERNAL_ERROR"}});});
  await page.goto("/");
  await expect(page.locator(".api-unavailable")).toContainText("서버에서 요청을 처리하지 못했습니다.");
  expect(reads).toBe(1);
  await page.unroute("**/api/regions");
  let writes=0;
  await page.route("**/api/schedules", route=>{
    if(route.request().method()!=="POST") return route.continue();
    writes++;return route.fulfill({status:429,json:{code:"DEMO_RATE_LIMITED"},headers:{"Retry-After":"2"}});
  });
  await page.goto("/scenarios");
  await page.getByRole("button",{name:"4안 비교 실행"}).click();
  await expect(page.locator(".api-error")).toContainText("DEMO_RATE_LIMITED");
  await page.waitForTimeout(2500);
  expect(writes).toBe(1);
});
