# VillageCoverage 최종 릴리스 감사 2026-10-24

**공개 릴리스 NO-GO / RELEASE_BLOCKED.** RC의 보안·로컬 검증과 Render 운영 검증을 구분한다. 사용자 조건부 GO는 유지되지만 현재 Render 대상 및 rollback 확인 게이트가 충족되지 않았다.

## Git 및 보존

- 원본 checkout: quality/public-demo-stability-study, ce3bc40a1815b59f507a7b9cf2a95d32e1567d02. 기존 수정 28개 파일 해시 보존, 미추적 파일/SQLite 미삭제, 원본 실제 checkout과 태그 유지. 처음부터 경로가 없던 stale worktree 등록 8개는 orch worker 정리의 git worktree prune에서 제거됐다. 실제 작업 파일 삭제는 관측되지 않았고 원본 branch ref/SHA는 모두 동일함을 확인했다. 등록까지 보존됐다는 초기 표현을 정정한다.
- 격리 worktree: primary repo 안 `.release-final-20261024`; 브랜치 security/final-release-20261024. 원본 checkout은 바꾸지 않았다.
- 기준 44a524adfb2d827316042595b50656a38d8b72e3에서 생성하고 official package 69c2f0a8f0b84333289cb057115a50db40f981dd를 no-ff merge했다. Merge commit bd46bb38331f7e4ecfea88972a2b1d2f951319bd, 충돌 0.
- PR #1 b6ff52a, PR #2 44a524a, 제출 패키지 69c2f0a, 기존 main 4f2089e, 배포 브랜치 7b69649가 모두 RC의 조상이다. 원본 커밋 손실/중복 cherry-pick 없음.
- PR #1/#2는 Open Draft 상태를 보존했다. main=4f2089e9da83308c011fc9cafb306f18baeca8f6와 deploy=7b696499c6c4b59fd613866faa89c1afe8934398를 갱신하지 않았다.
- 제출 바이너리 15개는 원본 package와 바이트 일치. 공식 양식, AI 문서, Render 사건 기록, 실험 artifact와 데이터/템플릿을 보존했다. 제출 상태 Markdown 4개와 manifest만 현재 판정을 추가했다.

## 소스 수정과 검증

실행 소스 SHA: `9a8c4bed60bca57cce2941a028945b2f002c6f01`. frontend 의존성 보안 패치와 Next 생성 AGENTS 헤더 갱신 외 UI 기능을 추가하지 않았다. Next 16.4.3, eslint-config-next 16.4.3, React/DOM 19.2.9, sharp 0.35.5/librsvg 2.63.2. 개발 Zod는 4.6.7. full/production audit 모두 0. 두 vendored RSC 서버 production 파일은 공식 보안 패치와 SHA-256 일치. 추가 Python 운영 감사에서 certifi/OpenTelemetry/Pillow 3종 39개 권고를 발견해 certifi 2026.10.23, opentelemetry-api 1.45.1, Pillow 13.0.0으로 보안 갱신했다. ReportLab 4.5.1은 유지했고 선언된 Pillow>=9 조건에 호환된다. 운영 46개 패키지 pip-audit 재검사는 알려진 권고 0건이다. CI에 동일한 잠금 운영 의존성 감사 단계를 추가했다. Pillow major 갱신은 37개 보안 권고의 고정 버전이기 때문에 적용한 관련 보안 수정이다. 상세는 `NEXTJS_16_4_3_SECURITY_PATCH.md`.

첫 backend full: **FAIL 586 passed / 1 failed / 1 skipped (387.47s)**. 날짜 의존 wide sparse hub test에서 UNKNOWN을 반환했고 단독 재현도 실패했다. 날짜를 2026-10-13/2026-06-01로 바꾼 진단은 OPTIMAL, 2026-10-24는 탐색 전 symmetry presolve 종료였다. 동일 모델·원래 3초 제한에서 symmetry_level=0은 OPTIMAL을 반환했다.

