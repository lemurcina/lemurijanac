from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class Signal(BaseModel):
    id: str
    source: str
    confidence: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=utcnow)


class OpportunityStatus(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"


class Opportunity(BaseModel):
    id: str
    strategy_id: str
    title: str
    status: OpportunityStatus
    estimated_value: float = Field(ge=0)
    created_at: datetime = Field(default_factory=utcnow)


class StrategyStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"


class Strategy(BaseModel):
    id: str
    name: str
    status: StrategyStatus
    capital_at_risk_limit: float = Field(ge=0)


class Allocation(BaseModel):
    id: str
    strategy_id: str
    share: float = Field(ge=0, le=1)
    active: bool = True


class OutcomeStatus(StrEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"


class Outcome(BaseModel):
    id: str
    opportunity_id: str
    status: OutcomeStatus
    realized_value: float | None = Field(default=None, ge=0)
    notes: str | None = None
    marked_at: datetime | None = None


class ChannelPolicyStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISABLED = "disabled"


class ChannelPolicy(BaseModel):
    id: str
    name: str
    status: ChannelPolicyStatus = ChannelPolicyStatus.PENDING
    max_send_per_day: int = Field(default=0, ge=0)


class AuditEvent(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int


class ErrorModel(BaseModel):
    error: str
    detail: str
    code: str


class SetCapitalAtRiskLimitRequest(BaseModel):
    limit: float = Field(ge=0, le=1_000_000)


class MarkOutcomeRequest(BaseModel):
    status: OutcomeStatus
    realized_value: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_realized_value(self) -> MarkOutcomeRequest:
        if self.status == OutcomeStatus.WON and self.realized_value is None:
            raise ValueError("realized_value is required when marking an outcome as won")
        if self.status == OutcomeStatus.PENDING:
            raise ValueError("status must be won or lost when marking an outcome")
        return self


class AppInfo(BaseModel):
    version: str


class Ack(BaseModel):
    ok: bool = True


class HealthResponse(BaseModel):
    status: str


class CapitalAtRiskLimitResponse(BaseModel):
    limit: float


class PauseResumeResponse(BaseModel):
    strategy: Strategy


class PolicyStateResponse(BaseModel):
    policy: ChannelPolicy


class OutcomeStateResponse(BaseModel):
    outcome: Outcome


class FilterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
