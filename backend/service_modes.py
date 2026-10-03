"""Service delivery modes, funding sources, and cost categories (V4 §8, §11).

Delivery mode is a policy choice. These tables describe which modes a service
can use; they never rank one mode as the best.
"""

from __future__ import annotations

from typing import Literal

ServiceMode = Literal[
    "HOME_VISIT",
    "VILLAGE_PICKUP",
    "VILLAGE_HUB",
    "MOBILE_SERVICE",
    "DELIVERY",
    "SHUTTLE_TO_HUB",
    "HYBRID",
]

SERVICE_MODE_LABELS_KO: dict[str, str] = {
    "HOME_VISIT": "가정방문형",
    "VILLAGE_PICKUP": "마을 수거·배달형",
    "VILLAGE_HUB": "마을 거점형",
    "MOBILE_SERVICE": "이동형 (차량 순회)",
    "DELIVERY": "배달형",
    "SHUTTLE_TO_HUB": "거점 이동 지원형",
    "HYBRID": "혼합형",
}

SERVICE_ALLOWED_MODES: dict[str, tuple[str, ...]] = {
    "laundry": ("VILLAGE_PICKUP", "MOBILE_SERVICE", "HOME_VISIT", "VILLAGE_HUB", "HYBRID"),
    "daily_necessities": ("VILLAGE_HUB", "DELIVERY"),
    "home_repair": ("HOME_VISIT",),
}

FundingSource = Literal[
    "LOCAL_GOV_BUDGET",
    "CENTRAL_GOV_SUBSIDY",
    "PUBLIC_PROGRAM",
    "USER_FEE",
    "COOPERATIVE_REVENUE",
    "DONATION",
    "SOCIAL_CONTRIBUTION",
    "OTHER",
]

FUNDING_SOURCE_LABELS_KO: dict[str, str] = {
    "LOCAL_GOV_BUDGET": "지자체 예산",
    "CENTRAL_GOV_SUBSIDY": "국비 보조",
    "PUBLIC_PROGRAM": "공공 일자리·자활 등 사업",
    "USER_FEE": "이용료",
    "COOPERATIVE_REVENUE": "협동조합 수익",
    "DONATION": "기부금",
    "SOCIAL_CONTRIBUTION": "사회공헌",
    "OTHER": "기타",
}

CostCategory = Literal[
    "FIXED_INFRASTRUCTURE_COST",
    "STAFF_COST",
    "VEHICLE_COST",
    "TRAVEL_DISTANCE_COST",
    "TRAVEL_TIME_COST",
    "MATERIAL_COST",
    "SERVICE_EXECUTION_COST",
    "FACILITY_OPERATING_COST",
    "MAINTENANCE_COST",
]

COST_CATEGORY_LABELS_KO: dict[str, str] = {
    "FIXED_INFRASTRUCTURE_COST": "고정 시설비",
    "STAFF_COST": "인건비",
    "VEHICLE_COST": "차량비",
    "TRAVEL_DISTANCE_COST": "이동거리 비용",
    "TRAVEL_TIME_COST": "이동시간 비용",
    "MATERIAL_COST": "재료비",
    "SERVICE_EXECUTION_COST": "서비스 수행비",
    "FACILITY_OPERATING_COST": "시설 운영비",
    "MAINTENANCE_COST": "유지보수비",
}
