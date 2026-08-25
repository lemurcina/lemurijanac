"""Policy engine – pure, testable, no UI dependency.

Every public method returns a ``Decision`` and records an ``AuditEvent``.

Usage::

    engine = PolicyEngine()

    # capital gate
    decision = engine.check_capital(action="buy_leads", amount=50.0, daily_spent=0.0)
    if decision.outcome != Outcome.ALLOW:
        raise RuntimeError(decision.reason)

    # outbound channel gate
    decision = engine.check_channel(
        channel="email",
        recipient_id="user-123",
        attempt_count=1,
        local_hour=10,
        jurisdiction="US",
        opted_out=False,
    )

    # outbound claim gate
    decision = engine.check_evidence(claim="vendor X ships next day", evidence_ids=["ev-1"])
"""

from __future__ import annotations

import logging
from typing import Any

from .config import PolicyConfig
from .models import AuditEvent, Decision, Outcome, ReasonCode

logger = logging.getLogger(__name__)


class PolicyEngine:
    """Stateless policy evaluator.

    The engine is constructed with an optional ``PolicyConfig``.  If none is
    supplied it calls ``PolicyConfig.load()`` which reads environment variables
    (or ``POLICY_CONFIG_PATH``), so operators can relax any rule without
    editing source code.

    All methods are synchronous and have no I/O side effects beyond writing to
    the standard ``logging`` framework.  Callers are responsible for persisting
    ``AuditEvent`` objects to their audit store.
    """

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self._config = config if config is not None else PolicyConfig.load()
        self._audit_log: list[AuditEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def audit_log(self) -> list[AuditEvent]:
        """In-memory audit trail (tests and simple deployments)."""
        return list(self._audit_log)

    def check_capital(
        self,
        action: str,
        amount: float,
        daily_spent: float,
        strategy_spent: float = 0.0,
        is_speculative: bool = False,
        creates_debt: bool = False,
        is_irreversible: bool = False,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Evaluate capital controls for a financial action."""
        cfg = self._config.capital
        ctx: dict[str, Any] = context or {}

        # Fail closed if config fields are somehow None
        if cfg is None:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.POLICY_DATA_MISSING,
                    details="Capital config is None – failing closed.",
                ),
                ctx,
            )

        # Fail closed on invalid monetary state: negative values could silently
        # reduce totals and bypass limit checks.
        for field_name, field_value in (
            ("amount", amount),
            ("daily_spent", daily_spent),
            ("strategy_spent", strategy_spent),
        ):
            if field_value < 0:
                return self._record(
                    action,
                    Decision(
                        outcome=Outcome.DENY,
                        reason=ReasonCode.POLICY_DATA_MISSING,
                        details=f"Invalid monetary input: '{field_name}' must not be negative (got {field_value}).",
                        metadata={"field": field_name, "value": field_value},
                    ),
                    ctx,
                )

        # Hard-stop checks: evaluate before the irreversible escalation so that
        # outright-forbidden operations cannot escape a DENY by being also
        # marked irreversible.
        if creates_debt and not cfg.allow_debt:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.DEBT_FORBIDDEN,
                    details="Debt creation is not permitted by policy.",
                ),
                ctx,
            )

        if is_speculative and not cfg.allow_speculative_purchases:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.SPECULATIVE_PURCHASE_BLOCKED,
                    details="Speculative purchases are blocked by policy.",
                ),
                ctx,
            )

        # Irreversible financial action → require review by default (after hard-stops)
        if is_irreversible:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.REQUIRE_REVIEW,
                    reason=ReasonCode.IRREVERSIBLE_ACTION,
                    details=f"Action '{action}' is marked irreversible; human review required.",
                ),
                ctx,
            )

        if amount > cfg.per_action_limit:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.EXCEEDS_ACTION_LIMIT,
                    details=(
                        f"Amount {amount} exceeds per-action limit {cfg.per_action_limit}."
                    ),
                    metadata={"amount": amount, "limit": cfg.per_action_limit},
                ),
                ctx,
            )

        if daily_spent + amount > cfg.daily_limit:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.EXCEEDS_DAILY_LIMIT,
                    details=(
                        f"Spending {amount} would bring daily total to "
                        f"{daily_spent + amount}, exceeding limit {cfg.daily_limit}."
                    ),
                    metadata={
                        "amount": amount,
                        "daily_spent": daily_spent,
                        "limit": cfg.daily_limit,
                    },
                ),
                ctx,
            )

        if strategy_spent + amount > cfg.strategy_limit:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.EXCEEDS_STRATEGY_LIMIT,
                    details=(
                        f"Spending {amount} would bring strategy total to "
                        f"{strategy_spent + amount}, exceeding limit {cfg.strategy_limit}."
                    ),
                    metadata={
                        "amount": amount,
                        "strategy_spent": strategy_spent,
                        "limit": cfg.strategy_limit,
                    },
                ),
                ctx,
            )

        return self._record(
            action,
            Decision(outcome=Outcome.ALLOW, reason=ReasonCode.OK),
            ctx,
        )

    def check_channel(
        self,
        channel: str,
        recipient_id: str,
        attempt_count: int,
        local_hour: int,
        jurisdiction: str = "",
        opted_out: bool = False,
        source_terms_compliant: bool = True,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Evaluate channel controls before contacting a recipient."""
        cfg = self._config.channel
        ctx: dict[str, Any] = context or {}

        if cfg is None:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.POLICY_DATA_MISSING,
                    details="Channel config is None – failing closed.",
                ),
                ctx,
            )

        if channel not in cfg.enabled_channels:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.CHANNEL_NOT_ENABLED,
                    details=f"Channel '{channel}' is not in enabled_channels list.",
                    metadata={"channel": channel, "enabled": cfg.enabled_channels},
                ),
                ctx,
            )

        if opted_out:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.RECIPIENT_OPT_OUT,
                    details=f"Recipient '{recipient_id}' has opted out.",
                ),
                ctx,
            )

        if attempt_count >= cfg.max_attempts_per_recipient:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.ATTEMPT_LIMIT_REACHED,
                    details=(
                        f"Recipient '{recipient_id}' has reached max attempts "
                        f"({cfg.max_attempts_per_recipient})."
                    ),
                    metadata={"attempts": attempt_count, "limit": cfg.max_attempts_per_recipient},
                ),
                ctx,
            )

        if self._in_quiet_hours(local_hour, cfg.quiet_hours_start, cfg.quiet_hours_end):
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.QUIET_HOURS,
                    details=(
                        f"Local hour {local_hour} falls within quiet hours "
                        f"({cfg.quiet_hours_start}–{cfg.quiet_hours_end})."
                    ),
                    metadata={
                        "local_hour": local_hour,
                        "quiet_start": cfg.quiet_hours_start,
                        "quiet_end": cfg.quiet_hours_end,
                    },
                ),
                ctx,
            )

        if jurisdiction and jurisdiction.upper() in [j.upper() for j in cfg.blocked_jurisdictions]:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.JURISDICTION_BLOCKED,
                    details=f"Jurisdiction '{jurisdiction}' is blocked by policy.",
                    metadata={"jurisdiction": jurisdiction},
                ),
                ctx,
            )

        if not source_terms_compliant:
            return self._record(
                f"channel:{channel}",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.SOURCE_TERMS_VIOLATION,
                    details="Source terms compliance flag is False.",
                ),
                ctx,
            )

        return self._record(
            f"channel:{channel}",
            Decision(outcome=Outcome.ALLOW, reason=ReasonCode.OK),
            ctx,
        )

    def check_business(
        self,
        action: str,
        is_binding_contract: bool = False,
        is_licensed_professional_impersonation: bool = False,
        is_regulated_brokerage: bool = False,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Evaluate business compliance controls."""
        cfg = self._config.business
        ctx: dict[str, Any] = context or {}

        if cfg is None:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.POLICY_DATA_MISSING,
                    details="Business config is None – failing closed.",
                ),
                ctx,
            )

        if is_binding_contract and not cfg.allow_binding_contracts:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.BINDING_CONTRACT_FORBIDDEN,
                    details="Binding contracts are not permitted by policy.",
                ),
                ctx,
            )

        if is_licensed_professional_impersonation and not cfg.allow_licensed_professional_impersonation:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.IMPERSONATION_FORBIDDEN,
                    details="Licensed professional impersonation is forbidden by policy.",
                ),
                ctx,
            )

        if is_regulated_brokerage and not cfg.allow_regulated_brokerage:
            return self._record(
                action,
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.REGULATED_BROKERAGE_BLOCKED,
                    details=(
                        "Regulated brokerage/referral is blocked by policy. "
                        "Set POLICY_ALLOW_REGULATED_BROKERAGE=I_ACCEPT_RISK to permit explicitly."
                    ),
                ),
                ctx,
            )

        return self._record(
            action,
            Decision(outcome=Outcome.ALLOW, reason=ReasonCode.OK),
            ctx,
        )

    def check_evidence(
        self,
        claim: str,
        evidence_ids: list[str],
        is_inference: bool = False,
        context: dict[str, Any] | None = None,
    ) -> Decision:
        """Gate outbound claims: must map to evidence or be labeled inference."""
        cfg = self._config.evidence
        ctx: dict[str, Any] = context or {}

        if cfg is None:
            return self._record(
                "evidence_gate",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.POLICY_DATA_MISSING,
                    details="Evidence config is None – failing closed.",
                ),
                ctx,
            )

        if cfg.require_evidence_for_outbound_claims and not is_inference and not evidence_ids:
            return self._record(
                "evidence_gate",
                Decision(
                    outcome=Outcome.DENY,
                    reason=ReasonCode.CLAIM_LACKS_EVIDENCE,
                    details=(
                        f"Claim '{claim[:120]}' has no evidence IDs and is not labeled inference."
                    ),
                    metadata={"claim_snippet": claim[:120]},
                ),
                ctx,
            )

        return self._record(
            "evidence_gate",
            Decision(outcome=Outcome.ALLOW, reason=ReasonCode.OK),
            ctx,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(
        self,
        action: str,
        decision: Decision,
        context: dict[str, Any],
    ) -> Decision:
        event = AuditEvent(action=action, decision=decision, context=context)
        self._audit_log.append(event)
        level = logging.WARNING if decision.outcome != Outcome.ALLOW else logging.DEBUG
        logger.log(
            level,
            "policy decision action=%s outcome=%s reason=%s details=%r",
            action,
            decision.outcome.value,
            decision.reason.value,
            decision.details,
        )
        return decision

    @staticmethod
    def _in_quiet_hours(hour: int, start: int, end: int) -> bool:
        """Return True if *hour* falls within quiet hours [start, end).

        Supports overnight ranges (e.g. start=21, end=8).
        """
        if start == end:
            return False
        if start <= end:
            # Normal range (e.g. 2–6)
            return start <= hour < end
        # Overnight range (e.g. 21–8: 21,22,23,0,1..7)
        return hour >= start or hour < end
