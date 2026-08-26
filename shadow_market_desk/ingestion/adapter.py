from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import Signal, SourceTerms

logger = logging.getLogger(__name__)


class SourceFetchError(RuntimeError):
    """Raised when a source cannot be fetched."""


class SourceClient(Protocol):
    def get_json(self, url: str, *, params: Mapping[str, Any] | None = None) -> Any:
        ...


class JsonHttpSourceClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        rate_limit_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._rate_limit_hook = rate_limit_hook
        self._http_client = httpx.Client(timeout=self._timeout_seconds)

    def get_json(self, url: str, *, params: Mapping[str, Any] | None = None) -> Any:
        if self._rate_limit_hook:
            self._rate_limit_hook(url)

        try:
            return self._request_with_retry(url, params=params)
        except httpx.HTTPError as exc:  # pragma: no cover - defensive boundary
            raise SourceFetchError(f"failed to fetch source: {url}") from exc

    def close(self) -> None:
        self._http_client.close()

    def _request_with_retry(self, url: str, *, params: Mapping[str, Any] | None = None) -> Any:
        retrying = Retrying(
            reraise=True,
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(httpx.HTTPError),
        )
        for attempt in retrying:
            with attempt:
                response = self._http_client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        return None


class SignalAdapter(ABC):
    source_terms: SourceTerms

    def __init__(self, *, client: SourceClient) -> None:
        self._client = client

    @property
    @abstractmethod
    def source_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def endpoint(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def normalize_record(self, raw_record: Mapping[str, Any]) -> Signal | None:
        raise NotImplementedError

    def fetch_raw_records(self) -> list[dict[str, Any]]:
        data = self._client.get_json(self.endpoint)
        if not isinstance(data, list):
            raise SourceFetchError(f"expected list payload from {self.source_name}")
        return [record for record in data if isinstance(record, dict)]

    def ingest(self) -> list[Signal]:
        raw_records = self.fetch_raw_records()
        logger.info(
            "ingest_start",
            extra={"source_name": self.source_name, "record_count": len(raw_records)},
        )
        deduped: dict[str, Signal] = {}
        for raw_record in raw_records:
            signal = self.normalize_record(raw_record)
            if signal is None:
                logger.warning(
                    "ingest_record_skipped",
                    extra={"source_name": self.source_name, "raw_record": raw_record},
                )
                continue
            deduped.setdefault(signal.dedup_key, signal)
        logger.info(
            "ingest_complete",
            extra={"source_name": self.source_name, "signal_count": len(deduped)},
        )
        return list(deduped.values())


def deterministic_key(parts: list[str]) -> str:
    canonical = "|".join(part.strip().lower() for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest
