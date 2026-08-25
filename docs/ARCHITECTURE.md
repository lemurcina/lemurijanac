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

## Opportunity graph domain extension points
- Current implementation lives in `shadow_market_desk/opportunity_graph.py` and is transport/UI isolated.
- `OpportunityGraphRepository` is the persistence boundary; `InMemoryOpportunityGraphRepository` is a deterministic reference implementation.
- Postgres extension should map:
  - entities/signals/needs/opportunities to core tables
  - relationships (`relation`, `confidence`, `evidence_ids`) to join/edge tables
  - evidence and merge/split lineage to append-only provenance/event tables
- Merge and split operations must preserve evidence links and lineage relationships; no provenance deletion.

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
