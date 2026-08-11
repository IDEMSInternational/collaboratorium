"""
Reading across a link, against a real database.

The rest of the cross-link tests hand `evaluate` a resolver over rows written in
the test, which is the right way to test the language. This file tests the one
thing that cannot mock: that the resolver relevance builds by default reaches
the database, reads the row a link points at, and gives the same answers about
versions and deletion that the rest of the app gives.

It also covers the path nobody calls explicitly — `form_gen` submits by calling
`irrelevant_elements(form_config, data)` with no resolver, so if the default did
not work the server-side recomputation would silently clear the wrong answers.
"""
import datetime

import pytest

from pantograph.db import db_connect
from pantograph.relevance import irrelevant_elements, link_resolver
from pantograph.requirements import outstanding

# A person is linked, and a question is asked only of people with an email on
# file — the shape of the ROPA case, over the tables the test database has.
FORM = {
    "label": "Contact",
    "default_table": "initiatives",
    "elements": {
        "responsible_person": {
            "type": "select_one", "label": "Responsible Person",
            "parameters": {"source_table": "people",
                           "value_column": "id", "label_column": "name"},
        },
        "how_contacted": {
            "type": "string", "label": "How They Were Contacted",
            "relevant": "${responsible_person.email} != ''",
            "required": "${responsible_person.email} != ''",
        },
    },
    "meta": {"id": {}, "status": {}},
}

TESTER_EMAIL = "testrunner@idems.international"


@pytest.fixture
def person_with_no_email():
    """A person whose latest version has no email, and who is then deleted."""
    now = datetime.datetime.now().isoformat()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO people (id, version, name, email, status, timestamp, created_by)"
                " VALUES (901, 1, 'Nameless', 'first@test.com', 'active', ?, 1)", (now,))
    cur.execute("INSERT INTO people (id, version, name, email, status, timestamp, created_by)"
                " VALUES (901, 2, 'Nameless', NULL, 'active', ?, 1)", (now,))
    conn.commit()
    conn.close()
    yield 901
    conn = db_connect()
    conn.execute("DELETE FROM people WHERE id = 901")
    conn.commit()
    conn.close()


def _resolve(link_value, column="email"):
    return link_resolver(FORM)("responsible_person", column, link_value)


def test_the_default_resolver_reads_the_linked_row_from_the_database():
    assert _resolve(1) == TESTER_EMAIL


def test_an_id_that_came_back_from_the_browser_as_a_string_still_matches():
    """
    A dropdown hands back whatever its option value was, and that can survive a
    round trip through the browser as a string. Nothing here coerces it: an id
    column has INTEGER affinity, so SQLite compares '1' to 1 as numbers. Pinned
    by a test because the day that stops being true, every cross-link condition
    on an edited form quietly reads as unanswered.
    """
    assert _resolve("1") == TESTER_EMAIL


def test_an_unset_or_unknown_link_resolves_to_nothing():
    assert _resolve(None) is None
    assert _resolve("") is None
    assert _resolve(99999) is None


def test_the_latest_version_of_the_linked_row_wins(person_with_no_email):
    """Version 2 cleared the email; a condition must not read version 1's."""
    assert _resolve(person_with_no_email) is None
    assert _resolve(person_with_no_email, "name") == "Nameless"


def test_a_deleted_linked_row_reads_as_unanswered(person_with_no_email):
    now = datetime.datetime.now().isoformat()
    conn = db_connect()
    conn.execute("INSERT INTO people (id, version, name, email, status, timestamp, created_by)"
                 " VALUES (901, 3, 'Nameless', 'back@test.com', 'deleted', ?, 1)", (now,))
    conn.commit()
    conn.close()
    assert _resolve(person_with_no_email) is None


def test_one_query_serves_every_column_read_of_one_row(monkeypatch):
    """A form with six conditions over one linked row is one fetch, not six."""
    import pantograph.db

    calls = []
    real = pantograph.db.get_latest_record

    def counted(table, object_id=None):
        calls.append((table, object_id))
        return real(table, object_id)

    monkeypatch.setattr(pantograph.db, "get_latest_record", counted)
    resolve = link_resolver(FORM)
    assert resolve("responsible_person", "email", 1) == TESTER_EMAIL
    assert resolve("responsible_person", "name", 1) == "Automated Tester"
    assert len(calls) == 1


# --------------------------------------------------------------------------
# The paths that pass no resolver of their own
# --------------------------------------------------------------------------

def test_the_submit_path_follows_the_link_without_being_asked_to():
    """
    `form_gen` calls this with the answers and nothing else. If the link were
    not followed here, an answer the linked row justifies would be cleared to
    NULL on save.
    """
    answers = {"responsible_person": 1, "how_contacted": "by email"}
    assert irrelevant_elements(FORM, answers) == set()
    assert irrelevant_elements(FORM, {"how_contacted": "by email"}) == {"how_contacted"}


class _RecordingApp:
    """Enough of a Dash app to capture the callback bodies that get registered."""

    def __init__(self):
        self.callbacks = []

    def callback(self, *args, **kwargs):
        def register(func):
            self.callbacks.append(func)
            return func
        return register


def test_the_registered_toggle_callback_follows_the_link():
    """
    The callback body builds its own resolver from the form it was registered
    for. Nothing else exercises that line, and without it every cross-link
    condition would render as false on screen while submitting correctly.
    """
    from pantograph.relevance import HIDDEN, VISIBLE, register_relevance_callbacks

    app = _RecordingApp()
    register_relevance_callbacks(app, {"contact_form": FORM})
    toggle, = app.callbacks
    assert toggle(1) == [VISIBLE]
    assert toggle(99999) == [HIDDEN]


def test_the_submit_check_demands_what_the_linked_row_justifies():
    assert outstanding(FORM, {"responsible_person": 1}) == ["how_contacted"]
    assert outstanding(FORM, {"responsible_person": 1, "how_contacted": "x"}) == []
    assert outstanding(FORM, {}) == []
