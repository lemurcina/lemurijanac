from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shadow_market_desk.crm_workflow import (
    AuditLog,
    ContactPolicy,
    ConversationMemory,
    CRMWorkflow,
    EvidenceFact,
    FollowUpScheduler,
    ForbiddenClaimChecker,
    InferredNeed,
    MessageGenerator,
    Opportunity,
    OpportunityState,
    PolicyViolationError,
    SandboxTransport,
    UnsupportedClaimError,
)


def _workflow(*, max_attempts: int = 3, forbidden_claims: set[str] | None = None) -> CRMWorkflow:
    return CRMWorkflow(
        policy=ContactPolicy(
            allowed_channels={"email"},
            quiet_hours=(0, 0),
            max_attempts=max_attempts,
            jurisdiction_constraints={"US-CA"},
            source_constraints={"public_permit_feed"},
        ),
        message_generator=MessageGenerator(),
        claim_checker=ForbiddenClaimChecker(forbidden_claims=forbidden_claims),
        transport=SandboxTransport(),
        scheduler=FollowUpScheduler(),
        audit_log=AuditLog(),
        memory=ConversationMemory(),
    )


def _priced_opportunity() -> Opportunity:
    return Opportunity(
        opportunity_id="opp-1",
        company_name="Acme Builders",
        state=OpportunityState.PRICED,
    )


def test_opt_out_blocks_future_contacts() -> None:
    workflow = _workflow()
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    workflow.send_outreach(
        opportunity=opportunity,
        channel="email",
        now=now,
        jurisdiction="US-CA",
        source="public_permit_feed",
        offer_summary="fast permit-closeout support",
        facts=[EvidenceFact(fact="Tenant improvement permit #123 is active", source="city portal")],
        inferred_needs=[InferredNeed(need="inspection scheduling help", confidence=0.78, signal="permit age")],
    )
    workflow.process_reply(
        opportunity=opportunity,
        now=now + timedelta(minutes=30),
        reply_text="Please unsubscribe and stop contacting us.",
    )

    with pytest.raises(PolicyViolationError, match="contact opted out"):
        workflow.send_outreach(
            opportunity=opportunity,
            channel="email",
            now=now + timedelta(days=1),
            jurisdiction="US-CA",
            source="public_permit_feed",
            offer_summary="follow-up",
            facts=[],
            inferred_needs=[],
        )


def test_max_attempt_limit_enforced() -> None:
    workflow = _workflow(max_attempts=2)
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    workflow.send_outreach(
        opportunity=opportunity,
        channel="email",
        now=now,
        jurisdiction="US-CA",
        source="public_permit_feed",
        offer_summary="first offer",
        facts=[EvidenceFact(fact="Permit posted this week", source="city portal")],
        inferred_needs=[],
    )
    workflow.send_outreach(
        opportunity=opportunity,
        channel="email",
        now=now + timedelta(hours=1),
        jurisdiction="US-CA",
        source="public_permit_feed",
        offer_summary="second offer",
        facts=[],
        inferred_needs=[],
    )

    with pytest.raises(PolicyViolationError):
        workflow.send_outreach(
            opportunity=opportunity,
            channel="email",
            now=now + timedelta(hours=2),
            jurisdiction="US-CA",
            source="public_permit_feed",
            offer_summary="third attempt",
            facts=[],
            inferred_needs=[],
        )


def test_follow_up_scheduler_is_idempotent() -> None:
    workflow = _workflow()
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    task1 = workflow.schedule_follow_up(
        opportunity=opportunity,
        idempotency_key="opp-1-attempt-1",
        base_time=now,
        delay=timedelta(hours=24),
        channel="email",
        message="Just checking in.",
    )
    task2 = workflow.schedule_follow_up(
        opportunity=opportunity,
        idempotency_key="opp-1-attempt-1",
        base_time=now,
        delay=timedelta(hours=24),
        channel="email",
        message="Just checking in.",
    )

    assert task1 is task2
    assert len(workflow.scheduler.all_tasks()) == 1
    follow_up_events = [event for event in workflow.audit_log.events if event.event_type == "FOLLOW_UP_SCHEDULED"]
    assert len(follow_up_events) == 1


def test_forbidden_claims_are_blocked() -> None:
    workflow = _workflow(forbidden_claims={"guaranteed results"})
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    with pytest.raises(UnsupportedClaimError):
        workflow.send_outreach(
            opportunity=opportunity,
            channel="email",
            now=now,
            jurisdiction="US-CA",
            source="public_permit_feed",
            offer_summary="guaranteed results for inspection turnaround",
            facts=[EvidenceFact(fact="Permit was filed yesterday", source="city portal")],
            inferred_needs=[],
        )
    assert opportunity.state == OpportunityState.PRICED
    assert workflow.audit_log.transitions == []


def test_message_separates_facts_and_inference() -> None:
    workflow = _workflow()
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    send = workflow.send_outreach(
        opportunity=opportunity,
        channel="email",
        now=now,
        jurisdiction="US-CA",
        source="public_permit_feed",
        offer_summary="permit-closeout support",
        facts=[EvidenceFact(fact="Permit #A100 is open", source="city portal")],
        inferred_needs=[InferredNeed(need="faster inspection prep", confidence=0.64, signal="open status age")],
    )

    assert "Facts observed:" in send.message
    assert "Possible needs (inference, not confirmed facts):" in send.message


def test_every_transition_is_audited() -> None:
    workflow = _workflow()
    opportunity = _priced_opportunity()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    workflow.send_outreach(
        opportunity=opportunity,
        channel="email",
        now=now,
        jurisdiction="US-CA",
        source="public_permit_feed",
        offer_summary="permit-closeout support",
        facts=[EvidenceFact(fact="Permit #A100 is open", source="city portal")],
        inferred_needs=[],
    )
    workflow.process_reply(
        opportunity=opportunity,
        now=now + timedelta(minutes=5),
        reply_text="Interested and ready to discuss timeline.",
    )

    path = [(t.from_state, t.to_state) for t in workflow.audit_log.transitions]
    assert path == [
        (OpportunityState.PRICED, OpportunityState.OFFER_CREATED),
        (OpportunityState.OFFER_CREATED, OpportunityState.CONTACT_QUEUED),
        (OpportunityState.CONTACT_QUEUED, OpportunityState.CONTACTED),
        (OpportunityState.CONTACTED, OpportunityState.RESPONDED),
        (OpportunityState.RESPONDED, OpportunityState.NEGOTIATING),
    ]
