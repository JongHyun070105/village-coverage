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

The live source responses, timestamps, field names, and record counts are
recorded in `artifacts/api_smoke_report.json`,
`artifacts/public_schema_manifest.json`, and
`artifacts/data_quality_report.json`. Those artifacts contain no credentials
or raw resident notes. Facility identifiers, names, addresses, telephone
numbers, and manager names are not persisted in the generated pilot data.

## Simulated pre-R&D inputs

The following are synthetic and seeded with `2026`; they are not resident or
provider survey results:

- service-request observations and monthly demand units;
- provider availability and capacity;
- service unit prices and beneficiary estimates;
- the representative provider hub and route-based cost multipliers.

The UI and reports label these as `SIMULATED FOR PRE-R&D`. The synthetic demand
generator uses public older-population and household proportions to create a
plausible test distribution; this does not turn the generated values into
observed demand. Public population is not apportioned across differently named
administrative villages.

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
