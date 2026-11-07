"""
The handoff bundle and the page that serves it.

Acceptance criteria in docs/agentic-ingest.md item C: a signed-in user gets a
bundle whose contract hash matches the running config, the snapshot contains no
superseded versions and no deleted links, and nothing restates the schema in
prose.
"""
import io
import json
import sqlite3
import zipfile
from datetime import datetime

import pytest
import yaml

from pantograph import contract, handoff, snapshot
from pantograph.db import get_current_records
from pantograph.settings import get_settings


@pytest.fixture
def client(dash_app):
    return dash_app.server.test_client()


@pytest.fixture
def versioned_activity():
    """
    An activity edited twice and a link since removed, which is the shape the
    snapshot has to read correctly. Cleaned up so the suite's counts are not
    left changed for other tests.
    """
    now = datetime.now().isoformat()
    conn = sqlite3.connect(get_settings().database_path)
    cur = conn.cursor()
    act_id = cur.execute("SELECT MAX(id) + 1 FROM activities").fetchone()[0]
    link_id = cur.execute(
        "SELECT MAX(id) + 1 FROM activity_initiative_links").fetchone()[0]
    for version, name in ((1, "First name"), (2, "Second name")):
        cur.execute(
            "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
            " VALUES (?, ?, ?, 'active', ?, 1)", (act_id, version, name, now))
    # A link added and then removed: removal is a new version with status
    # 'deleted', not a DELETE.
    for version, status in ((1, "active"), (2, "deleted")):
        cur.execute(
            "INSERT INTO activity_initiative_links"
            " (id, version, activity_id, initiative_id, status, timestamp, created_by)"
            " VALUES (?, ?, ?, 1, ?, ?, 1)", (link_id, version, act_id, status, now))
    conn.commit()
    yield act_id
    cur.execute("DELETE FROM activities WHERE id = ?", (act_id,))
    cur.execute("DELETE FROM activity_initiative_links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# The latest-version read the snapshot is built on
# --------------------------------------------------------------------------

def test_current_records_takes_the_highest_version_only(versioned_activity):
    rows = [r for r in get_current_records("activities")
            if r["id"] == versioned_activity]
    assert len(rows) == 1, "a record appeared once per version"
    assert rows[0]["name"] == "Second name"


def test_current_records_excludes_deleted(versioned_activity):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(get_settings().database_path)
    conn.execute(
        "INSERT INTO activities (id, version, name, status, timestamp, created_by)"
        " VALUES (?, 3, 'Gone', 'deleted', ?, 1)", (versioned_activity, now))
    conn.commit()
    conn.close()
    ids = {r["id"] for r in get_current_records("activities")}
    assert versioned_activity not in ids


# --------------------------------------------------------------------------
# The snapshot
# --------------------------------------------------------------------------

def test_snapshot_omits_email_elements(app_config):
    document = snapshot.build(app_config)
    assert document["omitted_elements"] == ["people.email"]
    assert document["records"]["people"], "no people to check"
    for person in document["records"]["people"]:
        assert "email" not in person
    # Stated, not merely absent: a producer must not read a withheld value as
    # an empty one it could helpfully fill in.
    assert "people.email" in document["omitted_elements"]


def test_snapshot_keeps_the_person_resolvable(app_config):
    """Minimisation has to stop short of making a person unidentifiable."""
    person = snapshot.build(app_config)["records"]["people"][0]
    assert "id" in person and "name" in person


def test_snapshot_drops_row_bookkeeping(app_config):
    initiative = snapshot.build(app_config)["records"]["initiatives"][0]
    assert "version" not in initiative
    assert "timestamp" not in initiative
    assert "rn" not in initiative


def test_snapshot_excludes_a_removed_link(versioned_activity, app_config):
    links = snapshot.build(app_config)["links"]["activity_initiative_links"]
    assert not [l for l in links if l["activity_id"] == versioned_activity], \
        "a link whose latest version is deleted was exported"


def test_snapshot_carries_links_as_pairs_not_as_records(app_config):
    document = snapshot.build(app_config)
    assert "activity_initiative_links" in document["links"]
    assert "activity_initiative_links" not in document["records"]
    pair = document["links"]["activity_initiative_links"][0]
    assert set(pair) == {"activity_id", "initiative_id"}
    assert all(isinstance(v, int) for v in pair.values())


def test_snapshot_round_trips_as_yaml(app_config):
    reloaded = yaml.safe_load(snapshot.dumps(app_config))
    assert reloaded["format"] == snapshot.SNAPSHOT_FORMAT
    assert reloaded["counts"]["initiatives"] == len(reloaded["records"]["initiatives"])


# --------------------------------------------------------------------------
# The bundle
# --------------------------------------------------------------------------

def test_bundle_holds_every_file_a_producer_needs(app_config):
    assert set(handoff.build(app_config)) == {
        "contract.json", "snapshot.yaml", "rejections.yaml", "instructions.md",
        "suggestions-format.md", "record-style-guide.md"}


def test_the_bundle_does_not_send_a_producer_to_a_url(app_config):
    """
    The format and the style guide travel inside the bundle. A link to the
    repository fails for a producer with no network access to it and is a 404
    for any path not yet on main; both happened.
    """
    files = handoff.build(app_config)
    assert "IDEMSInternational/collaboratorium" not in files["instructions.md"]
    assert "blob/main" not in files["instructions.md"]
    assert "suggestions-format.md" in files["instructions.md"]
    assert files["suggestions-format.md"].startswith("# `collaboratorium-suggestions/0.3`")


def test_the_instructions_say_where_to_look_for_work(app_config):
    text = handoff.build(app_config)["instructions.md"]
    for place in ("Forgejo", "Shared drive", "Publications", "Calendar"):
        assert place in text
    assert "A repository is an initiative" in text
    # Not every issue: only the overarching ones, with many beneath them.
    assert "never every issue" in text
    assert "Keep scan facts out" in text
    assert "Do not stop at the first source" in text


def test_producers_are_told_to_attach_evidence_to_an_activity(app_config):
    """
    Attachments are a field of an activity's description, and no producer was told
    so, so none ever proposed one.
    """
    bundle = handoff.build(app_config)
    assert "Attach the evidence" in bundle["instructions.md"]
    assert "{name, url}" in bundle["instructions.md"]
    assert "attachments:" in bundle["suggestions-format.md"]
    assert "added to" in bundle["suggestions-format.md"]


def test_producers_are_not_told_to_credit_people(app_config):
    """
    Telling producers to credit people by name, with the subject's own name as the
    example, ended most generated descriptions on "<subject> built it". That says
    nothing in the subject's own report. If crediting returns it should be asked
    for narrowly, and benchmarked first (see the prompt-lab repository).
    """
    bundle = handoff.build(app_config)
    for name in ("instructions.md", "record-style-guide.md"):
        assert "credit people" not in bundle[name].lower()
        assert "wrote most of the code" not in bundle[name]


def test_the_style_guide_defines_every_tag_category(app_config):
    guide = handoff.build(app_config)["record-style-guide.md"]
    for term in ("Deep Interoperability", "Local Capacity Building",
                 "IDEMS R&D", "Public Health"):
        assert term in guide


def test_bundle_parts_agree_on_the_config_hash(app_config):
    files = handoff.build(app_config)
    expected = contract.config_hash(app_config)
    assert json.loads(files["contract.json"])["config_hash"] == expected
    assert yaml.safe_load(files["snapshot.yaml"])["config_hash"] == expected
    assert yaml.safe_load(files["rejections.yaml"])["config_hash"] == expected
    assert expected.removeprefix("sha256:")[:12] in handoff.filename(app_config)


def test_instructions_name_what_the_format_refuses(app_config):
    instructions = handoff.build(app_config)["instructions.md"]
    assert "tag_groups" in instructions
    assert "people.email" in instructions
    # It points at the bundled spec rather than restating the schema (item C).
    assert "suggestions-format.md" in instructions


def test_instructions_state_the_record_counts(app_config):
    files = handoff.build(app_config)
    counts = yaml.safe_load(files["snapshot.yaml"])["counts"]
    assert f"| {counts['activities']} |" in files["instructions.md"]


def test_rejections_file_is_present_but_empty(app_config):
    """
    Staging does not exist yet (item E). The file ships anyway so a producer
    cannot tell "nothing rejected" from "no such file".
    """
    rejections = yaml.safe_load(handoff.build(app_config)["rejections.yaml"])
    assert rejections["rejected"] == []
    assert rejections["format"] == handoff.REJECTIONS_FORMAT


def test_zip_contains_the_same_files(app_config):
    archive = zipfile.ZipFile(io.BytesIO(handoff.zip_bytes(app_config)))
    assert set(archive.namelist()) == set(handoff.build(app_config))
    assert archive.testzip() is None


def test_zip_does_not_record_when_it_was_built(app_config):
    for info in zipfile.ZipFile(io.BytesIO(handoff.zip_bytes(app_config))).infolist():
        assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_bundle_text_is_utf8(app_config):
    """
    config.py carries the scar for this one: a file written in the platform's
    default encoding fails to load on another platform.
    """
    for name, text in handoff.build(app_config).items():
        text.encode("utf-8")


# --------------------------------------------------------------------------
# The route
# --------------------------------------------------------------------------

def test_page_renders_for_a_signed_in_user(client):
    response = client.get("/handoff")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Agent handoff" in body
    assert "collaboratorium-handoff-" in body


def test_page_says_the_bundle_leaves_and_cannot_be_withdrawn(client):
    """
    Decision in docs/agentic-ingest.md §2.4: the residual risk is stated on the
    page rather than designed away, so it is a test and not a nicety.
    """
    body = client.get("/handoff").get_data(as_text=True)
    assert "neither see it nor withdraw it" in body
    assert "Email addresses are left out" in body


def test_bundle_route_serves_a_zip(client, app_config):
    response = client.get("/handoff/bundle")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert handoff.filename(app_config) in response.headers["Content-Disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.data))
    assert "contract.json" in archive.namelist()


def test_bundle_route_matches_the_running_config(client, app_config):
    response = client.get("/handoff/bundle")
    archive = zipfile.ZipFile(io.BytesIO(response.data))
    served = json.loads(archive.read("contract.json"))
    assert served["config_hash"] == contract.config_hash(app_config)


@pytest.mark.parametrize("path", ["/handoff", "/handoff/bundle"])
def test_handoff_is_behind_login(client, monkeypatch, path):
    """
    Any signed-in user, but only a signed-in one — including the download,
    which is the route that actually hands over the data.

    The suite runs with auth.py's development auto-login, which is disabled by
    DEBUG being explicitly off rather than by patching the hook: the hook is
    already registered on the Flask server, so replacing the module attribute
    would change nothing.
    """
    monkeypatch.setenv("DEBUG", "0")
    with client.session_transaction() as flask_session:
        flask_session.clear()
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (301, 302)
    assert "/login" in response.headers["Location"]
