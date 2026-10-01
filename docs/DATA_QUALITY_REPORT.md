# Data quality report

This report summarizes the live public-data pull and source-page recheck made
on 2026-10-01. Machine-readable values are in
`artifacts/data_quality_report.json`; per-source pull results are in
`artifacts/api_smoke_report.json`.

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

The V2 pilot fixture enables three Chungcheongnam-do towns. Every enabled
service area has an exact 10-digit population/household code join and at least
one facility anchor whose Kakao reverse-geocoded code matches the area.

| Region | Service areas | Population ↔ household exact-code join | Anchored areas | Full source joins |
|---|---:|---:|---:|---:|
| Hongseong-gun Janggok-myeon | 16 | 16 / 16 (100%) | 16 / 16 | 16 / 16 (100%) |
| Buyeo-gun Buyeo-eup | 22 | 22 / 22 (100%) | 22 / 22 | 22 / 22 (100%) |
| Asan-si Eumbong-myeon | 16 | 16 / 16 (100%) | 16 / 16 | 16 / 16 (100%) |
| **Total** | **54** | **54 / 54 (100%)** | **54 / 54** | **54 / 54 (100%)** |

Across the enabled pilots, 158 source facility records support the area
anchors. Some records share coordinates; the anchor is not a claim that each
facility serves every household in its legal-ri area. There are no duplicate
population or household legal codes in the selected joins. Free-text address
matching remains diagnostic only; the canonical facility join uses coordinate
reverse-geocoding.

The legal code from coordinate reverse-geocoding is the canonical facility join.
Address-string matching is only a diagnostic; one address has no single text
match even though its coordinate resolves to the correct legal code. Multiple
facilities may share coordinates and remain separate source records.

## Important source limitation

The official [population dataset page](https://www.data.go.kr/data/15099158/fileData.do)
describes legal-dong population by age and sex. On 2026-10-01, the page had one
linked CSV attachment; its successful download parsed to 2,088 rows and 231
columns, all in Chungcheongnam-do. No alternate regional attachment was linked,
and the linked file downloaded successfully. This is evidence of the current
catalog publication's contents; it does not establish why the publisher's
single file is province-limited or what files may exist elsewhere. The
single-household CSV contains 16 provinces. Its 16,536 codes without population
rows remain unmatched and unimputed. All 54 enabled service areas across the
three pilots join exactly; regions outside observed population coverage remain
disabled until another population source is verified.

The route matrix stores 942 directed inter-area Kakao routes (240, 462, and 240
per town respectively) plus one exact self-route per area. Matrix construction
is town-scoped and does not request cross-town routes. The cache is local
ignored state and must be rebuilt or supplied as persistent state in a fresh
deployment.

## Rebuild

```sh
uv run python scripts/api_smoke_test.py
uv run python scripts/build_demo_data.py
```

The rebuild requires data.go.kr and Kakao settings in `.env`. It prints status
summaries only and does not persist raw source rows or facility contact fields.
