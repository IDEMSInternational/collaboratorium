"""
The Report tab: acting on the report you are reading, and copying one that
knows nothing about this app.

The report is markdown, so its only affordance is a link, and the links are
routes (see pantograph.editor.parse_hash). Clicking one has to travel the whole
chain — markdown link -> url.hash -> core's load_form -> a prefilled add form —
which is why this is a browser test; the route parsing and the markdown
rendering are unit-tested in test_editor_requests.py and test_report_actions.py.

The session fixture seeds Initiative 1 with Activities 1-3 and the signed-in
person as responsible, and the default target entity is that person, so the
report has a hierarchy to render without touching any filter.
"""
import pytest
from playwright.sync_api import Page, expect

SEEDED_INITIATIVE = "Initiative 1"


def _open_report(page: Page):
    """Land on Explore's Report tab with a rendered, non-empty report."""
    page.goto("/")
    page.locator("#nav-explore").click()
    page.locator(".nav-link", has_text="Report").click()
    expect(page.locator("#report-container")).to_contain_text(
        SEEDED_INITIATIVE, timeout=20000
    )


def _action(page: Page, label):
    return page.locator("#report-container").get_by_role("link", name=label).first


# --------------------------------------------------------------------------
# Acting on what you just read
# --------------------------------------------------------------------------

def test_the_report_offers_its_configured_actions(app_config):
    """
    Guards the fixture these tests rest on: they assert against the deployment's
    own config, so a deployment that configured no actions would pass them
    vacuously.
    """
    initiatives = app_config["reports"]["annual_report"]["hierarchy"][0]
    labels = [a["label"] for a in initiatives["actions"]]
    assert "+ activity" in labels
    assert "+ sub-initiative" in labels


def test_adding_an_activity_from_the_report_links_it_to_that_initiative(page: Page):
    """
    The whole point: you notice work missing while reading the report, and
    record it without first going to find the initiative somewhere else.
    """
    _open_report(page)
    _action(page, "+ activity").click()

    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text(SEEDED_INITIATIVE)
    expect(editor.locator('[id*="initiatives_links"]').first).to_contain_text(
        SEEDED_INITIATIVE
    )


def test_adding_a_child_initiative_arrives_with_its_parent_set(page: Page):
    """
    The same route, pointed at an initiative's own `parents` element rather
    than an activity's link to it.
    """
    _open_report(page)
    _action(page, "+ sub-initiative").click()

    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(editor.locator('[id*="parents"]').first).to_contain_text(SEEDED_INITIATIVE)


def test_the_edit_action_still_opens_the_record(page: Page):
    """It moved out of the template into the actions; it must still work."""
    _open_report(page)
    _action(page, "✏️").click()

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit")


def test_the_same_action_can_be_clicked_twice(page: Page):
    """
    The editor clears the hash as it closes, so the next click on the same link
    is a change again and reopens it. Asserted because the callback that clears
    it used to match on the substring "edit", which would have left an add route
    sitting in the address bar — and a link that only works once is a link that
    looks broken.

    Waiting for the clear is part of the behaviour, not test hygiene: it is a
    callback round-trip, so a second click that lands before it arrives sets the
    hash to the value it already holds and nothing fires. That is true of the
    edit links as they stand too.
    """
    _open_report(page)
    editor = page.locator("#editor-popup")

    _action(page, "+ activity").click()
    expect(editor).to_be_visible()
    # Retried rather than pressed once: the modal reports visible while it is
    # still fading in, and a key that lands before its listeners are attached
    # is lost — a property of the test's speed, not of the app.
    for _ in range(5):
        page.keyboard.press("Escape")
        if not editor.is_visible():
            break
        page.wait_for_timeout(500)
    expect(editor).to_be_hidden()
    page.wait_for_function("() => window.location.hash === ''")

    _action(page, "+ activity").click()
    expect(editor).to_be_visible()


# --------------------------------------------------------------------------
# Reading it as a document
# --------------------------------------------------------------------------

def test_the_actions_can_be_switched_off_for_reading(page: Page):
    _open_report(page)
    report = page.locator("#report-container")
    expect(report.get_by_role("link", name="+ activity").first).to_be_visible()

    page.locator("#report-show-actions").uncheck()

    expect(report.get_by_role("link", name="+ activity")).to_have_count(0)
    expect(report).to_contain_text(SEEDED_INITIATIVE)


def test_the_switch_is_remembered(page: Page):
    """
    A personal preference, kept in the browser: someone who works from the
    clean document should not have to switch it off on every visit.
    """
    _open_report(page)
    page.locator("#report-show-actions").uncheck()
    expect(
        page.locator("#report-container").get_by_role("link", name="+ activity")
    ).to_have_count(0)

    _open_report(page)
    expect(page.locator("#report-show-actions")).not_to_be_checked()
