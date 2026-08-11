"""
Provenance and confirmation.

A value, where it came from, and whether someone here stood behind it. The
invariant every one of these tests is really guarding is the first section's:
absent provenance means "entered", so a deployment that has never heard of any
of this sees no difference at all.
"""
from dataclasses import replace
from uuid import uuid4

import pytest
from dash import Dash, html

import pantograph.settings as pg_settings
from pantograph.config import load_config

from pantograph import provenance
from pantograph.component_factory import (
    CONFIRMED_STYLE,
    UNCONFIRMED_STYLE,
    wrap_provenance,
)
from pantograph.db import (
    PROVENANCE_TABLE,
    db_connect,
    get_all_provenance,
    get_provenance,
    init_db,
    save_provenance,
)
from pantograph.form_gen import generate_form_layout, register_submit_callbacks
from pantograph.provenance import (
    CITED,
    ENTERED,
    INHERITED,
    SUGGESTED,
    ProvenanceError,
    annotation,
    by_element,
    confirm,
    confirmation_for,
    describe,
    is_confirmed,
    normalise,
    record,
    surviving_edits,
    unconfirmed,
)
from pantograph.report_generator import generate_markdown_report
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
        FORM, answers(), "ropa_form", provenances={"collection_purpose": SUGGESTION})
    assert unanswered == []
    assert pending == ["collection_purpose"]


def test_confirming_the_value_settles_it():
    confirmed = {"collection_purpose": confirm(SUGGESTION, person_id=1)}
    assert unsatisfied(FORM, answers(), "ropa_form", provenances=confirmed) == ([], [])


def test_an_unconfirmed_value_on_an_optional_field_blocks_nothing():
    assert outstanding(FORM, {**answers(), "notes": "n"}, "f",
                       provenances={"notes": SUGGESTION}) == []


def test_an_empty_field_is_unanswered_rather_than_unconfirmed():
    """Both are outstanding, but the cure differs and so must the wording."""
    unanswered, pending = unsatisfied(
        FORM, {"name": "x", "collection_purpose": ""}, "f",
        provenances={"collection_purpose": SUGGESTION})
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


# --------------------------------------------------------------------------
# Persistence
#
# The record row and its provenance are one immutable pair, keyed by the
# record's version. What is being guarded here is the same invariant as
# everywhere else, now that it has to survive a disk: a value nobody stood
# behind must not come back looking like one somebody typed.
# --------------------------------------------------------------------------

# Every column of `initiatives` the form is responsible for: the submit path
# writes the whole row, so a form that leaves one out cannot save at all.
STORED_FORM = {
    "label": "Initiative",
    "default_table": "initiatives",
    "elements": {
        "name": {"type": "string", "label": "Name", "required": True},
        "description": {"type": "string", "label": "Description"},
        "responsible_person": {"type": "string", "label": "Responsible Person"},
        "tag_groups": {"type": "string", "label": "Tag Groups"},
        "status": {"type": "string", "label": "Status"},
    },
    "meta": {"id": {"type": "hidden"}, "version": {"type": "hidden"}},
}

BLANK = {"name": "n", "description": "d", "responsible_person": None,
         "tag_groups": None, "status": "active", "id": None, "version": None}

RECORD_ID = 1


@pytest.fixture
def record_db(monkeypatch, tmp_path):
    """
    A database of this test's own, built from the real config.

    Its own file rather than the session's: these tests write records, and the
    session database is shared with the tests that drive a browser. A new file
    per test rather than one deleted and rebuilt, because a connection left open
    elsewhere makes a Windows delete fail silently and the next test would
    inherit the rows.
    """
    monkeypatch.setattr(
        pg_settings, "_settings",
        replace(pg_settings.get_settings(),
                database_path=tmp_path / f"records-{uuid4().hex}.db"),
    )
    config = load_config("config")
    init_db(config)
    return config


@pytest.fixture
def saved(record_db):
    """
    Write a record row and its provenance the way the submit callback does — one
    cursor, one commit for both — and hand back what was stored.
    """
    def save(values, provenances, version=1, record_id=RECORD_ID):
        conn = db_connect()
        cur = conn.cursor()
        columns = ["id", "version", "status", *values]
        cur.execute(
            f'INSERT INTO "initiatives" ({", ".join(columns)}) '
            f'VALUES ({", ".join(["?"] * len(columns))})',
            [record_id, version, "active", *values.values()],
        )
        save_provenance(cur, "initiatives", record_id, version, provenances)
        conn.commit()
        conn.close()
        return get_provenance("initiatives", record_id, version)

    return save


