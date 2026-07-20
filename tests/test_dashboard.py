"""
Dashboard page tests.

The session fixture seeds person 1 (Automated Tester) as responsible for
Initiative 1 and linked to Activities 1-3, which covers the feed. The extra
rows seeded here cover the gap-spotting sections, which are the point of the
page: an initiative with nothing linked, an old one, and a loose activity.
"""
import datetime
import re
import sqlite3

import pytest
from playwright.sync_api import Page, expect

TEST_DB = "test_database.db"

NEW_EMPTY = "Seeded New Empty Initiative"
OLD_EMPTY = "Seeded Quiet Initiative"
ORPHAN_INITIATIVE = "Seeded Ownerless Initiative"
LOOSE_ACTIVITY = "Seeded Unlinked Activity"
OTHERS_ACTIVITY = "Seeded Activity By Someone Else"
INVOLVED_NOT_OWNED = "Seeded Involved But Not Responsible"
NEAR_VIA_INVOLVEMENT = "Seeded Near Via Involvement"


@pytest.fixture(scope="module", autouse=True)
def dashboard_rows(live_server):
    """
    Seed the cases the base fixture has no examples of, then remove them again.

    The session database is shared, and other suites assert on exact row counts,
    so anything added here has to be taken back out.
    """
    now = datetime.datetime.now()
    recent = (now - datetime.timedelta(days=5)).isoformat()
    old = (now - datetime.timedelta(days=200)).isoformat()

    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()

    # Created inside the window, nothing linked -> "New — no activity yet"
    cur.execute(
        "INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person)"
        " VALUES (901, 1, ?, 'active', ?, 1, 1)",
        (NEW_EMPTY, recent),
    )
    # Created before the window, nothing linked -> "Nothing recorded in a while"
    cur.execute(
        "INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person)"
        " VALUES (902, 1, ?, 'active', ?, 1, 1)",
        (OLD_EMPTY, old),
    )
    # Created by me, nobody responsible -> Mine via the orphan fallback
    cur.execute(
        "INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person)"
        " VALUES (903, 1, ?, 'active', ?, 1, NULL)",
        (ORPHAN_INITIATIVE, recent),
    )
    # An activity I'm on that hangs off no initiative
    cur.execute(
        "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
        " VALUES (901, 1, ?, 'active', ?, 1)",
        (LOOSE_ACTIVITY, recent),
    )
    cur.execute(
        "INSERT INTO activity_people_links (id, version, activity_id, person_id, status, timestamp, created_by)"
        " VALUES (901, 1, 901, 1, 'active', ?, 1)",
        (recent,),
    )
    # Someone else recorded this against Initiative 1, which I'm responsible for,
    # and I am not linked to it -> "Touching your work"
    cur.execute(
        "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
        " VALUES (902, 1, ?, 'active', ?, 2)",
        (OTHERS_ACTIVITY, recent),
    )
    cur.execute(
        "INSERT INTO activity_initiative_links (id, version, activity_id, initiative_id, status, timestamp, created_by)"
        " VALUES (902, 1, 902, 1, 'active', ?, 2)",
        (recent,),
    )
    # An initiative someone else is responsible for, that is Mine only because I'm
    # on one of its activities. Must NOT claim "You're responsible".
    cur.execute(
        "INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person)"
        " VALUES (904, 1, ?, 'active', ?, 2, 2)",
        (INVOLVED_NOT_OWNED, recent),
    )
    cur.execute(
        "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
        " VALUES (903, 1, 'Activity I helped with', 'active', ?, 1)",
        (recent,),
    )
    cur.execute(
        "INSERT INTO activity_people_links (id, version, activity_id, person_id, status, timestamp, created_by)"
        " VALUES (903, 1, 903, 1, 'active', ?, 1)",
        (recent,),
    )
    cur.execute(
        "INSERT INTO activity_initiative_links (id, version, activity_id, initiative_id, status, timestamp, created_by)"
        " VALUES (903, 1, 903, 904, 'active', ?, 1)",
        (recent,),
    )
    # Someone else's activity on that same involved-in-but-not-owned initiative,
    # which I'm not on -> must surface in "Near Your Work" under the broadened
    # rule (it would not under the old responsible-for-only rule).
    cur.execute(
        "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
        " VALUES (905, 1, ?, 'active', ?, 2)",
        (NEAR_VIA_INVOLVEMENT, recent),
    )
    cur.execute(
        "INSERT INTO activity_initiative_links (id, version, activity_id, initiative_id, status, timestamp, created_by)"
        " VALUES (905, 1, 905, 904, 'active', ?, 2)",
        (recent,),
    )
    conn.commit()
    conn.close()

    yield

    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM initiatives WHERE id IN (901, 902, 903, 904)")
    cur.execute("DELETE FROM activities WHERE id IN (901, 902, 903, 905)")
    cur.execute("DELETE FROM activity_people_links WHERE id IN (901, 903)")
    cur.execute("DELETE FROM activity_initiative_links WHERE id IN (902, 903, 905)")
    conn.commit()
    conn.close()


