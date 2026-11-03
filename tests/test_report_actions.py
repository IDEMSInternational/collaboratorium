"""
Tests for the actions a report offers — the edit link, and the add links that
let someone record missing work from the report they noticed it was missing in.

Two things are worth holding still here. The first is that the actions are
removable: they exist so a reader can act on what they just read, and the same
document has to be copyable into a final report with nothing in it that
addresses this app. That is why they are config rather than link syntax typed
into a template, and the test that the two renders differ by exactly the
actions is the point of the whole arrangement.

The second is that an action names a table and a form element, and a route
carries no more than that. Nothing checks at runtime that the pair exists, so
it is checked here against the deployment's own config instead of failing as a
dead link years later.
"""
import json

import pandas as pd
import pytest

from pantograph.report_generator import (
    _action_link,
    _render_actions,
    generate_markdown_report,
)


EMPTY_CONTEXT = {
    "people_map": {},
    "act_people_df": pd.DataFrame(columns=["activity_id", "person_id"]),
    "provenance_by_row": {},
}


def _nodes(*nodes):
    return [{"data": node} for node in nodes]


def _initiative(record_id=1, name="Water Access"):
    return {
        "id": f"initiatives-{record_id}",
        "type": "initiatives",
        "label": name,
        "properties": {"name": name, "version": 1},
    }


# --------------------------------------------------------------------------
# One action, as a link
# --------------------------------------------------------------------------

def test_an_edit_action_addresses_the_record_it_is_rendered_against():
    link = _action_link({"label": "edit", "mode": "edit"}, "initiatives", 4)
    assert link == '<a class="report-action" href="#edit/initiatives/4">edit</a>'


def test_edit_is_the_default_mode():
    """The commonest action, and the one that predates the others."""
    assert 'href="#edit/activities/2"' in _action_link({"label": "e"}, "activities", 2)


def test_an_add_action_links_the_new_record_to_this_one():
    """
    The id in the route is the record being read, and the element is on the form
    of the record being created: a new activity's `initiatives_links`.
    """
    link = _action_link(
        {"label": "+ activity", "mode": "add", "table": "activities",
         "element": "initiatives_links"},
        "initiatives", 4,
    )
    assert 'href="#add/activities/initiatives_links/4"' in link
    assert ">+ activity</a>" in link


def test_an_add_action_with_no_element_opens_an_unlinked_form():
    link = _action_link({"label": "+", "mode": "add", "table": "activities"},
                        "initiatives", 4)
    assert 'href="#add/activities"' in link


def test_adding_is_accented_and_editing_is_not():
    """
    The same distinction the dashboard draws between its own two: recording
    work is the thing worth reaching for.
    """
    add = _action_link({"label": "+", "mode": "add", "table": "activities"}, "initiatives", 1)
    edit = _action_link({"label": "e", "mode": "edit"}, "initiatives", 1)
    assert "report-action-go" in add
    assert "report-action-go" not in edit


@pytest.mark.parametrize("action", [
    {"mode": "edit"},                                  # no label to click
    {"label": "+", "mode": "add"},                     # no table to add to
    {"label": "?", "mode": "sideways"},                # not a mode we serve
])
def test_an_action_that_cannot_be_built_is_dropped_not_guessed_at(action):
    assert _action_link(action, "initiatives", 4) is None


# --------------------------------------------------------------------------
# The {actions} substitution
# --------------------------------------------------------------------------

def test_actions_render_in_configured_order_as_one_row():
    """
    One element, not loose links: a template can give the row a line of its own
    and have the whole line come and go with the switch.
    """
    level = {"actions": [
        {"label": "a", "mode": "edit"},
        {"label": "b", "mode": "add", "table": "activities"},
    ]}
    rendered = _render_actions(level, "initiatives", 1, True)
    assert rendered.startswith('<div class="report-actions">')
    assert rendered.endswith("</div>")
    assert rendered.index(">a</a>") < rendered.index(">b</a>")