def submit(values, provenances, form=None):
    """
    The submit callback itself, on the values and provenance stores a form would
    hand it. `__wrapped__` is the function Dash registered, so this is the real
    save path rather than a re-enactment of it — everything but Dash's dispatch,
    which a forged callback POST cannot be driven past.
    """
    form = form or STORED_FORM
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_submit_callbacks(app, {"f": form})
    callback = list(app.callback_map.values())[0]["callback"].__wrapped__

    ids = [{"type": "provenance", "form": "f", "element": element}
           for element in provenances]
    ordered = [values.get(element) for element in
               list(form["elements"]) + list(form["meta"])]
    return callback(1, [], [], 1, list(provenances.values()), ids, *ordered)


def test_an_unconfirmed_value_is_still_unconfirmed_after_a_round_trip(saved):
    """The acceptance criterion, and the reason the whole issue exists: an
    unconfirmed value on an *optional* field was previously saved as though a
    human had typed it."""
    stored = saved({"description": "to keep participants informed"},
                   {"description": SUGGESTION})
    assert is_confirmed(stored["description"]) is False
    assert stored["description"] == normalise(SUGGESTION)


def test_a_signature_survives_the_round_trip_intact(saved):
    stored = saved({"description": "d"},
                   {"description": confirm(SUGGESTION, person_id=7,
                                           at="2026-03-04T09:00:00")})
    assert is_confirmed(stored["description"]) is True
    assert describe(stored["description"]) == (
        "Suggested by run-4 (82% confidence), confirmed by 7")


def test_a_value_that_was_typed_here_leaves_no_trace(saved):
    """Absent provenance means "entered", so the table stays empty for every
    deployment that has never supplied one — which is all of them so far."""
    assert saved({"name": "n"}, {"name": record(ENTERED), "description": None}) == {}
    assert get_provenance("initiatives", RECORD_ID, 1) == {}


@pytest.mark.parametrize("origin", [
    [12, 3],      # a citation, pinned to the version it was approved against
    "scope-3",
    "12",         # a scope id that looks like a number and is not one
    4,
])
def test_where_a_value_came_from_survives_whatever_shape_it_has(saved, origin):
    """`from` is opaque to core — a scope id, an [assessment_id, version] pair,
    an analysis run id — so storage has to hand back exactly what the thing that
    produced the value put there, type and all."""
    stored = saved({"description": "d"}, {"description": record(CITED, origin=origin)})
    assert stored["description"]["from"] == origin
    assert type(stored["description"]["from"]) is type(origin)


def test_a_stored_provenance_that_cannot_be_read_is_not_promoted_to_entered(saved):
    """A hand-edited row, or one written by a version that knew a source this
    one does not. Reading it as "a human typed this" is the failure."""
    stored = saved({"description": "d"}, {"description": {"source": "vibes"}})
    assert is_confirmed(stored["description"]) is False
    assert stored["description"]["from"] == "vibes"


def test_provenance_belongs_to_the_version_it_was_saved_with(saved):
    """What makes a table beside the record safe: the row it annotates can never
    change under it, because a saved version never changes."""
    saved({"description": "first"}, {"description": SUGGESTION}, version=1)
    saved({"description": "second"}, {"description": record(INHERITED, "scope-3")},
          version=2)
    assert get_provenance("initiatives", RECORD_ID, 1)["description"]["source"] == SUGGESTED
    assert get_provenance("initiatives", RECORD_ID, 2)["description"]["source"] == INHERITED


def test_a_record_with_no_provenance_reads_back_as_none_of_it(saved):
    saved({"description": "d"}, {})
    assert get_provenance("initiatives", RECORD_ID, 1) == {}
    assert get_all_provenance().get(("initiatives", RECORD_ID, 1)) is None


def test_every_unconfirmed_value_in_the_register_is_one_query(saved):
    """The thing a side table is for, and the reason the columns are columns
    rather than a blob."""
    saved({"description": "d"}, {"description": SUGGESTION, "name": SUGGESTION})
    conn = db_connect()
    rows = conn.execute(
        f'SELECT record_table, record_id, element FROM "{PROVENANCE_TABLE}" '
        f'WHERE confirmed_by IS NULL AND record_id = ?', (RECORD_ID,)).fetchall()
    conn.close()
    assert sorted(rows) == [("initiatives", RECORD_ID, "description"),
                            ("initiatives", RECORD_ID, "name")]


