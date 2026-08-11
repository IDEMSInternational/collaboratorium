"""
Provenance and confirmation.

A value, where it came from, and whether someone here stood behind it. The
invariant every one of these tests is really guarding is the first section's:
absent provenance means "entered", so a deployment that has never heard of any
of this sees no difference at all.
"""
import pytest
from dash import Dash, html

from pantograph import provenance
from pantograph.component_factory import (
    CONFIRMED_STYLE,
    UNCONFIRMED_STYLE,
    wrap_provenance,
)
from pantograph.form_gen import generate_form_layout
from pantograph.provenance import (
    CITED,
    ENTERED,
    INHERITED,
    SUGGESTED,
    ProvenanceError,
    by_element,
    confirm,
    confirmation_for,
    describe,
    is_confirmed,
    normalise,
    record,
    unconfirmed,
)
from pantograph.requirements import (
    ENABLED_LABEL,
    outstanding,
    register_required_callbacks,
    rejection_message,
    submit_label,
    unsatisfied,
)

FORM = {
    "label": "Processing Activity",
    "elements": {
        "name": {"type": "string", "label": "Name", "required": True},
        "collection_purpose": {"type": "string", "label": "Collection Purpose",
                               "required": True},
        "notes": {"type": "string", "label": "Notes"},
    },
    "meta": {},
}

SUGGESTION = record(SUGGESTED, origin="run-4", confidence=0.82)


def element_ids(component):
    """Every component id in a rendered tree, so a test can ask what got added."""
    found = []
    stack = [component]
    while stack:
        node = stack.pop()
        node_id = getattr(node, "id", None)
        if node_id is not None:
            found.append(node_id)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return found


def types_in(component):
    return {i.get("type") for i in element_ids(component) if isinstance(i, dict)}


def node_of_type(component, wanted):
    """The one component whose pattern-matching id has this `type`."""
    stack = [component]
    while stack:
        node = stack.pop()
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict) and node_id.get("type") == wanted:
            return node
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            stack.extend(children)
        elif children is not None:
            stack.append(children)
    return None


# --------------------------------------------------------------------------
# Absent provenance means "entered"
# --------------------------------------------------------------------------

@pytest.mark.parametrize("absent", [None, {}, "", 0])
def test_a_value_with_no_provenance_is_confirmed(absent):
    """The whole compatibility story: nothing existing has provenance, and
    nothing existing may start needing confirmation."""
    assert is_confirmed(absent) is True
    assert normalise(absent) is None


def test_an_explicit_entered_source_behaves_exactly_like_no_provenance():
    assert normalise(record(ENTERED)) is None
    assert is_confirmed(record(ENTERED)) is True
    assert describe(record(ENTERED)) == ""


def test_a_form_with_no_provenance_renders_the_dom_it_always_did():
    layout = generate_form_layout("f", {"f": FORM}, initial_values={"name": "x"})
    assert not {"provenance", "provenance-confirm", "provenance-block"} & types_in(layout)


def test_a_value_with_no_provenance_still_satisfies_required():
    assert outstanding(FORM, {"name": "x", "collection_purpose": "because"}) == []
    assert rejection_message(FORM, {"name": "x", "collection_purpose": "because"}) is None


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

def test_the_four_sources_are_the_three_directions_plus_entered():
    assert set(provenance.SOURCES) == {"entered", "inherited", "cited", "suggested"}


def test_a_source_core_cannot_honour_is_refused_at_construction():
    with pytest.raises(ProvenanceError, match="guessed"):
        record("guessed")


def test_an_unconfirmed_value_is_unconfirmed_whatever_its_source():
    for source in (INHERITED, CITED, SUGGESTED):
        assert is_confirmed(record(source)) is False


def test_confirming_records_who_and_when_without_erasing_where_it_came_from():
    confirmed = confirm(SUGGESTION, person_id=7, at="2026-03-04T09:00:00")
    assert is_confirmed(confirmed) is True
    assert confirmed["source"] == SUGGESTED
    assert confirmed["from"] == "run-4"
    assert confirmed["confirmed_by"] == 7
    assert confirmed["confirmed_at"] == "2026-03-04T09:00:00"


def test_confirming_stamps_a_time_when_none_is_given():
    assert confirm(SUGGESTION, person_id=7)["confirmed_at"]