수정은 joint strategy이면서 route matrix가 incomplete인 경우에만 symmetry search optimization을 끈다. feasibility constraint·score·worker·시간 제한·상태 판정은 유지했다. 날짜 3개를 strict assertion과 예산 상한으로 검증해 scheduling 36개 통과, 그 뒤 전체 회귀를 다시 수행했다. 기존 실패 로그는 보존했다. Worker의 날짜 고정/분해 경로 추측은 그대로 채택하지 않았고 직접 실행 증거로 범위를 정했다.

| 검증 | 실제 결과 | 증거 수준 |
|---|---|---|
| Backend full 최종 | 589 passed / 1 skipped | EXEC PASS |
| Ruff / compileall | PASS | EXEC PASS |
| R1–R13 | 112 passed | EXEC PASS |
| npm ci / lint / typecheck / Node 22 standalone build | PASS | EXEC PASS |
| Standard E2E | 12 passed / 1 skipped (remote opt-in) | EXEC PASS / SKIP |
| Public Demo E2E | 6 passed | EXEC PASS |
| Responsive | 2 passed, 390/768/1280/1440px | EXEC PASS |
| A/B/C plans·provider declines·approvals / exports | 로컬 격리 검증 | EXEC PASS |
| Cookie·30분 expiry·256 cap·Health 제외·allowlist·rate/solver gates | backend regression 유지/통과 | EXEC PASS / STATIC Secure Render flag |
| GET retry / POST no replay / HTML proxy errors | Public Demo browser tests 통과 | EXEC PASS |
| Production Python audit | 46 packages / 0 known advisories; 39 before | EXEC PASS |
| Source CI | run 40073124556, SHA 9a8c4bed60bca57cce2941a028945b2f002c6f01, conclusion success | EXEC PASS |
| Current Render runtime / latest remote 16-step journey | 미실행/미검증 | SKIP / NOT_VERIFIABLE |

source commit 뒤 audit-only commit이 있으면 해당 최신 HEAD의 CI를 별도로 확인해야 한다. 로컬 결과를 최신 SHA의 원격 CI로 재사용하지 않는다. 최종 사용자 보고에는 실제 최종 RC HEAD와 그 exact-SHA CI run을 기록한다.

## 교차 제공자 검토

orch-parallel 2개 대상 gemini-high/agy-sonnet과 orch-collect를 사용했다. 두 결과는 checkout 변경 감지로 기계 검증 FAILED/BLOCKED였다. 해당 기간 MAIN의 격리 작업이 진행됐고 helper가 stale 등록도 prune했으므로 기계 검증 성공으로 대체하지 않았다. 원본 HEAD와 28개 사용자 수정 파일은 별도로 검증했다. 이를 검토 PASS/합의로 표시하지 않았다. 보안 버전·조상 관계·retry·CI·rollback 주장은 MAIN이 실제 소스/공식 자료/실행 결과로 대조했다. 잘못된 frontend/src 검색에 근거한 retry 부재 주장과 Free rollback 불가 주장은 기각했다. 추가 bounded solver 진단 worker는 checkout unchanged, PARTIAL이며 실행 환경이 없어 static 의견만 반환했다. 총 delegate 3회, 추가 사용/쿼터 우회 없음.

## Render와 복구

GitHub 마지막 성공 기록은 API/Web 7b696499이며 실제 현재 이미지 SHA로 대체하지 않았다. 현재 Dashboard/인증 도구 부재로 추적 브랜치·Live·logs·env·retained rollback 확인 불가. 단발 Web 200 관측과 API health timeout은 `RENDER_FINAL_DEPLOYMENT_REPORT.md`에 기록했다. 새 배포, main merge, deploy branch 갱신을 실행하지 않았다. 기존 유료 자원·키·결제·DB 변경 없음.

## 최종 게이트

- SECURITY_PASS: 검증한 RC 범위. 기존 공개 런타임 패치 완료 판정 아님.
- FULL_REGRESSION_PASS: 위 pinned source와 exact-SHA CI 근거에 한정.
- NOT_DEPLOYED: 신규 Render 배포와 최신 원격 검증 없음.
- 제출 기술 준비 PARTIAL: 영상·Office·원격 캡처·신청자/IP 확인 미완료.

