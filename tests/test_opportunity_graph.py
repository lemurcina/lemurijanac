from datetime import UTC, datetime, timedelta

from shadow_market_desk.opportunity_graph import (
    EntityIdentity,
    Evidence,
    InMemoryOpportunityGraphRepository,
)


def _evidence(ref: str, days_ago: int = 0, confidence: float = 0.8) -> Evidence:
    return Evidence(
        source="city_records",
        source_ref=ref,
        observed_at=datetime(2026, 8, 25, tzinfo=UTC) - timedelta(days=days_ago),
        method="manual-review",
        confidence=confidence,
        url=f"https://example.test/{ref}",
    )


def test_dedup_stable_id_and_needs_by_signal() -> None:
    repo = InMemoryOpportunityGraphRepository()
    identity_a = EntityIdentity(name="Acme Signs", address="100 Main St", evidence_id=_evidence("e-1").id)
    identity_b = EntityIdentity(name="  ACME SIGNS ", address="100  main st ", evidence_id=_evidence("e-2").id)

    entity_a = repo.record_entity_identity(identity_a)
    entity_b = repo.record_entity_identity(identity_b)

    assert entity_a == entity_b
    signal_id = repo.create_signal(entity_a, "permit", "tenant improvement", _evidence("sig-1"))
    need_id = repo.create_need(signal_id, "signage", _evidence("need-1"))
    needs = repo.needs_by_signal(signal_id)

    assert [need.id for need in needs] == [need_id]
    assert needs[0].entity_id == entity_a


def test_conflicting_names_and_addresses_are_reported() -> None:
    repo = InMemoryOpportunityGraphRepository()
    name_conflict_1 = EntityIdentity(name="Blue Finch LLC", address="99 Pine St", evidence_id=_evidence("c-1").id)
    name_conflict_2 = EntityIdentity(name="Blue Finch Lighting", address="99 Pine St", evidence_id=_evidence("c-2").id)
    entity_id = repo.record_entity_identity(name_conflict_1)

    repo._entities[entity_id].identities.append(name_conflict_2)  # intentional synthetic conflict fixture

    conflicts = repo.conflicting_evidence()

    assert len(conflicts) == 1
    assert conflicts[0].entity_id == entity_id
    assert conflicts[0].conflicting_names == ("blue finch lighting", "blue finch llc")


def test_merge_preserves_provenance_and_updates_queries() -> None:
    repo = InMemoryOpportunityGraphRepository()
    buyer = repo.record_entity_identity(EntityIdentity("Buyer One", "1 Oak St", _evidence("b-1").id))
    vendor_a = repo.record_entity_identity(EntityIdentity("Vendor Prime", "2 Elm St", _evidence("v-1").id))
    vendor_b = repo.record_entity_identity(EntityIdentity("Vendor Prime Co", "2 Elm St", _evidence("v-2").id))
    signal_id = repo.create_signal(buyer, "permit", "electrical upgrade", _evidence("m-sig"))
    need_id = repo.create_need(signal_id, "electrical", _evidence("m-need"))
    repo.link_candidate_vendor(need_id, vendor_b, _evidence("cand-v"), 0.71)

    opportunity_id = repo.create_opportunity(need_id, buyer, vendor_b, _evidence("opp"), 0.85)
    repo.merge_entities(vendor_a, vendor_b, _evidence("merge", confidence=0.95))

    merged_opps = repo.opportunities_by_entity(vendor_a)
    assert [opp.id for opp in merged_opps] == [opportunity_id]
    assert any(rel.relation == "MERGED_FROM" for rel in repo.relationships)
    assert any(e.source_ref == "merge" for e in repo.evidences)
    assert repo.opportunities_by_entity(vendor_b) == [repo._opportunities[opportunity_id]]


def test_split_reassigns_identity_and_tracks_lineage() -> None:
    repo = InMemoryOpportunityGraphRepository()
    id_a = EntityIdentity("North Star Electric", "700 Lake St", _evidence("s-1").id)
    id_b = EntityIdentity("North Star HVAC", "700 Lake St", _evidence("s-2").id)

    entity_id = repo.record_entity_identity(id_a)
    repo._entities[entity_id].identities.append(id_b)  # synthetic conflated entity
    split_entity_id = repo.split_entity(entity_id, id_b, _evidence("split", confidence=0.9))

    assert split_entity_id != entity_id
    assert any(rel.relation == "SPLIT_FROM" and rel.left_id == split_entity_id for rel in repo.relationships)
    assert all(identity.name != "North Star HVAC" for identity in repo._entities[entity_id].identities)
    resolved_split = repo.record_entity_identity(
        EntityIdentity("North Star HVAC", "700 Lake St", _evidence("s-3").id)
    )
    assert resolved_split == split_entity_id


def test_candidate_queries_and_stale_evidence() -> None:
    repo = InMemoryOpportunityGraphRepository()
    buyer = repo.record_entity_identity(EntityIdentity("Buyer Two", "15 Ash St", _evidence("q-b").id))
    vendor = repo.record_entity_identity(EntityIdentity("Vendor Two", "16 Ash St", _evidence("q-v").id))
    signal_id = repo.create_signal(buyer, "license", "new location", _evidence("q-sig", days_ago=9))
    need_id = repo.create_need(signal_id, "low-voltage", _evidence("q-need", days_ago=8))
    vendor_rel_id = repo.link_candidate_vendor(need_id, vendor, _evidence("q-cv"), 0.62)
    buyer_rel_id = repo.link_candidate_buyer(need_id, buyer, _evidence("q-cb"), 0.77)

    vendor_candidates = repo.candidate_vendors(need_id)
    buyer_candidates = repo.candidate_buyers(need_id)
    stale = repo.stale_evidence(timedelta(days=7), now=datetime(2026, 8, 25, tzinfo=UTC))

    assert [rel.id for rel in vendor_candidates] == [vendor_rel_id]
    assert [rel.id for rel in buyer_candidates] == [buyer_rel_id]
    assert {e.source_ref for e in stale} == {"q-need", "q-sig"}
