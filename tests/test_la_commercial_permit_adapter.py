from __future__ import annotations

import json
from pathlib import Path

import pytest

from shadow_market_desk.ingestion import SourceFetchError
from shadow_market_desk.ingestion.adapters import LACommercialPermitAdapter


class StubClient:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self, url: str, *, params=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _load_fixture(name: str):
    fixture_path = Path(__file__).parent / "fixtures" / name
    return json.loads(fixture_path.read_text())


def test_normalization_keeps_traceable_evidence() -> None:
    records = _load_fixture("la_permits.json")
    adapter = LACommercialPermitAdapter(client=StubClient([records[0]]))

    signals = adapter.ingest()

    assert len(signals) == 1
    signal = signals[0]
    assert signal.signal_type == "la.commercial_permit"
    assert signal.evidence.source_record_id == "24016-10000-12345"
    assert signal.evidence.raw_metadata["work_description"] == "Tenant improvement"
    assert signal.entity_refs[0].kind == "permit"


def test_ingest_deduplicates_records() -> None:
    records = _load_fixture("la_permits.json")
    adapter = LACommercialPermitAdapter(client=StubClient(records[:2]))

    signals = adapter.ingest()

    assert len(signals) == 1


def test_ingest_skips_malformed_records() -> None:
    records = _load_fixture("la_permits.json")
    adapter = LACommercialPermitAdapter(client=StubClient(records))

    signals = adapter.ingest()

    assert len(signals) == 1
    assert signals[0].evidence.source_record_id == "24016-10000-12345"


def test_ingest_raises_source_failures() -> None:
    adapter = LACommercialPermitAdapter(client=StubClient(SourceFetchError("boom")))

    with pytest.raises(SourceFetchError):
        adapter.ingest()


def test_ingest_rejects_non_list_payload() -> None:
    adapter = LACommercialPermitAdapter(client=StubClient({"not": "a list"}))

    with pytest.raises(SourceFetchError):
        adapter.ingest()
