# Data provenance and privacy

## Real public data

| Data | Source | Use in prototype | Provenance label |
|---|---|---|---|
| Legal-dong codes | 행정안전부, `StanReginCd.getStanReginCdList` | Canonical 10-digit join key | `REAL PUBLIC DATA` |
| Population | 행정안전부, dataset `15099158` | Total and older-age aggregates by legal area | `REAL PUBLIC DATA` |
| Single-person households | 행정안전부, dataset `15099160` | Total and older-age household aggregates | `REAL PUBLIC DATA` |
| Village halls and senior centers | Public standard dataset `15114136` | Facility counts and representative coordinate anchors | `REAL PUBLIC DATA` |
| Geocoding and legal area of coordinates | Kakao Local API | Coordinate lookup and reverse-code validation | `REAL PUBLIC DATA` |
| Road distance and duration | Kakao Mobility route API | Directed travel matrix cached in SQLite | `REAL PUBLIC DATA` |

## Release snapshot and reuse audit

The catalog pages and metadata below were checked on 2026-10-07. A catalog's
"이용허락범위 제한 없음" statement is recorded as the portal's reuse field;
it does not mean that API credentials or Kakao route responses may be published.
The checked-in fixture is a minimized product input, not a retained raw source
dump.

| Source / official page | Snapshot and scope used | Official reuse evidence | Release artifact |
|---|---|---|---|
| MOIS legal-dong codes, dataset `15077871` | Live code lookup; canonical legal-code join keys in the 54-area fixture. Raw response is not checked in. | Catalog says free and `이용허락범위 제한 없음`. | `data/demo.json`, combined fixture SHA-256 below. |
| MOIS age/sex resident population, dataset `15099158` | Catalog file is dated `2026-08-31` and reports 18,624 rows. The local validated Chungcheongnam-do slice has 2,088 rows; only the 54 pilot area aggregates are in the fixture. | Catalog says free and `이용허락범위 제한 없음`. | `data/demo.json`, combined fixture SHA-256 below; no raw source file is retained. |
| MOIS age/sex single-person households, dataset `15099160` | Reference date `2026-08-31`; 18,624 source rows, with only the 54 pilot area aggregates in the fixture. | Catalog says free and `이용허락범위 제한 없음`. | `data/demo.json`, combined fixture SHA-256 below. |
| National village hall/senior center data, dataset `15114136` | Source reference date `2026-08-27`; catalog response reported 50,609 rows. The fixture uses counts and one coordinate anchor per area across 54 areas. | Official DCAT service metadata (`dct:rights`, modified `2026-09-10`) says `이용허락범위 제한 없음`; the current catalog page itself does not render that field. Recheck before redistribution. | `data/demo.json`, combined fixture SHA-256 below. |
| Buyeo detail entry `15114136:uddi:d4c76add-7771-4c45-a057-e30472b0dae3` | Reference date `2026-08-26`; source entry had 469 rows. The fixture retains 51 minimized rows across 22 Buyeo areas and only facility type/status, coordinates, build date, area, and data date. It excludes names, addresses, phones, and manager names. | The official detail-entry metadata captured for the source audit says `이용허락범위 제한 없음`; the official national service DCAT rights field is linked above. | `data/demo.json`, combined fixture SHA-256 below. |
| Self-support enterprise directory, dataset `15091502` | Reference date `2025-12-31`; 977 normalized nationwide organizations. Representative name excluded. | Official catalog audit: `OPEN_NO_RESTRICTION`. | [`data/provider_snapshots/data_go_kr_15091502_2025-12-31_21c090ee0dcd5c33.json`](../data/provider_snapshots/data_go_kr_15091502_2025-12-31_21c090ee0dcd5c33.json), SHA-256 `41b096ebdbb953651b6b5207148782a4fc7a513d035edf72cb04ae0bc70cd099`. |
| Village-enterprise directory, dataset `15080745` | Reference date `2025-12-31`; 1,727 parsed normalized rows. Business registration number excluded; portal catalog reports 1,726 rows. | Official catalog audit: `OPEN_NO_RESTRICTION`; retain the one-row parser/catalog discrepancy with any count claim. | [`data/provider_snapshots/data_go_kr_15080745_2025-12-31_fa924463f015a777.json`](../data/provider_snapshots/data_go_kr_15080745_2025-12-31_fa924463f015a777.json), SHA-256 `ec8a39e091b5947f0b341d5719f2ae50ae632db759578f54907b75e0d510b260`. |
| Social enterprise directory, dataset `15090110` | Catalog reference date `2025-06-30`; no source rows retained. | Catalog reuse is allowed; the official file link did not yield a verifiable source file in the 2026-10-06 audit. Not ingested. | No snapshot. |
| Cooperative standard data, dataset `15155661` | No snapshot. | Official catalog page did not expose a reuse statement in the 2026-10-06 audit. `UNCLEAR`; ingestion blocked. | No snapshot. |

The combined `data/demo.json` artifact is 85,821 bytes with SHA-256
`ac46b2276e8fcbd48bff4c8503655e75516b3230966fcd12c049df622407b611`.
It covers three regions and 54 legal-area entries; facility detail is limited
to the Buyeo subset above. The checked-in source metadata reports all source
dates, row counts, detail scope, and field exclusions. `artifacts/data_quality_report.json`
and `artifacts/public_schema_manifest.json` describe the source joins and
schema; they are audit artifacts, not raw snapshots. The provider snapshot
files are approximately 0.45 MiB and 0.80 MiB; no raw nationwide population,
household, facility, or provider source file is checked in.

