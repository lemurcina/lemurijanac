from __future__ import annotations

import json

import pytest

from shadow_market_desk.scoring import (
    OpportunityScoringInput,
    StrategyConfig,
    StrategyWeights,
    load_strategy_configs,
    score_opportunity,
)


def make_input(**overrides: float | bool | None) -> OpportunityScoringInput:
    base = {
        "urgency": 0.6,
        "confidence": 0.6,
        "buyer_intent": 0.6,
        "expected_margin": 0.4,
        "competition": 0.4,
        "fulfillment_ease": 0.6,
        "evidence_freshness": 0.7,
        "evidence_provenance_present": True,
        "expected_deal_value": 10_000.0,
        "estimated_agent_hours": 10.0,
    }
    base.update(overrides)
    return OpportunityScoringInput(**base)


def test_monotonicity_for_urgency() -> None:
    low = score_opportunity(make_input(urgency=0.2))
    high = score_opportunity(make_input(urgency=0.9))

    assert high.score > low.score


def test_missing_data_penalty_is_applied() -> None:
    complete = score_opportunity(make_input())
    missing = score_opportunity(make_input(buyer_intent=None))

    assert missing.score < complete.score
    assert missing.breakdown.missing_data_penalties["buyer_intent"] > 0


def test_score_is_bounded_for_extreme_values() -> None:
    extreme = score_opportunity(
        make_input(
            urgency=5.0,
            confidence=-5.0,
            buyer_intent=3.0,
            expected_margin=2.0,
            competition=-1.0,
            fulfillment_ease=10.0,
            evidence_freshness=4.0,
        )
    )

    assert 0.0 <= extreme.score <= 100.0


def test_scoring_is_deterministic() -> None:
    inputs = make_input()
    first = score_opportunity(inputs)
    second = score_opportunity(inputs)

    assert first == second


def test_score_is_zero_without_evidence_provenance() -> None:
    no_provenance = score_opportunity(make_input(evidence_provenance_present=False))

    assert no_provenance.score == 0.0
    assert no_provenance.breakdown.evidence_penalty > 0


def test_expected_profit_metrics_are_separate() -> None:
    result = score_opportunity(make_input(expected_margin=0.5, expected_deal_value=8_000.0, estimated_agent_hours=4.0))

    assert result.expected_gross_profit == 4_000.0
    assert result.expected_gross_profit_per_agent_hour == 1_000.0


def test_strategy_config_is_loadable_without_code_changes(tmp_path) -> None:
    config_file = tmp_path / "strategies.json"
    config_file.write_text(
        json.dumps(
            {
                "default": {
                    "weights": {
                        "urgency": 1,
                        "confidence": 0,
                        "buyer_intent": 0,
                        "expected_margin": 0,
                        "competition": 0,
                        "fulfillment_ease": 0,
                        "evidence_freshness": 0,
                    },
                    "missing_data_penalty_points": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    configs = load_strategy_configs(config_file)
    result_low = score_opportunity(make_input(urgency=0.1), strategy_configs=configs)
    result_high = score_opportunity(make_input(urgency=0.9), strategy_configs=configs)

    assert result_high.score > result_low.score


def test_strategy_specific_weights_change_outcome() -> None:
    strategy_configs = {
        "default": StrategyConfig(
            weights=StrategyWeights(
                urgency=0,
                confidence=0,
                buyer_intent=0,
                expected_margin=1,
                competition=0,
                fulfillment_ease=0,
                evidence_freshness=0,
            ),
            missing_data_penalty_points=0,
        )
    }

    low_margin = score_opportunity(make_input(expected_margin=0.1), strategy_configs=strategy_configs)
    high_margin = score_opportunity(make_input(expected_margin=0.8), strategy_configs=strategy_configs)

    assert high_margin.score > low_margin.score


def test_loading_invalid_strategy_weights_fails_fast(tmp_path) -> None:
    config_file = tmp_path / "invalid_strategies.json"
    config_file.write_text(
        json.dumps(
            {
                "default": {
                    "weights": {
                        "urgency": 0,
                        "confidence": 0,
                        "buyer_intent": 0,
                        "expected_margin": 0,
                        "competition": 0,
                        "fulfillment_ease": 0,
                        "evidence_freshness": 0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid weights for strategy 'default'"):
        load_strategy_configs(config_file)


def test_synthetic_docs_example_a_matches_engine_output() -> None:
    result = score_opportunity(
        OpportunityScoringInput(
            urgency=0.8,
            confidence=0.9,
            buyer_intent=0.7,
            expected_margin=0.5,
            competition=0.3,
            fulfillment_ease=0.6,
            evidence_freshness=0.8,
            evidence_provenance_present=True,
            expected_deal_value=12_000.0,
            estimated_agent_hours=6.0,
        )
    )

    assert result.score == 72.0
    assert result.expected_gross_profit == 6_000.0
    assert result.expected_gross_profit_per_agent_hour == 1_000.0
