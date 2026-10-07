# 공개 테스트 URL 배포 준비도

**현재 판정: `NOT READY` — 공개 URL을 만들거나 외부에 공유하지 않는다.** 공식 공고에서 웹 서비스 테스트 URL은 필수다. 현재 repository는 field-pilot-ready prototype이지만 공개 인터넷 데모가 안전한 상태는 아니다. 배포 명령이나 외부 서비스 변경은 하지 않았다.

## 현재 차단 사유

1. `backend/api_feedback.py`의 `GET /api/feedback/{feedback_id}/contact`는 `role` 쿼리값을 요구할 뿐 인증/인가를 하지 않고 연락처를 반환한다. `backend/governance.py`와 [`docs/PUBLIC_SECTOR_WORKFLOW.md`](../docs/PUBLIC_SECTOR_WORKFLOW.md)는 PLANNER/REVIEWER 선택이 데모 역할이지 인증이 아니라고 명시한다.
2. API에는 피드백 접수·검토, 제공자 참여, 수요·자료 적재, 계획 생성·재계획·승인 등 쓰기 경로가 많다. 누가 호출할지 제한하는 production auth가 없다. 공용 SQLite를 열면 평가자가 다른 사용자의 데모 상태를 바꿀 수 있다.
3. `public_demo_mode` 또는 synthetic-only / no-contact / read-only / per-session reset 경계가 구현되어 있지 않다. 현재는 공개 URL용 데이터 격리나 재현 가능한 초기화도 보장되지 않는다.
4. `.env.example`은 data.go.kr, KOSIS, Kakao 서버 키와 Gemini 키를 서버 전용으로 둔다. 브라우저 지도 키는 공개되더라도 도메인 제한이 필요하다. 실제 운영 환경 값은 이 저장소에 기록하지 않는다.

현재 `backend/api_feedback.py`의 연락처 조회 한 건만 끄는 것으로 충분하지 않다. 여러 쓰기 API와 데모 데이터 reset/session-isolation 설계까지 같이 검토해야 한다. 공모전 URL 때문에 full authentication system을 새로 만드는 것은 이번 작업 범위가 아니다. 다만 외부 공개 전 최소한의 공개 데모 경계는 필요하다.

## 합격 조건이 될 최소 안전 범위

- 전 요청이 합성/공개 데이터만 읽고, 개인 연락처·주민 원문 메모·관리자 정보를 제공하지 않는다.
- 연락처 경로는 라우트 수준에서 차단한다. 숨김 UI나 역할 선택에 의존하지 않는다.
- 쓰기는 기본 차단한다. 시연상 재계획 등 필요한 동작은 고정 합성 fixture에 한정해 평가자끼리 상태를 공유하지 않거나, 초기화 가능한 일회성 세션 상태로 격리한다.
- CSV 업로드·임의 외부 데이터 입력·제공자 운영정보 변경·관리자 endpoint를 차단한다.
- secret은 server-only 환경변수로 보관하고, 지도 브라우저 키는 승인된 도메인으로 제한한다. 오류 응답·로그·캡처에서 키와 개인 자료를 확인한다.
- CORS를 최종 프론트 도메인만 허용하고, 외부 접근 가능한 API 표면을 목록화한다.
- 새 브라우저에서 읽기 경로, 쓰기 거부, 연락처 거부, reset/session isolation, 키 노출, 데모 화면 표시를 별도로 검증한다.

이것은 full production authentication/authorization을 대체하지 않는다. 실데이터 운영에는 적합하지 않다.

## 호스팅 후보와 현재 판단

