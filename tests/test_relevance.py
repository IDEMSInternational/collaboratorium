"""
`relevant:` on form elements: validation, toggling, and what gets stored.

The form under test is defined here as config only — no Python is written to
make its conditional fields work, which is the point of the feature.
"""
import json

import pytest
from dash import Dash

from pantograph import relevance
from pantograph.form_gen import generate_form_layout
from pantograph.relevance import (
    FormConfigError,
    HIDDEN,
    VISIBLE,
    compile_form,
    irrelevant_elements,
    link_resolver,
    register_relevance_callbacks,
    styles_for,
    validate_forms,
)

# A cut-down Record of Processing Activity: the lawful basis you pick decides
# which further questions you are legally required to answer.
ROPA_FORM = {
    "label": "Processing Activity",
    "default_table": "processing_activities",
    "elements": {
        "name": {"type": "string", "label": "Name", "required": True},
        "lawful_basis": {
            "type": "select_one", "label": "Lawful Basis", "list_name": "basis_list",
            "basis_list": {
                "consent": "Consent",
                "legitimate_interest": "Legitimate Interest",
                "legal_obligation": "Legal Obligation",
            },
        },
        "collection_purpose": {
            "type": "string", "label": "Collection Purpose",
            "relevant": "${lawful_basis} = 'legitimate_interest'",
        },
        "collection_balance": {
            "type": "string", "label": "Collection Balance",
            "relevant": "${lawful_basis} = 'legitimate_interest'",
        },
        "consent_record": {
            "type": "string", "label": "How consent is recorded",
            "relevant": "${lawful_basis} = 'consent'",
        },
        "special_category_safeguards": {
            "type": "string", "label": "Safeguards",
            "relevant": "selected(${data_categories}, 'health') or selected(${data_categories}, 'biometric')",
        },
        "data_categories": {
            "type": "select_multiple", "label": "Categories", "list_name": "cat_list",
            "cat_list": {"health": "Health", "biometric": "Biometric", "contact": "Contact"},
        },
    },
    "meta": {"id": {}, "version": {}, "timestamp": {}, "created_by": {}, "status": {}},
}

FORMS = {"ropa_form": ROPA_FORM}


# --------------------------------------------------------------------------
# Which fields show
# --------------------------------------------------------------------------

def _styles(**answers):
    compiled = compile_form("ropa_form", ROPA_FORM)
    conditional = sorted(compiled)
    watched = sorted({n for node in compiled.values()
                      for n in relevance.referenced_elements(node)})
    values = [answers.get(name) for name in watched]
    return dict(zip(conditional, styles_for(compiled, watched, conditional, values)))


def test_legitimate_interest_reveals_its_three_questions():
    shown = _styles(lawful_basis="legitimate_interest")
    assert shown["collection_purpose"] == VISIBLE
    assert shown["collection_balance"] == VISIBLE
    assert shown["consent_record"] == HIDDEN


def test_consent_reveals_a_different_question():
    shown = _styles(lawful_basis="consent")
    assert shown["consent_record"] == VISIBLE
    assert shown["collection_purpose"] == HIDDEN
    assert shown["collection_balance"] == HIDDEN


def test_an_unanswered_basis_reveals_nothing():
    shown = _styles()
    assert all(style == HIDDEN for style in shown.values())


def test_a_third_basis_reveals_neither_branch():
    shown = _styles(lawful_basis="legal_obligation")
    assert shown["collection_purpose"] == HIDDEN
    assert shown["consent_record"] == HIDDEN


def test_a_multiselect_condition():
    assert _styles(data_categories=["contact"])["special_category_safeguards"] == HIDDEN
    assert _styles(data_categories=["contact", "health"])["special_category_safeguards"] == VISIBLE
    assert _styles(data_categories=["biometric"])["special_category_safeguards"] == VISIBLE


