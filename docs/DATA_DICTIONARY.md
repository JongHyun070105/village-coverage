# 공개데이터 사전

아래 원본 필드는 현재 공식 API/CSV 응답에서 직접 읽었습니다. 연령별 남녀 컬럼은 응답의 실제 컬럼명을 모두 열거합니다.
Nullable 판정은 현재 응답 표본 기준입니다. 시설명·주소·전화번호·관리기관 예시는 개인정보와 접촉정보 노출 방지를 위해 저장하지 않았습니다.

## 핵심 내부 필드와 조인

| 내부 필드 | 원본 필드 | 계산 또는 연결 방식 | Nullable |
|---|---|---|---|
| `legal_code` | 코드 API `region_cd`, 통계 `법정동코드` | 10자리 exact key | 아니오 |
| `population_total` | 인구 `계` | 원본 총인구 | 아니오 |
| 인구 `65_plus` / `75_plus` / `80_plus` | 원본 연령 컬럼 | 이상 남녀 합계 | 아니오 |
| `single_households_total` | 1인세대 `계` | 원본 총 1인세대 | 아니오 |
| 1인세대 `65_plus` / `75_plus` / `80_plus` | 원본 연령 컬럼 | 이상 남녀 합계 | 아니오 |
| `anchor_lat` / `anchor_lng` | 시설 좌표와 Kakao 역지오코딩 | 대표 앵커 | 조건부 |
| `facility_count` | 시설 API | exact legal-code에 매핑된 시설 레코드 수 | 아니오 |
| `facilities` | 선택적 행 단위 시설 snapshot | 좌표·유형·운영상태·건축일·면적·원천 기준일을 저장하고 이름·주소·전화·관리자 정보는 제외 | 데이터 제공 시 |
| `facility_id` | 내부 fingerprint | 허용된 공개 속성의 SHA-256 fingerprint와 중복 순번으로 생성 | 행 단위 snapshot 제공 시 |
| `simulated_monthly_demand`, `demand_*` | 공개 원본에 없음 | 시뮬레이션 | 예 |

인구와 1인가구는 정확한 10자리 법정동 코드로 연결했습니다. 행정리 이름만으로 통계 인구를 임의 분할하거나 보간하지 않습니다.

## 원본 필드 전체 목록

시설 API의 현재 `data/demo.json` snapshot은 집계치와 대표 좌표만 보존합니다.
행 단위 시설은 아직 적재되어 있지 않으며, SQLite v12는 허용 속성만 저장할
테이블과 조회 경로를 제공합니다. 공식 원본에 존재하는 시설명·주소·전화번호·
관리기관 필드 및 원본 식별자는 저장하지 않습니다.

### 행정안전부 법정동 코드 OpenAPI (`data.go.kr/15077871`)

제공기관: 행정안전부
기준일/기준연월: —
관측 행 수: 20560
실제 호출/다운로드: `GET https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList`
공식 안내: https://www.data.go.kr/data/15077871/openapi.do

| 원본 필드명 | 의미 | 내부 필드 | 조인 역할 | 실제 예시 | Nullable(표본) |
|---|---|---|---|---|---|
| `region_cd` | 10자리 법정동 지역코드. | `legal_code` | join key | `2717010900` | 아니오 |
| `sido_cd` | 시도 행정표준 코드. | `—` | — | `27` | 아니오 |
| `sgg_cd` | 시군구 행정표준 코드. | `—` | — | `170` | 아니오 |
| `umd_cd` | 읍면동 행정표준 코드. | `—` | — | `109` | 아니오 |
| `ri_cd` | 리 행정표준 코드. | `—` | — | `00` | 아니오 |
| `locatjumin_cd` | 주민등록 지역코드. | `—` | — | `2717010900` | 아니오 |
| `locatjijuk_cd` | 지적 지역코드. | `—` | — | `2717010900` | 아니오 |
| `locatadd_nm` | 지역 주소명. | `legal_name` | — | `대구광역시 서구 원대동3가` | 아니오 |
| `locat_order` | 지역 코드 서열. | `—` | — | `9` | 아니오 |
| `locat_rm` | 지역 코드 비고. | `—` | — | `—` | 예 |
| `locathigh_cd` | 상위 지역코드. | `—` | — | `2717000000` | 아니오 |
| `locallow_nm` | 최하위 지역명. | `legal_name` | — | `원대동3가` | 아니오 |
| `adpt_de` | 법정동 코드 생성일(YYYYMMDD). | `—` | — | `—` | 예 |

