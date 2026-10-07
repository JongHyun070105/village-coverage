# 공개 테스트 URL 배포 기록

**현재 상태: `DEPLOYMENT_READY_NEEDS_USER_AUTH`**

보안 경계, public-demo 설정, 배포 설정, 테스트 코드는 준비했다. Render Dashboard에서 로그인 화면을 확인했지만 현재 연결된 세션이 없어 이 작업에서 배포를 생성하거나 URL을 검증하지 못했다. 프로젝트에서 확인된 공개 URL은 없으며 예상 주소를 제출 URL로 사용하지 않는다.

## 선택한 구성

Render의 동일 Singapore 리전에 Native Node.js와 Python Web Service 두 개를 둔다. Next.js는 Render HTTPS 프런트엔드, FastAPI는 Render HTTPS API다. 배포 정의는 저장소 루트 [`../render.yaml`](../render.yaml)에 한 번만 둔다.

| 항목 | 결정 |
|---|---|
| 프런트엔드 | Render Free Node.js Web Service, standalone server entrypoint |
| API | Render Free Python Web Service, `--workers 1` |
| DB | 전용 `/tmp` SQLite 2개(앱 상태와 합성 경로 추정 캐시 분리) |
| 초기화 | 프로세스 startup 때 DB/WAL/SHM 삭제 후 fixture와 경로 추정치를 재생성 |
| 외부 키/API | 없음. 공개 fixture 및 결정론적 straight-line estimate만 사용 |
| CORS | 프런트엔드 HTTPS origin 하나만 설정 |
| 인스턴스 | 무료 단일 인스턴스; scale-out 구성 없음 |
| 도메인/TLS | 플랫폼 `onrender.com` host 및 managed HTTPS |
| 비용 계획 | $0/month free compute, included-usage 한도 내에서만 |

예상 host는 `https://villagecoverage-public-demo-web.onrender.com` 및 `https://villagecoverage-public-demo-api.onrender.com`이다. 서비스가 실제 생성되고 외부에서 TLS·라우트·refresh를 확인하기 전까지 두 값은 **예정값**이다.

### 선정 이유와 경계

- 하나의 Render Blueprint가 두 서비스를 구성하고 플랫폼 TLS, health check, 런타임 `PORT`, 빌드/시작 명령을 관리한다. 현재 Next.js 서버 렌더링 구성을 정적 export로 재구성할 필요가 없다. [Next.js standalone 배포 방식](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)에 맞춰 `.next/standalone/server.js`를 실행하고 `public/`, `.next/static/`을 빌드 산출물에 포함한다.
- 백엔드 free filesystem은 ephemeral이므로 SQLite 영속성을 기대하지 않는다. 앱/route fixture는 시작 시 매번 deterministic하게 재생성된다.
- 무료 서비스는 15분 유휴 후 sleep하고 다음 요청에서 깨우는 데 약 1분 걸릴 수 있다. 무료 서비스의 local file 변경은 restart/redeploy/sleep 후 사라진다.
- Render는 workspace마다 월 750 Free instance hours를 부여하며, Free web services가 이를 공유한다. 이 한도를 다 쓰면 무료 웹 서비스가 월말까지 정지된다. 포함 outbound bandwidth를 넘으면 결제수단이 등록된 계정은 추가 요금이 청구될 수 있고, 결제수단이 없으면 서비스가 월말까지 정지된다. build-pipeline 초과도 spend limit 설정에 따라 청구될 수 있다. 현재 계정의 결제수단·spend limit·잔여 quota는 로그인 전이라 확인되지 않았다. 두 서비스를 생성하기 전에 이 설정과 실제 사용량을 확인하고, 비용 노출이 생기는 설정이면 멈춘다.
- 이 선택은 “공모전 안전 데모” 구성이다. 운영 SLA나 production security/availability 약속이 아니다.

### 배포 대안 비교 (2026-10-07 공식 요금/제약 기준)

