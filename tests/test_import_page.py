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


def test_a_saved_suggestion_leaves_the_queue_without_a_reload(page: Page):
    """
    Accepting a suggestion is a save in the ordinary editor. The queue behind it
    has to notice, or the reviewer closes the editor onto a list that still
    offers what they have just done.
    """
    _open_import(page)
    name = "Import Page Saved Initiative"
    page.locator("#import-textarea").fill(
        FILE.replace("Import Page Test Initiative", name)
            .replace("test:import-page", "test:import-page-saved"))
    page.locator("#import-check").click()
    page.locator("#import-stage").click()

    row = page.locator("#import-queue tr", has_text=name)
    expect(row).to_have_count(1)
    row.get_by_role("button", name="Open").click()

    editor = page.locator("#editor-popup")
    expect(editor).to_contain_text("Suggested initiative")
    # Every Confirm on the form, so the required answers are stood behind.
    # A confirmed field drops its button, so take the first one each time.
    confirms = editor.get_by_role("button", name="Confirm", exact=True)
    for _ in range(12):
        if not confirms.count():
            break
        confirms.first.click()
        page.wait_for_timeout(300)
    editor.get_by_role("button", name="Submit").click()

    expect(page.locator("#import-queue tr", has_text=name)).to_have_count(0, timeout=10000)
