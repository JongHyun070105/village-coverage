"""External empirical priors encoded verbatim from KREI R 2025-23 (<표 4-8>, <표 4-9>).

Values are copied from the published report; nothing is interpolated.
need_rate is a demand-propensity prior from a rural survey. It is never a
village's observed demand and is never multiplied by population to produce a
service-visit count.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Literal

KREI_SOURCE_ID = "KREI_R2025_23_T4_8"

KREI_SOURCE = {
    "source_id": KREI_SOURCE_ID,
    "source_title": "저출생·초고령화에 대응한 농촌정책의 전환(2/2차 연도)",
    "publisher": "한국농촌경제연구원",
    "report_id": "R 2025-23",
    "series": "경제·인문사회연구회 협동연구 총서 25-32-01",
    "isbn": "979-11-6149-816-4 93520",
    "published_date": "2025-12",
    "chapter": "제4장 농촌 주민의 기초 생활서비스 접근 및 이용 지원 방안",
    "table_id": "<표 4-8> 농촌 주민의 생활서비스 필요 충족 현황",
    "report_page": 68,
    "underlying_survey": (
        "이순미·김정섭 외(2025), '농촌 주민 생활서비스 이용 현황 및 만족도 조사' 원자료"
    ),
    "source_url": "https://repository.krei.re.kr/bitstream/2018.oak/32516/1/R2025-23.pdf",
    "catalog_url": "https://repository.krei.re.kr/handle/2018.oak/32516",
    "license_status": "CITATION_WITH_ATTRIBUTION",
    "license_note": "보고서 판권면: 출처를 명시하면 자유롭게 인용할 수 있습니다.",
    "reuse_allowed": True,
    "checked_at": "2026-10-03",
    "sample_size": "NOT_STATED_IN_SOURCE",
    "population_scope": "농촌 주민 (조사 응답자)",
    "source_scope": "전국 농촌 표본조사; 특정 마을·읍면 대표값 아님",
    "provenance": "EXTERNAL_EMPIRICAL_PRIOR",
}

DEFINITIONS = {
    "need_rate": "‘전혀 필요 없음’과 ‘필요 없음’에 응답한 사람을 제외한 비율",
    "usage_rate": "서비스를 필요로 하는 사람 중 서비스를 이용한 사람의 비율",
    "unmet_rate": "서비스 필요자 중 서비스 미이용자의 비율",
    "unmet_by_program": (
        "‘농촌 생활돌봄 지원사업’(정부·지자체 유사 지원사업 통칭) 수행/미수행 지역별 미충족률"
    ),
}

NOT_INTENDED_USES = (
    "need_rate × 인구를 서비스 회차로 변환하는 용도",
    "특정 마을의 실제 수요로 표시하는 용도",
    "지역 조사 없이 LOCAL_CALIBRATED 상태를 부여하는 근거",
)

KreiCategory = Literal["일상생활 유지", "문화·여가, 체육", "주거환경"]


@dataclass(frozen=True, slots=True)
class ExternalEmpiricalPrior:
    source_id: str
    row_number: int
    service_label: str
    category: KreiCategory
    service_type: str | None
    need_rate: float
    usage_rate: float
    unmet_rate: float
    unmet_rate_program_area: float
    unmet_rate_non_program_area: float
    population_scope: str = KREI_SOURCE["population_scope"]
    reference_year: int = 2025
    methodology: str = "표본조사 원자료 분석 (KREI 저자 작성)"
    sample_scope: str = KREI_SOURCE["source_scope"]
    provenance: str = "EXTERNAL_EMPIRICAL_PRIOR"
    confidence_class: str = "EMPIRICAL_EXTERNAL"
    unit: str = "%"
    definitions: dict[str, str] = field(default_factory=lambda: dict(DEFINITIONS))


def _row(
    n: int,
    label: str,
    cat: KreiCategory,
    service_type: str | None,
    need: float,
    usage: float,
    unmet: float,
    program: float,
    non_program: float,
) -> ExternalEmpiricalPrior:
    return ExternalEmpiricalPrior(
        source_id=KREI_SOURCE_ID,
        row_number=n,
        service_label=label,
        category=cat,
        service_type=service_type,
        need_rate=need,
        usage_rate=usage,
        unmet_rate=unmet,
        unmet_rate_program_area=program,
        unmet_rate_non_program_area=non_program,
    )


# Exact transcription of <표 4-8> (단위: %). service_type maps only the three
# V4 demo services; other rows are retained as context without an app mapping.
KREI_TABLE_4_8: tuple[ExternalEmpiricalPrior, ...] = (
    _row(1, "이동 및 외출 지원", "일상생활 유지", "mobility_support",
         13.2, 16.5, 83.5, 78.8, 88.9),
    _row(2, "반찬 지원, 장보기", "일상생활 유지", "daily_necessities",
         16.5, 14.0, 86.0, 83.8, 89.4),
    _row(3, "청소, 세탁", "일상생활 유지", "laundry", 19.0, 16.4, 83.6, 81.3, 87.8),
    _row(4, "목욕 지원", "일상생활 유지", None, 17.8, 26.7, 73.3, 67.5, 83.3),
    _row(5, "이미용", "일상생활 유지", None, 21.0, 20.1, 79.9, 77.3, 84.2),
    _row(6, "쓰레기/폐기물 처리", "일상생활 유지", None, 22.3, 12.8, 87.2, 84.7, 90.9),
    _row(7, "공동급식", "일상생활 유지", None, 18.8, 19.6, 80.4, 73.3, 92.3),
    _row(8, "평생교육 프로그램(한글, 외국어, IT 등)", "문화·여가, 체육", None,
         28.4, 21.1, 78.9, 80.2, 77.7),
    _row(9, "문화·여가 활동 지원(동아리, 공연 등)", "문화·여가, 체육", None,
         35.2, 29.7, 70.3, 74.6, 65.0),
    _row(10, "도서 대여", "문화·여가, 체육", None, 27.5, 16.3, 83.7, 89.2, 76.9),
    _row(11, "건강교실", "문화·여가, 체육", None, 41.1, 29.8, 70.2, 68.3, 73.1),
    _row(12, "상하수도, 동파, 보일러", "주거환경", None, 28.0, 4.9, 95.1, 96.9, 92.1),
    _row(13, "간단 집수리(문고리, 방충망, 세면대 수리, 전구·형광등 교체 등)", "주거환경",
         "home_repair", 31.8, 5.6, 94.4, 95.3, 93.0),
    _row(14, "누전·가스차단기, 전기 수리", "주거환경", None, 33.1, 5.8, 94.2, 96.2, 90.4),
    _row(15, "안전손잡이, 계단 난간 설치", "주거환경", None, 25.6, 7.4, 92.6, 93.3, 91.2),
    _row(16, "도배, 실내 장판 교체", "주거환경", None, 31.2, 6.6, 93.4, 97.2, 87.1),
)

# Table-level "전체" row (any one service needed/used).
KREI_TABLE_4_8_TOTAL = {"need_rate": 61.5, "usage_rate": 40.3, "unmet_rate": 59.7,
                        "unmet_rate_program_area": 59.1, "unmet_rate_non_program_area": 60.8}

V4_DEMO_SERVICES = ("laundry", "daily_necessities", "home_repair")


def prior_for_service(service_type: str) -> ExternalEmpiricalPrior | None:
    for row in KREI_TABLE_4_8:
        if row.service_type == service_type:
            return row
    return None


def prior_payload(row: ExternalEmpiricalPrior) -> dict[str, object]:
    payload = asdict(row)
    payload.update(
        {
            "source_title": KREI_SOURCE["source_title"],
            "publisher": KREI_SOURCE["publisher"],
            "report_id": KREI_SOURCE["report_id"],
            "published_date": KREI_SOURCE["published_date"],
            "table_id": KREI_SOURCE["table_id"],
            "definition": DEFINITIONS["need_rate"],
            "source_scope": KREI_SOURCE["source_scope"],
            "display_label": "농촌 외부 조사 기준값",
            "interpretation_warning": (
                "외부 농촌 조사값을 해당 마을 실제 수요로 해석하면 안 됩니다."
            ),
        }
    )
    return payload


# ---------------------------------------------------------------------------
# <표 4-9> laundry service cases and chapter-4 operating patterns.
# CASE_REFERENCE only: never used as a default policy or national cost value.


@dataclass(frozen=True, slots=True)
class LaundryCaseReference:
    case_id: str
    name: str
    location: str
    operation_type: str
    operator: str
    funding_sources: tuple[str, ...]
    pickup_days: str | None
    processing_days: str | None
    delivery_days: str | None
    vehicle_count: int | None
    machine_capacity: str | None
    daily_capacity: str | None
    eligible_population: str | None
    general_fee: str | None
    discount_policy: str | None
    staffing: str | None
    care_linkage: bool
    notes: str
    usage: str = "CASE_REFERENCE"
    source_table: str = "<표 4-9> 세탁 서비스 사례 (R 2025-23, p.71)"


LAUNDRY_CASES: tuple[LaundryCaseReference, ...] = (
    LaundryCaseReference(
        case_id="krei-laundry-sapyeong",
        name="사평 빨래방",
        location="전남 화순군",
        operation_type="VILLAGE_PICKUP",
        operator="지방자치단체 직영 (화순군)",
        funding_sources=("LOCAL_GOV_BUDGET", "SOCIAL_CONTRIBUTION"),
        pickup_days="월·수·금 (경로당·마을회관 방문 수거)",
        processing_days="화·목 세탁·건조·검수",
        delivery_days="화·목 배달",
        vehicle_count=3,
        machine_capacity="대형 세탁기(50kg) 5대, 소형 세탁기(25kg) 3대, 대형 건조기 3대, "
        "소형 건조기 2대",
        daily_capacity="하루 겨울 이불 150채",
        eligible_population="65세 이상, 장애인, 차상위 계층 무료",
        general_fee="일반 군민 겨울 이불 1만 원, 기타 이불 5000원",
        discount_policy="사평면 주민 50% 감면",
        staffing="전담 인력 20명 (70% 취약계층 여성·노인 채용)",
        care_linkage=True,
        notes="건축비 14억 원 투입; 강원랜드 사회공헌재단 운영비 지원; 정기 수거 시 안부 확인",
    ),
    LaundryCaseReference(
        case_id="krei-laundry-namseong",
        name="공감 세탁",
        location="제주도 남성마을",
        operation_type="HOME_VISIT",
        operator="주민 공동체 (남성 마을관리 사회적 협동조합)",
        funding_sources=("DONATION", "COOPERATIVE_REVENUE"),
        pickup_days="직접 방문 접수",
        processing_days=None,
        delivery_days=None,
        vehicle_count=None,
        machine_capacity="마을 내 세탁소와 협약해 전문 세탁 수행",
        daily_capacity=None,
        eligible_population="독거노인, 장애인 등 거동 불편 취약계층",
        general_fee=None,
        discount_policy=None,
        staffing="활동가 6명 (2인1조)",
        care_linkage=True,
        notes="연 2회 계절별 이불 세탁; 말벗·위생 점검·생활지도 병행, 안전 문제 시 행정기관 연계",
    ),
    LaundryCaseReference(
        case_id="krei-laundry-samcheok",
        name="희망을 담은 빨래바구니",
        location="강원 삼척시",
        operation_type="HYBRID",
        operator="노인 일자리 사업 수행기관",
        funding_sources=("PUBLIC_PROGRAM", "SOCIAL_CONTRIBUTION"),
        pickup_days="방문 수거",
        processing_days=None,
        delivery_days="방문 배달",
        vehicle_count=None,
        machine_capacity="고정형 빨래방",
        daily_capacity=None,
        eligible_population="고령 어르신, 장애인, 기초생활수급자 등 취약계층",
        general_fee=None,
        discount_policy=None,
        staffing="노인 일자리 참여자 30명",
        care_linkage=True,
        notes="노노케어 형태 돌봄; 생필품 구매 대행 병행",
    ),
    LaundryCaseReference(
        case_id="krei-laundry-gammul",
        name="커뮤니티 편의점",
        location="충북 괴산 감물면",
        operation_type="VILLAGE_HUB",
        operator="주민 공동체 ‘달천신나는협동조합’",
        funding_sources=("CENTRAL_GOV_SUBSIDY", "COOPERATIVE_REVENUE"),
        pickup_days=None,
        processing_days=None,
        delivery_days=None,
        vehicle_count=None,
        machine_capacity="대형 코인 세탁기 1대, 건조기 1대, 운동화 세탁기",
        daily_capacity=None,
        eligible_population=None,
        general_fee=None,
        discount_policy=None,
        staffing="주민 순번제",
        care_linkage=False,
        notes="괴산군 신활력플러스 사업 1억 원 지원; 세탁기 수익금은 장비 추가 구입; 편의점 병행",
    ),
    LaundryCaseReference(
        case_id="krei-laundry-gyeongnam",
        name="찾아가는 빨래방",
        location="경남",
        operation_type="MOBILE_SERVICE",
        operator="경상남도청, 경남 광역자활센터",
        funding_sources=("LOCAL_GOV_BUDGET", "PUBLIC_PROGRAM"),
        pickup_days="읍면 주민센터 신청 접수 후 주 5회 마을 방문",
        processing_days="현장 세탁·건조 (겨울 이불 40~50분)",
        delivery_days="현장 전달",
        vehicle_count=7,
        machine_capacity="이동형 세탁차량 (2.5톤 6대·1.2톤 1대)",
        daily_capacity=None,
        eligible_population="도내 65세 이상 어르신, 저소득 독거노인, 취약계층",
        general_fee=None,
        discount_policy=None,
        staffing="운영 인력 22명 (전담 2, 수행 20)",
        care_linkage=False,
        notes="연평균 1만 명 이용",
    ),
    LaundryCaseReference(
        case_id="krei-laundry-yeongam",
        name="기찬 빨래방",
        location="전남 영암",
        operation_type="MOBILE_SERVICE",
        operator="영암시니어클럽 (노인 일자리 사업 수행기관)",
        funding_sources=("PUBLIC_PROGRAM", "DONATION"),
        pickup_days="주 3회 순회",
        processing_days="수거→세탁→건조",
        delivery_days="배송",
        vehicle_count=1,
        machine_capacity="2.5톤 특수차량 1대 (세탁기 3, 건조기 1 탑재)",
        daily_capacity="하루 평균 18가구 방문",
        eligible_population="거동 불편 독거노인, 장애인 등 취약계층",
        general_fee=None,
        discount_policy=None,
        staffing=None,
        care_linkage=False,
        notes="연간 약 2,300가구 수혜 예상; 운영비·인건비 고향사랑기부금 충당; 읍면 11개 지역",
    ),
)

# Chapter 3 case in the pilot town (KREI R 2025-23, pp.50-51). Reference only.
JANGGOK_LAUNDRY_CASE = LaundryCaseReference(
    case_id="krei-laundry-janggok",
    name="행복나눔공동빨래방",
    location="충남 홍성군 장곡면",
    operation_type="HYBRID",
    operator="행복나눔공동빨래방 운영협의회 (장곡사협, 주민자치회 등)",
    funding_sources=("LOCAL_GOV_BUDGET", "USER_FEE", "COOPERATIVE_REVENUE"),
    pickup_days="주민자치회 자원봉사 수거",
    processing_days=None,
    delivery_days="주민자치회 자원봉사 배달",
    vehicle_count=None,
    machine_capacity="유휴 예비군 중대본부 건물 리모델링",
    daily_capacity=None,
    eligible_population="75세 이상 1회 3000원; 수급자·등록 장애인 등 무료",
    general_fee="일반 주민 5000원",
    discount_policy="75세 이상 3000원, 취약계층 무료",
    staffing="운영 매니저 (이용료·지원금으로 수당)",
    care_linkage=True,
    notes="2022년 홍성군 주민참여예산 공모사업; 전기·수도 요금은 면 행정복지센터, 세제는 "
    "지역사회보장협의체 부담",
    source_table="R 2025-23 제3장 3.2 (pp.50-51)",
)

SERVICE_DESIGN_REFERENCE_MODELS = (
    {
        "model_id": "MOBILE_SERVICE",
        "label": "이동형 서비스",
        "rationale": "농촌의 분산성과 고령화에 대응; 세탁·상점 사례",
        "example_case_ids": ["krei-laundry-gyeongnam", "krei-laundry-yeongam"],
        "usage": "REFERENCE_MODEL",
    },
    {
        "model_id": "VILLAGE_HUB",
        "label": "복합 거점",
        "rationale": "마을회관·유휴 공공시설·공동공간 활용",
        "example_case_ids": ["krei-laundry-gammul", "krei-laundry-janggok"],
        "usage": "REFERENCE_MODEL",
    },
    {
        "model_id": "CARE_LINKED",
        "label": "돌봄결합형",
        "rationale": "세탁물 수거·배달 중 안부확인 등 서비스와 돌봄 결합",
        "example_case_ids": ["krei-laundry-sapyeong", "krei-laundry-namseong",
                             "krei-laundry-samcheok"],
        "usage": "REFERENCE_MODEL",
    },
)


def empirical_prior_snapshot() -> dict[str, object]:
    rows = [prior_payload(row) for row in KREI_TABLE_4_8]
    cases = [asdict(case) for case in (*LAUNDRY_CASES, JANGGOK_LAUNDRY_CASE)]
    body = {
        "source": KREI_SOURCE,
        "definitions": DEFINITIONS,
        "not_intended_uses": list(NOT_INTENDED_USES),
        "table_total": KREI_TABLE_4_8_TOTAL,
        "priors": rows,
        "laundry_cases": cases,
        "service_design_reference_models": list(SERVICE_DESIGN_REFERENCE_MODELS),
    }
    digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {"snapshot_hash": digest, **body}
