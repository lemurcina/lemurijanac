# Architecture

## Services
- `ingest`: source adapters -> normalized Signal
- `verify`: source/date/entity validation and evidence ledger
- `infer`: signal -> predicted Need candidates
- `price`: vendor cost / sell-price ranges / margin
- `score`: urgency, confidence, buyer intent, margin, competition, fulfillment ease
- `graph`: entity-signal-need-vendor-buyer relationships
- `allocator`: expected-value strategy allocation
- `crm`: outreach and negotiation state machine
- `policy`: compliance, spend and channel gates
- `api`: opportunities, strategies, outcomes, health
- `ui`: operator dashboard

## Event model
Events are append-only. Derived state can be rebuilt from events.

Core event types:
- SIGNAL_DISCOVERED
- SIGNAL_VERIFIED
- NEED_INFERRED
- OPPORTUNITY_SCORED
- OFFER_CREATED
- CONTACT_QUEUED
- CONTACTED
- RESPONSE_RECEIVED
- NEGOTIATION_UPDATED
- DEAL_WON
- DEAL_LOST
- STRATEGY_REALLOCATED

## Evidence rule
Every material claim must preserve source URL/id, observed timestamp, extraction method and confidence. Guesses are predictions, never facts.

## Initial deployment
Python service + Postgres. Scheduled collectors run independently. FastAPI exposes a read/write control plane. A minimal dashboard reads the API. Everything must run locally with synthetic fixtures before any live integration.

## Adding a new ingestion adapter
1. Create a `SignalAdapter` implementation under `shadow_market_desk/ingestion/adapters`.
2. Define deterministic normalization in `normalize_record` and generate a stable `dedup_key`.
3. Populate `SourceEvidence` with `source_url`, `source_record_id`, raw metadata and observed timestamps so every `Signal` is traceable.
4. Keep network access injectable via a `SourceClient` so tests can run on synthetic fixtures.
5. Add unit tests for valid normalization, duplicate handling, malformed records, and source fetch failures.