| 선택지 | 비용·제약 | 이번 제출 적합성 |
|---|---|---|
| **Render 프런트 + API (선택)** | 두 서비스 모두 Free compute. workspace 단위 월 750 instance hours 공유, 15분 idle sleep, ephemeral filesystem. 포함 bandwidth/build 초과는 계정 결제·spend limit 설정에 따라 요금이 생길 수 있다. | SQLite를 startup seed로 재생성하고, Node/Python을 한 Blueprint로 관리할 수 있다. cold start와 quota 위험은 수용하고 계정 사용량을 먼저 확인한다. |
| Vercel Hobby 프런트 + Render API | 프런트 Hobby는 무료지만 개인·비상업 용도만 허용. API는 Render Free와 같은 sleep/quota/계정 billing 제약. | 두 공급자 계정과 CORS 설정이 필요하고 Hobby 이용 조건을 이번 공모전 공개 데모에 적용할 수 있는지 별도 판단해야 하므로 보류. |
| Vercel Hobby 프런트 + Railway API | Vercel Hobby 이용 제한. Railway Free는 월 `$1` 리소스 크레딧, Hobby는 `$5/month` 최소 사용료와 `$5` 사용량 포함, 초과 사용 추가 청구. | 서비스 분리와 사용량 청구가 추가되고, 무료 초과 비용을 피할 계정 설정도 확인해야 하므로 선택하지 않음. |
| Railway Node + API | Free는 월 `$1` 리소스 크레딧, Hobby는 `$5/month` 최소 사용료와 사용량 기반 초과 청구. Free service별 1 vCPU/0.5 GB 메모리 제한. | 단일 플랫폼이지만 현재 solver/backend와 Next 두 프로세스의 리소스·비용 한도를 실사용으로 검증하지 못했으며, 비용 없는 지속 사용으로 가정할 수 없음. |
| Render Static Site + API | Static Site는 무료지만 현재 Next.js 앱은 Node standalone 서버로 SSR을 제공한다. | 앱을 별도로 정적 export로 바꾸면 현재 범위를 넘고 public demo 라우트 동작도 재검증해야 하므로 제외. |

공식 근거: [Render Free 서비스](https://render.com/docs/free), [Render 요금](https://render.com/pricing), [Vercel Hobby 이용 조건](https://vercel.com/docs/plans/hobby), [Railway 요금표](https://docs.railway.com/pricing/plans). Free tier는 비용이 무조건 0이라는 뜻이 아니다. Blueprint 생성 전 실제 계정의 결제수단, spend limit, 포함 사용량을 확인한다.

## 계정/비용 게이트

Render Dashboard가 로그인 페이지로 열렸다. 기존 로그인 세션이나 연결된 계정을 통해서만 Blueprint를 생성해야 한다. 사용자 interaction이 필요한 로그인에서 멈춘 상태다. 계정 연결, 권한 동의, 약관 동의, 결제수단 추가, 유료 플랜·유료 서비스 선택은 수행하지 않았다. 예상 비용은 `$0/month`지만, included bandwidth/build minutes 초과 시 작업이 중지될 수 있으므로 유료 resource를 선택하면 그 지점에서 멈춘다.

로그인된 계정에서 필요한 동작:

1. `JongHyun070105/village-coverage` 저장소의 `submission/public-demo-deploy` 브랜치를 연결한다.
2. root `render.yaml` Blueprint를 검토하고 두 Free 서비스만 생성한다.
3. Blueprint가 요구하는 추가 변수/결제수단/유료 플랜이 있는지 확인한다. 유료 항목은 선택하지 않는다. 기존 결제수단·spend limit·bandwidth/build 잔여량을 확인하고 추가 청구 가능성을 없애거나 사용자 승인을 받기 전에는 진행하지 않는다.
4. 두 서비스가 healthy해진 뒤 실제 frontend HTTPS URL을 새 브라우저에서 검증한다.

## 외부 URL 검증 체크리스트 — 미실행

- [ ] 실제 HTTPS host가 열리고 브라우저 인증 없이 dashboard가 보임
- [ ] direct deep link와 refresh가 성공
- [ ] API cold start 및 `/health` 확인, 실제 대기시간 기록
- [ ] public dashboard, area evidence, scenario comparison, coverage map, provider view 확인
- [ ] provider decline → replan → Decision Memo 승인 표시와 Evidence Center 흐름 확인
- [ ] contact/import/revision/schema 경로가 404로 차단됨
- [ ] 허용 CORS origin은 프런트 origin이며 임의 origin은 거부됨
- [ ] Desktop 및 390×844 mobile-sized browser 확인
- [ ] API 실패 화면이 white screen이 아닌 준비/오류 안내를 제공하는지 확인
- [ ] 공개 숫자에 synthetic/public/model provenance 배지가 보임
- [ ] screenshot은 실제 URL에서 생성하고 개인정보/secret 없음 확인
- [ ] service status, measured cold start, 월별 free usage를 기록

물리 Android 기기는 `adb devices -l`에서 연결 목록이 비어 있어 ARTEMIS 장치 검증을 수행할 수 없었다. Playwright의 mobile-sized viewport 검증은 별도로 실행한다.

## 공식 가격/제약 확인 (2026-10-07)

- [Render Free instances](https://render.com/docs/free): 15분 idle sleep, 약 1분 wake, ephemeral filesystem, 750 free instance hours/workspace/month, quota 초과 시 서비스 제한.
- [Render pricing](https://render.com/pricing): free compute와 사용량 기반 기능 구분.
- [Render web services](https://render.com/docs/web-services): `0.0.0.0`와 포트 binding, managed host/TLS.
- [Render Blueprint specification](https://render.com/docs/blueprint-spec): `render.yaml` 서비스 정의.
