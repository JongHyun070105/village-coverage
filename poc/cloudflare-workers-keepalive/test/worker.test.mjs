import assert from "node:assert/strict";
import test from "node:test";
import { isInBusinessWindow, runScheduledCheck } from "../src/index.mjs";

const CRON = "5,15,25,35,45,55 0-7 * * *";
const PREWARM_CRON = "55 23 * * *";

const WEB_URL = "https://villagecoverage-public-demo-web.onrender.com/";
const API_URL = "https://villagecoverage-public-demo-api.onrender.com/health";
const INTEGRATED_URL = "https://villagecoverage-public-demo-web.onrender.com/api/health";

// Deterministic virtual clock that is correct for parallel probes: sleep() parks the caller and
// the driver advances time to the earliest timer only once every task is blocked.
function createVirtualTime(startIso) {
  const startMs = Date.parse(startIso);
  let elapsed = 0;
  const timers = [];
  return {
    get elapsed() {
      return elapsed;
    },
    advance(ms) {
      elapsed += ms;
    },
    now: () => new Date(startMs + elapsed),
    monotonic: () => elapsed,
    sleep: (ms) =>
      new Promise((resolve) => {
        timers.push({ at: elapsed + ms, resolve });
      }),
    async drive(promise) {
      let done = false;
      const tracked = promise.finally(() => {
        done = true;
      });
      while (!done) {
        for (let i = 0; i < 4 && !done; i += 1) await new Promise((r) => setImmediate(r));
        if (done) break;
        if (timers.length > 0) {
          timers.sort((a, b) => a.at - b.at);
          const next = timers.shift();
          elapsed = Math.max(elapsed, next.at);
          next.resolve();
        }
      }
      return tracked;
    },
  };
}

async function runVirtual({ cron = CRON, startIso = "2026-11-04T03:10:00.000Z", fetchFor, latency = 0 }) {
  const vt = createVirtualTime(startIso);
  const logs = [];
  const requests = [];
  let inflight = 0;
  let peakInflight = 0;
  const result = await vt.drive(
    runScheduledCheck(
      { cron, scheduledTime: Date.parse(startIso) },
      {
        now: vt.now,
        monotonic: vt.monotonic,
        sleep: vt.sleep,
        emit: (entry) => logs.push(entry),
        fetchImpl: async (url, options) => {
          const at = vt.elapsed;
          requests.push({ url, at, options, now: vt.now() });
          inflight += 1;
          peakInflight = Math.max(peakInflight, inflight);
          try {
            await Promise.resolve();
            if (latency) vt.advance(latency);
            return await fetchFor(url, at, requests.filter((r) => r.url === url).length);
          } finally {
            inflight -= 1;
          }
        },
      },
    ),
  );
  const complete = logs.find((entry) => entry.event === "scheduled_complete");
  return { result, logs, requests, vt, peakInflight, complete };
}

const timesFor = (requests, url) => requests.filter((r) => r.url === url).map((r) => r.at);
const summaryFor = (complete, service) => complete.endpoints.find((ep) => ep.service === service);

function plain(status, headers = {}) {
  return new Response("busy", { status, headers: { "Content-Type": "text/plain", ...headers } });
}

