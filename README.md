# VillageCoverage

**요청이 적다는 이유로 서비스가 필요한 마을이 계획에서 사라지지 않도록 돕는 공공기관 파일럿용 의사결정 지원 프로토타입입니다.**

VillageCoverage는 농촌 생활서비스 배달 앱이 아닙니다. 제한된 예산과 공급자 조건 아래에서 **효율, 균형, 소외 최소화, 최소 서비스 보장** 공급안을 비교해 공공 담당자가 검토하도록 돕습니다. 현재 상태는 **V5.2 RC1 · FIELD_PILOT_READY · 현장 검증 전**입니다. 실제 지자체 운영 실적이나 수요 예측 정확도가 확인됐다는 뜻은 아닙니다.

## 문제

요청이 적은 마을은 기록이 적어서일 수 있습니다. 관측이 적다는 이유로 수요를 0이라고 단정하지 않고, 근거와 불확실성을 분리해 추가 조사가 필요한 곳을 드러냅니다.

## 핵심 아이디어

실제 지역 자료가 제공되면 수요 근거, 공급자 운영조건, 예산, 이동, 일정 정보를 검토하고 여러 공급안을 계산합니다. 담당자는 결과와 근거를 살펴 승인하거나 수정합니다. 시스템은 자동 행정결정, 조달, 계약 또는 서비스 제공을 하지 않습니다.

## 무엇을 해결하는가

- 요청 기록이 적은 지역을 자동으로 무수요 처리하지 않고 조사 필요 상태로 남깁니다.
- 같은 조건에서 공급 시나리오별 배정 지역, 회차, 비용, 이동, 미충족 지역을 비교합니다.
- 공급자 거절이나 변경 입력을 반영해 후속 계획 버전을 다시 계산합니다.
- 수집한 자료의 출처와 기준일, 추정·가정·시뮬레이션을 결과에 연결합니다.
- 제한된 예산으로 가능한 최소 서비스 범위와 추가 재원 추정치를 따로 보여줍니다.

## 주요 기능

현재 기능과 범위는 [기능 현황표](docs/FEATURE_INVENTORY.md)에 정리했습니다. 실제 구현 여부와 현장 검증 여부를 구분합니다.

- 공개 지역 통계와 출처가 있는 공급자 디렉터리 자료를 연결합니다.
- 전화·회의·대리·현장 조사와 주민 의견을 검토 가능한 수요 근거로 기록합니다.
- 예산·공급자·용량·가격·거리·일정 제약을 반영해 계획을 계산합니다.
- Pilot Mode에서 확인된 입력만 사용하고, 없는 값은 Demo 값으로 조용히 대체하지 않습니다.
- 승인, 재계획, 수행 기록, 계획 대비 실적과 데이터 품질 상태를 연결합니다.
- 데모 fixture는 세 지역의 법정리 54곳을 다루며, 시설 상세는 재사용을 확인한 부여 지역 일부에만 포함합니다.

## 공급 시나리오

네 안은 정책 선택지이며 AI 추천이나 정답이 아닙니다. 비교할 때 같은 지역·예산·입력 조건을 사용합니다.

| 화면 표현 | 시나리오 키 | 목적과 해석 |
|---|---|---|
| 효율 우선 | `EFFICIENCY` | 같은 예산에서 배정 서비스 회차를 늘리는 데 집중합니다. 기록이 적거나 이동비가 큰 지역이 빠질 수 있습니다. |
| 균형 | `BALANCED` | 서비스량·권역 분산과 장기 서비스 공백을 함께 고려하고, 조사 필요·취약성·서비스 집중도·이동 비용의 표시된 정책 가중치를 반영합니다. |
| 소외 최소화 | `UNDERSERVED_FIRST` | 입력된 서비스 공백 이력에서 오래 기다린 권역을 먼저 고려합니다. 이력과 결과가 실제 현장 기록인지 확인해야 합니다. |
| 최소 서비스 보장 | `MINIMUM_GUARANTEE` (`minimum_coverage`) | 담당자가 정한 최소 접근·공급 기준을 만족하는 마을 수를 우선 늘립니다. 주민 요청 전체를 모두 만족한다는 뜻은 아닙니다. 예산·공급·경로가 부족하면 미충족 지역을 남기며, 추가 필요액은 가능성과 최적성이 확인될 때만 제시합니다. |

