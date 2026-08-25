"""Policy configuration – operator-owned rules loaded from environment / YAML.

Operators can relax (or tighten) any rule by setting the corresponding
environment variable *or* by supplying a YAML file path in the
``POLICY_CONFIG_PATH`` environment variable.  No code edits are required.

## Safety-critical relaxation flags

Flags that weaken the default-deny safety posture (allow_debt,
allow_speculative_purchases, allow_binding_contracts,
allow_licensed_professional_impersonation, allow_regulated_brokerage,
require_evidence_for_outbound_claims=false) require **explicit operator
intent** when set via environment variable.  Setting them to a generic
truthy value (``1``, ``true``, ``yes``) is intentionally *ignored* and
the safe default is preserved.

To relax a safety flag via env var, the value must be the exact
acknowledgement token ``I_ACCEPT_RISK``::

    # Wrong – ignored, safe default kept:
    export POLICY_ALLOW_SPECULATIVE_PURCHASES=true

    # Correct – operator explicitly accepts the risk:
    export POLICY_ALLOW_SPECULATIVE_PURCHASES=I_ACCEPT_RISK

This design prevents stale variables inherited from developer shells or
copied from examples from silently weakening the production safety posture.

YAML-based configuration (``POLICY_CONFIG_PATH``) does not require the
acknowledgement token because the YAML file is an intentional artefact
that operators must create and deploy explicitly.

## Example YAML (save as e.g. ``policy.yaml`` and set
``POLICY_CONFIG_PATH=/path/to/policy.yaml``):

    capital:
      per_action_limit: 500.00
      daily_limit: 2000.00
      strategy_limit: 5000.00
      allow_debt: false
      allow_speculative_purchases: false

    channel:
      enabled_channels: ["email", "sms"]
      max_attempts_per_recipient: 3
      quiet_hours_start: 21   # 21:00 local
      quiet_hours_end: 8      # 08:00 local
      blocked_jurisdictions: []

    business:
      allow_binding_contracts: false
      allow_licensed_professional_impersonation: false
      allow_regulated_brokerage: false

    evidence:
      require_evidence_for_outbound_claims: true

To disable the evidence gate via env var (requires acknowledgement)::

    export POLICY_DISABLE_EVIDENCE_GATE=I_ACCEPT_RISK
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


# Acknowledgement token required to relax a safety-critical flag via env var.
_RISK_ACK = "I_ACCEPT_RISK"


def _env_safety_relax(name: str) -> bool:
    """Return True only when the env var is set to the explicit risk-acknowledgement token.

    Generic truthy values (``true``, ``1``, ``yes``) are intentionally ignored
    so that stale variables inherited from developer shells or copied from
    documentation cannot silently weaken the production safety posture.

    Usage::

        export POLICY_ALLOW_SPECULATIVE_PURCHASES=I_ACCEPT_RISK
    """
    raw = os.environ.get(name)
    return raw is not None and raw.strip() == _RISK_ACK


def _env_safety_tighten(name: str, default: bool) -> bool:
    """Inverse of _env_safety_relax for flags where the default is True (tightened).

    The flag stays at its ``default`` unless the operator explicitly relaxes it
    by setting the env var to ``I_ACCEPT_RISK``.  Any other value (including
    ``false``, ``0``) is treated as the safe default to prevent accidental
    weakening via copy-paste or stale variables.
    """
    if _env_safety_relax(name):
        return not default
    return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


@dataclass
class CapitalConfig:
    per_action_limit: float = field(
        default_factory=lambda: _env_float("POLICY_PER_ACTION_LIMIT", 100.0)
    )
    daily_limit: float = field(
        default_factory=lambda: _env_float("POLICY_DAILY_LIMIT", 500.0)
    )
    strategy_limit: float = field(
        default_factory=lambda: _env_float("POLICY_STRATEGY_LIMIT", 1000.0)
    )
    allow_debt: bool = field(
        # Safety-critical: requires I_ACCEPT_RISK, not a generic truthy value.
        default_factory=lambda: _env_safety_relax("POLICY_ALLOW_DEBT")
    )
    allow_speculative_purchases: bool = field(
        # Safety-critical: requires I_ACCEPT_RISK, not a generic truthy value.
        default_factory=lambda: _env_safety_relax("POLICY_ALLOW_SPECULATIVE_PURCHASES")
    )


@dataclass
class ChannelConfig:
    enabled_channels: list[str] = field(
        default_factory=lambda: _env_list("POLICY_ENABLED_CHANNELS", [])
    )
    max_attempts_per_recipient: int = field(
        default_factory=lambda: _env_int("POLICY_MAX_ATTEMPTS_PER_RECIPIENT", 3)
    )
    quiet_hours_start: int = field(
        default_factory=lambda: _env_int("POLICY_QUIET_HOURS_START", 21)
    )
    quiet_hours_end: int = field(
        default_factory=lambda: _env_int("POLICY_QUIET_HOURS_END", 8)
    )
    blocked_jurisdictions: list[str] = field(
        default_factory=lambda: _env_list("POLICY_BLOCKED_JURISDICTIONS", [])
    )


@dataclass
class BusinessConfig:
    allow_binding_contracts: bool = field(
        # Safety-critical: requires I_ACCEPT_RISK, not a generic truthy value.
        default_factory=lambda: _env_safety_relax("POLICY_ALLOW_BINDING_CONTRACTS")
    )
    allow_licensed_professional_impersonation: bool = field(
        # Safety-critical: requires I_ACCEPT_RISK, not a generic truthy value.
        default_factory=lambda: _env_safety_relax(
            "POLICY_ALLOW_LICENSED_PROFESSIONAL_IMPERSONATION"
        )
    )
    allow_regulated_brokerage: bool = field(
        # Safety-critical: requires I_ACCEPT_RISK, not a generic truthy value.
        default_factory=lambda: _env_safety_relax("POLICY_ALLOW_REGULATED_BROKERAGE")
    )


@dataclass
class EvidenceConfig:
    require_evidence_for_outbound_claims: bool = field(
        # Safety-critical: disabling evidence gate requires I_ACCEPT_RISK.
        # The old env var POLICY_REQUIRE_EVIDENCE_FOR_OUTBOUND_CLAIMS is no
        # longer read; a warning is emitted if it is still present so operators
        # know their configuration must be migrated.
        default_factory=lambda: _env_safety_tighten(
            "POLICY_DISABLE_EVIDENCE_GATE", default=True
        )
    )

    def __post_init__(self) -> None:
        import logging as _logging

        _old = "POLICY_REQUIRE_EVIDENCE_FOR_OUTBOUND_CLAIMS"
        if os.environ.get(_old) is not None:
            _logging.getLogger(__name__).warning(
                "Env var %s is no longer read. "
                "To disable the evidence gate set POLICY_DISABLE_EVIDENCE_GATE=I_ACCEPT_RISK.",
                _old,
            )


@dataclass
class PolicyConfig:
    capital: CapitalConfig = field(default_factory=CapitalConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    business: BusinessConfig = field(default_factory=BusinessConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)

    @classmethod
    def from_yaml(cls, path: str) -> PolicyConfig:
        """Load config from a YAML file.  Requires PyYAML."""
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Install PyYAML to load policy config from a file.") from exc

        with open(path, "r") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        def _get(section: str, key: str, default: Any) -> Any:
            return raw.get(section, {}).get(key, default)

        _cap_d = CapitalConfig()
        capital = CapitalConfig(
            per_action_limit=_get("capital", "per_action_limit", _cap_d.per_action_limit),
            daily_limit=_get("capital", "daily_limit", _cap_d.daily_limit),
            strategy_limit=_get("capital", "strategy_limit", _cap_d.strategy_limit),
            allow_debt=_get("capital", "allow_debt", _cap_d.allow_debt),
            allow_speculative_purchases=_get(
                "capital", "allow_speculative_purchases", _cap_d.allow_speculative_purchases,
            ),
        )
        _chan_d = ChannelConfig()
        channel = ChannelConfig(
            enabled_channels=_get("channel", "enabled_channels", _chan_d.enabled_channels),
            max_attempts_per_recipient=_get(
                "channel", "max_attempts_per_recipient", _chan_d.max_attempts_per_recipient,
            ),
            quiet_hours_start=_get("channel", "quiet_hours_start", _chan_d.quiet_hours_start),
            quiet_hours_end=_get("channel", "quiet_hours_end", _chan_d.quiet_hours_end),
            blocked_jurisdictions=_get(
                "channel", "blocked_jurisdictions", _chan_d.blocked_jurisdictions
            ),
        )
        _biz_d = BusinessConfig()
        business = BusinessConfig(
            allow_binding_contracts=_get(
                "business", "allow_binding_contracts", _biz_d.allow_binding_contracts,
            ),
            allow_licensed_professional_impersonation=_get(
                "business", "allow_licensed_professional_impersonation",
                _biz_d.allow_licensed_professional_impersonation,
            ),
            allow_regulated_brokerage=_get(
                "business", "allow_regulated_brokerage", _biz_d.allow_regulated_brokerage,
            ),
        )
        _ev_d = EvidenceConfig()
        evidence = EvidenceConfig(
            require_evidence_for_outbound_claims=_get(
                "evidence", "require_evidence_for_outbound_claims",
                _ev_d.require_evidence_for_outbound_claims,
            )
        )
        return cls(capital=capital, channel=channel, business=business, evidence=evidence)

    @classmethod
    def load(cls) -> PolicyConfig:
        """Load from YAML if ``POLICY_CONFIG_PATH`` is set, else use env defaults."""
        path = os.environ.get("POLICY_CONFIG_PATH")
        if path:
            return cls.from_yaml(path)
        return cls()
