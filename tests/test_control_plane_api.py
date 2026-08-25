from fastapi.testclient import TestClient

from shadow_market_desk.control_plane.dependencies import get_repositories
from shadow_market_desk.control_plane.main import app
from shadow_market_desk.control_plane.repositories import build_default_repositories


def make_client() -> TestClient:
    repositories = build_default_repositories()
    app.dependency_overrides[get_repositories] = lambda: repositories
    return TestClient(app)


def test_health_endpoint() -> None:
    client = make_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_versioned_api_root() -> None:
    client = make_client()
    response = client.get("/api/v1")
    assert response.status_code == 200
    assert response.json()["version"] == "0.1.0"


def test_read_endpoint_pagination_and_filtering() -> None:
    client = make_client()
    response = client.get("/api/v1/opportunities", params={"status": "open", "limit": 1, "offset": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["status"] == "open"


def test_mark_outcome_validation() -> None:
    client = make_client()
    response = client.post(
        "/api/v1/outcomes/out-1/mark",
        json={"status": "won"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation_error"


def test_policy_enforcement_disabled_policy_cannot_be_approved() -> None:
    client = make_client()

    response = client.post("/api/v1/channel-policies/policy-2/approve")

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"] == "http_error"
    assert "disabled policy" in payload["detail"]


def test_control_actions_are_audit_logged() -> None:
    client = make_client()

    pause_response = client.post("/api/v1/strategies/strat-1/pause")
    assert pause_response.status_code == 200

    audit_response = client.get("/api/v1/audit-events", params={"action": "strategy.pause"})
    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["resource_id"] == "strat-1"
    assert payload["items"][0]["action"] == "strategy.pause"