function responseFor(url, status = 200) {
  if (url.endsWith("/health") || url.endsWith("/api/health")) {
    return new Response(JSON.stringify({ status: "ok" }), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response("<html><title>VillageCoverage</title></html>", {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

test("KST window includes 08:55 and excludes 18:00", () => {
  assert.equal(isInBusinessWindow(new Date("2026-11-04T23:55:00.000Z")), true);
  assert.equal(isInBusinessWindow(new Date("2026-11-04T08:59:00.000Z")), true);
  assert.equal(isInBusinessWindow(new Date("2026-11-04T09:00:00.000Z")), false);
});

test("normal cron GETs Web and API, validates both and records actual schedule delay", async () => {
  const requests = [];
  const logs = [];
  const now = () => new Date("2026-11-04T03:10:00.000Z");
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now,
      sleep: async () => {},
      emit: (entry) => logs.push(entry),
      fetchImpl: async (url, options) => {
        requests.push({ url, options });
        return responseFor(url);
      },
    },
  );

  assert.deepEqual(result, { outcome: "ok", successes: 2, failures: 0, skipped: 0 });
  assert.equal(requests.length, 2);
  assert.ok(requests.every(({ options }) => options.method === "GET"));
  assert.ok(requests.every(({ options }) => options.redirect === "manual"));
  assert.equal(logs[0].scheduled_delay_seconds, 300);
});

test("08:55 pre-warm checks existing integrated health route too", async () => {
  const requests = [];
  const result = await runScheduledCheck(
    { cron: PREWARM_CRON, scheduledTime: Date.parse("2026-11-04T23:55:00.000Z") },
    {
      now: () => new Date("2026-11-04T23:55:01.000Z"),
      sleep: async () => {},
      emit: () => {},
      fetchImpl: async (url) => {
        requests.push(url);
        return responseFor(url);
      },
    },
  );
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  assert.equal(requests.length, 3);
  assert.ok(requests.some((url) => url.endsWith("/api/health")));
});

test("Web HTML validation uses the same bounded prefix for large pages", async () => {
  const largeHtml = `<html><title>VillageCoverage</title>${"x".repeat(5_000)}</html>`;
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      sleep: async () => {},
      emit: () => {},
      fetchImpl: async (url) => {
        if (url === "https://villagecoverage-public-demo-web.onrender.com/") {
          return new Response(largeHtml, {
            status: 200,
            headers: { "Content-Type": "text/html; charset=utf-8" },
          });
        }
        return responseFor(url);
      },
    },
  );
  assert.deepEqual(result, { outcome: "ok", successes: 2, failures: 0, skipped: 0 });
});

test("503 health response retries, recovers to 200, and checks integrated health", async () => {
  const counts = new Map();
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      sleep: async () => {},
      emit: () => {},
      fetchImpl: async (url) => {
        const count = (counts.get(url) ?? 0) + 1;
        counts.set(url, count);
        return responseFor(url, url === "https://villagecoverage-public-demo-api.onrender.com/health" && count === 1 ? 503 : 200);
      },
    },
  );
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  assert.equal([...counts.values()].reduce((total, count) => total + count, 0), 4);
});

test("Retry-After beyond the remaining 150 second endpoint budget fails without an early retry", async () => {
  const requests = [];
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      sleep: async () => {},
      emit: () => {},
      fetchImpl: async (url) => {
        requests.push(url);
        if (url.endsWith("/health")) {
          return new Response("busy", {
            status: 429,
            headers: { "Content-Type": "text/plain", "Retry-After": "301" },
          });
        }
        return responseFor(url);
      },
    },
  );
  assert.equal(result.outcome, "failed");
  // Web, API once. Integrated health is skipped because API failed (no repeat calls).
  assert.equal(requests.length, 2);
});

test("429 Retry-After is honored before a bounded retry", async () => {
  const requests = [];
  const sleeps = [];
  const logs = [];
  let apiAttempts = 0;
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      monotonic: () => 0,
      sleep: async (milliseconds) => sleeps.push(milliseconds),
      emit: (entry) => logs.push(entry),
      fetchImpl: async (url) => {
        requests.push(url);
        if (url.endsWith("/health")) {
          apiAttempts += 1;
          if (apiAttempts === 1) {
            return new Response("busy", {
              status: 429,
              headers: { "Content-Type": "text/plain", "Retry-After": "90" },
            });
          }
        }
        return responseFor(url);
      },
    },
  );
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  assert.deepEqual(sleeps, [90_000]);
  assert.equal(requests.length, 4);
  assert.ok(logs.some((entry) => entry.retry_after === true));
});

test("unknown cron fails closed without a GET", async () => {
  let requested = false;
  const result = await runScheduledCheck(
    { cron: "* * * * *", scheduledTime: Date.now() },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      emit: () => {},
      fetchImpl: async () => {
        requested = true;
        throw new Error("unexpected request");
      },
    },
  );
  assert.equal(result.outcome, "invalid_schedule");
  assert.equal(requested, false);
});

test("out-of-window scheduled event issues no GET", async () => {
  let requested = false;
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T09:01:00.000Z") },
    {
      now: () => new Date("2026-11-04T09:01:00.000Z"),
      emit: () => {},
      fetchImpl: async () => {
        requested = true;
        throw new Error("unexpected request");
      },
    },
  );
  assert.equal(result.outcome, "skipped_window");
  assert.equal(requested, false);
});

