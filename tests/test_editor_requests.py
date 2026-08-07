"""
Tests for the editor-request seam between core and the pages that open the
editor.

The graph-tap path had no coverage at all before this, which is exactly why it
was risky to change: core used to read `cyto` directly, so a mistake in moving
that out would only show up when somebody tapped a node. The translation from a
tap to a request is now a set of plain functions, tested here, and the wiring
that carries the request is asserted structurally.
"""
import ast
import pathlib

import pytest

from pantograph.editor import STORE_ID, add_request, edit_request, message_request
from pantograph_explore.editor_bridge import (
    _node_is_newer,
    _request_for_edge,
    _request_for_node,
    _timestamp,
)

CORE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "pantograph"


# --------------------------------------------------------------------------
# Request construction
# --------------------------------------------------------------------------

def test_requests_carry_their_mode_and_token():
    assert edit_request("activities", 3, token=7) == {
        "mode": "edit", "table": "activities", "id": 3, "token": 7,
    }
    assert add_request("activities", {"a": 1}, "Add activity", token=7) == {
        "mode": "add", "table": "activities", "values": {"a": 1},
        "title": "Add activity", "token": 7,
    }
    assert message_request("nope", token=7) == {
        "mode": "message", "text": "nope", "token": 7,
    }


def test_add_request_defaults_values_to_an_empty_mapping():
    """So a consumer can index it without a None check."""
    assert add_request("activities")["values"] == {}


# --------------------------------------------------------------------------
# Translating a graph tap
# --------------------------------------------------------------------------

def test_node_tap_becomes_an_edit_request_for_its_table_and_id():
    request = _request_for_node({"id": "activities-12", "timeStamp": 100})
    assert request == {"mode": "edit", "table": "activities", "id": 12, "token": 100}


def test_node_id_splits_on_the_first_hyphen():
    """
    Node ids are "<table>-<id>", split on the first hyphen, so a table name
    containing one is not addressable. Pre-existing and unchanged here; recorded
    because it fails safe — a hyphenated table name yields the "invalid node"
    message rather than silently opening the wrong record.
    """
    assert _request_for_node({"id": "tag_groups-4"})["table"] == "tag_groups"
    assert _request_for_node({"id": "tag-groups-4"})["mode"] == "message"


@pytest.mark.parametrize("node", [
    {"id": "activities"},          # no id part
    {"id": "activities-abc"},      # non-numeric id
    {"id": None},
    {},
])
def test_an_unparseable_node_asks_for_a_message_not_a_form(node):
    request = _request_for_node(node)
    assert request["mode"] == "message"
    assert "Invalid node" in request["text"]


def test_edge_tap_with_a_backing_record_becomes_an_edit_request():
    request = _request_for_edge(
        {"table_name": "activity_people_links", "object_id": 5, "timeStamp": 9}
    )
    assert request == {
        "mode": "edit", "table": "activity_people_links", "id": 5, "token": 9,
    }


@pytest.mark.parametrize("edge", [
    {"label": "responsible for"},                      # drawn from a column
    {"table_name": "links", "object_id": None},
    {"table_name": None, "object_id": 5},
])
def test_edge_without_a_backing_record_explains_itself(edge):
    request = _request_for_edge(edge)
    assert request["mode"] == "message"
    assert "not editable" in request["text"]


def test_object_id_zero_is_a_record_not_a_missing_value():
    """`if not object_id` would wrongly reject id 0."""
    assert _request_for_edge({"table_name": "links", "object_id": 0})["mode"] == "edit"


# --------------------------------------------------------------------------
# Token, so a repeated tap still reopens the editor
# --------------------------------------------------------------------------

def test_token_comes_from_the_tap_timestamp():
    """
    Dash only fires on a *changed* value, so two taps on the same node must not
    produce equal requests or the editor would not reopen after being closed.
    """
    first = _request_for_node({"id": "activities-1", "timeStamp": 100})
    second = _request_for_node({"id": "activities-1", "timeStamp": 250})
    assert first != second
    assert (first["token"], second["token"]) == (100, 250)


@pytest.mark.parametrize("tap, expected", [
    ({"timeStamp": 5}, 5),
    ({"timeStamp": "5"}, 5),
    ({"timeStamp": None}, None),
    ({"timeStamp": "nonsense"}, None),
    ({}, None),
    (None, None),
])
def test_timestamp_reading_survives_whatever_cytoscape_supplies(tap, expected):
    assert _timestamp(tap) == expected


# --------------------------------------------------------------------------
# Node/edge tie-break, when Dash dispatches both in one batch
# --------------------------------------------------------------------------

def test_the_more_recent_tap_wins():
    assert _node_is_newer({"timeStamp": 200}, {"timeStamp": 100}) is True
    assert _node_is_newer({"timeStamp": 100}, {"timeStamp": 200}) is False


def test_a_node_and_edge_tapped_at_the_same_instant_resolve_to_the_node():
    """Clicking a node that sits on an edge should open the node."""
    assert _node_is_newer({"timeStamp": 100}, {"timeStamp": 100}) is True


def test_an_untimed_tap_loses_to_a_timed_one():
    assert _node_is_newer({}, {"timeStamp": 100}) is False
    assert _node_is_newer({"timeStamp": 100}, {}) is True


# --------------------------------------------------------------------------
# The wiring that carries a request
# --------------------------------------------------------------------------

def _inputs_of(app, output_fragment):
    for key, callback in app.callback_map.items():
        if output_fragment in key:
            yield key, {f"{i['id']}.{i['property']}" for i in callback["inputs"]}


def test_core_opens_the_editor_from_a_request(dash_app):
    """Both the form it renders and the container it renders into must listen."""
    for fragment in ["form-container.children", "editor-popup.is_open"]:
        listeners = list(_inputs_of(dash_app, fragment))
        assert listeners, f"no callback outputs {fragment}"
        for key, inputs in listeners:
            assert f"{STORE_ID}.data" in inputs, f"{key} does not listen to {STORE_ID}"


def test_explore_publishes_graph_taps_as_requests(dash_app):
    publishers = list(_inputs_of(dash_app, f"{STORE_ID}.data"))
    assert publishers, "nothing publishes editor requests"
    assert any(
        {"cyto.tapNodeData", "cyto.tapEdgeData"} <= inputs for _, inputs in publishers
    ), "the graph does not publish taps as editor requests"


def test_core_names_no_explore_component():
    """
    An architectural guard, not a behaviour test. Core used to reference `cyto`
    directly; a deployment without Explore then relied on
    suppress_callback_exceptions to paper over the missing component. Prose in
    docstrings is fine — component ids are not.
    """
    offenders = []
    for path in CORE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == "cyto" and node.value not in docstrings:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"core references the Explore graph at {offenders}"