def test_the_table_is_there_for_a_database_that_predates_it(record_db):
    """Existing deployments have a database already, and init_db returns early
    for one. The mechanism is useless to them if it only arrives with a fresh
    database — they are the deployments with records to defend."""
    conn = db_connect()
    conn.execute(f'DROP TABLE "{PROVENANCE_TABLE}"')
    conn.commit()
    conn.close()

    init_db(record_db)  # the same call the app makes on every start

    conn = db_connect()
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
    conn.close()
    assert PROVENANCE_TABLE in names


# --------------------------------------------------------------------------
# Saving a form
# --------------------------------------------------------------------------

def test_a_submitted_provenance_is_stored_with_the_record(record_db):
    """The gap #82 left: it survived prefill, rendering, confirmation and the
    submit gate, and was dropped on the way to the disk."""
    submit({**BLANK, "description": "to keep participants informed"},
           {"description": SUGGESTION})
    stored = get_provenance("initiatives", 1, 1)
    assert is_confirmed(stored["description"]) is False
    assert describe(stored["description"]) == "Suggested by run-4 (82% confidence)"


def test_an_unconfirmed_optional_value_is_not_saved_as_though_it_were_typed(record_db):
    """`description` is optional, so the submit gate lets it through — which is
    precisely the corner where an unconfirmed value used to become a human's
    word for it."""
    submit({**BLANK, "description": "a model wrote this"},
           {"description": SUGGESTION})
    layout = generate_form_layout("f", {"f": STORED_FORM}, object_id=1)
    assert node_of_type(layout, "provenance-block").style == UNCONFIRMED_STYLE


def test_a_saved_record_a_human_then_rewrote_is_theirs(record_db, saved):
    saved({"name": "n", "description": "a model wrote this"},
          {"description": SUGGESTION})
    submit({**BLANK, "description": "a person wrote this", "id": 1, "version": 1},
           {"description": SUGGESTION})
    assert get_provenance("initiatives", 1, 2) == {}


def test_a_saved_record_a_human_left_alone_keeps_its_origin(record_db, saved):
    saved({"name": "n", "description": "a model wrote this"},
          {"description": SUGGESTION})
    submit({**BLANK, "description": "a model wrote this", "id": 1, "version": 1},
           {"description": SUGGESTION})
    assert get_provenance("initiatives", 1, 2)["description"] == normalise(SUGGESTION)


def test_a_claim_about_an_answer_that_no_longer_applies_dies_with_it(record_db):
    """The submit path already blanks an answer to a question the form has
    stopped asking. A note saying where that answer came from would outlive the
    answer and describe an empty column."""
    form = {**STORED_FORM, "elements": {
        **STORED_FORM["elements"],
        "description": {"type": "string", "label": "Description",
                        "relevant": "${name} = 'keep'"},
    }}
    submit({**BLANK, "name": "drop", "description": "a model wrote this"},
           {"description": SUGGESTION}, form=form)
    assert get_provenance("initiatives", 1, 1) == {}


def test_a_form_with_no_provenance_stores_none(record_db):
    """The whole compatibility story, at the far end: an existing deployment
    writes exactly the rows it always wrote."""
    submit(BLANK, {})
    assert get_all_provenance() == {}


# --------------------------------------------------------------------------
# Reopening the record
# --------------------------------------------------------------------------

def test_an_edit_form_reopens_the_claim_the_record_was_saved_with(saved):
    saved({"name": "n", "description": "to keep participants informed"},
          {"description": SUGGESTION})
    layout = generate_form_layout("f", {"f": STORED_FORM}, object_id=RECORD_ID)
    block = node_of_type(layout, "provenance-block")
    assert block.style == UNCONFIRMED_STYLE
    assert "Suggested by run-4" in str(node_of_type(layout, "provenance-note").children)


def test_an_edit_form_for_a_record_with_no_provenance_renders_what_it_always_did(saved):
    saved({"name": "n", "description": "d"}, {})
    layout = generate_form_layout("f", {"f": STORED_FORM}, object_id=RECORD_ID)
    assert not {"provenance", "provenance-confirm", "provenance-block"} & types_in(layout)


def test_a_caller_that_supplies_provenances_is_describing_its_own_values(saved):
    """A prefill passes the values *and* where they came from; what is on disk
    describes a different set of values and must not overrule it."""
    saved({"name": "n", "description": "d"}, {"description": SUGGESTION})
    layout = generate_form_layout("f", {"f": STORED_FORM}, object_id=RECORD_ID,
                                  provenances={"name": record(INHERITED, "scope-3")})
    notes = str(node_of_type(layout, "provenance-note").children)
    assert "Inherited from scope-3" in notes and "Suggested" not in notes


