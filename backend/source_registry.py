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
        source_id="DATA_GO_KR_15155661",
        name_ko="전국협동조합표준데이터 (공급 후보 출처)",
        publisher="기획재정부 소관 / 지방자치단체 제공",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2026-09-15 (포털 수정일)",
        spatial_scope="전국 (지방자치단체 관리 협동조합)",
        update_cycle="수시; 개별기관 데이터는 월초 병합되어 시차 가능",
        purpose="지역의 잠재 협력조직 존재 여부를 조사할 후보 출처",
        limitations=(
            "서비스 분야, 운영 여부, 참여 의사, 인력, 수용량, 가격을 확인하지 않음",
            "대표자·전화번호 필드가 있으나 이 시스템은 원자료를 수집·표시하지 않음",
            "이용허락범위를 확인할 수 없어 실제 수집은 차단",
        ),
        must_not=("공급자 가용성·수용량으로 간주", "확인 없이 계획에 실제 공급자로 배정"),
        license_status="UNCLEAR",
        reuse_allowed=False,
        source_url="https://www.data.go.kr/data/15155661/standard.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="DATA_GO_KR_15091502",
        name_ko="전국 자활기업 현황 (공급 후보 출처)",
        publisher="한국자활복지개발원",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2025-12-31 (자료 기준일)",
        spatial_scope="전국",
        update_cycle="연간 (포털 차기 등록 예정 2027-04-08)",
        purpose="지역의 잠재 협력조직 존재 여부를 조사할 후보 출처",
        limitations=(
            "포털에 977개 행으로 안내된 2025-12-31 파일 기준",
            "업종 정보만으로 서비스 운영 여부, 참여 의사, 인력, 수용량, 가격을 알 수 없음",
            "대표자명 필드가 있으나 이 시스템은 원자료를 수집·표시하지 않음",
        ),
        must_not=("공급자 가용성·수용량으로 간주", "확인 없이 계획에 실제 공급자로 배정"),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15091502/fileData.do",
        checked_at="2026-10-03",
    ),
    DataSource(
        source_id="DATA_GO_KR_15090110",
        name_ko="고용노동부 사회적기업 목록 (공급 후보 출처)",
        publisher="고용노동부",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2025-06-30 (활동 중 목록 기준)",
        spatial_scope="전국",
        update_cycle="수시 (포털 자동 갱신 안내; 현재 공개 스냅샷은 2025-06-30)",
        purpose="공개된 사회적기업 조직·지역·사업내용·서비스분야 후보 확인",
        limitations=(
            "현재 페이지의 활동 기준일은 2025-06-30이며 실제 현재 활동 여부는 현장 확인 필요",
            "대표자 필드는 수집·저장하지 않음",
            "등재와 사업내용은 참여 의사, 가용 인력, 수용량, 가격을 입증하지 않음",
        ),
        must_not=("현재 참여 의사·공급 능력으로 간주", "확인 없이 계획에 실제 공급자로 배정"),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15090110/fileData.do",
        checked_at="2026-10-04",
    ),
    DataSource(
        source_id="DATA_GO_KR_15080745",
        name_ko="행정안전부 전국 마을기업 현황 (공급 후보 출처)",
        publisher="행정안전부",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2025-12-31",
        spatial_scope="전국 (2025-12 기준 1,726행)",
        update_cycle="연간 (포털 수정 2026-09-14; 차기 예정 2027-09-14)",
        purpose="공개된 마을기업 조직·소재지·업종·사업내용 후보 확인",
        limitations=(
            "정기 실태조사 스냅샷으로 현재 운영 여부는 기관·공급자 확인 필요",
            "파일 내 공백이 있을 수 있다고 포털이 안내",
            "대표전화 등 연락처는 수집·저장하지 않음",
            "등재는 공급 가용성·수용량·가격·참여 의사를 입증하지 않음",
        ),
        must_not=("현재 참여 의사·공급 능력으로 간주", "확인 없이 계획에 실제 공급자로 배정"),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15080745/fileData.do",
        checked_at="2026-10-04",
    ),
    DataSource(
        source_id="DATA_GO_KR_15064216",
        name_ko="전북특별자치도 부안군 협동조합 현황 (비대상 지역 참고)",
        publisher="전북특별자치도 부안군",
        role="PUBLIC_DATA",
        reality="REAL",
        reference_date="2025-08-20",
        spatial_scope="전북특별자치도 부안군 (57행; 시범 권역 밖)",
        update_cycle="수시 (1회성; 포털 수정 2025-12-26)",
        purpose="협동조합 기본정보·소재 범위의 출처 적합성 비교",
        limitations=(
            "부안군 자료이며 부여군 시범권역과 다른 지역",
            "조합명·설립일·주소만 포함하며 서비스 분야는 제공하지 않음",
            "소재지와 설립 정보만으로 현재 활동·서비스·수용량을 확인할 수 없음",
        ),
        must_not=("부여군 자료로 오인", "서비스 공급 후보 또는 가용성으로 간주"),
        license_status="OPEN_NO_RESTRICTION",
        reuse_allowed=True,
        source_url="https://www.data.go.kr/data/15064216/fileData.do",
        checked_at="2026-10-04",
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
