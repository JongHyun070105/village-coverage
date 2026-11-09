import assert from "node:assert/strict";
import test from "node:test";
import { isInBusinessWindow, runScheduledCheck } from "../src/index.mjs";

const CRON = "5,15,25,35,45,55 0-7 * * *";
const PREWARM_CRON = "55 23 * * *";

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

test("Retry-After beyond the 180 second bound fails without an early retry", async () => {
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
  assert.equal(requests.length, 3); // Web, API once, then integrated health.
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
  const clock = { elapsed: 0 };
  const base = new Date("2026-11-04T03:10:00.000Z");
  const readyAfter = new Map([
    ["https://villagecoverage-public-demo-web.onrender.com/", 40_000],
    ["https://villagecoverage-public-demo-api.onrender.com/health", 90_000],
    ["https://villagecoverage-public-demo-web.onrender.com/api/health", 0],
  ]);
  const firstRequestAt = new Map();
  const counts = new Map();
  const logs = [];
  const result = await runScheduledCheck(
    { cron: CRON, scheduledTime: Date.parse("2026-11-04T03:05:00.000Z") },
    {
      now: () => new Date(base.getTime() + clock.elapsed),
      monotonic: () => clock.elapsed,
      sleep: async (milliseconds) => {
        clock.elapsed += milliseconds;
      },
      emit: (entry) => logs.push(entry),
      fetchImpl: async (url) => {
        counts.set(url, (counts.get(url) ?? 0) + 1);
        firstRequestAt.set(url, firstRequestAt.get(url) ?? clock.elapsed);
        if (clock.elapsed - firstRequestAt.get(url) < readyAfter.get(url)) {
          return responseFor(url, 503);
        }
        return responseFor(url);
      },
    },
  );
  assert.deepEqual(result, { outcome: "ok", successes: 3, failures: 0, skipped: 0 });
  assert.ok(counts.get("https://villagecoverage-public-demo-web.onrender.com/") >= 5);
  assert.ok(counts.get("https://villagecoverage-public-demo-api.onrender.com/health") >= 7);
  assert.equal(counts.get("https://villagecoverage-public-demo-web.onrender.com/api/health"), 1);
  assert.ok(logs.some((entry) => entry.service === "web" && entry.outcome === "recovered"));
  assert.ok(logs.some((entry) => entry.service === "api" && entry.outcome === "recovered"));
  assert.ok(clock.elapsed <= 8 * 60_000);
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
  assert.equal(
    counts.get("https://villagecoverage-public-demo-api.onrender.com/health"),
    16,
  );
  assert.equal(
    counts.get("https://villagecoverage-public-demo-web.onrender.com/api/health"),
    16,
  );
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
