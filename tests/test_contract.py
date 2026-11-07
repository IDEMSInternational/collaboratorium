"""
The producer contract is derived from config, so these tests mostly assert that
a config change moves the contract and that nothing is hand-written into it.

The acceptance criteria being checked are in docs/agentic-ingest.md item B.
"""
import copy
import json

import pytest

from pantograph import contract


@pytest.fixture
def minimal_config():
    """
    A deployment this exporter has never seen, so a passing test cannot be
    explained by Collaboratorium's own table names.
    """
    return {
        "title": "Widgets",
        "default_forms": {"widgets": "widgets_form"},
        "tables": {"widgets": {"fields": {"id": "integer", "name": "string"}}},
        "forms": {
            "widgets_form": {
                "default_table": "widgets",
                "elements": {
                    "name": {"type": "string", "label": "Name", "required": True},
                    "colour": {
                        "type": "select_one", "label": "Colour",
                        "list_name": "colour_list",
                        "colour_list": ["red", "blue"],
                        "default": "red",
                    },
                    "owner": {
                        "type": "select_one", "label": "Owner",
                        "parameters": {"source_table": "people",
                                       "value_column": "id",
                                       "label_column": "name"},
                    },
                    "why": {
                        "type": "string", "label": "Why",
                        "relevant": "${colour} = 'red'",
                        "required": "${colour} = 'red'",
                    },
                    "notes": {
                        "type": "subform", "label": "Notes",
                        "parameters": {"1": {"body": {"type": "string",
                                                      "label": "Body"}}},
                    },
                    "groups": {
                        "type": "subform", "label": "Groups",
                        "parameters": {"source_table": "group_table",
                                       "value_column": "id",
                                       "label_column": "name"},
                    },
                    "contact": {"type": "email", "label": "Contact"},
                },
                "meta": {},
            }
        },
    }


def test_describes_every_table_that_has_a_form(minimal_config):
    document = contract.build(minimal_config)
    assert set(document["tables"]) == {"widgets"}
    assert document["tables"]["widgets"]["form"] == "widgets_form"
    assert document["deployment"] == "Widgets"


def test_serialises_as_json(minimal_config):
    # The contract is consumed by something that is not Python.
    json.loads(contract.dumps(minimal_config))


def test_static_and_conditional_required(minimal_config):
    elements = contract.build(minimal_config)["tables"]["widgets"]["elements"]
    assert elements["name"]["required"] is True
    assert elements["why"]["required"] == {"when": "${colour} = 'red'"}
    assert elements["why"]["relevant"] == {"when": "${colour} = 'red'"}
    # An element that is never required says nothing, rather than saying false.
    assert "required" not in elements["colour"]


def test_config_held_choices_are_stated(minimal_config):
    colour = contract.build(minimal_config)["tables"]["widgets"]["elements"]["colour"]
    assert colour["choices"] == {"values": ["red", "blue"], "default": "red"}


def test_table_held_choices_are_pointed_at_not_resolved(minimal_config):
    """
    The dominant trap: only `status` keeps its options in config. A contract
    that inlined the rest would be invalidated by every new person record.
    """
    owner = contract.build(minimal_config)["tables"]["widgets"]["elements"]["owner"]
    assert owner["choices"] == {
        "from_table": "people", "value_column": "id",
        "label_column": "name", "resolved_in": "snapshot",
    }
    assert "values" not in owner["choices"]


def test_static_subform_groups_are_described(minimal_config):
    notes = contract.build(minimal_config)["tables"]["widgets"]["elements"]["notes"]
    assert notes["subform"]["kind"] == "static"
    assert notes["subform"]["groups"]["1"]["body"]["type"] == "string"
    assert notes.get("accepts_suggestions") is not False


def test_a_vocabulary_subform_says_where_its_terms_live(minimal_config):
    """
    It used to be refused outright, on the ground that neither the contract nor
    the importer could check a value. Only half of that was ever true: the
    terms are rows, so this document cannot list them, but the snapshot carries
    those rows and the importer reads them. So it declares rather than refuses,
    exactly as a `select_multiple` over a table does.
    """
    groups = contract.build(minimal_config)["tables"]["widgets"]["elements"]["groups"]
    assert groups.get("accepts_suggestions") is not False
    assert groups["subform"]["kind"] == "dynamic"
    assert groups["subform"]["vocabulary"]["from_table"] == "group_table"
    assert groups["subform"]["vocabulary"]["resolved_in"] == "snapshot"


def test_a_vocabulary_subform_does_not_inline_its_terms(minimal_config):
    """The terms are data; inlining them would stale the contract on every edit."""
    groups = contract.build(minimal_config)["tables"]["widgets"]["elements"]["groups"]
    assert "values" not in groups["subform"]["vocabulary"]


def test_an_email_element_is_refused(minimal_config):
    contact = contract.build(minimal_config)["tables"]["widgets"]["elements"]["contact"]
    assert contact["accepts_suggestions"] is False


def test_hash_moves_when_a_choice_list_changes(minimal_config):
    """Item B's acceptance: editing a choice list changes the schema and hash."""
    before = contract.build(minimal_config)
    changed = copy.deepcopy(minimal_config)
    changed["forms"]["widgets_form"]["elements"]["colour"]["colour_list"].append("green")
    after = contract.build(changed)

    assert before["config_hash"] != after["config_hash"]
    assert (before["tables"]["widgets"]["elements"]["colour"]["choices"]
            != after["tables"]["widgets"]["elements"]["colour"]["choices"])


def test_hash_is_stable_across_key_order(minimal_config):
    """
    The config is merged from a directory in filename order, so the hash has to
    survive the same content arriving in a different order — otherwise renaming
    a config file reads as "the form changed".
    """
    reordered = {k: minimal_config[k] for k in reversed(list(minimal_config))}
    assert contract.config_hash(reordered) == contract.config_hash(minimal_config)


def test_hash_is_stable_across_calls(minimal_config):
    assert contract.config_hash(minimal_config) == contract.config_hash(minimal_config)


def test_link_elements_carry_their_link_table(minimal_config):
    minimal_config["forms"]["widgets_form"]["elements"]["parts"] = {
        "type": "select_multiple", "label": "Parts",
        "parameters": {"source_table": "parts", "value_column": "id",
                       "label_column": "name"},
        "store": {"link_table": "widget_part_links", "source_field": "widget_id",
                  "target_field": "part_id", "orientation": "forward"},
    }
    parts = contract.build(minimal_config)["tables"]["widgets"]["elements"]["parts"]
    assert parts["link"]["link_table"] == "widget_part_links"
    assert parts["link"]["source_field"] == "widget_id"


def test_a_form_named_in_default_forms_but_absent_is_skipped(minimal_config):
    """A config mid-edit should not take the exporter down."""
    minimal_config["default_forms"]["ghosts"] = "ghosts_form"
    assert "ghosts" not in contract.build(minimal_config)["tables"]


def test_real_deployment_config_exports(app_config):
    """
    The one test that uses this deployment's own config, to catch a shape the
    minimal fixture does not have.
    """
    document = contract.build(app_config)
    activities = document["tables"]["activities"]["elements"]

    assert activities["name"]["required"] is True
    assert activities["initiatives_links"]["required"] is True
    assert activities["tag_groups"]["subform"]["vocabulary"]["from_table"] == "tag_groups"
    # The activity summary is a static subform and must stay proposable: it is
    # the field a model is most useful at drafting.
    assert activities["description"]["subform"]["kind"] == "static"
    assert activities["description"].get("accepts_suggestions") is not False
    assert document["tables"]["initiatives"]["elements"]["status"]["choices"]["values"]
