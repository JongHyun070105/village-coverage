const PREWARM_CRON = "55 23 * * *";
const ALLOWED_CRONS = new Set([
  PREWARM_CRON,
  "5,15,25,35,45,55 0-7 * * *",
  "5,15,25,35,45 8 * * *",
]);

const WINDOW_START_MINUTE = 8 * 60 + 55;
const WINDOW_END_MINUTE = 18 * 60;
const MAX_ATTEMPTS = 16;
const REQUEST_TIMEOUT_MS = 10_000;
const ENDPOINT_RECOVERY_BUDGET_MS = 4 * 60_000;
const MAX_RUN_MS = 8 * 60_000;
const RETRY_BASE_MS = 5_000;
const RETRY_MAX_MS = 20_000;
const MAX_RETRY_AFTER_MS = 3 * 60_000;
const MAX_BODY_BYTES = 4_096;
const USER_AGENT = "villagecoverage-cloudflare-keepalive-poc/1";

const WEB = {
  name: "web",
  url: "https://villagecoverage-public-demo-web.onrender.com/",
  kind: "html",
};
const API = {
  name: "api",
  url: "https://villagecoverage-public-demo-api.onrender.com/health",
  kind: "health",
};
const INTEGRATED = {
  name: "integrated-health",
  url: "https://villagecoverage-public-demo-web.onrender.com/api/health",
  kind: "health",
};
const ALLOWED_URLS = new Set([WEB.url, API.url, INTEGRATED.url]);

const kstClock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Seoul",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

export function isInBusinessWindow(instant) {
  const parts = Object.fromEntries(
    kstClock.formatToParts(instant).map(({ type, value }) => [type, value]),
  );
  const minute = Number(parts.hour) * 60 + Number(parts.minute);
  return minute >= WINDOW_START_MINUTE && minute < WINDOW_END_MINUTE;
}

function millisecondsUntilWindowEnd(instant) {
  const parts = Object.fromEntries(
    kstClock.formatToParts(instant).map(({ type, value }) => [type, value]),
  );
  const elapsedMs =
    (Number(parts.hour) * 60 * 60 + Number(parts.minute) * 60 + Number(parts.second)) * 1_000 +
    instant.getMilliseconds();
  return Math.max(0, 18 * 60 * 60 * 1_000 - elapsedMs);
}

function retryAfterMs(value, nowMs) {
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isInteger(seconds) && seconds >= 0) {
    return seconds * 1_000;
  }
  const retryAt = Date.parse(value);
  if (!Number.isFinite(retryAt)) return null;
  return Math.max(0, retryAt - nowMs);
}

function retryableStatus(status) {
  return status === 429 || (status >= 500 && status <= 599);
}

function retryDelayMs(attempt) {
  return Math.min(RETRY_BASE_MS * 2 ** (attempt - 1), RETRY_MAX_MS);
}

async function readBoundedText(response) {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const boundedBody = new Uint8Array(MAX_BODY_BYTES);
  let size = 0;
  try {
    while (size < MAX_BODY_BYTES) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = value.subarray(0, Math.min(value.byteLength, MAX_BODY_BYTES - size));
      boundedBody.set(chunk, size);
      size += chunk.byteLength;
      if (chunk.byteLength < value.byteLength || size === MAX_BODY_BYTES) {
        await reader.cancel();
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }

  return new TextDecoder("utf-8", { fatal: false }).decode(boundedBody.subarray(0, size));
}

async function validateResponse(endpoint, response) {
  if (response.status !== 200) {
    await response.body?.cancel();
    return { ok: false, failure: "http_status", retryAfter: response.headers.get("Retry-After") };
  }

  const contentType = (response.headers.get("Content-Type") ?? "").toLowerCase();
  if (endpoint.kind === "html") {
    if (!contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
      await response.body?.cancel();
      return { ok: false, failure: "unexpected_content_type" };
    }
    const body = await readBoundedText(response);
    if (body === null) return { ok: false, failure: "body_too_large" };
    if (!/<html\b/i.test(body) || !/villagecoverage/i.test(body)) {
      return { ok: false, failure: "unexpected_body" };
    }
    return { ok: true, failure: "ok" };
  }

  if (!contentType.includes("json")) {
    await response.body?.cancel();
    return { ok: false, failure: "unexpected_content_type" };
  }
  const body = await readBoundedText(response);
  if (body === null) return { ok: false, failure: "body_too_large" };
  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return { ok: false, failure: "invalid_json" };
  }
  if (!payload || typeof payload !== "object" || payload.status !== "ok") {
    return { ok: false, failure: "unhealthy_json" };
  }
  return { ok: true, failure: "ok" };
}

