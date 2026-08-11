"""
The Records of Processing example config: it loads, it is internally coherent,
and the lawful-basis conditionals behave.

This is the config-only draft of the register (#65). Nothing here imports a
GDPR plugin, because there is not one: if a thing the register needs cannot be
asserted by these tests over plain YAML, that is a gap in the config dialect
rather than a reason to write Python.
"""
import sqlite3

import pytest

from pantograph.config import load_config
from pantograph.db import init_db
from pantograph.relevance import irrelevant_elements
from pantograph.relevance import validate_forms as validate_relevance
from pantograph.requirements import outstanding
from pantograph.requirements import validate_forms as validate_required

CONFIG_DIR = "examples/ropa/config"

# The decided grain. Named here so a change to it fails a test rather than
# quietly widening what one row means.
GRAIN = ["scope", "data_field", "purpose", "recipient", "data_subject_category"]


@pytest.fixture(scope="module")
def ropa():
    return load_config(CONFIG_DIR)


@pytest.fixture
def record_form(ropa):
    return ropa["forms"]["processing_records_form"]


def _answers(**overrides):
    """A live record with every gate answered, before the overrides."""
    base = {
        "name": "Phone number for SMS reminders",
        "scope": 1,
        "data_field": 1,
        "purpose": 1,
        "data_subject_category": 1,
        "disposition": "declared",
        "recipient_role": "processor",
        "recipient": 1,
        "agreement": 1,
        "lawful_basis": "consent",
        "special_category_data": "no",
        "retention_trigger": "collection",
        "retention_indefinite": "no",
        "retention_period_value": 3,
        "retention_period_unit": "years",
        "transfer_outside_uk_eea": "no",
        "consent_mechanism": 1,
        "consent_withdrawal_method": "Reply STOP",
        "status": "active",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# It loads, and startup validation passes
# --------------------------------------------------------------------------

def test_the_example_config_directory_loads(ropa):
    assert ropa["title"] == "Records of Processing"
    assert {"tables", "links", "forms", "default_forms", "plugins"} <= set(ropa)


def test_relevance_validation_passes(ropa):
    """Every `relevant:` parses and names elements its own form defines."""
    compiled = validate_relevance(ropa)
    assert compiled["processing_records_form"], "the conditionals went missing"


def test_required_validation_passes(ropa):
    compiled = validate_required(ropa)
    assert compiled["processing_records_form"]


# --------------------------------------------------------------------------
# Schema coherence
# --------------------------------------------------------------------------

def test_every_table_has_a_default_form_and_every_form_a_table(ropa):
    assert set(ropa["default_forms"]) == set(ropa["tables"])
    for table, form_name in ropa["default_forms"].items():
        assert ropa["forms"][form_name]["default_table"] == table


def test_every_link_points_at_a_real_table_and_column(ropa):
    for table, spec in ropa["links"].items():
        for mapping in spec["mappings"]:
            assert mapping["link_col"] in ropa["tables"][table]["fields"]
            target = ropa["tables"][mapping["target_table"]]["fields"]
            assert mapping["target_col"] in target


def test_every_column_is_answered_by_its_form(ropa):
    """
    The submit callback reads one value per column of the default table, so a
    column with no element and no meta strategy is a KeyError at first save,
    not a validation error at startup.
    """
    for table, form_name in ropa["default_forms"].items():
        form = ropa["forms"][form_name]
        answered = set(form["elements"]) | set(form["meta"])
        missing = set(ropa["tables"][table]["fields"]) - answered
        assert not missing, f"{form_name} answers nothing for {sorted(missing)}"


def test_every_dropdown_reads_a_real_table_and_column(ropa):
    for form_name, form in ropa["forms"].items():
        for element_id, element in form["elements"].items():
            if "list_name" in element or "parameters" not in element:
                continue
            params = element["parameters"]
            fields = ropa["tables"][params["source_table"]]["fields"]
            assert params["value_column"] in fields, f"{form_name}.{element_id}"
            assert params["label_column"] in fields, f"{form_name}.{element_id}"


def test_every_stored_link_writes_to_a_real_link_table(ropa):
    for form_name, form in ropa["forms"].items():
        for element_id, element in form["elements"].items():
            store = element.get("store")
            if not store:
                continue
            fields = ropa["tables"][store["link_table"]]["fields"]
            assert store["source_field"] in fields, f"{form_name}.{element_id}"
            assert store["target_field"] in fields, f"{form_name}.{element_id}"


def test_the_schema_creates(ropa, tmp_path, monkeypatch):
    """Types survive the DBML-to-SQLite mapping and the tables actually build."""
    db_path = tmp_path / "ropa.db"
    monkeypatch.setattr("pantograph.db._db_path", lambda: str(db_path))
    init_db(ropa)

    conn = sqlite3.connect(db_path)
    built = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert set(ropa["tables"]) <= built


# --------------------------------------------------------------------------
# The grain
# --------------------------------------------------------------------------

def test_the_fact_table_carries_the_decided_grain(ropa):
    fields = ropa["tables"]["processing_records"]["fields"]
    assert all(dimension in fields for dimension in GRAIN)


def test_every_grain_dimension_is_a_link_not_a_text_field(ropa):
    """
    Promoting a dimension later is mechanical if it was already a relationship
    and a re-interpretation of every row if it was not.
    """
    linked = {m["link_col"] for m in ropa["links"]["processing_records"]["mappings"]}
    assert set(GRAIN) <= linked


def test_scope_is_a_tree_rather_than_two_fixed_levels(ropa):
    parents = [
        m for m in ropa["links"]["scopes"]["mappings"]
        if m["target_table"] == "scopes"
    ]
    assert parents, "scopes has no self-link, so it cannot nest"
    levels = ropa["forms"]["scopes_form"]["elements"]["level"]["level_list"]
    assert len(levels) > 2


def test_data_fields_hang_off_a_scope_so_they_are_defined_once(ropa):
    product = ropa["links"]["data_fields"]["mappings"]
    assert any(m["link_col"] == "product" and m["target_table"] == "scopes"
               for m in product)


# --------------------------------------------------------------------------
# The lawful-basis conditionals — the acceptance criterion of #65
# --------------------------------------------------------------------------

BASIS_FOLLOW_UPS = {
    "consent": {"consent_mechanism", "consent_withdrawal_method"},
    "contract": {"contract_reference"},
    "legal_obligation": {"legal_obligation_reference"},
    "vital_interests": {"vital_interests_note"},
    "public_task": {"public_task_reference"},
    "legitimate_interest": {"assessment", "objection_method"},
}

ALL_FOLLOW_UPS = set().union(*BASIS_FOLLOW_UPS.values())


@pytest.mark.parametrize("basis,expected", sorted(BASIS_FOLLOW_UPS.items()))
def test_each_lawful_basis_shows_only_its_own_follow_ups(record_form, basis, expected):
    hidden = irrelevant_elements(record_form, _answers(lawful_basis=basis))
    assert ALL_FOLLOW_UPS & hidden == ALL_FOLLOW_UPS - expected


def test_legitimate_interest_demands_an_assessment(record_form):
    answers = _answers(lawful_basis="legitimate_interest")
    answers.pop("consent_mechanism")
    answers.pop("consent_withdrawal_method")
    missing = outstanding(record_form, answers)
    assert "assessment" in missing
    # And it does not ask for the consent questions it is no longer showing.
    assert "consent_mechanism" not in missing


def test_consent_does_not_demand_a_balancing_test(record_form):
    missing = outstanding(record_form, _answers(lawful_basis="consent"))
    assert missing == []


def test_an_unanswered_basis_asks_for_no_follow_up_at_all(record_form):
    """
    Emptiness is falsehood, so a basis nobody has picked must not leave every
    branch's questions on screen at once.
    """
    hidden = irrelevant_elements(record_form, _answers(lawful_basis=""))
    assert ALL_FOLLOW_UPS <= hidden


# --------------------------------------------------------------------------
# The other conditionals
# --------------------------------------------------------------------------

def test_a_removal_asks_only_why(record_form):
    """
    A scope that switched a feature off needs a row saying so, and that row
    should not also be claiming a lawful basis and a retention period.
    """
    answers = _answers(disposition="removed")
    hidden = irrelevant_elements(record_form, answers)
    assert "removal_reason" not in hidden
    assert {"lawful_basis", "retention_trigger", "recipient_role"} <= hidden

    answers.pop("removal_reason", None)
    assert outstanding(record_form, answers) == ["removal_reason"]


def test_a_live_record_does_not_ask_why_it_was_removed(record_form):
    assert "removal_reason" in irrelevant_elements(record_form, _answers())


def test_an_internal_record_asks_for_no_recipient_or_transfer(record_form):
    hidden = irrelevant_elements(record_form, _answers(recipient_role="internal"))
    assert {"recipient", "agreement", "transfer_outside_uk_eea"} <= hidden


def test_a_recipient_is_not_asked_for_before_the_role_is_picked(record_form):
    """`${recipient_role} and ...` guards the unanswered case."""
    hidden = irrelevant_elements(record_form, _answers(recipient_role=""))
    assert {"recipient", "agreement"} <= hidden


def test_only_a_processor_must_have_an_agreement(record_form):
    answers = _answers(recipient_role="separate_controller")
    answers.pop("agreement")
    assert "agreement" not in outstanding(record_form, answers)

    answers["recipient_role"] = "processor"
    assert "agreement" in outstanding(record_form, answers)


def test_an_adequacy_decision_needs_no_written_safeguard(record_form):
    answers = _answers(transfer_outside_uk_eea="yes",
                       transfer_country="India",
                       transfer_mechanism="adequacy")
    assert "transfer_safeguard" in irrelevant_elements(record_form, answers)

    answers["transfer_mechanism"] = "sccs"
    assert "transfer_safeguard" not in irrelevant_elements(record_form, answers)
    assert "transfer_safeguard" in outstanding(record_form, answers)


def test_a_safeguard_is_not_asked_for_before_the_mechanism_is_picked(record_form):
    answers = _answers(transfer_outside_uk_eea="yes", transfer_mechanism="")
    assert "transfer_safeguard" in irrelevant_elements(record_form, answers)


def test_indefinite_retention_swaps_the_period_for_a_justification(record_form):
    answers = _answers(retention_indefinite="yes")
    hidden = irrelevant_elements(record_form, answers)
    assert {"retention_period_value", "retention_period_unit"} <= hidden

    answers.pop("retention_justification", None)
    assert "retention_justification" in outstanding(record_form, answers)


def test_a_finite_retention_period_is_a_number_and_a_unit(ropa, record_form):
    """
    Typed rather than prose, so that "held longer than five years" is a query.
    The comparison works on the string a dcc.Input yields.
    """
    assert ropa["tables"]["processing_records"]["fields"]["retention_period_value"] == "integer"
    answers = _answers(retention_period_value="10")
    assert outstanding(record_form, answers) == []


def test_article_9_follows_the_special_category_gate(record_form):
    assert "article_9_condition" in irrelevant_elements(record_form, _answers())
    yes = _answers(special_category_data="yes")
    assert "article_9_condition" not in irrelevant_elements(record_form, yes)
    assert "article_9_condition" in outstanding(record_form, yes)


# --------------------------------------------------------------------------
# The register's own shape
# --------------------------------------------------------------------------

def test_a_processing_record_cites_an_assessment_rather_than_three_textareas(record_form):
    """A register that merely could deduplicate will not."""
    assessment = record_form["elements"]["assessment"]
    assert assessment["type"] == "select_one"
    assert assessment["parameters"]["source_table"] == "assessments"
    prose = {"purpose_test", "necessity_test", "balancing_test"}
    assert not prose & set(record_form["elements"])


def test_an_assessment_binds_one_of_each_written_part(ropa):
    elements = ropa["forms"]["assessments_form"]["elements"]
    for part in ("purpose", "necessity", "balancing"):
        assert elements[f"{part}_justification"]["type"] == "select_one"
        # Pinned by hand: links: maps one column to one column, so the citation
        # cannot be declared as a composite (id, version) foreign key.
        assert f"{part}_justification_version" in elements


def test_a_root_scope_needs_no_parent(ropa):
    form = ropa["forms"]["scopes_form"]
    assert "parent_scope" in irrelevant_elements(form, {"level": "product"})
    assert "parent_scope" in outstanding(form, {"level": "deployment", "name": "n"})


def test_the_deployment_mounts_no_plugin_whose_tables_it_lacks(ropa):
    """
    The register defines its own organisations and people rather than sharing
    Collaboratorium's, so a plugin assuming activities would fail at startup.
    """
    from pantograph.plugins import load_plugins

    plugins, landing = load_plugins(ropa)
    assert landing == "explore"
    for plugin in plugins:
        assert set(plugin.requires_tables) <= set(ropa["tables"])


def test_explore_only_graphs_tables_that_exist(ropa):
    assert set(ropa["node_tables"]) <= set(ropa["tables"])
