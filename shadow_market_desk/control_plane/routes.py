from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from policy import Outcome as PolicyOutcome

from .dependencies import get_repositories
from .models import (
    Allocation,
    AuditEvent,
    CapitalAtRiskLimitResponse,
    ChannelPolicyStatus,
    ErrorModel,
    FilterParams,
    MarkOutcomeRequest,
    Opportunity,
    OpportunityStatus,
    Outcome,
    OutcomeStateResponse,
    OutcomeStatus,
    Page,
    PauseResumeResponse,
    PolicyStateResponse,
    SetCapitalAtRiskLimitRequest,
    Signal,
    Strategy,
    StrategyStatus,
)
from .repositories import RepositoryBundle

router = APIRouter(prefix="/api/v1")


def _page_params(offset: int, limit: int) -> FilterParams:
    return FilterParams(offset=offset, limit=limit)


def _policy_metadata(outcome: PolicyOutcome, reason: str, detail: str) -> dict[str, str]:
    return {"policy_outcome": outcome.value, "policy_reason": reason, "policy_detail": detail}


@router.get(
    "/signals",
    response_model=Page[Signal],
    tags=["signals"],
    responses={400: {"model": ErrorModel}},
)
def list_signals(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[Signal]:
    params = _page_params(offset, limit)
    items, total = repos.signals.list(offset=params.offset, limit=params.limit, min_confidence=min_confidence)
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.get("/opportunities", response_model=Page[Opportunity], tags=["opportunities"])
def list_opportunities(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: OpportunityStatus | None = None,
    strategy_id: str | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[Opportunity]:
    params = _page_params(offset, limit)
    items, total = repos.opportunities.list(
        offset=params.offset,
        limit=params.limit,
        status=status,
        strategy_id=strategy_id,
    )
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.get("/strategies", response_model=Page[Strategy], tags=["strategies"])
def list_strategies(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: StrategyStatus | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[Strategy]:
    params = _page_params(offset, limit)
    items, total = repos.strategies.list(offset=params.offset, limit=params.limit, status=status)
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.get("/allocations", response_model=Page[Allocation], tags=["allocations"])
def list_allocations(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    strategy_id: str | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[Allocation]:
    params = _page_params(offset, limit)
    items, total = repos.allocations.list(offset=params.offset, limit=params.limit, strategy_id=strategy_id)
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.get("/outcomes", response_model=Page[Outcome], tags=["outcomes"])
def list_outcomes(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: OutcomeStatus | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[Outcome]:
    params = _page_params(offset, limit)
    items, total = repos.outcomes.list(offset=params.offset, limit=params.limit, status=status)
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.get("/audit-events", response_model=Page[AuditEvent], tags=["audit"])
def list_audit_events(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    repos: RepositoryBundle = Depends(get_repositories),
) -> Page[AuditEvent]:
    params = _page_params(offset, limit)
    items, total = repos.audits.list(offset=params.offset, limit=params.limit, action=action)
    return Page(items=items, total=total, offset=params.offset, limit=params.limit)


@router.post(
    "/strategies/{strategy_id}/pause",
    response_model=PauseResumeResponse,
    tags=["controls"],
    responses={404: {"model": ErrorModel}},
)
def pause_strategy(strategy_id: str, repos: RepositoryBundle = Depends(get_repositories)) -> PauseResumeResponse:
    strategy = repos.strategies.get(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy not found")
    strategy.status = StrategyStatus.PAUSED
    repos.strategies.upsert(strategy)
    repos.audits.add(
        action="strategy.pause",
        resource_type="strategy",
        resource_id=strategy_id,
        metadata={"status": str(strategy.status)},
    )
    return PauseResumeResponse(strategy=strategy)


@router.post(
    "/strategies/{strategy_id}/resume",
    response_model=PauseResumeResponse,
    tags=["controls"],
    responses={404: {"model": ErrorModel}},
)
def resume_strategy(strategy_id: str, repos: RepositoryBundle = Depends(get_repositories)) -> PauseResumeResponse:
    strategy = repos.strategies.get(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="strategy not found")
    strategy.status = StrategyStatus.RUNNING
    repos.strategies.upsert(strategy)
    repos.audits.add(
        action="strategy.resume",
        resource_type="strategy",
        resource_id=strategy_id,
        metadata={"status": str(strategy.status)},
    )
    return PauseResumeResponse(strategy=strategy)


@router.put(
    "/controls/capital-at-risk-limit",
    response_model=CapitalAtRiskLimitResponse,
    tags=["controls"],
)
def set_capital_at_risk_limit(
    request: SetCapitalAtRiskLimitRequest,
    repos: RepositoryBundle = Depends(get_repositories),
) -> CapitalAtRiskLimitResponse:
    decision = repos.policy_engine.check_capital(
        action="controls.set_capital_at_risk_limit",
        amount=request.limit,
        daily_spent=repos.capital_daily_spent,
        strategy_spent=repos.capital_strategy_spent,
        context={"resource_type": "controls", "resource_id": "capital-at-risk-limit"},
    )
    if decision.outcome is not PolicyOutcome.ALLOW:
        repos.audits.add(
            action="controls.set_capital_at_risk_limit.denied",
            resource_type="controls",
            resource_id="capital-at-risk-limit",
            metadata=_policy_metadata(
                outcome=decision.outcome,
                reason=decision.reason.value,
                detail=decision.details,
            ),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=decision.details)

    limit = repos.set_capital_at_risk_limit(request.limit)
    repos.audits.add(
        action="controls.set_capital_at_risk_limit",
        resource_type="controls",
        resource_id="capital-at-risk-limit",
        metadata={
            "limit": f"{limit:.2f}",
            **_policy_metadata(
                outcome=decision.outcome,
                reason=decision.reason.value,
                detail=decision.details,
            ),
        },
    )
    return CapitalAtRiskLimitResponse(limit=limit)


@router.post(
    "/outcomes/{outcome_id}/mark",
    response_model=OutcomeStateResponse,
    tags=["controls"],
    responses={404: {"model": ErrorModel}},
)
def mark_outcome(
    outcome_id: str,
    request: MarkOutcomeRequest,
    repos: RepositoryBundle = Depends(get_repositories),
) -> OutcomeStateResponse:
    outcome = repos.outcomes.get(outcome_id)
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="outcome not found")
    outcome.status = request.status
    outcome.realized_value = request.realized_value
    outcome.notes = request.notes
    outcome.marked_at = datetime.now(UTC)
    repos.outcomes.upsert(outcome)
    repos.audits.add(
        action="outcome.mark",
        resource_type="outcome",
        resource_id=outcome_id,
        metadata={"status": str(outcome.status)},
    )
    return OutcomeStateResponse(outcome=outcome)


@router.post(
    "/channel-policies/{policy_id}/approve",
    response_model=PolicyStateResponse,
    tags=["controls"],
    responses={404: {"model": ErrorModel}, 409: {"model": ErrorModel}},
)
def approve_channel_policy(
    policy_id: str,
    repos: RepositoryBundle = Depends(get_repositories),
) -> PolicyStateResponse:
    policy = repos.channel_policies.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel policy not found")
    if policy.status == ChannelPolicyStatus.DISABLED:
        repos.audits.add(
            action="channel_policy.approve.denied",
            resource_type="channel_policy",
            resource_id=policy_id,
            metadata={"reason": "disabled policy cannot be approved"},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="disabled policy cannot be approved")

    decision = repos.policy_engine.check_channel(
        channel=policy.name,
        recipient_id=f"policy:{policy_id}",
        attempt_count=0,
        local_hour=12,
        context={"resource_type": "channel_policy", "resource_id": policy_id},
    )
    if decision.outcome is not PolicyOutcome.ALLOW:
        repos.audits.add(
            action="channel_policy.approve.denied",
            resource_type="channel_policy",
            resource_id=policy_id,
            metadata=_policy_metadata(
                outcome=decision.outcome,
                reason=decision.reason.value,
                detail=decision.details,
            ),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=decision.details)

    policy.status = ChannelPolicyStatus.APPROVED
    repos.channel_policies.upsert(policy)
    repos.audits.add(
        action="channel_policy.approve",
        resource_type="channel_policy",
        resource_id=policy_id,
        metadata={
            "status": str(policy.status),
            **_policy_metadata(
                outcome=decision.outcome,
                reason=decision.reason.value,
                detail=decision.details,
            ),
        },
    )
    return PolicyStateResponse(policy=policy)


@router.post(
    "/channel-policies/{policy_id}/disable",
    response_model=PolicyStateResponse,
    tags=["controls"],
    responses={404: {"model": ErrorModel}},
)
def disable_channel_policy(
    policy_id: str,
    repos: RepositoryBundle = Depends(get_repositories),
) -> PolicyStateResponse:
    policy = repos.channel_policies.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel policy not found")
    policy.status = ChannelPolicyStatus.DISABLED
    repos.channel_policies.upsert(policy)
    repos.audits.add(
        action="channel_policy.disable",
        resource_type="channel_policy",
        resource_id=policy_id,
        metadata={"status": str(policy.status)},
    )
    return PolicyStateResponse(policy=policy)
