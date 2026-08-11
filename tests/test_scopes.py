"""
Scope resolution: inheritance down a tree of arbitrary depth, and the three
divergence kinds.

The fixture is the register's own example — one product, two deployments, two
programs under one of them — because the interesting cases (a program diverging
from a deployment that already diverged from the product) only exist at three
levels.
"""
import pytest

from pantograph.scopes import (
    ADDED,
    OVERRIDDEN,
    REMOVED,
    ScopeError,
    ScopeTree,
    divergences,
    grain_key,
    resolve,
    resolve_all,
)

# Product → Deployment → Program. Nothing in scopes.py names these levels; the
# names are here only so the assertions read like the register does.
SCOPES = [
    {"id": "parentapp", "parent": None},
    {"id": "kenya", "parent": "parentapp"},
    {"id": "india", "parent": "parentapp"},
    {"id": "national_online", "parent": "india"},
    {"id": "state_hybrid", "parent": "india"},
]


def tree():
    return ScopeTree(SCOPES)


def record(scope, field, purpose="service", recipient=None, category="parents", **extra):
    return {
        "scope": scope,
        "field": field,
        "purpose": purpose,
        "recipient": recipient,
        "data_subject_category": category,
        **extra,
    }


def removal(scope, field, **kwargs):
    return record(scope, field, status=REMOVED, **kwargs)


def keys(resolved):
    return [r["field"] for r in resolved]


def by_field(resolved):
    return {r["field"]: r for r in resolved}


# --------------------------------------------------------------------------
# The tree
# --------------------------------------------------------------------------

def test_ancestry_is_root_first():
    assert tree().ancestry("state_hybrid") == ["parentapp", "india", "state_hybrid"]


def test_depth_is_reported_not_fixed():
    assert [tree().depth(s) for s in ("parentapp", "india", "state_hybrid")] == [0, 1, 2]


def test_descendants_exclude_the_scope_itself():
    assert set(tree().descendants("india")) == {"national_online", "state_hybrid"}
    assert tree().descendants("state_hybrid") == []


def test_several_roots_are_allowed():
    forest = ScopeTree([{"id": "parentapp"}, {"id": "otherapp"}])
    assert sorted(forest.roots()) == ["otherapp", "parentapp"]


def test_a_parent_that_is_not_a_scope_is_rejected():
    with pytest.raises(ScopeError, match="not a scope"):
        ScopeTree([{"id": "kenya", "parent": "parentapp"}])


def test_a_cycle_is_rejected_at_construction():
    with pytest.raises(ScopeError, match="own ancestor"):
        ScopeTree([{"id": "a", "parent": "b"}, {"id": "b", "parent": "a"}])


def test_duplicate_scope_ids_are_rejected():
    with pytest.raises(ScopeError, match="Duplicate"):
        ScopeTree([{"id": "kenya"}, {"id": "kenya"}])


def test_asking_about_an_unknown_scope_raises_rather_than_answering_empty():
    with pytest.raises(ScopeError, match="Unknown scope"):
        resolve(tree(), [], "peru")


# --------------------------------------------------------------------------
# Inheritance
# --------------------------------------------------------------------------

def test_a_product_record_reaches_every_scope_beneath_without_duplication():
    records = [record("parentapp", "child_name")]
    resolved = resolve_all(tree(), records)
    assert all(keys(resolved[s]) == ["child_name"] for s in resolved)
    assert len(records) == 1


def test_an_inherited_record_names_the_scope_it_came_from():
    resolved = resolve(tree(), [record("parentapp", "child_name")], "state_hybrid")
    assert resolved[0]["provenance"]["source"] == "inherited"
    assert resolved[0]["provenance"]["from"] == "parentapp"


def test_from_is_the_declaring_scope_not_the_immediate_parent():
    records = [record("parentapp", "child_name"), record("india", "child_name", purpose="research")]
    # india's own record is a different grain key, so state_hybrid still
    # inherits the product's — from the product, two levels up.
    resolved = by_field(resolve(tree(), records, "state_hybrid"))
    assert len(resolve(tree(), records, "state_hybrid")) == 2
    assert resolved["child_name"]["provenance"]["from"] == "parentapp"