test("cold start retries recover Web after 40s and API after 90s", async () => {
  const readyAfter = new Map([
    [WEB_URL, 40_000],
    [API_URL, 90_000],
    [INTEGRATED_URL, 0],
  ]);
  const { result, logs, requests, vt } = await runVirtual({
    fetchFor: async (url, at) => {
      return at < readyAfter.get(url) ? responseFor(url, 503) : responseFor(url);
    },
  });
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  assert.ok(timesFor(requests, WEB_URL).length >= 5);
  assert.ok(timesFor(requests, API_URL).length >= 7);
  assert.equal(timesFor(requests, INTEGRATED_URL).length, 1);
  assert.ok(logs.some((entry) => entry.service === "web" && entry.outcome === "recovered"));
  assert.ok(logs.some((entry) => entry.service === "api" && entry.outcome === "recovered"));
  assert.ok(vt.elapsed <= 180_000);
});

test("no new ping starts at or after 18:00 KST", async () => {
  const clock = { elapsed: 0 };
  const start = new Date("2026-11-04T08:59:50.000Z"); // 17:59:50 KST
  const requestTimes = [];
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T08:55:00.000Z") },
    {
      now: () => new Date(start.getTime() + clock.elapsed),
      monotonic: () => clock.elapsed,
      sleep: async (milliseconds) => {
        clock.elapsed += milliseconds;
      },
      emit: () => {},
      fetchImpl: async (url) => {
        requestTimes.push({ url, now: new Date(start.getTime() + clock.elapsed) });
        return url.endsWith("/api/health") ? responseFor(url) : responseFor(url, 503);
      },
    },
  );
  assert.equal(result.outcome, "failed");
  assert.ok(requestTimes.length > 0);
  assert.ok(requestTimes.every(({ now }) => isInBusinessWindow(now)));
  assert.ok(requestTimes.every(({ now }) => now.getTime() < Date.parse("2026-11-04T09:00:00.000Z")));
  assert.ok(clock.elapsed < 10_000);
});

test("invalid health JSON fails after bounded retries and does not log response data", async () => {
  const logs = [];
  const counts = new Map();
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date("2026-11-04T03:10:00.000Z"),
      sleep: async () => {},
      emit: (entry) => logs.push(entry),
      fetchImpl: async (url) => {
        counts.set(url, (counts.get(url) ?? 0) + 1);
        if (url.endsWith("/health")) {
          return new Response("resident-private-data", {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return responseFor(url);
      },
    },
  );

  assert.equal(result.outcome, "failed");
  assert.equal(counts.get("https://villagecoverage-public-demo-web.onrender.com/"), 1);
  assert.equal(counts.get("https://villagecoverage-public-demo-api.onrender.com/health"), 12);
  // API failed, so the integrated route is not probed at all.
  assert.equal(counts.get("https://villagecoverage-public-demo-web.onrender.com/api/health"), undefined);
  assert.ok(logs.every((entry) => !JSON.stringify(entry).includes("resident-private-data")));
});

test("observability logs capture scheduled_at, started_at, GET dispatch, HTTP status, retries, elapsed_ms, outcome, failure and wrangler.toml enables Workers Logs", async () => {
  const fs = await import("node:fs/promises");
  const wranglerToml = await fs.readFile(new URL("../wrangler.toml", import.meta.url), "utf8");
  assert.match(wranglerToml, /^\[observability\]/m);
  assert.match(wranglerToml, /^enabled\s*=\s*true/m);
  assert.match(wranglerToml, /^head_sampling_rate\s*=\s*1\b/m);

  const logs = [];
  let apiCalls = 0;
  let elapsed = 0;
  const baseMs = Date.parse("2026-11-04T03:05:12.000Z");
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date(baseMs + elapsed),
      monotonic: () => elapsed,
      sleep: async (ms) => {
        elapsed += ms;
      },
      emit: (entry) => logs.push(entry),
      fetchImpl: async (url) => {
        elapsed += 120;
        if (url.endsWith("/health")) {
          apiCalls += 1;
          if (apiCalls === 1) {
            return responseFor(url, 503);
          }
        }
        return responseFor(url, 200);
      },
    },
  );

  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  const startLog = logs.find((entry) => entry.event === "scheduled_start");
  assert.equal(startLog.scheduled_at, "2026-11-04T03:05:00.000Z");
  assert.equal(startLog.started_at, "2026-11-04T03:05:12.000Z");
  assert.equal(startLog.scheduled_delay_seconds, 12);

  const attemptLogs = logs.filter((entry) => entry.event === "endpoint_attempt");
  assert.equal(attemptLogs.length, 4);
  assert.ok(attemptLogs.every((entry) => entry.method === "GET" && entry.request_sent === true));

  const completeLog = logs.find((entry) => entry.event === "scheduled_complete");
  assert.equal(completeLog.scheduled_at, "2026-11-04T03:05:00.000Z");
  assert.equal(completeLog.started_at, "2026-11-04T03:05:12.000Z");
  assert.equal(completeLog.request_sent, true);
  assert.equal(completeLog.total_attempts, 4);
  assert.equal(completeLog.total_retries, 1);
  assert.ok(completeLog.elapsed_ms >= 5_000);
  assert.equal(completeLog.outcome, "ok");
  const apiSummary = completeLog.endpoints.find((ep) => ep.service === "api");
  assert.deepEqual(apiSummary, {
    service: "api",
    request_sent: true,
    status: 200,
    attempts: 2,
    retries: 1,
    elapsed_ms: apiSummary.elapsed_ms,
    outcome: "recovered",
    failure: "ok",
  });
});

