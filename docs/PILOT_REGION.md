# Pilot region coverage

## Decision

The default region remains **Hongseong-gun Janggok-myeon**. Phase J adds two
Chungcheongnam-do pilots, Buyeo-eup and Eumbong-myeon, after checking population
and household joins by exact 10-digit legal code and resolving every selected
service-area facility anchor to its legal code with Kakao reverse geocoding.
The current fixture contains 54 legal-ri service areas across the three towns.

## Verified regional snapshots

Values below are aggregates from the live public pull dated 2026-10-01. Facility
records and service-area anchors are separate measures: several public facility
records can share one coordinate, and an anchor represents an area rather than
every household in it.

| Region | Areas | Population | Age 65+ | Age 65+ share | Single-person households | Single-person HH age 65+ | Facility records | Anchored areas | Exact source joins |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Hongseong-gun Janggok-myeon | 16 | 2,631 | 1,486 | 56.5% | 773 | 518 | 66 | 16 / 16 | 100% |
| Buyeo-gun Buyeo-eup | 22 | 17,204 | 6,142 | 35.7% | 4,337 | 1,997 | 51 | 22 / 22 | 100% |
| Asan-si Eumbong-myeon | 16 | 22,923 | 3,585 | 15.6% | 4,913 | 988 | 41 | 16 / 16 | 100% |

No population is divided among legal-ri names by a ratio. The selected pilots
are enabled only when every area has an exact population row, exact household
row, facility record, and coordinate anchor. Detailed current counts and source
dates are in `artifacts/data_quality_report.json`.

## Join and provenance interpretation

Population and household records join on their exact legal code. Each selected
facility's coordinates are reverse-geocoded to the same region and service-area
code; free-text addresses are diagnostic only. The fixture stores area-level
counts and anchors, not facility names, addresses, phone numbers, or manager
fields.

Population, age counts, single-household counts, facility counts, and coordinates
are real public-source observations. Resident demand, survey history, provider
identity, availability, service prices, and schedules remain clearly marked
synthetic research inputs. The population CSV currently covers
Chungcheongnam-do only; no region outside its observed coverage is enabled.

## Road network

The directed Kakao Mobility cache contains 942 inter-area routes: 240 for
Janggok-myeon, 462 for Buyeo-eup, and 240 for Eumbong-myeon. Each region also
has one exact zero self-route per area. Routes are built only within a selected
town; no cross-town trips are requested or used by planning. The cache is in the
local ignored SQLite database. See `artifacts/travel_matrix_report.json` for
coverage and retrieval time; rebuild it or provide the cache as persistent state
in a fresh deployment.
