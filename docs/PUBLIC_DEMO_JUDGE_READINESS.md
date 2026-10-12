# Public Demo Judge Readiness

확인 시각: 2026-10-12 17:00 KST · 기준 SHA: d93bc31aace96428e38f6f7b1818f40ce36a7e0a

## 상태

| 상태 | 값 | 근거 |
|---|---|---|
| URL_EXISTS | PASS | web https://villagecoverage-public-demo-web.onrender.com, API https://villagecoverage-public-demo-api.onrender.com |
| PREVIOUSLY_DEPLOYED | PASS | GitHub deployment records: web/API 성공 |
| CURRENT_HTTPS_VERIFIED | PASS (HTTP endpoints only) | web / 200/22.685s, API /api/health 200/52.644s, TLS 검증 통과 |
| DEPLOYED_SHA_VERIFIED | PASS | 두 deployment 모두 7b696499c6c4b59fd613866faa89c1afe8934398 |
| CURRENT_BROWSER_FLOW_VERIFIED | NOT_VERIFIABLE | 현재 공개 origin에서 end-to-end 브라우저 흐름을 실행하지 않음 |
| READY_FOR_SUBMISSION | NO | 원격 브라우저 흐름, 최종 신청물/서명, 영상 및 Q&A 본문 대조 미완료 |
| 신규 배포 | NOT_DEPLOYED | 이번 작업에서 Render를 변경하지 않음 |

## 심사자 첫 방문

- Render Free 서비스는 15분 유휴 뒤 sleep하고 첫 wake-up은 약 1분까지 걸릴 수 있다. 52.644초 API health 응답은 한 번의 관측값이며 보장 시간이나 cold-start 증거로 단정하지 않는다.
- web 200 이후 API가 준비 중일 수 있다. 공개 데모 API 실패 UI에는 503/network 안내와 명시적 수동 재시도 버튼이 있다. 최초 로딩에는 약 1분 대기가 가능하다는 안내를 추가했다.
- 세션은 브라우저별로 분리되고 30분 idle expiry가 적용된다. /tmp SQLite 계획은 Render restart/redeploy/spin-down 뒤 보존되지 않을 수 있다고 배너에 표시한다. plan id 공유 링크를 영구 저장 수단으로 설명하지 않는다.
- API는 same-origin rewrite로 고정 backend origin에 연결된다. 신청 자료에는 별도 API URL 대신 web URL을 테스트 진입점으로 제시한다.

## 권장 심사 순서

1. Dashboard에서 공개 데이터와 합성 수요/공급 전제를 읽는다.
2. 네 정책 비교와 소외 지역 배려 근거를 본다.
3. 공급자 데모 불참을 입력하고 계획을 재계산한다.
4. 계획 상세와 Decision Memo를 확인한다.
5. 재시작/세션 만료 시 계획은 초기화될 수 있음을 읽는다.

심사자가 확인해야 하는 구분: AI는 비정형 수요 근거를 검토 가능한 초안으로 구조화하는 보조 단계, 규칙은 충분도/권한/출처 검증, OR-Tools는 제약 기반 계획, 통계는 표본 기반 추정, demo 수치는 합성 시뮬레이션, 최종 정책 선택/승인은 사람의 역할이다. 현장 정확도·비용 절감률·주민 성과는 실증되지 않았다.

## Verification limits

저빈도 GET 외에 계획 생성, 불참, 재계획, export, session cookie, 원격 browser UI, cold-start failure, 503/429 scenario는 이 공개 서비스에서 실행하지 않았다. 해당 흐름은 격리된 local Playwright/pytest를 통해서만 검증한다. 이번 실행은 public load/security test를 하지 않았다.

## Sources

- [Render Free service limits](https://render.com/docs/free)
- [Frontend security and release audit](FRONTEND_SECURITY_AUDIT.md)
- [Submission checklist](../submission/SUBMISSION_CHECKLIST.md)