| 선택지 | 적합성 | 주의 |
|---|---|---|
| Vercel frontend + Railway FastAPI | 조건부 후보. Next.js 프런트와 Python API를 분리할 수 있고 Railway 볼륨은 서비스에 마운트된 경로에 영속 데이터를 보존할 수 있다. | Railway Hobby는 현재 $5/월 기본료와 $5 사용량 포함액, 초과 리소스 과금 구조다. 실제 비용은 사용량에 따라 달라진다. SQLite를 쓴다면 데이터 경로를 볼륨에 맞추고 한 API 인스턴스/초기화/백업 동작을 확인한다. 배포 스펙과 지역 비용은 확정하지 않았다. |
| Render frontend/API 분리 | 조건부 대안. 유료 웹 서비스에 persistent disk를 연결해 SQLite 경로를 보존할 수 있다. | 무료 인스턴스는 유휴 15분 뒤 sleep하며 깨우는 데 약 1분이 걸릴 수 있고, 무료 파일시스템은 재시작·재배포 시 데이터를 보존하지 않는다. 제출 당일 응답성과 DB 지속성이 필요하면 무료 플랜은 맞지 않는다. |
| Vercel 단독 FastAPI + SQLite | 권장하지 않음. | 현재 저장소의 FastAPI+SQLite를 서버리스 파일 저장과 같은 것으로 취급하면 안 된다. Vercel Edge Functions는 파일시스템 접근이 없으며 persistent database를 사용하라고 안내한다. 별도 DB로 옮기는 것은 이번 공모전용 요구보다 범위가 크다. |

`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`이 있다. Compose는 FastAPI를 `8000`, Next.js를 `3000`에 공개하고 API의 `/var/lib/villagecoverage` 아래 SQLite/cache에 named volume을 붙인다. 그러나 이것은 로컬 Compose 실행 구성이지 외부 공급자 배포·secret·도메인·공개 데모 경계를 검증한 설정은 아니다. 프런트의 `NEXT_PUBLIC_API_BASE_URL`과 Kakao JS key는 build arg이고, CORS의 `FRONTEND_ORIGINS`는 최종 도메인에 맞춰야 한다. Compose에 노출된 host port와 환경변수도 안전한 public mode를 대신하지 않는다. 비용은 `NOT_ESTIMATED`; Railway 기본료는 게시 가격일 뿐 견적이나 지출 승인이 아니다.

## DB와 reset 판단

- 안전한 정적/읽기 전용 데모라면 영속 데이터가 필수는 아니다. 이 경우 앱이 DB 변경에 의존하지 않고 fixture를 매번 재현할 수 있어야 한다.
- 현재 앱은 사용자 작업과 계획 결과를 SQLite에 저장한다. 합성 데이터만 넣는다고 공유 쓰기가 안전해지지는 않는다.
- 재계획 시연을 보존하려면 per-session isolation과 초기화 또는 단일 데모 세션 전용 통제가 필요하다. 단일 SQLite 파일을 다중 writer/수평 확장으로 운영하는 구성은 선택하지 않는다.
- 사용자 작업은 사용자별로 분리하거나 매 세션 초기화하기 전까지 외부 URL을 제출하지 않는다.

## URL 제출 전 체크

- [ ] 공개 모드 구현 및 별도 보안 검토 통과
- [ ] 모든 API에 synthetic-only 및 허용 메서드 경계 확인
- [ ] 연락처·개인정보·관리자 라우트 외부 접근 차단 확인
- [ ] reset/session isolation과 동시 브라우저 사용 검증
- [ ] 실제 도메인·CORS·환경변수·secret 경계 점검
- [ ] 로그·오류·브라우저·스크린샷에 PII/secret이 없는지 확인
- [ ] cold start 포함해 새 브라우저에서 실제 URL 접속 및 핵심 플로우 확인
- [ ] 평가자가 사용할 안전한 권한과 제한을 `TESTER_GUIDE.md`에 기재

외부 인프라 생성·배포는 이 문서 작성 과정에서 수행하지 않았다.

## 호스팅 근거 (2026-10-07 확인)

- [Railway 가격](https://docs.railway.com/pricing/plans): Hobby 기본료·사용량 포함액·리소스 단가.
- [Railway 볼륨](https://docs.railway.com/volumes): 서비스 마운트 경로와 데이터 영속성.
- [Render 무료 인스턴스와 파일시스템 FAQ](https://render.com/docs/faq), [Render Persistent Disks](https://render.com/docs/disks).
- [Vercel Edge Functions 파일시스템 제한](https://vercel.com/docs/functions/runtimes/edge/edge-functions).
