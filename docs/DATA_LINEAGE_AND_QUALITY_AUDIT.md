# Data lineage and quality audit

Audit date: 2026-10-08. This is a repository snapshot audit. It did not fetch
new external datasets or use API keys. Values below are tied to the checked-in
source snapshots and summaries; current live availability is not inferred.

## Source inventory and interpretation

| Source | Classification and scope | Snapshot / schema evidence | Transformation and current use | Quality / limitation |
|---|---|---|---|---|
| Legal-dong registry (`15077871`, `StanReginCd.getStanReginCdList`) | REAL PUBLIC DATA; national legal-area code lookup | `artifacts/data_quality_report.json`: 20,560 records, 13 columns in the recorded pull | Canonical 10-digit key for exact fixture joins | Current audit checks only recorded pull and 54 enabled pilot areas; complete jurisdiction-wide registry validation for arbitrary uploaded codes is not established. |
| Age/sex population (`15099158`) | REAL PUBLIC DATA; official source title is national | `2026-08-31`; 2,088 rows, 231 columns; source pull reports one province (Chungcheongnam-do) | Age bands (65+, 75+, 80+) are summed from explicit age columns; only 54 area aggregates enter the demo fixture | The source is province-limited despite its national title. The 16 pilot households with unmatched population codes are not imputed. It does not provide village-level service demand. |
| Single-person households (`15099160`) | REAL PUBLIC DATA; 16-province public file | `2026-08-31`; 18,624 rows, 231 columns | Exact legal-code join for the 54 enabled areas | 16,536 source codes have no matching population row. No values are manufactured for them. Household aggregates are not service requests. |
| Village halls / senior centers (`15114136`) | REAL PUBLIC DATA; nationwide public facility source | Latest update `2026-08-27`; 50,609 rows; 158 candidate records in enabled pilot anchors | Coordinates are reverse-geocoded and joined by exact legal code; facility counts/anchors flow into the minimized `data/demo.json` | 28 records share coordinates (130 distinct points). One facility coordinate anchor does not prove catchment or service availability. Facility names/contact fields are not retained. |
| Licensed Buyeo facility detail (`15114136:uddi:d4c76add-7771-4c45-a057-e30472b0dae3`) | REAL PUBLIC DATA; only the audited detail source | Reference date `2026-08-26`; 51 minimized rows across 22 areas; unrestricted reuse is recorded in the existing audit | Type, status, coordinates, construction date, area, and date only | Does not cover the other two towns at the same detail level. The prior facility snapshot and transformation remain unchanged. |
| KREI R 2025-23, table 4-8 | EXTERNAL PRIOR; national rural survey percentages | Published 2025-12; sample size not stated in the cited table | Reference values for broad rural service context and model discussion | Not a village-level count, demand rate, or forecast calibration. Multiplying a national percentage by one village's population is not validated. |
| KOSIS `G_14 / 117_A_003` and configured tables | EXTERNAL PRIOR / EXTERNAL CONTEXT; nationwide household social-service survey | Snapshot retrieved `2026-10-03`; 8 configured pulls in `artifacts/kosis_snapshot.json` | Context on social-service needs/usage only | Not rural village demand. Fee-burden questions do not establish willingness to pay; matching desired-time/WTP tables were not found in the recorded catalog search. |
| HomeDoctor (`15120958`) | EXTERNAL PRIOR; public-rental-housing operations | Snapshot retrieved `2026-10-03T05:32:25Z`; dataset through `2026-06`; 22,058 rows, 54 contiguous months from 2022-01 | Operational-volume variation, forecast-method and load scenarios only | Not rural demand or village service visits. 2,905 rows mismatch the reported total and category sum. Totals: 2,811,630; category sum: 2,791,503; difference: 20,127. Original totals/categories are preserved. |
| Self-support enterprise directory (`15091502`) | OFFICIAL DIRECTORY; nationwide organization listing | Reference `2025-12-31`; 977 parsed rows and 977 portal rows; audit downloaded `2026-10-05` | Candidate discovery after redacting representative names | No current operation, service capacity, participation, contract, staffing, or price is established. 14 duplicate candidates are review flags, not automatically deleted rows. |
| Village enterprise directory (`15080745`) | OFFICIAL DIRECTORY; nationwide organization listing | Reference `2025-12-31`; 1,727 parsed rows versus portal metadata 1,726; audit downloaded `2026-10-05` | Candidate discovery after excluding business-registration field | One-row discrepancy is retained and flagged; 10 duplicate candidates are review flags, not deletion instructions. Directory presence is not availability. |
| Synthetic fixture and provider profiles | SCENARIO ASSUMPTION / SIMULATED | `data/demo.json`, deterministic helpers in `backend/simulation.py`, and route model fingerprints in experiment outputs | Seeded service demand, provider availability/capacity, prices, and straight-line route estimates for reproducible engineering tests | Not an observation, calibrated prediction, road route, real provider commitment, or expected service outcome. |
| Local observation / pilot CSV assumptions | LOCAL OBSERVATION or SCENARIO ASSUMPTION only when supplied with provenance | No real authority/resident input was used in this audit | Existing import workflow retains source, context, row fingerprint, and explicit assumption fields | The 2026-10-08 experiment did not add pilot observations. PII and authority data remain out of scope. |

## Rechecked known data-quality issues

1. **HomeDoctor total/category mismatch:** the preserved summary has 22,058 rows
   and 2,905 mismatch rows. Re-summing the 54 monthly aggregate rows gives
   total `2,811,630` versus category total `2,791,503`, a difference of
   `20,127`. The raw-source hash is
   `819a0e94b297996988ea2a4d432962e6bba5a714f1d7c55d0f850c2b91c15684`.
   No total was “corrected” and no record was removed.
2. **Village-enterprise row count:** the ingestion summary preserves
   `1,727` parsed rows against portal metadata `1,726`; status remains a
   warning. The provider source audit instructs retaining the original rows
   until the discrepancy is investigated.
3. **Legal-code registry coverage:** the recorded pull has 20,560 codes and
   the 54 enabled areas join exactly, but user-uploaded codes are not all
   validated against a complete current registry. Keep arbitrary jurisdiction
   imports gated for responsible-authority validation.
4. **Duplicate candidates:** 14 self-support and 10 village-enterprise
   duplicate candidates are not confirmed duplicates. Preserve source rows;
   do not deduplicate by name alone.

## Required checks if local authority data are added

- Confirm owner, lawful basis, source system, license/redistribution terms,
  retrieval date, geographic and temporal scope, schema, and refresh cadence.
- Preserve raw source and hash separately from normalized rows; document every
  excluded field, duplicate rule, code normalization, join rate, and missingness
  decision.
- Validate all legal-area codes against the responsible authority's current
  registry; report unmatched and ambiguous rows without imputation.
- Keep observed demand, external prior, model estimate, and scenario assumption
  in separate fields. Never turn missing frequency into zero or claim directory
  presence as operational availability.
- Review PII minimization, access, retention, consent, and screen/export
  boundaries before accepting resident data.

## Conclusion

The 54-area synthetic/public fixture has exact recorded population-household
joins and exact reverse-geocode facility joins in the three configured pilot
regions. This does not validate the completeness of all Korean legal codes,
local service demand, local provider availability, forecast accuracy, or field
impact. The two known source count issues remain preserved and labeled. No raw
snapshot or existing SQLite evidence was modified by this audit.
