"""Deterministic opportunity scoring.

Defaults are intentionally explicit:
- Scores are bounded to 0-100.
- Missing factor penalty defaults to 3 score points per missing factor.
- Opportunities without evidence provenance are hard-gated to score 0.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType

FACTOR_NAMES = (
    "urgency",
    "confidence",
    "buyer_intent",
    "expected_margin",
    "competition",
    "fulfillment_ease",
    "evidence_freshness",
)


@dataclass(frozen=True)
class StrategyWeights:
    urgency: float
    confidence: float
    buyer_intent: float
    expected_margin: float
    competition: float
    fulfillment_ease: float
    evidence_freshness: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyConfig:
    weights: StrategyWeights
    missing_data_penalty_points: float = 3.0


@dataclass(frozen=True)
class OpportunityScoringInput:
    urgency: float | None
    confidence: float | None
    buyer_intent: float | None
    expected_margin: float | None
    competition: float | None
    fulfillment_ease: float | None
    evidence_freshness: float | None
    evidence_provenance_present: bool
    expected_deal_value: float | None = None
    estimated_agent_hours: float | None = None


@dataclass(frozen=True)
class ScoreBreakdown:
    normalized_inputs: Mapping[str, float | None]
    factor_contributions: Mapping[str, float]
    missing_data_penalties: Mapping[str, float]
    evidence_penalty: float
    total_penalty: float
    base_score: float
    final_score: float
    evidence_provenance_present: bool


@dataclass(frozen=True)
class OpportunityScore:
    strategy: str
    score: float
    potential_gross_profit: float | None
    potential_gross_profit_per_agent_hour: float | None
    breakdown: ScoreBreakdown


DEFAULT_STRATEGY_CONFIGS: dict[str, StrategyConfig] = {
    "default": StrategyConfig(
        weights=StrategyWeights(
            urgency=0.18,
            confidence=0.20,
            buyer_intent=0.20,
            expected_margin=0.18,
            competition=0.12,
            fulfillment_ease=0.07,
            evidence_freshness=0.05,
        ),
        missing_data_penalty_points=3.0,
    ),
    "speed_to_close": StrategyConfig(
        weights=StrategyWeights(
            urgency=0.25,
            confidence=0.22,
            buyer_intent=0.21,
            expected_margin=0.10,
            competition=0.10,
            fulfillment_ease=0.08,
            evidence_freshness=0.04,
        ),
        missing_data_penalty_points=3.0,
    ),
}


def _clamp_01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, weights.get(name, 0.0)) for name in FACTOR_NAMES)
    if total <= 0:
        raise ValueError("Strategy weights must contain at least one positive value")
    return {name: max(0.0, weights.get(name, 0.0)) / total for name in FACTOR_NAMES}


def _normalized_inputs(inputs: OpportunityScoringInput) -> dict[str, float | None]:
    return {
        "urgency": _clamp_01(inputs.urgency),
        "confidence": _clamp_01(inputs.confidence),
        "buyer_intent": _clamp_01(inputs.buyer_intent),
        "expected_margin": _clamp_01(inputs.expected_margin),
        "competition": _clamp_01(inputs.competition),
        "fulfillment_ease": _clamp_01(inputs.fulfillment_ease),
        "evidence_freshness": _clamp_01(inputs.evidence_freshness),
    }


def _compute_potential_gross_profit(inputs: OpportunityScoringInput) -> tuple[float | None, float | None]:
    if inputs.expected_deal_value is None or inputs.expected_margin is None:
        return None, None

    gross_profit = max(0.0, inputs.expected_deal_value) * (_clamp_01(inputs.expected_margin) or 0.0)
    if inputs.estimated_agent_hours is None or inputs.estimated_agent_hours <= 0:
        return gross_profit, None

    return gross_profit, gross_profit / inputs.estimated_agent_hours


def _freeze_mapping[T](values: Mapping[str, T]) -> Mapping[str, T]:
    return MappingProxyType(dict(values))


def score_opportunity(
    inputs: OpportunityScoringInput,
    strategy: str = "default",
    strategy_configs: dict[str, StrategyConfig] | None = None,
) -> OpportunityScore:
    configs = strategy_configs or DEFAULT_STRATEGY_CONFIGS
    if strategy not in configs:
        raise ValueError(f"Unknown strategy '{strategy}'")

    config = configs[strategy]
    weights = _normalize_weights(config.weights.as_dict())
    normalized_inputs = _normalized_inputs(inputs)

    contributions: dict[str, float] = {}
    penalties: dict[str, float] = {}
    weighted_sum = 0.0

    for name in FACTOR_NAMES:
        value = normalized_inputs[name]
        if value is None:
            contributions[name] = 0.0
            penalties[name] = config.missing_data_penalty_points
            continue

        effective_value = 1.0 - value if name == "competition" else value
        contribution = effective_value * weights[name] * 100.0
        contributions[name] = contribution
        penalties[name] = 0.0
        weighted_sum += contribution

    base_score = max(0.0, min(100.0, weighted_sum))
    missing_penalty_total = sum(penalties.values())
    score_after_missing_penalty = max(0.0, min(100.0, base_score - missing_penalty_total))

    if not inputs.evidence_provenance_present:
        evidence_penalty = score_after_missing_penalty
        final_score = 0.0
    else:
        evidence_penalty = 0.0
        final_score = score_after_missing_penalty

    total_penalty = missing_penalty_total + evidence_penalty

    potential_gross_profit, potential_gross_profit_per_agent_hour = _compute_potential_gross_profit(inputs)

    breakdown = ScoreBreakdown(
        normalized_inputs=_freeze_mapping(normalized_inputs),
        factor_contributions=_freeze_mapping(contributions),
        missing_data_penalties=_freeze_mapping(penalties),
        evidence_penalty=evidence_penalty,
        total_penalty=total_penalty,
        base_score=base_score,
        final_score=final_score,
        evidence_provenance_present=inputs.evidence_provenance_present,
    )

    return OpportunityScore(
        strategy=strategy,
        score=final_score,
        potential_gross_profit=potential_gross_profit,
        potential_gross_profit_per_agent_hour=potential_gross_profit_per_agent_hour,
        breakdown=breakdown,
    )


def load_strategy_configs(path: str | Path) -> dict[str, StrategyConfig]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    configs: dict[str, StrategyConfig] = {}

    for strategy_name, strategy_data in raw.items():
        weights = strategy_data.get("weights", {})
        configs[strategy_name] = StrategyConfig(
            weights=StrategyWeights(
                urgency=float(weights.get("urgency", 0.0)),
                confidence=float(weights.get("confidence", 0.0)),
                buyer_intent=float(weights.get("buyer_intent", 0.0)),
                expected_margin=float(weights.get("expected_margin", 0.0)),
                competition=float(weights.get("competition", 0.0)),
                fulfillment_ease=float(weights.get("fulfillment_ease", 0.0)),
                evidence_freshness=float(weights.get("evidence_freshness", 0.0)),
            ),
            missing_data_penalty_points=float(strategy_data.get("missing_data_penalty_points", 3.0)),
        )

    if "default" not in configs:
        raise ValueError("Strategy config must include a 'default' strategy")

    for strategy_name, config in configs.items():
        try:
            _normalize_weights(config.weights.as_dict())
        except ValueError as exc:
            raise ValueError(f"Invalid weights for strategy '{strategy_name}'") from exc

    return configs