def _dashboard(page: Page):
    page.goto("http://localhost:8055")
    expect(page.locator("#dashboard-page")).to_be_visible()
    # The body arrives by callback; without waiting for it a click can land
    # before Dash has attached its handlers.
    expect(page.locator("#dashboard-body .dash-panel").first).to_be_visible()
    return page


def _open_card(page: Page, name: str):
    """
    Click an entity link in the dashboard body.

    Scoped to the anchor and to #dashboard-body on purpose: the hidden Explore
    spreadsheet also holds cells with these names, so a bare get_by_text is
    ambiguous.
    """
    page.locator("#dashboard-body a.dash-entity-link").filter(
        has_text=re.compile(rf"^{re.escape(name)}$")
    ).first.click()
    card = page.locator("#dashboard-detail-modal")
    expect(card).to_be_visible()
    return card


def test_dashboard_is_the_landing_page(page: Page):
    _dashboard(page)
    expect(page.locator("#explore-container")).to_be_hidden()
    expect(page.locator("#nav-dashboard")).to_have_class(re.compile(r"\bactive\b"))


def test_mine_shows_my_feed_and_gaps(page: Page):
    _dashboard(page)
    body = page.locator("#dashboard-body")

    # Feed: the initiative I'm responsible for, with its activities beneath it
    expect(body).to_contain_text("Initiative 1")
    expect(body).to_contain_text("You're responsible")

    # Gap-spotting sections
    expect(body).to_contain_text("New — no activity yet")
    expect(body).to_contain_text(NEW_EMPTY)
    expect(body).to_contain_text("Nothing recorded in a while")
    expect(body).to_contain_text(OLD_EMPTY)
    expect(body).to_contain_text("Not linked to an initiative")
    expect(body).to_contain_text(LOOSE_ACTIVITY)


def test_involvement_is_not_labelled_as_responsibility(page: Page):
    """An initiative that's Mine via an activity link isn't claimed as yours to own."""
    _dashboard(page)
    item = page.locator(".dash-repo", has_text=INVOLVED_NOT_OWNED)
    expect(item).to_be_visible()
    expect(item).not_to_contain_text("You're responsible")
    expect(item).to_contain_text("Person 2 responsible")


def test_orphan_initiative_counts_as_mine(page: Page):
    """created_by only qualifies where nobody is responsible."""
    _dashboard(page)
    expect(page.locator("#dashboard-body")).to_contain_text(ORPHAN_INITIATIVE)


def test_near_your_work_shows_owned_by_default_hides_involved(page: Page):
    _dashboard(page)
    body = page.locator("#dashboard-body")
    expect(body).to_contain_text("Near Your Work")
    # On an initiative I own, shown by default...
    expect(body).to_contain_text(OTHERS_ACTIVITY)
    # ...but activity on one I'm only involved in stays behind the toggle, so one
    # incidental link can't flood the section.
    expect(body).not_to_contain_text(NEAR_VIA_INVOLVEMENT)


