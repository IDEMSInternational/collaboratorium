"""
A callback that raises used to be invisible: the component it feeds stays as it
was and nothing says anything happened, which is how an empty review queue read
as "nothing here". The server now logs each failure with a reference and returns
it in a header; the page shows a banner quoting it.
"""
import logging

from playwright.sync_api import Page, expect

def _dispatch_endpoint(server):
    return next(rule.endpoint for rule in server.url_map.iter_rules()
                if rule.rule == "/_dash-update-component")


def test_a_failed_callback_is_logged_once_with_a_reference(dash_app, caplog, monkeypatch):
    server = dash_app.server

    def raising(*args, **kwargs):
        raise RuntimeError("the queue could not be built")

    monkeypatch.setitem(server.view_functions, _dispatch_endpoint(server), raising)
    monkeypatch.setitem(server.config, "PROPAGATE_EXCEPTIONS", False)
    with caplog.at_level(logging.ERROR, logger="pantograph.callbacks"):
        response = server.test_client().post(
            "/_dash-update-component",
            json={"output": "import-queue.children", "inputs": []})

    assert response.status_code == 500
    reference = response.headers["X-Error-Id"]
    assert len(reference) == 8

    records = [r for r in caplog.records if r.name == "pantograph.callbacks"]
    assert len(records) == 1
    assert reference in records[0].getMessage()
    assert "import-queue.children" in records[0].getMessage()
    assert records[0].exc_info and "could not be built" in str(records[0].exc_info[1])


def test_an_error_elsewhere_carries_no_reference(dash_app, monkeypatch):
    """Only callback requests are tagged; nothing else about errors changes."""
    server = dash_app.server

    def raising(*args, **kwargs):
        raise RuntimeError("not a callback")

    # Dash's own index route stands in for any page: it is not a callback.
    index = next(rule.endpoint for rule in server.url_map.iter_rules()
                 if rule.rule == "/")
    monkeypatch.setitem(server.view_functions, index, raising)
    monkeypatch.setitem(server.config, "PROPAGATE_EXCEPTIONS", False)
    response = server.test_client().get("/")
    assert response.status_code == 500
    assert "X-Error-Id" not in response.headers


def test_the_page_says_so_when_a_callback_fails(page: Page):
    page.route(
        "**/_dash-update-component",
        lambda route: route.fulfill(
            status=500, body="boom",
            headers={"X-Error-Id": "ab12cd34",
                     "Access-Control-Expose-Headers": "X-Error-Id"}))
    page.goto("/")

    banner = page.locator("#pantograph-callback-failure")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("failed to update")
    expect(banner).to_contain_text("ab12cd34")

    banner.get_by_role("button", name="Dismiss").click()
    expect(banner).to_have_count(0)