### 행정안전부 주민등록 인구 CSV (`data.go.kr/15099158`)

제공기관: 행정안전부
기준일/기준연월: 20260831
관측 행 수: 2088
실제 호출/다운로드: `CSV linked from https://www.data.go.kr/data/15099158/fileData.do`
공식 안내: https://www.data.go.kr/data/15099158/fileData.do

| 원본 필드명 | 의미 | 내부 필드 | 조인 역할 | 실제 예시 | Nullable(표본) |
|---|---|---|---|---|---|
| `법정동코드` | 법정동 10자리 코드. | `legal_code` | join key | `4413110100` | 아니오 |
| `기준연월` | 통계 기준연월(YYYYMM). | `public_data_reference_date` | — | `2026-08-31` | 아니오 |
| `시도명` | 시도명. | `province` | — | `충청남도` | 아니오 |
| `시군구명` | 시군구명. | `county` | — | `천안시 동남구` | 아니오 |
| `읍면동명` | 읍면동명. | `town` | — | `대흥동` | 아니오 |
| `리명` | 법정리명. | `village_name` | — | `서리` | 예 |
| `계` | 총 주민등록 인구수. | `population_total` | — | `595` | 아니오 |
| `남자` | 남성 인구 또는 남성 1인세대 수. | `—` | — | `380` | 아니오 |
| `여자` | 여성 인구 또는 여성 1인세대 수. | `—` | — | `215` | 아니오 |
| `0세남자` | 0세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `1세남자` | 1세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `2세남자` | 2세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `3세남자` | 3세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `4세남자` | 4세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `5세남자` | 5세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `6세남자` | 6세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `7세남자` | 7세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `8세남자` | 8세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `9세남자` | 9세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `10세남자` | 10세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `11세남자` | 11세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `12세남자` | 12세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `13세남자` | 13세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `14세남자` | 14세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `15세남자` | 15세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `16세남자` | 16세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `17세남자` | 17세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `18세남자` | 18세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `19세남자` | 19세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `20세남자` | 20세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `21세남자` | 21세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `22세남자` | 22세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `23세남자` | 23세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `24세남자` | 24세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `25세남자` | 25세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `26세남자` | 26세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `27세남자` | 27세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `28세남자` | 28세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `29세남자` | 29세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `30세남자` | 30세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `31세남자` | 31세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `32세남자` | 32세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `33세남자` | 33세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `34세남자` | 34세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `35세남자` | 35세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `36세남자` | 36세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `37세남자` | 37세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `38세남자` | 38세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `39세남자` | 39세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `40세남자` | 40세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `41세남자` | 41세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `42세남자` | 42세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `7` | 아니오 |
| `43세남자` | 43세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `44세남자` | 44세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `45세남자` | 45세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `46세남자` | 46세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `47세남자` | 47세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `48세남자` | 48세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `49세남자` | 49세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `50세남자` | 50세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `51세남자` | 51세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `13` | 아니오 |
| `52세남자` | 52세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `53세남자` | 53세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `54세남자` | 54세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `55세남자` | 55세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `12` | 아니오 |
| `56세남자` | 56세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `57세남자` | 57세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `11` | 아니오 |
| `58세남자` | 58세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `16` | 아니오 |
| `59세남자` | 59세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `21` | 아니오 |
| `60세남자` | 60세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `8` | 아니오 |
| `61세남자` | 61세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `7` | 아니오 |
| `62세남자` | 62세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `15` | 아니오 |
| `63세남자` | 63세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `10` | 아니오 |
| `64세남자` | 64세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `11` | 아니오 |
| `65세남자` | 65세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `11` | 아니오 |
| `66세남자` | 66세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `67세남자` | 67세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `11` | 아니오 |
| `68세남자` | 68세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `69세남자` | 69세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `10` | 아니오 |
| `70세남자` | 70세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `71세남자` | 71세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `72세남자` | 72세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `7` | 아니오 |
| `73세남자` | 73세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `74세남자` | 74세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `75세남자` | 75세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `76세남자` | 76세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `77세남자` | 77세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `78세남자` | 78세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `79세남자` | 79세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `80세남자` | 80세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `81세남자` | 81세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `82세남자` | 82세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `83세남자` | 83세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `84세남자` | 84세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `8` | 아니오 |
| `85세남자` | 85세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `86세남자` | 86세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `87세남자` | 87세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `88세남자` | 88세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `89세남자` | 89세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `90세남자` | 90세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `91세남자` | 91세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `92세남자` | 92세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `93세남자` | 93세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `94세남자` | 94세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `95세남자` | 95세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `96세남자` | 96세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `97세남자` | 97세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `98세남자` | 98세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `99세남자` | 99세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `100세남자` | 100세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `101세남자` | 101세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `102세남자` | 102세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `103세남자` | 103세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `104세남자` | 104세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `105세남자` | 105세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `106세남자` | 106세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `107세남자` | 107세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `108세남자` | 108세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `109세남자` | 109세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `110세이상 남자` | 110세 이상 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `0세여자` | 0세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `1세여자` | 1세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `2세여자` | 2세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `3세여자` | 3세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `4세여자` | 4세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `5세여자` | 5세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `6세여자` | 6세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `7세여자` | 7세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `8세여자` | 8세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `9세여자` | 9세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `10세여자` | 10세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `11세여자` | 11세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `12세여자` | 12세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `13세여자` | 13세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `14세여자` | 14세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `15세여자` | 15세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `16세여자` | 16세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `17세여자` | 17세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `18세여자` | 18세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `19세여자` | 19세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `20세여자` | 20세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `21세여자` | 21세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `22세여자` | 22세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `23세여자` | 23세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `24세여자` | 24세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `25세여자` | 25세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `26세여자` | 26세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `27세여자` | 27세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `28세여자` | 28세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `29세여자` | 29세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `30세여자` | 30세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `31세여자` | 31세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `32세여자` | 32세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `33세여자` | 33세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `34세여자` | 34세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `35세여자` | 35세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `36세여자` | 36세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `37세여자` | 37세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `38세여자` | 38세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `39세여자` | 39세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `40세여자` | 40세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `41세여자` | 41세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `42세여자` | 42세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `43세여자` | 43세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `44세여자` | 44세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `45세여자` | 45세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `46세여자` | 46세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `47세여자` | 47세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `48세여자` | 48세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `49세여자` | 49세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `50세여자` | 50세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `51세여자` | 51세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `52세여자` | 52세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `53세여자` | 53세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `54세여자` | 54세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `55세여자` | 55세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `56세여자` | 56세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `57세여자` | 57세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `58세여자` | 58세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `59세여자` | 59세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `60세여자` | 60세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `61세여자` | 61세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `62세여자` | 62세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `63세여자` | 63세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `9` | 아니오 |
| `64세여자` | 64세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `65세여자` | 65세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `14` | 아니오 |
| `66세여자` | 66세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `67세여자` | 67세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `68세여자` | 68세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `69세여자` | 69세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `8` | 아니오 |
| `70세여자` | 70세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `71세여자` | 71세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `72세여자` | 72세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `10` | 아니오 |
| `73세여자` | 73세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `8` | 아니오 |
| `74세여자` | 74세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `75세여자` | 75세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `76세여자` | 76세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `77세여자` | 77세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `78세여자` | 78세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `6` | 아니오 |
| `79세여자` | 79세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `7` | 아니오 |
| `80세여자` | 80세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `81세여자` | 81세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `82세여자` | 82세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `83세여자` | 83세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `84세여자` | 84세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `85세여자` | 85세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `86세여자` | 86세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `87세여자` | 87세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `88세여자` | 88세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `89세여자` | 89세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `90세여자` | 90세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `91세여자` | 91세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `92세여자` | 92세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `93세여자` | 93세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `94세여자` | 94세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `95세여자` | 95세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `96세여자` | 96세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `97세여자` | 97세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `98세여자` | 98세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `99세여자` | 99세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `100세여자` | 100세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `101세여자` | 101세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `102세여자` | 102세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `103세여자` | 103세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `104세여자` | 104세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `105세여자` | 105세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `106세여자` | 106세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `107세여자` | 107세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `108세여자` | 108세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `109세여자` | 109세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `110세이상 여자` | 110세 이상 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |

