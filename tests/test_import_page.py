"""
The Import page: paste, check, stage, and open from the queue.

The suggestion logic is covered in test_import.py. What a browser adds is the
chain no unit test reaches — a nav button, a Dash callback writing to the shared
`url.hash`, and core's editor opening on a suggestion that was staged a moment
ago, which only works if the page also told the session which one it opened.
"""
import re

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


def _tag_vocabulary():
    """
    A `tag_groups` row to propose tags against, added once for the session and
    returned by id. Inserting it twice would give the form two groups to offer.
    """
    import json
    from pantograph.db import db_connect

    vocabulary = {"impact_area": {
        "type": "select_multiple", "label": "Impact Area",
        "list_name": "impact_area_list",
        "impact_area_list": {"education": "Education", "climate": "Climate"}},
        "idems_domain": {
        "type": "select_multiple", "label": "IDEMS Domain",
        "list_name": "idems_domain_list",
        "idems_domain_list": {"idems_rd": "IDEMS R&D"}}}
    conn = db_connect()
    try:
        row = conn.execute(
            "SELECT id FROM tag_groups WHERE name = 'Tags' ORDER BY id LIMIT 1").fetchone()
        if row:
            return row[0]
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM tag_groups").fetchone()[0]
        conn.execute(
            "INSERT INTO tag_groups (id, version, name, key_values, status, timestamp, created_by)"
            " VALUES (?, 1, 'Tags', ?, 'active', '2026-11-07T00:00:00', 1)",
            (next_id, json.dumps(vocabulary)))
        conn.commit()
        return next_id
    finally:
        conn.close()


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


def test_a_suggestion_carrying_tags_can_be_saved(page: Page):
    """
    Found on the live server: opening a staged suggestion that carries tags put
    the tags in the form as a mapping, and submitting handed that mapping to
    SQLite, which cannot bind one, so the save failed with a server error and
    nothing was recorded. Every earlier test saved a suggestion with no tags.
    """
    import json
    from pantograph.db import db_connect

    next_id = _tag_vocabulary()

    name = "Import Page Tagged Initiative"
    _open_import(page)
    page.locator("#import-textarea").fill(
        FILE.replace("Import Page Test Initiative", name)
            .replace("test:import-page", "test:import-page-tagged")
        + "    tags:\n      impact_area: [Education]\n")
    page.locator("#import-check").click()
    expect(page.locator("#import-report")).to_contain_text("1 ready")
    page.locator("#import-stage").click()

    row = page.locator("#import-queue tr", has_text=name)
    expect(row).to_have_count(1)
    row.get_by_role("button", name="Open").click()

    editor = page.locator("#editor-popup")
    expect(editor).to_contain_text("Suggested initiative")
    confirms = editor.get_by_role("button", name="Confirm", exact=True)
    for _ in range(12):
        if not confirms.count():
            break
        confirms.first.click()
        page.wait_for_timeout(300)
    editor.get_by_role("button", name="Submit").click()

    expect(page.locator("#import-queue tr", has_text=name)).to_have_count(0, timeout=10000)
    conn = db_connect()
    saved = conn.execute(
        "SELECT tag_groups FROM initiatives WHERE name = ?", (name,)).fetchone()
    conn.close()
    assert saved and json.loads(saved[0])[str(next_id)]["impact_area"] == ["education"]


def test_a_suggestion_opened_from_its_link_is_marked_answered_when_saved(page: Page):
    """
    The editor route `#suggest/<id>` is a link people paste and bookmark. It has
    to remember which suggestion it opened, or saving creates the record and
    leaves the suggestion pending, which in turn leaves anything waiting on it
    unable to link.
    """
    from pantograph import staging

    name = "Import Page Linked Initiative"
    _open_import(page)
    page.locator("#import-textarea").fill(
        FILE.replace("Import Page Test Initiative", name)
            .replace("test:import-page", "test:import-page-linked"))
    page.locator("#import-check").click()
    page.locator("#import-stage").click()
    expect(page.locator("#import-queue tr", has_text=name)).to_have_count(1)
    suggestion_id = next(i["id"] for i in staging.queue() if i["name"] == name)

    page.goto(f"/#suggest/{suggestion_id}")
    editor = page.locator("#editor-popup")
    expect(editor).to_contain_text("Suggested initiative")
    confirms = editor.get_by_role("button", name="Confirm", exact=True)
    for _ in range(12):
        if not confirms.count():
            break
        confirms.first.click()
        page.wait_for_timeout(300)
    editor.get_by_role("button", name="Submit").click()
    expect(editor).to_contain_text("Created initiatives record")

    assert staging.get(suggestion_id)["state"] == staging.ACCEPTED


def test_clearing_the_last_tag_keeps_the_block_so_another_can_be_chosen(page: Page):
    """
    Found on the live server: removing the only selected tag made the whole tags
    block vanish, because an all-empty group was dropped from the form's state
    and a dynamic subform draws the groups its state holds. Swapping one tag for
    another therefore lost the block between the two clicks. The empty group now
    stays on the page and is dropped only when the record is saved.
    """
    import json
    from pantograph.db import db_connect

    group_id = _tag_vocabulary()
    name = "Import Page Cleared Tags Initiative"
    _open_import(page)
    page.locator("#import-textarea").fill(
        FILE.replace("Import Page Test Initiative", name)
            .replace("test:import-page", "test:import-page-cleared")
        + "    tags:\n      impact_area: [Education]\n")
    page.locator("#import-check").click()
    page.locator("#import-stage").click()
    page.locator("#import-queue tr", has_text=name).get_by_role("button", name="Open").click()

    editor = page.locator("#editor-popup")
    expect(editor).to_contain_text(re.compile("impact area", re.I))

    # Remove the only tag.
    editor.locator("[id*='tag_groups'] button[aria-label*='lear'], [id*='tag_groups'] [class*='clear']").first.click()
    page.wait_for_timeout(1500)
    expect(editor).to_contain_text(re.compile("impact area", re.I))
    expect(editor).to_contain_text(re.compile("idems domain", re.I))

    # Then pick another, which is what the reviewer came to do.
    # The dropdown sits just under its label, and is not itself labelled.
    box = editor.get_by_text("Impact Area", exact=True).first.bounding_box()
    page.mouse.click(box["x"] + 180, box["y"] + 32)
    page.locator(".dash-options-list-option:visible", has_text="Climate").first.click()
    page.wait_for_timeout(1500)

    confirms = editor.get_by_role("button", name="Confirm", exact=True)
    for _ in range(12):
        if not confirms.count():
            break
        confirms.first.click()
        page.wait_for_timeout(300)
    editor.get_by_role("button", name="Submit").click()
    expect(editor).to_contain_text("Created initiatives record")

    conn = db_connect()
    saved = conn.execute("SELECT tag_groups FROM initiatives WHERE name = ?", (name,)).fetchone()
    conn.close()
    assert json.loads(saved[0])[str(group_id)]["impact_area"] == ["climate"]