def test_actions_render_as_nothing_when_they_are_switched_off():
    level = {"actions": [{"label": "a", "mode": "edit"}]}
    assert _render_actions(level, "initiatives", 1, False) == ""


@pytest.mark.parametrize("level", [{}, {"actions": None}, {"actions": []}])
def test_a_level_with_no_actions_renders_nothing(level):
    assert _render_actions(level, "initiatives", 1, True) == ""


# --------------------------------------------------------------------------
# The whole report, with and without them
# --------------------------------------------------------------------------

REPORT_CFG = {
    "name": "Annual Activity Report",
    "hierarchy": [{
        "type": "initiatives",
        "template": "## {name} {actions}\n\n{description}\n\n",
        "actions": [
            {"label": "edit", "mode": "edit"},
            {"label": "+ activity", "mode": "add", "table": "activities",
             "element": "initiatives_links"},
        ],
    }],
}


def test_a_report_renders_its_actions_into_the_placeholder():
    md = generate_markdown_report(
        REPORT_CFG, _nodes(_initiative()), include_actions=True, context=EMPTY_CONTEXT,
    )
    assert 'href="#edit/initiatives/1"' in md
    assert 'href="#add/activities/initiatives_links/1"' in md
    assert '<div class="report-actions">' in md


def test_the_two_renders_differ_by_the_actions_and_nothing_else():
    """
    The reason the actions are config and not link syntax inside the template:
    the copy a reader pastes into a final document is the same document, minus
    exactly this app's own affordances.
    """
    elements = _nodes(_initiative())
    shown = generate_markdown_report(
        REPORT_CFG, elements, include_actions=True, context=EMPTY_CONTEXT,
    )
    clean = generate_markdown_report(
        REPORT_CFG, elements, include_actions=False, context=EMPTY_CONTEXT,
    )
    assert "#edit/" in shown and "#add/" in shown
    assert "#edit/" not in clean and "#add/" not in clean
    assert "Water Access" in clean
    actions = _render_actions(REPORT_CFG["hierarchy"][0], "initiatives", 1, True)
    assert shown.replace(actions, "").strip() == clean.strip()


def test_a_description_containing_a_link_survives_being_cleaned():
    """
    What hunting link syntax out of the rendered markdown would have broken.
    A description is someone's prose and may hold links of its own; the
    attachments formatter emits them too.
    """
    node = _initiative()
    node["properties"]["description"] = "See [the policy](https://example.org/p)."
    clean = generate_markdown_report(
        REPORT_CFG, _nodes(node), include_actions=False, context=EMPTY_CONTEXT,
    )
    assert "[the policy](https://example.org/p)" in clean


def test_an_actions_placeholder_does_not_consult_the_row_for_a_column():
    """
    `{actions}` goes through the same substitution as every other placeholder,
    so a table with a column called `actions` must not be able to render where
    the links go.
    """
    node = _initiative()
    node["properties"]["actions"] = "a column, not the affordances"
    md = generate_markdown_report(
        REPORT_CFG, _nodes(node), include_actions=True, context=EMPTY_CONTEXT,
    )
    assert "a column, not the affordances" not in md
    assert 'href="#edit/initiatives/1"' in md


# --------------------------------------------------------------------------
# The deployment's own config
# --------------------------------------------------------------------------

def _levels(hierarchy):
    for level in hierarchy or []:
        yield level
        yield from _levels(level.get("children"))


def _configured_levels(app_config):
    for report_cfg in app_config.get("reports", {}).values():
        yield from _levels(report_cfg.get("hierarchy"))


def test_every_level_with_actions_has_somewhere_to_put_them(app_config):
    """Actions configured against a template with no `{actions}` never render."""
    for level in _configured_levels(app_config):
        if level.get("actions"):
            assert "{actions}" in level.get("template", ""), (
                f"{level.get('type')} configures actions its template cannot show"
            )