test("persistent 503 on the 08:55 pre-warm stays well below the Free 50-subrequest limit", async () => {
  const { result, requests, vt } = await runVirtual({
    cron: PREWARM_CRON,
    startIso: "2026-11-04T23:55:00.000Z",
    fetchFor: async (url) => responseFor(url, 503),
  });
  assert.equal(result.outcome, "failed");
  // 12 Web + 12 API attempts at 10 s spacing; integrated health is skipped after a Web/API failure.
  assert.equal(requests.length, 24);
  assert.equal(timesFor(requests, INTEGRATED_URL).length, 0);
  assert.ok(vt.elapsed <= 180_000);
});

test("even with a frozen clock the attempt caps bound one invocation below the Free 50-subrequest limit", async () => {
  let fetches = 0;
  await runScheduledCheck(
    { cron: PREWARM_CRON, scheduledTime: Date.parse("2026-11-04T23:55:00.000Z") },
    {
      now: () => new Date("2026-11-04T23:55:00.000Z"),
      monotonic: () => 0,
      sleep: async () => {},
      emit: () => {},
      fetchImpl: async (url) => {
        fetches += 1;
        return responseFor(url, 503);
      },
    },
  );
  assert.equal(fetches, 24);
  assert.ok(fetches < 50);
});

test("wrangler.nocron.toml deploys the same Worker with every Cron Trigger removed", async () => {
  const fs = await import("node:fs/promises");
  const read = (name) => fs.readFile(new URL(`../${name}`, import.meta.url), "utf8");
  const [cron, nocron] = await Promise.all([read("wrangler.toml"), read("wrangler.nocron.toml")]);
  for (const key of ["name", "main", "compatibility_date", "workers_dev"]) {
    const line = new RegExp(`^${key}\\s*=.*$`, "m");
    assert.equal(nocron.match(line)?.[0], cron.match(line)?.[0]);
  }
  assert.match(nocron, /^\[triggers\]\s*\ncrons\s*=\s*\[\]\s*$/m);
  assert.match(nocron, /^enabled\s*=\s*true/m);
});

// ---------------------------------------------------------------------------
// B-plan regression tests: status-specific retry, budgets, parallel probes, diagnostics.
// ---------------------------------------------------------------------------

test("[1] persistent 429 stops after 5 attempts per endpoint, 30 s apart, well inside the run budget", async () => {
  const { result, requests, vt, complete } = await runVirtual({
    fetchFor: async () => plain(429),
  });
  assert.equal(result.outcome, "failed");
  assert.deepEqual(timesFor(requests, WEB_URL), [0, 30_000, 60_000, 90_000, 120_000]);
  assert.deepEqual(timesFor(requests, API_URL), [0, 30_000, 60_000, 90_000, 120_000]);
  assert.equal(timesFor(requests, INTEGRATED_URL).length, 0);
  assert.equal(requests.length, 10); // the 10:15 incident made 30 requests over ~8 minutes
  assert.equal(vt.elapsed, 120_000);
  assert.ok(vt.elapsed <= 180_000);
  assert.equal(summaryFor(complete, "web").failure, "rate_limited_max_attempts");
  assert.equal(complete.integrated_health, "skipped_prior_failure");
});

