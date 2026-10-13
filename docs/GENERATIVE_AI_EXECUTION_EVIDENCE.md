# Generative AI execution evidence

## Verdict

**`REAL_MODEL_NOT_VERIFIED` / `MODEL_CALL_BLOCKED`.** No Gemini request was sent. The active user policy forbids extra usage and overage, and the task does not provide a verified no-cost invocation entitlement. No credential was read, copied, or written to an artifact. This report therefore makes no claim of live Gemini inference.

## Product role and code path

The generative-AI path structures free-text demand notes into a `StructuredDemand` draft (`backend/demand.py`, called by `POST /api/demand/structure` in `backend/main.py`). The code default model is `gemini-3.5-flash-lite`, overridable by `GEMINI_MODEL`; the model actually configured in Render was not observable. The AI draft is subject to schema validation and human review. Evidence sufficiency and follow-up policy are handled separately. OR-Tools CP-SAT is used for schedule/resource optimization, not for note interpretation. A person reviews and approves demand/policy decisions.

The public-demo allowlist continues to block demand structure/draft endpoints and pilot/feedback routes. No anonymous real-time inference endpoint was enabled.

## Synthetic fallback check

The following synthetic note was processed locally with the deterministic fallback (`use_remote=False`):

> 마을회관에 방문한 주민이 겨울철 현관문 수리를 요청했다. 이동이 어려워 방문 서비스를 원하며, 수요일은 병원 방문 때문에 어렵다고 말했다.

The fallback produced a Pydantic-valid `StructuredDemand` with service `home_repair` and season `winter`, but did not extract the Wednesday exclusion, the requested visit preference, or the mobility constraint. It returned no frequency, `confidence=null`, `needs_followup_survey=false`, and method `deterministic_fallback`. This is a concrete extraction limitation, not evidence of Gemini behavior or general accuracy.

A separate synthetic note (“겨울철 현관문 수리 서비스를 월 2회 요청합니다. 수요일을 선호하며 병원 방문일은 제외해 주세요.”) also passed schema validation through the fallback and produced `home_repair`, winter, 2/month, preferred Wednesday, and a generic hospital-visit-day exclusion. This deterministic rule-path check does not establish model inference.

## Validation and limits

- Pydantic schema round-trip: `EXEC PASS` for the fallback objects described above.
- Real Gemini request/response/model ID/latency: `SKIP` under the no-extra-usage policy; no model call count beyond zero.
- Hallucination or model extraction accuracy: `NOT_VERIFIABLE`; no real inference sample was obtained. The single fallback miss above should be retained as a known limitation.
- Private data: synthetic text only. No resident data, key, token, or raw authentication header was used in the artifact.
- External inference cost: zero for this run because no request was sent. No claim is made about cost for a future model call.
- Human review: remains required before a structured draft is treated as final demand.
- Field accuracy: not evaluated. AI confidence is not an empirical accuracy estimate.

## Evidence for a presentation

The source path and deterministic fallback can be shown as a clearly labeled static/code-path demonstration. It must be labeled `SYNTHETIC INPUT` and `DETERMINISTIC FALLBACK`, with `REAL_MODEL_NOT_VERIFIED`; it must not be presented as a live Gemini result. A real-inference screen/video and model identifier remain outstanding and require a separately authorized, cost-bounded invocation environment.
