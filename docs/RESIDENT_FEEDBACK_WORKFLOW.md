# 주민 의견·정정 워크플로 (Resident Feedback)

주민 의견은 **검증 전 주장(claim)** 이며 조사(survey)와 동급이 아니다. 의견은 수요 평가(DemandAssessment),
예측(forecast), 계획(plan)을 자동으로 바꾸지 않는다.

## 흐름

1. 접수 (`POST /api/feedback`, 화면 "주민 의견·정정"): 담당자 대리 입력 또는 간단한 공개 양식. 전체 주민 앱은 범위 밖이다.
2. 담당자 검토: `SUBMITTED -> UNDER_REVIEW -> NEEDS_MORE_INFO | ACCEPTED_AS_EVIDENCE | REJECTED`, 채택 후 `RESOLVED`.
   반려·추가 확인·채택·완료에는 처리 메모가 필수이다. PLANNER/REVIEWER는 시연용 역할이며 실제 인증이 아니다.
3. 채택(`accept`): `resident_claim_evidence`에 `UNVERIFIED_CLAIM`으로만 기록한다. `demand_observations`,
   `demand_evidence`, `surveys`는 변경하지 않는다.
4. 계획 stale 표시: 채택 시 같은 지역의 유효 계획에 `stale_since/stale_reason`을 표시한다. 승인된 계획의 내용은
   트리거(`APPROVED_PLAN_IMMUTABLE`)로 보호되며 stale 표시만 바뀐다.
5. 담당자가 재계획하면 새 계획 버전이 만들어진다.

## 근거 정책 (`backend/evidence_source_policy.py`)

| source | 관측 기여 상한 | 빈도 하한 | 보정(calibration) | 예측 |
| --- | --- | --- | --- | --- |
| SURVEY | 제한 없음 | 가능 | 가능 | 가능 |
| RESIDENT_FEEDBACK | 최대 1건 | 불가 | 불가 | 불가 |

의견이 20건 채택되어도 기여는 1건 상한이며 `calibrated=false`이다. 이후 같은 서비스에 대한 공식 조사가 등록되면
해당 주장은 확인된 것으로 계산되어 기여가 0으로 돌아간다. 의견이 있으면 평가는 `needs_survey=true`가 된다.

## 충돌·중복

- 충돌: 최신 공식 조사와 비교한다. 조사가 `structured_data.demand_status == "NO_DEMAND"`인데 수요를 주장하거나,
  주장 빈도와 조사 빈도 차이가 절대 2회 이상이고 비율 1.5배 이상이면 `EVIDENCE CONFLICT`를 만든다.
  어느 쪽도 덮어쓰지 않는다. 해결 방식: `KEEP_OFFICIAL_EVIDENCE`(의견 반려), `FURTHER_SURVEY`(추가 확인),
  `ACCEPT_AS_RANGE`(채택 허용). 미해결 충돌이 있으면 채택은 `FEEDBACK_CONFLICT`로 거부된다.
- 중복: 같은 내용(정규화 후 해시)의 재접수는 `FEEDBACK_DUPLICATE`로 거부한다. 유사 의견(토큰 유사도 0.6 이상)은
  후보로만 표시하며 자동 병합하지 않는다. 담당자가 `LINKED_DUPLICATE` 또는 `CONFIRMED_DISTINCT`로 판정한다.
- 규제·제외 서비스에 대한 의견은 `REGULATED_SERVICE`로 근거 채택이 거부된다.
- 폭주 방지: 생활권당 24시간 30건, 지역당 200건을 넘으면 `FEEDBACK_RATE_LIMITED`(429)를 반환한다.

## 개인정보

- 설명은 전화번호·식별번호·이메일·호칭 이름 패턴을 마스킹한 뒤 저장한다.
- 연락처는 `resident_feedback_contacts`에 분리 저장하며 목록·내보내기·감사 로그·오류 응답에 포함하지 않는다.
- 감사 이벤트(`FEEDBACK_*`)에는 ID와 상태만 기록하고 원문은 기록하지 않는다.

## 신선도

의견 접수일 기준으로 조사 근거와 같은 정책(FRESH <= 90일, AGING <= 180일, 이후 STALE)을 쓴다.

## 한계

- 실제 인증이 없다. 공개 양식의 남용 방지는 단순 건수 제한뿐이다.
- 중복 판정은 단순 토큰 유사도이며 의미 유사도가 아니다.
- 주민 의견에서 수요량을 추정하지 않는다. 오직 "조사가 필요하다"는 신호만 만든다.
