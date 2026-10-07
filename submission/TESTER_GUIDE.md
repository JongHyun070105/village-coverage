# VillageCoverage 공개 데모 테스트 안내

## 접속 상태

- 실제 공개 테스트 URL: **검증된 주소 없음** (`DEPLOYMENT_READY_NEEDS_USER_AUTH`)
- Render 예상 주소는 [`DEPLOYMENT_PLAN.md`](DEPLOYMENT_PLAN.md)에 기록했지만, 계정 인증과 실제 배포 전까지 접속 가능한 URL로 간주하지 않는다.
- 공개 데모는 로그인 없는 공모전 체험용 synthetic-only sandbox다. 실제 주민, 주민 연락처, 실제 공급자 운영정보, 실제 행정 승인 또는 pilot 데이터는 포함하지 않는다.
- 화면 상단의 `공개 데모 · 합성/공개 데이터` 표시와 시뮬레이션 출처 배지를 확인한다.

## 권장 체험 순서

1. Dashboard에서 서비스 미배정 마을, 기준일, 자료 출처를 확인한다.
2. Area detail에서 수요 evidence와 `조사 필요` 상태를 확인한다.
3. Scenario Compare에서 네 가지 공급안을 비교한다.
4. Provider 화면에서 `데모 불참`을 선택하고 계획 화면으로 돌아간다.
5. 계획에 `데모 승인`을 표시한 뒤 불참을 반영해 재계획하고 전후 차이를 본다.
6. Decision Memo와 Evidence Center에서 결정 근거 및 `SIMULATED`, `PUBLIC DATA`, `OFFICIAL DIRECTORY`, `MODEL ESTIMATE` 출처를 확인한다.

공급자 불참, 계획, 승인 표시는 이 데모 DB에만 저장된다. 개인별 세션은 분리되지 않으므로 다른 방문자의 합성 시나리오가 같은 sandbox에 보일 수 있다. 서버 재시작·재배포 시 startup fixture로 초기화된다. 동시 방문자의 변경 순서는 보장하지 않는다.

## 제한 및 데이터 안내

- 연락처 조회, feedback, 주민 조사·원문, pilot/import, 임의 revision, audit, 관리자성 API는 서버에서 차단된다. UI에서 숨기는 것만으로 제한하지 않는다.
- 재계획 등 데모 write는 합성 데이터 전용 DB에서만 가능하다. 계획·승인 등 허용 write와 대시보드 최적화는 방문자 공통으로 분당 총 20회 제한된다.
- 경로 비용은 공개 데모에서 외부 지도 API를 호출하지 않고 생성한 직선거리 기반 `MODEL ESTIMATE`다. 도로 경로 또는 실제 이동시간이 아니다.
- public demo에서는 외부 LLM·공공 API 키 없이 체크인 fixture를 사용한다.
- 데이터/예산 숫자는 주민 결과, 실제 운영성과, 실수요 정확도, 공급 확정 또는 행정 결재를 뜻하지 않는다.
- cold start가 발생하면 Render 무료 backend가 깨어날 때까지 약 1분 걸릴 수 있다. 이후 15분 유휴 시 다시 sleep할 수 있다.

## 접속 권장

실제 URL 발급 후 외부 브라우저에서 로그인 없이 열고, 먼저 Dashboard를 본다. Desktop과 390×844 mobile-sized viewport, 직접 deep link, refresh, API 오류 상태를 확인한다. Android 기기 검증은 연결된 ARTEMIS 장치가 있을 때 별도로 기록한다.

## 문제 신고

화면 이름과 오류 시각만 전달한다. 주민 연락처, 개인 사례, 비밀키, 인증 정보를 넣지 않는다.
