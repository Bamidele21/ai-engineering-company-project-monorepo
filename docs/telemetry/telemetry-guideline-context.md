Your company already has an inventory management system in production: a FastAPI backend with authentication, a relational data model in Supabase, and a non-negotiable business rule — stock cannot be modified directly, only through inbound and outbound orders traceable to a user. The system works. But the operations team has no idea what is happening inside it.

The management team has filed an **RFI** with the technology team: they want to know whether the system can generate actionable business information — and not just about the inventory, but about any part of the application a user or internal process touches. Your tech lead has assigned you the task of responding to that RFI with a **Telemetry Plan**: a technical document that identifies, as exhaustively as possible, what data is worth capturing today — and what could be valuable tomorrow, even if you don't have the exact business question it answers yet — before writing a single line of instrumentation.
# 💻 What You Need to Do

### Phase 1 — Exhaustive Catalogue of Data Opportunities

- [ ] Review your `company-BRIEFING.md` and identify the **mandatory metrics** your company requires from day one. These are a floor, not a ceiling — they must be in your plan no matter what.
- [ ] Map the **inventory management flow** in your application: from when an authenticated user accesses the system to when they complete an inbound or outbound order. Identify at least **5 instrumentation points** in that flow — including direct stock modification attempts (which the system rejects), failed validations, and minimum threshold activations.
- [ ] Explore, without capping yourself at a minimum count, other backoffice sections that can also provide valuable data: authentication (login attempts, expired sessions, credential failures), performance (API response times, load times), uncaught frontend errors, and navigation (which sections operators visit most, which flows get abandoned). The goal is a broad catalogue, not a minimum list checked off as a formality.
- [ ] For each opportunity you identify, complete the sentence: _"We capture `[event_type]` because we need to know `[hypothesis]`, which allows us to make the decision `[decision]`."_ If you cannot complete it, discard the point.
- [ ] Classify every event in your catalogue into two groups: **mandatory** (comes from your BRIEFING) or **identified opportunity** (you proposed it). This gives the team visibility into what is baseline and what is exploration.

⚠️ **IMPORTANT:** The mandatory metrics, entities, and identifiers in your plan must match exactly what your `company-BRIEFING.md` specifies. In addition, the catalogue of additional opportunities is expected to be broad and well-grounded — a plan that only covers the mandatory minimum, without exploring the rest of the application, will not be accepted.

### Phase 2 — Event Envelope Design

- [ ] Define the **standard Event Envelope** your company will use: the mandatory fields every event must include (`eventId`, `timestamp` in ISO 8601, `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId` for correlation, and `properties` for event-specific payload).
- [ ] Design the complete schema for **all the mandatory metrics from your BRIEFING**, plus **at least 8 additional events** from your catalogue, covering at least 3 distinct categories (for example: business/inventory, authentication, performance, errors, navigation). Each `event_type` must follow the `entity_action` taxonomy with consistent verbs (e.g. `inbound_order_created`, `stock_threshold_triggered`, `direct_stock_edit_rejected`, `session_expired`, `api_latency_recorded`).
- [ ] For each event, define a **property allowlist**: an explicit list of the permitted keys for that event. Nothing outside the allowlist should be included — this prevents accidental data leakage.
- [ ] For each event, specify: `event_type`, description, `properties` (name, type, required/optional, description), and whether it contains sensitive data or PII — in which case document how it is anonymised or sanitised before the event is emitted.
- [ ] Export the schemas to the `event-schemas.json` file with a validatable structure (you may use JSON Schema draft-07 or a documented custom structure).

### Phase 3 — Delivery Strategy

- [ ] For each event designed, decide and justify whether it should be processed as **stream** (real time) or **batch** (periodic batches). The justification must be based on the urgency of the decision it feeds or the operational need to detect it quickly — not on technical preference.
- [ ] Document the **throttle/debounce** strategy for high-frequency events (if any exist in your design).
- [ ] Write a **risks and exclusions** section in the plan: events you considered and discarded, and why; data that will not be captured for privacy or cost reasons.

---

## ✅ What We Will Evaluate

- [ ] Every mandatory metric from `company-BRIEFING.md` is present and correctly identified in the plan
- [ ] The plan covers both **technical** opportunities (errors, performance, authentication, navigation) and **business** ones, broadly — not limited to a minimum count checked off as a formality
- [ ] Every event has a hypothesis and a business or operational decision that justifies it — no "just in case" events
- [ ] The Event Envelope is consistent across all events and contains at least: `eventId`, `timestamp` (ISO 8601), `sessionId`, `userId`, `event_type` in `entity_action` format, `schemaVersion`, `requestId`, and `properties`
- [ ] Every event has a documented **property allowlist** — only explicitly permitted keys
- [ ] The `event-schemas.json` file is valid and the schemas are consistent with the Markdown plan
- [ ] The stream/batch decision is justified by business or operational urgency, not technical preference
- [ ] Sensitive data or PII is identified and documented with its anonymisation or sanitisation strategy
- [ ] The risks and exclusions section demonstrates critical thinking: events were discarded for a reason
- [ ] The plan is precise enough for another developer to instrument it without needing clarification
