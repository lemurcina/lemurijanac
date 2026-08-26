"""Tests for the policy engine."""

from __future__ import annotations

import os
from typing import ClassVar

import pytest

from policy.config import (
    BusinessConfig,
    CapitalConfig,
    ChannelConfig,
    EvidenceConfig,
    PolicyConfig,
)
from policy.engine import PolicyEngine
from policy.models import Outcome, ReasonCode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine(
    *,
    per_action_limit: float = 100.0,
    daily_limit: float = 500.0,
    strategy_limit: float = 1000.0,
    allow_debt: bool = False,
    allow_speculative: bool = False,
    enabled_channels: list[str] | None = None,
    max_attempts: int = 3,
    quiet_start: int = 21,
    quiet_end: int = 8,
    blocked_jurisdictions: list[str] | None = None,
    allow_binding_contracts: bool = False,
    allow_impersonation: bool = False,
    allow_brokerage: bool = False,
    require_evidence: bool = True,
) -> PolicyEngine:
    cfg = PolicyConfig(
        capital=CapitalConfig(
            per_action_limit=per_action_limit,
            daily_limit=daily_limit,
            strategy_limit=strategy_limit,
            allow_debt=allow_debt,
            allow_speculative_purchases=allow_speculative,
        ),
        channel=ChannelConfig(
            enabled_channels=enabled_channels if enabled_channels is not None else ["email"],
            max_attempts_per_recipient=max_attempts,
            quiet_hours_start=quiet_start,
            quiet_hours_end=quiet_end,
            blocked_jurisdictions=blocked_jurisdictions or [],
        ),
        business=BusinessConfig(
            allow_binding_contracts=allow_binding_contracts,
            allow_licensed_professional_impersonation=allow_impersonation,
            allow_regulated_brokerage=allow_brokerage,
        ),
        evidence=EvidenceConfig(require_evidence_for_outbound_claims=require_evidence),
    )
    return PolicyEngine(config=cfg)


# ---------------------------------------------------------------------------
# Capital controls
# ---------------------------------------------------------------------------