def test_confirming_something_that_was_entered_here_is_a_no_op():
    assert confirm(None, person_id=7) is None


def test_a_provenance_that_cannot_be_read_is_unconfirmed_rather_than_assumed_entered():
    """
    Promoting data we cannot parse into "a human typed this" is the one failure
    this module exists to prevent, so garbage is kept and flagged.
    """
    for garbage in ["nonsense", {"source": "vibes"}, ["run", 4], 42]:
        assert is_confirmed(garbage) is False
        assert normalise(garbage) is not None


@pytest.mark.parametrize("raw, kept", [
    (0.82, 0.82), (0, 0.0), (1, 1.0), ("0.5", 0.5),
    (1.4, None), (-0.1, None), ("high", None), (True, None), (None, None),
])
def test_a_confidence_outside_zero_to_one_is_dropped_rather_than_shown(raw, kept):
    assert record(SUGGESTED, confidence=raw)["confidence"] == kept


# --------------------------------------------------------------------------
# What the user is told
# --------------------------------------------------------------------------

def test_the_note_names_the_source_and_where_it_came_from():
    assert describe(record(INHERITED, origin="scope-3")) == "Inherited from scope-3"
    assert describe(record(SUGGESTED, origin="run-4")) == "Suggested by run-4"


def test_a_citation_shows_the_version_it_was_pinned_to():
    """'Approved against Assessment v3, and v4 now exists' is a state the
    register must be able to show, so the version is never dropped."""
    assert describe(record(CITED, origin=[12, 3])) == "Cited from 12 v3"


def test_a_confidence_is_shown_as_a_percentage():
    assert describe(SUGGESTION) == "Suggested by run-4 (82% confidence)"


def test_the_note_says_who_confirmed_it():
    assert describe(confirm(SUGGESTION, "Ada")).endswith(", confirmed by Ada")


def test_a_source_with_no_origin_still_reads():
    assert describe(record(INHERITED)) == "Inherited"


# --------------------------------------------------------------------------
# An unconfirmed value does not satisfy required:
# --------------------------------------------------------------------------

def answers():
    return {"name": "x", "collection_purpose": "to keep in touch"}


def test_an_unconfirmed_value_does_not_answer_the_question():
    unanswered, pending = unsatisfied(
        FORM, answers(), "ropa_form", {"collection_purpose": SUGGESTION})
    assert unanswered == []
    assert pending == ["collection_purpose"]


def test_confirming_the_value_settles_it():
    confirmed = {"collection_purpose": confirm(SUGGESTION, person_id=1)}
    assert unsatisfied(FORM, answers(), "ropa_form", confirmed) == ([], [])


def test_an_unconfirmed_value_on_an_optional_field_blocks_nothing():
    assert outstanding(FORM, {**answers(), "notes": "n"}, "f",
                       {"notes": SUGGESTION}) == []


def test_an_empty_field_is_unanswered_rather_than_unconfirmed():
    """Both are outstanding, but the cure differs and so must the wording."""
    unanswered, pending = unsatisfied(
        FORM, {"name": "x", "collection_purpose": ""}, "f",
        {"collection_purpose": SUGGESTION})
    assert unanswered == ["collection_purpose"] and pending == []


def test_the_button_asks_for_confirmation_rather_than_for_the_value():
    assert submit_label(FORM, [], ["collection_purpose"]) == (
        "Confirm Collection Purpose to submit")
    assert submit_label(FORM, ["name"], ["collection_purpose"]) == (
        "Add Name and confirm Collection Purpose to submit")
    assert submit_label(FORM, [], []) == ENABLED_LABEL


def test_the_button_still_says_what_it_always_said_when_nothing_is_unconfirmed():
    assert submit_label(FORM, ["name"]) == "Add Name to submit"


def test_a_submit_carrying_an_unconfirmed_required_value_is_refused():
    """
    The disabled button is a courtesy; the client posts the callback directly.
    A record whose purpose only a model ever asserted is not a defensible one.
    """
    message = rejection_message(FORM, answers(), provenances={"collection_purpose": SUGGESTION})
    assert message == "Not saved — not confirmed: Collection Purpose"


