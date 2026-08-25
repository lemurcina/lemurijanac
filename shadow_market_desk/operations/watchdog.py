from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import Enum


class ActionKind(str, Enum):
    COPILOT_ASSIGN = "copilot_assign"
    WORKFLOW_APPROVAL = "workflow_approval"
    PR_REVIEW = "pr_review"
    READY_FOR_REVIEW = "ready_for_review"
    MERGE = "merge"
    CI_RERUN = "ci_rerun"
    EXACT_SHA_VERIFY = "exact_sha_verify"
    DEPLOY_VERIFY = "deploy_verify"
    PAYMENT = "payment"
    CONTRACT = "contract"
    CHECKOUT = "checkout"
    IRREVERSIBLE_FINANCIAL = "irreversible_financial"


class ActionRisk(str, Enum):
    ROUTINE = "routine"
    OWNER_ONLY = "owner_only"


@dataclass(frozen=True)
class InterventionDecision:
    action: ActionKind
    risk: ActionRisk
    reason: str


@dataclass(frozen=True)
class EvidenceState:
    exact_sha: str | None = None
    ci_green: bool = False
    browser_proof: bool = False
    meaningful_output: str | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class WatchdogInput:
    agent_or_workflow: str
    current_state: str
    priority: int
    revenue_blocker_priority: int | None = None
    consecutive_no_progress_count: int = 0
    busy: bool = False
    failure_signature: str | None = None
    previous_failure_signature: str | None = None
    retry_count_same_signature: int = 0
    recovery_attempted: bool = False
    supervision_level: str = "trusted"
    evidence: EvidenceState = EvidenceState()


@dataclass(frozen=True)
class WatchdogFinding:
    code: str
    severity: str
    failure_tag: str
    reaction: str


@dataclass(frozen=True)
class WatchdogReport:
    agent_or_workflow: str
    current_state: str
    findings: tuple[WatchdogFinding, ...]
    escalation_required: bool
    supervision_level: str
    evidence_ref: str | None

    def as_dict(self) -> dict:
        data = asdict(self)
        data["findings"] = [asdict(item) for item in self.findings]
        return data


_OWNER_ONLY = {
    ActionKind.PAYMENT,
    ActionKind.CONTRACT,
    ActionKind.CHECKOUT,
    ActionKind.IRREVERSIBLE_FINANCIAL,
}


def classify_owner_intervention(action: ActionKind) -> InterventionDecision:
    if action in _OWNER_ONLY:
        return InterventionDecision(
            action,
            ActionRisk.OWNER_ONLY,
            "financial/legal/irreversible judgment",
        )
    return InterventionDecision(
        action,
        ActionRisk.ROUTINE,
        "safe operational action when normal evidence gates pass",
    )


def _raise_supervision(level: str) -> str:
    order = ["autonomous", "trusted", "supervised", "sandbox", "trainee"]
    try:
        idx = order.index(level)
    except ValueError:
        return "supervised"
    return order[min(idx + 1, len(order) - 1)]


def evaluate_watchdog(item: WatchdogInput) -> WatchdogReport:
    findings: list[WatchdogFinding] = []

    if item.consecutive_no_progress_count >= 2:
        findings.append(
            WatchdogFinding(
                "NO_PROGRESS_X2",
                "high",
                "no-progress",
                "change recovery strategy; increase supervision on recurrence",
            )
        )

    if item.busy and not item.evidence.meaningful_output:
        findings.append(
            WatchdogFinding(
                "BUSY_WITHOUT_OUTPUT",
                "medium",
                "vanity-activity",
                "require evidence artifact before next run",
            )
        )

    same_failure = (
        item.failure_signature
        and item.failure_signature == item.previous_failure_signature
        and item.retry_count_same_signature >= 1
    )
    if same_failure:
        findings.append(
            WatchdogFinding(
                "UNCHANGED_FAILURE_RETRY",
                "high",
                "unchanged-retry",
                "stop retry loop and choose a different recovery path",
            )
        )

    state = item.current_state.upper()
    if state in {"READY", "DONE"}:
        has_required_proof = bool(
            item.evidence.exact_sha
            and item.evidence.ci_green
            and item.evidence.evidence_ref
        )
        if state == "DONE":
            has_required_proof = has_required_proof and item.evidence.browser_proof
        if not has_required_proof:
            findings.append(
                WatchdogFinding(
                    "READY_DONE_WITHOUT_PROOF",
                    "critical",
                    "false-done",
                    "revert state to STALLED/FAILED until exact-SHA and route/browser proof exist",
                )
            )

    if (
        item.revenue_blocker_priority is not None
        and item.priority > item.revenue_blocker_priority
    ):
        findings.append(
            WatchdogFinding(
                "LOW_VALUE_DURING_REVENUE_BLOCKER",
                "high",
                "priority-conflict",
                "pause/requeue unless this work directly resolves the blocker",
            )
        )

    repeated = any(
        f.code in {"NO_PROGRESS_X2", "UNCHANGED_FAILURE_RETRY"} for f in findings
    )
    supervision = (
        _raise_supervision(item.supervision_level) if repeated else item.supervision_level
    )
    escalation = (
        bool(findings)
        and item.recovery_attempted
        and any(f.severity == "critical" for f in findings)
    )

    return WatchdogReport(
        agent_or_workflow=item.agent_or_workflow,
        current_state=item.current_state,
        findings=tuple(findings),
        escalation_required=escalation,
        supervision_level=supervision,
        evidence_ref=item.evidence.evidence_ref,
    )


def render_markdown_report(reports: Iterable[WatchdogReport]) -> str:
    rows = [
        "# Owner Friction + Watchdog",
        "",
        "| Work | State | Findings | Supervision | Evidence |",
        "|---|---|---|---|---|",
    ]
    for report in reports:
        findings = ", ".join(f.code for f in report.findings) or "PASS"
        rows.append(
            f"| {report.agent_or_workflow} | {report.current_state} | "
            f"{findings} | {report.supervision_level} | {report.evidence_ref or '-'} |"
        )
    return "\n".join(rows) + "\n"
