# 데모 화면·제출 캡처 촬영 목록

## 대표 이미지

**1순위:** Scenario Compare + coverage map을 한 화면에 담은 재캡처. 예산과 `SIMULATED` 표시, 네 정책의 서비스량·비용·미배정 권역이 잘 읽히는지 확인한다. 현재 회귀 캡처 `artifacts/v5_2_rc1_visual_qa/scenario-comparison.png`는 1366×3671 픽셀 전체 페이지라 제출용으로는 글자가 작다. 이 캡처를 그대로 대표 이미지로 쓰지 말고, 약 1440×900 창 크기의 집중 화면으로 새로 캡처한다. **2순위:** Dashboard의 `dashboard.png`를 새 브라우저 세션에서 같은 기준으로 캡처한다.

## 8장 이내 후보

| # | 화면·회귀 참고 | 한 문장 캡션 | 심사자가 봐야 할 것 | 캡처 조건 |
|---|---|---|---|---|
| 1 | Dashboard — `dashboard.png` | “계획 현황과 함께 조사 필요·서비스 공백을 먼저 드러낸다.” | 서비스 요청과 근거 부족을 같은 지표로 취급하지 않음 | 전체 브라우저 UI 최소화, DEMO 표시, 오버플로 없음 |
| 2 | Area Detail / Demand Evidence — `village-and-survey-form.png` 또는 `resident-feedback-reviewed.png` | “관측이 부족한 권역은 0수요가 아니라 추가 조사 대상으로 남는다.” | 근거 수준·출처·조사 필요 표시 | 주민 실명·연락처·자유 텍스트 미포함 |
| 3 | Data Sources / Evidence Center — `data-sources.png` | “공개자료, 외부 참고자료, 합성 운영값을 출처별로 분리한다.” | REAL PUBLIC / EXTERNAL PRIOR / SIMULATED 구분 | 기준일과 품질 표시, API key 없음 |
| 4 | Scenario Compare + map — `scenario-comparison.png` | “같은 조건에서도 정책 우선순위에 따라 서비스 공백과 비용이 달라진다.” | 정책 설명, 예산, coverage, zero-service, solver 상태 | 새 창 크기로 재캡처, 해당 비교가 같은 입력인지 확인 |
| 5 | Schedule / budget — `schedule.png` | “예산·일정·공급 조건을 확인하고, 불가능한 조건도 결과에 남긴다.” | 설정값·solver 상태·비용 추정 라벨 | 해당 schedule이 시뮬레이션인지 표시 |
| 6 | Provider Participation — `provider-participation.png` | “제공 거절 입력 뒤 기존안을 고정하지 않고 재계획을 만든다.” | 거절이 입력 변화이며 운영 약속이 아님 | 이름·전화번호 대신 데모 제공자만 표시 |
| 7 | Replan / Version — `plan-replanned.png` | “변경 전후 계획과 남은 공백을 버전으로 비교한다.” | 비용·권역·미충족·재계획 근거 | DEMO 배지·같은 조건 확인 |
| 8 | Decision Memo / Evidence Center — `plan-approved-and-versioned.png` 및 `data-sources.png` | “비용과 근거, 미배정 사유를 행정 검토 메모로 잇는다.” | 메모는 초안, role selector는 인증/법적 결재가 아님 | 실제 개인 이름·연락처 없음, 승인 고지 포함 |

## 캡처 품질 기준

- 권장 작업 창은 1440×900 전후다. 이는 제작 권고이며 공식 영상·캡처 규격은 `NOT_SPECIFIED`.
- Chrome 탭·주소창 등 불필요 UI를 줄이되, 편집으로 데모·합성 고지를 지우지 않는다.
- 텍스트 잘림, 툴팁 가림, 오류 토스트, 빈 차트, 맵 타일 누락, 개인 정보, API 키가 없도록 새 브라우저 세션에서 확인한다.
- `SIMULATED`, `DEMO DATA`, `UNKNOWN`, `FIELD VALIDATION NOT STARTED`를 해당 주장 가까이에 남긴다.
- 기존 캡처는 1366px 너비의 긴 회귀 증거다. 제출 이미지는 새로 촬영한다. 현재 확인한 시각자료는 synthetic/demo 데이터이며 실제 효과 증거가 아니다.

통제 실험의 숫자 비교는 보고서 그림 후보로 따로 설계할 수 있다. 제품 화면 screenshot과 혼동하지 말고 `artifacts/experiment_results.json`의 두 정책, 500만원, 19개 단위 조건을 유지해 `SIMULATED`로 표시한다. 실제 화면이 그 실험 결과를 재현하지 않으면 영상에서는 해당 숫자를 말하지 않는다.
