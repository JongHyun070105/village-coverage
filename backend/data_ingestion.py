"""Small, pure transformations used at the public-data ingestion boundary."""

from __future__ import annotations

import re
from typing import Any


def legal_code(value: Any) -> str:
    """Canonicalize an observed legal-dong code to its ten-digit key."""
    raw = str(value or "").strip()
    decimal_integer = re.fullmatch(r"(\d+)\.0+", raw)
    digits = decimal_integer.group(1) if decimal_integer else re.sub(r"\D", "", raw)
    return digits.zfill(10) if digits else ""
