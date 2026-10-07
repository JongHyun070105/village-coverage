# Submission screenshot plan

아직 발표자료나 제출 이미지를 만들지 않습니다. 아래 화면은 제출자료를 만들 때 사용할 후보입니다. 실제 화면을 새 세션에서 캡처하고 각 이미지에 있는 demo/simulation 표시를 유지합니다.

| # | 화면 | 보여줄 주장 | 캡처 전 확인 |
|---|---|---|---|
| 1 | Dashboard | 요청이 적은 지역과 조사 필요 표시를 함께 검토 | 지역·예산·시뮬레이션 고지, 잘린 카드와 overflow |
| 2 | Area / Demand Evidence | 관측과 근거 부족을 수요 0으로 바꾸지 않음 | 주민 이름·연락처·자유 텍스트 미노출, source/freshness 표시 |
| 3 | Scenario Compare | 네 공급안의 서로 다른 비용·범위 trade-off | 동일 조건, budget·solver status, simulated supply 표기 |
| 4 | Zero-service comparison | 통제 시뮬레이션에서 계획별 서비스 미배정 지역 변화 | artifact provenance `SIMULATION`; 실제 농촌 효과 문장 금지 |
| 5 | Provider fallback / replan | decline 입력 뒤 새 plan version 생성 | 실제 공급자 응답이 아닌 demo/synthetic flow 표기 |
| 6 | Decision Memo / Approval | 근거·미충족·비용을 사람이 검토 | role selector가 인증/법적 승인 아님을 표시 |
| 7 | Data Quality / Evidence Center | 공개자료·local input·추정·가정·simulation·unknown 구분 | source date, cache provenance, 수치와 artifact 일치 |

공모전 캡처에서는 `.env`, API key, browser storage/auth, 주민 연락처, 개인정보, 개인별 공급자 연락처를 노출하지 않습니다. 자동 E2E 스크린샷은 대화형 화면 캡처의 대체물이 아닙니다.
