# PII Inventory

This inventory covers the prototype database, pilot import, API response, audit,
and export paths. It is not a legal retention schedule or a complete
anonymization guarantee. The repository has no automated retention/deletion
policy. The pilot organization must set retention and access rules before
loading real resident or provider information.

| Data | Location | Purpose | Retention assumption | Exported? | Logged? | Risk |
|---|---|---|---|---|---|---|
| Resident name, phone, email, resident ID, address | Prohibited in pilot CSV fields and notes; common patterns are masked before persistence | Not required for planning | Do not collect; if detected in preview, verify the redacted value and remove source file under agency policy | No in default plan/feedback exports; masked import error CSV may include a row | No raw row is written to audit event details; standard server logs must be checked in the deployment | High; pattern redaction is incomplete |
| Demand observation note | `pilot_import_rows`, `pilot_import_records`, `pilot_promoted_records.payload_json` | Minimal de-identified provenance context | Database record retained until operator-managed deletion; no TTL | Error CSV only after best-effort redaction; not included in plan provenance snapshot | Audit contains batch/row fingerprint and source metadata, not note | High if free text includes indirect identifiers |
| Survey note | Pilot import tables and promoted payload; legacy `surveys.free_text_note` | Survey method/context; response count is not converted to demand | Same as source dataset; no automatic expiry | Not included in standard plan/CSV exports; error export may contain redacted value | No raw note in plan audit events | High; free text can identify a household |
| Resident feedback description, requested change, claim | `resident_feedback.description`, `requested_change`, `claim_json`; common patterns redacted on intake | Review and conflict/duplicate resolution | No automatic expiry | Feedback export omits contact, attachments, and reviewer notes; description/claim may still contain sensitive free text | Audit events record status and ids only; no raw description in event details; pilot link stores only feedback ID and minimal status/provenance | High; linkage does not make the claim verified demand |
| Resident contact text | Separate `resident_feedback_contacts.contact_text` table; not returned in list/export endpoints | Optional follow-up | Agency must define access and deletion; no TTL | Excluded from default exports | Must not be added to logs/audit; endpoint access is not real authentication in this prototype | Very high |
| Provider public business address | Pilot organization payload and provider directory entries | Verify public business geography/source identity | Retain with source dataset and remove when reuse basis expires | Not included in pilot plan provenance summaries or standard assignment exports | No address in pilot audit event details | Medium; reject private residence addresses |
| Provider contact | Pilot schema stores only `public_contact_available` boolean; it does not accept a contact value | Indicate whether an official contact exists | Not applicable | No value to export | No value to log | Low for boolean; very high if future schema adds the value |
| Provider service description and mapping note | Promoted provider service payload and `pilot_service_mapping_reviews.note` | Human mapping review | Retain with context; no TTL | Mapping decision/provenance may appear in plan snapshot; raw description/note is not copied to the plan source summary | Audit records decision metadata only | Medium; redact common PII patterns, review source text |
| Execution cancel reason | `pilot_execution_logs.cancel_reason` and promoted import payload | Operational outcome explanation | Retain with execution batch under agency policy | Not included in default plan provenance/export | Import audit does not include reason text | Medium to high; contact/household text is prohibited and common PII patterns are masked |
| Scenario assumption reason and plan change comment | `pilot_scenario_assumptions.reason`, `pilot_plan_change_requests.comment`, `pilot_plans.change_reason` | Explain operational/scenario decisions | Retain as immutable plan lineage; no TTL | Assumption history is visible in plan detail; comments are not in default exports | Audit event records transition, not comment | Medium; keep comments operational and non-identifying |
| Context name, provider organization name, IDs, source record references | `pilot_contexts`, promoted records, plan JSON | Dataset and source reproducibility | Retain with context; no TTL | Plan detail may include organization names and opaque source IDs | Audit may include context and plan IDs | Low to medium; do not use personal names as identifiers |
| API secrets | Server environment/config only; not an accepted import field | Provider API authentication | Secret manager/environment policy | Never | Never | Very high; do not send secrets in CSV or error reports |

## Current safeguards and gaps

- Import validation returns issue codes and generic field-specific messages, not
  raw row contents. Row previews and failed-row CSVs contain normalized values
  after best-effort masking.
- Import and plan audit details use context IDs, batch IDs, fingerprints,
  provenance, and state transitions; they do not include resident free text or
  contact values.
- Resident-feedback default exports omit contact, attachment metadata, and
  reviewer free text. Pilot plans may include linked feedback IDs, categories,
  status, dates, area code, and conflict type/status; they omit descriptions,
  requested changes, claims, and contact values.
- PII masking catches common Korean phone, resident-ID, email, and honorific
  name patterns. It does not detect all names, addresses, rare identifiers, or
  sensitive facts. A human source-data review remains mandatory.
- The prototype has no authenticated staff roles, field-level access control,
  encryption-at-rest configuration contract, automatic retention schedule, or
  deletion workflow. A staff-only label is not an authorization boundary.
- Before field data use, the agency must approve lawful purpose, minimization,
  consent/notice, roles, retention/deletion, breach response, export handling,
  and the permitted source/license basis.
