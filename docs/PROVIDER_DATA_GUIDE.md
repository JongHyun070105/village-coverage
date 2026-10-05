# 공급자 데이터 안내

## 공식 directory 검토 결과 (2026-10-06)

| 자료 | 제공기관 / 지역 | 라이선스·재사용 | 기준일·갱신 | V5.2 상태 |
|---|---|---|---|---|
| [전국 자활기업 현황](https://www.data.go.kr/data/15091502/fileData.do) | 한국자활복지개발원 / 전국 | 포털의 이용허락범위 제한 없음 | 2025-12-31 / 연간, 다음 등록 예정 2027-04-08 | 허용; 원본 977행 수집 |
| [사회적기업 목록](https://www.data.go.kr/data/15090110/fileData.do) | 고용노동부 / 전국 | 포털의 이용허락범위 제한 없음 | 2025-06-30 / 수시 자동 갱신 안내 | 허용; 공식 SEIS 목록으로 연결되나 확인 가능한 직접 bulk 파일을 찾지 못해 미수집 |
| [전국 마을기업 현황](https://www.data.go.kr/data/15080745/fileData.do) | 행정안전부 / 전국 | 포털의 이용허락범위 제한 없음 | 2025-12-31 / 연간, 다음 등록 예정 2027-09-14 | 허용; 원본 1,727행 수집, 포털 메타데이터 1,726행과 차이 경고 |
| [전국협동조합표준데이터](https://www.data.go.kr/data/15155661/standard.do) | 기획재정부 소관·지자체 제공 / 전국 | 명확한 재사용 허가 문구를 확인하지 못함 | 포털 2026-09-15 수정 표기; 월별 병합 | `INGEST_BLOCKED`; 라이선스 확인 전 수집 금지 |

검토 기준일 이후 URL, 조건, 기준일이 바뀔 수 있으므로 실제 수집 때 공식 페이지와 파일을 다시 확인합니다. 감사 기록은 `artifacts/provider_source_audit.json`에 있습니다.

## 해석과 개인정보

- `REAL_DIRECTORY`는 해당 기준일의 공식 목록에 조직 레코드가 있었다는 의미입니다. 운영 중, 지역 방문 가능, 서비스 제공 능력, 계약 의사 또는 참여 확정을 뜻하지 않습니다.
- directory 파일에서 대표자명, 사업자등록번호 등 개인 식별 가능 열을 정규화 스냅샷에 복사하지 않습니다. 사업장 주소의 연락처 형식도 가립니다.
- 공급 가능성, 일별 availability, capacity, service duration, price, minimum compensation, participation은 별도 검증 전까지 모두 `UNKNOWN` 또는 사용자가 명시한 `SIMULATED`입니다.
- 지도상 거리·서비스 유형은 후보 신호만 제공합니다. UI 표현은 “거리상 후보”, “서비스 유형상 후보”, “운영 가능 여부 확인 필요”로 한정해야 합니다.
- 공급자 응답은 `PROVIDER_SELF_REPORTED`, 지자체 현장 확인은 `LOCAL_AUTHORITY_VERIFIED`로 출처를 남기고 검증일과 검증자를 별도로 보관합니다.

## 중복과 서비스 매핑

- 같은 이름·주소 신호는 `POSSIBLE_DUPLICATE` 검토 후보만 만들며 자동 병합·삭제하지 않습니다. 전화번호나 법인 식별자는 이 초기 directory snapshot의 매칭 근거로 저장하지 않습니다.
- 업종·서비스 설명은 rule-based `MAPPING_SUGGESTED` 또는 `UNMAPPED`로 시작합니다. 담당자가 `VERIFIED_MAPPING` 또는 `REJECTED_MAPPING`으로 검토하기 전 계획 공급 능력으로 취급하지 않습니다.
- 전기·가스·의료·법률·전문건설·자격/면허가 필요한 영역은 초기 서비스 scope로 자동 편입하지 않습니다. 간단 집수리는 `LIMITED`로 분류하고 정책 확인을 요구합니다.

## 갱신과 재현

수집 시 원본 SHA-256, 스키마 hash/version, source 기준일, downloaded_at, 정규화 snapshot을 함께 남깁니다. 스키마가 달라지면 `SCHEMA_DRIFT`로 중단하고 과거 snapshot을 유지합니다. 새 snapshot은 이미 승인된 계획의 스냅샷·계산 결과를 수정하지 않습니다.
