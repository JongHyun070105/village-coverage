# VillageCoverage 공개 데모 테스트 안내

확인 기준: 2026-10-12

## 접속 주소와 상태

- 공개 웹 데모: https://villagecoverage-public-demo-web.onrender.com
- API health: https://villagecoverage-public-demo-api.onrender.com/api/health
- GitHub deployment record: web/API 성공, ref submission/public-demo-deploy, SHA 7b696499c6c4b59fd613866faa89c1afe8934398. 그 SHA의 Next.js는 16.3.7이다.
- 이 실행의 저빈도 HTTPS GET: 웹 HTTP 200 (22.685초), API health HTTP 200 (52.644초), 인증서 검증 통과.
- 이 값은 브라우저에서 모든 흐름을 테스트했거나 항상 응답한다는 뜻이 아니다. 원격 browser flow는 아직 확인되지 않았다.
- 별도 보안 패치 후보 16.3.8은 현재 public deployment에 배포되지 않았다.

## 첫 방문과 임시 저장

Render Free web service는 15분 유휴 후 잠들 수 있고, 첫 요청에서 깨어나는 데 약 1분까지 걸릴 수 있다. 첫 대시보드 요청은 기다려 본 뒤 오류 안내가 나타나면 다시 시도 버튼을 누른다. 계속 실패하면 URL, 시각, 표시된 오류 코드만 기록한다.

이 데모는 세션별로 계획·공급자 불참·승인 상태를 격리한다. 세션은 30분 idle 뒤 만료된다. Render Free 임시 SQLite에 저장한 계획은 재시작·재배포·spin-down 뒤 초기화될 수 있다. 계획 ID를 영구 공유 링크로 취급하지 않는다.

## 권장 체험 순서

1. Dashboard에서 공개 데이터와 합성 시연값 표시를 확인한다.
2. 시나리오 비교에서 효율·균형·최소 보장·소외 최소화 정책과 제한을 비교한다.
3. 공급자 목록/상세에서 데모 불참을 선택한다.
4. 계획으로 돌아가 재계획 결과와 전후 차이를 확인한다.
5. 계획 상세, Decision Memo, 증거·출처 분류를 확인한다.
6. 새로고침/세션 만료/서버 재시작 뒤 저장 계획이 남는다고 가정하지 않는다.

## 데이터와 제품 경계

- 실제 주민 개인정보·연락처, 실제 공급자 운영정보 또는 행정 승인은 포함하지 않는다. 입력 칸에는 합성 예시만 쓴다.
- 공개 통계는 원출처를 표시하고, 요청·수요·공급자 일정·가격은 합성 fixture일 수 있다.
- 공개 데모의 이동은 좌표 기반 직선거리 MODEL ESTIMATE이며 도로경로나 실제 비용이 아니다.
- AI는 일부 비정형 증거의 검토 가능한 초안을 돕는다. 최적화는 CP-SAT solver, 규칙과 통계 추정은 별도 처리다. 결과는 인간의 결정을 대신하지 않는다.
- 현장 예측 정확도, 실제 비용 절감, 실제 주민 서비스 개선은 검증되지 않았다.

## 아직 검증하지 않은 공개 경로

이번 감사는 GET health만 공개 사이트에서 확인했다. 계획 생성·불참·재계획·export·cookie 속성·심사자 전체 브라우저 흐름은 공개 origin에서 실행하지 않았다. 해당 구간은 현재 CURRENT_BROWSER_FLOW_VERIFIED=NOT_VERIFIABLE이다. Android 기기 검증은 실제 연결 ARTEMIS device가 있을 때 별도 실행해야 한다.
