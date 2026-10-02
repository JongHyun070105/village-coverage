"""Deterministic duplicate and conflict detection for reviewed demand evidence.

This module only proposes review work. It never merges, deletes, or resolves
evidence, and it does not use an LLM to make identity or conflict decisions.
"""

from __future__ import annotations

import hashlib
import itertools
import unicodedata
from datetime import date
from typing import Any

DUPLICATE_DATE_PROXIMITY_DAYS = 14
CONFLICT_DATE_PROXIMITY_DAYS = 30
FREQUENCY_RANGE_PLANNING_POLICY = "CONSERVATIVE_LOW"

DUPLICATE_STATES = (
    "UNREVIEWED",
    "POSSIBLE_DUPLICATE",
    "LINKED_DUPLICATE",
    "CONFIRMED_DISTINCT",
)
CONFLICT_TYPES = (
    "FREQUENCY_CONFLICT",
    "DATE_CONFLICT",
    "TIME_CONFLICT",
    "PREFERRED_DAY_CONFLICT",
    "EXCLUDED_DAY_CONFLICT",
    "SERVICE_TYPE_CONFLICT",
    "CONSTRAINT_CONFLICT",
)
CONFLICT_STATES = ("NO_CONFLICT", "REVIEW_REQUIRED", "RESOLVED", "ACCEPTED_AS_RANGE")
CONFLICT_RESOLUTION_METHODS = (
    "SELECT_EVIDENCE",
    "ACCEPTED_AS_RANGE",
    "LATEST_EVIDENCE",
    "FURTHER_SURVEY",
)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in text if character.isalnum())