시나리오별 목적함수, 계산 범위, 최적성 표시는 [Optimizer Card](docs/OPTIMIZER_CARD.md)를 확인하세요. 파일럿 경로의 기본 선택은 `BASELINE_DECOMPOSED`입니다. Geographic 및 rolling-horizon 경로는 구현돼 있지만 `EXPERIMENTAL`이며 기본값이 아닙니다.

## 데이터와 AI 역할

AI는 주민 메모나 자유 텍스트에서 날짜, 서비스, 빈도, 제약 같은 항목을 구조화해 담당자가 검토할 초안을 만드는 보조 수단입니다. AI가 공급계획을 결정하거나 최적화하지 않습니다. 모델 호출은 선택 사항이며, 현재 데모는 원문 보존·완전한 익명화를 보장하지 않습니다.

수요 전망은 허용된 출처와 충분도 기준을 만족할 때만 보조 정보로 계산합니다. 기준을 만족하지 못하면 숫자를 지어내지 않고 조사 필요 또는 `UNKNOWN`으로 둡니다. 현재 지역 주민의 장기 실측 시계열이 없어 실제 수요 예측 정확도는 검증되지 않았습니다. 자세한 범위는 [Demand Model Card](docs/MODEL_CARD_DEMAND.md)를 참조하세요.

## 최적화 역할

Optimizer는 선택한 정책과 입력을 바탕으로 예산, 거리, 공급자, 용량, 서비스 비용, 일정, 최소 서비스 조건을 계산합니다. `OPTIMAL`은 선언된 모델과 범위 안에서만 최적성이 증명됐다는 뜻이고, `FEASIBLE`은 제약을 만족하는 실행 가능안이 있다는 뜻입니다. `TIME_LIMIT`과 `UNKNOWN`은 성공이나 최적성 증거로 세지 않습니다.

## 데모

대표 흐름에서는 **간단 집수리**를 예로 사용합니다. 제품 전체가 집수리 전용인 것은 아닙니다. 현재 서비스 구조에는 세탁, 생활필수품, 간단 집수리가 포함되며 서비스별 전달 방식은 달라질 수 있습니다.

데모의 수요, 공급자 운영 가능성·용량·가격, 일부 일정과 비용 입력은 시뮬레이션일 수 있습니다. 공급자 디렉터리 등재는 조직의 해당 기준일 목록 존재만 뜻하며 실제 영업·가용성·참여 의사가 아닙니다. 공모전 제출 영상은 공식 2–5분 기준을 따르며, 초안은 [DEMO_VIDEO_SCRIPT.md](submission/DEMO_VIDEO_SCRIPT.md)에 있습니다. [내부 5–7분 QA walkthrough](docs/DEMO_WALKTHROUGH.md)는 제출 영상용이 아닙니다.

## 실행 방법

macOS 기준 Python `>=3.12,<3.15`, Node.js `>=20.9`, `uv`, `npm`이 필요합니다. Python·Node 버전 조건은 `pyproject.toml`과 `frontend/package.json`에 있습니다. `uv` 자체의 고정 버전은 저장소에서 선언하지 않습니다.

```sh
uv sync --all-groups
cd frontend && npm ci
cd ..
scripts/start_demo.sh
```

브라우저에서 <http://127.0.0.1:3000>을 엽니다. 시작 스크립트는 매 실행마다 새 임시 앱 DB를 만들어 데모 상태를 초기화하고, 종료 시 그 DB를 삭제하지 않습니다. 사용하던 route cache는 유지합니다. 이 방식으로 기존 사용자 DB를 지우지 않고 새 데모 세션을 시작할 수 있습니다.

