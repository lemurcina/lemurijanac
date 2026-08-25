"""CRM and outreach workflow primitives."""

from .scoring import (
    DEFAULT_STRATEGY_CONFIGS,
    OpportunityScore,
    OpportunityScoringInput,
    ScoreBreakdown,
    StrategyConfig,
    StrategyWeights,
    load_strategy_configs,
    score_opportunity,
)

__all__ = [
    "DEFAULT_STRATEGY_CONFIGS",
    "OpportunityScore",
    "OpportunityScoringInput",
    "ScoreBreakdown",
    "StrategyConfig",
    "StrategyWeights",
    "load_strategy_configs",
    "score_opportunity",
]