def test_adding_a_conditional_field_needs_no_python():
    """
    The acceptance criterion, stated directly: a new conditional field is a
    config edit. This form is defined in this file and nothing imports it.
    """
    extended = {**ROPA_FORM, "elements": {
        **ROPA_FORM["elements"],
        "retention_justification": {
            "type": "string", "label": "Why retain this long?",
            "relevant": "${lawful_basis} != 'consent' and ${lawful_basis}",
        },
    }}
    compiled = compile_form("ropa_form", extended)
    assert "retention_justification" in compiled
    node = compiled["retention_justification"]
    from pantograph.expressions import evaluate
    assert evaluate(node, {"lawful_basis": "legitimate_interest"}) is True
    assert evaluate(node, {"lawful_basis": "consent"}) is False
    assert evaluate(node, {"lawful_basis": None}) is False


# --------------------------------------------------------------------------
# Startup validation
# --------------------------------------------------------------------------

def test_an_unparseable_expression_names_the_form_and_element():
    bad = {"f": {"elements": {"a": {"type": "string", "relevant": "${x} ==== "}}, "meta": {}}}
    with pytest.raises(FormConfigError, match=r"f\.a"):
        validate_forms({"forms": bad})


def test_a_reference_to_a_nonexistent_element_is_rejected():
    bad = {"f": {"elements": {
        "a": {"type": "string"},
        "b": {"type": "string", "relevant": "${typo_here} = '1'"},
    }, "meta": {}}}
    with pytest.raises(FormConfigError, match="typo_here"):
        validate_forms({"forms": bad})


def test_a_reference_to_a_meta_element_is_allowed():
    """`status` and `version` are real values a form can legitimately condition on."""
    ok = {"f": {"elements": {"a": {"type": "string", "relevant": "${status} = 'active'"}},
                "meta": {"status": {}}}}
    assert validate_forms({"forms": ok})["f"]


def test_relevant_on_a_subform_is_rejected_rather_than_silently_ignored():
    """
    Out of scope for now: a subform renders its inputs in its own namespace, so
    the enclosing form's callback cannot see their state. Failing loudly beats a
    condition that never fires.
    """
    bad = {"f": {"elements": {
        "a": {"type": "string"},
        "s": {"type": "subform", "relevant": "${a} = '1'"},
    }, "meta": {}}}
    with pytest.raises(FormConfigError, match="subform"):
        validate_forms({"forms": bad})


def test_the_shipped_config_validates():
    """Whatever this deployment ships must pass the check that runs at startup."""
    from pantograph.config import load_config
    validate_forms(load_config("config"))


def test_a_form_with_no_conditions_compiles_to_nothing():
    plain = {"elements": {"a": {"type": "string"}}, "meta": {}}
    assert compile_form("plain", plain) == {}


# --------------------------------------------------------------------------
# Reading across a link
# --------------------------------------------------------------------------

# The register's real shape: the record points at a data field, and the field
# already records whether it is special category. Asking again is how the two
# copies of one fact come to disagree.
LINKED_FORM = {
    "label": "Processing Record",
    "default_table": "processing_records",
    "elements": {
        "data_field": {
            "type": "select_one", "label": "Data Field",
            "parameters": {"source_table": "data_fields",
                           "value_column": "id", "label_column": "name"},
        },
        "article_9_condition": {
            "type": "select_one", "label": "Article 9 Condition",
            "list_name": "a9", "a9": {"explicit_consent": "Explicit consent"},
            "relevant": "${data_field.special_category} = 'yes'",
        },
    },
    "meta": {"id": {}, "status": {}},
}

SCHEMA = {
    "data_fields": {"fields": {"id": "integer", "version": "integer",
                               "name": "string", "special_category": "string"}},
    "processing_records": {"fields": {"id": "integer", "data_field": "integer"}},
}

DATA_FIELDS = {
    7: {"id": 7, "name": "face_scan", "special_category": "yes"},
    8: {"id": 8, "name": "first_name", "special_category": "no"},
}


def _fake_fetch(rows=None, log=None):
    rows = DATA_FIELDS if rows is None else rows

    def fetch(table, object_id):
        if log is not None:
            log.append((table, object_id))
        assert table == "data_fields"
        return rows.get(object_id, {})

    return fetch


def _linked_hidden(fetch=None, **answers):
    return irrelevant_elements(LINKED_FORM, answers,
                               link_resolver(LINKED_FORM, fetch or _fake_fetch()))


def test_a_condition_follows_the_link_instead_of_asking_again():
    assert "article_9_condition" not in _linked_hidden(data_field=7)
    assert "article_9_condition" in _linked_hidden(data_field=8)