test("[2] observed 429 -> 503 -> 200 flow (429 until ~95 s, 503 until ~135 s) is recovered, not failed early", async () => {
  const phase = (at, ready) => (at < ready - 40_000 ? 429 : at < ready ? 503 : 200);
  const { result, requests, vt, complete, logs } = await runVirtual({
    fetchFor: async (url, at) => {
      if (url === WEB_URL) return responseForPhase(url, phase(at, 135_000));
      if (url === API_URL) return responseForPhase(url, phase(at, 125_000));
      return responseFor(url);
    },
  });
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  // 429 at 0/30/60/90 (still limited at 95 s), 503 at 120/130, 200 at 140 s: 10 s of margin.
  assert.deepEqual(timesFor(requests, WEB_URL), [0, 30_000, 60_000, 90_000, 120_000, 130_000, 140_000]);
  assert.equal(summaryFor(complete, "web").outcome, "recovered");
  assert.equal(summaryFor(complete, "api").outcome, "recovered");
  assert.equal(timesFor(requests, INTEGRATED_URL).length, 1);
  assert.ok(vt.elapsed <= 150_000);
  const statuses = logs.filter((e) => e.event === "endpoint_attempt" && e.service === "web").map((e) => e.status);
  assert.deepEqual(statuses, [429, 429, 429, 429, 503, 503, 200]);
});

function responseForPhase(url, status) {
  return status === 429 ? plain(429) : responseFor(url, status);
}

test("[3] 503 lasting 100 s (Render cold start) recovers at 10 s spacing; 160 s exhausts the bounded policy", async () => {
  const recovered = await runVirtual({
    fetchFor: async (url, at) => (url === WEB_URL && at < 100_000 ? responseFor(url, 503) : responseFor(url)),
  });
  assert.equal(recovered.result.outcome, "ok");
  assert.equal(timesFor(recovered.requests, WEB_URL).length, 11);
  assert.ok(timesFor(recovered.requests, WEB_URL).every((at, i, all) => i === 0 || at - all[i - 1] === 10_000));
  assert.equal(timesFor(recovered.requests, INTEGRATED_URL).length, 1);

  const exhausted = await runVirtual({
    fetchFor: async (url, at) => (url === WEB_URL && at < 160_000 ? responseFor(url, 503) : responseFor(url)),
  });
  assert.equal(exhausted.result.outcome, "failed");
  assert.equal(timesFor(exhausted.requests, WEB_URL).length, 12);
  assert.equal(summaryFor(exhausted.complete, "web").failure, "maximum_attempts_exhausted");
  assert.equal(timesFor(exhausted.requests, INTEGRATED_URL).length, 0);
  assert.ok(exhausted.vt.elapsed <= 150_000);
});

test("[4] Web failure does not block or delay the API check", async () => {
  const { result, requests, complete } = await runVirtual({
    fetchFor: async (url) => (url === WEB_URL ? responseFor(url, 503) : responseFor(url)),
  });
  assert.equal(result.outcome, "failed");
  assert.equal(timesFor(requests, API_URL).length, 1);
  assert.equal(timesFor(requests, API_URL)[0], 0); // started at t=0, not after Web's ~110 s of retries
  assert.equal(summaryFor(complete, "api").outcome, "healthy");
  assert.equal(summaryFor(complete, "web").outcome, "failed");
  assert.equal(summaryFor(complete, "web").attempts, 12);
  assert.equal(timesFor(requests, INTEGRATED_URL).length, 0);
});

test("[5] API failure is recorded independently of a healthy Web", async () => {
  const { result, requests, complete } = await runVirtual({
    fetchFor: async (url) => (url === API_URL ? plain(429) : responseFor(url)),
  });
  assert.equal(result.outcome, "failed");
  assert.equal(result.successes, 1);
  assert.equal(result.failures, 1);
  assert.equal(summaryFor(complete, "web").outcome, "healthy");
  assert.equal(summaryFor(complete, "web").attempts, 1);
  assert.equal(summaryFor(complete, "api").status, 429);
  assert.equal(summaryFor(complete, "api").failure, "rate_limited_max_attempts");
  assert.equal(timesFor(requests, WEB_URL).length, 1);
});