def test_a_refusal_separates_the_missing_from_the_unconfirmed():
    message = rejection_message(FORM, {"name": "", "collection_purpose": "p"},
                                provenances={"collection_purpose": SUGGESTION})
    assert message == "Not saved — still needed: Name; not confirmed: Collection Purpose"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def component():
    return html.Div("input", id={"type": "input", "form": "f", "element": "collection_purpose"})


def test_an_element_with_no_provenance_is_not_wrapped_at_all():
    plain = component()
    assert wrap_provenance(plain, "f", "collection_purpose", None) is plain
    assert wrap_provenance(plain, "f", "collection_purpose", record(ENTERED)) is plain


def test_an_unconfirmed_value_renders_visibly_distinct_with_a_way_to_confirm():
    wrapped = wrap_provenance(component(), "f", "collection_purpose", SUGGESTION)
    assert wrapped.style == UNCONFIRMED_STYLE
    assert wrapped.style != CONFIRMED_STYLE
    assert types_in(wrapped) >= {"provenance", "provenance-confirm", "provenance-note"}


def test_a_confirmed_value_keeps_its_origin_but_loses_the_emphasis():
    wrapped = wrap_provenance(component(), "f", "collection_purpose",
                              confirm(SUGGESTION, person_id=1))
    assert wrapped.style == CONFIRMED_STYLE
    assert "provenance" in types_in(wrapped)


def test_a_value_already_confirmed_offers_no_second_confirmation():
    """There is nothing left to say, and a live button would invite a signature
    that overwrites the one already on the record."""
    unconfirmed_block = wrap_provenance(component(), "f", "collection_purpose", SUGGESTION)
    confirmed_block = wrap_provenance(component(), "f", "collection_purpose",
                                      confirm(SUGGESTION, person_id=1))
    assert node_of_type(unconfirmed_block, "provenance-confirm").style is None
    assert node_of_type(confirmed_block, "provenance-confirm").style == {"display": "none"}


def test_the_store_travels_with_the_value_so_submit_can_read_it():
    layout = generate_form_layout(
        "f", {"f": FORM}, initial_values={"collection_purpose": "to keep in touch"},
        provenances={"collection_purpose": SUGGESTION})
    stores = [i for i in element_ids(layout)
              if isinstance(i, dict) and i.get("type") == "provenance"]
    assert stores == [{"type": "provenance", "form": "f", "element": "collection_purpose"}]


def test_only_the_element_that_carries_a_provenance_is_decorated():
    layout = generate_form_layout("f", {"f": FORM}, initial_values={"name": "x"},
                                  provenances={"collection_purpose": SUGGESTION})
    blocks = [i for i in element_ids(layout)
              if isinstance(i, dict) and i.get("type") == "provenance-block"]
    assert len(blocks) == 1


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

def test_confirming_updates_the_store_and_drops_the_provisional_styling():
    store, note, container_style, control_style = confirmation_for(SUGGESTION, person_id=9)
    assert is_confirmed(store)
    assert "confirmed by 9" in note
    assert container_style == CONFIRMED_STYLE
    assert control_style == {"display": "none"}


def test_the_required_callback_watches_the_provenance_stores():
    """Otherwise confirming a value would leave the submit button disabled."""
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_required_callbacks(app, {"ropa_form": FORM})
    inputs = " ".join(str(spec) for spec in app.callback_map.values()).replace(" ", "")
    assert "'type':'provenance'" in inputs.replace('"', "'")


def test_the_confirm_control_is_wired_once_for_the_whole_app():
    app = Dash(__name__, suppress_callback_exceptions=True)
    provenance.register_provenance_callbacks(app)
    keys = " ".join(app.callback_map).replace(" ", "")
    assert "provenance-confirm" in keys
    assert len(app.callback_map) == 1


def test_by_element_ignores_stores_with_nothing_to_record():
    ids = [{"type": "provenance", "form": "f", "element": "a"},
           {"type": "provenance", "form": "f", "element": "b"}]
    assert by_element(ids, [SUGGESTION, None]) == {"a": normalise(SUGGESTION)}
    assert by_element([], []) == {}
    assert by_element(None, None) == {}


def test_unconfirmed_lists_the_elements_nobody_stood_behind():
    provenances = {"a": SUGGESTION, "b": confirm(SUGGESTION, person_id=1)}
    assert unconfirmed(provenances) == {"a"}
    assert unconfirmed(provenances, ["a", "b", "c"]) == {"a"}