def test_an_unset_link_hides_the_question_it_would_have_revealed():
    assert "article_9_condition" in _linked_hidden()
    assert "article_9_condition" in _linked_hidden(data_field=None)
    assert "article_9_condition" in _linked_hidden(data_field="")


def test_an_unset_link_is_not_looked_up_at_all():
    """An empty dropdown is not a row id, and asking the database for it is a
    query per keystroke on a form nobody has started filling in."""
    log = []
    _linked_hidden(fetch=_fake_fetch(log=log), data_field="  ")
    assert log == []


def test_the_toggle_callbacks_body_follows_the_link():
    """`styles_for` is the callback's whole body; the resolver has to reach it."""
    compiled = compile_form("linked", LINKED_FORM)
    styles = styles_for(compiled, ["data_field"], ["article_9_condition"], [7],
                        link_resolver(LINKED_FORM, _fake_fetch()))
    assert styles == [VISIBLE]
    styles = styles_for(compiled, ["data_field"], ["article_9_condition"], [8],
                        link_resolver(LINKED_FORM, _fake_fetch()))
    assert styles == [HIDDEN]


def test_a_link_pointing_at_a_row_that_is_gone_reads_as_unanswered():
    """
    `get_latest_record` returns nothing for a row whose current version is
    deleted, so a reference into it is empty rather than the value it last had.
    """
    assert "article_9_condition" in _linked_hidden(fetch=_fake_fetch({}), data_field=7)


def test_the_row_is_fetched_once_however_many_columns_are_read():
    """
    Six conditions over one linked row must not be six queries. The cache is per
    resolver, and a resolver is built per evaluation.
    """
    log = []
    form = {**LINKED_FORM, "elements": {
        **LINKED_FORM["elements"],
        "article_9_note": {"type": "string",
                           "relevant": "${data_field.special_category} = 'yes'"},
        "origin_note": {"type": "string", "relevant": "${data_field.name}"},
    }}
    hidden = irrelevant_elements(form, {"data_field": 7},
                                 link_resolver(form, _fake_fetch(log=log)))
    assert hidden == set()
    assert log == [("data_fields", 7)]


def test_a_resolver_built_fresh_per_evaluation_cannot_serve_a_stale_row():
    rows = dict(DATA_FIELDS)
    assert "article_9_condition" not in _linked_hidden(fetch=_fake_fetch(rows), data_field=7)
    rows[7] = {**rows[7], "special_category": "no"}
    assert "article_9_condition" in _linked_hidden(fetch=_fake_fetch(rows), data_field=7)


def test_the_callback_watches_the_link_element():
    """A linked row can only change when the link is re-pointed."""
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_relevance_callbacks(app, {"linked": LINKED_FORM})
    watched = set()
    for cb in app.callback_map.values():
        for i in cb["inputs"]:
            cid = json.loads(i["id"]) if isinstance(i["id"], str) else i["id"]
            if cid.get("type") == "input":
                watched.add(cid["element"])
    assert watched == {"data_field"}


# --------------------------------------------------------------------------
# Startup validation of cross-link references
# --------------------------------------------------------------------------

def _validate(elements, tables=None):
    return validate_forms({
        "forms": {"records_form": {**LINKED_FORM, "elements": elements}},
        "tables": SCHEMA if tables is None else tables,
    })


def test_a_valid_cross_link_reference_passes_startup_validation():
    assert _validate(LINKED_FORM["elements"])["records_form"]


def test_a_misspelt_column_of_the_linked_table_fails_at_startup():
    """The whole point of validating: a typo stops the deployment rather than
    surfacing as a condition that is quietly always false."""
    elements = {**LINKED_FORM["elements"], "article_9_condition": {
        "type": "string", "relevant": "${data_field.special_categry} = 'yes'"}}
    with pytest.raises(FormConfigError, match="special_categry"):
        _validate(elements)
    with pytest.raises(FormConfigError, match=r"records_form\.article_9_condition"):
        _validate(elements)


def test_a_reference_through_an_element_that_is_not_a_link_fails_at_startup():
    elements = {**LINKED_FORM["elements"], "article_9_condition": {
        "type": "string", "relevant": "${status.name} = 'x'"}}
    with pytest.raises(FormConfigError, match="not a link"):
        _validate(elements)


