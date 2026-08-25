from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class Evidence:
    source: str
    source_ref: str
    observed_at: datetime
    method: str
    confidence: float
    url: str | None = None
    note: str | None = None

    @property
    def id(self) -> str:
        return _stable_id(
            "ev",
            _normalize(self.source),
            _normalize(self.source_ref),
            self.observed_at.astimezone(UTC).isoformat(),
            _normalize(self.method),
        )


@dataclass(frozen=True)
class EntityIdentity:
    name: str
    address: str
    evidence_id: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fingerprint",
            _stable_id("fp", _normalize(self.name), _normalize(self.address)),
        )


@dataclass
class Entity:
    id: str
    identities: list[EntityIdentity] = field(default_factory=list)
    merged_into: str | None = None
    split_from: str | None = None

    @property
    def active(self) -> bool:
        return self.merged_into is None


@dataclass(frozen=True)
class Signal:
    id: str
    entity_id: str
    kind: str
    payload: str


@dataclass(frozen=True)
class Need:
    id: str
    signal_id: str
    entity_id: str
    kind: str


@dataclass(frozen=True)
class Opportunity:
    id: str
    need_id: str
    buyer_entity_id: str
    vendor_entity_id: str


@dataclass(frozen=True)
class Relationship:
    id: str
    left_id: str
    right_id: str
    relation: str
    confidence: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceConflict:
    entity_id: str
    conflicting_names: tuple[str, ...]
    conflicting_addresses: tuple[str, ...]