test("[5b] an exception in one probe is isolated (Promise.allSettled)", async () => {
  const { result, complete, logs } = await runVirtual({
    fetchFor: async (url) => {
      if (url === API_URL) throw new TypeError("boom with resident-private-data");
      return responseFor(url);
    },
  });
  assert.equal(result.outcome, "failed");
  assert.equal(summaryFor(complete, "web").outcome, "healthy");
  assert.equal(summaryFor(complete, "api").failure, "maximum_attempts_exhausted");
  const apiDone = logs.find((e) => e.event === "endpoint_complete" && e.service === "api");
  assert.equal(apiDone.last_cause, "network_error"); // underlying cause survives the stop reason
  assert.ok(logs.every((entry) => !JSON.stringify(entry).includes("resident-private-data")));
});

test("[6a] Retry-After: integer seconds and HTTP-date are honored; tiny values are floored to 5 s", async () => {
  const sleepsFor = async (headerValue, status = 429) => {
    const { requests, complete } = await runVirtual({
      fetchFor: async (url, at, count) => {
        if (url === API_URL && count === 1) return plain(status, { "Retry-After": headerValue });
        return responseFor(url);
      },
    });
    assert.equal(complete.outcome, "ok");
    return timesFor(requests, API_URL);
  };
  assert.deepEqual(await sleepsFor("45"), [0, 45_000]);
  assert.deepEqual(await sleepsFor("Wed, 04 Nov 2026 03:11:00 GMT"), [0, 60_000]);
  assert.deepEqual(await sleepsFor("1"), [0, 5_000]);
  assert.deepEqual(await sleepsFor("0", 503), [0, 5_000]);
  assert.deepEqual(await sleepsFor("20", 503), [0, 20_000]);
});

test("[6b] invalid Retry-After values are ignored: 429 falls back to 30 s, 503 to 10 s", async () => {
  for (const bad of ["soon", "-5", "1e3", "12.5", "", "Wed, 99 Foo 2026 25:61:61 GMT", "5 seconds", "9".repeat(20)]) {
    const rate = await runVirtual({
      fetchFor: async (url, at, count) =>
        url === API_URL && count === 1 ? plain(429, { "Retry-After": bad }) : responseFor(url),
    });
    assert.deepEqual(timesFor(rate.requests, API_URL), [0, 30_000], `429 with ${JSON.stringify(bad)}`);
    const down = await runVirtual({
      fetchFor: async (url, at, count) =>
        url === API_URL && count === 1 ? responseFor(url, 503) : responseFor(url),
    });
    assert.deepEqual(timesFor(down.requests, API_URL), [0, 10_000]);
  }
});

test("[6c] Retry-After beyond the remaining budget stops immediately without sleeping", async () => {
  const over = await runVirtual({
    fetchFor: async (url) => (url === API_URL ? plain(429, { "Retry-After": "151" }) : responseFor(url)),
  });
  assert.deepEqual(timesFor(over.requests, API_URL), [0]);
  assert.equal(summaryFor(over.complete, "api").failure, "retry_after_exceeds_remaining_budget");
  assert.equal(summaryFor(over.complete, "api").outcome, "retry_budget_exhausted");
  assert.equal(over.complete.budget_exhausted, true);
  assert.equal(over.vt.elapsed, 0);

  // 100 s consumed by the first wait leaves 50 s; a second Retry-After of 100 s must not be waited.
  const second = await runVirtual({
    fetchFor: async (url) => (url === API_URL ? plain(429, { "Retry-After": "100" }) : responseFor(url)),
  });
  assert.deepEqual(timesFor(second.requests, API_URL), [0, 100_000]);
  assert.equal(summaryFor(second.complete, "api").failure, "retry_after_exceeds_remaining_budget");
  assert.ok(second.vt.elapsed <= 150_000);

  // HTTP-date far in the future is also bounded.
  const dated = await runVirtual({
    fetchFor: async (url) =>
      url === API_URL ? plain(503, { "Retry-After": "Thu, 05 Nov 2026 03:10:00 GMT" }) : responseFor(url),
  });
  assert.deepEqual(timesFor(dated.requests, API_URL), [0]);
});

