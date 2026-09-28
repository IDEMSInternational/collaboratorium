"""
`#edit/<table>/<id>` routing.

Report templates emit these links so a reader can get from a figure back to
the record behind it, and the link is usually pasted somewhere else and
followed from cold. Arriving with the route already in the URL has to work,
not just setting it on a page that is already open.
"""
from playwright.sync_api import Page, expect

NAME_INPUT = '[id*=\'"element":"name"\'][id*="initiatives_form"]'
CANCEL = '[id*=\'"type":"cancel"\']'


def _editor(page: Page):
    return page.locator("#editor-popup")


def test_edit_route_in_the_url_opens_that_record(page: Page):
    """Arriving cold, not navigating once the app is already up."""
    page.goto("/#edit/initiatives/1")

    expect(_editor(page)).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Edit")
    expect(page.locator(NAME_INPUT)).to_have_value("Initiative 1")
    # The route survives the load: everything that can open the editor also
    # writes back to the modal, and one of those writes used to be read as the
    # editor closing, which cleared the hash before anything had routed on it.
    assert page.evaluate("location.hash") == "#edit/initiatives/1"
    # The record was named, so there is nothing for the "Add" dropdown to pick.
    expect(page.locator("#add-dropdown-container")).to_be_hidden()


def test_closing_the_editor_clears_the_edit_route(page: Page):
    page.goto("/#edit/initiatives/2")
    expect(_editor(page)).to_be_visible()

    page.locator(CANCEL).click()

    expect(_editor(page)).to_be_hidden()
    expect(page.locator("#form-heading")).to_have_count(0)
    assert page.evaluate("location.hash") == ""


def test_the_same_record_opens_twice_in_a_row(page: Page):
    """
    Closing clears the hash, so following the same link again is a real
    change to it — and has to reopen the editor rather than look like a repeat.
    """
    page.goto("/#edit/initiatives/3")
    expect(page.locator(NAME_INPUT)).to_have_value("Initiative 3")

    page.locator(CANCEL).click()
    expect(_editor(page)).to_be_hidden()

    page.evaluate("location.hash = '#edit/initiatives/3'")
    expect(_editor(page)).to_be_visible()
    expect(page.locator(NAME_INPUT)).to_have_value("Initiative 3")


def test_a_route_set_on_an_open_page_still_opens_the_editor(page: Page):
    page.goto("/")
    expect(page.locator("#dashboard-container")).to_be_visible()

    page.evaluate("location.hash = '#edit/initiatives/4'")

    expect(_editor(page)).to_be_visible()
    expect(page.locator(NAME_INPUT)).to_have_value("Initiative 4")


def test_a_route_stashed_before_login_is_restored_after_it(page: Page):
    """
    The fragment never reaches the server, so it cannot ride `next=` through
    the OAuth round trip. The login page stashes it; the app puts it back.
    This stands in for that trip, which needs Google to run for real.
    """
    page.goto("/")
    page.evaluate(
        "sessionStorage.setItem('pantograph-pending-hash', '#edit/initiatives/5')"
    )

    page.goto("/")

    expect(_editor(page)).to_be_visible()
    expect(page.locator(NAME_INPUT)).to_have_value("Initiative 5")
    # Spent, so a later visit is not hijacked by an old link.
    assert page.evaluate(
        "sessionStorage.getItem('pantograph-pending-hash')"
    ) is None


def test_a_junk_route_leaves_the_editor_shut(page: Page):
    page.goto("/#something-else")

    expect(page.locator("#dashboard-container")).to_be_visible()
    expect(_editor(page)).to_be_hidden()
