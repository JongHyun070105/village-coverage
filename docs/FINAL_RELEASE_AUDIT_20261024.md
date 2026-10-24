# VillageCoverage 최종 릴리스 감사 2026-10-24

**공개 릴리스 NO-GO / RELEASE_BLOCKED.** RC의 보안·로컬 검증과 Render 운영 검증을 구분한다. 사용자 조건부 GO는 유지되지만 현재 Render 대상 및 rollback 확인 게이트가 충족되지 않았다.

## Git 및 보존

- 원본 checkout: quality/public-demo-stability-study, ce3bc40a1815b59f507a7b9cf2a95d32e1567d02. 기존 수정 28개 파일 해시 보존, 미추적 파일/SQLite 미삭제, 기존 worktree/태그 유지.
- 격리 worktree: primary repo 안 `.release-final-20261024`; 브랜치 security/final-release-20261024. 원본 checkout은 바꾸지 않았다.
- 기준 44a524adfb2d827316042595b50656a38d8b72e3에서 생성하고 official package 69c2f0a8f0b84333289cb057115a50db40f981dd를 no-ff merge했다. Merge commit bd46bb38331f7e4ecfea88972a2b1d2f951319bd, 충돌 0.
- PR #1 b6ff52a, PR #2 44a524a, 제출 패키지 69c2f0a, 기존 main 4f2089e, 배포 브랜치 7b69649가 모두 RC의 조상이다. 원본 커밋 손실/중복 cherry-pick 없음.
- PR #1/#2는 Open Draft 상태를 보존했다. main=4f2089e9da83308c011fc9cafb306f18baeca8f6와 deploy=7b696499c6c4b59fd613866faa89c1afe8934398를 갱신하지 않았다.
- 제출 바이너리 15개는 원본 package와 바이트 일치. 공식 양식, AI 문서, Render 사건 기록, 실험 artifact와 데이터/템플릿을 보존했다. 제출 상태 Markdown 4개와 manifest만 현재 판정을 추가했다.

## 소스 수정과 검증

실행 소스 SHA: `1150aa3c285dda521ce0b2e2ec3aeb8b760ccf21`. frontend 의존성 보안 패치와 Next 생성 AGENTS 헤더 갱신 외 UI 기능을 추가하지 않았다. Next 16.4.3, eslint-config-next 16.4.3, React/DOM 19.2.9, sharp 0.35.5/librsvg 2.63.2. 개발 Zod는 4.6.7. full/production audit 모두 0. 두 vendored RSC 서버 production 파일은 공식 보안 패치와 SHA-256 일치. 상세는 `NEXTJS_16_4_3_SECURITY_PATCH.md`.

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
| Source CI | run 40071531585, SHA 1150aa3c285dda521ce0b2e2ec3aeb8b760ccf21, conclusion success | EXEC PASS |
| Current Render runtime / latest remote 16-step journey | 미실행/미검증 | SKIP / NOT_VERIFIABLE |

source commit 뒤 audit-only commit이 있으면 해당 최신 HEAD의 CI를 별도로 확인해야 한다. 로컬 결과를 최신 SHA의 원격 CI로 재사용하지 않는다. 최종 사용자 보고에는 실제 최종 RC HEAD와 그 exact-SHA CI run을 기록한다.

## 교차 제공자 검토

orch-parallel 2개 대상 gemini-high/agy-sonnet과 orch-collect를 사용했다. 두 결과는 nested MAIN worktree 변경 감지로 기계 검증 FAILED/BLOCKED였다. 원본 HEAD와 28개 사용자 수정 파일은 별도로 검증했다. 이를 검토 PASS/합의로 표시하지 않았다. 보안 버전·조상 관계·retry·CI·rollback 주장은 MAIN이 실제 소스/공식 자료/실행 결과로 대조했다. 잘못된 frontend/src 검색에 근거한 retry 부재 주장과 Free rollback 불가 주장은 기각했다. 추가 bounded solver 진단 worker는 checkout unchanged, PARTIAL이며 실행 환경이 없어 static 의견만 반환했다. 총 delegate 3회, 추가 사용/쿼터 우회 없음.

## Render와 복구

GitHub 마지막 성공 기록은 API/Web 7b696499이며 실제 현재 이미지 SHA로 대체하지 않았다. 현재 Dashboard/인증 도구 부재로 추적 브랜치·Live·logs·env·retained rollback 확인 불가. 단발 Web 200 관측과 API health timeout은 `RENDER_FINAL_DEPLOYMENT_REPORT.md`에 기록했다. 새 배포, main merge, deploy branch 갱신을 실행하지 않았다. 기존 유료 자원·키·결제·DB 변경 없음.

## 최종 게이트

- SECURITY_PASS: 검증한 RC 범위. 기존 공개 런타임 패치 완료 판정 아님.
- FULL_REGRESSION_PASS: 위 pinned source와 exact-SHA CI 근거에 한정.
- NOT_DEPLOYED: 신규 Render 배포와 최신 원격 검증 없음.
- 제출 기술 준비 PARTIAL: 영상·Office·원격 캡처·신청자/IP 확인 미완료.

운영 재개 조건: 기존 Render 세션/도구 연결 → 두 서비스 현재 대상/SHA·무과금 설정·retained rollback 확인 → 최신 RC exact-SHA CI → 안전한 main/deploy branch 통합 → 실제 Live/SHA 확인 → 원격 16단계·격리·PDF/CSV·4개 viewport·캡처 → 제출 상태 갱신. 상세 제출 제한은 `SUBMISSION_FINAL_TECHNICAL_READINESS.md`.
