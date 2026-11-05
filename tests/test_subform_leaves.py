"""
Addressing one field inside a subform, and the three things that then work on it.

Before this, a subform's fields were invisible to everything that works per
element: provenance, `required:` and the producer contract all match on the
parent form's elements, and a leaf is not one. Three separate wants pointed at
the same seam, so these tests are grouped by which one they cover.

The load-bearing trick is in `_leaf`: a leaf's provenance block carries the
**parent** form's name and the leaf's path, while its input keeps the subform's
own namespace. That is what lets the submit callback's existing `element: ALL`
and the confirm callback's existing `MATCH` pick a leaf up with no change.
"""
import json

import pytest

from pantograph import provenance, requirements, subforms
from pantograph.component_factory import generate_subform_block, leaf_store_id
from pantograph.form_gen import generate_form_layout
from pantograph.relevance import FormConfigError

PATH = "description.1.description"
SUBFORM_VALUE = {"1": {"description": "drafted by a model", "attachments": []}}


def _ids(component):
    """Every pattern-matching id in a rendered tree."""
    found = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict):
            found.append(node_id)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children if isinstance(children, (list, tuple)) else [children])

    walk(component)
    return found


@pytest.fixture
def leafy_form():
    """A form with a static subform whose fields are addressable."""
    return {
        "widgets_form": {
            "default_table": "widgets",
            "elements": {
                "name": {"type": "string", "label": "Name", "required": True},
                "detail": {
                    "type": "subform", "label": "Detail",
                    "parameters": {
                        "1": {
                            "summary": {"type": "string", "label": "Summary",
                                        "required": True},
                            "note": {"type": "string", "label": "Note"},
                        }
                    },
                },
                "tags": {
                    "type": "subform", "label": "Tags",
                    "parameters": {"source_table": "tag_groups",
                                   "value_column": "id", "label_column": "name"},
                },
            },
            "meta": {},
        }
    }


# --------------------------------------------------------------------------
# The paths themselves
# --------------------------------------------------------------------------

def test_a_path_round_trips():
    path = subforms.leaf_path("description", "1", "description")
    assert path == PATH
    assert subforms.split_leaf(path) == ("description", "1", "description")


def test_an_element_name_is_not_a_leaf_path():
    assert not subforms.is_leaf_path("description")
    assert not subforms.is_leaf_path("responsible_person")
    assert subforms.split_leaf("a.b") is None
    assert subforms.split_leaf(None) is None


def test_a_field_name_containing_a_dot_survives():
    """
    The element id and group id are ours; a field name comes from a
    deployment's config or from a row in its database.
    """
    assert subforms.split_leaf("tags.3.a.b") == ("tags", "3", "a.b")


def test_leaf_value_reads_a_dict_or_the_json_it_was_stored_as():
    as_dict = {"description": SUBFORM_VALUE}
    as_json = {"description": json.dumps(SUBFORM_VALUE)}
    for values in (as_dict, as_json):
        assert subforms.leaf_value(values, PATH) == "drafted by a model"
    assert subforms.leaf_value({}, PATH) is None
    assert subforms.leaf_value({"description": "not json"}, PATH) is None


def test_static_leaves_skips_a_vocabulary_subform(leafy_form):
    """
    A dynamic subform's groups are rows in another table, so there is nothing
    in the config to walk — the same fact that makes the contract refuse to
    state its values.
    """
    paths = [p for p, _ in subforms.static_leaves(leafy_form["widgets_form"])]
    assert paths == ["detail.1.summary", "detail.1.note"]
    assert not any(p.startswith("tags.") for p in paths)


# --------------------------------------------------------------------------
# Provenance on a leaf
# --------------------------------------------------------------------------

def test_the_leaf_block_is_keyed_to_the_parent_form(app_config):
    """
    The whole trick. A leaf's provenance ids carry the parent form so the
    submit callback's `element: ALL` and the confirm callback's `MATCH` reach
    it unchanged; the input keeps the subform namespace so
    `handle_subform_block` still gathers it.
    """
    element = dict(app_config["forms"]["activities_form"]["elements"]["description"],
                   element_id="description")
    record = provenance.record("cited", origin="ar2021", confidence=0.6)

    ids = _ids(generate_subform_block(
        element, "activities_form", json.dumps(SUBFORM_VALUE),
        {PATH: record}, "activities_form"))

    assert provenance.store_id("activities_form", PATH) in ids
    assert provenance.confirm_id("activities_form", PATH) in ids
    assert provenance.container_id("activities_form", PATH) in ids
    assert {"type": "input", "form": "activities_form-description",
            "element": "1|description"} in ids


