"""Verified public region catalogue and region-scoped demo views."""

from __future__ import annotations

from typing import Any

DEFAULT_REGION_ID = "pilot:홍성군 장곡면"


def region_id(county: str, town: str) -> str:
    return f"pilot:{county.strip()} {town.strip()}"


def region_catalog(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the source-verified regions, with a legacy single-region fallback."""
    configured = data.get("regions")
    if isinstance(configured, list) and configured:
        return [dict(item) for item in configured if isinstance(item, dict)]

    areas = data.get("areas", [])
    by_region: dict[str, dict[str, Any]] = {}
    for area in areas:
        county = str(area.get("county", "")).strip()
        town = str(area.get("town", "")).strip()
        identifier = str(area.get("region_id") or region_id(county, town))
        by_region.setdefault(
            identifier,
            {
                "region_id": identifier,
                "province": str(area.get("province", "")),
                "county": county,
                "town": town,
                "name": f"{county} {town}".strip(),
                "area_count": 0,
                "full_source_join_rate": None,
                "provenance": area.get("data_provenance", "REAL PUBLIC DATA"),
            },
        )
        by_region[identifier]["area_count"] += 1
    return sorted(
        by_region.values(),
        key=lambda item: (item["province"], item["county"], item["town"]),
    )


def select_region(data: dict[str, Any], selected_id: str | None = None) -> dict[str, Any]:
    """Filter planning input to one verified region without mutating shared fixture data."""
    options = region_catalog(data)
    if not options:
        raise ValueError("unknown or unverified pilot region: no verified region is available")
    identifier = selected_id or str(data.get("default_region_id") or DEFAULT_REGION_ID)
    option = next((item for item in options if item.get("region_id") == identifier), None)
    if option is None:
        raise ValueError("unknown or unverified pilot region")
    areas = []
    for area in data.get("areas", []):
        area_identifier = area.get("region_id") or region_id(
            str(area.get("county", "")), str(area.get("town", ""))
        )
        if str(area_identifier) == identifier:
            areas.append(dict(area))
    if not areas:
        raise ValueError("selected pilot region has no service areas")
    return {
        **data,
        "region": str(option.get("name") or f"{option.get('county', '')} {option.get('town', '')}"),
        "region_id": identifier,
        "selected_region": option,
        "areas": areas,
    }
