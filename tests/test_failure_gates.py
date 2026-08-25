from shadow_market_desk.operations.gates import GateInput, evaluate_failure_gates


def codes(result):
    return {failure.code for failure in result.failures}


def test_good_control_passes():
    result = evaluate_failure_gates(
        GateInput(
            human_tone_score=4,
            specificity_score=4,
            has_price=True,
            pricing_evidence=True,
            cta_is_specific=True,
            state="DONE",
            exact_sha="abc123",
            ci_green=True,
            browser_or_route_proof=True,
            expected_cash=3000,
            realized_cash=0,
            labels_expected_as_realized=False,
            demo_has_unique_observation=True,
            unchanged_failure_retries=0,
        )
    )
    assert result.passed
    assert not result.failures


def test_robotic_outreach_fails():
    result = evaluate_failure_gates(GateInput(human_tone_score=1, specificity_score=1))
    assert "ROBOTIC_OUTREACH" in codes(result)


def test_premature_price_fails():
    result = evaluate_failure_gates(GateInput(has_price=True, pricing_evidence=False))
    assert "PREMATURE_PRICE" in codes(result)


def test_generic_cta_fails():
    result = evaluate_failure_gates(GateInput(cta_is_specific=False))
    assert "GENERIC_CTA" in codes(result)


def test_done_without_exact_sha_route_proof_fails():
    result = evaluate_failure_gates(
        GateInput(state="DONE", exact_sha="abc", ci_green=True, browser_or_route_proof=False)
    )
    assert "DONE_WITHOUT_PROOF" in codes(result)


def test_expected_cash_cannot_be_realized_cash():
    result = evaluate_failure_gates(
        GateInput(expected_cash=3000, realized_cash=0, labels_expected_as_realized=True)
    )
    assert "EXPECTED_AS_REALIZED" in codes(result)


def test_template_demo_without_unique_observation_fails():
    result = evaluate_failure_gates(GateInput(demo_has_unique_observation=False))
    assert "TEMPLATE_LOOKING_DEMO" in codes(result)


def test_two_unchanged_retries_fail():
    result = evaluate_failure_gates(GateInput(unchanged_failure_retries=2))
    assert "SILENT_RETRY_LOOP" in codes(result)
