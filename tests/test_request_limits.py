from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.pilot_imports import MAX_PILOT_CSV_BYTES
from backend.request_limits import read_bounded_request_body


def _request(events, headers=()) -> Request:
    messages = iter(events)

    async def receive():
        return next(messages, {"type": "http.disconnect"})

    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "root_path": "",
            "headers": list(headers),
            "server": ("test", 80),
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )


def _body_event(body: bytes, *, more_body: bool = False):
    return {"type": "http.request", "body": body, "more_body": more_body}


def test_bounded_body_accepts_small_and_exact_ten_megabytes():
    small = _request([_body_event(b"header\nrow\n")])
    assert (
        asyncio.run(
            read_bounded_request_body(small, MAX_PILOT_CSV_BYTES, too_large_detail="large")
        )
        == b"header\nrow\n"
    )

    exact = b"x" * MAX_PILOT_CSV_BYTES
    exact_request = _request(
        [_body_event(exact)],
        [(b"content-length", str(MAX_PILOT_CSV_BYTES).encode("ascii"))],
    )
    assert (
        asyncio.run(
            read_bounded_request_body(
                exact_request, MAX_PILOT_CSV_BYTES, too_large_detail="large"
            )
        )
        == exact
    )


def test_bounded_body_rejects_actual_chunked_overflow_and_large_declared_length():
    chunked = _request(
        [_body_event(b"x" * MAX_PILOT_CSV_BYTES, more_body=True), _body_event(b"y")]
    )
    with pytest.raises(HTTPException) as overflow:
        asyncio.run(
            read_bounded_request_body(
                chunked, MAX_PILOT_CSV_BYTES, too_large_detail="large"
            )
        )
    assert overflow.value.status_code == 413

    async def no_body_read():
        raise AssertionError("oversized declared body must be rejected before reading")

    declared = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-length", str(MAX_PILOT_CSV_BYTES + 1).encode("ascii"))],
            "server": ("test", 80),
            "client": ("127.0.0.1", 12345),
        },
        no_body_read,
    )
    with pytest.raises(HTTPException) as declared_overflow:
        asyncio.run(
            read_bounded_request_body(
                declared, MAX_PILOT_CSV_BYTES, too_large_detail="large"
            )
        )
    assert declared_overflow.value.status_code == 413


@pytest.mark.parametrize(
    "headers",
    [[(b"content-length", b"5x")], [(b"content-length", b"2"), (b"content-length", b"2")]],
)
def test_bounded_body_rejects_malformed_or_duplicate_lengths(headers):
    request = _request([_body_event(b"abcde")], headers)
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(read_bounded_request_body(request, 10, too_large_detail="large"))
    assert invalid.value.status_code == 400


def test_bounded_body_rejects_truncated_length_and_midstream_disconnect():
    truncated = _request([_body_event(b"ab")], [(b"content-length", b"5")])
    with pytest.raises(HTTPException) as short_body:
        asyncio.run(read_bounded_request_body(truncated, 10, too_large_detail="large"))
    assert short_body.value.status_code == 400

    disconnected = _request(
        [_body_event(b"ab", more_body=True), {"type": "http.disconnect"}],
        [(b"content-length", b"5")],
    )
    with pytest.raises(HTTPException) as disconnect:
        asyncio.run(read_bounded_request_body(disconnected, 10, too_large_detail="large"))
    assert disconnect.value.status_code == 400