def test_only_the_leaf_with_a_provenance_is_wrapped(app_config):
    element = dict(app_config["forms"]["activities_form"]["elements"]["description"],
                   element_id="description")
    ids = _ids(generate_subform_block(
        element, "activities_form", json.dumps(SUBFORM_VALUE),
        {PATH: provenance.record("suggested", origin="r")}, "activities_form"))
    assert provenance.container_id("activities_form",
                                   "description.1.attachments") not in ids


def test_a_subform_renders_as_before_when_nothing_supplies_one(app_config):
    element = dict(app_config["forms"]["activities_form"]["elements"]["description"],
                   element_id="description")
    ids = _ids(generate_subform_block(element, "activities_form",
                                      json.dumps(SUBFORM_VALUE), None, "activities_form"))
    assert not [i for i in ids if str(i.get("type", "")).startswith("provenance")]


def test_the_form_mounts_a_store_per_subform_element(app_config):
    """
    A subform's body is built by a callback, so the records cannot be handed
    to the renderer directly — they wait in a store it reads.
    """
    layout = generate_form_layout(
        "activities_form", app_config["forms"],
        initial_values={"name": "x", "description": SUBFORM_VALUE},
        provenances={PATH: provenance.record("cited", origin="ar2021")})

    stores = {i["element"]: i for i in _ids(layout)
              if i.get("type") == "subform-provenance"}
    assert "description" in stores and "tag_groups" in stores


def test_each_store_carries_only_its_own_element_s_leaves(app_config):
    layout = generate_form_layout(
        "activities_form", app_config["forms"],
        initial_values={"name": "x", "description": SUBFORM_VALUE},
        provenances={PATH: provenance.record("cited", origin="ar2021"),
                     "tag_groups.3.impact_area": provenance.record("suggested",
                                                                   origin="r")})

    carried = {}

    def walk(node):
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        node_id = getattr(node, "id", None)
        if isinstance(node_id, dict) and node_id.get("type") == "subform-provenance":
            carried[node_id["element"]] = getattr(node, "data", None) or {}
        children = getattr(node, "children", None)
        if children is not None:
            walk(children if isinstance(children, (list, tuple)) else [children])

    walk(layout)
    assert list(carried["description"]) == [PATH]
    assert list(carried["tag_groups"]) == ["tag_groups.3.impact_area"]


# --------------------------------------------------------------------------
# Editing a leaf disowns its origin
#
# This is the part element-level provenance could never do: a subform's value
# is a dict, `_comparable` declines to compare one, so the claim survived any
# edit. Per leaf, prose compares exactly again.
# --------------------------------------------------------------------------

def test_editing_the_leaf_drops_its_provenance():
    record = provenance.record("suggested", origin="run-4")
    before = {"description": json.dumps(SUBFORM_VALUE)}
    after = {"description": {"1": {"description": "rewritten by a person",
                                   "attachments": []}}}
    assert provenance.surviving_edits({PATH: record}, before, after) == {}


def test_a_leaf_that_did_not_change_keeps_it():
    """The stored JSON against the dict the browser sends is not an edit."""
    record = provenance.record("suggested", origin="run-4")
    before = {"description": json.dumps(SUBFORM_VALUE)}
    after = {"description": SUBFORM_VALUE}
    assert PATH in provenance.surviving_edits({PATH: record}, before, after)


def test_editing_a_sibling_leaf_does_not_disown_this_one():
    record = provenance.record("suggested", origin="run-4")
    before = {"description": json.dumps(SUBFORM_VALUE)}
    after = {"description": {"1": {"description": "drafted by a model",
                                   "attachments": [{"name": "a", "url": "b"}]}}}
    assert PATH in provenance.surviving_edits({PATH: record}, before, after)


