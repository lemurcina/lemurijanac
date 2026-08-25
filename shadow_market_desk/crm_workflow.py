from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4


class OpportunityState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VERIFIED = "VERIFIED"
    PRICED = "PRICED"
    OFFER_CREATED = "OFFER_CREATED"
    CONTACT_QUEUED = "CONTACT_QUEUED"
    CONTACTED = "CONTACTED"
    RESPONDED = "RESPONDED"
    NEGOTIATING = "NEGOTIATING"
    WON = "WON"
    LOST = "LOST"


ALLOWED_TRANSITIONS: dict[OpportunityState, set[OpportunityState]] = {
    OpportunityState.DISCOVERED: {OpportunityState.VERIFIED},
    OpportunityState.VERIFIED: {OpportunityState.PRICED},
    OpportunityState.PRICED: {OpportunityState.OFFER_CREATED},
    OpportunityState.OFFER_CREATED: {OpportunityState.CONTACT_QUEUED},
    OpportunityState.CONTACT_QUEUED: {OpportunityState.CONTACTED},
    OpportunityState.CONTACTED: {OpportunityState.RESPONDED, OpportunityState.LOST},
    OpportunityState.RESPONDED: {OpportunityState.NEGOTIATING, OpportunityState.WON, OpportunityState.LOST},
    OpportunityState.NEGOTIATING: {OpportunityState.WON, OpportunityState.LOST},
    OpportunityState.WON: set(),
    OpportunityState.LOST: set(),
}


@dataclass(frozen=True)
class EvidenceFact:
    fact: str
    source: str


@dataclass(frozen=True)
class InferredNeed:
    need: str
    confidence: float
    signal: str


@dataclass
class ContactPolicy:
    allowed_channels: set[str]
    quiet_hours: tuple[int, int] = (21, 8)
    max_attempts: int = 3
    jurisdiction_constraints: set[str] = field(default_factory=set)
    source_constraints: set[str] = field(default_factory=set)

    def permits(
        self,
        *,
        channel: str,
        now: datetime,
        attempts: int,
        opted_out: bool,
        jurisdiction: str | None,
        source: str | None,
    ) -> tuple[bool, str]:
        if opted_out:
            return False, "contact opted out"
        if channel not in self.allowed_channels:
            return False, "channel not allowed"
        if attempts >= self.max_attempts:
            return False, "max attempts reached"
        if self.jurisdiction_constraints and jurisdiction not in self.jurisdiction_constraints:
            return False, "jurisdiction not allowed"
        if self.source_constraints and source not in self.source_constraints:
            return False, "source not allowed"
        if self._is_quiet_hour(now.hour):
            return False, "quiet hours"
        return True, "allowed"

    def _is_quiet_hour(self, hour: int) -> bool:
        start, end = self.quiet_hours
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end


@dataclass(frozen=True)
class GeneratedMessage:
    text: str


class MessageGenerator:
    def generate(
        self,
        *,
        company_name: str,
        offer_summary: str,
        facts: Iterable[EvidenceFact],
        inferred_needs: Iterable[InferredNeed],
    ) -> GeneratedMessage:
        facts_section = "\n".join(
            f"- {fact.fact} (source: {fact.source})" for fact in facts
        ) or "- none provided"
        inferred_section = "\n".join(
            f"- {need.need} (confidence: {need.confidence:.2f}, signal: {need.signal})"
            for need in inferred_needs
        ) or "- none provided"
        text = (
            f"Hi {company_name} team,\n\n"
            f"We can help with: {offer_summary}\n\n"
            "Facts observed:\n"
            f"{facts_section}\n\n"
            "Possible needs (inference, not confirmed facts):\n"
            f"{inferred_section}\n"
        )
        return GeneratedMessage(text=text)


class UnsupportedClaimError(ValueError):
    pass


class ForbiddenClaimChecker:
    def __init__(self, forbidden_claims: Iterable[str] | None = None) -> None:
        self._forbidden_claims = {claim.lower() for claim in forbidden_claims or set()}

    def validate(self, message: GeneratedMessage) -> None:
        lowered = message.text.lower()
        for claim in self._forbidden_claims:
            if claim in lowered:
                raise UnsupportedClaimError(f"forbidden claim found: {claim}")


@dataclass
class Opportunity:
    opportunity_id: str
    company_name: str
    state: OpportunityState = OpportunityState.DISCOVERED
    contact_attempts: int = 0
    contacted_at: datetime | None = None
    opted_out: bool = False


@dataclass(frozen=True)
class TransitionEvent:
    opportunity_id: str
    from_state: OpportunityState
    to_state: OpportunityState
    timestamp: datetime
    reason: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    timestamp: datetime
    details: dict[str, str]


