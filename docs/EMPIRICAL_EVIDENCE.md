# Empirical Evidence and Source Scope

Evidence snapshots describe what the source measured. They do not turn a
national or external observation into a village-level observation.

## KREI rural service survey

- Source: 한국농촌경제연구원, R 2025-23, *저출생·초고령화에 대응한 농촌정책의 전환 (2/2차 연도)*, Chapter 4, Table 4-8.
- Table: 농촌 주민의 생활서비스 필요 충족 현황; unit: percent.
- Published: 2025-12. Source scope: nationwide rural survey respondents. The report does not state the sample size in this table, and the estimate is not representative of a named town or village.
- License recorded by the source registry: citation with attribution.
- Primary sources: [KREI report record](https://repository.krei.re.kr/handle/2018.oak/32516), [report PDF](https://repository.krei.re.kr/bitstream/2018.oak/32516/1/R2025-23.pdf).

The meanings are preserved as published: `need_rate` excludes respondents who
said “not needed at all” or “not needed”; `usage_rate` is among people who
needed the service; `unmet_rate` is the share of needers who did not use it.
Usage plus unmet is 100% subject to published rounding. Need rate is a
propensity among survey respondents. Multiplying it by village population and
calling the result service visits is invalid.

| Service in Table 4-8 | Need | Used among needers | Unmet among needers |
| --- | ---: | ---: | ---: |
| 이동 및 외출 지원 | 13.2% | 16.5% | 83.5% |
| 반찬 지원, 장보기 | 16.5% | 14.0% | 86.0% |
| 청소, 세탁 | 19.0% | 16.4% | 83.6% |
| 목욕 지원 | 17.8% | 26.7% | 73.3% |
| 이미용 | 21.0% | 20.1% | 79.9% |
| 쓰레기/폐기물 처리 | 22.3% | 12.8% | 87.2% |
| 공동급식 | 18.8% | 19.6% | 80.4% |
| 평생교육 프로그램 | 28.4% | 21.1% | 78.9% |
| 문화·여가 활동 지원 | 35.2% | 29.7% | 70.3% |
| 도서 대여 | 27.5% | 16.3% | 83.7% |
| 건강교실 | 41.1% | 29.8% | 70.2% |
| 상하수도, 동파, 보일러 | 28.0% | 4.9% | 95.1% |
| 간단 집수리 | 31.8% | 5.6% | 94.4% |
| 누전·가스차단기, 전기 수리 | 33.1% | 5.8% | 94.2% |
| 안전손잡이, 계단 난간 설치 | 25.6% | 7.4% | 92.6% |
| 도배, 실내 장판 교체 | 31.2% | 6.6% | 93.4% |

Only cleaning/laundry, side-dish/shopping, and simple home repair map to the
initial supported demo services. The other rows remain external context.
Laundry case descriptions and KREI operating patterns are `CASE_REFERENCE`
only; their staffing, prices, capacity, fee policy, and vehicle counts are not
defaults for another region.

## KOSIS social-service survey

Catalog discovery was performed through the official KOSIS catalog on
2026-10-03. The confirmed path is `G > G_14 > 117_A_003` under
사회서비스수요·공급실태조사. The client stores only table IDs found there; it
does not infer IDs from names. See the [KOSIS catalog/API guide](https://kosis.kr/openapi/devGuide/devGuide_0101List.do)
and [statistics data guide](https://kosis.kr/openapi/devGuide/devGuide_0201List.do).

The live snapshot is `artifacts/kosis_snapshot.json`, retrieved
2026-10-03T05:32Z. All eight configured pulls returned `LIVE`:

| Table ID | Catalog title | Retrieved period | Records |
| --- | --- | ---: | ---: |
| DT_117078_001 | 최근 1년간 필요했던 사회서비스: 서비스 영역별 | 2023 | 29 |
| DT_117078_003 | 최근 1년간 이용 경험이 있는 사회서비스: 서비스 영역별 | 2023 | 29 |
| DT_117078_011 | 사회서비스 필요 대비 이용률 | 2023 | 19 |
| DT_117078_005 | 향후 1년 내 이용 의향: 서비스 영역별 | 2023 | 29 |
| DT_117078_012 | 서비스 영역별 양적 충분성 | 2023 | 36 |
| DT_117078_04 | 이용료 부담 주체 의견: 생애주기별 | 2023 | 47 |
| DT_117078_01 | 영역별 사회서비스 이용률 (legacy) | 2017 | 12 |
| DT_117078_09 | 지역 내 동일 서비스 사업체 존재 여부·경쟁 사업체 수 | 2017 | 45 |

KOSIS is `EXTERNAL_CONTEXT`: a nationwide household social-service survey,
not the KREI rural living-service survey and not village demand. The catalog
did not expose matching tables for willingness to pay or desired service time.
The fee-burden opinion table is not a willingness-to-pay measure. Those topics
remain explicitly `NOT_FOUND_IN_CATALOG` in the snapshot.

## Home Doctor monthly support data

- Source: 주택관리공단(주), dataset 15120958, 주택관리공단(주)_임대주택 관리홈닥터 월별지원현황.
- Primary period requested by the provider: 2021-10 onward. The current live API response begins in 2022-01.
- Source note: dates with no data can be present; the provider recommends using data since 2021-10.
- Official listing: [data.go.kr dataset and field metadata](https://www.data.go.kr/data/15120958/fileData.do).
- Live snapshot: `artifacts/home_doctor_snapshot.json`, retrieved 2026-10-03; 22,058 raw rows, 54 contiguous monthly periods from 2022-01 through 2026-06.

The API response has 2,905 rows where the four category counts do not sum to
the reported total. These are retained and counted as a quality issue; the
pipeline does not silently rewrite totals. This source represents vulnerable
households in public rental housing. Its permitted uses here are monthly
count variability, forecast-method checks, category distribution, and
operational load scenarios. It is never a rural demand prior or a village
service-visit estimate.

## Provider-directory source discovery

Two official public-data catalogues were checked on 2026-10-03 as possible
starting points for finding local organizations:

- [Nationwide cooperative standard data](https://www.data.go.kr/data/15155661/standard.do)
  is maintained by local governments and includes cooperative type, address,
  coordinates, and business description. The portal says local submissions are
  merged monthly and may lag. Its page did not expose a reuse license during
  this check, so the source registry marks ingestion `INGEST_BLOCKED`.
- [Nationwide self-support enterprise status](https://www.data.go.kr/data/15091502/fileData.do)
  lists 977 rows for 2025-12-31, was updated 2026-03-09, and states no reuse
  restrictions. It includes enterprise type, address, industry, and a
  representative-name field. The system does not ingest or display these raw
  rows.

These catalogues establish that candidate organizations may be discoverable;
they do not establish that an organization currently operates a supported
service, will participate, or has capacity, availability, staffing, or a
price. They are source-discovery references only and are not joined to the
simulated providers used by the planner. Any later ingestion must minimize
personal fields and separately verify organization status and service fit.

## Provenance and snapshots

Raw response hashes, retrieval timestamps, parameters, record counts, parser
status, and schema checks are stored with the snapshots. KOSIS and Home Doctor
snapshots can be used as last-successful cache when the live endpoint fails;
the UI should retain the cached retrieval date and source status. A schema
change is recorded as `SCHEMA_DRIFT_DETECTED`, not accepted as an empty or
zero-valued dataset.

Plan records bind the source snapshot hashes used at generation time. Updating
the latest source snapshot does not rewrite an existing plan's provenance.