def _normal_set(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    normalized = tuple(sorted({item for item in (_normalize_text(v) for v in values) if item}))
    return normalized or None


def evidence_fields(record: dict[str, Any]) -> dict[str, Any]:
    evidence_payload = record.get("evidence_payload") or {}
    structured = record.get("structured_data") or evidence_payload.get("structured_data") or {}
    frequency = record.get("frequency_per_month")
    if frequency is None:
        frequency = structured.get(
            "frequency_per_month", evidence_payload.get("frequency_per_month")
        )
    return {
        "frequency_per_month": int(frequency) if frequency is not None else None,
        "requested_period": _normalize_text(
            record.get("preferred_period")
            or structured.get("requested_period")
            or evidence_payload.get("preferred_period")
        )
        or None,
        "desired_date": _normalize_text(structured.get("desired_date")) or None,
        "desired_time": _normalize_text(structured.get("desired_time")) or None,
        "recurring_pattern": _normalize_text(structured.get("recurring_pattern")) or None,
        "preferred_days": _normal_set(
            record.get("preferred_days")
            or structured.get("preferred_days")
            or evidence_payload.get("preferred_days")
        ),
        "excluded_days": _normal_set(
            structured.get("excluded_days") or evidence_payload.get("excluded_days")
        ),
        "constraints": _normal_set(
            record.get("constraints")
            or structured.get("constraints")
            or evidence_payload.get("constraints")
        ),
    }


def note_fingerprint(record: dict[str, Any]) -> str | None:
    note = _normalize_text(record.get("free_text_note") or record.get("source_text_redacted"))
    if not note:
        return None
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def _date_gap(left: dict[str, Any], right: dict[str, Any]) -> int | None:
    try:
        return abs(
            (
                date.fromisoformat(str(left["survey_date"]))
                - date.fromisoformat(str(right["survey_date"]))
            ).days
        )
    except (KeyError, ValueError):
        return None


def _same_legal_area(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_code = str(left.get("legal_code") or left.get("area_id") or "")
    right_code = str(right.get("legal_code") or right.get("area_id") or "")
    return bool(left_code) and left_code == right_code


def _matching_fields(left: dict[str, Any], right: dict[str, Any]) -> tuple[int, list[str]]:
    left_fields = evidence_fields(left)
    right_fields = evidence_fields(right)
    matched: list[str] = []
    for key, left_value in left_fields.items():
        right_value = right_fields[key]
        if left_value is not None and right_value is not None and left_value == right_value:
            matched.append(key)
    return len(matched), matched


def _frequency_similar(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_frequency = evidence_fields(left)["frequency_per_month"]
    right_frequency = evidence_fields(right)["frequency_per_month"]
    return (
        left_frequency is not None
        and right_frequency is not None
        and abs(left_frequency - right_frequency) <= 1
    )


def detect_duplicate_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return cautious, deterministic candidates; no candidate is auto-linked."""
    candidates: list[dict[str, Any]] = []
    for left, right in itertools.combinations(records, 2):
        if not _same_legal_area(left, right):
            continue
        if left.get("service_type") != right.get("service_type"):
            continue
        if (left.get("survey_type") or left.get("source_type")) != (
            right.get("survey_type") or right.get("source_type")
        ):
            continue
        date_gap = _date_gap(left, right)
        if date_gap is None or date_gap > DUPLICATE_DATE_PROXIMITY_DAYS:
            continue

        match_count, matched_fields = _matching_fields(left, right)
        exact_note_match = note_fingerprint(left) is not None and note_fingerprint(
            left
        ) == note_fingerprint(right)
        frequency_similar = _frequency_similar(left, right)
        if not (exact_note_match or (frequency_similar and match_count >= 2) or match_count >= 3):
            continue

        first_id, second_id = sorted((str(left["survey_id"]), str(right["survey_id"])))
        reasons = [
            "SAME_LEGAL_AREA",
            "SAME_SERVICE_TYPE",
            "SAME_SOURCE_TYPE",
            f"SURVEY_DATES_WITHIN_{DUPLICATE_DATE_PROXIMITY_DAYS}_DAYS",
        ]
        if exact_note_match:
            reasons.append("NORMALIZED_NOTE_FINGERPRINT_MATCH")
        if matched_fields:
            reasons.append("NORMALIZED_FIELDS_MATCH:" + ",".join(sorted(matched_fields)))
        if frequency_similar:
            reasons.append("FREQUENCY_WITHIN_ONE_PER_MONTH")
        candidates.append(
            {
                "survey_id_a": first_id,
                "survey_id_b": second_id,
                "date_gap_days": date_gap,
                "match_reasons": reasons,
            }
        )
    return candidates


def _conflict_values(records: list[dict[str, Any]], conflict_type: str) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    for record in records:
        fields = evidence_fields(record)
        if conflict_type == "FREQUENCY_CONFLICT":
            value = fields["frequency_per_month"]
        elif conflict_type == "DATE_CONFLICT":
            value = fields["desired_date"]
        elif conflict_type == "TIME_CONFLICT":
            value = fields["desired_time"]
        elif conflict_type == "PREFERRED_DAY_CONFLICT":
            value = fields["preferred_days"]
        elif conflict_type == "EXCLUDED_DAY_CONFLICT":
            value = fields["excluded_days"]
        elif conflict_type == "CONSTRAINT_CONFLICT":
            value = fields["constraints"]
        else:
            value = None
        if value is not None:
            values.append((str(record["survey_id"]), value))
    return values


def detect_conflicts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group nearby contradictory facts without averaging or selecting a winner."""
    by_service: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            str(record.get("legal_code") or record.get("area_id") or ""),
            str(record["service_type"]),
        )
        by_service.setdefault(key, []).append(record)

    conflicts: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for service_records in by_service.values():
        ordered = sorted(
            service_records, key=lambda item: (str(item["survey_date"]), str(item["survey_id"]))
        )
        for start_index, start in enumerate(ordered):
            window = [
                item
                for item in ordered[start_index:]
                if (_date_gap(start, item) or 0) <= CONFLICT_DATE_PROXIMITY_DAYS
            ]
            if len(window) < 2:
                continue
            for conflict_type in CONFLICT_TYPES:
                if conflict_type == "SERVICE_TYPE_CONFLICT":
                    continue
                field_values = _conflict_values(window, conflict_type)
                if len({repr(value) for _, value in field_values}) < 2:
                    continue
                evidence_ids = tuple(sorted(survey_id for survey_id, _ in field_values))
                conflicts[(conflict_type, evidence_ids)] = {
                    "conflict_type": conflict_type,
                    "service_type": str(start["service_type"]),
                    "survey_ids": list(evidence_ids),
                    "values": {survey_id: value for survey_id, value in field_values},
                }

    for left, right in itertools.combinations(records, 2):
        if not _same_legal_area(left, right) or left.get("service_type") == right.get(
            "service_type"
        ):
            continue
        date_gap = _date_gap(left, right)
        left_fingerprint = note_fingerprint(left)
        if (
            date_gap is None
            or date_gap > CONFLICT_DATE_PROXIMITY_DAYS
            or not left_fingerprint
            or left_fingerprint != note_fingerprint(right)
        ):
            continue
        evidence_ids = tuple(sorted((str(left["survey_id"]), str(right["survey_id"]))))
        conflicts[("SERVICE_TYPE_CONFLICT", evidence_ids)] = {
            "conflict_type": "SERVICE_TYPE_CONFLICT",
            "service_type": None,
            "survey_ids": list(evidence_ids),
            "values": {
                str(left["survey_id"]): str(left["service_type"]),
                str(right["survey_id"]): str(right["service_type"]),
            },
        }
    return [conflicts[key] for key in sorted(conflicts)]


def planning_frequency_selection(
    records: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    *,
    canonical_survey_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Apply only explicit conflict decisions; unresolved values never enter a precise floor."""
    frequency_conflicts = [
        conflict for conflict in conflicts if conflict["conflict_type"] == "FREQUENCY_CONFLICT"
    ]
    conflicted_ids: set[str] = set()
    blocked_ids: set[str] = set()
    selected_values: dict[str, int] = {}
    range_values: list[tuple[set[str], int, int]] = []
    unresolved = False
    further_survey = False
    for conflict in frequency_conflicts:
        ids = {
            str(item)
            for item in conflict.get("survey_ids", conflict.get("evidence_survey_ids", []))
        }
        conflicted_ids.update(ids)
        state = conflict.get("status", "REVIEW_REQUIRED")
        method = conflict.get("resolution_method")
        selected_id = conflict.get("selected_survey_id")
        if state == "REVIEW_REQUIRED":
            unresolved = True
            blocked_ids.update(ids)
        elif state == "ACCEPTED_AS_RANGE":
            low = conflict.get("frequency_min")
            high = conflict.get("frequency_max")
            if low is not None and high is not None:
                range_values.append((ids, int(low), int(high)))
        elif method in {"SELECT_EVIDENCE", "LATEST_EVIDENCE"} and selected_id in ids:
            selected_values[str(selected_id)] = next(
                int(evidence_fields(item)["frequency_per_month"])
                for item in records
                if str(item["survey_id"]) == str(selected_id)
                and evidence_fields(item)["frequency_per_month"] is not None
            )
        elif method == "FURTHER_SURVEY":
            further_survey = True
            blocked_ids.update(ids)

    selected_values = {
        survey_id: frequency
        for survey_id, frequency in selected_values.items()
        if survey_id not in blocked_ids
    }
    range_values = [
        (ids, low, high) for ids, low, high in range_values if not ids.intersection(blocked_ids)
    ]

    values = [
        int(record["frequency_per_month"])
        for record in records
        if record.get("frequency_per_month") is not None
        and str(record["survey_id"]) not in conflicted_ids
        and (canonical_survey_ids is None or str(record["survey_id"]) in canonical_survey_ids)
    ]
    values.extend(selected_values.values())
    values.extend(low for _ids, low, _high in range_values)
    range_summary = None
    if range_values:
        range_summary = {
            "frequency_min": min(low for _ids, low, _high in range_values),
            "frequency_max": max(high for _ids, _low, high in range_values),
            "policy": FREQUENCY_RANGE_PLANNING_POLICY,
            "planning_frequency_per_month": min(low for _ids, low, _high in range_values),
        }
    conflict_state = (
        "REVIEW_REQUIRED"
        if unresolved or further_survey
        else "RESOLVED"
        if frequency_conflicts
        else "NO_CONFLICT"
    )
    return {
        "frequencies": values,
        "precision_blocked": unresolved or further_survey,
        "needs_further_survey": further_survey,
        "frequency_range": range_summary,
        "frequency_policy": FREQUENCY_RANGE_PLANNING_POLICY,
        "evidence_count": len(values),
        "conflict_state": conflict_state,
    }
