# 제출 초안 red-team / 일관성 검토

검토 기준: 2026-10-07의 `main` 기반 branch와 저장소 내 최신 문서·artifact. 이번 문서 수정 뒤 application test suite는 실행하지 않았다. 초안의 수치와 출처는 기록된 evidence에 대조했다.

## 공격 질문과 조치

| 공격 질문 | 발견 | 문서 조치 |
|---|---|---|
| 실제 농촌에서 효과가 났다고 썼나? | 실제 field validation이 없다. | 보고서·요약·영상에서 모든 효과를 목표/가능성으로 표현하고, 500만원 비교에는 `SIMULATED`를 반복 표기. |
| AI가 공급계획을 직접 결정하나? | AI 기록 구조화와 CP-SAT allocation이 분리돼 있다. | AI는 검토용 초안·근거 부족 보류, 최적화는 예산·공급량·거리·일정 계산이라고 나눴다. |
| 요청 없는 마을에 AI가 필요를 만들어 주나? | 실험의 수요·관측은 합성값이고 실제 예측 정확도는 미검증. | 데이터가 없으면 `조사 필요`; 추정 억제 원칙을 넣고 사람 검토를 요구했다. |
| 13→4가 동일 실험 수치인가? | 요청 기준안과 균형안은 `experiment_1_request_count_vs_balanced`에서 같은 16개 권역·예산·19개 단위 조건으로 비교된다. 다른 artifact로 네 정책의 동일 실험을 만들면 안 된다. | 보고서·영상·claim map 모두 두 정책만으로 좁혔다. |
| 가격·거리·수혜자 수가 실제 값인가? | 운영 가격·용량·수요 합성. 거리 자료는 실제 공공/캐시 자료지만 모델 비용은 거점 왕복 가정이다. | 현실 공급·효과로 해석하지 않게 표시하고 네 정책 모두 정책 선택이라고 설명했다. |
| 최소보장이 모든 요청을 채우나? | 설정된 최소 기회에 대한 우선순위며 불가능할 때 미배정이 남는다. | 100% 보장이 아니라는 설명을 보고서·영상·FAQ·tester guide에 반영했다. |
| 제공자 거절은 실제 업체 응답인가? | 시연 입력이고 simulation. | “데모 제공자”, “시뮬레이션”, “실제 업체 통보 아님”으로 표현했다. |
| 승인 버튼이 행정 승인인가? | role selector는 인증/인가가 아니다. | 데모 검토 메모로만 설명했다. |
| 기술 테스트가 제품 효과를 증명하나? | 테스트는 코드·시나리오 통과 기록이며 field outcome이 아니다. | 테스트 숫자를 보조 신뢰 근거로 둔다. 측정된 효과와 분리했다. |
| 기술이 지나치게 복잡한가? | DB·endpoint·class보다 evidence → AI → optimization → scenario → human review 흐름으로 요약했다. | 보고서에 5개 핵심 축만 남기고 세부 framework 나열을 피했다. |
| 최종 발표물에서 데이터가 섞일 수 있나? | 실제 공개 자료, 공식 디렉터리, 외부 prior, synthetic fixture는 성격이 다르다. | Claim map에 분류·허용 문구·조건을 넣었다. |
| 테스트 URL을 안전하게 낼 수 있나? | 공개 연락처 조회와 무인증 쓰기 API가 있어 현 상태로는 불가. | URL을 제출 blocker로 공개하고 배포/기능 사용을 권하지 않는다. |

## 기술 수치 대조

- 공식 통제 실험 artifact의 `experiment_scope`는 합성 수요·관측·공급·가격을 명시한다.
- 500만원, 요청 기준안 19단위/3권역/13 미배정, 균형안 19단위/12권역/4 미배정, 조사 필요 배정 0/8 대 7/8 숫자를 `artifacts/experiment_results.json`에서 확인했다.
- backend 562 passed/1 skipped, Playwright 12 passed, R1–R13 112 passed 수치는 `docs/VERIFIED_METRICS.md`가 지정한 코드 소스 SHA `fe2c10486b5f05559619e0cdbdb6b71ac1deb7e3`의 기록이다. 현재 제출 준비 HEAD에서 다시 실행했다고 쓰지 않는다.
- 공식 후보작 목록에는 `VillageCoverage` 이름이 있지만 아이디어 번호는 표시되지 않았다. 5점 가점과 공동 IP 적용은 신청자와 제안자 확인이 남았다.

## AI 문장·공식 Q&A 정합성

- 반복 문구(“다만”, “이를 통해”, “~하는 것이 중요합니다”, “~방향입니다”)를 줄이고 개발 판단과 구체적인 한계를 사용했다.
- 제출된 실제 Q&A 답변 원문은 저장소에서 발견하지 못했다. FAQ는 사용자가 이번 요청에서 준 기준과 제품 문서에 맞춰 작성했으나, 원 제출 답변 및 10월 12일 이후 공개 답변과의 최종 대조는 신청자가 해야 한다.
- 공식 보고서 초안은 필수 7항목만 두고 항목 순서를 유지했다. 텍스트 양을 공식 2쪽/HWP 및 4쪽/PPT 템플릿에 맞춰 옮기고 페이지 수를 확인해야 한다.

## 공개 저장소 검토 메모

- GitHub 저장소는 public이고 기본 브랜치는 `main`이다. GitHub API는 repository size 6,014 KiB, 현재 공개 metadata상 license 없음으로 응답했다.
- license를 추가하지 않았다. 아이디어 기반 결과의 50:50 IP 원칙과 권리자 확인이 남아 있다.
- 이번 branch의 tracked text와 제출 문서를 high-confidence key pattern으로 검사한 결과 매치 없음, `.env` 미추적·ignored를 확인했다. 전용 `gitleaks`/`trufflehog` 명령은 이 환경에 없다. `docs/VERIFIED_METRICS.md`의 전체-history secret scan은 과거 RC 기록이므로 이번 commit 전체 검사와 혼동하지 않는다. 최종 공개 전 조직 표준 scanner로 재검사한다.
- 공개 README의 로컬 Markdown 링크를 확인했고 깨진 로컬 링크는 없었다. tracked repository는 362개 파일, 원격 GitHub의 현재 main 저장소 크기는 6,014 KiB였다. 새 공식 양식 ZIP 사본은 약 3.26 MB이며 100 MB를 넘는 단일 파일은 없다.
- 테스트 이미지는 1366px 너비의 긴 전체 페이지 캡처가 많다. 발표 대표 화면에는 새로 집중 캡처를 한다. 현재 이미지는 민감 항목을 노출하지 않는 synthetic QA evidence로 표시되어 있다.

## Independent review 상태

`orch-parallel`의 Sonnet 작업은 rate limit으로 유효 결과를 내지 못했고, Gemini 결과도 orchestrator가 checkout guard 사유로 `FAILED` 처리했다(기계 기록상 시작/종료 SHA는 같고 변경 파일은 없음). 따라서 독립 2-provider semantic consensus는 없다. 공식 요건은 확보된 공고·첨부 양식과 KEIT 공지에서 직접 대조했으며, worker 주장은 단독 근거로 채택하지 않았다.
