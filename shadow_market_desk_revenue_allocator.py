from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from random import Random


class OutcomeKind(str, Enum):
    WON = "WON"
    LOST = "LOST"
    NO_RESPONSE = "NO_RESPONSE"
    INVALID = "INVALID"


@dataclass(slots=True)
class Outcome:
    strategy_id: str
    kind: OutcomeKind
    realized_gross_profit: float
    agent_hours: float
    capital_at_risk: float


@dataclass(slots=True)
class StrategyModel:
    strategy_id: str
    alpha: float = 1.0
    beta: float = 1.0
    sample_count: int = 0
    total_profit: float = 0.0
    total_agent_hours: float = 0.0
    total_capital_at_risk: float = 0.0
    consecutive_negative_outcomes: int = 0
    cooldown_rounds_remaining: int = 0

    def record_outcome(self, outcome: Outcome) -> None:
        self.sample_count += 1
        self.total_profit += outcome.realized_gross_profit
        self.total_agent_hours += max(outcome.agent_hours, 1e-9)
        self.total_capital_at_risk += max(outcome.capital_at_risk, 0.0)

        if outcome.kind == OutcomeKind.WON:
            self.alpha += 1.0
        else:
            self.beta += 1.0

        if outcome.realized_gross_profit < 0:
            self.consecutive_negative_outcomes += 1
        else:
            self.consecutive_negative_outcomes = 0

    @property
    def posterior_expected_value(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.total_profit / self.sample_count

    @property
    def expected_gross_profit_per_agent_hour(self) -> float:
        if self.total_agent_hours <= 0:
            return 0.0
        return self.total_profit / self.total_agent_hours

    @property
    def uncertainty(self) -> float:
        n = self.alpha + self.beta
        if n <= 0:
            return 1.0
        variance = (self.alpha * self.beta) / ((n**2) * (n + 1.0))
        return variance**0.5

    @property
    def avg_capital_risk_per_hour(self) -> float:
        if self.total_agent_hours <= 0:
            return 0.0
        return self.total_capital_at_risk / self.total_agent_hours

    @property
    def in_cooldown(self) -> bool:
        return self.cooldown_rounds_remaining > 0


@dataclass(slots=True)
class AllocationDecision:
    strategy_id: str
    allocated_agent_hours: float
    reason: str


@dataclass(slots=True)
class AllocationResult:
    decisions: list[AllocationDecision]
    reserve_exploration_hours: float
    explanations: list[str]


@dataclass(slots=True)
class RevenueAllocator:
    min_samples_for_kill: int = 5
    kill_gph_threshold: float = -10.0
    reactivation_gph_threshold: float = 0.0
    cooldown_rounds: int = 2
    exploration_fraction: float = 0.2

    strategies: dict[str, StrategyModel] = field(default_factory=dict)

    def ensure_strategy(self, strategy_id: str) -> StrategyModel:
        return self.strategies.setdefault(strategy_id, StrategyModel(strategy_id=strategy_id))

    def record_outcome(self, outcome: Outcome) -> None:
        strategy = self.ensure_strategy(outcome.strategy_id)
        strategy.record_outcome(outcome)

        if (
            strategy.sample_count >= self.min_samples_for_kill
            and strategy.expected_gross_profit_per_agent_hour <= self.kill_gph_threshold
            and strategy.consecutive_negative_outcomes >= 3
        ):
            strategy.cooldown_rounds_remaining = self.cooldown_rounds

        if strategy.in_cooldown and strategy.expected_gross_profit_per_agent_hour >= self.reactivation_gph_threshold:
            strategy.cooldown_rounds_remaining = 0

    def allocate(
        self,
        total_agent_hours: float,
        capital_at_risk_limit: float,
    ) -> AllocationResult:
        total_agent_hours = max(total_agent_hours, 0.0)
        capital_remaining = max(capital_at_risk_limit, 0.0)

        exploration_budget = total_agent_hours * min(max(self.exploration_fraction, 0.0), 0.5)
        exploitation_budget = total_agent_hours - exploration_budget

        active = [s for s in self.strategies.values() if not s.in_cooldown]
        cooling = [s for s in self.strategies.values() if s.in_cooldown]

        decisions: list[AllocationDecision] = []
        explanations: list[str] = []

        if not active:
            for strategy in cooling:
                decisions.append(
                    AllocationDecision(strategy.strategy_id, 0.0, "cooldown: paused for low value")
                )
            explanations.append("All strategies are paused; no allocation made.")
            self._tick_cooldown()
            return AllocationResult(decisions, exploration_budget, explanations)

        explore_candidates = sorted(active, key=lambda s: (s.sample_count, -s.uncertainty, s.strategy_id))
        exploit_candidates = sorted(
            active,
            key=lambda s: (s.expected_gross_profit_per_agent_hour, s.posterior_expected_value),
            reverse=True,
        )

        exploration_allocations: dict[str, float] = {}
        if exploration_budget > 0 and explore_candidates:
            per_strategy = exploration_budget / len(explore_candidates)
            for strategy in explore_candidates:
                if strategy.expected_gross_profit_per_agent_hour < self.kill_gph_threshold:
                    continue
                capped = self._cap_by_risk(per_strategy, strategy, capital_remaining)
                if capped <= 0:
                    continue
                exploration_allocations[strategy.strategy_id] = capped
                capital_remaining -= capped * strategy.avg_capital_risk_per_hour

        positive_exploit = [s for s in exploit_candidates if s.expected_gross_profit_per_agent_hour > 0]
        total_weight = sum(s.expected_gross_profit_per_agent_hour for s in positive_exploit)
        exploitation_allocations: dict[str, float] = {}

        if exploitation_budget > 0 and total_weight > 0:
            for strategy in positive_exploit:
                target = exploitation_budget * (
                    strategy.expected_gross_profit_per_agent_hour / total_weight
                )
                capped = self._cap_by_risk(target, strategy, capital_remaining)
                if capped <= 0:
                    continue
                exploitation_allocations[strategy.strategy_id] = capped
                capital_remaining -= capped * strategy.avg_capital_risk_per_hour

        all_ids = {s.strategy_id for s in self.strategies.values()}
        for strategy_id in sorted(all_ids):
            strategy = self.strategies[strategy_id]
            explore = exploration_allocations.get(strategy_id, 0.0)
            exploit = exploitation_allocations.get(strategy_id, 0.0)
            allocated = explore + exploit

            if strategy.in_cooldown:
                reason = "cooldown: persistently low expected gross profit per agent-hour"
            elif allocated <= 0:
                reason = (
                    "not allocated: expected gross profit per agent-hour <= 0 or capital constraint"
                )
            elif explore > 0 and exploit > 0:
                reason = "allocated via exploitation and bounded exploration"
            elif explore > 0:
                reason = "allocated via bounded exploration budget"
            else:
                reason = "allocated via exploitation based on expected gross profit per agent-hour"

            decisions.append(
                AllocationDecision(
                    strategy_id=strategy_id,
                    allocated_agent_hours=round(allocated, 6),
                    reason=reason,
                )
            )

            explanations.append(
                f"{strategy_id}: gph={strategy.expected_gross_profit_per_agent_hour:.2f}, "
                f"posterior={strategy.posterior_expected_value:.2f}, samples={strategy.sample_count}, "
                f"uncertainty={strategy.uncertainty:.4f}, cooldown={strategy.cooldown_rounds_remaining}, "
                f"allocated={allocated:.2f}, reason={reason}."
            )

        self._tick_cooldown()
        return AllocationResult(decisions, exploration_budget, explanations)

    def _cap_by_risk(self, hours: float, strategy: StrategyModel, capital_remaining: float) -> float:
        risk_per_hour = strategy.avg_capital_risk_per_hour
        if risk_per_hour <= 0:
            return max(hours, 0.0)
        max_hours = capital_remaining / risk_per_hour
        return max(min(hours, max_hours), 0.0)

    def _tick_cooldown(self) -> None:
        for strategy in self.strategies.values():
            if strategy.cooldown_rounds_remaining > 0:
                strategy.cooldown_rounds_remaining -= 1


@dataclass(slots=True)
class SyntheticStrategy:
    strategy_id: str
    win_rate: float
    won_profit_range: tuple[float, float]
    lost_profit_range: tuple[float, float]
    no_response_profit_range: tuple[float, float]
    invalid_profit_range: tuple[float, float]
    agent_hours_range: tuple[float, float]
    capital_at_risk_range: tuple[float, float]

    def sample_outcome(self, rng: Random) -> Outcome:
        draw = rng.random()
        if draw < self.win_rate:
            kind = OutcomeKind.WON
            gross = _uniform(rng, *self.won_profit_range)
        elif draw < self.win_rate + 0.4 * (1 - self.win_rate):
            kind = OutcomeKind.LOST
            gross = _uniform(rng, *self.lost_profit_range)
        elif draw < self.win_rate + 0.8 * (1 - self.win_rate):
            kind = OutcomeKind.NO_RESPONSE
            gross = _uniform(rng, *self.no_response_profit_range)
        else:
            kind = OutcomeKind.INVALID
            gross = _uniform(rng, *self.invalid_profit_range)

        return Outcome(
            strategy_id=self.strategy_id,
            kind=kind,
            realized_gross_profit=gross,
            agent_hours=_uniform(rng, *self.agent_hours_range),
            capital_at_risk=_uniform(rng, *self.capital_at_risk_range),
        )


@dataclass(slots=True)
class SimulationResult:
    daily_allocations: list[AllocationResult]
    total_realized_gross_profit: float
    total_agent_hours: float


def run_seeded_simulation(
    allocator: RevenueAllocator,
    synthetic_strategies: list[SyntheticStrategy],
    days: int,
    daily_agent_hours: float,
    daily_capital_limit: float,
    seed: int,
) -> SimulationResult:
    rng = Random(seed)
    strategies = {strategy.strategy_id: strategy for strategy in synthetic_strategies}

    for strategy in synthetic_strategies:
        allocator.ensure_strategy(strategy.strategy_id)

    daily_allocations: list[AllocationResult] = []
    total_profit = 0.0
    total_hours = 0.0

    for _ in range(days):
        allocation = allocator.allocate(
            total_agent_hours=daily_agent_hours,
            capital_at_risk_limit=daily_capital_limit,
        )
        daily_allocations.append(allocation)

        for decision in allocation.decisions:
            if decision.allocated_agent_hours <= 0:
                continue
            model = allocator.strategies[decision.strategy_id]
            avg_hours = model.total_agent_hours / model.sample_count if model.sample_count else 1.0
            attempts = max(1, round(decision.allocated_agent_hours / max(avg_hours, 1e-9)))

            for _ in range(attempts):
                outcome = strategies[decision.strategy_id].sample_outcome(rng)
                allocator.record_outcome(outcome)
                total_profit += outcome.realized_gross_profit
                total_hours += outcome.agent_hours

    return SimulationResult(
        daily_allocations=daily_allocations,
        total_realized_gross_profit=total_profit,
        total_agent_hours=total_hours,
    )


def summarize_daily_strategy_table(allocator: RevenueAllocator) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    for strategy in sorted(allocator.strategies.values(), key=lambda s: s.strategy_id):
        rows.append(
            {
                "strategy_id": strategy.strategy_id,
                "samples": strategy.sample_count,
                "posterior_expected_value": round(strategy.posterior_expected_value, 2),
                "expected_gross_profit_per_agent_hour": round(
                    strategy.expected_gross_profit_per_agent_hour, 2
                ),
                "uncertainty": round(strategy.uncertainty, 4),
                "cooldown_rounds_remaining": strategy.cooldown_rounds_remaining,
            }
        )
    return rows


def _uniform(rng: Random, low: float, high: float) -> float:
    if low == high:
        return low
    return low + (high - low) * rng.random()
