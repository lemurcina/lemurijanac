from pathlib import Path


def test_governing_contracts_present_and_pipeline_ordered() -> None:
    portfolio = Path("PORTFOLIO_CONTRACT.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "SIGNAL -> EVIDENCE -> REALITY CHECK -> BUYER-FIRST VALIDATION -> SCORE -> OFFER CANDIDATE -> OUTCOME -> LEARNING" in portfolio
    assert "Los Angeles commercial permits / new businesses / local contractors" in portfolio
    assert "Estimated or pipeline revenue must not be labeled realized" in portfolio
    assert "no production send without an explicitly enabled channel policy" in agents