### 행정안전부 1인세대 CSV (`data.go.kr/15099160`)

제공기관: 행정안전부
기준일/기준연월: 20260831
관측 행 수: 18624
실제 호출/다운로드: `CSV linked from https://www.data.go.kr/data/15099160/fileData.do`
공식 안내: https://www.data.go.kr/data/15099160/fileData.do

| 원본 필드명 | 의미 | 내부 필드 | 조인 역할 | 실제 예시 | Nullable(표본) |
|---|---|---|---|---|---|
| `법정동코드` | 법정동 10자리 코드. | `legal_code` | join key | `1111010100` | 아니오 |
| `기준연월` | 통계 기준연월(YYYYMM). | `public_data_reference_date` | — | `2026-08-31` | 아니오 |
| `시도명` | 시도명. | `province` | — | `서울특별시` | 아니오 |
| `시군구명` | 시군구명. | `county` | — | `종로구` | 아니오 |
| `읍면동명` | 읍면동명. | `town` | — | `청운동` | 아니오 |
| `리명` | 법정리명. | `village_name` | — | `—` | 예 |
| `계` | 총 주민등록 1인세대 수. | `single_households_total` | — | `182` | 아니오 |
| `남자` | 남성 인구 또는 남성 1인세대 수. | `—` | — | `67` | 아니오 |
| `여자` | 여성 인구 또는 여성 1인세대 수. | `—` | — | `115` | 아니오 |
| `0세남자` | 0세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `1세남자` | 1세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `2세남자` | 2세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `3세남자` | 3세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `4세남자` | 4세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `5세남자` | 5세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `6세남자` | 6세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `7세남자` | 7세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `8세남자` | 8세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `9세남자` | 9세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `10세남자` | 10세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `11세남자` | 11세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `12세남자` | 12세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `13세남자` | 13세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `14세남자` | 14세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `15세남자` | 15세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `16세남자` | 16세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `17세남자` | 17세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `18세남자` | 18세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `19세남자` | 19세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `20세남자` | 20세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `21세남자` | 21세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `22세남자` | 22세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `23세남자` | 23세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `24세남자` | 24세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `25세남자` | 25세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `26세남자` | 26세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `27세남자` | 27세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `28세남자` | 28세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `29세남자` | 29세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `30세남자` | 30세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `31세남자` | 31세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `32세남자` | 32세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `33세남자` | 33세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `34세남자` | 34세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `35세남자` | 35세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `36세남자` | 36세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `37세남자` | 37세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `38세남자` | 38세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `39세남자` | 39세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `40세남자` | 40세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `41세남자` | 41세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `42세남자` | 42세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `43세남자` | 43세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `44세남자` | 44세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `45세남자` | 45세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `46세남자` | 46세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `47세남자` | 47세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `48세남자` | 48세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `49세남자` | 49세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `50세남자` | 50세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `51세남자` | 51세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `52세남자` | 52세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `53세남자` | 53세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `54세남자` | 54세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `55세남자` | 55세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `56세남자` | 56세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `57세남자` | 57세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `58세남자` | 58세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `59세남자` | 59세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `60세남자` | 60세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `61세남자` | 61세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `62세남자` | 62세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `63세남자` | 63세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `64세남자` | 64세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `65세남자` | 65세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `66세남자` | 66세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `67세남자` | 67세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `68세남자` | 68세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `69세남자` | 69세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `70세남자` | 70세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `71세남자` | 71세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `72세남자` | 72세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `73세남자` | 73세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `74세남자` | 74세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `75세남자` | 75세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `76세남자` | 76세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `77세남자` | 77세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `78세남자` | 78세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `79세남자` | 79세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `80세남자` | 80세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `81세남자` | 81세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `82세남자` | 82세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `83세남자` | 83세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `84세남자` | 84세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `85세남자` | 85세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `86세남자` | 86세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `87세남자` | 87세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `88세남자` | 88세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `89세남자` | 89세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `90세남자` | 90세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `91세남자` | 91세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `92세남자` | 92세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `93세남자` | 93세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `94세남자` | 94세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `95세남자` | 95세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `96세남자` | 96세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `97세남자` | 97세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `98세남자` | 98세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `99세남자` | 99세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `100세남자` | 100세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `101세남자` | 101세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `102세남자` | 102세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `103세남자` | 103세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `104세남자` | 104세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `105세남자` | 105세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `106세남자` | 106세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `107세남자` | 107세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `108세남자` | 108세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `109세남자` | 109세 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `110세이상 남자` | 110세 이상 남성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `0세여자` | 0세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `1세여자` | 1세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `2세여자` | 2세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `3세여자` | 3세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `4세여자` | 4세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `5세여자` | 5세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `6세여자` | 6세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `7세여자` | 7세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `8세여자` | 8세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `9세여자` | 9세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `10세여자` | 10세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `11세여자` | 11세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `12세여자` | 12세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `13세여자` | 13세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `14세여자` | 14세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `15세여자` | 15세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `16세여자` | 16세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `17세여자` | 17세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `18세여자` | 18세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `19세여자` | 19세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `20세여자` | 20세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `21세여자` | 21세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `22세여자` | 22세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `23세여자` | 23세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `24세여자` | 24세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `25세여자` | 25세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `26세여자` | 26세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `27세여자` | 27세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `28세여자` | 28세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `29세여자` | 29세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `30세여자` | 30세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `31세여자` | 31세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `32세여자` | 32세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `33세여자` | 33세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `34세여자` | 34세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `35세여자` | 35세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `36세여자` | 36세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `37세여자` | 37세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `38세여자` | 38세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `39세여자` | 39세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `40세여자` | 40세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `41세여자` | 41세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `42세여자` | 42세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `43세여자` | 43세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `44세여자` | 44세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `45세여자` | 45세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `46세여자` | 46세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `47세여자` | 47세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `48세여자` | 48세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `49세여자` | 49세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `50세여자` | 50세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `51세여자` | 51세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `52세여자` | 52세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `53세여자` | 53세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `54세여자` | 54세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `55세여자` | 55세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `56세여자` | 56세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `57세여자` | 57세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `58세여자` | 58세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `59세여자` | 59세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `60세여자` | 60세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `61세여자` | 61세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `62세여자` | 62세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `63세여자` | 63세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `64세여자` | 64세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `65세여자` | 65세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `66세여자` | 66세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `67세여자` | 67세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `68세여자` | 68세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `69세여자` | 69세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `70세여자` | 70세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `71세여자` | 71세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `72세여자` | 72세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `73세여자` | 73세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `74세여자` | 74세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `75세여자` | 75세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `76세여자` | 76세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `77세여자` | 77세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `78세여자` | 78세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `79세여자` | 79세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `80세여자` | 80세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `81세여자` | 81세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `5` | 아니오 |
| `82세여자` | 82세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `83세여자` | 83세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `3` | 아니오 |
| `84세여자` | 84세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `4` | 아니오 |
| `85세여자` | 85세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `86세여자` | 86세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `87세여자` | 87세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `88세여자` | 88세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `89세여자` | 89세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `90세여자` | 90세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `91세여자` | 91세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `2` | 아니오 |
| `92세여자` | 92세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `93세여자` | 93세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `94세여자` | 94세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `95세여자` | 95세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `1` | 아니오 |
| `96세여자` | 96세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `97세여자` | 97세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `98세여자` | 98세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `99세여자` | 99세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `100세여자` | 100세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `101세여자` | 101세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `102세여자` | 102세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `103세여자` | 103세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `104세여자` | 104세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `105세여자` | 105세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `106세여자` | 106세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `107세여자` | 107세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `108세여자` | 108세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `109세여자` | 109세 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |
| `110세이상 여자` | 110세 이상 여성 인구 또는 1인세대 수. | `age-specific source count` | — | `0` | 아니오 |