def test_element_level_behaviour_is_unchanged():
    record = provenance.record("suggested", origin="run-4")
    assert provenance.surviving_edits({"name": record}, {"name": "A"},
                                      {"name": "B"}) == {}
    assert "name" in provenance.surviving_edits({"name": record}, {"name": "A"},
                                                {"name": "A"})


# --------------------------------------------------------------------------
# required: on a leaf
# --------------------------------------------------------------------------

def test_a_required_leaf_is_compiled(leafy_form):
    compiled = requirements.compile_required("widgets_form",
                                             leafy_form["widgets_form"])
    assert compiled["detail.1.summary"] is True
    assert "detail.1.note" not in compiled


def test_an_empty_required_leaf_blocks_the_save(leafy_form):
    form = leafy_form["widgets_form"]
    values = {"name": "a widget", "detail": {"1": {"summary": "", "note": "x"}}}
    assert requirements.rejection_message(form, values, "widgets_form")
    assert "detail.1.summary" in requirements.outstanding(form, values,
                                                          "widgets_form")


def test_a_filled_required_leaf_does_not(leafy_form):
    form = leafy_form["widgets_form"]
    values = {"name": "a widget", "detail": {"1": {"summary": "filled"}}}
    assert requirements.rejection_message(form, values, "widgets_form") is None


def test_a_required_leaf_reads_the_stored_json_too(leafy_form):
    form = leafy_form["widgets_form"]
    values = {"name": "a widget", "detail": json.dumps({"1": {"summary": "filled"}})}
    assert requirements.rejection_message(form, values, "widgets_form") is None


def test_an_unconfirmed_required_leaf_is_refused(leafy_form):
    """
    The same rule the rest of the form has: a value nobody here has stood
    behind does not answer a required question.
    """
    form = leafy_form["widgets_form"]
    values = {"name": "a widget", "detail": {"1": {"summary": "drafted"}}}
    message = requirements.rejection_message(
        form, values, "widgets_form",
        provenances={"detail.1.summary": provenance.record("suggested",
                                                            origin="run-4")})
    assert message and "not confirmed" in message


def test_a_leaf_is_named_not_pathed_in_a_message(leafy_form):
    form = leafy_form["widgets_form"]
    values = {"name": "a widget", "detail": {"1": {"summary": ""}}}
    message = requirements.rejection_message(form, values, "widgets_form")
    assert "Detail — Summary" in message
    assert "detail.1.summary" not in message


def test_a_conditional_requirement_on_a_leaf_is_refused_at_startup(leafy_form):
    """
    An expression inside a subform resolves against the enclosing form's state,
    which is the limit `relevant:` has. Better to say so at startup than to
    evaluate it against the wrong scope.
    """
    leafy_form["widgets_form"]["elements"]["detail"]["parameters"]["1"]["note"][
        "required"] = "${name} = 'x'"
    with pytest.raises(FormConfigError, match="subform field"):
        requirements.compile_required("widgets_form", leafy_form["widgets_form"])


def test_the_deployment_s_own_forms_still_compile(app_config):
    requirements.validate_forms(app_config)


# --------------------------------------------------------------------------
# A leaf in the producer contract
# --------------------------------------------------------------------------

def test_a_leaf_can_be_refused_to_a_producer(leafy_form):
    from pantograph import contract

    leafy_form["widgets_form"]["elements"]["detail"]["parameters"]["1"]["note"][
        "producer"] = False
    document = contract.build({
        "default_forms": {"widgets": "widgets_form"},
        "forms": leafy_form, "tables": {"widgets": {"fields": {}}},
    })
    groups = document["tables"]["widgets"]["elements"]["detail"]["subform"]["groups"]
    assert groups["1"]["note"]["accepts_suggestions"] is False
    assert groups["1"]["summary"].get("accepts_suggestions") is not False


def test_a_required_leaf_is_stated_in_the_contract(leafy_form):
    from pantograph import contract

    document = contract.build({
        "default_forms": {"widgets": "widgets_form"},
        "forms": leafy_form, "tables": {"widgets": {"fields": {}}},
    })
    groups = document["tables"]["widgets"]["elements"]["detail"]["subform"]["groups"]
    assert groups["1"]["summary"]["required"] is True
    assert "required" not in groups["1"]["note"]
