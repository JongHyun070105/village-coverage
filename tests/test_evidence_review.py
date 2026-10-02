from __future__ import annotations

import json
from pathlib import Path

from backend import database
from backend.evidence_review import (
    detect_conflicts,
    detect_duplicate_candidates,
    planning_frequency_selection,
)
from backend.main import _apply_existing_service_history

ROOT = Path(__file__).resolve().parents[1]


def _demo_data() -> dict:
    return json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8"))


def _connect(path: Path):
    connection = database.connect(path)
    data = _demo_data()
    database.seed_reference_data(connection, data)
    return connection, str(data["areas"][0]["id"])


def _insert_survey(
    connection,
    area_id: str,
    *,
    survey_type: str = "phone",
    survey_date: str = "2026-09-01",
    service_type: str = "laundry",
    frequency: int | None = 2,
    note: str = "세탁 서비스를 월 2회 요청함",
    structured: dict | None = None,
) -> str:
    return database.insert_survey(
        connection,
        area_id=area_id,
        survey_type=survey_type,
        survey_date=survey_date,
        service_type=service_type,
        frequency_per_month=frequency,
        preferred_period=None,
        preferred_days=[],
        constraints=[],
        free_text_note=note,
        source_text_was_redacted=False,
        structured_data=structured or {},
        provenance="TEST_EVIDENCE",
    )


def test_identical_semantic_evidence_is_a_deterministic_duplicate_candidate(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "duplicate-candidate.sqlite")
    try:
        first = _insert_survey(connection, area_id)
        second = _insert_survey(connection, area_id)
        records = database._review_records(connection, area_id)

        candidates = detect_duplicate_candidates(records)
        assert [(item["survey_id_a"], item["survey_id_b"]) for item in candidates] == [
            tuple(sorted((first, second)))
        ]
        assert "NORMALIZED_NOTE_FINGERPRINT_MATCH" in candidates[0]["match_reasons"]
    finally:
        connection.close()


def test_unrelated_evidence_is_not_marked_as_a_duplicate(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "unrelated-evidence.sqlite")
    try:
        _insert_survey(connection, area_id)
        _insert_survey(
            connection,
            area_id,
            frequency=12,
            note="집수리 서비스 일회 요청, 현관 손잡이가 고장남",
        )

        assert detect_duplicate_candidates(database._review_records(connection, area_id)) == []
    finally:
        connection.close()


def test_linked_duplicate_retains_raw_records_and_is_idempotent(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "linked-duplicates.sqlite")
    try:
        first = _insert_survey(connection, area_id, frequency=4)
        second = _insert_survey(connection, area_id, frequency=4)
        database.evidence_review(connection, area_id)

        first_resolution = database.resolve_duplicate_pair(
            connection,
            area_id=area_id,
            first_survey_id=first,
            second_survey_id=second,
            decision="LINKED_DUPLICATE",
            reason="같은 조사 기록의 재전송 확인",
        )
        replay = database.resolve_duplicate_pair(
            connection,
            area_id=area_id,
            first_survey_id=second,
            second_survey_id=first,
            decision="LINKED_DUPLICATE",
            reason="같은 조사 기록의 재전송 확인",
        )
        records = database.list_surveys(connection, area_id, "laundry")
        canonical = next(
            item for item in records if item["canonical_survey_id"] == item["survey_id"]
        )

        assert first_resolution["state"] == "LINKED_DUPLICATE"
        assert replay["idempotent"] is True
        assert len(records) == 2
        assert sum(item["duplicate_status"] == "LINKED_DUPLICATE" for item in records) == 2
        assert all(item["evidence_id"] and item["observation_id"] for item in records)
        assert canonical["survey_id"] in {first, second}
        audit = dict(
            connection.execute(
                "SELECT * FROM demand_evidence_review_audit WHERE action='LINK_DUPLICATE'"
            ).fetchone()
        )
        assert audit["actor_type"] == "DEMO_PLANNER"
        assert audit["previous_state"] == "POSSIBLE_DUPLICATE"
        assert audit["new_state"] == "LINKED_DUPLICATE"
        assert audit["selected_survey_id"] == canonical["survey_id"]
        assert audit["reason"] == "같은 조사 기록의 재전송 확인"
        assert audit["provenance"] == "DEMO_PLANNER_DECISION"

        area = next(item for item in _demo_data()["areas"] if str(item["id"]) == area_id)
        area["simulated_monthly_demand"] = 0
        area["population_adjusted_baseline_units"] = 0
        _apply_existing_service_history(
            area,
            connection,
            surveys=database.list_surveys(connection, area_id, "laundry"),
        )
        assert area["survey_frequency_observation_count"] == 1
        assert area["survey_frequency_floor_monthly"] == 4
    finally:
        connection.close()