### 전국 마을회관·경로당 표준데이터 API (`data.go.kr/15114136`)

제공기관: 행정안전부
기준일/기준연월: 2026-08-27
관측 행 수: 50609
실제 호출/다운로드: `GET https://api.data.go.kr/openapi/tn_pubr_public_vill_hall_sen_cent_api`
공식 안내: https://www.data.go.kr/data/15114136/standard.do

| 원본 필드명 | 의미 | 내부 필드 | 조인 역할 | 실제 예시 | Nullable(표본) |
|---|---|---|---|---|---|
| `flctNm` | 시설명. | `—` | not persisted | `—` | 아니오 |
| `flctTyp` | 시설 유형. | `—` | — | `마을회관및경로당` | 아니오 |
| `lctnRoadNmAddr` | 도로명 주소. | `—` | not persisted | `—` | 아니오 |
| `lctnLotnoAddr` | 지번 주소. | `—` | not persisted | `—` | 예 |
| `lat` | 위도(WGS84 좌표). | `anchor_lat` | coordinate input | `36.47553189` | 아니오 |
| `lot` | 경도(WGS84 좌표). | `anchor_lng` | coordinate input | `127.2363253` | 아니오 |
| `busiCodNm` | 시설 운영 유형 코드명. | `—` | — | `영업` | 아니오 |
| `telno` | 시설 연락 전화번호. | `—` | not persisted | `—` | 예 |
| `builYmd` | 시설 건축일. | `—` | — | `2013-01-01` | 아니오 |
| `builArea` | 시설 건축 면적. | `—` | — | `73.4` | 예 |
| `mngInstNm` | 시설 관리기관명. | `—` | not persisted | `—` | 아니오 |
| `crtrYmd` | 원천 레코드 기준일. | `—` | — | `2026-01-13` | 아니오 |
| `insttCode` | 제공기관 코드. | `—` | — | `5690000` | 아니오 |
| `insttNm` | 제공기관명. | `—` | not persisted | `—` | 아니오 |
