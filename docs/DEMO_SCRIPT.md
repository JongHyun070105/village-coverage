# 2–5 minute demo script

Target length: about 3 minutes. Use the local seeded pilot; narrate that service
requests, supply schedules, prices, and beneficiary multipliers are simulated.

1. **Problem (0:00–0:25)** — Ask: “기록이 적으면 정말 수요가 없는 걸까요?”
   Show the 16 legal-ri areas and explain that the public population data and
   simulated request data have separate provenance.
2. **Request-count baseline (0:25–0:55)** — Show the result comparison: at
   5,000,000 KRW the naive request-count baseline serves three areas and none
   of the eight survey-required areas.
3. **Low-data protection (0:55–1:20)** — Select a `조사 필요` marker. Show its
   observation count, survey status, and recommendation. Explain that sparse
   records do not become zero demand.
4. **AI structuring (1:20–1:50)** — Paste the sample winter laundry request.
   Show service, season, frequency, excluded day, and human-review status.
   Point out that AI structures a note and does not generate a route.
5. **Policy choices (1:50–2:30)** — Compare efficiency, balanced, and minimum
   guarantee. In the balanced result, three of eight survey-required areas are
   covered in this simulation. The minimum scenario shows uncovered areas if
   the budget does not meet the guarantee.
6. **Budget what-if (2:30–3:00)** — Move the monthly slider to 4,000,000 KRW:
   the minimum guarantee leaves two areas uncovered and shows a 608,959 KRW
   gap. Move to 5,000,000 KRW: all 16 simulated areas meet one monthly service
   at the modeled 4,608,959 KRW requirement.
7. **Close (3:00–3:15)** — Emphasize that the prototype makes the equity cost
   visible; real resident surveys, provider quotations, and field validation
   are required before operational adoption.

Do not show `.env`, secret settings, facility contact fields, or real resident
records in the recording.