Official references: [legal-dong codes](https://www.data.go.kr/data/15077871/openapi.do),
[population](https://www.data.go.kr/data/15099158/fileData.do),
[single-person households](https://www.data.go.kr/data/15099160/fileData.do),
[facility catalog](https://www.data.go.kr/data/15114136/standard.do),
[facility DCAT rights metadata](https://www.data.go.kr/biz/dcat/metadata/15114136.do),
[self-support directory](https://www.data.go.kr/data/15091502/fileData.do),
[social enterprise directory](https://www.data.go.kr/data/15090110/fileData.do),
[village-enterprise directory](https://www.data.go.kr/data/15080745/fileData.do),
and [cooperative catalog](https://www.data.go.kr/data/15155661/standard.do).

The live source responses, timestamps, field names, and record counts are
recorded in `artifacts/api_smoke_report.json`,
`artifacts/public_schema_manifest.json`, and
`artifacts/data_quality_report.json`. Those artifacts contain no credentials
or raw resident notes. Facility identifiers, names, addresses, telephone
numbers, and manager names are not persisted in the generated pilot data.
The checked-in demo fixture also contains 51 minimized row-level facility
records across 22 Buyeo areas from the detail dataset whose page stated
unrestricted reuse; Hongseong and Asan retain aggregate counts and coordinate
anchors only. The detailed source and fields are documented in
`docs/DATA_DICTIONARY.md`.

## Provider directory snapshots and reuse

The checked-in normalized provider snapshots are limited to the two directory
sources whose official catalog entries were audited as `OPEN_NO_RESTRICTION`:

| Source | Snapshot date | Included records | Reuse decision |
|---|---|---:|---|
| Korea Self-Sufficiency Promotion Agency, nationwide self-support enterprises (`15091502`) | 2025-12-31 | 977 | Ingested; representative name excluded. |
| Ministry of the Interior and Safety, village enterprises (`15080745`) | 2025-12-31 | 1,727 parsed rows | Ingested; business registration number excluded. Official catalog metadata reports 1,726 rows; the one-row difference is recorded and must accompany any count claim. |
| Ministry of Employment and Labor, social enterprises (`15090110`) | catalog date 2025-06-30 | not ingested | Reuse is allowed in the catalog, but a verifiable source file was not available from the official link during the recorded audit. |
| Nationwide cooperative standard data (`15155661`) | catalog page modified 2026-09-15 | not ingested | Reuse terms were unresolved; ingestion is blocked. |

The audit date, source URLs, catalog license fields, row-count checks, and
normalization hashes are in `artifacts/provider_source_audit.json` and
`artifacts/provider_ingestion_summary.json`. The repository contains normalized
snapshots, not retained raw source files. Recheck the official catalog and
terms before reuse beyond this prototype. Provider listing means directory
presence only; it is not an operational verification.

The Kakao route cache is local SQLite runtime data and is not checked in.
Provider terms for route caching and redistribution must be reviewed for the
intended demo or public release. A missing route is never replaced with a
straight-line estimate.

## Simulated pre-R&D inputs

The following are synthetic and seeded with `2026`; they are not resident or
provider survey results:

- service-request observations and monthly demand units;
- provider availability and capacity;
- service unit prices and operating conditions;
- the representative provider hub and route-based cost multipliers.

The UI and reports label these as `SIMULATED FOR PRE-R&D`. The synthetic demand
generator uses public older-population and household proportions to create a
plausible test distribution; this does not turn the generated values into
observed demand. Public population is not apportioned across differently named
administrative villages.

`artifacts/experiment_results.json` also varies synthetic request counts,
modeled need, service categories, and provider capacity over 21 seeds, keeping
the public pilot and route matrix fixed. This is algorithm robustness testing,
not real-world evidence.

## Privacy behavior

- API keys are read server-side and are not printed, returned, or committed.
- Root `.env` is ignored by Git and Docker; `.env.example` contains only empty
  placeholders and non-secret defaults.
- The note demo masks common Korean phone, resident-ID, email, and honorific-name
  patterns. If a pattern is found, the original note is not sent to Gemini.
- Note text is not persisted. Model output is checked against local
  deterministic extraction and is shown as a human-reviewed draft.
- A detected PII pattern is not a complete anonymization guarantee. Do not use
  real resident records until the collection, access, retention, and consent
  process has been reviewed by the responsible organization.

## Source references

- [Legal-dong code OpenAPI](https://www.data.go.kr/data/15077871/openapi.do)
- [Resident population dataset](https://www.data.go.kr/data/15099158/fileData.do)
- [Single-person household dataset](https://www.data.go.kr/data/15099160/fileData.do)
- [Village hall and senior center standard data](https://www.data.go.kr/data/15114136/standard.do)
- [Kakao Mobility multiple-destination route API](https://developers.kakaomobility.com/guide/navi-api/destinations.html)
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)

## V5.2 pilot import lineage

Pilot plans persist their context ID, context snapshot ID, import batch IDs,
region/demand/provider snapshot IDs, row fingerprints, source types,
provenance labels, source record references, mapping decisions, explicit
assumptions, optimizer version, and route matrix fingerprint. Per-row source
and provenance remain attached after promotion. An uploaded organization marked
`REAL_DIRECTORY` must match source ID, source record ID, and name in the local
official-directory table; the local operational conditions still have their
own import provenance.

`PILOT` excludes rows whose source type or provenance is `SIMULATED` and never
loads the demo fixture as a replacement. `SYNTHETIC_REHEARSAL` accepts clearly
labeled simulated rows and assumptions; all resulting plans retain a synthetic
rehearsal label. Explicit scenario assumptions are included in the plan
snapshot, are not rewritten as observed facts, and can change a later plan
version without changing an approved snapshot.
