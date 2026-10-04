# Provider directory, fallback and reserve policy

Pilot decision-support only. Candidates are never contracts and nothing is auto-assigned.

## Source lifecycle (license first)
`DISCOVERED` (unregistered, not reviewed) -> `LICENSE_VERIFIED` (license known, not a supply
directory) -> `INGEST_ALLOWED` (license known and a supply-candidate source) or
`INGEST_BLOCKED` (license unclear or reuse not allowed). Only `INGEST_ALLOWED` sources can be
ingested; everything else is refused with a 422. An unclear license means no ingest.

Current source review (2026-10-04):

| Source | Scope and published contents | Reuse state | Directory decision |
|---|---|---|---|
| [DATA_GO_KR_15091502, Korea Self-Sufficiency Welfare Development Institute](https://www.data.go.kr/data/15091502/fileData.do) | Nationwide; 977 rows for 2025-12-31; region, organization name/type, address, representative, and broad industry | `이용허락범위 제한 없음` | `INGEST_ALLOWED`; retain only organization name, service hint, region and reference date |
| [DATA_GO_KR_15090110, Ministry of Employment and Labor social-enterprise list](https://www.data.go.kr/data/15090110/fileData.do) | Nationwide; active-list snapshot dated 2025-06-30; region, organization, business description, social-purpose type and service sector; representative is also present | `이용허락범위 제한 없음` | `INGEST_ALLOWED`; old snapshot needs current status confirmation |
| [DATA_GO_KR_15080745, Ministry of the Interior and Safety village-enterprise list](https://www.data.go.kr/data/15080745/fileData.do) | Nationwide; 1,726 rows at 2025-12-31; organization, location, industry and business description; annual update | `이용허락범위 제한 없음` | `INGEST_ALLOWED`; a listing is not proof of current operations or participation |
| [DATA_GO_KR_15155661, nationwide cooperative standard data](https://www.data.go.kr/data/15155661/standard.do) | Nationwide local-government records; service/operating attributes vary | License was not clear on the checked source page | `INGEST_BLOCKED` |
| [DATA_GO_KR_15064216, Buan-gun cooperative file](https://www.data.go.kr/data/15064216/fileData.do) | Buan-gun only; 57 rows; organization, establishment date and address, with no service category; one-time file | `이용허락범위 제한 없음` | `LICENSE_VERIFIED`; outside the three pilot regions and not enough to classify service, so do not ingest as provider candidates |

The three nationwide organization files have a documented open reuse field and are marked
`INGEST_ALLOWED`; no file has been ingested in this repository. The source registry retains
snapshot dates and limits. Representative names and telephone/contact fields are not stored.
The Buan-gun file is not Buyeo-gun and is kept out of the pilot directory. No current official
nationwide directory for housing-welfare centers or local service communities was identified
in this review; those remain `DISCOVERED` and blocked from ingestion until a source and reuse
terms are verified.

Directory existence, address and published service category can be real source attributes.
Availability, capacity, price, participation likelihood and minimum compensation stay
`SIMULATED` until organizations provide operating data. No organization is auto-assigned.

Ingest keeps only name, service hint, region and reference date. Phone, representative,
address and e-mail fields are dropped and counted.

## Real vs simulated badges
A directory hit only proves the organization exists in a public registry
(`REAL_DIRECTORY`). Availability, capacity and price badges stay `SIMULATED` until a provider
reports them. Existence badge is `REAL_DIRECTORY` only after a planner links a directory
entry to a provider.

## Fallback candidates
For each planned round the same hard constraints apply as for the primary: supported service,
availability window, travel limit, daily hours, monthly capacity, no double booking that day,
and for home repair a verified capability (unknown is excluded). Ranking is by estimated
total cost, then travel time, then provider id: SECONDARY then TERTIARY. Every candidate is
flagged `requires_provider_confirmation` and `auto_contract: false`.

## Reserve comparison
The planner chooses the reserve ratio (0, 5, 10 or 15 percent); the system and the AI never do.
- NO_RESERVE: plan with the full budget, a decline loses the provider's rounds.
- BUDGET_RESERVE: plan with (100 - r)% and re-plan with the full budget after a decline.
- PROVIDER_FALLBACK: plan with the full budget and move rounds to ranked fallbacks while the
  leftover budget (including freed cost) allows, including any minimum-compensation top-up.
- BOTH: reserve plan, fallback first, then a re-plan if rounds remain unrecovered; the better
  of the two outcomes is reported with its mechanism.
Each planned provider is declined alone; the report shows the worst case. It is a
SIMULATION of declines, not a forecast of provider behavior.

## Limits
Fallbacks assume one round per provider per day, a conservative simplification. Recovery by
re-plan is a full solve and does not preserve the original schedule for unaffected rounds.
