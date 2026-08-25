"""Policy data models."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class Outcome(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"


class ReasonCode(str, enum.Enum):
    # Capital
    EXCEEDS_ACTION_LIMIT = "EXCEEDS_ACTION_LIMIT"
    EXCEEDS_DAILY_LIMIT = "EXCEEDS_DAILY_LIMIT"
    EXCEEDS_STRATEGY_LIMIT = "EXCEEDS_STRATEGY_LIMIT"
    DEBT_FORBIDDEN = "DEBT_FORBIDDEN"
    SPECULATIVE_PURCHASE_BLOCKED = "SPECULATIVE_PURCHASE_BLOCKED"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"
    # Channel
    RECIPIENT_OPT_OUT = "RECIPIENT_OPT_OUT"
    ATTEMPT_LIMIT_REACHED = "ATTEMPT_LIMIT_REACHED"
    QUIET_HOURS = "QUIET_HOURS"
    JURISDICTION_BLOCKED = "JURISDICTION_BLOCKED"
    CHANNEL_NOT_ENABLED = "CHANNEL_NOT_ENABLED"
    SOURCE_TERMS_VIOLATION = "SOURCE_TERMS_VIOLATION"
    # Business
    BINDING_CONTRACT_FORBIDDEN = "BINDING_CONTRACT_FORBIDDEN"
    IMPERSONATION_FORBIDDEN = "IMPERSONATION_FORBIDDEN"
    UNSUPPORTED_FACTUAL_CLAIM = "UNSUPPORTED_FACTUAL_CLAIM"
    REGULATED_BROKERAGE_BLOCKED = "REGULATED_BROKERAGE_BLOCKED"
    # Evidence
    CLAIM_LACKS_EVIDENCE = "CLAIM_LACKS_EVIDENCE"
    # Config
    POLICY_DATA_MISSING = "POLICY_DATA_MISSING"
    # Allow
    OK = "OK"


@dataclass
class Decision:
    outcome: Outcome
    reason: ReasonCode
    details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AuditEvent:
    action: str
    decision: Decision
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
