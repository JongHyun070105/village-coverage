# 지역 운영자료 가져오기 안내

Pilot API는 `POST /api/pilot-imports/{template_type}/preview`에서 업로드 파일을 파싱·검증하고, 담당자가 행별 결과를 확인한 뒤 `POST /api/pilot-imports/{batch_id}/confirm`으로 명시적으로 확정할 때만 운영 입력 레코드를 만듭니다. 오류행은 `GET /api/pilot-imports/{batch_id}/failed.csv`로 받을 수 있습니다. 파일 hash와 행 fingerprint로 재업로드·수정행을 구분합니다.

각 CSV 파일에는 PII를 넣지 마십시오. 검증은 연락처 패턴을 가리지만, 임의 메모에 적힌 민감정보를 모두 식별한다고 보장하지 않습니다. context를 지정하면 확정과 domain promotion이 한 transaction으로 처리되며, 계획은 그 context의 검증된 입력 snapshot만 사용합니다.

## 공통 규칙

- UTF-8 BOM 또는 CP949, 최대 10MB / 10,000행. 헤더가 다르면 파일 전체를 거절합니다.
- `ERROR` 행은 확정 시에도 저장되지 않고, `WARNING` 행은 경고를 확인한 뒤 확정됩니다. `INFO` 성격의 관측은 계산값으로 승격하지 않습니다.
- `source_type`: `PUBLIC_DATA`, `OFFICIAL_DIRECTORY`, `LOCAL_AUTHORITY_INPUT`, `SURVEY_INPUT`, `PROVIDER_SELF_REPORTED`, `SERVICE_EXECUTION_LOG`, `RESIDENT_FEEDBACK`, `SIMULATED`.
- 날짜는 `YYYY-MM-DD`, 서비스 코드는 `laundry`, `daily_necessities`, `home_repair`를 사용합니다. 알 수 없는 service 코드는 ERROR 행이며 promotion하지 않습니다. provider service의 빈 mapping suggestion은 담당자 review 전에 planning에 사용하지 않습니다.
- CSV 안의 중복은 경고되고 fingerprint가 같은 record는 한 번만 저장됩니다. 서로 다른 원본 행은 따로 보존됩니다.

## `region_areas`

