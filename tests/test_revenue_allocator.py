from shadow_market_desk_revenue_allocator import (
    Outcome,
    OutcomeKind,
    RevenueAllocator,
    SyntheticStrategy,
    run_seeded_simulation,
)


def _record(
    allocator: RevenueAllocator,
    strategy_id: str,
    kind: OutcomeKind,
    profit: float,
    hours: float = 1.0,
    capital: float = 10.0,
) -> None:
    allocator.record_outcome(
        Outcome(
            strategy_id=strategy_id,
            kind=kind,
            realized_gross_profit=profit,
            agent_hours=hours,
            capital_at_risk=capital,
        )
    )


def test_exploitation_shifts_toward_proven_strategy() -> None:
    allocator = RevenueAllocator(exploration_fraction=0.2)

    allocator.ensure_strategy("proven")
    allocator.ensure_strategy("weak")

    for _ in range(8):
        _record(allocator, "proven", OutcomeKind.WON, profit=200.0)
        _record(allocator, "weak", OutcomeKind.LOST, profit=-20.0)

    result = allocator.allocate(total_agent_hours=10.0, capital_at_risk_limit=1_000.0)
    hours = {d.strategy_id: d.allocated_agent_hours for d in result.decisions}

    assert hours["proven"] > hours["weak"]
    assert any("expected gross profit per agent-hour" in e for e in result.explanations)


def test_bounded_exploration_and_sparse_data() -> None:
    allocator = RevenueAllocator(exploration_fraction=0.25)
    allocator.ensure_strategy("new_a")
    allocator.ensure_strategy("new_b")

    result = allocator.allocate(total_agent_hours=8.0, capital_at_risk_limit=100.0)
    hours = {d.strategy_id: d.allocated_agent_hours for d in result.decisions}

    assert result.reserve_exploration_hours == 2.0
    assert hours["new_a"] == 1.0
    assert hours["new_b"] == 1.0


def test_negative_outcomes_trigger_cooldown_and_recovery() -> None:
    allocator = RevenueAllocator(min_samples_for_kill=3, kill_gph_threshold=-1.0, cooldown_rounds=2)
    allocator.ensure_strategy("fragile")

    _record(allocator, "fragile", OutcomeKind.LOST, profit=-10.0)
    _record(allocator, "fragile", OutcomeKind.NO_RESPONSE, profit=-10.0)
    _record(allocator, "fragile", OutcomeKind.INVALID, profit=-10.0)

    assert allocator.strategies["fragile"].in_cooldown

    paused = allocator.allocate(total_agent_hours=4.0, capital_at_risk_limit=100.0)
    reason = {d.strategy_id: d.reason for d in paused.decisions}["fragile"]
    assert "cooldown" in reason

    _record(allocator, "fragile", OutcomeKind.WON, profit=100.0)
    assert not allocator.strategies["fragile"].in_cooldown


def test_capital_at_risk_constraint_caps_allocation() -> None:
    allocator = RevenueAllocator(exploration_fraction=0.0)
    allocator.ensure_strategy("risky")
    _record(allocator, "risky", OutcomeKind.WON, profit=100.0, hours=1.0, capital=100.0)

    result = allocator.allocate(total_agent_hours=10.0, capital_at_risk_limit=250.0)
    hours = {d.strategy_id: d.allocated_agent_hours for d in result.decisions}

    assert hours["risky"] == 2.5


def test_seeded_simulation_is_deterministic() -> None:
    strategies = [
        SyntheticStrategy(
            strategy_id="alpha",
            win_rate=0.4,
            won_profit_range=(120.0, 140.0),
            lost_profit_range=(-40.0, -20.0),
            no_response_profit_range=(-10.0, 0.0),
            invalid_profit_range=(-30.0, -10.0),
            agent_hours_range=(0.8, 1.2),
            capital_at_risk_range=(20.0, 30.0),
        ),
        SyntheticStrategy(
            strategy_id="beta",
            win_rate=0.2,
            won_profit_range=(200.0, 220.0),
            lost_profit_range=(-70.0, -40.0),
            no_response_profit_range=(-15.0, -5.0),
            invalid_profit_range=(-50.0, -20.0),
            agent_hours_range=(1.0, 1.4),
            capital_at_risk_range=(35.0, 45.0),
        ),
    ]

    run_one = run_seeded_simulation(
        allocator=RevenueAllocator(),
        synthetic_strategies=strategies,
        days=7,
        daily_agent_hours=10.0,
        daily_capital_limit=500.0,
        seed=123,
    )
    run_two = run_seeded_simulation(
        allocator=RevenueAllocator(),
        synthetic_strategies=strategies,
        days=7,
        daily_agent_hours=10.0,
        daily_capital_limit=500.0,
        seed=123,
    )

    assert run_one.total_realized_gross_profit == run_two.total_realized_gross_profit
    assert run_one.total_agent_hours == run_two.total_agent_hours
    assert [
        [d.allocated_agent_hours for d in day.decisions]
        for day in run_one.daily_allocations
    ] == [
        [d.allocated_agent_hours for d in day.decisions]
        for day in run_two.daily_allocations
    ]
