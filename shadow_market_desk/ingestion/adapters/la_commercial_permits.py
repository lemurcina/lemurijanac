from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from ..adapter import SignalAdapter, canonical_json, deterministic_key
from ..models import EntityRef, Signal, SourceEvidence, SourceTerms

logger = logging.getLogger(__name__)


class LACommercialPermitAdapter(SignalAdapter):
    source_terms = SourceTerms(
        source_name="LA Building and Safety Permits",
        source_url="https://data.lacity.org/",
        terms_url="https://data.lacity.org/stories/s/What-is-the-Open-Data-Policy-/4r7x-3h6j",
        notes="Public city open-data endpoint. No authentication or paywall.",
    )

    @property
    def source_name(self) -> str:
        return self.source_terms.source_name

    @property
    def endpoint(self) -> str:
        return "https://data.lacity.org/resource/yv23-pmwf.json"

    def normalize_record(self, raw_record: Mapping[str, Any]) -> Signal | None:
        permit_number = _clean(raw_record.get("pcis_permit"))
        issued_date_raw = raw_record.get("issue_date")
        if not permit_number or not issued_date_raw:
            return None

        try:
            observed_at = datetime.fromisoformat(str(issued_date_raw))
        except ValueError:
            logger.warning(
                "ingest_record_invalid_date",
                extra={"source_name": self.source_name, "issued_date": issued_date_raw},
            )
            return None

        address = _clean(raw_record.get("address"))
        description = _clean(raw_record.get("work_description"))
        dedup_key = deterministic_key([permit_number, observed_at.date().isoformat()])

        entity_refs = [EntityRef(kind="permit", value=permit_number)]
        if address:
            entity_refs.append(EntityRef(kind="address", value=address, display_name=address))

        raw_metadata = canonical_json(dict(raw_record))

        try:
            evidence = SourceEvidence(
                source_name=self.source_name,
                source_record_id=permit_number,
                source_url=f"{self.endpoint}?pcis_permit={permit_number}",
                observed_at=observed_at,
                extraction_method="api",
                terms=self.source_terms,
                raw_metadata=raw_metadata,
            )
            return Signal(
                signal_type="la.commercial_permit",
                dedup_key=dedup_key,
                observed_at=observed_at,
                entity_refs=entity_refs,
                evidence=evidence,
                payload={
                    "address": address,
                    "work_description": description,
                    "status": _clean(raw_record.get("status")),
                },
            )
        except ValidationError:
            return None


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())