def test_a_record_declared_here_carries_no_inherited_provenance():
    # Absent provenance means "entered"; the resolver must not invent any.
    resolved = resolve(tree(), [record("kenya", "id_number")], "kenya")
    assert "provenance" not in resolved[0]


def test_inheriting_preserves_confidence_and_confirmation():
    suggested = record(
        "parentapp", "child_name",
        provenance={"source": "suggested", "confidence": 0.7,
                    "confirmed_by": 12, "confirmed_at": "2026-08-01T00:00:00Z"},
    )
    got = resolve(tree(), [suggested], "kenya")[0]["provenance"]
    assert got["source"] == "inherited"
    assert got["confidence"] == 0.7
    assert got["confirmed_by"] == 12
    assert got["confirmed_at"] == "2026-08-01T00:00:00Z"


def test_inheriting_does_not_mutate_the_stored_record():
    stored = record("parentapp", "child_name")
    resolve(tree(), [stored], "kenya")
    assert "provenance" not in stored


def test_provenance_is_filled_out_to_the_full_contract():
    got = resolve(tree(), [record("parentapp", "child_name")], "kenya")[0]["provenance"]
    assert set(got) == {"source", "from", "confidence", "confirmed_by", "confirmed_at"}


# --------------------------------------------------------------------------
# The three divergence kinds
# --------------------------------------------------------------------------

def test_added_is_visible_only_beneath_the_scope_that_added_it():
    records = [record("parentapp", "child_name"), record("kenya", "national_id")]
    resolved = resolve_all(tree(), records)
    assert keys(resolved["kenya"]) == ["child_name", "national_id"]
    assert keys(resolved["india"]) == ["child_name"]
    assert divergences(tree(), records, "kenya") == {grain_key(records[1]): ADDED}


def test_overridden_replaces_the_inherited_record_for_that_scope_only():
    records = [
        record("parentapp", "child_name", retention="7y"),
        record("kenya", "child_name", retention="2y"),
    ]
    resolved = resolve_all(tree(), records)
    assert by_field(resolved["kenya"])["child_name"]["retention"] == "2y"
    assert by_field(resolved["india"])["child_name"]["retention"] == "7y"
    assert divergences(tree(), records, "kenya") == {grain_key(records[1]): OVERRIDDEN}


def test_removed_takes_the_record_off_this_scope_and_everything_beneath():
    records = [record("parentapp", "face_scan"), removal("india", "face_scan")]
    resolved = resolve_all(tree(), records)
    assert keys(resolved["parentapp"]) == ["face_scan"]
    assert keys(resolved["india"]) == []
    assert keys(resolved["state_hybrid"]) == []
    assert keys(resolved["kenya"]) == ["face_scan"]


def test_a_removal_is_never_itself_an_effective_record():
    # The register must not report "processes face_scan (removed)" as a row.
    resolved = resolve(tree(), [record("parentapp", "face_scan"), removal("kenya", "face_scan")], "kenya")
    assert resolved == []


def test_a_removal_is_visible_as_a_divergence():
    records = [record("parentapp", "face_scan"), removal("kenya", "face_scan")]
    assert divergences(tree(), records, "kenya") == {grain_key(records[1]): REMOVED}


def test_removing_something_no_ancestor_declared_is_harmless():
    assert resolve(tree(), [removal("kenya", "face_scan")], "kenya") == []


# --------------------------------------------------------------------------
# Depth beyond two levels
# --------------------------------------------------------------------------

def test_a_program_diverges_from_a_deployment_that_already_diverged():
    records = [
        record("parentapp", "child_name", retention="7y"),
        record("india", "child_name", retention="3y"),
        record("state_hybrid", "child_name", retention="1y"),
    ]
    resolved = resolve_all(tree(), records)
    assert by_field(resolved["parentapp"])["child_name"]["retention"] == "7y"
    assert by_field(resolved["india"])["child_name"]["retention"] == "3y"
    assert by_field(resolved["national_online"])["child_name"]["retention"] == "3y"
    assert by_field(resolved["state_hybrid"])["child_name"]["retention"] == "1y"
    assert by_field(resolved["national_online"])["child_name"]["provenance"]["from"] == "india"