function isTransientFailure(failure) {
  return [
    "unexpected_content_type",
    "unexpected_body",
    "body_too_large",
    "invalid_json",
    "unhealthy_json",
    "network_error",
    "timeout",
  ].includes(failure);
}

async function probe(endpoint, { fetchImpl, now, sleep, monotonic, emit, runDeadline }) {
  if (!ALLOWED_URLS.has(endpoint.url)) {
    emit({ service: endpoint.name, outcome: "blocked_url" });
    return { ok: false, failure: "blocked_url", status: null, attempts: 0, outcome: "failed" };
  }

  const endpointStarted = monotonic();
  const endpointDeadline = Math.min(endpointStarted + ENDPOINT_RECOVERY_BUDGET_MS, runDeadline);
  let recovered = false;
  let last = { ok: false, failure: "not_attempted", status: null, retryAfter: null };
  let attempts = 0;

  const finish = (outcome, stopReason = null) => {
    const result = {
      ...last,
      outcome,
      attempts,
      recovered,
      ...(stopReason ? { stopReason } : {}),
    };
    emit({
      service: endpoint.name,
      outcome,
      attempts,
      status: last.status,
      failure: last.failure,
      elapsed_ms: Math.max(0, Math.round(monotonic() - endpointStarted)),
    });
    return result;
  };

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    if (!isInBusinessWindow(now())) {
      return finish("skipped_window", "window_closed");
    }

    const remainingBudget = endpointDeadline - monotonic();
    if (remainingBudget <= 0) {
      last.failure = "endpoint_or_run_budget_exhausted";
      return finish("retry_budget_exhausted");
    }

    const startedAt = monotonic();
    attempts = attempt;
    let retryable = false;
    try {
      const response = await fetchImpl(endpoint.url, {
        method: "GET",
        redirect: "manual",
        cache: "no-store",
        headers: {
          Accept: "text/html, application/json",
          "User-Agent": USER_AGENT,
        },
        signal: AbortSignal.timeout(Math.max(1, Math.min(REQUEST_TIMEOUT_MS, remainingBudget))),
      });
      const validation = await validateResponse(endpoint, response);
      last = {
        ...validation,
        status: response.status,
        retryAfter: validation.retryAfter ?? response.headers.get("Retry-After"),
      };
      retryable = retryableStatus(response.status);
      emit({
        service: endpoint.name,
        attempt,
        status: response.status,
        elapsed_ms: Math.max(0, Math.round(monotonic() - startedAt)),
        failure: validation.failure,
        outcome: validation.ok ? "ok" : validation.failure,
      });
      if (monotonic() >= endpointDeadline) {
        last.failure = "request_completed_after_budget";
        return finish("retry_budget_exhausted");
      }
      if (validation.ok) {
        return finish(recovered ? "recovered" : "healthy");
      }
      retryable = retryable || isTransientFailure(validation.failure);
    } catch (error) {
      last = {
        ok: false,
        failure: error?.name === "TimeoutError" ? "timeout" : "network_error",
        status: null,
        retryAfter: null,
      };
      retryable = true;
      emit({
        service: endpoint.name,
        attempt,
        status: null,
        elapsed_ms: Math.max(0, Math.round(monotonic() - startedAt)),
        failure: last.failure,
        outcome: last.failure,
      });
      if (monotonic() >= endpointDeadline) {
        last.failure = "request_completed_after_budget";
        return finish("retry_budget_exhausted");
      }
    }

    if (!retryable || attempt === MAX_ATTEMPTS) {
      return finish("failed");
    }

    const retryAfter = retryAfterMs(last.retryAfter, now().getTime());
    if (retryAfter !== null && retryAfter > MAX_RETRY_AFTER_MS) {
      last.failure = "retry_after_exceeds_bound";
      emit({
        service: endpoint.name,
        outcome: "retry_after_exceeds_bound",
        status: last.status,
        retry_after_ms: retryAfter,
        max_retry_after_ms: MAX_RETRY_AFTER_MS,
      });
      return finish("failed");
    }

    const delay =
      retryAfter === null ? retryDelayMs(attempt) : Math.max(retryAfter, retryDelayMs(attempt));
    const availableWindow = millisecondsUntilWindowEnd(now());
    if (delay >= availableWindow) {
      last.failure = "retry_would_cross_1800_kst";
      emit({
        service: endpoint.name,
        outcome: "skipped_window_before_retry",
        status: last.status,
        retry_delay_ms: delay,
      });
      return finish("failed", "window_closed");
    }
    const remaining = endpointDeadline - monotonic();
    if (delay >= remaining) {
      last.failure = "retry_delay_exceeds_remaining_budget";
      emit({
        service: endpoint.name,
        outcome: "retry_budget_exhausted",
        status: last.status,
        retry_delay_ms: delay,
        remaining_budget_ms: Math.max(0, Math.floor(remaining)),
      });
      return finish("retry_budget_exhausted");
    }

    recovered = true;
    emit({
      service: endpoint.name,
      attempt,
      retry_in_ms: delay,
      retry_after: retryAfter !== null,
    });
    await sleep(delay);
  }

  last.failure = "maximum_attempts_exhausted";
  return finish("failed");
}

