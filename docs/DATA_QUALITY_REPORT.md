# Data quality report

This report summarizes the live public-data pull recorded on 2026-09-30. The
exact machine-readable values are in `artifacts/data_quality_report.json` and
the per-source smoke results are in `artifacts/api_smoke_report.json`.

## Observed source coverage

| Source | Live records | Columns | Reference date / latest source date | Result |
|---|---:|---:|---|---|
| Legal-dong code API | 20,560 | 13 | — | PASS, JSON result `INFO-0` |
| Population CSV | 2,088 | 231 | 2026-08-31 | PASS, Chungcheongnam-do only |
| Single-household CSV | 18,624 | 231 | 2026-08-31 | PASS, 16 provinces |
| Village hall / senior center API | 50,609 | 14 | 2026-08-27 | PASS, all 51 pages |

Both statistical CSVs expose individual ages 0–109 and a 110+ column for each
sex. The transformation calculates 65+, 75+, and 80+ by summing observed age
columns. It fails if a required age column is absent.

## Pilot joins

| Check | Result |
|---|---:|
| Hongseong-gun Janggok-myeon legal-ri areas | 16 |
| Population ↔ single-household exact-code join | 16 / 16 (100%) |
| Facility records selected from the pilot | 66 |
| Selected facility coordinates available | 66 / 66 (100%) |
| Kakao reverse-geocode exact-code matches | 66 / 66 (100%) |
| Pilot areas with population, household, and facility | 16 / 16 (100%) |
| Duplicate population / household legal codes | 0 / 0 |
| Distinct facility coordinates / records sharing a coordinate | 39 / 27 |
| Facility address strings with one / ambiguous / no area-name match | 65 / 0 / 1 |

The legal code from coordinate reverse-geocoding is the canonical facility join.
Address-string matching is only a diagnostic; one address has no single text
match even though its coordinate resolves to the correct legal code. Multiple
facilities may share coordinates and remain separate source records.

## Important source limitation

The live population CSV named as a regional dataset contained one province only
(Chungcheongnam-do), while the single-household CSV contained 16 provinces.
There are 16,536 household legal codes without a population row in that pull.
Those codes are left unmatched, not imputed. This limits population-based
planning outside the observed coverage. Re-check the source before expanding
the pilot.

## Rebuild

```sh
uv run python scripts/api_smoke_test.py
uv run python scripts/build_demo_data.py
```

The rebuild requires data.go.kr and Kakao settings in `.env`. It prints status
summaries only and does not persist raw source rows or facility contact fields.
