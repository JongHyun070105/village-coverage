# Technical debt and validation gaps

이 목록은 제품 readiness 결과와 구분한 후속 작업입니다. 데이터나 권한이 없는 항목을 `PASS`로 추정하지 않습니다.

| 항목 | 현재 상태 | 다음 검증 |
|---|---|---|
| Solver `TIME_LIMIT` / `UNKNOWN` | 큰 입력·제한시간 조건에서 남음. 성공·최적성으로 세지 않음. | 입력 크기별 현재 baseline smoke를 유지하고, 제한시간을 성능 통과용으로 늘리지 않음. |
| 실제 local demand 및 forecast calibration | 현장 시계열 없음. | 승인된 기관·주민 자료와 사전 정의된 표본·누수 방지·오차 기준 필요. |
| Provider operation validation | 공식 directory 존재와 실제 availability/capacity/price가 분리됨. | 공급자/기관 담당자가 서비스·날짜·수용량·가격·참여를 확인하고 freshness를 남김. |
| 공식 region registry cross-check | 10자리 코드 형식은 확인하지만 모든 pilot 멤버십은 기관 원장과 재대조해야 함. | 실제 파일럿 권역의 기준일·법정코드 원장을 authority가 확인. |
| Live API smoke | Offline/mock failure contract와 분리되어 있으며 RC regression에서는 opt-in live call을 수행하지 않음. | key 사용과 네트워크 비용을 담당자가 승인한 환경에서 별도 실행. |
| Route cache availability and reuse | 실험·데모 계산에 완전한 local Kakao matrix가 필요. route cache는 Git에 포함되지 않음. | 시연 환경에 승인된 cache를 준비하고 현재 provider terms와 공개 배포 조건을 검토. |
| Manual accessibility | 자동 focus/keyboard/responsive 회귀만 확인. | 화면 reader 사용자 및 실제 authority 사용자와 검증. |
| Identity, authorization, retention | prototype role selector만 있음. 인증·인가·전자서명·기관 보존 정책 없음. public internet/shared network에 공개하지 말 것. | 별도 보안 설계와 기관 승인 필요. |
| PII masking scope | 전화·주민번호·email·일부 호칭 이름 pattern을 다루는 best-effort 보호. | 실제 schema에 맞춘 개인정보 영향·필드·오류·export 점검. 완전 익명화로 표현 금지. |
| Provider directory counts | 마을기업 원본에는 source row count와 catalog metadata 사이 1행 차이가 audit에 기록됨. | 제출에서 행 수를 사용할 경우 원본 metadata와 parser counting rule을 함께 설명. |
| Frontend dependency advisories | 2026-10-07 clean-lock audit: production dependency audit passes after `source-map-js` moves from 1.2.1 to 1.2.2. The full tree still reports five high advisories in the development-only Next ESLint chain (`eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → `braces` 3.0.3). The registry exposes no patched `braces` release; npm's suggested fix downgrades `eslint-config-next` to 14.2.35 and is a breaking major change. | Keep the compatible Next 16 toolchain; recheck on the next safe patch release. Do not apply a forced downgrade in this RC. |
| Python dependency advisories | `pip-audit` against the clean frozen Python environment found no known vulnerabilities on 2026-10-07. | Re-run against the locked environment before a later release; this is advisory database coverage at scan time, not a security guarantee. |

세부 readiness 판정은 [V5_2_FIELD_PILOT_READINESS_AUDIT.md](V5_2_FIELD_PILOT_READINESS_AUDIT.md), 실행 수치는 [VERIFIED_METRICS.md](VERIFIED_METRICS.md)를 참조하세요.
