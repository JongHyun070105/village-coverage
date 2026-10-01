"""Canonical service taxonomy and initial policy status for the pilot product."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ServicePolicyStatus = Literal["ALLOWED", "REGULATED", "EXCLUDED"]


@dataclass(frozen=True, slots=True)
class ServiceDefinition:
    service_type_id: str
    label_ko: str
    policy_status: ServicePolicyStatus
    policy_reason: str
    keywords: tuple[str, ...]


SERVICE_REGISTRY_PROVENANCE = "POLICY: INITIAL DEMO SCOPE"

SERVICE_REGISTRY: tuple[ServiceDefinition, ...] = (
    ServiceDefinition(
        "laundry", "세탁", "ALLOWED", "초기 지원 서비스", ("세탁", "빨래")
    ),
    ServiceDefinition(
        "daily_necessities",
        "생활용품 전달·지원",
        "ALLOWED",
        "초기 지원 서비스",
        ("생필품", "장보기", "장 보러", "식료품", "장날"),
    ),
    ServiceDefinition(
        "home_repair",
        "간단한 주거생활 지원",
        "ALLOWED",
        "초기 지원 서비스",
        ("수리", "집수리", "전구", "보일러", "방충망"),
    ),
    ServiceDefinition(
        "mobility_support",
        "이동 지원",
        "EXCLUDED",
        "초기 시범사업의 서비스 범위 밖입니다.",
        ("이동지원", "병원동행", "병원 동행", "교통지원"),
    ),
    ServiceDefinition(
        "medical_service",
        "의료 서비스",
        "REGULATED",
        "인허가 전문 인력이 필요한 서비스로 초기 지원 범위에서 제외합니다.",
        ("의료 서비스", "의료서비스", "병원 진료", "진료", "처방", "투약", "주사", "간호"),
    ),
    ServiceDefinition(
        "legal_service",
        "법률 서비스",
        "REGULATED",
        "법률 자문·대리는 초기 지원 범위에서 제외합니다.",
        ("법률 상담", "법률 자문", "법률지원", "변호사", "소송"),
    ),
)


def service_definition_map() -> dict[str, ServiceDefinition]:
    return {service.service_type_id: service for service in SERVICE_REGISTRY}
