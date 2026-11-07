"""
The Import page: paste, check, stage, and open from the queue.

The suggestion logic is covered in test_import.py. What a browser adds is the
chain no unit test reaches — a nav button, a Dash callback writing to the shared
`url.hash`, and core's editor opening on a suggestion that was staged a moment
ago, which only works if the page also told the session which one it opened.
"""
from playwright.sync_api import Page, expect

FILE = """\
format: collaboratorium-suggestions/0.3
producer: {name: test, run_id: import-page-run}
subject: Automated Tester
initiatives:
  - name: Import Page Test Initiative
    description: Written by a browser test to see a suggestion through the queue.
    status: active
    responsible_person: Automated Tester
    source_ref: "test:import-page"
"""


def _open_import(page: Page):
    page.goto("/")
    page.locator("#nav-import").click()
    expect(page.get_by_role("heading", name="Import suggestions")).to_be_visible()


def test_the_page_has_a_nav_button(page: Page):
    page.goto("/")
    expect(page.locator("#nav-import")).to_have_text("Import")


def test_a_file_is_checked_before_it_is_staged(page: Page):
    _open_import(page)
    page.locator("#import-textarea").fill(FILE)
    page.locator("#import-check").click()

    expect(page.locator("#import-report")).to_contain_text("1 ready")
    expect(page.locator("#import-report")).to_contain_text("Import Page Test Initiative")
    # Checking staged nothing.
    expect(page.locator("#import-queue")).not_to_contain_text("Import Page Test Initiative")


def test_staged_work_is_queued_and_opens_in_the_editor(page: Page):
    _open_import(page)
    page.locator("#import-textarea").fill(FILE)
    page.locator("#import-check").click()
    expect(page.locator("#import-stage")).to_be_visible()
    page.locator("#import-stage").click()

    expect(page.locator("#import-report")).to_contain_text("staged")
    queue = page.locator("#import-queue")
    expect(queue).to_contain_text("Import Page Test Initiative")

    queue.get_by_role("button", name="Open").first.click()
    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(editor).to_contain_text("Suggested initiative")