export async function runScheduledCheck(
  controller,
  {
    fetchImpl = globalThis.fetch,
    now = () => new Date(),
    sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
    monotonic = () => performance.now(),
    emit = (entry) => console.log(JSON.stringify(entry)),
  } = {},
) {
  if (!ALLOWED_CRONS.has(controller.cron)) {
    return { outcome: "invalid_schedule", successes: 0, failures: 0, skipped: 0 };
  }

  const endpoints = controller.cron === PREWARM_CRON ? [WEB, API, INTEGRATED] : [WEB, API];
  const startedAt = now();
  if (!isInBusinessWindow(startedAt)) {
    const result = { outcome: "skipped_window", successes: 0, failures: 0, skipped: endpoints.length };
    emit({ event: "scheduled_complete", ...result });
    return result;
  }

  const scheduledAt = new Date(controller.scheduledTime);
  const scheduledDelaySeconds = Number.isNaN(scheduledAt.getTime())
    ? null
    : Math.max(0, Math.floor((startedAt.getTime() - scheduledAt.getTime()) / 1_000));
  emit({
    event: "scheduled_start",
    cron: controller.cron,
    scheduled_at: Number.isNaN(scheduledAt.getTime()) ? null : scheduledAt.toISOString(),
    started_at: startedAt.toISOString(),
    scheduled_delay_seconds: scheduledDelaySeconds,
  });

  const runStarted = monotonic();
  const runDeadline = runStarted + MAX_RUN_MS;
  const checks = [];
  for (const [index, endpoint] of endpoints.entries()) {
    if (!isInBusinessWindow(now())) {
      checks.push({ ok: false, outcome: "skipped_window", attempts: 0, recovered: false });
      for (const remaining of endpoints.slice(index + 1)) {
        emit({ service: remaining.name, outcome: "skipped_window_remaining" });
        checks.push({ ok: false, outcome: "skipped_window", attempts: 0, recovered: false });
      }
      break;
    }
    const check = await probe(endpoint, {
      fetchImpl,
      now,
      sleep,
      monotonic,
      emit,
      runDeadline,
    });
    checks.push(check);
    if (check.stopReason === "window_closed") {
      for (const remaining of endpoints.slice(index + 1)) {
        emit({ service: remaining.name, outcome: "skipped_window_remaining" });
        checks.push({ ok: false, outcome: "skipped_window", attempts: 0, recovered: false });
      }
      break;
    }
  }

  const needsRecoveryCheck =
    controller.cron !== PREWARM_CRON && checks.some((check) => check.recovered || !check.ok);
  if (needsRecoveryCheck) {
    if (isInBusinessWindow(now())) {
      checks.push(
        await probe(INTEGRATED, { fetchImpl, now, sleep, monotonic, emit, runDeadline }),
      );
    } else {
      emit({ service: INTEGRATED.name, outcome: "skipped_window" });
      checks.push({ ok: false, outcome: "skipped_window", attempts: 0, recovered: false });
    }
  }

  const successes = checks.filter((check) => check.ok).length;
  const skipped = checks.filter((check) => check.outcome === "skipped_window").length;
  const failures = checks.length - successes - skipped;
  const outcome = failures > 0 ? "failed" : skipped > 0 ? "partial" : "ok";
  const result = { outcome, successes, failures, skipped };
  emit({ event: "scheduled_complete", ...result });
  return result;
}

export default {
  async fetch() {
    return new Response("Cron-only worker", { status: 404 });
  },

  async scheduled(controller) {
    const result = await runScheduledCheck(controller);
    if (result.outcome !== "ok") {
      throw new Error(`keep-alive ${result.outcome}: ${result.failures ?? 0} failed endpoint(s)`);
    }
  },
};
