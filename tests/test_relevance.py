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
