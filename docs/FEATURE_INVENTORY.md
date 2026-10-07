# V5.2 RC1 기능 현황

상태는 코드와 체크인 evidence에서 확인한 구현 범위를 나타냅니다. `FIELD_VALIDATION_PENDING`은 기능 경로가 있다는 뜻이 아니라 실제 기관·주민·공급자 환경에서 확인되지 않았다는 뜻입니다. 테스트 통과를 현장 효과로 해석하지 않습니다.

| 기능 | 상태 | 현재 범위와 근거 |
|---|---|---|
| 공개 지역 데이터 | `IMPLEMENTED_LIMITED` | 법정동 코드, 인구·1인가구 통계, 시설 집계와 대표 좌표를 fixture에 연결. 재사용을 확인한 부여 지역 22곳에 최소 필드 상세 51행이 있고 다른 pilot 지역은 집계 중심. 커버리지와 기준일은 [DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md), [DATA_PROVENANCE.md](DATA_PROVENANCE.md). |
| 수요 근거 | `IMPLEMENTED_LIMITED` | 조사·요청·기존 제공 기록을 상태·출처와 연결. 적은 기록은 조사 필요로 남기며 실제 수요 대표성은 검증 전. |
| 주민 의견 | `IMPLEMENTED_LIMITED` | 의견 입력, 분류, 검토·중복·충돌 상태가 있음. 실제 현장 사용·완전 익명화는 검증 전. |
| 조사 workflow | `IMPLEMENTED` | 전화·마을회의·대리·현장 조사 입력, 검토, 근거 연결과 재평가. |
| 수요 보정 | `IMPLEMENTED_LIMITED` | 충분도·출처·신선도·실제 execution gates를 계산. 실제 지역 자료로 보정된 프로필은 아직 없음. |
| 수요 전망 | `EXPERIMENTAL` | 충분도 기준을 통과할 때만 범위형 추정을 보조로 제공. 지역 예측 시계열 성능 검증은 없음. |
| 공식 공급자 디렉터리 | `IMPLEMENTED_LIMITED` | 자활기업·마을기업 snapshot을 정규화. 사회적기업은 원본 파일 확인 전 미수집, 협동조합은 재사용 조건 미확인으로 차단. [PROVIDER_DATA_GUIDE.md](PROVIDER_DATA_GUIDE.md) |
| 공급자 운영 입력 | `IMPLEMENTED_LIMITED` | 파일럿에서 공급자 서비스·가용성·용량·가격·참여 입력을 가져오고 출처를 남김. 값은 기관·공급자가 현장에서 확인해야 함. |
| 공급자 가용성 확인 | `FIELD_VALIDATION_PENDING` | 디렉터리 등재는 실제 운영·방문 가능·참여 의사가 아님. 현장 확인 증거가 없음. |
| 공급자 대체 및 재계획 | `IMPLEMENTED_LIMITED` | decline를 반영해 새 버전 후보를 계산하는 synthetic lifecycle과 브라우저 흐름이 있음. 실제 공급자 응답은 확인되지 않음. |
| 비용 모델 | `IMPLEMENTED_LIMITED` | 서비스·이동·인건·재료 등 항목형 비용과 unknown-preserving 입력. demo 가격·운영값은 simulated. |
| 시나리오 비교 | `IMPLEMENTED` | 동일 조건에서 4개 정책안을 비교하고 비용·범위·미충족을 표시. |
| 기본 optimizer | `IMPLEMENTED_LIMITED` | Pilot 경로는 `BASELINE_DECOMPOSED`. 제약·invariant 및 solver status를 기록하며 `TIME_LIMIT`/`UNKNOWN`을 성공으로 세지 않음. |
| Geographic optimizer | `EXPERIMENTAL` | 구현과 회귀/벤치마크 evidence가 있으나 정책 품질·속도 trade-off 때문에 기본 선택이 아님. |
| Rolling-horizon optimizer | `EXPERIMENTAL` | 구현과 회귀/벤치마크 evidence가 있으나 기본 선택이 아님. |
| 일정 생성 | `IMPLEMENTED_LIMITED` | 용량·날짜·시간창·예산·참여 조건을 반영. 공급자 운영 입력은 demo에서 simulated일 수 있음. |
| 경로·이동 | `IMPLEMENTED_LIMITED` | directed road-cache 기반. route cache가 없거나 필요한 구간이 누락되면 계산을 중단하거나 허용된 hub 경로만 사용하며 직선거리로 대체하지 않음. |
| 재계획 | `IMPLEMENTED` | 입력 변경·공급자 decline에 새 plan version을 만들고 이전 승인 snapshot을 보존. |
| 승인 workflow | `IMPLEMENTED_LIMITED` | 제출·검토·승인·변경 요청과 immutable version 상태. 화면의 역할 선택은 demo selector이며 실제 인증·권한·전자서명 아님. |
| Decision Memo | `IMPLEMENTED` | 선택안·근거·미충족·비용 가정을 검토 자료로 구성. 법적 결정 문서는 아님. |
| 수행 기록 입력 | `IMPLEMENTED_LIMITED` | 승인된 계획 회차와 execution log를 연결. 실제 수행 자료는 아직 없음. |
| 계획 대비 실적 | `IMPLEMENTED_LIMITED` | coverage·비용·완료 지표를 계산하고 입력이 불충분하면 `UNKNOWN`을 유지. |
| Pilot import | `IMPLEMENTED` | 미리보기, row validation, 명시적 확인, context-scoped promotion, idempotency와 provenance. |
| Pilot setup | `IMPLEMENTED` | named `PILOT`/`SYNTHETIC_REHEARSAL` context, readiness dimension, source·mapping·assumption을 제공. |
| 데이터 품질 | `IMPLEMENTED` | 오류·경고·신선도·출처·조사 필요 상태를 표시. |
| 근거와 provenance | `IMPLEMENTED` | source, batch, fingerprint, assumption, route와 plan snapshot lineage를 보존. |
| 접근성 | `IMPLEMENTED_LIMITED` | 키보드/focus, label, table, map 대체, responsive 자동 회귀가 있음. 전체 화면 수동 screen-reader 평가와 현장 검증은 pending. |
| 실제 수요 예측 정확도 | `FIELD_VALIDATION_PENDING` | 지역 장기 관측 시계열이 없어 실제 정확도 평가 불가. |
| 인증·인가, 결제, SMS, GPS | `NOT_IMPLEMENTED` | RC 범위 밖. 제품에 포함된 것처럼 표현하지 않음. |

주요 근거는 [V5.2 field-pilot readiness audit](V5_2_FIELD_PILOT_READINESS_AUDIT.md), [현재 RC 수치](VERIFIED_METRICS.md), [제출 evidence index](SUBMISSION_EVIDENCE_INDEX.md)입니다.
