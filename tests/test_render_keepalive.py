from __future__ import annotations

import importlib.util
import sys
import unittest
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

    def test_scheduled_delay_is_measured_against_utc_cron_across_midnight(self):
        self.assertEqual(
            keepalive.scheduled_delay_seconds(
                "55 23 * * *", datetime(2026, 11, 2, 0, 1, tzinfo=timezone.utc)
            ),
            6 * 60,
        )
        self.assertEqual(
            keepalive.scheduled_delay_seconds(
                "5,15,25,35,45,55 0-7 * * *",
                datetime(2026, 11, 2, 0, 8, tzinfo=timezone.utc),
            ),
            3 * 60,
        )

    def test_late_scheduled_event_is_logged_and_skipped_before_network(self):
        events = []
        factory = Mock(side_effect=AssertionError("late schedule must not ping"))
        result = keepalive.run(
            scheduled_cron="55 23 * * *",
            now_fn=lambda: datetime(2026, 11, 2, 0, 1, tzinfo=timezone.utc),
            emit=events.append,
            opener_factory=factory,
        )
        self.assertEqual(result, 0)
        self.assertIn("outcome=schedule_delay delay_seconds=360", events)
        self.assertIn("outcome=skipped_late_schedule delay_seconds=360", events)
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
        self.assertEqual(timeout, 75)
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
        self.assertEqual(sleeps, [1])

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
                Response(status=429, headers={"Retry-After": "120", "Content-Type": "text/plain"}),
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
                Response(status=429, headers={"Retry-After": "5", "Content-Type": "text/plain"}),
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

    def test_malformed_health_payload_is_bounded_and_fails(self):
        opener = SequenceOpener(
            [
                Response(body=b"not-json"),
                Response(body=b"not-json"),
                Response(body=b"not-json"),
            ]
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
            keepalive.API.url: [Response(status=503), Response(status=503), Response(status=503)],
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
        self.assertEqual(visited.count(keepalive.API.url), 3)
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

    def test_run_stops_starting_requests_at_1800_kst_without_failing_the_schedule(self):
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
        self.assertEqual(result, 0)
        self.assertEqual(visited, [keepalive.WEB.url])

    def test_failure_before_window_close_is_reported_if_retry_is_skipped(self):
        times = iter(
            [
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 8, 59, 50, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
            ]
        )
        visited = []

        class FailingOpener:
            def open(self, request, timeout):
                visited.append(request.full_url)
                return Response(status=503)

        result = keepalive.run(
            now_fn=lambda: next(times),
            sleep_fn=lambda _: None,
            emit=lambda _: None,
            opener_factory=FailingOpener,
        )
        self.assertEqual(result, 1)
        self.assertEqual(visited, [keepalive.WEB.url])


if __name__ == "__main__":
    unittest.main()
