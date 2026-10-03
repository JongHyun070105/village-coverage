"""Registry of every evidence source shown in the 근거·출처 (data source) center.

Each entry states whether it is real, reference, or simulated data; its
spatial/temporal scope; the purpose it serves; what it must not be used for;
and its license state. An unclear license blocks ingestion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

LicenseStatus = Literal[
    "OPEN_NO_RESTRICTION",
    "CITATION_WITH_ATTRIBUTION",
    "API_TERMS",
    "UNCLEAR",
    "NOT_APPLICABLE",
]
Reality = Literal["REAL", "REFERENCE", "SIMULATED"]


@dataclass(frozen=True, slots=True)
class DataSource:
    source_id: str
    name_ko: str
    publisher: str
    role: str
    reality: Reality
    reference_date: str
    spatial_scope: str
    update_cycle: str
    purpose: str
    limitations: tuple[str, ...]
    must_not: tuple[str, ...]
    license_status: LicenseStatus
    reuse_allowed: bool
    source_url: str
    checked_at: str

    @property
    def ingest_status(self) -> str:
        if self.license_status == "UNCLEAR" or not self.reuse_allowed:
            return "INGEST_BLOCKED"
        return "INGEST_ALLOWED"


SOURCES: tuple[DataSource, ...] = (
    DataSource(
        source_id="KREI_R2025_23",
        name_ko="KREI 농촌 주민 생활서비스 필요·이용 (R 2025-23 <표 4-8>)",
        publisher="한국농촌경제연구원",
        role="EXTERNAL_EMPIRICAL_PRIOR",
        reality="REFERENCE",
        reference_date="2025-12",
        spatial_scope="전국 농촌 표본조사",
        update_cycle="비정기 (연구보고서)",
        purpose="서비스별 농촌 필요도·이용률·미충족률 외부 기준값",
        limitations=(
            "표본 크기가 이 보고서에 명시되지 않음",
            "읍면·마을 단위 대표값 아님",
        ),
        must_not=("특정 마을의 실제 수요로 표시", "필요도×인구를 서비스 회차로 변환"),
        license_status="CITATION_WITH_ATTRIBUTION",
        reuse_allowed=True,
        source_url="https://repository.krei.re.kr/handle/2018.oak/32516",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="KOSIS_117_DT_117078",
        name_ko="KOSIS 사회서비스수요·공급실태조사 (보건복지부)",
        publisher="보건복지부 / 통계청 KOSIS",
        role="EXTERNAL_CONTEXT",
        reality="REFERENCE",
        reference_date="2023 (조사연도, 2년 주기)",
        spatial_scope="전국 가구",
        update_cycle="2년",
        purpose="사회서비스 영역별 필요·이용·이용의향 맥락 근거",
        limitations=(
            "사회서비스 분류가 농촌 생활서비스와 동일하지 않음",
            "전국 가구 기준; 농촌 한정 아님",
        ),
        must_not=("KREI 농촌 생활서비스 기준값과 혼합", "마을 수요로 사용"),
        license_status="API_TERMS",
        reuse_allowed=True,
        source_url="https://kosis.kr/openapi/",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="DATA_GO_KR_15120958",
        name_ko="주택관리공단 임대주택 관리홈닥터 월별지원현황",
        publisher="주택관리공단(주)",
        role="EXTERNAL_OPERATIONAL_REFERENCE",
        reality="REFERENCE",
        reference_date="2026-06-30 (파일 기준), 2021-10 이후 활용 권장",
        spatial_scope="공단 관리 임대주택 단지 (전국 지사)",
        update_cycle="연간",
        purpose="실제 월별 운영 건수의 변동성·시계열 검증 프레임워크",
        limitations=(
            "데이터가 없는 일자 포함; 2021년 10월 이후 활용 권장 (제공기관 명시)",
            "임대주택 취약계층 운영자료이며 농촌 마을 수요가 아님",
        ),
        must_not=("농촌 수요 기준값으로 사용", "마을 서비스 회차로 변환"),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15120958/fileData.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="MOIS_15099158",
        name_ko="행정안전부 법정동별 주민등록 인구",
        publisher="행정안전부",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2026-08-31",
        spatial_scope="법정리 (시범 3개 읍면)",
        update_cycle="월간",
        purpose="총인구·65/75/80세 이상 인구",
        limitations=("행정리와 법정리 경계 불일치 가능",),
        must_not=("인구를 수요로 직접 환산",),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15099158/fileData.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="MOIS_15099160",
        name_ko="행정안전부 1인세대 현황",
        publisher="행정안전부",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2026-08-31",
        spatial_scope="법정리 (시범 3개 읍면)",
        update_cycle="월간",
        purpose="1인세대·고령 1인세대 집계",
        limitations=("세대 기준이며 실제 독거 여부와 다를 수 있음",),
        must_not=("개인 식별",),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15099160/fileData.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="STD_15114136",
        name_ko="마을회관·경로당 표준데이터",
        publisher="공공데이터포털 표준데이터",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2026-08-27",
        spatial_scope="전국 (시범 지역 법정코드 결합)",
        update_cycle="수시",
        purpose="거점 후보 시설 수·대표 좌표",
        limitations=("일부 지역은 시설 행 단위 상세 없이 집계만 보유",),
        must_not=("시설 운영 가능 여부를 확정",),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15114136/standard.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="KAKAO_MOBILITY",
        name_ko="카카오모빌리티 경로 (도로 거리·시간)",
        publisher="카카오모빌리티",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="경로 캐시 생성 시점",
        spatial_scope="시범 지역 대표 좌표 간",
        update_cycle="캐시 재생성 시",
        purpose="이동시간·거리 행렬",
        limitations=("대표 좌표 간 경로이며 개별 가구 위치 아님", "경로 누락 시 계획에서 제외"),
        must_not=("직선거리로 대체",),
        license_status="API_TERMS",
        reuse_allowed=True,
        source_url="https://developers.kakaomobility.com/",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="SIM_PROVIDER_DEMAND",
        name_ko="모의 공급자 운영조건·수요 관측",
        publisher="VillageCoverage (seed 2026)",
        role="SIMULATION",
        reality="SIMULATED",
        reference_date="생성 시점",
        spatial_scope="시범 지역",
        update_cycle="재생성 시",
        purpose="알고리즘 검증용 공급자 가용성·용량·단가, 요청 관측",
        limitations=("실제 공급자·주민 자료 아님",),
        must_not=("실제 공급자 일정·수요로 표시",),
        license_status="NOT_APPLICABLE",
        reuse_allowed=True,
        source_url="",
        checked_at="2026-10-03",
    ),
)


def source_payload(source: DataSource) -> dict[str, object]:
    payload = asdict(source)
    payload["limitations"] = list(source.limitations)
    payload["must_not"] = list(source.must_not)
    payload["ingest_status"] = source.ingest_status
    return payload


def source_map() -> dict[str, DataSource]:
    return {source.source_id: source for source in SOURCES}