# --------------------------------------------------------------------------
# Editing a value disowns its origin
# --------------------------------------------------------------------------

def test_a_value_a_human_has_rewritten_is_no_longer_the_models():
    """Confirming is not retyping, and retyping is not confirming. Persistence
    is what makes this matter: the stale claim used to die with the page, and
    would now be written into the register as a standing assertion."""
    assert surviving_edits({"description": SUGGESTION},
                           {"description": "to keep participants informed"},
                           {"description": "to send the monthly newsletter"}) == {}


def test_an_untouched_value_keeps_where_it_came_from():
    kept = surviving_edits({"description": SUGGESTION},
                           {"description": "same words"},
                           {"description": "same words"})
    assert kept == {"description": SUGGESTION}


def test_a_new_record_keeps_the_provenance_it_was_prefilled_with():
    """There is no previous value to have departed from — the prefill *is* where
    the value came from."""
    assert surviving_edits({"description": SUGGESTION}, None,
                           {"description": "suggested text"}) == {"description": SUGGESTION}


@pytest.mark.parametrize("before, after", [
    (5, "5"), (None, ""), ("", None),
])
def test_the_same_value_spelled_differently_is_not_an_edit(before, after):
    assert surviving_edits({"a": SUGGESTION}, {"a": before}, {"a": after})


@pytest.mark.parametrize("before, after", [
    ("{\"g\": {}}", {"g": {}}),          # a subform against the JSON it was stored as
    (1, True),                            # a checkbox against the 1 in the column
    ("2,3", [3, 2]),                      # a multi-select against its stored join
])
def test_a_shape_that_cannot_be_compared_exactly_keeps_its_provenance(before, after):
    """Dropping a provenance asserts "a human typed this". That claim is never
    made on a guess, so doubt keeps the record rather than clearing it."""
    assert surviving_edits({"a": SUGGESTION}, {"a": before}, {"a": after})


def test_an_element_the_previous_version_never_had_keeps_its_provenance():
    assert surviving_edits({"new_element": SUGGESTION}, {"name": "n"},
                           {"new_element": "v"})


# --------------------------------------------------------------------------
# The export
# --------------------------------------------------------------------------

REPORT_CFG = {"name": "Register", "hierarchy": [
    {"type": "initiatives", "template": "## {name}\n\n{description}\n"}]}


def nodes(**properties):
    data = {"id": 1, "version": 1, "name": "n", "description": "d", **properties}
    return [{"data": {"id": f"initiatives-{data['id']}", "label": data["name"],
                      "type": "initiatives", "properties": data}}]


def test_the_export_says_where_a_value_came_from(saved):
    saved({"name": "n", "description": "to keep participants informed"},
          {"description": SUGGESTION})
    md = generate_markdown_report(REPORT_CFG, nodes(id=RECORD_ID))
    assert "_[Suggested by run-4 (82% confidence), not confirmed]_" in md


def test_the_export_names_who_stood_behind_a_value(saved):
    saved({"name": "n", "description": "d"},
          {"description": confirm(SUGGESTION, person_id="Ada")})
    md = generate_markdown_report(REPORT_CFG, nodes(id=RECORD_ID))
    assert "confirmed by Ada" in md and "not confirmed" not in md


def test_the_export_of_a_record_with_no_provenance_is_the_report_it_always_was(saved):
    saved({"name": "n", "description": "d"}, {})
    md = generate_markdown_report(REPORT_CFG, nodes(id=RECORD_ID))
    assert md == "# Register\n\n## n\n\nd\n"


def test_the_export_does_not_borrow_another_versions_claims(saved):
    """A report rendered from version 1 must not annotate it with what version 2
    was saved believing."""
    saved({"name": "n", "description": "d"}, {}, version=1)
    saved({"name": "n", "description": "d"}, {"description": SUGGESTION}, version=2)
    md = generate_markdown_report(REPORT_CFG, nodes(id=RECORD_ID, version=1))
    assert "Suggested" not in md


def test_the_note_is_beside_the_value_rather_than_in_a_footnote():
    """A reader who has to look elsewhere to learn that nobody stood behind a
    purpose reads that purpose as asserted."""
    assert annotation(SUGGESTION) == " _[Suggested by run-4 (82% confidence), not confirmed]_"
    assert annotation(None) == ""
    assert annotation(record(ENTERED)) == ""
