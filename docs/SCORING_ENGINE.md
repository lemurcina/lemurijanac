# Opportunity scoring engine

The scoring engine is deterministic and pure (`score_opportunity`), with a bounded output of `0-100`.

## Inputs
All factor inputs are expected in `[0, 1]` and are clamped to `[0, 1]`:
- urgency
- confidence
- buyer_intent
- expected_margin
- competition (higher competition reduces score)
- fulfillment_ease
- evidence_freshness

Additional fields:
- `evidence_provenance_present` (required guardrail)
- `expected_deal_value` (for potential gross profit)
- `estimated_agent_hours` (for potential gross profit per agent-hour)

## Defaults (no hidden constants)
Default strategy weights:
- urgency: `0.18`
- confidence: `0.20`
- buyer_intent: `0.20`
- expected_margin: `0.18`
- competition: `0.12`
- fulfillment_ease: `0.07`
- evidence_freshness: `0.05`

Default missing-data penalty:
- `3.0` score points per missing factor

Evidence-provenance guardrail:
- If `evidence_provenance_present` is `False`, final score is forced to `0.0`.

## Explainability payload
`ScoreBreakdown` returns:
- normalized input values
- per-factor contribution (in score points)
- missing-data penalty by factor
- evidence penalty
- base score, total penalty, and final score

## Strategy configuration without code changes
Use `load_strategy_configs(path)` with a JSON file to define strategy weights and penalties.

Example (`strategies.json`):
```json
{
  "default": {
    "weights": {
      "urgency": 0.18,
      "confidence": 0.20,
      "buyer_intent": 0.20,
      "expected_margin": 0.18,
      "competition": 0.12,
      "fulfillment_ease": 0.07,
      "evidence_freshness": 0.05
    },
    "missing_data_penalty_points": 3.0
  },
  "speed_to_close": {
    "weights": {
      "urgency": 0.25,
      "confidence": 0.22,
      "buyer_intent": 0.21,
      "expected_margin": 0.10,
      "competition": 0.10,
      "fulfillment_ease": 0.08,
      "evidence_freshness": 0.04
    },
    "missing_data_penalty_points": 3.0
  }
}
```

## Synthetic examples
Example A (strong evidence, moderate competition):
- urgency `0.8`, confidence `0.9`, buyer_intent `0.7`, expected_margin `0.5`, competition `0.3`, fulfillment_ease `0.6`, evidence_freshness `0.8`, provenance `true`
- expected_deal_value `12000`, estimated_agent_hours `6`
- result: score `72.0`, potential gross profit `6000`, potential gross profit per agent-hour `1000`

Example B (missing provenance):
- same factors, provenance `false`
- result: final score forced to `0` by guardrail

Example C (missing data):
- buyer_intent missing (`null`)
- result: missing-data penalty is applied and reflected in `missing_data_penalties`