def test_frequency_conflicts_are_reported_without_averaging(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "frequency-conflicts.sqlite")
    try:
        _insert_survey(connection, area_id, survey_type="phone", frequency=2)
        _insert_survey(connection, area_id, survey_type="village_meeting", frequency=1)
        _insert_survey(connection, area_id, survey_type="field", frequency=4)

        conflicts = detect_conflicts(database._review_records(connection, area_id))
        frequency = next(
            item for item in conflicts if item["conflict_type"] == "FREQUENCY_CONFLICT"
        )

        assert set(frequency["values"].values()) == {1, 2, 4}
    finally:
        connection.close()


def test_desired_date_and_time_conflicts_are_detected(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "date-time-conflicts.sqlite")
    try:
        _insert_survey(
            connection,
            area_id,
            survey_type="phone",
            structured={"desired_date": "2026-10-08", "desired_time": "14:00"},
        )
        _insert_survey(
            connection,
            area_id,
            survey_type="village_meeting",
            structured={"desired_date": "2026-10-09", "desired_time": "15:00"},
        )

        types = {
            item["conflict_type"]
            for item in detect_conflicts(database._review_records(connection, area_id))
        }
        assert {"DATE_CONFLICT", "TIME_CONFLICT"} <= types
    finally:
        connection.close()


def test_preferred_excluded_constraint_and_service_conflicts_are_detected(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "structured-conflicts.sqlite")
    try:
        _insert_survey(
            connection,
            area_id,
            survey_type="phone",
            structured={
                "preferred_days": ["monday"],
                "excluded_days": ["sunday"],
                "constraints": ["계단 이동 어려움"],
            },
        )
        _insert_survey(
            connection,
            area_id,
            survey_type="village_meeting",
            structured={
                "preferred_days": ["tuesday"],
                "excluded_days": ["saturday"],
                "constraints": ["휠체어 접근 필요"],
            },
        )
        _insert_survey(
            connection,
            area_id,
            service_type="home_repair",
            survey_type="field",
            note="세탁 서비스를 월 2회 요청함",
        )

        types = {
            item["conflict_type"]
            for item in detect_conflicts(database._review_records(connection, area_id))
        }
        assert {
            "PREFERRED_DAY_CONFLICT",
            "EXCLUDED_DAY_CONFLICT",
            "CONSTRAINT_CONFLICT",
            "SERVICE_TYPE_CONFLICT",
        } <= types
    finally:
        connection.close()


def test_unresolved_frequency_conflict_blocks_precise_planning_input(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "unresolved-conflict.sqlite")
    try:
        _insert_survey(connection, area_id, survey_type="phone", frequency=2)
        _insert_survey(connection, area_id, survey_type="field", frequency=4)
        review = database.evidence_review(connection, area_id)
        records = review["evidence"]

        selection = planning_frequency_selection(records, review["conflicts"])
        assert review["conflict_state"] == "REVIEW_REQUIRED"
        assert selection["precision_blocked"] is True
        assert selection["frequencies"] == []
        area = next(item for item in _demo_data()["areas"] if str(item["id"]) == area_id)
        area["simulated_monthly_demand"] = 0
        area["population_adjusted_baseline_units"] = 0
        _apply_existing_service_history(area, connection, surveys=records)
        assert area["survey_frequency_floor_monthly"] is None
        assert area["planning_demand_precision_blocked"] is True
    finally:
        connection.close()


