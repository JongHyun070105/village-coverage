# 파일럿 데이터 체크리스트

## 없으면 시작 불가

- [ ] 담당 행정기관과 책임자, 자료 사용 목적 및 내부 검토 절차를 정했다.
- [ ] pilot 권역·행정코드와 자료 기준일을 지정했다.
- [ ] 계획에 포함할 서비스와 규제 제외 범위를 담당자가 확인했다.
- [ ] 개인 연락처·주민 이름·민감정보를 제거하거나 애초에 수집 대상에서 제외했다.
- [ ] 자료 제공 권한과 재사용 조건을 확인했다.
- [ ] 시나리오·모의값·실제값을 화면과 보고에서 구별하는 담당자가 있다.

## 없어도 제한적으로 시작 가능

- [ ] 마을별 인구·가구·취약특성: 없으면 인구 기반 우선순위와 대표성 판단이 제한된다.
- [ ] 최근 주민조사 및 수요관측: 없으면 수요는 미확정으로 남고 request count를 수요로 대체하지 않는다.
- [ ] 기존 서비스 제공 이력: 없으면 중복 제공 여부는 확인할 수 없다.
- [ ] 공식 provider directory: 없으면 실제 조직 후보를 확인할 수 없다.
- [ ] provider service mapping: 없으면 업종 설명만 보이며 서비스 후보로 자동 확정하지 않는다.
- [ ] 공급자 가용성·수용량·단가·최소 보상: 없으면 운영비·공급 가능성은 `UNKNOWN`이다.
- [ ] 도로 접근성 자료: 없으면 거리 기반 후보 비교는 제한된다.
- [ ] 취소·불참·미수행 및 실제 수행로그: 없으면 운영 성과 검증과 `LOCAL_VALIDATED_OPERATIONAL` 승격은 불가하다.
- [ ] 주민 의견·정정 기록: 없으면 계획의 현장 수용성과 변경 이유를 확인하기 어렵다.

## 각 자료와 함께 기록

- [ ] 제공기관/담당자, 원본 URL 또는 문서 식별자, 재사용 조건
- [ ] 기준일, 수집일, 갱신 주기, 지역 범위
- [ ] source type: `PUBLIC_DATA`, `OFFICIAL_DIRECTORY`, `LOCAL_AUTHORITY_INPUT`, `SURVEY_INPUT`, `PROVIDER_SELF_REPORTED`, `SERVICE_EXECUTION_LOG`, `RESIDENT_FEEDBACK`, `SIMULATED`
- [ ] 결측·중복·정정·충돌과 처리 결정
- [ ] 파일 hash, 템플릿 유형, 행별 미리보기 결과, 승인 batch ID

## 계획 생성 전에 추가 확인 (V5.2)

- [ ] 각 batch가 의도한 `pilot_context_id`에 연결되고 `PILOT` 또는
      `SYNTHETIC_REHEARSAL` 모드가 표시된다.
- [ ] 각 서비스 mapping은 CSV 제안만으로 승인되지 않았고 PLANNER 또는
      REVIEWER가 context별로 결정했다.
- [ ] 수요자료는 계획일 기준 30일 요청 건수와 180일 evidence gate를
      충족한다. 오래된 survey는 현재 수요를 채우는 데 쓰지 않는다.
- [ ] availability 날짜·시간, capacity 기간·단위, 가격의 기준일·단위를
      확인했다. 가격이 없으면 0원이 아니라 UNKNOWN이며, 수치 가정은
      provenance와 사유가 명시되어야 한다.
- [ ] provider 기준 위치와 모든 방향의 도로구간이 확인되었다. 경로가
      없으면 직선거리로 대체하지 않는다.
- [ ] 계획 snapshot의 import batch, provider source, local 운영조건, 가격,
      가정, route fingerprint, 기준일과 freshness warning을 검토했다.
- [ ] 실제 수행 후 로그가 같은 context·승인 plan version·round에 연결되고,
      계획 전체의 execution coverage 전까지 부분 실제 KPI를 UNKNOWN으로
      취급한다.
