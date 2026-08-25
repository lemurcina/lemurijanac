from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateInput:
    human_tone_score: int = 4
    specificity_score: int = 4
    has_price: bool = False
    pricing_evidence: bool = False
    cta_is_specific: bool = True
    state: str = "DRAFT"
    exact_sha: str | None = None
    ci_green: bool = False
    browser_or_route_proof: bool = False
    expected_cash: float = 0.0
    realized_cash: float = 0.0
    labels_expected_as_realized: bool = False
    demo_has_unique_observation: bool = True
    unchanged_failure_retries: int = 0


@dataclass(frozen=True)
class GateFailure:
    code: str
    failure_tag: str
    message: str


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[GateFailure, ...]


def evaluate_failure_gates(item: GateInput) -> GateResult:
    failures: list[GateFailure] = []

    if item.human_tone_score <= 1 or item.specificity_score <= 1:
        failures.append(
            GateFailure(
                "ROBOTIC_OUTREACH",
                "robotic-outreach",
                "outreach must be human-sounding and prospect-specific",
            )
        )

    if item.has_price and not item.pricing_evidence:
        failures.append(
            GateFailure(
                "PREMATURE_PRICE",
                "premature-price",
                "price claims require an evidence-backed pricing basis",
            )
        )

    if not item.cta_is_specific:
        failures.append(
            GateFailure(
                "GENERIC_CTA",
                "generic-cta",
                "CTA must ask for one concrete, low-friction next step",
            )
        )

    if item.state.upper() in {"READY", "DONE"}:
        if not (item.exact_sha and item.ci_green and item.browser_or_route_proof):
            failures.append(
                GateFailure(
                    "DONE_WITHOUT_PROOF",
                    "false-done",
                    "READY/DONE requires exact-SHA CI plus browser or route proof",
                )
            )

    if item.labels_expected_as_realized and item.expected_cash != item.realized_cash:
        failures.append(
            GateFailure(
                "EXPECTED_AS_REALIZED",
                "cash-evidence-confusion",
                "expected cash must remain separate from realized cash",
            )
        )

    if not item.demo_has_unique_observation:
        failures.append(
            GateFailure(
                "TEMPLATE_LOOKING_DEMO",
                "template-demo",
                "niche demo needs at least one verifiable prospect-specific observation",
            )
        )

    if item.unchanged_failure_retries >= 2:
        failures.append(
            GateFailure(
                "SILENT_RETRY_LOOP",
                "unchanged-retry",
                "two unchanged retries require a new recovery strategy",
            )
        )

    return GateResult(passed=not failures, failures=tuple(failures))