def test_near_your_work_toggle_reveals_involved(page: Page):
    _dashboard(page)
    body = page.locator("#dashboard-body")
    expect(body).not_to_contain_text(NEAR_VIA_INVOLVEMENT)

    body.get_by_text("from initiatives you've contributed to").click()
    expect(body).to_contain_text(NEAR_VIA_INVOLVEMENT)

    # Collapsing hides it again (the preference is remembered per-person).
    body.get_by_text("Show less", exact=True).click()
    expect(body).not_to_contain_text(NEAR_VIA_INVOLVEMENT)


def test_quiet_box_is_mine_only(page: Page):
    """Everyone must never become a report on other people's quiet projects."""
    _dashboard(page)
    expect(page.locator("#dashboard-body")).to_contain_text("Nothing recorded in a while")

    page.locator("#dash-scope-everyone").click()
    body = page.locator("#dashboard-body")
    expect(body).not_to_contain_text("Nothing recorded in a while")
    expect(body).not_to_contain_text("Near Your Work")
    # The same feed is still there, just unfiltered
    expect(body).to_contain_text("Recently updated")


def test_quiet_box_hides_and_comes_back(page: Page):
    _dashboard(page)
    body = page.locator("#dashboard-body")
    expect(body).to_contain_text(OLD_EMPTY)

    page.locator('[id*="dash-quiet-toggle"]').first.click()
    expect(body).to_contain_text("hidden")
    expect(body).not_to_contain_text(OLD_EMPTY)

    page.get_by_text("Show", exact=True).click()
    expect(body).to_contain_text(OLD_EMPTY)


def test_clicking_an_initiative_opens_its_detail_card(page: Page):
    _dashboard(page)
    card = _open_card(page, "Initiative 1")

    expect(card).to_contain_text("Initiative 1")
    expect(card).to_contain_text("Responsible")
    # Its activities are listed, and are themselves inspectable
    expect(card).to_contain_text("Activity 1")
    # We stay on the dashboard: the card replaced the jump to the graph
    expect(page.locator("#explore-container")).to_be_hidden()


def test_activities_are_inspectable(page: Page):
    _dashboard(page)
    card = _open_card(page, "Activity 1")

    expect(card).to_contain_text("Activity 1")
    expect(card).to_contain_text("Part of")
    expect(card).to_contain_text("Initiative 1")


def test_card_navigates_between_linked_records(page: Page):
    """An initiative card lists its activities; clicking one swaps the card."""
    _dashboard(page)
    card = _open_card(page, "Initiative 1")

    card.locator("a.dash-entity-link").filter(
        has_text=re.compile(r"^Activity 2$")
    ).first.click()
    expect(page.locator("#dash-card-header")).to_contain_text("Activity 2")
    expect(card).to_contain_text("Part of")


def test_card_hands_off_to_explore(page: Page):
    _dashboard(page)
    _open_card(page, "Initiative 1")

    page.locator('[id*="dash-card-explore"]').click()

    expect(page.locator("#explore-container")).to_be_visible()
    expect(page.locator("#dashboard-page")).to_be_hidden()
    expect(page.locator("#filter-target-entity")).to_contain_text("Initiative 1")


def test_header_quick_add_buttons_skip_the_table_dropdown(page: Page):
    _dashboard(page)

    page.locator("#btn-add-activity").click()
    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Add activity")
    # The table has already been chosen, so its dropdown is out of the way
    expect(page.locator("#add-dropdown-container")).to_be_hidden()

    page.reload()
    expect(page.locator("#dashboard-page")).to_be_visible()
    page.locator("#btn-add-initiative").click()
    expect(page.locator("#form-heading")).to_contain_text("Add initiative")


