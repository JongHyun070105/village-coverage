"""Business-date helpers for the Korea-based planning product."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")


def korea_today() -> date:
    """Return today's calendar date in the service's Korea business timezone."""
    return datetime.now(KOREA_TIME_ZONE).date()
