from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceTerms(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_name: str
    source_url: HttpUrl
    terms_url: HttpUrl
    access_level: Literal["public"] = "public"
    notes: str | None = None


class EntityRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str = Field(min_length=1)
    value: str = Field(min_length=1)
    display_name: str | None = None


class SourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_name: str
    source_record_id: str
    source_url: HttpUrl
    observed_at: datetime
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extraction_method: str = "api"
    terms: SourceTerms
    raw_metadata: dict[str, Any]


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_type: str
    dedup_key: str
    observed_at: datetime
    entity_refs: list[EntityRef]
    evidence: SourceEvidence
    payload: dict[str, Any] = Field(default_factory=dict)
