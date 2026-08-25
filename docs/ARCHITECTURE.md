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

## Chief revenue allocator behavior
- Allocates by expected gross profit per agent-hour, never by raw lead/email volume.
- Tracks strategy posterior expected value, sample count, uncertainty, and cooldown state.
- Reserves bounded exploration budget for sparse/high-uncertainty strategies while shifting the rest of capacity toward proven strategies.
- Enforces a capital-at-risk cap during allocation.
- Records outcomes (`WON`, `LOST`, `NO_RESPONSE`, `INVALID`) with realized gross profit and updates kill/pause or reactivation state.
- Emits plain-language explanations for every reallocation decision.

### Example daily strategy table

| strategy_id | samples | posterior_expected_value | expected_gross_profit_per_agent_hour | uncertainty | cooldown_rounds_remaining |
| --- | ---: | ---: | ---: | ---: | ---: |
| permits-ti | 34 | 182.40 | 96.00 | 0.0730 | 0 |
| business-openings | 12 | 41.75 | 28.50 | 0.1134 | 0 |
| surplus-assets | 7 | -14.10 | -8.80 | 0.1562 | 1 |