class TestCapitalControls:
    def test_allow_within_limits(self):
        e = _engine()
        d = e.check_capital("buy_leads", amount=50.0, daily_spent=0.0)
        assert d.outcome == Outcome.ALLOW

    def test_deny_exceeds_action_limit(self):
        e = _engine(per_action_limit=100.0)
        d = e.check_capital("buy_leads", amount=101.0, daily_spent=0.0)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.EXCEEDS_ACTION_LIMIT

    def test_deny_exceeds_daily_limit(self):
        e = _engine(daily_limit=500.0)
        d = e.check_capital("buy_leads", amount=50.0, daily_spent=460.0)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.EXCEEDS_DAILY_LIMIT

    def test_deny_exceeds_strategy_limit(self):
        e = _engine(strategy_limit=1000.0)
        d = e.check_capital("buy_leads", amount=50.0, daily_spent=0.0, strategy_spent=960.0)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.EXCEEDS_STRATEGY_LIMIT

    def test_deny_debt_by_default(self):
        e = _engine(allow_debt=False)
        d = e.check_capital("credit_purchase", amount=1.0, daily_spent=0.0, creates_debt=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.DEBT_FORBIDDEN

    def test_allow_debt_when_permitted(self):
        e = _engine(allow_debt=True)
        d = e.check_capital("credit_purchase", amount=1.0, daily_spent=0.0, creates_debt=True)
        assert d.outcome == Outcome.ALLOW

    def test_deny_speculative_by_default(self):
        e = _engine(allow_speculative=False)
        d = e.check_capital("speculative_buy", amount=1.0, daily_spent=0.0, is_speculative=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.SPECULATIVE_PURCHASE_BLOCKED

    def test_allow_speculative_when_permitted(self):
        e = _engine(allow_speculative=True)
        d = e.check_capital("speculative_buy", amount=1.0, daily_spent=0.0, is_speculative=True)
        assert d.outcome == Outcome.ALLOW

    def test_irreversible_requires_review(self):
        e = _engine()
        d = e.check_capital("wire_transfer", amount=1.0, daily_spent=0.0, is_irreversible=True)
        assert d.outcome == Outcome.REQUIRE_REVIEW
        assert d.reason == ReasonCode.IRREVERSIBLE_ACTION

    def test_exact_action_limit_is_allowed(self):
        """Amount exactly equal to the limit should be allowed."""
        e = _engine(per_action_limit=100.0)
        d = e.check_capital("buy_leads", amount=100.0, daily_spent=0.0)
        assert d.outcome == Outcome.ALLOW

    def test_exact_daily_limit_is_allowed(self):
        e = _engine(daily_limit=500.0)
        d = e.check_capital("buy_leads", amount=100.0, daily_spent=400.0)
        assert d.outcome == Outcome.ALLOW


# ---------------------------------------------------------------------------
# Channel controls
# ---------------------------------------------------------------------------


class TestChannelControls:
    def test_allow_enabled_channel_daytime(self):
        e = _engine(enabled_channels=["email"], quiet_start=21, quiet_end=8)
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=10)
        assert d.outcome == Outcome.ALLOW

    def test_deny_disabled_channel(self):
        e = _engine(enabled_channels=["email"])
        d = e.check_channel("sms", "u1", attempt_count=0, local_hour=10)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.CHANNEL_NOT_ENABLED

    def test_deny_opted_out_recipient(self):
        e = _engine(enabled_channels=["email"])
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=10, opted_out=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.RECIPIENT_OPT_OUT

    def test_deny_attempt_limit_reached(self):
        e = _engine(enabled_channels=["email"], max_attempts=3)
        d = e.check_channel("email", "u1", attempt_count=3, local_hour=10)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.ATTEMPT_LIMIT_REACHED

    def test_allow_under_attempt_limit(self):
        e = _engine(enabled_channels=["email"], max_attempts=3)
        d = e.check_channel("email", "u1", attempt_count=2, local_hour=10)
        assert d.outcome == Outcome.ALLOW

    def test_deny_quiet_hours_overnight(self):
        e = _engine(enabled_channels=["email"], quiet_start=21, quiet_end=8)
        for hour in [21, 22, 23, 0, 1, 7]:
            d = e.check_channel("email", "u1", attempt_count=0, local_hour=hour)
            assert d.outcome == Outcome.DENY, f"Expected DENY at hour {hour}"

    def test_allow_outside_quiet_hours(self):
        e = _engine(enabled_channels=["email"], quiet_start=21, quiet_end=8)
        for hour in [8, 12, 20]:
            d = e.check_channel("email", "u1", attempt_count=0, local_hour=hour)
            assert d.outcome == Outcome.ALLOW, f"Expected ALLOW at hour {hour}"

    def test_deny_blocked_jurisdiction(self):
        e = _engine(enabled_channels=["email"], blocked_jurisdictions=["CN", "RU"])
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=10, jurisdiction="CN")
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.JURISDICTION_BLOCKED

    def test_jurisdiction_check_is_case_insensitive(self):
        e = _engine(enabled_channels=["email"], blocked_jurisdictions=["CN"])
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=10, jurisdiction="cn")
        assert d.outcome == Outcome.DENY

    def test_deny_source_terms_violation(self):
        e = _engine(enabled_channels=["email"])
        d = e.check_channel(
            "email", "u1", attempt_count=0, local_hour=10, source_terms_compliant=False
        )
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.SOURCE_TERMS_VIOLATION


# ---------------------------------------------------------------------------
# Business controls
# ---------------------------------------------------------------------------


