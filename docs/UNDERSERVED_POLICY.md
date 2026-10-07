# 소외 최소화(Underserved) 정책 모델

이 문서는 V5의 서비스 공백 이력 모델과 `UNDERSERVED_FIRST` 정책을 설명합니다. 모든 결과는
**시뮬레이션**이며 실제 수혜 인원이나 감소율을 뜻하지 않습니다.

## 데이터

`area_service_history` (마이그레이션 18/22): 권역·서비스·월별 제공 회차와 선택적 관측 세부값.

| 필드 | 의미 |
|---|---|
| `month` | `YYYY-MM` |
| `rounds_delivered` | 그 달 제공 회차 (0은 "서비스 없음으로 확인됨") |
| `last_served_date` | 원자료가 실제 일자를 제공할 때만 기록. 월 자료에서 임의로 날짜를 만들지 않음 |
| `unmet_rounds` | 명시된 월별 미충족 회차; 입력되지 않으면 알 수 없음 |
| `demand_rounds` | 명시된 월별 필요 회차; 요청 건수에서 추정하지 않음 |
| `provenance` | `REAL_REPORTED` 또는 `SIMULATED` |

기록이 없는 달은 **미확인**이며 0으로 취급하지 않습니다. 데모용 가상 이력은
`POST /api/regions/{id}/underserved/demo-seed`로만 들어가며 `REAL_REPORTED` 행을 덮어쓰지 않습니다.

## 상태 (`backend/underserved.py: UnderservedPolicy`)

임계값은 모두 설정값이며 솔버 코드에 숫자가 박혀 있지 않습니다.

| 상태 | 정확한 일자가 있으면 경과 일수, 없으면 월 자료 기준 | 기본 가점 |
|---|---|---|
| RECENTLY_SERVED | ≤ 90일; 일자가 없으면 ≤ 2개월 | 0 |
| WAITING | 91–180일; 일자가 없으면 3–5개월 | 1 |
| LONG_UNSERVED | 181–365일; 일자가 없으면 6–11개월 | 3 |
| CHRONICALLY_UNSERVED | > 365일; 일자가 없으면 ≥ 12개월 (확인 창 안에서 서비스 없음 포함) | 5 |
| UNKNOWN | 확인된 달 < 3, 또는 최신 기록이 3개월보다 오래됨 | 0 |

일수 임계값은 `UnderservedPolicy` 설정이며 `/api/underserved/policy`가 제공합니다. 실제
서비스 일자가 입력되지 않으면 `days_since_last_service`와 `last_served_date`는 `null`입니다.
그 경우 상태는 월 단위 이력만으로 계산하고 응답의 `basis`에서 이를 구분합니다.

최근 3/6/12개월 회차 합계는 해당 기간의 모든 달이 기록된 경우에만 숫자로 제공합니다.
`*_known_periods`는 관측된 월 수를 표시합니다. `unmet_rounds`는 12개월 모두 명시된
미충족 값이 있을 때만 합산하며, `historical_coverage_rate`는 12개월의 필요 회차가 전부
명시된 경우에만 제공됩니다. `consecutive_unserved_periods`는 기준월부터 연속된 확인 0회차
월만 셉니다. 빠진 달은 0이 아니라 미확인입니다.

- 확인 창은 12개월입니다. 창 안에 서비스가 없으면 경과 개월은 "확인된 가장 이른 달부터"의 하한값입니다.
- UNKNOWN은 "서비스를 받지 못했다"가 아니라 "알 수 없다"이며 가점이 없습니다.

## 정책

- **UNDERSERVED_FIRST (소외 최소화)**: 사전식 목적 — (1) 배정된 권역의 공백 가점 합 최대, (2) 서비스 권역 수,
  (3) 총 회차, (4) 이동비용·시간 최소. 월 집계 모델과 일정(CP-SAT) 모델, 할당 단계 모두 같은 순서입니다.
- **Balanced v3**: 기존 V4 가중치(합 100)에 `underserved` 항목(4)을 추가했습니다. 이력이 없거나 가점이 0이면
  항목이 비활성이라 V4와 동일한 계획이 나옵니다 (테스트로 고정).
- 예산·용량·경로는 실행 가능성을 제한하는 조건입니다. `minimum_services_per_area`는
  `MINIMUM_GUARANTEE`에서 우선순위로 삼는 권역별 목표 회차이며, 선택한 예산·수요·공급 조건으로
  달성하지 못할 수 있습니다. 별도 필요예산 진단은 모든 적격 권역이 이 목표를 채운다는 조건으로
  계산하며, 불가능하거나 최적성을 증명하지 못하면 금액을 만들지 않습니다. 다른 정책에서 이 목표를
  보장한다고 해석하지 않습니다.

## KPI

- `ZERO_SERVICE_AREA_COUNT`: 수요가 있으나 현재 계획에서 서비스가 배정되지 않은 권역 수.
- `REDUCED_EXCLUSION_COUNT`: 요청 건수 기준선은 배정하지 않았고 해당 정책은 배정한 장기·만성 권역 수.

## 비교 실험 v2

`scripts/run_underserved_experiment.py` → `artifacts/underserved_experiment_v2.json`.
세 지역 × 예산 4개에서 요청 건수 기준선과 4개 정책을 비교합니다. 이력은 `SIMULATED`입니다.

해석 시 유의:
- 소외 최소화는 가점 합을 올리는 대신 총 회차가 줄 수 있습니다(실험에서 효율 우선 대비 최대 약 23% 적음(부여읍, 300만원)).
- 예산이 매우 작으면 어떤 정책도 서비스 미배정 권역을 크게 줄이지 못합니다.
- "N명을 구했다", "50% 감소" 같은 표현은 이 모델이 지지하지 않습니다.