운영 재개 조건: 기존 Render 세션/도구 연결 → 두 서비스 현재 대상/SHA·무과금 설정·retained rollback 확인 → 최신 RC exact-SHA CI → 안전한 main/deploy branch 통합 → 실제 Live/SHA 확인 → 원격 16단계·격리·PDF/CSV·4개 viewport·캡처 → 제출 상태 갱신. 상세 제출 제한은 `SUBMISSION_FINAL_TECHNICAL_READINESS.md`.

## 20시 재개 검증 및 현재 증거 우선순위

- 실행 소스 `9a8c4bed60bca57cce2941a028945b2f002c6f01`와 exact-SHA CI [40073124556](https://github.com/JongHyun070105/village-coverage/actions/runs/40073124556)의 head가 일치한다. Backend 589 passed / 1 skipped, R1–R13 112, Standard 12 / 1 skipped, Public Demo 6, Responsive 2, Python audit·npm production audit·lint·typecheck·Node 22 build가 모두 성공했다. CI Node는 22.23.3, 로컬 standalone 검증 Node는 22.18.0이다.
- 기존 중단 시점의 미커밋 Python 보안 갱신 증거를 수집했다. 이번 작업에서 실행 코드·lockfile·CI 정책을 추가 변경하지 않았다. 감사 증거 commit 이후에도 최신 RC HEAD의 CI를 별도로 확인한다. 이 문서의 source SHA는 실행 코드 동결점을 가리키며, 후속 문서 commit SHA를 가장한 값이 아니다.
- 새 batch `parallel-261024-202931-d6c18f`는 gemini-medium/agy-sonnet 두 제공자의 read-only 검토이며 orch-collect 기계 수집 COMPLETE, 두 worker 모두 main_checkout_unchanged=true다. STATIC 의견에서 새로운 운영 코드 결함은 보고되지 않았다. MAIN은 stale SHA/CI와 Python lock 설명의 갱신 필요성을 직접 확인해 반영했다. not continue-on-error는 의도된 차단 게이트이고 결함으로 채택하지 않았다. 새 검토는 이전 guard 실패 batch를 PASS로 바꾸지 않으며 의미적 합의나 독립 실행 테스트라고 주장하지 않는다.
- 20:30–20:32 KST 단발 baseline 재확인에서 API /health·/api/health, Web /·/api/regions·/api/schedules가 모두 200이었다. JSON 4개 정상, Health 쿠키 미발급, 조회 API 세션 속성 HttpOnly/Secure/Lax/Path=/api/1800초 확인. 초기 응답 지연 약 42.5–42.9초와 마지막 schedules 0.487초를 관측했으나 cold-start 원인을 입증한 것은 아니다. 후보의 배포 SHA 검증으로 대체하지 않는다.
- 현재 도구 재확인에서도 native app-server 오류·브라우저 목록 없음·iab 사용 불가였다. Render 연결 도구·CLI 인증·Office 앱을 찾지 못했다. 새 키 생성, 계정 설정 변경, 유료 자원 생성, 배포 우회는 하지 않았다. btc-orchestrator 스킬은 검색한 로컬 스킬 경로에서 찾지 못해 적용하지 못했다.
- 이전 FRONTEND_SECURITY_AUDIT/PRE_RELEASE_SECURITY_GAP_AUDIT/TECH_DEBT/VERIFIED_METRICS의 날짜가 있는 감사 기록은 당시 관측이며 현재 잠금 파일의 보안 판정이 아니다. 원본 이력은 보존하고 현재 판정은 본 문서와 NEXTJS_16_4_3_SECURITY_PATCH 및 새 JSON을 우선한다.

현재 결론은 **SECURITY_PASS + FULL_REGRESSION_PASS(동결 실행 소스) + NOT_DEPLOYED + 제출 PARTIAL**이다. Render 대상/현재 SHA/retained rollback을 확인하기 전에는 main과 deploy branch를 갱신하지 않는다. 추적 브랜치가 불명확하므로 main 변경 자체가 뜻하지 않은 자동배포를 유발할 가능성도 배제하지 못했다.