def test_new_unresolved_conflict_blocks_an_older_accepted_range() -> None:
    records = [
        {"survey_id": "survey-2", "frequency_per_month": 2},
        {"survey_id": "survey-4", "frequency_per_month": 4},
        {"survey_id": "survey-5", "frequency_per_month": 5},
    ]
    conflicts = [
        {
            "conflict_type": "FREQUENCY_CONFLICT",
            "survey_ids": ["survey-2", "survey-4"],
            "status": "ACCEPTED_AS_RANGE",
            "resolution_method": "ACCEPTED_AS_RANGE",
            "frequency_min": 2,
            "frequency_max": 4,
        },
        {
            "conflict_type": "FREQUENCY_CONFLICT",
            "survey_ids": ["survey-2", "survey-5"],
            "status": "REVIEW_REQUIRED",
            "resolution_method": None,
        },
    ]

    selection = planning_frequency_selection(records, conflicts)

    assert selection["precision_blocked"] is True
    assert selection["frequency_range"] is None
    assert selection["frequencies"] == []


def test_selecting_evidence_changes_planning_frequency_deterministically_and_audits(
    tmp_path,
) -> None:
    connection, area_id = _connect(tmp_path / "resolved-conflict.sqlite")
    try:
        first = _insert_survey(connection, area_id, survey_type="phone", frequency=2)
        second = _insert_survey(connection, area_id, survey_type="field", frequency=4)
        review = database.evidence_review(connection, area_id)
        conflict = next(
            item for item in review["conflicts"] if item["conflict_type"] == "FREQUENCY_CONFLICT"
        )

        resolution = database.resolve_evidence_conflict(
            connection,
            conflict_id=conflict["conflict_id"],
            method="SELECT_EVIDENCE",
            selected_survey_id=second,
            reason="현장 조사 기록을 채택",
        )
        updated = database.evidence_review(connection, area_id)
        saved = next(
            item for item in updated["conflicts"] if item["conflict_id"] == conflict["conflict_id"]
        )
        selection = planning_frequency_selection(updated["evidence"], updated["conflicts"])
        audit = next(
            item for item in updated["audit"] if item["subject_id"] == conflict["conflict_id"]
        )

        assert resolution["status"] == "RESOLVED"
        assert saved["selected_survey_id"] == second
        assert selection["frequencies"] == [4]
        assert selection["precision_blocked"] is False
        assert audit["actor_type"] == "DEMO_PLANNER"
        assert audit["previous_state"] == "REVIEW_REQUIRED"
        assert audit["new_state"] == "RESOLVED"
        assert audit["selected_survey_id"] == second
        assert audit["reason"] == "현장 조사 기록을 채택"
        assert audit["provenance"] == "HUMAN_REVIEW:SELECT_EVIDENCE"
        assert first in saved["evidence_survey_ids"]
    finally:
        connection.close()


def test_accepted_frequency_range_persists_and_uses_conservative_low(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "accepted-range.sqlite")
    try:
        _insert_survey(connection, area_id, survey_type="phone", frequency=1)
        _insert_survey(connection, area_id, survey_type="field", frequency=4)
        review = database.evidence_review(connection, area_id)
        conflict = next(
            item for item in review["conflicts"] if item["conflict_type"] == "FREQUENCY_CONFLICT"
        )

        resolved = database.resolve_evidence_conflict(
            connection,
            conflict_id=conflict["conflict_id"],
            method="ACCEPTED_AS_RANGE",
            reason="조사 간 차이를 범위로 유지",
        )
        updated = database.evidence_review(connection, area_id)
        selection = planning_frequency_selection(updated["evidence"], updated["conflicts"])

        assert resolved["status"] == "ACCEPTED_AS_RANGE"
        assert resolved["frequency_min"] == 1
        assert resolved["frequency_max"] == 4
        assert selection["frequency_range"] == {
            "frequency_min": 1,
            "frequency_max": 4,
            "policy": "CONSERVATIVE_LOW",
            "planning_frequency_per_month": 1,
        }
        assert selection["frequencies"] == [1]
        area = next(item for item in _demo_data()["areas"] if str(item["id"]) == area_id)
        area["simulated_monthly_demand"] = 0
        area["population_adjusted_baseline_units"] = 0
        _apply_existing_service_history(area, connection, surveys=updated["evidence"])
        assert area["survey_frequency_floor_monthly"] == 1
        assert area["survey_frequency_range_monthly"]["policy"] == "CONSERVATIVE_LOW"
    finally:
        connection.close()


