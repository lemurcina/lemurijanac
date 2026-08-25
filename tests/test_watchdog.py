from shadow_market_desk.operations.watchdog import (
    ActionKind,
    ActionRisk,
    EvidenceState,
    WatchdogInput,
    classify_owner_intervention,
    evaluate_watchdog,
    render_markdown_report,
)


def codes(report):
    return {f.code for f in report.findings}


def test_routine_and_owner_only_classification():
    assert classify_owner_intervention(ActionKind.COPILOT_ASSIGN).risk is ActionRisk.ROUTINE
    assert classify_owner_intervention(ActionKind.WORKFLOW_APPROVAL).risk is ActionRisk.ROUTINE
    assert classify_owner_intervention(ActionKind.DEPLOY_VERIFY).risk is ActionRisk.ROUTINE
    assert classify_owner_intervention(ActionKind.PAYMENT).risk is ActionRisk.OWNER_ONLY
    assert classify_owner_intervention(ActionKind.CONTRACT).risk is ActionRisk.OWNER_ONLY
    assert classify_owner_intervention(ActionKind.CHECKOUT).risk is ActionRisk.OWNER_ONLY


def test_no_progress_x2_demotes_supervision():
    report = evaluate_watchdog(WatchdogInput("copilot-agent", "STALLED", 1, consecutive_no_progress_count=2))
    assert "NO_PROGRESS_X2" in codes(report)
    assert report.supervision_level == "supervised"


def test_busy_without_output_is_flagged():
    report = evaluate_watchdog(WatchdogInput("integrator", "RUNNING", 1, busy=True))
    assert "BUSY_WITHOUT_OUTPUT" in codes(report)


def test_ready_without_exact_sha_proof_is_rejected():
    report = evaluate_watchdog(WatchdogInput("ci", "READY", 1, evidence=EvidenceState(ci_green=True)))
    assert "READY_DONE_WITHOUT_PROOF" in codes(report)


def test_done_without_browser_proof_is_rejected():
    report = evaluate_watchdog(
        WatchdogInput(
            "vercel",
            "DONE",
            1,
            evidence=EvidenceState(exact_sha="abc", ci_green=True, evidence_ref="run:1", browser_proof=False),
        )
    )
    assert "READY_DONE_WITHOUT_PROOF" in codes(report)


def test_low_value_work_pauses_during_revenue_blocker():
    report = evaluate_watchdog(WatchdogInput("docs-polish", "RUNNING", 5, revenue_blocker_priority=1))
    assert "LOW_VALUE_DURING_REVENUE_BLOCKER" in codes(report)


def test_unchanged_failure_retry_requires_new_recovery():
    report = evaluate_watchdog(
        WatchdogInput(
            "deploy",
            "FAILED",
            1,
            failure_signature="missing-vercel-project",
            previous_failure_signature="missing-vercel-project",
            retry_count_same_signature=2,
        )
    )
    assert "UNCHANGED_FAILURE_RETRY" in codes(report)
    assert report.supervision_level == "supervised"


def test_good_done_control_passes():
    report = evaluate_watchdog(
        WatchdogInput(
            "deploy",
            "DONE",
            1,
            evidence=EvidenceState(
                exact_sha="abc123",
                ci_green=True,
                browser_proof=True,
                meaningful_output="verified six routes",
                evidence_ref="https://example.test/deployment/1",
            ),
        )
    )
    assert not report.findings
    assert not report.escalation_required


def test_markdown_report_is_compact_and_evidence_backed():
    report = evaluate_watchdog(WatchdogInput("copilot", "STALLED", 1, consecutive_no_progress_count=2))
    text = render_markdown_report([report])
    assert "NO_PROGRESS_X2" in text
    assert "copilot" in text


def test_real_fixture_copilot_assignment_is_routine_not_owner_only():
    decision = classify_owner_intervention(ActionKind.COPILOT_ASSIGN)
    assert decision.risk is ActionRisk.ROUTINE


def test_real_fixture_bot_action_required_is_routine_recovery():
    decision = classify_owner_intervention(ActionKind.WORKFLOW_APPROVAL)
    assert decision.risk is ActionRisk.ROUTINE


def test_real_fixture_vercel_ready_without_browser_proof_fails():
    report = evaluate_watchdog(
        WatchdogInput(
            "vercel-preview",
            "READY",
            1,
            evidence=EvidenceState(exact_sha="deadbeef", ci_green=True, evidence_ref=None),
        )
    )
    assert "READY_DONE_WITHOUT_PROOF" in codes(report)
