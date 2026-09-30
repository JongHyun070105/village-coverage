# Pilot region selection

## Decision

The demonstration uses **Hongseong-gun Janggok-myeon**, represented as 16
official legal-ri service areas. The choice follows observable source
completeness instead of a preselected village name.

## Candidate comparison

All three candidates are in Chungcheongnam-do, the only province present in the
live population CSV pull. Counts below are from the live public-data join.

| Candidate | Legal-ri areas | Population | Age 65+ | Age 65+ share | Single-person households | Single-person HH age 65+ | Facilities with coordinates | Area name matches |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hongseong-gun Hongdong-myeon | 14 | 3,180 | 1,536 | 48.3% | 759 | 455 | 67 / 67 | 14 / 14 |
| **Hongseong-gun Janggok-myeon** | **16** | **2,631** | **1,486** | **56.5%** | **773** | **518** | **66 / 66** | **16 / 16** |
| Boryeong-si Misan-myeon | 14 | 1,590 | 937 | 58.9% | 552 | 374 | 21 / 21 | 13 / 14 |

Janggok-myeon has the largest candidate area count, a complete facility-to-area
join, full coordinate coverage, and the highest older-population share among
the fully name-matched candidates. Its older population and single-household
counts also give the dashboard enough variation to demonstrate the policy
trade-off.

## Join and map interpretation

Population and household rows join on an exact 10-digit legal code. All 66
selected facilities have coordinates and a Kakao reverse-geocoded legal code;
those codes cover all 16 service areas. A facility coordinate is an anchor for
its legal area, not a claim that the point represents every household or every
administrative village within that area.

## Road network

The selected pilot has a directed Kakao Mobility road matrix for all 240
inter-area origin/destination pairs, plus 16 exact self-routes. It was built
from live road results and is cached in the local ignored SQLite database.
See `artifacts/travel_matrix_report.json` for cache coverage and retrieval
time. The matrix must be rebuilt or supplied as persistent volume state in a
fresh deployment.