test("[7] retries never cross 18:00 KST: no GET at or after 18:00:00", async () => {
  for (const [startIso, expectedLastAt] of [
    ["2026-11-04T08:59:50.000Z", 0], // 17:59:50 + 10 s lands exactly on 18:00:00 -> refused
    ["2026-11-04T08:59:39.000Z", 20_000], // 17:59:39, 49, 59 -> next would be 18:00:09
  ]) {
    const run = await runVirtual({ startIso, fetchFor: async (url) => responseFor(url, 503) });
    assert.equal(run.result.outcome, "failed");
    assert.ok(run.requests.every((r) => r.now.getTime() < Date.parse("2026-11-04T09:00:00.000Z")));
    assert.ok(run.requests.every((r) => isInBusinessWindow(r.now)));
    assert.equal(Math.max(...run.requests.map((r) => r.at)), expectedLastAt);
    assert.equal(summaryFor(run.complete, "web").failure, "retry_would_cross_1800_kst");
  }
  // Long Retry-After that would land after 18:00 is refused before sleeping.
  const run = await runVirtual({
    startIso: "2026-11-04T08:58:00.000Z",
    fetchFor: async (url) => plain(429, { "Retry-After": "120" }),
  });
  assert.equal(run.requests.length, 2);
  assert.ok(run.requests.every((r) => r.now.getTime() < Date.parse("2026-11-04T09:00:00.000Z")));
  // A start exactly at 18:00:00 sends nothing.
  const closed = await runVirtual({
    startIso: "2026-11-04T09:00:00.000Z",
    fetchFor: async () => {
      throw new Error("unexpected request");
    },
  });
  assert.equal(closed.requests.length, 0);
  assert.equal(closed.result.outcome, "skipped_window");
});

test("[8] Cloudflare Free limits: subrequests < 50 and at most 2 concurrent outbound requests", async () => {
  for (const scenario of [
    { cron: PREWARM_CRON, startIso: "2026-11-04T23:55:00.000Z", status: 503 },
    { cron: CRON, startIso: "2026-11-04T03:10:00.000Z", status: 503 },
    { cron: CRON, startIso: "2026-11-04T03:10:00.000Z", status: 429 },
  ]) {
    const run = await runVirtual({
      cron: scenario.cron,
      startIso: scenario.startIso,
      fetchFor: async (url) => (scenario.status === 429 ? plain(429) : responseFor(url, 503)),
    });
    assert.ok(run.requests.length <= 28, `${run.requests.length} requests`);
    assert.ok(run.requests.length < 50);
    assert.ok(run.peakInflight <= 2);
  }
  const healthy = await runVirtual({
    cron: PREWARM_CRON,
    startIso: "2026-11-04T23:55:00.000Z",
    fetchFor: async (url) => responseFor(url),
  });
  assert.equal(healthy.peakInflight, 2); // Web and API really run in parallel
  assert.equal(healthy.requests.length, 3);
  // Worst case of the policy itself: 12 + 12 + 4.
  assert.equal(12 + 12 + 4 < 50, true);
});