경로·일정 계산에는 완전한 로컬 Kakao Mobility route cache가 필요합니다. 공개된 데모 route cache가 저장소에 포함돼 있지는 않습니다. 승인된 개발용 키로 한 번 생성하려면 `KAKAO_REST_API_KEY`를 로컬 `.env`에 설정하고 `uv run python scripts/build_travel_matrix.py`를 실행하세요. 이 명령은 외부 API에 요청하고 로컬 SQLite cache를 갱신합니다. 키가 없거나 경로가 빠진 경우 시스템은 직선거리로 대체하지 않고 해당 계획을 계산할 수 없다고 표시합니다. 지도 SDK 키가 없으면 좌표 기반 대체 화면을 사용할 수 있습니다.

`.env`는 선택적 live 데이터 수집·지도·AI 설정에만 필요합니다. `.env.example`은 빈 키 값만 포함합니다. 실제 키는 화면 캡처, 로그, Git에 넣지 마세요. 변수별 용도와 노출 범위는 [환경 변수 예시](.env.example) 및 [데이터 출처 안내](docs/DATA_PROVENANCE.md)를 확인하세요.

| 환경 변수 | 필요 조건 | 용도 / 노출 |
|---|---|---|
| `DATA_GO_KR_SERVICE_KEY` | live 공공데이터 조회·snapshot 갱신 시 선택 | 서버 전용 |
| `KOSIS_API_KEY` | live KOSIS 조회 시 선택 | 서버 전용 |
| `KAKAO_REST_API_KEY` | route cache 생성·live Kakao route 조회 시 선택 | 서버 전용; local demo fixture 시작에는 불필요 |
| `NEXT_PUBLIC_KAKAO_MAP_JS_KEY` | Kakao 지도 SDK 사용 시 선택 | 브라우저 공개 key; 허용 origin 제한 필요 |
| `GEMINI_API_KEY` | 원격 note structuring을 선택할 때만 필요 | 서버 전용; 규칙 기반 경로 사용 가능 |
| `GEMINI_MODEL` | 기본값 변경 시 선택 | 서버 설정 이름만 공개 |

## 검증 결과

현재 RC 브랜치에서 다시 실행한 결과와 정확한 기준 SHA는 [VERIFIED_METRICS.md](docs/VERIFIED_METRICS.md)에 기록합니다. 제출 시에는 [SUBMISSION_EVIDENCE_INDEX.md](docs/SUBMISSION_EVIDENCE_INDEX.md)의 claim-to-evidence 표를 사용하고 각 결과의 `SIMULATED`, `FIELD_VALIDATION_PENDING`, `UNKNOWN` 표기를 유지하세요.

## 실제 데이터 / 추정 / 시뮬레이션 구분

| 표기 | 의미 |
|---|---|
| `PUBLIC DATA` | 출처와 기준일이 있는 공개 지역 통계·시설 자료. 공개 출처라는 사실이 모든 재사용 형태의 허가를 뜻하지는 않습니다. |
| `OFFICIAL DIRECTORY` | 기준일 당시 공식 디렉터리의 조직 레코드. 실제 영업·참여·수용량을 보증하지 않습니다. |
| `LOCAL INPUT` | 담당 기관이나 공급자가 제출한 원자료. 출처·기준일·확인 상태를 별도로 검토해야 합니다. |
| `LOCAL OBSERVATION` | 현지 조사·수행 과정에서 기록한 관측. 표본과 수집 절차가 확인되기 전에는 대표성이나 정확도를 뜻하지 않습니다. |
| `MODEL ESTIMATE` | 명시된 자료와 방법으로 계산한 범위 또는 추정. 관측 사실과 구분합니다. |
| `SCENARIO ASSUMPTION` | 비교를 위해 담당자가 지정한 입력. 실제 사실로 바꾸어 표현하지 않습니다. |
| `SIMULATION` | 재현 가능한 합성 시험·시연 입력과 결과. 실제 주민·공급자·현장 효과가 아닙니다. |
| `UNKNOWN` | 근거가 없어 확인할 수 없는 상태. 0이나 완료로 해석하지 않습니다. |