@dataclass
class AuditLog:
    transitions: list[TransitionEvent] = field(default_factory=list)
    events: list[AuditEvent] = field(default_factory=list)

    def record_transition(
        self,
        *,
        opportunity_id: str,
        from_state: OpportunityState,
        to_state: OpportunityState,
        reason: str,
        now: datetime,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.transitions.append(
            TransitionEvent(
                opportunity_id=opportunity_id,
                from_state=from_state,
                to_state=to_state,
                timestamp=now,
                reason=reason,
                metadata=metadata or {},
            )
        )

    def record_event(self, *, event_type: str, now: datetime, details: dict[str, str]) -> None:
        self.events.append(AuditEvent(event_type=event_type, timestamp=now, details=details))


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    text: str
    timestamp: datetime


@dataclass
class ConversationMemory:
    threads: dict[tuple[str, str], list[ConversationTurn]] = field(
        default_factory=dict, init=False, repr=False
    )

    def add_turn(
        self,
        *,
        company_name: str,
        opportunity_id: str,
        role: str,
        text: str,
        timestamp: datetime,
    ) -> None:
        key = (company_name, opportunity_id)
        self.threads.setdefault(key, []).append(ConversationTurn(role=role, text=text, timestamp=timestamp))

    def get_history(self, *, company_name: str, opportunity_id: str) -> list[ConversationTurn]:
        return list(self.threads.get((company_name, opportunity_id), []))


@dataclass(frozen=True)
class SandboxSendRecord:
    send_id: str
    channel: str
    timestamp: datetime
    message: str
    opportunity_id: str


@dataclass
class SandboxTransport:
    sends: list[SandboxSendRecord] = field(default_factory=list)

    def send(
        self,
        *,
        opportunity_id: str,
        channel: str,
        timestamp: datetime,
        message: GeneratedMessage,
    ) -> SandboxSendRecord:
        record = SandboxSendRecord(
            send_id=str(uuid4()),
            channel=channel,
            timestamp=timestamp,
            message=message.text,
            opportunity_id=opportunity_id,
        )
        self.sends.append(record)
        return record


@dataclass(frozen=True)
class FollowUpTask:
    idempotency_key: str
    opportunity_id: str
    scheduled_for: datetime
    channel: str
    message: str


@dataclass
class FollowUpScheduler:
    tasks: dict[str, FollowUpTask] = field(default_factory=dict, init=False, repr=False)

    def has_task(self, idempotency_key: str) -> bool:
        return idempotency_key in self.tasks

    def schedule(
        self,
        *,
        idempotency_key: str,
        opportunity_id: str,
        base_time: datetime,
        delay: timedelta,
        channel: str,
        message: str,
    ) -> FollowUpTask:
        existing = self.tasks.get(idempotency_key)
        if existing:
            return existing
        task = FollowUpTask(
            idempotency_key=idempotency_key,
            opportunity_id=opportunity_id,
            scheduled_for=base_time + delay,
            channel=channel,
            message=message,
        )
        self.tasks[idempotency_key] = task
        return task

    def all_tasks(self) -> list[FollowUpTask]:
        return list(self.tasks.values())


class ReplyType(str, Enum):
    POSITIVE = "positive"
    QUESTION = "question"
    OBJECTION = "objection"
    OPT_OUT = "opt-out"
    WRONG_PERSON = "wrong person"
    NO_FIT = "no-fit"


class ReplyClassifier:
    def classify(self, reply_text: str) -> ReplyType:
        normalized = reply_text.lower()
        if any(token in normalized for token in ("unsubscribe", "stop contacting", "opt out")):
            return ReplyType.OPT_OUT
        if any(token in normalized for token in ("wrong person", "not the right contact")):
            return ReplyType.WRONG_PERSON
        if any(token in normalized for token in ("not a fit", "no fit", "no budget")):
            return ReplyType.NO_FIT
        if "?" in reply_text:
            return ReplyType.QUESTION
        if any(token in normalized for token in ("too expensive", "already have", "not interested")):
            return ReplyType.OBJECTION
        return ReplyType.POSITIVE


class PolicyViolationError(ValueError):
    pass


@dataclass
class CRMWorkflow:
    policy: ContactPolicy
    message_generator: MessageGenerator
    claim_checker: ForbiddenClaimChecker
    transport: SandboxTransport
    scheduler: FollowUpScheduler
    audit_log: AuditLog
    memory: ConversationMemory
    classifier: ReplyClassifier = field(default_factory=ReplyClassifier)

    def transition(
        self,
        opportunity: Opportunity,
        to_state: OpportunityState,
        *,
        reason: str,
        now: datetime,
        metadata: dict[str, str] | None = None,
    ) -> None:
        allowed = ALLOWED_TRANSITIONS.get(opportunity.state, set())
        if to_state not in allowed:
            raise ValueError(f"invalid transition {opportunity.state} -> {to_state}")
        from_state = opportunity.state
        opportunity.state = to_state
        self.audit_log.record_transition(
            opportunity_id=opportunity.opportunity_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            now=now,
            metadata=metadata,
        )

    def send_outreach(
        self,
        *,
        opportunity: Opportunity,
        channel: str,
        now: datetime,
        jurisdiction: str | None,
        source: str | None,
        offer_summary: str,
        facts: Iterable[EvidenceFact],
        inferred_needs: Iterable[InferredNeed],
    ) -> SandboxSendRecord:
        allowed, reason = self.policy.permits(
            channel=channel,
            now=now,
            attempts=opportunity.contact_attempts,
            opted_out=opportunity.opted_out,
            jurisdiction=jurisdiction,
            source=source,
        )
        if not allowed:
            raise PolicyViolationError(reason)
        message = self.message_generator.generate(
            company_name=opportunity.company_name,
            offer_summary=offer_summary,
            facts=facts,
            inferred_needs=inferred_needs,
        )
        self.claim_checker.validate(message)

        for current_state, next_state, reason_text in (
            (OpportunityState.PRICED, OpportunityState.OFFER_CREATED, "offer prepared"),
            (OpportunityState.OFFER_CREATED, OpportunityState.CONTACT_QUEUED, "contact queued"),
        ):
            if opportunity.state == current_state:
                self.transition(opportunity, next_state, reason=reason_text, now=now)
        if opportunity.state not in {OpportunityState.CONTACT_QUEUED, OpportunityState.CONTACTED}:
            raise ValueError("opportunity must be in CONTACT_QUEUED or CONTACTED state before send")

        send = self.transport.send(
            opportunity_id=opportunity.opportunity_id,
            channel=channel,
            timestamp=now,
            message=message,
        )
        opportunity.contact_attempts += 1
        opportunity.contacted_at = now
        self.memory.add_turn(
            company_name=opportunity.company_name,
            opportunity_id=opportunity.opportunity_id,
            role="agent",
            text=message.text,
            timestamp=now,
        )
        if opportunity.state == OpportunityState.CONTACT_QUEUED:
            self.transition(opportunity, OpportunityState.CONTACTED, reason="sandbox send recorded", now=now)
        self.audit_log.record_event(
            event_type="SANDBOX_SEND_RECORDED",
            now=now,
            details={"send_id": send.send_id, "channel": send.channel},
        )
        return send

    def schedule_follow_up(
        self,
        *,
        opportunity: Opportunity,
        idempotency_key: str,
        base_time: datetime,
        delay: timedelta,
        channel: str,
        message: str,
    ) -> FollowUpTask:
        is_new_task = not self.scheduler.has_task(idempotency_key)
        task = self.scheduler.schedule(
            idempotency_key=idempotency_key,
            opportunity_id=opportunity.opportunity_id,
            base_time=base_time,
            delay=delay,
            channel=channel,
            message=message,
        )
        if is_new_task:
            self.audit_log.record_event(
                event_type="FOLLOW_UP_SCHEDULED",
                now=base_time,
                details={"idempotency_key": idempotency_key, "opportunity_id": opportunity.opportunity_id},
            )
        return task

    def process_reply(self, *, opportunity: Opportunity, now: datetime, reply_text: str) -> ReplyType:
        reply_type = self.classifier.classify(reply_text)
        self.memory.add_turn(
            company_name=opportunity.company_name,
            opportunity_id=opportunity.opportunity_id,
            role="contact",
            text=reply_text,
            timestamp=now,
        )
        if opportunity.state == OpportunityState.CONTACTED:
            self.transition(opportunity, OpportunityState.RESPONDED, reason="reply received", now=now)

        if reply_type == ReplyType.OPT_OUT:
            opportunity.opted_out = True
            if OpportunityState.LOST in ALLOWED_TRANSITIONS.get(opportunity.state, set()):
                self.transition(opportunity, OpportunityState.LOST, reason="contact opted out", now=now)
        elif reply_type in {ReplyType.WRONG_PERSON, ReplyType.NO_FIT}:
            if OpportunityState.LOST in ALLOWED_TRANSITIONS.get(opportunity.state, set()):
                self.transition(opportunity, OpportunityState.LOST, reason=f"reply={reply_type.value}", now=now)
        elif reply_type in {ReplyType.OBJECTION, ReplyType.POSITIVE}:
            if OpportunityState.NEGOTIATING in ALLOWED_TRANSITIONS.get(opportunity.state, set()):
                self.transition(opportunity, OpportunityState.NEGOTIATING, reason=f"reply={reply_type.value}", now=now)
        self.audit_log.record_event(
            event_type="REPLY_CLASSIFIED",
            now=now,
            details={"type": reply_type.value},
        )
        return reply_type
