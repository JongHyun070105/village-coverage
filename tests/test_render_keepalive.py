from __future__ import annotations

import importlib.util
import io
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import Mock

SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "render_keepalive.py"
SPEC = importlib.util.spec_from_file_location("render_keepalive", SCRIPT)
assert SPEC and SPEC.loader
keepalive = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = keepalive
SPEC.loader.exec_module(keepalive)


class Response:
    def __init__(self, status=200, body=b'{"status":"ok"}', headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {"Content-Type": "application/json"}
        self.closed = False

    def getcode(self):
        return self.status

    def read(self, limit):
        assert limit == keepalive.MAX_BODY_BYTES
        return self.body[:limit]

    def close(self):
        self.closed = True


class SequenceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class KeepaliveTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 0, 5, tzinfo=timezone.utc)  # 09:05 KST

    def test_utc_cron_instants_convert_to_kst_across_month_boundary(self):
        cases = [
            (datetime(2026, 10, 31, 23, 55, tzinfo=timezone.utc), (11, 1, 8, 55)),
            (datetime(2026, 11, 2, 0, 5, tzinfo=timezone.utc), (11, 2, 9, 5)),
            (datetime(2026, 11, 30, 23, 55, tzinfo=timezone.utc), (12, 1, 8, 55)),
            (datetime(2026, 11, 2, 8, 45, tzinfo=timezone.utc), (11, 2, 17, 45)),
        ]
        for utc, expected in cases:
            with self.subTest(utc=utc):
                local = keepalive.current_kst(utc)
                self.assertEqual((local.month, local.day, local.hour, local.minute), expected)

    def test_window_includes_prewarm_and_stops_at_1800_kst(self):
        self.assertTrue(keepalive.in_window(datetime(2026, 11, 1, 23, 55, tzinfo=timezone.utc)))
        self.assertTrue(keepalive.in_window(datetime(2026, 11, 2, 8, 59, tzinfo=timezone.utc)))
        self.assertFalse(keepalive.in_window(datetime(2026, 11, 1, 23, 54, tzinfo=timezone.utc)))
        self.assertFalse(keepalive.in_window(datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)))

    def test_monthly_runtime_estimate_is_schedule_only(self):
        self.assertEqual(keepalive.estimate_scheduled_instance_hours(30), 272.5)
        self.assertAlmostEqual(keepalive.estimate_scheduled_instance_hours(31), 281.5833333333)
        self.assertAlmostEqual(2 * keepalive.estimate_scheduled_instance_hours(31), 563.1666666667)

    def test_workflow_has_exact_utc_schedule(self):
        workflow = (SCRIPT.parents[1] / "workflows" / "render-free-keepalive.yml").read_text()
        for cron in (
            '"55 23 * * *"',
            '"5,15,25,35,45,55 0-7 * * *"',
            '"5,15,25,35,45 8 * * *"',
        ):
            self.assertIn(cron, workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("--scheduled-cron", workflow)
        self.assertIn("timeout-minutes: 15", workflow)
        self.assertLess(keepalive.MAX_RUN_SECONDS, 15 * 60)

    def test_repeating_schedule_does_not_report_a_slot_as_event_delay(self):
        events = []
        web_opener = SequenceOpener(
            [Response(headers={"Content-Type": "text/html"}, body=b"<html>VillageCoverage</html>")]
        )
        api_opener = SequenceOpener([Response()])
        factory = Mock(side_effect=[web_opener, api_opener])
        result = keepalive.run(
            scheduled_cron="5,15,25,35,45,55 0-7 * * *",
            # A 00:05 event starting at 00:17 is 12 minutes late, but the same
            # cron also has a 00:15 slot. GitHub supplies no occurrence ID/time.
            now_fn=lambda: datetime(2026, 11, 2, 0, 17, tzinfo=timezone.utc),
            emit=events.append,
            opener_factory=factory,
        )
        self.assertEqual(result, 0)
        self.assertIn("outcome=schedule_cron_validated", events)
        self.assertFalse(any("delay_seconds=" in event for event in events))

    def test_scheduled_run_after_kst_window_is_blocked_by_window_gate(self):
        events = []
        factory = Mock(side_effect=AssertionError("out-of-window schedule must not ping"))
        result = keepalive.run(
            scheduled_cron="5,15,25,35,45,55 0-7 * * *",
            now_fn=lambda: datetime(2026, 11, 2, 9, 1, tzinfo=timezone.utc),  # 18:01 KST
            emit=events.append,
            opener_factory=factory,
        )
        self.assertEqual(result, 0)
        self.assertIn("outcome=schedule_cron_validated", events)
        self.assertTrue(any("outcome=skipped_window" in event for event in events))
        factory.assert_not_called()

    def test_unknown_schedule_fails_closed(self):
        events = []
        factory = Mock(side_effect=AssertionError("unknown schedule must not ping"))
        result = keepalive.run(
            scheduled_cron="* * * * *",
            now_fn=lambda: self.now,
            emit=events.append,
            opener_factory=factory,
        )
        self.assertEqual(result, 2)
        self.assertEqual(events, ["outcome=invalid_schedule"])
        factory.assert_not_called()

    def test_retry_after_parses_seconds_without_silently_truncating(self):
        self.assertEqual(keepalive.retry_after_seconds("120", self.now), 120)
        self.assertEqual(keepalive.retry_after_seconds("30", self.now), 30)
        self.assertEqual(keepalive.retry_after_seconds("-5", self.now), 0)
        self.assertIsNone(keepalive.retry_after_seconds("not-a-date", self.now))
        retry_at = self.now + timedelta(seconds=10)
        self.assertEqual(keepalive.retry_after_seconds(format_datetime(retry_at), self.now), 10)

    def test_only_allowlisted_https_get_requests_are_sent(self):
        opener = SequenceOpener(
            [Response(headers={"Content-Type": "text/html"}, body=b"<html>VillageCoverage</html>")]
        )
        ok, _, _ = keepalive.probe(
            keepalive.WEB,
            now_fn=lambda: self.now,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertTrue(ok)
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, keepalive.WEB.url)
        self.assertEqual(timeout, 10)
        self.assertNotIn("Cookie", request.headers)
        self.assertNotIn("Authorization", request.headers)

        external = keepalive.Endpoint("external", "https://example.com/", "health")
        blocked, _, _ = keepalive.probe(
            external,
            now_fn=lambda: self.now,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertFalse(blocked)
        self.assertEqual(len(opener.requests), 1)

    def test_render_html_wake_response_retries_health_until_json_is_ready(self):
        opener = SequenceOpener(
            [
                Response(headers={"Content-Type": "text/html"}, body=b"<html>booting</html>"),
                Response(),
            ]
        )
        sleeps = []
        ok, recovered, skipped = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=sleeps.append,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertTrue(ok)
        self.assertTrue(recovered)
        self.assertFalse(skipped)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [5])

    def test_render_html_wake_page_does_not_pass_as_healthy_web(self):
        opener = SequenceOpener(
            [
                Response(
                    headers={"Content-Type": "text/html"},
                    body=b"<html><title>Service is starting</title></html>",
                ),
                Response(
                    headers={"Content-Type": "text/html"},
                    body=b"<html><title>VillageCoverage</title></html>",
                ),
            ]
        )
        ok, recovered, skipped = keepalive.probe(
            keepalive.WEB,
            now_fn=lambda: self.now,
            sleep_fn=lambda _: None,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertTrue(ok)
        self.assertTrue(recovered)
        self.assertFalse(skipped)
        self.assertEqual(len(opener.requests), 2)

    def test_429_beyond_retry_limit_fails_without_retrying_too_early(self):
        opener = SequenceOpener(
            [
                Response(status=429, headers={"Retry-After": "301", "Content-Type": "text/plain"}),
                Response(),
            ]
        )
        sleeps = []
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=sleeps.append,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertFalse(ok)
        self.assertEqual(sleeps, [])
        self.assertEqual(len(opener.requests), 1)

    def test_429_retries_after_short_retry_after(self):
        opener = SequenceOpener(
            [
                Response(status=429, headers={"Retry-After": "0", "Content-Type": "text/plain"}),
                Response(),
            ]
        )
        sleeps = []
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=sleeps.append,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertTrue(ok)
        self.assertEqual(sleeps, [5])

    def test_urllib_http_error_503_honors_retry_after_and_recovers(self):
        error = urllib.error.HTTPError(
            keepalive.API.url,
            503,
            "Service Unavailable",
            {"Retry-After": "3"},
            io.BytesIO(b"busy"),
        )
        opener = SequenceOpener([error, Response()])
        sleeps = []
        events = []
        ok, recovered, skipped = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=sleeps.append,
            opener=opener,
            emit=events.append,
        )
        self.assertTrue(ok)
        self.assertTrue(recovered)
        self.assertFalse(skipped)
        self.assertEqual(sleeps, [5])
        self.assertTrue(any("attempt=1 status=503" in event for event in events))
        self.assertTrue(any("outcome=recovered" in event for event in events))

    def test_urllib_http_error_redirect_is_not_retried_or_followed(self):
        redirect = urllib.error.HTTPError(
            keepalive.API.url,
            302,
            "Found",
            {"Location": "https://example.com/"},
            io.BytesIO(b"redirect"),
        )
        opener = SequenceOpener([redirect])
        events = []
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            opener=opener,
            emit=events.append,
        )
        self.assertFalse(ok)
        self.assertEqual(len(opener.requests), 1)
        self.assertTrue(
            any("attempt=1 status=302" in event and "outcome=failed" in event for event in events)
        )

    def test_retry_after_longer_than_remaining_run_budget_is_not_shortened(self):
        opener = SequenceOpener(
            [Response(status=429, headers={"Retry-After": "120", "Content-Type": "text/plain"})]
        )
        sleeps = []
        events = []
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=sleeps.append,
            monotonic_fn=lambda: 0.0,
            run_deadline=60.0,
            opener=opener,
            emit=events.append,
        )
        self.assertFalse(ok)
        self.assertEqual(sleeps, [])
        self.assertEqual(len(opener.requests), 1)
        self.assertTrue(any("retry_delay_s=120 remaining_budget_s=60" in event for event in events))

    def test_failure_logs_include_status_cause_and_elapsed_time(self):
        opener = SequenceOpener([Response(status=418)])
        events = []
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            monotonic_fn=lambda: 1.0,
            opener=opener,
            emit=events.append,
        )
        self.assertFalse(ok)
        self.assertTrue(
            any(
                "attempt=1 status=418" in event and "failure=http_status" in event
                for event in events
            )
        )
        self.assertTrue(
            any(
                "outcome=failed attempts=1 status=418 failure=http_status elapsed_ms=0" in event
                for event in events
            )
        )

    def test_malformed_health_payload_is_bounded_and_fails(self):
        opener = SequenceOpener(
            [Response(body=b"not-json") for _ in range(keepalive.MAX_ATTEMPTS)]
        )
        ok, _, _ = keepalive.probe(
            keepalive.API,
            now_fn=lambda: self.now,
            sleep_fn=lambda _: None,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertFalse(ok)
        self.assertEqual(len(opener.requests), keepalive.MAX_ATTEMPTS)

    def test_redirect_is_not_followed(self):
        opener = SequenceOpener(
            [Response(status=302, headers={"Location": "https://example.com/"})]
        )
        ok, _, _ = keepalive.probe(
            keepalive.WEB,
            now_fn=lambda: self.now,
            opener=opener,
            emit=lambda _: None,
        )
        self.assertFalse(ok)
        self.assertEqual(len(opener.requests), 1)

        handler = keepalive.NoRedirectHandler()
        self.assertIsNone(
            handler.redirect_request(Mock(), None, 302, "Found", {}, "https://example.com/")
        )

    def test_one_failed_endpoint_does_not_skip_the_other_or_recovery_check(self):
        responses = {
            keepalive.WEB.url: [
                Response(
                    headers={"Content-Type": "text/html"}, body=b"<html>VillageCoverage</html>"
                )
            ],
            keepalive.API.url: [
                Response(status=503) for _ in range(keepalive.MAX_ATTEMPTS)
            ],
            keepalive.INTEGRATED.url: [Response()],
        }
        visited = []

        class RoutingOpener:
            def open(self, request, timeout):
                visited.append(request.full_url)
                return responses[request.full_url].pop(0)

        result = keepalive.run(
            now_fn=lambda: self.now,
            sleep_fn=lambda _: None,
            emit=lambda _: None,
            opener_factory=RoutingOpener,
        )
        self.assertEqual(result, 1)
        self.assertEqual(visited.count(keepalive.WEB.url), 1)
        self.assertEqual(visited.count(keepalive.API.url), keepalive.MAX_ATTEMPTS)
        self.assertEqual(visited.count(keepalive.INTEGRATED.url), 1)

    def test_out_of_window_dispatch_skips_without_network(self):
        factory = Mock(side_effect=AssertionError("must not open outside window"))
        late = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)  # 18:00 KST
        result = keepalive.run(
            now_fn=lambda: late,
            emit=lambda _: None,
            opener_factory=factory,
        )
        self.assertEqual(result, 0)
        factory.assert_not_called()

    def test_run_stops_starting_requests_at_1800_kst_and_reports_incomplete_health(self):
        times = iter(
            [
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
            ]
        )
        visited = []

        class OneShotOpener:
            def open(self, request, timeout):
                visited.append(request.full_url)
                return Response(
                    headers={"Content-Type": "text/html"},
                    body=b"<html>VillageCoverage</html>",
                )

        result = keepalive.run(
            now_fn=lambda: next(times),
            emit=lambda _: None,
            opener_factory=OneShotOpener,
        )
        self.assertEqual(result, 1)
        self.assertEqual(visited, [keepalive.WEB.url])

    def test_failure_before_window_close_is_reported_if_retry_is_skipped(self):
        clock = {"now": datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc)}
        visited = []

        class FailingOpener:
            def open(self, request, timeout):
                visited.append(request.full_url)
                return Response(status=503)

        result = keepalive.run(
            now_fn=lambda: clock["now"],
            sleep_fn=lambda delay: clock.__setitem__(
                "now", clock["now"] + timedelta(seconds=delay)
            ),
            emit=lambda _: None,
            opener_factory=FailingOpener,
        )
        self.assertEqual(result, 1)
        self.assertEqual(
            visited,
            [keepalive.WEB.url, keepalive.WEB.url, keepalive.INTEGRATED.url],
        )

    def test_cold_start_retries_recover_web_after_40s_and_api_after_90s(self):
        class Clock:
            elapsed = 0.0

            def sleep(self, delay):
                self.elapsed += delay

        clock = Clock()
        ready_after = {
            keepalive.WEB.url: 40,
            keepalive.API.url: 90,
            keepalive.INTEGRATED.url: 0,
        }
        first_request = {}
        requests = {url: 0 for url in ready_after}
        events = []

        class ColdStartOpener:
            def open(self, request, timeout):
                url = request.full_url
                requests[url] += 1
                first_request.setdefault(url, clock.elapsed)
                if clock.elapsed - first_request[url] < ready_after[url]:
                    return Response(status=503)
                if url == keepalive.WEB.url:
                    return Response(
                        headers={"Content-Type": "text/html"},
                        body=b"<html>VillageCoverage</html>",
                    )
                return Response()

        base_now = self.now
        result = keepalive.run(
            now_fn=lambda: base_now + timedelta(seconds=clock.elapsed),
            sleep_fn=clock.sleep,
            monotonic_fn=lambda: clock.elapsed,
            emit=events.append,
            opener_factory=ColdStartOpener,
        )
        self.assertEqual(result, 0)
        self.assertGreaterEqual(requests[keepalive.WEB.url], 5)
        self.assertGreaterEqual(requests[keepalive.API.url], 7)
        self.assertEqual(requests[keepalive.INTEGRATED.url], 1)
        self.assertLessEqual(clock.elapsed, keepalive.MAX_RUN_SECONDS)
        self.assertTrue(any("service=web outcome=recovered" in e for e in events))
        self.assertTrue(any("service=api outcome=recovered" in e for e in events))
        self.assertTrue(any("service=integrated-health outcome=healthy" in e for e in events))

    def test_repeated_failures_stop_within_the_eight_minute_run_budget(self):
        class Clock:
            elapsed = 0.0

            def sleep(self, delay):
                self.elapsed += delay

        clock = Clock()
        requests = {endpoint.url: 0 for endpoint in keepalive.ENDPOINTS}
        events = []

        class FailingOpener:
            def open(self, request, timeout):
                requests[request.full_url] += 1
                return Response(status=503)

        result = keepalive.run(
            now_fn=lambda: self.now + timedelta(seconds=clock.elapsed),
            sleep_fn=clock.sleep,
            monotonic_fn=lambda: clock.elapsed,
            emit=events.append,
            opener_factory=FailingOpener,
        )
        self.assertEqual(result, 1)
        self.assertLessEqual(clock.elapsed, keepalive.MAX_RUN_SECONDS)
        self.assertLessEqual(sum(requests.values()), 3 * keepalive.MAX_ATTEMPTS)
        self.assertTrue(any("outcome=retry_budget_exhausted" in e for e in events))


if __name__ == "__main__":
    unittest.main()
