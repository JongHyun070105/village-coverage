"""Canonical service taxonomy and initial policy status for the pilot product."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.home_repair import licensed_terms

ServicePolicyStatus = Literal["ALLOWED", "REGULATED", "EXCLUDED"]
RegulationLevel = Literal["UNREGULATED", "LIMITED", "LICENSE_REQUIRED", "EXCLUDED"]
ServiceUnitType = Literal["ROUND", "JOB", "HOUSEHOLD", "BATCH", "VISIT"]

REGULATION_LEVELS: tuple[str, ...] = ("UNREGULATED", "LIMITED", "LICENSE_REQUIRED", "EXCLUDED")
SERVICE_UNIT_TYPES: tuple[str, ...] = ("ROUND", "JOB", "HOUSEHOLD", "BATCH", "VISIT")
POLICY_FOR_REGULATION: dict[str, str] = {
    "UNREGULATED": "ALLOWED",
    "LIMITED": "ALLOWED",
    "LICENSE_REQUIRED": "REGULATED",
    "EXCLUDED": "EXCLUDED",
}


@dataclass(frozen=True, slots=True)
class ServiceDefinition:
    service_type_id: str
    label_ko: str
    policy_status: ServicePolicyStatus
    policy_reason: str
    keywords: tuple[str, ...]
    regulation_level: RegulationLevel = "UNREGULATED"
    unit_type: ServiceUnitType = "ROUND"


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
        unit_type="BATCH",
    ),
    ServiceDefinition(
        "home_repair",
        "간단한 주거생활 지원",
        "ALLOWED",
        "초기 지원 서비스",
        ("수리", "집수리", "전구", "방충망", "문고리", "손잡이"),
        regulation_level="LIMITED",
        unit_type="JOB",
    ),
    ServiceDefinition(
        "licensed_repair",
        "자격·인허가 필요 수리",
        "REGULATED",
        "가스·전기·배관·방수·구조 작업은 자격 보유자 작업이 필요해 간단 수리 범위에서 제외합니다.",
        licensed_terms(),
        regulation_level="LICENSE_REQUIRED",
        unit_type="JOB",
    ),
    ServiceDefinition(
        "mobility_support",
        "이동 지원",
        "EXCLUDED",
        "초기 시범사업의 서비스 범위 밖입니다.",
        ("이동지원", "병원동행", "병원 동행", "교통지원"),
        regulation_level="EXCLUDED",
        unit_type="VISIT",
    ),
    ServiceDefinition(
        "medical_service",
        "의료 서비스",
        "REGULATED",
        "인허가 전문 인력이 필요한 서비스로 초기 지원 범위에서 제외합니다.",
        ("의료 서비스", "의료서비스", "병원 진료", "진료", "처방", "투약", "주사", "간호"),
        regulation_level="LICENSE_REQUIRED",
        unit_type="VISIT",
    ),
    ServiceDefinition(
        "legal_service",
        "법률 서비스",
        "REGULATED",
        "법률 자문·대리는 초기 지원 범위에서 제외합니다.",
        ("법률 상담", "법률 자문", "법률지원", "변호사", "소송"),
        regulation_level="LICENSE_REQUIRED",
        unit_type="VISIT",
    ),
)


def service_definition_map() -> dict[str, ServiceDefinition]:
    return {service.service_type_id: service for service in SERVICE_REGISTRY}