def test_every_add_action_names_a_real_form_element(app_config):
    """
    A route carries a table and an element name and is resolved at click time,
    so a typo here is a dead link rather than an error. Checked against the
    deployment's own forms config instead.
    """
    forms = app_config.get("forms", {})
    default_forms = app_config.get("default_forms", {})

    for level in _configured_levels(app_config):
        for action in level.get("actions") or []:
            if action.get("mode") != "add":
                continue
            table = action["table"]
            form_name = default_forms.get(table)
            assert form_name, f"no default form for '{table}'"
            element = action.get("element")
            if not element:
                continue
            elements = forms[form_name].get("elements", {})
            assert element in elements, (
                f"'{element}' is not an element of {form_name}"
            )
            # The title the editor builds reads the linked record's own label
            # off this element's source table, so the pair has to be there.
            parameters = elements[element].get("parameters") or {}
            assert parameters.get("source_table"), f"{element} has no source_table"
            assert parameters.get("label_column"), f"{element} has no label_column"


def _report_renderer(dash_app):
    """The Report tab's own callback, with the clipboard among its outputs."""
    for key, callback in dash_app.callback_map.items():
        if "report-container.children" in key:
            return key, callback
    pytest.fail("nothing renders the report")


def _render(dash_app, elements, show_actions):
    """
    Call the registered callback as the renderer would. Dash's wrapper wants the
    outputs it is answering, which also pins their order: body, copy, title.
    """
    _, callback = _report_renderer(dash_app)
    outputs = [
        {"id": "report-container", "property": "children"},
        {"id": "report-clipboard", "property": "content"},
        {"id": "report-title", "property": "children"},
    ]
    return json.loads(
        callback["callback"](elements, show_actions, outputs_list=outputs)
    )["response"]


def _markdown_of(rendered):
    """The markdown inside the rendered body: html.Div -> dcc.Markdown."""
    body = rendered["report-container"]["children"]
    return body["props"]["children"]["props"]["children"]


def test_what_the_copy_button_carries_has_no_routes_in_it(dash_app):
    """
    The decision this holds in place: the toggle governs the page, and the copy
    is clean either way. Someone who never touches the switch still pastes a
    document with nothing in it that addresses this app.

    Driven through the registered callback rather than a browser, because the
    clipboard's content is a prop rather than anything in the DOM.
    """
    rendered = _render(dash_app, _nodes(_initiative()), True)
    body = _markdown_of(rendered)
    copied = rendered["report-clipboard"]["content"]

    assert "#add/activities/initiatives_links/1" in body
    assert "#add/" not in copied and "#edit/" not in copied
    assert "Water Access" in copied
    assert rendered["report-title"]["children"] == "Annual Activity Report"


def test_switching_the_actions_off_changes_the_page_not_the_copy(dash_app):
    with_actions = _render(dash_app, _nodes(_initiative()), True)
    without = _render(dash_app, _nodes(_initiative()), False)

    assert "#add/" in _markdown_of(with_actions)
    assert "#add/" not in _markdown_of(without)
    assert (
        with_actions["report-clipboard"]["content"]
        == without["report-clipboard"]["content"]
    )


def test_the_report_copies_without_the_actions_it_displays(dash_app):
    """
    A structural guard on the arrangement, not on the markdown: whatever
    renders the report body must also set what the clipboard carries, from the
    same callback and the same switch. Split across two callbacks, the copy
    could silently go back to carrying whatever is on screen.
    """
    renderers = [
        (key, {f"{i['id']}.{i['property']}" for i in callback["inputs"]})
        for key, callback in dash_app.callback_map.items()
        if "report-container.children" in key
    ]
    assert renderers, "nothing renders the report"
    for key, inputs in renderers:
        assert "report-clipboard.content" in key, (
            "the report body and the clipboard are set by different callbacks"
        )
        assert "report-show-actions.value" in inputs, (
            "the report does not read the actions switch"
        )