def test_a_link_selecting_on_something_other_than_id_is_refused():
    """A linked row is fetched by id; reading the wrong row silently is worse."""
    elements = {
        "data_field": {"type": "select_one", "parameters": {
            "source_table": "data_fields", "value_column": "name", "label_column": "name"}},
        "article_9_condition": {"type": "string",
                                "relevant": "${data_field.special_category} = 'yes'"},
    }
    with pytest.raises(FormConfigError, match="'id'"):
        _validate(elements)


def test_a_link_to_a_table_the_config_does_not_define_fails_at_startup():
    elements = {**LINKED_FORM["elements"], "article_9_condition": {
        "type": "string", "relevant": "${data_field.special_category} = 'yes'"}}
    with pytest.raises(FormConfigError, match="not a table"):
        _validate(elements, tables={"processing_records": {"fields": {"id": "integer"}}})


def test_columns_go_unchecked_when_there_is_no_schema_to_check_them_against():
    """
    The submit path compiles a form on its own, with no config around it. The
    startup check is where a typo is caught; this one must not start failing on
    a form it cannot judge.
    """
    assert compile_form("<submit>", LINKED_FORM)["article_9_condition"]


# --------------------------------------------------------------------------
# What gets stored
# --------------------------------------------------------------------------

def test_answers_to_questions_that_no_longer_apply_are_cleared():
    """
    A record claiming a legitimate-interest balancing test when the basis has
    since become Consent would be actively misleading. The append-only schema
    keeps the previous answer in the record's history.
    """
    submitted = {
        "lawful_basis": "consent",
        "collection_purpose": "left over from an earlier answer",
        "collection_balance": "also left over",
        "consent_record": "signed form",
        "data_categories": ["contact"],
    }
    stale = irrelevant_elements(ROPA_FORM, submitted)
    assert "collection_purpose" in stale and "collection_balance" in stale
    assert "consent_record" not in stale
    assert "special_category_safeguards" in stale


def test_relevant_answers_are_untouched():
    submitted = {"lawful_basis": "legitimate_interest",
                 "collection_purpose": "keep me", "data_categories": []}
    stale = irrelevant_elements(ROPA_FORM, submitted)
    assert "collection_purpose" not in stale
    assert "name" not in stale, "an element with no condition is never stale"


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

def test_only_conditional_elements_are_wrapped(monkeypatch):
    """
    An element with no `relevant:` must render exactly as before, so nothing
    about an existing deployment's DOM changes.
    """
    monkeypatch.setattr("pantograph.component_factory.get_dropdown_options",
                        lambda *a, **k: [])
    layout = generate_form_layout("ropa_form", FORMS)
    wrapped = _wrapper_ids(layout)
    assert wrapped == {"collection_purpose", "collection_balance",
                       "consent_record", "special_category_safeguards"}


def _wrapper_ids(component):
    found = set()
    cid = getattr(component, "id", None)
    if isinstance(cid, dict) and cid.get("type") == "relevance":
        found.add(cid["element"])
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            found |= _wrapper_ids(child)
    elif children is not None:
        found |= _wrapper_ids(children)
    return found


def test_the_callback_watches_only_the_elements_its_conditions_read():
    """Watching every field would re-run on every keystroke anywhere in the form."""
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_relevance_callbacks(app, FORMS)

    # callback_map stores component ids as JSON strings, not dicts.
    watched = set()
    outputs = set()
    for key, cb in app.callback_map.items():
        for i in cb["inputs"]:
            cid = json.loads(i["id"]) if isinstance(i["id"], str) else i["id"]
            if cid.get("type") == "input":
                watched.add(cid["element"])
        for part in key.split(".."):
            if '"type":"relevance"' in part.replace(" ", ""):
                outputs.add(part)

    assert watched == {"lawful_basis", "data_categories"}
    assert "name" not in watched
    assert len(outputs) == 4


def test_a_form_without_conditions_registers_no_callback():
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_relevance_callbacks(app, {"plain": {"elements": {"a": {"type": "string"}}, "meta": {}}})
    assert app.callback_map == {}