test("[9] logs are allowlisted and bounded: no cookie, token, body or control characters", async () => {
  const secret = "SESSION-SECRET-TOKEN-123";
  const { logs } = await runVirtual({
    fetchFor: async (url) =>
      new Response(`body-with-${secret}-resident-private-data`, {
        status: 503,
        headers: {
          "Content-Type": "text/plain",
          "Set-Cookie": `sid=${secret}; HttpOnly`,
          Authorization: `Bearer ${secret}`,
          "X-Api-Key": secret,
          Server: `cloudflare\t${"x".repeat(200)}`,
          "CF-Ray": "8abc123def456-ICN",
          "x-render-routing": "no-server",
          "rndr-id": "abcd-1234",
          "Retry-After": "bad-value",
        },
      }),
  });
  const text = JSON.stringify(logs);
  for (const forbidden of [secret, "sid=", "resident-private-data", "Bearer", "Set-Cookie", "set-cookie", "api_key", "authorization"]) {
    assert.ok(!text.toLowerCase().includes(forbidden.toLowerCase()), forbidden);
  }
  const attempt = logs.find((entry) => entry.event === "endpoint_attempt");
  assert.equal(attempt.cf_ray, "8abc123def456-ICN");
  assert.equal(attempt.render_routing, "no-server");
  assert.equal(attempt.render_id, "abcd-1234");
  assert.equal(attempt.retry_after_header, "bad-value");
  assert.equal(attempt.server.length, 64);
  for (const entry of logs.filter((e) => e.event === "endpoint_attempt")) {
    for (const key of ["server", "cf_ray", "render_routing", "render_id", "retry_after_header"]) {
      assert.ok(entry[key] === null || (entry[key].length <= 64 && !/[^\x20-\x7e]/.test(entry[key])), key);
    }
  }
  assert.ok(logs.length <= 80);
  const allowed = new Set([
    "event", "service", "method", "request_sent", "attempt", "retries", "status", "elapsed_ms", "failure", "outcome",
    "retry_after_header", "server", "cf_ray", "render_routing", "render_id", "attempts", "retry_in_ms", "retry_after",
    "retry_delay_ms", "retry_after_ms", "remaining_budget_ms", "reason", "error_name", "cron", "scheduled_at",
    "started_at", "scheduled_delay_seconds", "total_attempts", "total_retries", "run_budget_ms", "endpoint_budget_ms",
    "budget_exhausted", "last_cause", "integrated_health", "endpoints", "successes", "failures", "skipped",
  ]);
  for (const entry of logs) {
    for (const key of Object.keys(entry)) assert.ok(allowed.has(key), `unexpected log key ${key}`);
  }
});

test("[10] execution budget: slow or timing-out requests still finish within 180 s", async () => {
  // Every request times out after 10 s (TimeoutError).
  const timeouts = await runVirtual({
    fetchFor: async () => {
      throw new DOMException("timed out", "TimeoutError");
    },
    latency: 10_000,
  });
  assert.equal(timeouts.result.outcome, "failed");
  assert.ok(timeouts.vt.elapsed <= 180_000, `${timeouts.vt.elapsed}`);
  assert.ok(timeouts.requests.every((r) => r.options.signal instanceof AbortSignal));
  assert.ok(timeouts.requests.length <= 24);

  // Slow 503s: 9.5 s each plus 10 s waits.
  const slow = await runVirtual({ fetchFor: async (url) => responseFor(url, 503), latency: 9_500 });
  assert.equal(slow.result.outcome, "failed");
  assert.ok(slow.vt.elapsed <= 180_000, `${slow.vt.elapsed}`);
  assert.ok(slow.complete.elapsed_ms <= 180_000);
  assert.ok(slow.requests.length < 50);

  // A response completing after the endpoint budget is not retried.
  const late = await runVirtual({
    fetchFor: async (url) => responseFor(url, 503),
    latency: 160_000,
  });
  assert.equal(late.requests.length, 2);
  assert.ok(late.complete.budget_exhausted);
});

test("integrated health: skipped on a clean normal run, checked once after recovery, skipped if Web failed on pre-warm", async () => {
  const clean = await runVirtual({ fetchFor: async (url) => responseFor(url) });
  assert.equal(clean.complete.integrated_health, "not_needed");
  assert.equal(timesFor(clean.requests, INTEGRATED_URL).length, 0);

  const recovered = await runVirtual({
    fetchFor: async (url, at) => (url === API_URL && at < 10_000 ? responseFor(url, 503) : responseFor(url)),
  });
  assert.equal(recovered.complete.integrated_health, "checked");
  assert.equal(timesFor(recovered.requests, INTEGRATED_URL).length, 1);

  const webDownPrewarm = await runVirtual({
    cron: PREWARM_CRON,
    startIso: "2026-11-04T23:55:00.000Z",
    fetchFor: async (url) => (url === WEB_URL ? responseFor(url, 503) : responseFor(url)),
  });
  assert.equal(webDownPrewarm.complete.integrated_health, "skipped_prior_failure");
  assert.equal(timesFor(webDownPrewarm.requests, INTEGRATED_URL).length, 0);
});

test("non-retryable statuses (404, 3xx) fail on the first attempt", async () => {
  const { requests, complete } = await runVirtual({
    fetchFor: async (url) => (url === WEB_URL ? new Response("nf", { status: 404 }) : responseFor(url)),
  });
  assert.equal(timesFor(requests, WEB_URL).length, 1);
  assert.equal(summaryFor(complete, "web").outcome, "failed");
});