def test_a_fourth_level_needs_no_change_to_the_library():
    deeper = ScopeTree(SCOPES + [{"id": "maharashtra", "parent": "state_hybrid"}])
    resolved = resolve(deeper, [record("parentapp", "child_name")], "maharashtra")
    assert keys(resolved) == ["child_name"]
    assert deeper.depth("maharashtra") == 3


def test_a_program_can_re_add_what_its_deployment_removed():
    records = [
        record("parentapp", "face_scan"),
        removal("india", "face_scan"),
        record("state_hybrid", "face_scan", retention="30d"),
    ]
    resolved = resolve_all(tree(), records)
    assert keys(resolved["national_online"]) == []
    assert by_field(resolved["state_hybrid"])["face_scan"]["retention"] == "30d"
    # The parent, having removed it, does not have it — so this reads as added.
    assert divergences(tree(), records, "state_hybrid") == {grain_key(records[2]): ADDED}


# --------------------------------------------------------------------------
# The grain
# --------------------------------------------------------------------------

def test_the_same_field_for_two_purposes_is_two_records_not_an_override():
    records = [
        record("parentapp", "child_name", purpose="service"),
        record("kenya", "child_name", purpose="research"),
    ]
    resolved = resolve(tree(), records, "kenya")
    assert [r["purpose"] for r in resolved] == ["research", "service"]


def test_recipient_and_category_separate_records_that_share_a_field_and_purpose():
    records = [
        record("parentapp", "child_name", recipient=1),
        record("parentapp", "child_name", recipient=2),
        record("parentapp", "child_name", recipient=2, category="staff"),
    ]
    assert len(resolve(tree(), records, "kenya")) == 3


def test_a_removal_only_removes_its_own_grain_key():
    records = [
        record("parentapp", "child_name", recipient=1),
        record("parentapp", "child_name", recipient=2),
        removal("kenya", "child_name", recipient=2),
    ]
    assert [r["recipient"] for r in resolve(tree(), records, "kenya")] == [1]


def test_a_missing_dimension_is_a_key_value_not_a_wildcard():
    records = [
        record("parentapp", "child_name", recipient=None),
        record("kenya", "child_name", recipient=7),
    ]
    assert len(resolve(tree(), records, "kenya")) == 2


def test_a_record_with_no_field_is_rejected():
    with pytest.raises(ScopeError, match="no field"):
        resolve(tree(), [{"scope": "kenya", "purpose": "service"}], "kenya")


def test_a_record_on_an_unknown_scope_is_rejected():
    with pytest.raises(ScopeError, match="unknown scope"):
        resolve(tree(), [record("peru", "child_name")], "kenya")


def test_two_records_at_one_scope_with_one_grain_key_are_rejected():
    with pytest.raises(ScopeError, match="twice"):
        resolve(tree(), [record("kenya", "child_name"), record("kenya", "child_name")], "kenya")


# --------------------------------------------------------------------------
# Output shape
# --------------------------------------------------------------------------

def test_resolve_and_resolve_all_agree():
    records = [
        record("parentapp", "child_name"),
        record("parentapp", "face_scan"),
        removal("india", "face_scan"),
        record("state_hybrid", "face_scan", retention="30d"),
        record("kenya", "national_id"),
    ]
    whole = resolve_all(tree(), records)
    assert all(whole[s] == resolve(tree(), records, s) for s in whole)


def test_row_order_is_stable_regardless_of_input_order():
    records = [record("parentapp", f) for f in ("face_scan", "child_name", "national_id")]
    forwards = keys(resolve(tree(), records, "kenya"))
    backwards = keys(resolve(tree(), list(reversed(records)), "kenya"))
    assert forwards == backwards == ["child_name", "face_scan", "national_id"]


def test_resolve_all_covers_every_scope_including_empty_ones():
    assert set(resolve_all(tree(), [])) == {s["id"] for s in SCOPES}
