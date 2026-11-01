"""Bound request-body reads independently of client-supplied length headers."""

from __future__ import annotations

import re

from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect


async def read_bounded_request_body(
    request: Request,
    max_bytes: int,
    *,
    too_large_detail: str,
    invalid_detail: str = "요청 본문 길이가 올바르지 않습니다.",
) -> bytes:
    """Read at most ``max_bytes`` and reject malformed, truncated, or oversized bodies."""
    length_values = [
        value for name, value in request.scope.get("headers", [])
        if name.lower() == b"content-length"
    ]
    if len(length_values) > 1:
        raise HTTPException(status_code=400, detail=invalid_detail)

    declared_length: int | None = None
    if length_values:
        try:
            raw_length = length_values[0].decode("ascii").strip()
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail=invalid_detail) from None
        if not re.fullmatch(r"[0-9]+", raw_length):
            raise HTTPException(status_code=400, detail=invalid_detail)
        declared_length = int(raw_length)
        if declared_length > max_bytes:
            raise HTTPException(status_code=413, detail=too_large_detail)

    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=too_large_detail)
            chunks.append(chunk)
    except ClientDisconnect:
        raise HTTPException(status_code=400, detail=invalid_detail) from None

    if declared_length is not None and total != declared_length:
        raise HTTPException(status_code=400, detail=invalid_detail)
    return b"".join(chunks)
