"""
One realistic file that uses every feature a producer can use, put through every
place a staged suggestion is shown.

Why this exists: a queue that rendered nothing on the live server (an activity's
summary is a nested mapping and two queue renderers sliced it as text) got
through a green suite, because every queue test used a record with no summary.
The shapes that differ between "a test fixture" and "what a producer really
sends" are exactly the ones nobody thinks to write a test for. So this file
sends the awkward shape once, and then looks at every surface that reads it.

When a new element type or a new way of proposing something is added, add it to
`FULL_FILE_BODY` here, and every surface below checks it for free.
"""
import datetime
import json
import os
import tempfile

import pytest
import yaml

from pantograph import contract, settings, staging, suggestions
from pantograph.db import db_connect, init_db
from pantograph.form_gen import generate_form_layout

VOCABULARY = {
    "impact_area": {
        "type": "select_multiple", "label": "Impact Area",
        "list_name": "impact_area_list",
        "impact_area_list": {"education": "Education", "climate": "Climate"}},
    "idems_domain": {
        "type": "select_multiple", "label": "IDEMS Domain",
        "list_name": "idems_domain_list",
        "idems_domain_list": {"idems_rd": "IDEMS R&D"}},
}

# Every way of saying something that a producer has been told it may use:
# a summary and attachments on an activity, a bare `description:` string, tags,
# links by name, a stated guess (`inferred:`, including one about attachments),
# an update to a record that exists, and a long unbroken URL.
FULL_FILE_BODY = """
initiatives:
  - name: Smoke Initiative
    description: A plain string description on an initiative.
    status: active
    responsible_person: Gabe Bolton
    tags:
      impact_area: [Education, Climate]
      idems_domain: [IDEMS R&D]
    source_ref: "smoke:initiative"
  - target: {id: 1, expect: R-Instat}
    description: An updated description for a record that already exists.
    source_ref: "smoke:update"
activities:
  - name: Smoke Activity With Summary
    summary: Released v0.23.0 with offline sync, and a long https://example.org/a/very/long/url/that/does/not/break/anywhere/at/all
    attachments:
      - {name: Release notes, url: "https://example.org/releases/v0.23.0"}
      - {name: Pull request, url: "https://example.org/pull/12"}
    initiatives: [R-Instat, ePICSA]
    people: [Gabe Bolton, Michele Zamparo]
    start_date: 2024-02-14
    tags:
      impact_area: [Education]
    inferred:
      summary: worked out from the release notes
      attachments: repo name matches the project, not confirmed
    source_ref: "smoke:activity-summary"
  - name: Smoke Activity With Bare Description
    description: A bare description string on an activity.
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "smoke:activity-bare"
  - name: Smoke Activity With Nothing Else
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "smoke:activity-minimal"
"""


@pytest.fixture
def staged(app_config):
    """A fresh database with the full file already staged, as the live one is."""
    directory = tempfile.mkdtemp(prefix="smoke-tests-")
    previous = settings.get_settings()
    settings.configure(database_path=os.path.join(directory, "t.db"),
                       analytics_path=os.path.join(directory, "a.db"))
    init_db(app_config)

    now = datetime.datetime.now().isoformat()
    conn = db_connect()
    cur = conn.cursor()
    for pid, name in ((1, "Gabe Bolton"), (2, "Michele Zamparo")):
        cur.execute("INSERT INTO people (id,version,name,status,timestamp,created_by)"
                    " VALUES (?,1,?,'active',?,1)", (pid, name, now))
    for iid, name in ((1, "R-Instat"), (2, "ePICSA")):
        cur.execute("INSERT INTO initiatives"
                    " (id,version,name,status,timestamp,created_by,responsible_person)"
                    " VALUES (?,1,?,'active',?,1,1)", (iid, name, now))
    cur.execute("INSERT INTO tag_groups (id, version, name, key_values, status,"
                " timestamp, created_by) VALUES (1, 1, 'Tags', ?, 'active', ?, 1)",
                (json.dumps(VOCABULARY), now))
    conn.commit()
    conn.close()

    text = yaml.safe_dump({
        "format": suggestions.FORMAT, "contract": contract.config_hash(app_config),
        "producer": {"name": "smoke", "run_id": "smoke-run"},
        "subject": "Gabe Bolton"}, sort_keys=False) + FULL_FILE_BODY
    proposal = suggestions.check(
        text, contract.build(app_config), staging.current_names(app_config),
        staging.pending_rows(), vocabulary=staging.tag_vocabulary(app_config))
    assert not proposal.errors, [f.message for f in proposal.errors]
    report = staging.stage(proposal, 1)
    assert len(report["staged"]) == 5, \
        [(r.name, [f.message for f in r.findings]) for r in proposal.records]

    yield app_config
    settings.configure(database_path=previous.database_path,
                       analytics_path=previous.analytics_path)


def _text_of(component):
    """
    Every string a Dash tree would show: its children, and the `value` of a field
    (a textarea's content and a table's rows are props, not children).
    """
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return " ".join(_text_of(c) for c in component)
    if isinstance(component, dict):
        return " ".join(_text_of(v) for v in component.values())
    parts = []
    for prop in ("children", "value", "data"):
        inner = getattr(component, prop, None)
        if inner is not None:
            parts.append(_text_of(inner))
    return " ".join(parts)


def test_the_whole_file_staged_and_every_record_is_queued(staged):
    names = {item["name"] for item in staging.queue()}
    assert names >= {"Smoke Initiative", "Smoke Activity With Summary",
                     "Smoke Activity With Bare Description",
                     "Smoke Activity With Nothing Else"}


def test_the_flask_queue_page_renders_every_staged_record(staged, dash_app):
    client = dash_app.server.test_client()
    page = client.get("/import/queue")
    assert page.status_code == 200
    for item in staging.queue():
        assert item["name"].encode() in page.data


def test_the_import_pages_queue_renders_every_staged_record(staged):
    """The Dash page builds its own rows; a callback error there is silent."""
    from pantograph_import import page

    text = _text_of(page._queue("import"))
    for item in staging.queue():
        assert item["name"] in text, f"{item['name']} missing from the queue"


def test_every_staged_record_opens_in_the_ordinary_form(staged):
    forms = staged["forms"]
    for item in staging.queue():
        values, provenances = staging.form_inputs(item)
        form_name = staged["default_forms"][item["table"]]
        layout = generate_form_layout(
            form_name, forms_config=forms,
            object_id=item["target_id"] if item["action"] == "update" else None,
            initial_values=values, provenances=provenances)
        assert _text_of(layout), f"{item['name']} opened as an empty form"


def test_the_summary_and_its_attachments_reach_the_form(staged):
    item = next(i for i in staging.queue()
                if i["name"] == "Smoke Activity With Summary")
    values, provenances = staging.form_inputs(item)
    form_name = staged["default_forms"]["activities"]
    text = _text_of(generate_form_layout(
        form_name, forms_config=staged["forms"], object_id=None,
        initial_values=values, provenances=provenances))
    assert "Released v0.23.0" in text
    assert "Release notes" in text and "Pull request" in text
    # The guess about the attachments is shown to the reviewer.
    assert "attachments: repo name matches the project" in text