## 현재 한계

- 실제 기관 데이터·주민의 종단 수요·공급자 가용성/가격·수행 실적에 대한 현장 검증은 시작되지 않았습니다.
- 지역 데이터가 가구 단위 또는 자연마을 단위 수요를 입증하지 않습니다. 확인되지 않은 비율로 쪼개지 않습니다.
- Pilot Mode는 확인된 local input만 사용하며, 부족한 수요·비용·공급·도로 근거가 있으면 계획을 중단합니다.
- Demo의 공급자, 수요, 용량, 가격, 운영 조건과 통제 실험은 시뮬레이션일 수 있습니다.
- 승인 화면의 역할 선택은 데모 흐름이며 인증·권한·전자서명이 아닙니다. 신뢰된 격리 환경에서만 파일럿 준비에 사용하세요.
- 인증이 없는 prototype이므로 공개 인터넷이나 신뢰되지 않은 공유망에 노출하지 마세요.
- 개인정보 패턴 가림은 일부 형식만 처리하는 보조 보호입니다. 완전한 익명화, 접근통제, 보존·삭제 기능을 제공하지 않습니다.
- 외부 API live smoke, 실제 공급자 참여 확인, 수동 스크린리더 검증은 제출 evidence의 automated/mock 통과와 별개입니다.

세부 제한은 [LIMITATIONS.md](docs/LIMITATIONS.md), [TECH_DEBT.md](docs/TECH_DEBT.md), [V5.2 Field-Pilot Readiness Audit](docs/V5_2_FIELD_PILOT_READINESS_AUDIT.md)에 정리했습니다.

## 프로젝트 구조

| 경로 | 내용 |
|---|---|
| `backend/` | FastAPI, evidence·pilot lifecycle, cost, scheduling, routing, optimizer |
| `frontend/` | Next.js 대시보드와 브라우저 E2E |
| `data/demo.json` | 공개 통계·시설 집계 및 일부 최소 시설 상세와 명시된 시뮬레이션 입력이 섞인 데모 fixture |
| `data/provider_snapshots/` | 재사용 범위를 확인한 정규화 공급자 디렉터리 snapshot |
| `artifacts/` | 출처·품질·수요·optimizer·stress·acceptance 검증 자료 |
| `docs/` | 아키텍처, 데이터·모델 카드, 파일럿, 검증·제출 문서 |
| `scripts/` | 데이터 수집, route cache, benchmark, 제안서 acceptance, demo 실행 |

## 문서

- [기능 현황과 상태](docs/FEATURE_INVENTORY.md) · [한계](docs/LIMITATIONS.md) · [다음 단계](docs/ROADMAP.md)
- [데모 walkthrough](docs/DEMO_WALKTHROUGH.md) · [화면 캡처 계획](docs/SUBMISSION_SCREENSHOT_PLAN.md)
- [데이터 출처](docs/DATA_PROVENANCE.md) · [공급자 자료](docs/PROVIDER_DATA_GUIDE.md) · [개인정보 목록](docs/PII_INVENTORY.md)
- [Demand Model Card](docs/MODEL_CARD_DEMAND.md) · [Optimizer Card](docs/OPTIMIZER_CARD.md) · [Public-Sector Workflow](docs/PUBLIC_SECTOR_WORKFLOW.md)
- [파일럿 시작 안내](docs/PILOT_START_GUIDE.md) · [field-pilot readiness audit](docs/V5_2_FIELD_PILOT_READINESS_AUDIT.md)
- [검증 수치](docs/VERIFIED_METRICS.md) · [제출 evidence index](docs/SUBMISSION_EVIDENCE_INDEX.md) · [release notes](docs/RELEASE_NOTES_V5_2_RC1.md)