class OpportunityGraphRepository(ABC):
    @abstractmethod
    def record_entity_identity(self, identity: EntityIdentity) -> str:
        raise NotImplementedError

    @abstractmethod
    def create_signal(self, entity_id: str, kind: str, payload: str, evidence: Evidence) -> str:
        raise NotImplementedError

    @abstractmethod
    def create_need(self, signal_id: str, kind: str, evidence: Evidence) -> str:
        raise NotImplementedError

    @abstractmethod
    def create_opportunity(
        self,
        need_id: str,
        buyer_entity_id: str,
        vendor_entity_id: str,
        evidence: Evidence,
        confidence: float,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def link_candidate_vendor(self, need_id: str, vendor_entity_id: str, evidence: Evidence, confidence: float) -> str:
        raise NotImplementedError

    @abstractmethod
    def link_candidate_buyer(self, need_id: str, buyer_entity_id: str, evidence: Evidence, confidence: float) -> str:
        raise NotImplementedError

    @abstractmethod
    def merge_entities(self, canonical_entity_id: str, duplicate_entity_id: str, evidence: Evidence) -> None:
        raise NotImplementedError

    @abstractmethod
    def split_entity(
        self,
        source_entity_id: str,
        identity_to_split: EntityIdentity,
        split_evidence: Evidence,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def opportunities_by_entity(self, entity_id: str) -> list[Opportunity]:
        raise NotImplementedError

    @abstractmethod
    def needs_by_signal(self, signal_id: str) -> list[Need]:
        raise NotImplementedError

    @abstractmethod
    def candidate_vendors(self, need_id: str) -> list[Relationship]:
        raise NotImplementedError

    @abstractmethod
    def candidate_buyers(self, need_id: str) -> list[Relationship]:
        raise NotImplementedError

    @abstractmethod
    def stale_evidence(self, older_than: timedelta, now: datetime | None = None) -> list[Evidence]:
        raise NotImplementedError

    @abstractmethod
    def conflicting_evidence(self) -> list[EvidenceConflict]:
        raise NotImplementedError


class InMemoryOpportunityGraphRepository(OpportunityGraphRepository):
    """In-memory implementation with deterministic behavior and explicit extension points.

    Extension points for a Postgres implementation:
    - stable ID generation can be replaced by UUIDs while preserving external IDs.
    - relationship/evidence records map directly to join tables.
    - merge/split provenance is represented as relationships and never deleted.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._fingerprint_to_entity: dict[str, str] = {}
        self._signals: dict[str, Signal] = {}
        self._needs: dict[str, Need] = {}
        self._opportunities: dict[str, Opportunity] = {}
        self._relationships: dict[str, Relationship] = {}
        self._need_to_signal: dict[str, str] = {}
        self._evidence: dict[str, Evidence] = {}

    def _store_evidence(self, evidence: Evidence) -> None:
        self._evidence[evidence.id] = evidence

    def _entity_or_merged_target(self, entity_id: str) -> str:
        entity = self._entities[entity_id]
        visited = {entity_id}
        while entity.merged_into is not None:
            if entity.merged_into in visited:
                raise ValueError("merge lineage contains a cycle")
            visited.add(entity.merged_into)
            entity = self._entities[entity.merged_into]
        return entity.id

    def record_entity_identity(self, identity: EntityIdentity) -> str:
        entity_id = self._fingerprint_to_entity.get(identity.fingerprint)
        if entity_id is None:
            entity_id = _stable_id("ent", identity.fingerprint)
            self._entities[entity_id] = Entity(id=entity_id, identities=[identity])
            self._fingerprint_to_entity[identity.fingerprint] = entity_id
            return entity_id

        canonical_id = self._entity_or_merged_target(entity_id)
        canonical_entity = self._entities[canonical_id]
        if identity not in canonical_entity.identities:
            canonical_entity.identities.append(identity)
        self._fingerprint_to_entity[identity.fingerprint] = canonical_id
        return canonical_id

    def create_signal(self, entity_id: str, kind: str, payload: str, evidence: Evidence) -> str:
        self._store_evidence(evidence)
        canonical_entity_id = self._entity_or_merged_target(entity_id)
        signal_id = _stable_id("sig", canonical_entity_id, _normalize(kind), _normalize(payload), evidence.id)
        self._signals[signal_id] = Signal(
            id=signal_id,
            entity_id=canonical_entity_id,
            kind=kind,
            payload=payload,
        )
        return signal_id

    def create_need(self, signal_id: str, kind: str, evidence: Evidence) -> str:
        self._store_evidence(evidence)
        signal = self._signals[signal_id]
        need_id = _stable_id("need", signal_id, _normalize(kind), evidence.id)
        self._needs[need_id] = Need(id=need_id, signal_id=signal_id, entity_id=signal.entity_id, kind=kind)
        self._need_to_signal[need_id] = signal_id
        return need_id

    def _add_relationship(
        self,
        left_id: str,
        right_id: str,
        relation: str,
        evidence: Evidence,
        confidence: float,
    ) -> str:
        self._store_evidence(evidence)
        relationship_id = _stable_id("rel", left_id, right_id, relation)
        existing = self._relationships.get(relationship_id)
        if existing is None:
            self._relationships[relationship_id] = Relationship(
                id=relationship_id,
                left_id=left_id,
                right_id=right_id,
                relation=relation,
                confidence=confidence,
                evidence_ids=(evidence.id,),
            )
        else:
            merged_evidence_ids = tuple(sorted({*existing.evidence_ids, evidence.id}))
            self._relationships[relationship_id] = Relationship(
                id=existing.id,
                left_id=existing.left_id,
                right_id=existing.right_id,
                relation=existing.relation,
                confidence=max(existing.confidence, confidence),
                evidence_ids=merged_evidence_ids,
            )
        return relationship_id

    def create_opportunity(
        self,
        need_id: str,
        buyer_entity_id: str,
        vendor_entity_id: str,
        evidence: Evidence,
        confidence: float,
    ) -> str:
        buyer = self._entity_or_merged_target(buyer_entity_id)
        vendor = self._entity_or_merged_target(vendor_entity_id)
        self._store_evidence(evidence)
        opportunity_id = _stable_id("opp", need_id, buyer, vendor)
        self._opportunities[opportunity_id] = Opportunity(
            id=opportunity_id,
            need_id=need_id,
            buyer_entity_id=buyer,
            vendor_entity_id=vendor,
        )
        self._add_relationship(need_id, opportunity_id, "NEED_TO_OPPORTUNITY", evidence, confidence)
        self._add_relationship(opportunity_id, buyer, "OPPORTUNITY_BUYER", evidence, confidence)
        self._add_relationship(opportunity_id, vendor, "OPPORTUNITY_VENDOR", evidence, confidence)
        return opportunity_id

    def link_candidate_vendor(self, need_id: str, vendor_entity_id: str, evidence: Evidence, confidence: float) -> str:
        vendor = self._entity_or_merged_target(vendor_entity_id)
        return self._add_relationship(need_id, vendor, "CANDIDATE_VENDOR", evidence, confidence)

    def link_candidate_buyer(self, need_id: str, buyer_entity_id: str, evidence: Evidence, confidence: float) -> str:
        buyer = self._entity_or_merged_target(buyer_entity_id)
        return self._add_relationship(need_id, buyer, "CANDIDATE_BUYER", evidence, confidence)

    def merge_entities(self, canonical_entity_id: str, duplicate_entity_id: str, evidence: Evidence) -> None:
        canonical_id = self._entity_or_merged_target(canonical_entity_id)
        duplicate_id = self._entity_or_merged_target(duplicate_entity_id)
        if canonical_id == duplicate_id:
            return

        self._store_evidence(evidence)
        canonical = self._entities[canonical_id]
        duplicate = self._entities[duplicate_id]
        canonical.identities.extend(identity for identity in duplicate.identities if identity not in canonical.identities)
        duplicate.merged_into = canonical_id

        for identity in duplicate.identities:
            self._fingerprint_to_entity[identity.fingerprint] = canonical_id

        self._add_relationship(canonical_id, duplicate_id, "MERGED_FROM", evidence, evidence.confidence)

        for relationship_id, relationship in list(self._relationships.items()):
            left = canonical_id if relationship.left_id == duplicate_id else relationship.left_id
            right = canonical_id if relationship.right_id == duplicate_id else relationship.right_id
            if (left, right) == (relationship.left_id, relationship.right_id):
                continue
            merged_id = _stable_id("rel", left, right, relationship.relation)
            existing = self._relationships.get(merged_id)
            if existing is None:
                self._relationships[merged_id] = Relationship(
                    id=merged_id,
                    left_id=left,
                    right_id=right,
                    relation=relationship.relation,
                    confidence=relationship.confidence,
                    evidence_ids=relationship.evidence_ids,
                )
            else:
                self._relationships[merged_id] = Relationship(
                    id=merged_id,
                    left_id=left,
                    right_id=right,
                    relation=relationship.relation,
                    confidence=max(existing.confidence, relationship.confidence),
                    evidence_ids=tuple(sorted({*existing.evidence_ids, *relationship.evidence_ids})),
                )
            if merged_id != relationship_id:
                del self._relationships[relationship_id]

        for opportunity_id, opportunity in list(self._opportunities.items()):
            buyer = canonical_id if opportunity.buyer_entity_id == duplicate_id else opportunity.buyer_entity_id
            vendor = canonical_id if opportunity.vendor_entity_id == duplicate_id else opportunity.vendor_entity_id
            self._opportunities[opportunity_id] = Opportunity(
                id=opportunity_id,
                need_id=opportunity.need_id,
                buyer_entity_id=buyer,
                vendor_entity_id=vendor,
            )

    def split_entity(
        self,
        source_entity_id: str,
        identity_to_split: EntityIdentity,
        split_evidence: Evidence,
    ) -> str:
        source_id = self._entity_or_merged_target(source_entity_id)
        source = self._entities[source_id]
        if identity_to_split not in source.identities:
            raise ValueError("identity_to_split must already belong to source_entity_id")

        self._store_evidence(split_evidence)
        split_entity_id = _stable_id("ent", source_id, identity_to_split.fingerprint, "split")
        existing = self._entities.get(split_entity_id)
        if existing is None:
            self._entities[split_entity_id] = Entity(
                id=split_entity_id,
                identities=[identity_to_split],
                split_from=source_id,
            )
        else:
            if existing.merged_into is not None:
                raise ValueError("cannot split into an entity that is already merged")
            if identity_to_split not in existing.identities:
                existing.identities.append(identity_to_split)
            if existing.split_from is None:
                existing.split_from = source_id
        source.identities = [identity for identity in source.identities if identity != identity_to_split]
        self._fingerprint_to_entity[identity_to_split.fingerprint] = split_entity_id
        self._add_relationship(split_entity_id, source_id, "SPLIT_FROM", split_evidence, split_evidence.confidence)
        return split_entity_id

    def opportunities_by_entity(self, entity_id: str) -> list[Opportunity]:
        canonical = self._entity_or_merged_target(entity_id)
        opportunities = [
            opp
            for opp in self._opportunities.values()
            if opp.buyer_entity_id == canonical or opp.vendor_entity_id == canonical
        ]
        return sorted(opportunities, key=lambda opp: opp.id)

    def needs_by_signal(self, signal_id: str) -> list[Need]:
        return sorted(
            [need for need in self._needs.values() if need.signal_id == signal_id],
            key=lambda need: need.id,
        )

    def _candidate_relationships(self, need_id: str, relation: str) -> list[Relationship]:
        relationships = [
            rel
            for rel in self._relationships.values()
            if rel.left_id == need_id and rel.relation == relation
        ]
        return sorted(relationships, key=lambda rel: rel.id)

    def candidate_vendors(self, need_id: str) -> list[Relationship]:
        return self._candidate_relationships(need_id, "CANDIDATE_VENDOR")

    def candidate_buyers(self, need_id: str) -> list[Relationship]:
        return self._candidate_relationships(need_id, "CANDIDATE_BUYER")

    def stale_evidence(self, older_than: timedelta, now: datetime | None = None) -> list[Evidence]:
        """Return all evidence records older than the threshold, including lineage evidence."""
        reference_now = now or datetime.now(tz=UTC)
        threshold = reference_now - older_than
        stale = [evidence for evidence in self._evidence.values() if evidence.observed_at < threshold]
        return sorted(stale, key=lambda evidence: evidence.id)

    def conflicting_evidence(self) -> list[EvidenceConflict]:
        conflicts: list[EvidenceConflict] = []
        for entity in sorted(self._entities.values(), key=lambda item: item.id):
            if not entity.active:
                continue
            names = sorted({_normalize(identity.name) for identity in entity.identities})
            addresses = sorted({_normalize(identity.address) for identity in entity.identities})
            if len(names) > 1 or len(addresses) > 1:
                conflicts.append(
                    EvidenceConflict(
                        entity_id=entity.id,
                        conflicting_names=tuple(names),
                        conflicting_addresses=tuple(addresses),
                    )
                )
        return conflicts

    @property
    def entities(self) -> Iterable[Entity]:
        return tuple(sorted(self._entities.values(), key=lambda entity: entity.id))

    @property
    def relationships(self) -> Iterable[Relationship]:
        return tuple(sorted(self._relationships.values(), key=lambda relationship: relationship.id))

    @property
    def evidence_items(self) -> Iterable[Evidence]:
        return tuple(sorted(self._evidence.values(), key=lambda evidence: evidence.id))