파일: [`templates/region_areas.csv`](../templates/region_areas.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| area_code | string | yes | 4480031021 | 10자리 법정동 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| area_name | string | yes | 장곡면 오서리 | 마을 또는 서비스 권역 이름 | 낮음 | 행 단위 source_type을 따릅니다. |
| latitude | decimal | yes | 36.5123 | 대표 좌표 위도 | 낮음 | 행 단위 source_type을 따릅니다. |
| longitude | decimal | yes | 126.6123 | 대표 좌표 경도 | 낮음 | 행 단위 source_type을 따릅니다. |
| population_total | integer | yes | 420 | 기준 인구 | 낮음 | 행 단위 source_type을 따릅니다. |
| population_65_plus | integer | yes | 160 | 65세 이상 인구 | 낮음 | 행 단위 source_type을 따릅니다. |
| households_total | integer | yes | 210 | 기준 가구 수 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_date | date | yes | 2026-09-30 | 자료 기준일 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PUBLIC_DATA | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `demand_observations`

파일: [`templates/demand_observations.csv`](../templates/demand_observations.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| region_code | string | yes | 홍성군 | 지자체 또는 pilot 권역 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| area_code | area_code | yes | 4480031021 | 10자리 법정동 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| observed_date | date | yes | 2026-09-30 | 관측일 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| observed_count | integer | yes | 4 | 관측한 요청 또는 필요 건수; 행 수와 수요를 혼동하지 않도록 정의 필요 | 낮음 | 행 단위 source_type을 따릅니다. |
| observation_kind | string | yes | 전화 조사 | 관측 방식 또는 사건 유형 | 낮음 | 행 단위 source_type을 따릅니다. |
| note | string | yes | 세탁 지원 요청 4건 | 최소한의 비식별 근거 메모 | 높음; 전화번호·이름·주소·민감정보 입력 금지 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | SURVEY_INPUT | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `surveys`

파일: [`templates/surveys.csv`](../templates/surveys.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| region_code | string | yes | 홍성군 | 지자체 또는 pilot 권역 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| area_code | area_code | yes | 4480031021 | 10자리 법정동 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| survey_date | date | yes | 2026-09-30 | 조사일 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| survey_count | integer | yes | 12 | 유효 응답 수; 개인 수요로 자동 환산하지 않음 | 낮음 | 행 단위 source_type을 따릅니다. |
| eligible_population | integer | yes | 30 | 조사 대상 모집단 수 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | SURVEY_INPUT | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |
| note | string | no | 마을회관 대면 조사 | 조사 방법 메모 | 높음; 개인 식별 정보 입력 금지 | 행 단위 source_type을 따릅니다. |

## `provider_organizations`

파일: [`templates/provider_organizations.csv`](../templates/provider_organizations.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | 업무상 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| official_name | string | yes | 홍성돌봄협동조합 | 공식 조직명; 대표자 이름은 입력하지 않음 | 낮음 | 행 단위 source_type을 따릅니다. |
| organization_type | string | yes | 사회적기업 | 공식 directory의 조직 유형 | 낮음 | 행 단위 source_type을 따릅니다. |
| region_code | string | yes | 홍성군 | 등록 주소 기준 지자체 코드 또는 명칭 | 낮음 | 행 단위 source_type을 따릅니다. |
| public_business_address | string | no | 충남 홍성군 ... | 공개된 사업장 주소만 입력 | 중간; 개인 주거 주소 금지 | 행 단위 source_type을 따릅니다. |
| public_contact_available | boolean | yes | true | 공식 공개 연락처가 존재하는지 여부만 기록; 연락처 값은 넣지 않음 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_id | string | yes | DATA_GO_KR_15090110 | 공식 source registry 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_record_id | string | yes | row-000042 | 원본에서 해당 조직을 찾는 공개 레코드 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_snapshot | date | yes | 2025-06-30 | 디렉터리 기준일 | 낮음 | 행 단위 source_type을 따릅니다. |
| provenance | provenance | yes | REAL_DIRECTORY | 조직 존재 근거; 운영 검증 상태가 아님 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | OFFICIAL_DIRECTORY | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `provider_services`

파일: [`templates/provider_services.csv`](../templates/provider_services.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | provider_organizations의 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_description | string | yes | 주거환경개선 | 원문 서비스 설명 | 중간; 개인정보 포함 여부 확인 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | no | home_repair | VillageCoverage 후보 서비스 코드; 불명확하면 빈 값 | 낮음 | 행 단위 source_type을 따릅니다. |
| mapping_status | mapping_status | yes | MAPPING_SUGGESTED | UNMAPPED/MAPPING_SUGGESTED/VERIFIED_MAPPING/REJECTED_MAPPING | 낮음 | 행 단위 source_type을 따릅니다. |
| regulation_level | regulation_level | yes | LIMITED | UNREGULATED/LIMITED/LICENSE_REQUIRED/EXCLUDED | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PROVIDER_SELF_REPORTED | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `provider_availability`

파일: [`templates/provider_availability.csv`](../templates/provider_availability.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | provider_organizations의 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| available_date | date | yes | 2026-10-15 | 가용 여부 기준일 | 낮음 | 행 단위 source_type을 따릅니다. |
| available | boolean | yes | true | 공급자가 보고한 해당 일자 가용 여부 | 낮음 | 행 단위 source_type을 따릅니다. |
| start_time | time | no | 09:00 | 시작 시간 | 낮음 | 행 단위 source_type을 따릅니다. |
| end_time | time | no | 12:00 | 종료 시간 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PROVIDER_SELF_REPORTED | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `provider_capacity`

파일: [`templates/provider_capacity.csv`](../templates/provider_capacity.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | provider_organizations의 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| period_start | date | yes | 2026-10-01 | 수용량 기간 시작일 | 낮음 | 행 단위 source_type을 따릅니다. |
| period_end | date | yes | 2026-10-31 | 수용량 기간 종료일 | 낮음 | 행 단위 source_type을 따릅니다. |
| capacity_count | integer | yes | 20 | 해당 기간 내 보고 수용량; 0도 유효한 사실 | 낮음 | 행 단위 source_type을 따릅니다. |
| capacity_unit | string | yes | 회 | 수용량 단위 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PROVIDER_SELF_REPORTED | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `provider_prices`

파일: [`templates/provider_prices.csv`](../templates/provider_prices.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | provider_organizations의 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| effective_date | date | yes | 2026-10-01 | 가격 기준일 | 낮음 | 행 단위 source_type을 따릅니다. |
| price_won | integer | no | 25000 | 양수 원화 단가; 미확인 시 비워 UNKNOWN 경고로 남김 | 낮음 | 0원은 미확인 단가로 사용할 수 없습니다. |
| price_basis | string | no | 방문 1회 | 단가 산정 기준 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PROVIDER_SELF_REPORTED | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## `service_execution_logs`

파일: [`templates/service_execution_logs.csv`](../templates/service_execution_logs.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| plan_id | string | yes | plan-2026-10-01 | 실행 대상 계획 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| plan_version | integer | no | 2 | 실행 대상 승인 계획 버전 | 낮음 | plan_id·version은 반드시 실제 승인 계획과 맞아야 합니다. |
| round_id | string | no | round-001 | 실제 수행 대상 계획 회차 | 낮음 | 생략 시에도 단일 planned round로 유일하게 연결되어야 합니다. |
| provider_org_id | string | yes | SE-00042 | 실행 공급자 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| region_code | string | yes | 홍성군 | 지자체 또는 pilot 권역 | 낮음 | 행 단위 source_type을 따릅니다. |
| area_code | area_code | yes | 4480031021 | 10자리 법정동 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| scheduled_date | date | yes | 2026-10-15 | 계획된 수행일 | 낮음 | 행 단위 source_type을 따릅니다. |
| actual_date | date | no | 2026-10-15 | 실제 수행일; 미수행이면 빈 값 | 낮음 | `executed_date`도 호환 입력으로 지원합니다. |
| execution_status | execution_status | yes | COMPLETED | COMPLETED/PARTIALLY_COMPLETED/CANCELLED/NO_SHOW/PROVIDER_CANCELLED/RESCHEDULED | 낮음 | 행 단위 source_type을 따릅니다. |
| rounds | integer | yes | 1 | 실제 수행 회차 | 낮음 | 행 단위 source_type을 따릅니다. |
| actual_duration_minutes | integer | no | 55 | 실제 수행 시간(분) | 낮음 | 빠진 값은 UNKNOWN으로 유지합니다. |
| actual_cost_won | integer | no | 28000 | 실제 비용(원) | 낮음 | 빠진 값은 UNKNOWN으로 유지합니다. |
| completion_percent | integer | no | 100 | 완료 비율 0–100 | 낮음 | 실제 상태와 함께 검토합니다. |
| cancel_reason | string | no | 공급자 일정 변경 | 취소·미수행 사유 | 높음 | 연락처·상세주소·주민 자유문장을 입력하지 않습니다. |
| source_type | source_type | yes | SERVICE_EXECUTION_LOG | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |

## Context와 확인

Pilot Setup에서 context를 선택한 뒤 가져옵니다. Preview 시 context ID가
batch에 기록되며 확인 시 valid/warning 행만 promotion됩니다. 오류 행은
domain table에 들어가지 않습니다. 동일 파일의 batch 재확정은 idempotent이며
수정된 내용은 새 content hash와 batch가 됩니다. 수행로그는 반드시 동일
context의 `APPROVED` plan version에 연결해야 합니다.

가격은 양수 금액만 planning input으로 사용합니다. 가격이 없으면 비워
UNKNOWN 경고를 유지하거나, 담당자가 `SCENARIO_ASSUMPTION` 또는
`SIMULATED` provenance 및 사유를 기록합니다. 0원은 미확인 가격의 대체값으로
허용되지 않습니다.

## `provider_participation`

파일: [`templates/provider_participation.csv`](../templates/provider_participation.csv)

| field | type | required | example | description | PII risk | provenance interpretation |
|---|---|---:|---|---|---|---|
| provider_org_id | string | yes | SE-00042 | provider_organizations의 내부 식별자 | 낮음 | 행 단위 source_type을 따릅니다. |
| plan_id | string | yes | plan-2026-10-01 | 참여 의사를 확인한 계획 | 낮음 | 행 단위 source_type을 따릅니다. |
| service_type | service_type | yes | laundry | 서비스 코드 | 낮음 | 행 단위 source_type을 따릅니다. |
| participation_status | participation_status | yes | DECLINED | INVITED/OPTED_IN/DECLINED/UNAVAILABLE | 낮음 | 행 단위 source_type을 따릅니다. |
| recorded_at | date | yes | 2026-10-02 | 참여 확인일 | 낮음 | 행 단위 source_type을 따릅니다. |
| source_type | source_type | yes | PROVIDER_SELF_REPORTED | 자료의 근거 유형 | 낮음 | 행 단위 source_type을 따릅니다. |
