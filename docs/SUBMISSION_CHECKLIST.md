# Competition submission checklist

This checklist follows the supplied competition notice and the supplied
four-page result-report template. Re-check the organizer's current notice before
submission because deadlines and upload rules can change.

## Product and evidence

- [x] Korean working prototype with budget comparison and four planning scenarios.
- [x] Low-data areas remain survey-required instead of being treated as no
  demand.
- [x] Real public-data provenance is separated from synthetic operating data.
- [x] API, source schema, pilot join, route-cache, and experiment evidence are
  recorded in `artifacts/` and `docs/`.
- [ ] Replace simulated service demand, provider capacity, and prices with
  documented field evidence before making real service recommendations.
- [ ] Recheck public-data and Kakao usage terms for the intended public demo,
  cached route output, and competition deliverables.

## Final report structure

Use the supplied four-page template:

1. **AI 기술명** — state the project/technology name.
2. **아이디어명 / 기술요약** — identify the idea and summarize it.
3. **최종목표 / 개발 내용 및 결과** — explain the goal, implemented product,
   exploration method, measured joins, API validation, and simulated experiment
   results.
4. **개발 과정에서 애로점 / 기대효과** — disclose source-coverage limits,
   synthetic-data limits, remaining risks, and expected value to local planners.

The template notes that the results report should be about four pages. Avoid
claiming measured field outcomes where only simulated results exist.

## Before uploading

- [ ] Confirm the competition's Pre-R&D scope, eligibility, naming rules, and
  submission deadline from the latest organizer notice. The supplied notice
  stated 2026-10-31 24:00.
- [ ] Complete and sign the organizer-required application/report forms using
  the applicant's own verified information. Do not commit those personal
  documents or identifiers to this repository.
- [ ] Prepare an accessible demo URL or executable package and verify it from a
  fresh browser session.
- [ ] Record a 5–7 minute demo video using `DEMO_WALKTHROUGH.md`; remove credentials,
  private settings, and resident identifiers from all footage.
- [ ] Re-run tests, frontend lint/typecheck/build, and secret-history checks on
  the final submission commit.
- [ ] Provide links to the public repository and demo, with concise setup and
  limitation notes.

Use [SUBMISSION_EVIDENCE_INDEX.md](SUBMISSION_EVIDENCE_INDEX.md) to select
claims and preserve each artifact's `SIMULATED`, `FIELD_VALIDATION_PENDING`,
and `UNKNOWN` labels. It is an evidence index, not the final submission report.
