"""Resident feedback API (intake form, staff review, conflicts, duplicates)."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from backend import database, resident_feedback
from backend.evidence_source_policy import source_policy_payload

router = APIRouter(prefix="/api")

FeedbackType = Literal[
    "DATA_CORRECTION", "SERVICE_REQUEST", "ACCESSIBILITY_ISSUE", "UNMET_SERVICE",
    "SCHEDULE_CONCERN", "OTHER",
]
ReviewRole = Literal["PLANNER", "REVIEWER"]


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimed_frequency_per_month: int | None = Field(default=None, ge=1, le=31)
    claims_demand: bool | None = None


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    area_id: str = Field(min_length=1, max_length=120)
    service_type: str | None = Field(default=None, max_length=60)
    feedback_type: FeedbackType
    description: str = Field(min_length=1, max_length=2000)
    requested_change: str | None = Field(default=None, max_length=1000)
    claim: ClaimInput | None = None
    submitter_role: Literal["RESIDENT", "VILLAGE_LEADER", "STAFF_ASSISTED", "OTHER"] = "RESIDENT"
    intake_channel: Literal["PUBLIC_FORM", "STAFF_ASSISTED"] = "PUBLIC_FORM"
    contact: str | None = Field(default=None, max_length=200)


class FeedbackActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start_review", "request_info", "accept", "reject", "resolve"]
    role: ReviewRole
    note: str | None = Field(default=None, max_length=1000)


class FeedbackConflictResolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_method: Literal["KEEP_OFFICIAL_EVIDENCE", "FURTHER_SURVEY", "ACCEPT_AS_RANGE"]
    role: ReviewRole
    reason: str = Field(min_length=1, max_length=1000)


class FeedbackDuplicateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    other_feedback_id: str = Field(min_length=1, max_length=120)
    state: Literal["LINKED_DUPLICATE", "CONFIRMED_DISTINCT"]
    role: ReviewRole
    reason: str = Field(min_length=1, max_length=1000)
    canonical_feedback_id: str | None = Field(default=None, max_length=120)


def _connection() -> sqlite3.Connection:
    from backend import main

    connection = database.connect()
    database.seed_reference_data(connection, main._load_demo())
    return connection


@router.post("/feedback", status_code=201)
def submit_feedback(item: FeedbackInput) -> dict[str, Any]:
    payload = item.model_dump(exclude_none=True)
    connection = _connection()
    try:
        return resident_feedback.submit_feedback(connection, payload)
    finally:
        connection.close()


@router.get("/feedback")
def list_feedback(
    region_id: str | None = Query(default=None, max_length=120),
    area_id: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    connection = _connection()
    try:
        items = resident_feedback.list_feedback(
            connection, region_id=region_id, area_id=area_id, status=status, limit=limit
        )
        return {
            "items": items,
            "status_labels": resident_feedback.STATUS_LABELS_KO,
            "source_policy": source_policy_payload(),
        }
    finally:
        connection.close()


@router.get("/feedback/export")
def export_feedback(region_id: str | None = Query(default=None, max_length=120)) -> dict[str, Any]:
    connection = _connection()
    try:
        return {
            "rows": resident_feedback.export_feedback_rows(connection, region_id),
            "legend": "LOCAL OBSERVATION (UNVERIFIED RESIDENT CLAIM); contact excluded",
        }
    finally:
        connection.close()


@router.get("/feedback/{feedback_id}")
def get_feedback(feedback_id: str) -> dict[str, Any]:
    connection = _connection()
    try:
        return resident_feedback.get_feedback(connection, feedback_id)
    finally:
        connection.close()


@router.get("/feedback/{feedback_id}/contact")
def get_feedback_contact(
    feedback_id: str, role: Annotated[ReviewRole, Query()]
) -> dict[str, Any]:
    connection = _connection()
    try:
        resident_feedback.get_feedback(connection, feedback_id)
        return {"feedback_id": feedback_id, "contact": resident_feedback.get_contact(
            connection, feedback_id)}
    finally:
        connection.close()


@router.post("/feedback/{feedback_id}/action")
def feedback_action(feedback_id: str, item: FeedbackActionInput) -> dict[str, Any]:
    connection = _connection()
    try:
        return resident_feedback.transition_feedback(
            connection, feedback_id, item.action, item.role, item.note
        )
    finally:
        connection.close()


@router.post("/feedback/{feedback_id}/duplicates")
def feedback_duplicate_decision(feedback_id: str, item: FeedbackDuplicateInput) -> dict[str, Any]:
    connection = _connection()
    try:
        decision = resident_feedback.decide_duplicate(
            connection, feedback_id, item.other_feedback_id, item.state, item.role,
            item.reason, item.canonical_feedback_id,
        )
        return {"decision": decision, "feedback": resident_feedback.get_feedback(
            connection, feedback_id)}
    finally:
        connection.close()


@router.post("/feedback/conflicts/{conflict_id}/resolve")
def resolve_feedback_conflict(
    conflict_id: str, item: FeedbackConflictResolutionInput
) -> dict[str, Any]:
    connection = _connection()
    try:
        return resident_feedback.resolve_conflict(
            connection, conflict_id, item.resolution_method, item.role, item.reason
        )
    finally:
        connection.close()


@router.get("/villages/{area_id}/feedback")
def area_feedback(area_id: str) -> dict[str, Any]:
    connection = _connection()
    try:
        return resident_feedback.area_feedback_summary(connection, area_id)
    finally:
        connection.close()


@router.get("/regions/{region_id}/feedback-attention")
def feedback_attention(region_id: str) -> dict[str, Any]:
    connection = _connection()
    try:
        return resident_feedback.attention_counts(connection, region_id)
    finally:
        connection.close()
