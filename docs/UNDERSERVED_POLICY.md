# 소외 최소화(Underserved) 정책 모델

이 문서는 V5의 서비스 공백 이력 모델과 `UNDERSERVED_FIRST` 정책을 설명합니다. 모든 결과는
**시뮬레이션**이며 실제 수혜 인원이나 감소율을 뜻하지 않습니다.

## 데이터

`area_service_history` (마이그레이션 18): 권역·서비스·월별 제공 회차.

| 필드 | 의미 |
|---|---|
| `month` | `YYYY-MM` |
| `rounds_delivered` | 그 달 제공 회차 (0은 "서비스 없음으로 확인됨") |
| `provenance` | `REAL_REPORTED` 또는 `SIMULATED` |

기록이 없는 달은 **미확인**이며 0으로 취급하지 않습니다. 데모용 가상 이력은
`POST /api/regions/{id}/underserved/demo-seed`로만 들어가며 `REAL_REPORTED` 행을 덮어쓰지 않습니다.

## 상태 (`backend/underserved.py: UnderservedPolicy`)

임계값은 모두 설정값이며 솔버 코드에 숫자가 박혀 있지 않습니다.

| 상태 | 기준 (마지막 서비스 후 경과 개월) | 기본 가점 |
|---|---|---|
| RECENTLY_SERVED | ≤ 2 | 0 |
| WAITING | 3–5 | 1 |
| LONG_UNSERVED | 6–11 | 3 |
| CHRONICALLY_UNSERVED | ≥ 12 (확인 창 안에서 서비스 없음 포함) | 5 |
| UNKNOWN | 확인된 달 < 3, 또는 최신 기록이 3개월보다 오래됨 | 0 |

- 확인 창은 12개월입니다. 창 안에 서비스가 없으면 경과 개월은 "확인된 가장 이른 달부터"의 하한값입니다.
- UNKNOWN은 "서비스를 받지 못했다"가 아니라 "알 수 없다"이며 가점이 없습니다.

## 정책

- **UNDERSERVED_FIRST (소외 최소화)**: 사전식 목적 — (1) 배정된 권역의 공백 가점 합 최대, (2) 서비스 권역 수,
  (3) 총 회차, (4) 이동비용·시간 최소. 월 집계 모델과 일정(CP-SAT) 모델, 할당 단계 모두 같은 순서입니다.
- **Balanced v3**: 기존 V4 가중치(합 100)에 `underserved` 항목(4)을 추가했습니다. 이력이 없거나 가점이 0이면
  항목이 비활성이라 V4와 동일한 계획이 나옵니다 (테스트로 고정).
- 예산·용량·최소 회차·경로 제약은 어떤 정책에서도 완화되지 않습니다.

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