def test_add_activity_arrives_linked_to_its_initiative(page: Page):
    """The prefill is the point: the new activity is already linked."""
    _dashboard(page)

    page.locator('[id*="dash-add-activity"]').first.click()
    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(page.locator("#form-heading")).to_contain_text("Add activity")
    # Linked Initiatives comes pre-filled with the initiative we started from
    linked = editor.locator('[id*="initiatives_links"]').first
    expect(linked).to_contain_text(NEW_EMPTY)
    # ...and Linked People comes pre-filled with me, so recording my own work
    # doesn't cost a search for my own name.
    people = editor.locator('[id*="people_links"]').first
    expect(people).to_contain_text("Automated Tester")


def test_add_activity_editor_names_the_initiative(page: Page):
    """The header says what's being added and into what, not a bare 'Editor'."""
    _dashboard(page)

    # Target NEW_EMPTY's own rail card so the title is unambiguous.
    card = page.locator(".dash-item", has_text=NEW_EMPTY)
    card.locator('[id*="dash-add-activity"]').click()
    expect(page.locator("#editor-popup")).to_be_visible()
    # The heading lives in the form DOM (set when the form renders), so it's
    # deterministic rather than a racy separate callback.
    expect(page.locator("#form-heading")).to_contain_text(f"Add activity to {NEW_EMPTY}")


def test_header_add_activity_prefills_me_without_an_initiative(page: Page):
    _dashboard(page)

    page.locator("#btn-add-activity").click()
    editor = page.locator("#editor-popup")
    expect(editor).to_be_visible()
    expect(editor.locator('[id*="people_links"]').first).to_contain_text("Automated Tester")
    # No initiative context here, so the heading is the generic add label.
    expect(page.locator("#form-heading")).to_contain_text("Add activity")


def test_prefill_does_not_leak_into_a_later_add(page: Page):
    """A prefill request lasts only as long as the editor it opened."""
    _dashboard(page)

    page.locator('[id*="dash-add-activity"]').first.click()
    editor = page.locator("#editor-popup")
    expect(editor.locator('[id*="initiatives_links"]').first).to_contain_text(NEW_EMPTY)

    page.keyboard.press("Escape")
    expect(editor).to_be_hidden()

    page.locator("#btn-add-activity").click()
    expect(editor).to_be_visible()
    expect(editor.locator('[id*="initiatives_links"]').first).not_to_contain_text(NEW_EMPTY)


def test_card_edit_opens_the_generic_editor(page: Page):
    _dashboard(page)
    _open_card(page, "Initiative 1")

    page.locator('[id*="dash-card-edit"]').click()

    expect(page.locator("#editor-popup")).to_be_visible()
    expect(page.locator("#dashboard-detail-modal")).to_be_hidden()


def test_view_as_control_is_hidden_for_non_admins(page: Page):
    _dashboard(page)
    expect(page.locator("#view-as-container")).to_be_hidden()


def test_admin_can_view_another_users_dashboard_read_only(page: Page, monkeypatch):
    """Admin 'view as' shows that person's dashboard with write affordances gone."""
    import admin_routes

    # The live server runs in this same process, so patching the module global
    # makes the dev user (Automated Tester) an admin for this test.
    monkeypatch.setattr(admin_routes, "ADMIN_EMAILS", ["testrunner@idems.international"])

    _dashboard(page)
    expect(page.locator("#view-as-container")).to_be_visible()

    # Pick Person 2 (base fixture: responsible for Initiative 2).
    page.locator("#view-as-pick").click()
    page.keyboard.type("Person 2", delay=50)
    page.keyboard.press("Enter")

    banner = page.locator(".dash-viewas-banner")
    expect(banner).to_contain_text("Viewing as Person 2")
    expect(banner).to_contain_text("read-only")

    body = page.locator("#dashboard-body")
    expect(body).to_contain_text("Initiative 2")

    # Write affordances are gone while impersonating.
    expect(page.locator("#btn-add-activity")).to_be_hidden()
    expect(page.locator("#btn-add-initiative")).to_be_hidden()
    _open_card(page, "Initiative 2")
    expect(page.locator("#dashboard-detail-modal")).to_contain_text("Open in Explore")
    expect(page.locator('[id*="dash-card-edit"]')).to_have_count(0)