def test_latest_evidence_and_further_survey_are_explicit_conflict_choices(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "conflict-resolution-options.sqlite")
    try:
        _insert_survey(
            connection, area_id, survey_type="phone", survey_date="2026-09-01", frequency=2
        )
        latest_id = _insert_survey(
            connection,
            area_id,
            survey_type="field",
            survey_date="2026-09-05",
            frequency=4,
        )
        review = database.evidence_review(connection, area_id)
        conflict = next(
            item for item in review["conflicts"] if item["conflict_type"] == "FREQUENCY_CONFLICT"
        )

        result = database.resolve_evidence_conflict(
            connection,
            conflict_id=conflict["conflict_id"],
            method="LATEST_EVIDENCE",
            reason="최신 조사 우선",
        )
        latest_selection = planning_frequency_selection(
            review["evidence"],
            [
                {
                    **conflict,
                    "status": result["status"],
                    "resolution_method": result["resolution_method"],
                    "selected_survey_id": result["selected_survey_id"],
                }
            ],
        )
        assert result["selected_survey_id"] == latest_id
        assert latest_selection["frequencies"] == [4]

        followup = database.resolve_evidence_conflict(
            connection,
            conflict_id=conflict["conflict_id"],
            method="FURTHER_SURVEY",
            reason="추가 전화조사 요청",
        )
        followup_selection = planning_frequency_selection(
            review["evidence"],
            [
                {
                    **conflict,
                    "status": followup["status"],
                    "resolution_method": followup["resolution_method"],
                    "selected_survey_id": followup["selected_survey_id"],
                }
            ],
        )
        assert followup_selection["needs_further_survey"] is True
        assert followup_selection["precision_blocked"] is True
        assert followup_selection["frequencies"] == []
    finally:
        connection.close()


def test_approved_ai_draft_is_linked_to_its_survey_observation_and_evidence(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "approved-draft-evidence.sqlite")
    try:
        draft_id = database.insert_demand_structuring_draft(
            connection,
            area_id=area_id,
            survey_type="phone",
            survey_date="2026-09-01",
            source_text_redacted="세탁 서비스를 월 2회 원함",
            source_text_was_redacted=False,
            structured={"requests": []},
        )
        assert database.claim_demand_structuring_draft(connection, draft_id)
        survey_id = _insert_survey(connection, area_id)
        assert database.approve_demand_structuring_draft(
            connection,
            draft_id=draft_id,
            survey_ids=[survey_id],
            approved={"requests": [{"service_type": "laundry"}]},
        )
        connection.commit()

        record = next(
            item
            for item in database.evidence_review(connection, area_id)["evidence"]
            if item["survey_id"] == survey_id
        )
        assert record["approved_draft_id"] == draft_id
        assert record["observation_id"]
        assert record["evidence_id"]
        assert record["observation_source_type"] == "phone"
        assert record["evidence_type"] == "survey_form"
        assert record["evidence_payload"]["service_type"] == "laundry"
    finally:
        connection.close()


def test_confirmed_distinct_keeps_both_requests_countable(tmp_path) -> None:
    connection, area_id = _connect(tmp_path / "confirmed-distinct.sqlite")
    try:
        first = _insert_survey(connection, area_id)
        second = _insert_survey(connection, area_id)
        database.evidence_review(connection, area_id)
        database.resolve_duplicate_pair(
            connection,
            area_id=area_id,
            first_survey_id=first,
            second_survey_id=second,
            decision="LINKED_DUPLICATE",
            reason="초기 검토에서 연결",
        )

        result = database.resolve_duplicate_pair(
            connection,
            area_id=area_id,
            first_survey_id=first,
            second_survey_id=second,
            decision="CONFIRMED_DISTINCT",
            reason="별도 요청으로 확인",
        )
        review = database.evidence_review(connection, area_id)
        records = database.list_surveys(connection, area_id, "laundry")

        assert result["state"] == "CONFIRMED_DISTINCT"
        assert all(item["canonical_survey_id"] == item["survey_id"] for item in records)
        assert any(
            item["status"] == "CONFIRMED_DISTINCT" for item in review["duplicate_candidates"]
        )
        assert sum(item["action"] == "CONFIRM_DISTINCT" for item in review["audit"]) == 1
    finally:
        connection.close()
