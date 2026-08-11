"""
Tapping the network graph opens the editor.

This is the path the editor-request seam replaced, and the one place where the
restructure changed runtime behaviour rather than structure. It resisted testing
because dash-cytoscape draws to a canvas, so there is no DOM node to click — but
cytoscape registers its instance on the container element as `_cyreg.cy`, and
emitting a tap through it exercises the real chain: cytoscape event ->
dash-cytoscape's tapNodeData/tapEdgeData -> the Explore bridge callback ->
the editor-request store -> core's load_form.

The graph is only reachable through Explore's Network Graph tab, so these are
browser tests; the translation logic itself is unit-tested in
test_editor_requests.py.
"""
import pytest
from playwright.sync_api import Page, expect

CY = "document.getElementById('cyto')._cyreg.cy"


def _open_graph(page: Page):
    """Land on Explore's graph tab with a rendered, non-empty graph."""
    page.goto("/")
    page.locator("#nav-explore").click()
    page.locator(".nav-link", has_text="Network Graph").click()
    # The default target entity is the signed-in person, so the degree view
    # holds them and the activities they are linked to.
    page.wait_for_function(
        "() => { const e = document.getElementById('cyto');"
        "        return e && e._cyreg && e._cyreg.cy && e._cyreg.cy.nodes().length > 0; }",
        timeout=20000,
    )


def _tap_node(page: Page, index=0):
    return page.evaluate(
        f"() => {{ const n = {CY}.nodes()[{index}]; n.emit('tap'); return n.id(); }}"
    )


def _tap_edge_where(page: Page, predicate_js):
    """
    Tap the first edge matching `predicate_js`, returning its data (or None when
    the current graph has no such edge).
    """
    return page.evaluate(
        f"() => {{ const e = {CY}.edges().filter(e => ({predicate_js})(e.data()))[0];"
        f"        if (!e) return null; e.emit('tap'); return e.data(); }}"
    )


def _expected_heading(app_config, table):
    """
    The editor heads the form with the *configured* label for the table's
    default form, which need not resemble the table name. Deriving it here
    rather than title-casing the table keeps the test honest about that.
    """
    form_name = app_config["default_forms"][table]
    return app_config["forms"][form_name]["label"]


def _close_editor(page: Page):
    page.locator("#form-container").get_by_text("Cancel").click()
    expect(page.locator("#editor-popup")).to_be_hidden()


# --------------------------------------------------------------------------

def test_tapping_a_node_opens_that_record_for_editing(page: Page, app_config):
    _open_graph(page)
    node_id = _tap_node(page)
    table = node_id.split("-", 1)[0]

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit", timeout=10000)
    # The form is the one configured for the tapped node's table, not just any form.
    expect(page.locator("#form-heading")).to_contain_text(_expected_heading(app_config, table))


def test_tapping_a_node_hides_the_add_a_table_dropdown(page: Page):
    """Tapping an existing record is an edit; offering "add new" alongside is noise."""
    _open_graph(page)
    _tap_node(page)
    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#add-dropdown-container")).to_be_hidden()


def test_tapping_the_same_node_again_reopens_the_editor(page: Page):
    """
    Reopening after a close is its own path: the editor is closed by one
    callback and reopened by another, off a store whose value may not have
    changed.

    Note this passes even with the request token stubbed to a constant, because
    dash-renderer re-dispatches on a reassigned Store value regardless of
    equality. It guards the reopen flow, not the token.
    """
    _open_graph(page)
    _tap_node(page)
    expect(page.locator("#editor-popup")).to_be_visible()

    _close_editor(page)

    _tap_node(page)
    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit", timeout=10000)


def test_tapping_a_link_edge_opens_the_link_record(page: Page, app_config):
    """An edge backed by a link table carries the record it was drawn from."""
    _open_graph(page)
    data = _tap_edge_where(page, "d => d.table_name && d.object_id !== undefined")
    if data is None:
        pytest.skip("no link-table edge in the default graph")

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit", timeout=10000)
    expect(page.locator("#form-heading")).to_contain_text(
        _expected_heading(app_config, data["table_name"])
    )


def test_tapping_an_edge_with_no_record_behind_it_says_so(page: Page):
    """
    Edges drawn from a foreign key column have no link row to open. The page
    that owns the graph supplies that wording, since core has none.
    """
    _open_graph(page)
    data = _tap_edge_where(page, "d => !d.table_name")
    if data is None:
        pytest.skip("no foreign-key edge in the default graph")

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-container")).to_contain_text("not editable", timeout=10000)