class TestBusinessControls:
    def test_allow_normal_action(self):
        e = _engine()
        d = e.check_business("send_proposal")
        assert d.outcome == Outcome.ALLOW

    def test_deny_binding_contract_by_default(self):
        e = _engine(allow_binding_contracts=False)
        d = e.check_business("sign_contract", is_binding_contract=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.BINDING_CONTRACT_FORBIDDEN

    def test_allow_binding_contract_when_permitted(self):
        e = _engine(allow_binding_contracts=True)
        d = e.check_business("sign_contract", is_binding_contract=True)
        assert d.outcome == Outcome.ALLOW

    def test_deny_impersonation_by_default(self):
        e = _engine(allow_impersonation=False)
        d = e.check_business("pose_as_lawyer", is_licensed_professional_impersonation=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.IMPERSONATION_FORBIDDEN

    def test_deny_regulated_brokerage_by_default(self):
        e = _engine(allow_brokerage=False)
        d = e.check_business("refer_investment", is_regulated_brokerage=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.REGULATED_BROKERAGE_BLOCKED

    def test_allow_regulated_brokerage_when_permitted(self):
        e = _engine(allow_brokerage=True)
        d = e.check_business("refer_investment", is_regulated_brokerage=True)
        assert d.outcome == Outcome.ALLOW


# ---------------------------------------------------------------------------
# Evidence gate
# ---------------------------------------------------------------------------


class TestEvidenceGate:
    def test_allow_claim_with_evidence(self):
        e = _engine(require_evidence=True)
        d = e.check_evidence("Vendor ships next day", evidence_ids=["ev-001"])
        assert d.outcome == Outcome.ALLOW

    def test_deny_claim_without_evidence(self):
        e = _engine(require_evidence=True)
        d = e.check_evidence("Vendor ships next day", evidence_ids=[])
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.CLAIM_LACKS_EVIDENCE

    def test_allow_inference_without_evidence(self):
        """Inferences are allowed without evidence IDs when labeled as such."""
        e = _engine(require_evidence=True)
        d = e.check_evidence("Likely ships next day", evidence_ids=[], is_inference=True)
        assert d.outcome == Outcome.ALLOW

    def test_allow_claim_without_evidence_when_gate_disabled(self):
        e = _engine(require_evidence=False)
        d = e.check_evidence("Unverified claim", evidence_ids=[])
        assert d.outcome == Outcome.ALLOW


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_every_decision_is_recorded(self):
        e = _engine()
        e.check_capital("action", amount=1.0, daily_spent=0.0)
        e.check_channel("email", "u1", attempt_count=0, local_hour=10)
        e.check_business("send_proposal")
        e.check_evidence("claim", evidence_ids=["ev-1"])
        assert len(e.audit_log) == 4

    def test_audit_log_is_copy(self):
        """Mutating the returned list must not affect internal state."""
        e = _engine()
        e.check_capital("a", amount=1.0, daily_spent=0.0)
        log = e.audit_log
        log.clear()
        assert len(e.audit_log) == 1

    def test_denied_decision_audit_entry(self):
        e = _engine(allow_speculative=False)
        e.check_capital("spec_buy", amount=1.0, daily_spent=0.0, is_speculative=True)
        entry = e.audit_log[0]
        assert entry.decision.outcome == Outcome.DENY
        assert entry.action == "spec_buy"


# ---------------------------------------------------------------------------
# Fail-closed when policy data is missing
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_capital_config_none_fails_closed(self):
        cfg = PolicyConfig(
            capital=None,  # type: ignore[arg-type]
            channel=ChannelConfig(enabled_channels=["email"]),
            business=BusinessConfig(),
            evidence=EvidenceConfig(),
        )
        e = PolicyEngine(config=cfg)
        d = e.check_capital("action", amount=1.0, daily_spent=0.0)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_channel_config_none_fails_closed(self):
        cfg = PolicyConfig(
            capital=CapitalConfig(),
            channel=None,  # type: ignore[arg-type]
            business=BusinessConfig(),
            evidence=EvidenceConfig(),
        )
        e = PolicyEngine(config=cfg)
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=10)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_business_config_none_fails_closed(self):
        cfg = PolicyConfig(
            capital=CapitalConfig(),
            channel=ChannelConfig(enabled_channels=["email"]),
            business=None,  # type: ignore[arg-type]
            evidence=EvidenceConfig(),
        )
        e = PolicyEngine(config=cfg)
        d = e.check_business("action")
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_evidence_config_none_fails_closed(self):
        cfg = PolicyConfig(
            capital=CapitalConfig(),
            channel=ChannelConfig(enabled_channels=["email"]),
            business=BusinessConfig(),
            evidence=None,  # type: ignore[arg-type]
        )
        e = PolicyEngine(config=cfg)
        d = e.check_evidence("claim", evidence_ids=[])
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING


# ---------------------------------------------------------------------------
# Adversarial bypass attempts
# ---------------------------------------------------------------------------


class TestAdversarialBypass:
    """Ensure common bypass techniques are rejected."""

    def test_negative_amount_does_not_bypass_debt_rule(self):
        """A negative amount is rejected outright (fail-closed on invalid input) before debt check."""
        e = _engine(allow_debt=False)
        d = e.check_capital("credit", amount=-50.0, daily_spent=0.0, creates_debt=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_zero_amount_speculative_still_blocked(self):
        e = _engine(allow_speculative=False)
        d = e.check_capital("spec", amount=0.0, daily_spent=0.0, is_speculative=True)
        assert d.outcome == Outcome.DENY

    def test_irreversible_not_bypassed_by_small_amount(self):
        e = _engine(per_action_limit=1000.0)
        d = e.check_capital("wire", amount=0.01, daily_spent=0.0, is_irreversible=True)
        assert d.outcome == Outcome.REQUIRE_REVIEW

    def test_debt_deny_takes_priority_over_irreversible(self):
        """A forbidden-debt action must be DENIED even if also marked irreversible."""
        e = _engine(allow_debt=False)
        d = e.check_capital(
            "credit_wire", amount=1.0, daily_spent=0.0,
            creates_debt=True, is_irreversible=True,
        )
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.DEBT_FORBIDDEN

    def test_speculative_deny_takes_priority_over_irreversible(self):
        """A blocked-speculative action must be DENIED even if also marked irreversible."""
        e = _engine(allow_speculative=False)
        d = e.check_capital(
            "spec_wire", amount=1.0, daily_spent=0.0,
            is_speculative=True, is_irreversible=True,
        )
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.SPECULATIVE_PURCHASE_BLOCKED

    def test_opted_out_not_bypassed_by_different_channel(self):
        """Opt-out is checked per channel; a blocked channel is still blocked."""
        e = _engine(enabled_channels=["sms"])
        # sms enabled but opted out
        d = e.check_channel("sms", "u1", attempt_count=0, local_hour=10, opted_out=True)
        assert d.outcome == Outcome.DENY

    def test_blocked_jurisdiction_case_variants(self):
        e = _engine(enabled_channels=["email"], blocked_jurisdictions=["RU"])
        for jur in ["RU", "ru", "Ru", "rU"]:
            d = e.check_channel("email", "u1", attempt_count=0, local_hour=10, jurisdiction=jur)
            assert d.outcome == Outcome.DENY, f"Expected DENY for jurisdiction '{jur}'"

    def test_brokerage_not_allowed_even_with_other_flags_clear(self):
        """Regulated brokerage must be explicitly enabled; no implicit path through."""
        e = _engine(
            allow_binding_contracts=True,
            allow_impersonation=True,
            allow_brokerage=False,
        )
        d = e.check_business("invest_refer", is_regulated_brokerage=True)
        assert d.outcome == Outcome.DENY

    def test_empty_evidence_list_bypassed_only_by_inference_flag(self):
        """Passing an empty list must not be silently treated as evidence."""
        e = _engine(require_evidence=True)
        d_no_flag = e.check_evidence("claim", evidence_ids=[], is_inference=False)
        d_with_flag = e.check_evidence("claim", evidence_ids=[], is_inference=True)
        assert d_no_flag.outcome == Outcome.DENY
        assert d_with_flag.outcome == Outcome.ALLOW

    def test_quiet_hour_boundary_not_off_by_one(self):
        """Hour 8 is *outside* quiet hours (quiet ends at 8, exclusive)."""
        e = _engine(enabled_channels=["email"], quiet_start=21, quiet_end=8)
        d = e.check_channel("email", "u1", attempt_count=0, local_hour=8)
        assert d.outcome == Outcome.ALLOW

    def test_attempt_count_exactly_at_limit_is_denied(self):
        e = _engine(enabled_channels=["email"], max_attempts=3)
        d = e.check_channel("email", "u1", attempt_count=3, local_hour=10)
        assert d.outcome == Outcome.DENY

    def test_attempt_count_one_below_limit_is_allowed(self):
        e = _engine(enabled_channels=["email"], max_attempts=3)
        d = e.check_channel("email", "u1", attempt_count=2, local_hour=10)
        assert d.outcome == Outcome.ALLOW

    @pytest.mark.parametrize("field,kwargs", [
        ("amount",        {"amount": -1.0, "daily_spent": 0.0, "strategy_spent": 0.0}),
        ("amount",        {"amount": -0.01, "daily_spent": 0.0, "strategy_spent": 0.0}),
        ("daily_spent",   {"amount": 1.0, "daily_spent": -50.0, "strategy_spent": 0.0}),
        ("strategy_spent", {"amount": 1.0, "daily_spent": 0.0, "strategy_spent": -100.0}),
    ])
    def test_negative_monetary_input_is_denied(self, field, kwargs):
        """Negative monetary inputs must be rejected to prevent limit-bypass via underflow."""
        e = _engine(per_action_limit=1000.0, daily_limit=1000.0, strategy_limit=1000.0)
        d = e.check_capital("action", **kwargs)
        assert d.outcome == Outcome.DENY, f"Expected DENY for negative '{field}'"
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_negative_amount_denied_even_when_debt_allowed(self):
        """Negative amount is rejected before debt/speculative checks regardless of flag."""
        e = _engine(allow_debt=True)
        d = e.check_capital("action", amount=-10.0, daily_spent=0.0, creates_debt=True)
        assert d.outcome == Outcome.DENY
        assert d.reason == ReasonCode.POLICY_DATA_MISSING

    def test_brokerage_deny_message_uses_i_accept_risk_token(self):
        """Error detail must direct operators to set the env var to I_ACCEPT_RISK, not 'true'."""
        e = _engine(allow_brokerage=False)
        d = e.check_business("invest_refer", is_regulated_brokerage=True)
        assert d.outcome == Outcome.DENY
        assert "I_ACCEPT_RISK" in (d.details or "")
        assert "=true" not in (d.details or "")

# ---------------------------------------------------------------------------
# Stale env-var safety: safety-critical relaxation flags require I_ACCEPT_RISK
# ---------------------------------------------------------------------------


class TestStaleEnvVarSafety:
    """Verify that generic truthy env-var values cannot silently weaken safety defaults.

    Safety-critical flags are only relaxed when the env var equals the explicit
    acknowledgement token ``I_ACCEPT_RISK``.  Common truthy values that might
    appear in developer shells or be copy-pasted from documentation (``true``,
    ``1``, ``yes``) must be silently ignored and the safe default preserved.
    """

    # Each tuple is (env_var_name, config_attr_path)
    SAFETY_RELAX_FLAGS: ClassVar[list[tuple[str, str]]] = [
        ("POLICY_ALLOW_DEBT", "capital.allow_debt"),
        ("POLICY_ALLOW_SPECULATIVE_PURCHASES", "capital.allow_speculative_purchases"),
        ("POLICY_ALLOW_BINDING_CONTRACTS", "business.allow_binding_contracts"),
        (
            "POLICY_ALLOW_LICENSED_PROFESSIONAL_IMPERSONATION",
            "business.allow_licensed_professional_impersonation",
        ),
        ("POLICY_ALLOW_REGULATED_BROKERAGE", "business.allow_regulated_brokerage"),
    ]

    def _get_flag(self, cfg: PolicyConfig, dotted: str) -> bool:
        obj: object = cfg
        for part in dotted.split("."):
            obj = getattr(obj, part)
        return bool(obj)

    @pytest.mark.parametrize("env_var,dotted", SAFETY_RELAX_FLAGS)
    @pytest.mark.parametrize("stale_value", ["true", "1", "yes", "True", "TRUE", "YES"])
    def test_stale_truthy_value_does_not_relax_flag(
        self, env_var: str, dotted: str, stale_value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A generic truthy env-var value must not relax a safety flag."""
        monkeypatch.setenv(env_var, stale_value)
        cfg = PolicyConfig()
        assert self._get_flag(cfg, dotted) is False, (
            f"{env_var}={stale_value!r} should NOT relax {dotted}"
        )

    @pytest.mark.parametrize("env_var,dotted", SAFETY_RELAX_FLAGS)
    def test_ack_token_does_relax_flag(
        self, env_var: str, dotted: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The explicit I_ACCEPT_RISK token must relax the flag."""
        monkeypatch.setenv(env_var, "I_ACCEPT_RISK")
        cfg = PolicyConfig()
        assert self._get_flag(cfg, dotted) is True, (
            f"{env_var}=I_ACCEPT_RISK should relax {dotted}"
        )

    @pytest.mark.parametrize("stale_value", ["false", "0", "no", "False", "FALSE"])
    def test_stale_falsy_evidence_gate_stays_enabled(
        self, stale_value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting the evidence-gate disable var to a falsy value must not disable the gate."""
        monkeypatch.setenv("POLICY_DISABLE_EVIDENCE_GATE", stale_value)
        cfg = PolicyConfig()
        assert cfg.evidence.require_evidence_for_outbound_claims is True

    def test_ack_token_disables_evidence_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """I_ACCEPT_RISK must disable the evidence gate when set."""
        monkeypatch.setenv("POLICY_DISABLE_EVIDENCE_GATE", "I_ACCEPT_RISK")
        cfg = PolicyConfig()
        assert cfg.evidence.require_evidence_for_outbound_claims is False

    def test_unset_safety_flags_default_to_false(self) -> None:
        """Without any env vars, every safety-critical flag defaults to the safe value."""
        safety_vars = [v for v, _ in self.SAFETY_RELAX_FLAGS] + ["POLICY_DISABLE_EVIDENCE_GATE"]
        for v in safety_vars:
            assert v not in os.environ, f"Unexpected env var {v} in test environment"
        cfg = PolicyConfig()
        for _, dotted in self.SAFETY_RELAX_FLAGS:
            assert self._get_flag(cfg, dotted) is False
        assert cfg.evidence.require_evidence_for_outbound_claims is True

    def test_old_evidence_gate_env_var_emits_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Setting the old POLICY_REQUIRE_EVIDENCE_FOR_OUTBOUND_CLAIMS env var emits a warning."""
        import logging

        monkeypatch.setenv("POLICY_REQUIRE_EVIDENCE_FOR_OUTBOUND_CLAIMS", "false")
        with caplog.at_level(logging.WARNING, logger="policy.config"):
            PolicyConfig()
        assert any(
            "POLICY_REQUIRE_EVIDENCE_FOR_OUTBOUND_CLAIMS" in record.message
            for record in caplog.records
        ), "Expected a deprecation warning for the old env var name"
