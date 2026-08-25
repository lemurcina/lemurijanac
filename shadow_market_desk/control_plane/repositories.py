from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import islice
from uuid import uuid4

from .models import (
    Allocation,
    AuditEvent,
    ChannelPolicy,
    ChannelPolicyStatus,
    Opportunity,
    OpportunityStatus,
    Outcome,
    OutcomeStatus,
    Signal,
    Strategy,
    StrategyStatus,
)


def paginate[T](items: list[T], *, offset: int, limit: int) -> list[T]:
    return list(islice(items, offset, offset + limit))


class InMemorySignalRepository:
    def __init__(self, signals: Iterable[Signal]) -> None:
        self._signals = list(signals)

    def list(self, *, offset: int, limit: int, min_confidence: float | None) -> tuple[list[Signal], int]:
        filtered = self._signals
        if min_confidence is not None:
            filtered = [signal for signal in filtered if signal.confidence >= min_confidence]
        return paginate(filtered, offset=offset, limit=limit), len(filtered)


class InMemoryOpportunityRepository:
    def __init__(self, opportunities: Iterable[Opportunity]) -> None:
        self._opportunities = list(opportunities)

    def list(
        self,
        *,
        offset: int,
        limit: int,
        status: OpportunityStatus | None,
        strategy_id: str | None,
    ) -> tuple[list[Opportunity], int]:
        filtered = self._opportunities
        if status is not None:
            filtered = [opportunity for opportunity in filtered if opportunity.status == status]
        if strategy_id is not None:
            filtered = [opportunity for opportunity in filtered if opportunity.strategy_id == strategy_id]
        return paginate(filtered, offset=offset, limit=limit), len(filtered)


class InMemoryStrategyRepository:
    def __init__(self, strategies: Iterable[Strategy]) -> None:
        self._strategies = {strategy.id: strategy for strategy in strategies}

    def list(self, *, offset: int, limit: int, status: StrategyStatus | None) -> tuple[list[Strategy], int]:
        strategies = list(self._strategies.values())
        if status is not None:
            strategies = [strategy for strategy in strategies if strategy.status == status]
        return paginate(strategies, offset=offset, limit=limit), len(strategies)

    def get(self, strategy_id: str) -> Strategy | None:
        return self._strategies.get(strategy_id)

    def upsert(self, strategy: Strategy) -> Strategy:
        self._strategies[strategy.id] = strategy
        return strategy


class InMemoryAllocationRepository:
    def __init__(self, allocations: Iterable[Allocation]) -> None:
        self._allocations = list(allocations)

    def list(self, *, offset: int, limit: int, strategy_id: str | None) -> tuple[list[Allocation], int]:
        filtered = self._allocations
        if strategy_id is not None:
            filtered = [allocation for allocation in filtered if allocation.strategy_id == strategy_id]
        return paginate(filtered, offset=offset, limit=limit), len(filtered)


class InMemoryOutcomeRepository:
    def __init__(self, outcomes: Iterable[Outcome]) -> None:
        self._outcomes = {outcome.id: outcome for outcome in outcomes}

    def list(self, *, offset: int, limit: int, status: OutcomeStatus | None) -> tuple[list[Outcome], int]:
        outcomes = list(self._outcomes.values())
        if status is not None:
            outcomes = [outcome for outcome in outcomes if outcome.status == status]
        return paginate(outcomes, offset=offset, limit=limit), len(outcomes)

    def get(self, outcome_id: str) -> Outcome | None:
        return self._outcomes.get(outcome_id)

    def upsert(self, outcome: Outcome) -> Outcome:
        self._outcomes[outcome.id] = outcome
        return outcome


class InMemoryChannelPolicyRepository:
    def __init__(self, policies: Iterable[ChannelPolicy]) -> None:
        self._policies = {policy.id: policy for policy in policies}

    def get(self, policy_id: str) -> ChannelPolicy | None:
        return self._policies.get(policy_id)

    def upsert(self, policy: ChannelPolicy) -> ChannelPolicy:
        self._policies[policy.id] = policy
        return policy


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def add(self, *, action: str, resource_type: str, resource_id: str, metadata: dict[str, str]) -> AuditEvent:
        event = AuditEvent(
            id=f"aud-{uuid4()}",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
        self._events.append(event)
        return event

    def list(self, *, offset: int, limit: int, action: str | None) -> tuple[list[AuditEvent], int]:
        events = self._events
        if action is not None:
            events = [event for event in events if event.action == action]
        return paginate(events, offset=offset, limit=limit), len(events)


@dataclass
class RepositoryBundle:
    signals: InMemorySignalRepository
    opportunities: InMemoryOpportunityRepository
    strategies: InMemoryStrategyRepository
    allocations: InMemoryAllocationRepository
    outcomes: InMemoryOutcomeRepository
    channel_policies: InMemoryChannelPolicyRepository
    audits: InMemoryAuditRepository
    capital_at_risk_limit: float

    def set_capital_at_risk_limit(self, limit: float) -> float:
        self.capital_at_risk_limit = limit
        return self.capital_at_risk_limit


def build_default_repositories() -> RepositoryBundle:
    return RepositoryBundle(
        signals=InMemorySignalRepository(
            [
                Signal(id="sig-1", source="permits", confidence=0.72),
                Signal(id="sig-2", source="procurement", confidence=0.88),
                Signal(id="sig-3", source="openings", confidence=0.63),
            ]
        ),
        opportunities=InMemoryOpportunityRepository(
            [
                Opportunity(
                    id="opp-1",
                    strategy_id="strat-1",
                    title="Tenant improvement permit at Koreatown",
                    status=OpportunityStatus.OPEN,
                    estimated_value=12000,
                ),
                Opportunity(
                    id="opp-2",
                    strategy_id="strat-1",
                    title="New storefront low-voltage setup",
                    status=OpportunityStatus.WON,
                    estimated_value=8500,
                ),
            ]
        ),
        strategies=InMemoryStrategyRepository(
            [
                Strategy(
                    id="strat-1",
                    name="LA permits outreach",
                    status=StrategyStatus.RUNNING,
                    capital_at_risk_limit=10000,
                ),
                Strategy(
                    id="strat-2",
                    name="Public procurement early signal",
                    status=StrategyStatus.PAUSED,
                    capital_at_risk_limit=5000,
                ),
            ]
        ),
        allocations=InMemoryAllocationRepository(
            [
                Allocation(id="alloc-1", strategy_id="strat-1", share=0.65),
                Allocation(id="alloc-2", strategy_id="strat-2", share=0.35),
            ]
        ),
        outcomes=InMemoryOutcomeRepository(
            [
                Outcome(id="out-1", opportunity_id="opp-1", status=OutcomeStatus.PENDING),
                Outcome(
                    id="out-2",
                    opportunity_id="opp-2",
                    status=OutcomeStatus.WON,
                    realized_value=9000,
                ),
            ]
        ),
        channel_policies=InMemoryChannelPolicyRepository(
            [
                ChannelPolicy(id="policy-1", name="email", status=ChannelPolicyStatus.PENDING, max_send_per_day=0),
                ChannelPolicy(id="policy-2", name="sms", status=ChannelPolicyStatus.DISABLED, max_send_per_day=0),
            ]
        ),
        audits=InMemoryAuditRepository(),
        capital_at_risk_limit=15000,
    )
