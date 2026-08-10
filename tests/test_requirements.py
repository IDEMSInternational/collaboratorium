"""
`required:` follows relevance, and the submit button names what is missing.

The rule a checklist actually needs is not "Purpose is required" but "Purpose is
required *if* you claimed Legitimate Interest" — and a question the form is not
showing must never be demanded.
"""
import json

import pytest
from dash import Dash

from pantograph.relevance import FormConfigError
from pantograph.requirements import (
    ENABLED_LABEL,
    can_be_required,
    compile_required,
    is_static_required,
    label_for,
    outstanding,
    register_required_callbacks,
    submit_label,
    validate_forms,
    watched_elements,
)

FORM = {
    "label": "Processing Activity",
    "elements": {
        "name": {"type": "string", "label": "Name", "required": True},
        "lawful_basis": {"type": "select_one", "label": "Lawful Basis"},
        "collection_purpose": {
            "type": "string", "label": "Collection Purpose",
            "relevant": "${lawful_basis} = 'legitimate_interest'",
            "required": "${lawful_basis} = 'legitimate_interest'",
        },
        # Required whenever visible: the common case, needing no expression.
        "consent_record": {
            "type": "string", "label": "How consent is recorded",
            "relevant": "${lawful_basis} = 'consent'",
            "required": True,
        },
        "notes": {"type": "string", "label": "Notes"},
    },
    "meta": {},
}


def missing(**answers):
    return outstanding(FORM, answers, "ropa_form")


# --------------------------------------------------------------------------
# Required follows relevance
# --------------------------------------------------------------------------

def test_a_conditionally_required_field_is_demanded_only_when_its_condition_holds():
    assert "collection_purpose" in missing(name="x", lawful_basis="legitimate_interest")
    assert "collection_purpose" not in missing(name="x", lawful_basis="consent")


def test_a_question_that_is_not_shown_is_never_demanded():
    """
    Otherwise the form demands an answer it is not displaying: unfillable, with
    no cue as to why.
    """
    assert missing(name="x", lawful_basis="legal_obligation") == []
    assert "consent_record" not in missing(name="x", lawful_basis="legal_obligation")


def test_required_true_on_a_conditional_field_means_required_when_visible():
    assert "consent_record" in missing(name="x", lawful_basis="consent")
    assert "consent_record" not in missing(name="x", lawful_basis="legitimate_interest")


def test_an_unconditional_field_is_always_demanded():
    assert "name" in missing()
    assert "name" in missing(lawful_basis="consent")
    assert "name" not in missing(name="filled")


def test_an_optional_field_is_never_demanded():
    assert "notes" not in missing()
    assert "notes" not in missing(name="x", notes="")


def test_answering_the_last_outstanding_field_clears_the_list():
    assert missing(name="x", lawful_basis="legitimate_interest") == ["collection_purpose"]
    assert missing(name="x", lawful_basis="legitimate_interest",
                   collection_purpose="because") == []


@pytest.mark.parametrize("value", ["", "   ", None, [], {}])
def test_emptiness_matches_the_relevance_engine(value):
    assert "name" in outstanding(FORM, {"name": value}, "f")


def test_a_form_with_nothing_required_has_nothing_outstanding():
    plain = {"elements": {"a": {"type": "string"}}, "meta": {}}
    assert outstanding(plain, {}) == []


# --------------------------------------------------------------------------
# Saying which field is missing (TODO B)
# --------------------------------------------------------------------------

def test_the_button_names_a_single_missing_field():
    assert submit_label(FORM, ["name"]) == "Add Name to submit"


def test_the_button_names_two_and_three_missing_fields():
    assert submit_label(FORM, ["name", "notes"]) == "Add Name and Notes to submit"
    assert submit_label(FORM, ["name", "notes", "collection_purpose"]) == (
        "Add Name, Notes and Collection Purpose to submit"
    )


def test_a_long_list_is_summarised_rather_than_recited():
    label = submit_label(FORM, ["name", "notes", "collection_purpose", "consent_record"])
    assert label == "Add Name, Notes and 2 more to submit"


def test_the_button_reads_submit_when_nothing_is_outstanding():
    assert submit_label(FORM, []) == ENABLED_LABEL


def test_a_field_with_no_label_falls_back_to_a_readable_name():
    form = {"elements": {"some_field": {"type": "string", "required": True}}, "meta": {}}
    assert label_for(form, "some_field") == "some field"


# --------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------

def test_a_broken_required_expression_names_the_form_and_element():
    bad = {"f": {"elements": {"a": {"type": "string", "required": "${x} ==="}}, "meta": {}}}
    with pytest.raises(FormConfigError, match=r"f\.a.*required"):
        validate_forms({"forms": bad})


def test_a_required_expression_referencing_an_unknown_element_is_rejected():
    bad = {"f": {"elements": {"a": {"type": "string", "required": "${nope} = '1'"}}, "meta": {}}}
    with pytest.raises(FormConfigError, match="nope"):
        validate_forms({"forms": bad})


def test_a_nonsense_required_value_is_rejected():
    bad = {"f": {"elements": {"a": {"type": "string", "required": 42}}, "meta": {}}}
    with pytest.raises(FormConfigError, match="yes/no or an expression"):
        validate_forms({"forms": bad})


@pytest.mark.parametrize("raw, static, possible", [
    (True, True, True), ("yes", True, True), ("true", True, True),
    (False, False, False), ("no", False, False), (None, False, False), ("", False, False),
    ("${x} = '1'", False, True),
])
def test_required_spellings(raw, static, possible):
    assert is_static_required(raw) is static
    assert can_be_required(raw) is possible


def test_the_shipped_config_validates():
    from pantograph.config import load_config
    validate_forms(load_config("config"))


def test_static_required_still_compiles_without_an_expression():
    assert compile_required("f", FORM)["name"] is True


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

def test_the_callback_watches_the_required_fields_and_their_conditions():
    assert watched_elements("ropa_form", FORM) == [
        "collection_purpose", "consent_record", "lawful_basis", "name",
    ]
    assert "notes" not in watched_elements("ropa_form", FORM)


def test_a_form_with_nothing_required_registers_no_callback():
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_required_callbacks(app, {"plain": {"elements": {"a": {"type": "string"}}, "meta": {}}})
    assert app.callback_map == {}


def test_the_callback_outputs_the_submit_buttons_state():
    app = Dash(__name__, suppress_callback_exceptions=True)
    register_required_callbacks(app, {"ropa_form": FORM})
    keys = " ".join(app.callback_map).replace(" ", "")
    assert '"type":"submit"' in keys
    assert ".disabled" in keys and ".children" in keys


# --------------------------------------------------------------------------
# Server-side enforcement
# --------------------------------------------------------------------------

def test_a_submit_with_everything_answered_is_allowed():
    from pantograph.requirements import rejection_message
    assert rejection_message(FORM, {"name": "x", "lawful_basis": "consent",
                                    "consent_record": "signed"}) is None


def test_a_submit_missing_a_required_answer_is_refused_and_says_what_is_missing():
    """
    The disabled button is a courtesy; the client posts the callback directly
    and can send whatever it likes, so this is the check that actually decides.
    """
    from pantograph.requirements import rejection_message
    message = rejection_message(FORM, {"name": "", "lawful_basis": "consent"})
    assert message is not None
    assert "Name" in message and "How consent is recorded" in message
    assert "Not saved" in message


def test_refusal_respects_relevance_too():
    """A question the form is not showing must not block a save."""
    from pantograph.requirements import rejection_message
    assert rejection_message(FORM, {"name": "x", "lawful_basis": "legal_obligation"}) is None
