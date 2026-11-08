"""
Checking, staging and reviewing an uploaded suggestions file.

Each test builds its own database rather than using the session one, because
staging is stateful and idempotency is precisely what is under test: a suite
that shared rows between these would pass for the wrong reasons.
"""
import datetime
import json
import os
import sqlite3
import tempfile

import pytest
import yaml

from pantograph import contract, settings, staging, suggestions
from pantograph.config import load_config
from pantograph.db import db_connect, init_db


@pytest.fixture
def deployment(app_config, monkeypatch):
    """A fresh database with a handful of records, and settings pointed at it."""
    directory = tempfile.mkdtemp(prefix="import-tests-")
    previous = settings.get_settings()
    settings.configure(database_path=os.path.join(directory, "t.db"),
                       analytics_path=os.path.join(directory, "a.db"))
    init_db(app_config)

    now = datetime.datetime.now().isoformat()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("INSERT INTO people (id,version,name,status,timestamp,created_by)"
                " VALUES (1,1,'Gabe Bolton','active',?,1)", (now,))
    cur.execute("INSERT INTO people (id,version,name,status,timestamp,created_by)"
                " VALUES (2,1,'Michele Zamparo','active',?,1)", (now,))
    cur.execute("INSERT INTO initiatives"
                " (id,version,name,status,timestamp,created_by,responsible_person)"
                " VALUES (1,1,'R-Instat','active',?,1,1)", (now,))
    cur.execute("INSERT INTO initiatives"
                " (id,version,name,status,timestamp,created_by,responsible_person)"
                " VALUES (2,1,'ePICSA','active',?,1,1)", (now,))
    conn.commit()
    conn.close()

    yield app_config
    settings.configure(database_path=previous.database_path,
                       analytics_path=previous.analytics_path)


def _file(body, config, **header):
    head = {
        "format": suggestions.FORMAT,
        "contract": contract.config_hash(config),
        "producer": {"name": "test", "run_id": "run-1"},
        "subject": "Gabe Bolton",
    }
    head.update(header)
    return yaml.safe_dump(head, sort_keys=False) + body


def _check(text, config):
    return suggestions.check(text, contract.build(config),
                             staging.current_names(config),
                             staging.pending_rows())


GOOD_ACTIVITY = """
activities:
  - name: Open App Builder v0.23.0 release
    description: "Release notes: https://example.org/releases/v0.23.0"
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2024-02-14
    source_ref: "github:oab#v0.23.0"
"""


# --------------------------------------------------------------------------
# Parsing and the header
# --------------------------------------------------------------------------

def test_not_yaml_is_an_error_naming_the_problem(deployment):
    proposal = _check("activities:\n  - name: [unclosed", deployment)
    assert len(proposal.errors) == 1
    assert "not valid yaml" in proposal.errors[0].message.lower()


def test_empty_file(deployment):
    assert _check("", deployment).errors


def test_a_list_at_the_top_level_is_rejected(deployment):
    assert _check("- name: a thing", deployment).errors


def test_unknown_format_is_refused(deployment):
    proposal = _check(_file(GOOD_ACTIVITY, deployment, format="something/9"),
                      deployment)
    assert any("Unsupported format" in f.message for f in proposal.errors)


def test_a_different_contract_hash_warns_rather_than_refusing(deployment):
    """A proposal drafted on Monday against a config edited on Tuesday is
    usually still good."""
    proposal = _check(_file(GOOD_ACTIVITY, deployment, contract="sha256:0000"),
                      deployment)
    assert not proposal.errors
    assert any("different version of the forms" in f.message
               for f in proposal.warnings)
    assert len(proposal.stageable) == 1


def test_coverage_gap_is_surfaced(deployment):
    proposal = _check(
        _file(GOOD_ACTIVITY, deployment,
              period={"from": "2026-08-01", "to": "2026-11-04"},
              coverage=[{"source": "worklog", "through": "2026-08-06"}]),
        deployment)
    gap = [f for f in proposal.warnings if "2026-08-06" in f.message]
    assert gap
    assert "90 days before the end" in gap[0].message


def test_a_source_that_runs_to_the_end_of_the_period_is_not_a_gap(deployment):
    """
    The first real file declared six sources, five of which ran to the last
    day. Warning about each buried the one that mattered, and a warning that
    fires when nothing is wrong teaches people to skip warnings.
    """
    proposal = _check(
        _file(GOOD_ACTIVITY, deployment,
              period={"from": "2026-08-01", "to": "2026-11-04"},
              coverage=[
                  {"source": "github", "through": "2026-11-04"},
                  {"source": "drive", "through": "2026-11-04"},
                  {"source": "worklog", "through": "2026-08-06"},
              ]),
        deployment)
    gaps = [f for f in proposal.warnings if "Evidence from" in f.message]
    assert len(gaps) == 1
    assert "worklog" in gaps[0].message


def test_a_coverage_note_is_carried_into_the_warning(deployment):
    """
    Where the explanation has to live. The first real file put four paragraphs
    of caveats in YAML comments, which do not survive parsing.
    """
    proposal = _check(
        _file(GOOD_ACTIVITY, deployment,
              period={"from": "2026-08-01", "to": "2026-11-04"},
              coverage=[{"source": "worklog", "through": "2026-08-06",
                         "note": "No narrative log after this date."}]),
        deployment)
    assert any("No narrative log after this date." in f.message
               for f in proposal.warnings)


# --------------------------------------------------------------------------
# Per-record checking
# --------------------------------------------------------------------------

def test_a_good_record_is_stageable_with_nothing_to_say(deployment):
    proposal = _check(_file(GOOD_ACTIVITY, deployment), deployment)
    assert not proposal.errors
    assert len(proposal.stageable) == 1
    record = proposal.stageable[0]
    assert record.action == "create"
    assert record.links["initiatives_links"] == [1]
    assert record.links["people_links"] == [1]


def test_missing_required_links_block_the_record(deployment):
    proposal = _check(_file("""
activities:
  - name: Orphan
    description: no links
    source_ref: "x:1"
""", deployment), deployment)
    messages = " ".join(f.message for f in proposal.errors)
    assert "Linked Initiatives is required" in messages
    assert "Linked People is required" in messages
    assert proposal.stageable == []


def test_a_link_that_resolves_to_nothing_is_an_error_naming_it(deployment):
    proposal = _check(_file("""
activities:
  - name: Ghost
    initiatives: [No Such Initiative]
    people: [Gabe Bolton]
    source_ref: "x:2"
""", deployment), deployment)
    assert any("No Such Initiative" in f.message for f in proposal.errors)


def test_an_unparseable_date_is_an_error(deployment):
    proposal = _check(_file("""
activities:
  - name: Undated
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: last spring
    source_ref: "x:3"
""", deployment), deployment)
    assert any("is not a date" in f.message for f in proposal.errors)


def test_end_before_start_is_an_error(deployment):
    proposal = _check(_file("""
activities:
  - name: Backwards
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2024-06-01
    end_date: 2024-01-01
    source_ref: "x:4"
""", deployment), deployment)
    assert any("before" in f.message for f in proposal.errors)


def test_a_multi_year_span_is_an_advisory_not_an_error(deployment):
    proposal = _check(_file("""
activities:
  - name: Long haul
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2021-01-01
    end_date: 2024-12-31
    source_ref: "x:5"
""", deployment), deployment)
    assert not proposal.errors
    assert any("usually an initiative" in f.message for f in proposal.advisories)


def test_tags_are_dropped_when_there_is_no_vocabulary(deployment):
    """
    A deployment with no tag groups has nothing to choose from. The record
    still stages — tagging is never the reason a record fails.
    """
    proposal = _check(_file("""
activities:
  - name: Tagged
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    tags:
      impact_area: [Climate]
    source_ref: "x:6"
""", deployment), deployment)
    assert not proposal.errors
    assert len(proposal.stageable) == 1
    assert "tag_groups" not in proposal.stageable[0].values
    assert any("no tag groups defined" in f.message for f in proposal.warnings)


def test_an_element_that_does_not_exist_is_an_error(deployment):
    proposal = _check(_file("""
activities:
  - name: Odd
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    enthusiasm: high
    source_ref: "x:7"
""", deployment), deployment)
    assert any("enthusiasm" in f.message for f in proposal.errors)


def test_missing_source_ref_warns_about_what_it_costs(deployment):
    proposal = _check(_file("""
activities:
  - name: Anonymous
    initiatives: [R-Instat]
    people: [Gabe Bolton]
""", deployment), deployment)
    assert any("source_ref" in f.message for f in proposal.warnings)


def test_inferred_is_carried_and_an_unknown_element_in_it_warns(deployment):
    proposal = _check(_file("""
activities:
  - name: Guessy
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2024-01-01
    source_ref: "x:8"
    inferred:
      start_date: '"early 2024"'
      nonexistent: why
""", deployment), deployment)
    assert proposal.stageable[0].inferred["start_date"]
    assert any("nonexistent" in f.message for f in proposal.warnings)


# --------------------------------------------------------------------------
# Updating an existing record
# --------------------------------------------------------------------------

def test_a_target_whose_name_disagrees_is_refused(deployment):
    proposal = _check(_file("""
initiatives:
  - target: {id: 1, expect: Something Else}
    description: new words
    source_ref: "x:9"
""", deployment), deployment)
    assert any("Refusing rather than editing a different record" in f.message
               for f in proposal.errors)


def test_a_target_that_agrees_is_an_update(deployment):
    proposal = _check(_file("""
initiatives:
  - target: {id: 1, expect: R-Instat}
    description: Statistics software powered by R.
    source_ref: "x:10"
""", deployment), deployment)
    assert not proposal.errors
    assert proposal.stageable[0].action == "update"


def test_an_update_does_not_need_the_required_set(deployment):
    """The record already satisfies its own required elements."""
    proposal = _check(_file("""
initiatives:
  - target: {id: 1, expect: R-Instat}
    description: just a new description
    source_ref: "x:11"
""", deployment), deployment)
    assert not proposal.errors


def test_a_target_id_that_does_not_exist_is_refused(deployment):
    proposal = _check(_file("""
initiatives:
  - target: {id: 999, expect: Nothing}
    description: x
    source_ref: "x:12"
""", deployment), deployment)
    assert any("999" in f.message for f in proposal.errors)


# --------------------------------------------------------------------------
# Advisories: the thing already exists
# --------------------------------------------------------------------------

def test_a_rewording_of_an_existing_record_is_flagged(deployment):
    proposal = _check(_file("""
initiatives:
  - name: Development of R-Instat
    responsible_person: Gabe Bolton
    source_ref: "x:13"
""", deployment), deployment)
    assert not proposal.errors, "an advisory must never block"
    assert len(proposal.stageable) == 1
    matched = [f for f in proposal.advisories if f.match
               and f.match[0] == "initiatives"]
    assert matched and matched[0].match[2] == "R-Instat"
    assert any("reads as a description of work" in f.message
               for f in proposal.advisories)


def test_document_phrasing_is_not_flagged_on_an_activity(deployment):
    """
    An activity is a thing that happened, so a name describing work is what
    its name is for. The advisory is about initiatives, and it quotes a
    statistic about initiatives to justify itself — it fired on an activity in
    the first real run.
    """
    proposal = _check(_file("""
activities:
  - name: Teaching statistical problem solving
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "x:phrasing"
""", deployment), deployment)
    assert not [f for f in proposal.advisories
                if "description of work" in f.message]


def test_two_records_in_one_file_naming_the_same_thing(deployment):
    proposal = _check(_file("""
activities:
  - name: STACK conference Africa
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "x:14"
  - name: Africa STACK conference
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "x:15"
""", deployment), deployment)
    assert any("Also proposed in this file" in f.message
               for f in proposal.advisories)


def test_an_unrelated_name_gets_no_advisory(deployment):
    proposal = _check(_file("""
initiatives:
  - name: Certificator
    responsible_person: Gabe Bolton
    source_ref: "x:16"
""", deployment), deployment)
    assert proposal.advisories == []


# --------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------

def test_staging_then_reimporting_changes_nothing(deployment):
    """Roadmap #69's acceptance: importing twice produces the same state."""
    text = _file(GOOD_ACTIVITY, deployment)
    first = staging.stage(_check(text, deployment))
    assert len(first["staged"]) == 1

    second = staging.stage(_check(text, deployment))
    assert second["staged"] == []
    assert len(second["already"]) == 1
    assert staging.counts() == {"pending": 1}


def test_blocked_records_are_not_staged_and_the_rest_are(deployment):
    proposal = _check(_file(GOOD_ACTIVITY + """
  - name: Broken
    source_ref: "x:17"
""", deployment), deployment)
    report = staging.stage(proposal)
    assert len(report["staged"]) == 1
    assert len(report["blocked"]) == 1


def test_a_declined_suggestion_does_not_come_back(deployment):
    text = _file(GOOD_ACTIVITY, deployment)
    staging.stage(_check(text, deployment))
    staged_id = staging.queue()[0]["id"]
    staging.resolve(staged_id, staging.DECLINED, person_id=1)

    report = staging.stage(_check(text, deployment))
    assert report["staged"] == []
    assert len(report["declined"]) == 1


def test_declines_are_exported_for_the_next_bundle(deployment):
    staging.stage(_check(_file(GOOD_ACTIVITY, deployment), deployment))
    staging.resolve(staging.queue()[0]["id"], staging.DECLINED, person_id=1)

    declined = staging.rejections()
    assert len(declined) == 1
    assert declined[0]["source_ref"] == "github:oab#v0.23.0"
    # The name travels with the ref so a producer can recognise the same thing
    # proposed again under a different ref.
    assert declined[0]["name"] == "Open App Builder v0.23.0 release"


def test_a_record_with_no_source_ref_cannot_be_deduplicated(deployment):
    text = _file("""
activities:
  - name: Refless
    initiatives: [R-Instat]
    people: [Gabe Bolton]
""", deployment)
    staging.stage(_check(text, deployment))
    staging.stage(_check(text, deployment))
    assert staging.counts()["pending"] == 2, "nothing to deduplicate on"


# --------------------------------------------------------------------------
# Two people, one piece of work
# --------------------------------------------------------------------------

MINE = """
activities:
  - name: "2nd African STACK Conference"
    description: Second African STACK conference.
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "drive:mine"
"""

THEIRS = """
activities:
  - name: "African STACK Conference 2"
    description: The second STACK conference held in Africa.
    initiatives: [ePICSA]
    people: [Michele Zamparo]
    source_ref: "drive:theirs"
"""


def test_a_colleagues_pending_proposal_is_flagged_not_merged(deployment):
    staging.stage(_check(_file(MINE, deployment), deployment), person_id=1)

    proposal = _check(_file(THEIRS, deployment, subject="Michele Zamparo"),
                      deployment)
    collision = [f for f in proposal.advisories
                 if f.match and f.match[0] == "pending"]
    assert collision, "the same work from different evidence was not noticed"
    assert "Gabe Bolton" in collision[0].message


def test_overlapping_proposals_are_grouped(deployment):
    staging.stage(_check(_file(MINE, deployment), deployment), person_id=1)
    staging.stage(_check(_file(THEIRS, deployment, subject="Michele Zamparo"),
                         deployment), person_id=2)

    groups = staging.groups()
    assert len(groups) == 1, "two proposals for one thing were left separate"
    (items,) = groups.values()
    assert {item["subject"] for item in items} == {"Gabe Bolton",
                                                   "Michele Zamparo"}
    assert len({item["id"] for item in items}) == 2, "both are kept, not merged"


def test_different_work_is_not_grouped(deployment):
    staging.stage(_check(_file(MINE, deployment), deployment), person_id=1)
    staging.stage(_check(_file("""
activities:
  - name: Certificator API release
    initiatives: [ePICSA]
    people: [Michele Zamparo]
    source_ref: "drive:other"
""", deployment, subject="Michele Zamparo"), deployment), person_id=2)
    assert len(staging.groups()) == 2


# --------------------------------------------------------------------------
# Handing a suggestion to the form
# --------------------------------------------------------------------------

def test_form_inputs_marks_every_value_unconfirmed(deployment):
    from pantograph import provenance

    staging.stage(_check(_file("""
activities:
  - name: Release
    description: Shipped it.
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2024-02-14
    source_ref: "x:18"
    cites: [ar2021]
    inferred:
      start_date: '"February", no day given'
""", deployment), deployment))

    values, provenances = staging.form_inputs(staging.queue()[0])
    assert values["name"] == "Release"
    assert values["initiatives_links"] == [1]
    assert set(provenances) == set(values)
    assert not any(provenance.is_confirmed(p) for p in provenances.values())


def test_a_cited_record_is_cited_not_suggested(deployment):
    """
    A record read out of a document is a citation of a secondary source, which
    is a different claim from a model's inference.
    """
    staging.stage(_check(_file("""
activities:
  - name: From a report
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "x:19"
    cites: [ar2021]
""", deployment), deployment))
    _, provenances = staging.form_inputs(staging.queue()[0])
    assert provenances["name"]["source"] == "cited"
    assert "ar2021" in provenances["name"]["from"]


def test_a_record_with_no_citation_is_suggested(deployment):
    staging.stage(_check(_file(GOOD_ACTIVITY, deployment), deployment))
    _, provenances = staging.form_inputs(staging.queue()[0])
    assert provenances["name"]["source"] == "suggested"


def test_an_inferred_value_carries_less_confidence(deployment):
    staging.stage(_check(_file("""
activities:
  - name: Guessed
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    start_date: 2024-01-01
    end_date: 2024-12-31
    source_ref: "x:20"
    inferred:
      start_date: '"early in the year"'
""", deployment), deployment))
    _, provenances = staging.form_inputs(staging.queue()[0])
    assert provenances["start_date"]["confidence"] < provenances["end_date"]["confidence"]


def test_a_link_to_an_unaccepted_key_is_held_back_and_reported(deployment):
    """
    An activity cannot link to an initiative in the same file until that
    initiative has an id. The reviewer is told, rather than meeting a submit
    button that will not enable.
    """
    staging.stage(_check(_file("""
initiatives:
  - key: newthing
    name: Brand New Thing
    responsible_person: Gabe Bolton
    source_ref: "x:21"
activities:
  - name: Thing launch
    initiatives: [newthing]
    people: [Gabe Bolton]
    source_ref: "x:22"
""", deployment), deployment))

    activity = [i for i in staging.queue() if i["table"] == "activities"][0]
    assert staging.unresolved_links(activity) == {"initiatives_links": ["newthing"]}
    values, _ = staging.form_inputs(activity)
    assert "initiatives_links" not in values


# --------------------------------------------------------------------------
# The two-step page
#
# These exist because every unit test above passed while the actual flow was
# broken: the file was round-tripped between "check" and "stage" through a
# hidden form field, where it got escaped twice, so the second step re-parsed
# mangled YAML and staged nothing while reporting success.
# --------------------------------------------------------------------------

@pytest.fixture
def client(dash_app, deployment):
    return dash_app.server.test_client()


def _post(client, text, step="check"):
    with client.session_transaction() as flask_session:
        flask_session["csrf_token"] = "test-token"
    return client.post("/import", data={
        "csrf_token": "test-token", "step": step, "text": text},
        follow_redirects=True)


def test_the_page_checks_then_stages(client, deployment):
    text = _file(GOOD_ACTIVITY, deployment)

    report = _post(client, text)
    assert report.status_code == 200
    assert b"Import report" in report.data
    assert staging.counts() == {}, "checking must not stage anything"

    staged = _post(client, "", step="stage")
    assert b"Staged" in staged.data
    assert staging.counts() == {"pending": 1}


def test_a_file_with_quotes_and_newlines_survives_the_two_steps(client, deployment):
    """The exact shape that was being corrupted: quotes, colons and a URL."""
    text = _file("""
activities:
  - name: "Collaboratorium: agent handoff"
    description: "Built it. PR: https://example.org/pull/108 — see \\"the notes\\""
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "github:collab#1"
""", deployment)

    _post(client, text)
    _post(client, "", step="stage")

    assert staging.counts() == {"pending": 1}
    item = staging.queue()[0]
    assert item["name"] == "Collaboratorium: agent handoff"
    summary = item["payload"]["values"]["description"]["1"]["description"]
    assert "https://example.org/pull/108" in summary
    assert "&quot;" not in summary


def test_csrf_is_required(client, deployment):
    assert client.post("/import", data={"step": "check", "text": "x"}).status_code == 400


def test_the_queue_lists_what_was_staged(client, deployment):
    _post(client, _file(GOOD_ACTIVITY, deployment))
    _post(client, "", step="stage")

    page = client.get("/import/queue")
    assert b"Open App Builder v0.23.0 release" in page.data


@pytest.mark.evidence
def test_the_queue_still_loads_when_an_activity_carries_a_summary(client, deployment):
    """
    Found on the live server: an activity's summary is stored as a nested
    mapping (it is a leaf of a static subform), and the queue sliced it as if it
    were a string, so the whole page was a server error and nothing staged was
    visible. A second upload then reported every record as already here.
    """
    _post(client, _file("""
activities:
  - name: Queue Summary Activity
    summary: Released v0.23.0 with offline sync.
    attachments: [{name: Release notes, url: "https://example.org/r/1"}]
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "github:oab#queue-summary"
""", deployment))
    _post(client, "", step="stage")

    page = client.get("/import/queue")
    assert page.status_code == 200
    assert b"Queue Summary Activity" in page.data
    assert b"Released v0.23.0 with offline sync." in page.data


@pytest.mark.evidence
def test_the_import_page_queue_row_handles_a_nested_summary():
    """
    The Import page is a Dash page with its own row builder, and it sliced the
    description as a string too. An activity's summary is nested, so building the
    row raised and the queue rendered empty — which is what the live server did.
    """
    from pantograph_import import page

    def row(description):
        item = {"id": 1, "name": "An activity", "table": "activities",
                "action": "create", "subject": "Gabe", "run_id": "r",
                "payload": {"values": {"description": description},
                            "inferred": {}}}
        return _text_of(page._row(item, "import"))

    assert "Released v0.23.0" in row({"1": {"description": "Released v0.23.0",
                                            "attachments": [{"name": "n", "url": "https://e.org"}]}})
    assert "A plain summary" in row("A plain summary")
    assert "An activity" in row({"1": {"attachments": []}})


def test_declining_from_the_queue_sticks(client, deployment):
    _post(client, _file(GOOD_ACTIVITY, deployment))
    _post(client, "", step="stage")
    staged_id = staging.queue()[0]["id"]

    with client.session_transaction() as flask_session:
        flask_session["csrf_token"] = "test-token"
    client.post("/import/decline",
                data={"csrf_token": "test-token", "id": staged_id},
                follow_redirects=True)

    assert staging.counts() == {"declined": 1}
    assert staging.rejections()[0]["source_ref"] == "github:oab#v0.23.0"


def test_opening_a_suggestion_remembers_which_one(client, deployment):
    """
    What lets a successful save mark the suggestion answered. Without it the
    queue never empties.
    """
    _post(client, _file(GOOD_ACTIVITY, deployment))
    _post(client, "", step="stage")
    staged_id = staging.queue()[0]["id"]

    response = client.get(f"/import/open/{staged_id}")
    assert response.status_code in (301, 302)
    assert f"#suggest/{staged_id}" in response.headers["Location"]
    with client.session_transaction() as flask_session:
        assert tuple(flask_session["reviewing_suggestion"]) == (staged_id,
                                                                "activities")


def test_accepting_the_initiative_resolves_the_activity_s_link(deployment):
    staging.stage(_check(_file("""
initiatives:
  - key: newthing
    name: Brand New Thing
    responsible_person: Gabe Bolton
    source_ref: "x:23"
activities:
  - name: Thing launch
    initiatives: [newthing]
    people: [Gabe Bolton]
    source_ref: "x:24"
""", deployment), deployment))

    initiative = [i for i in staging.queue() if i["table"] == "initiatives"][0]
    staging.resolve(initiative["id"], staging.ACCEPTED, person_id=1, record_id=77)

    activity = [i for i in staging.queue() if i["table"] == "activities"][0]
    assert staging.unresolved_links(activity) == {}
    values, _ = staging.form_inputs(activity)
    assert values["initiatives_links"] == [77]


def _text_of(component):
    """Every string in a Dash component tree, joined."""
    if isinstance(component, str):
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(_text_of(c) for c in children)
    return _text_of(children) if children is not None else ""


def test_an_update_form_shows_what_is_recorded_now(deployment):
    """
    A proposal against an existing record is laid over it in the ordinary form,
    so the old value is overwritten on screen. The reviewer is asked to confirm a
    change, so the form has to say what it changes.
    """
    from pantograph.form_gen import generate_form_layout

    forms = deployment["forms"]
    form_name = deployment["default_forms"]["initiatives"]
    layout = generate_form_layout(
        form_name, forms_config=forms, object_id=1,
        initial_values={"name": "R-Instat Renamed"},
        provenances={"name": {"source": "suggested", "confirmed": False}})
    text = _text_of(layout)
    assert "Currently recorded:" in text
    assert "R-Instat" in text

    # A single linked value is shown by name, not by its id.
    person = generate_form_layout(
        form_name, forms_config=forms, object_id=1,
        initial_values={"responsible_person": 2},
        provenances={"responsible_person": {"source": "suggested", "confirmed": False}})
    assert "Currently recorded: Gabe Bolton" in _text_of(person).replace("  ", " ")

    # A value the proposal leaves alone gets no such line.
    same = generate_form_layout(
        form_name, forms_config=forms, object_id=1,
        initial_values={"name": "R-Instat"},
        provenances={"name": {"source": "suggested", "confirmed": False}})
    assert "Currently recorded:" not in _text_of(same)


# --------------------------------------------------------------------------
# Attachments: a leaf of the activity's description, proposed and kept
# --------------------------------------------------------------------------

def test_attachments_can_be_proposed_beside_the_summary(deployment):
    """
    An activity's attachments are a leaf of its `description`, and nothing told a
    producer so, or let one fill them in: every suggested activity arrived with
    none.
    """
    body = """
activities:
  - name: Open App Builder v0.23.0 release
    summary: Released v0.23.0 with offline sync.
    attachments:
      - name: Release notes
        url: https://example.org/releases/v0.23.0
      - {name: Pull request, url: "https://example.org/pull/12"}
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "github:oab#v0.23.0"
"""
    proposal = _check(_file(body, deployment), deployment)
    assert not proposal.errors, [f.message for f in proposal.errors]
    value = proposal.stageable[0].values["description"]
    assert value["1"]["description"] == "Released v0.23.0 with offline sync."
    assert value["1"]["attachments"] == [
        {"name": "Release notes", "url": "https://example.org/releases/v0.23.0"},
        {"name": "Pull request", "url": "https://example.org/pull/12"}]


def test_an_attachment_can_be_flagged_as_a_guess_under_inferred(deployment):
    """
    `inferred: attachments:` used to warn that the record did not set
    `attachments`, because the value lives in `description`, and the reason was
    lost. It now lands on the element the reviewer confirms, saying which part.
    """
    body = """
activities:
  - name: Open App Builder v0.23.0 release
    summary: Released v0.23.0 with offline sync.
    attachments: [{name: Repository, url: "https://example.org/oab"}]
    inferred:
      attachments: repo name matches the project, not confirmed
      summary: worked out from the release notes
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "github:oab#v0.23.0"
"""
    proposal = _check(_file(body, deployment), deployment)
    record = proposal.stageable[0]
    assert not any("inferred" in f.message for f in record.findings), \
        [f.message for f in record.findings]
    assert record.inferred["description"] == (
        "attachments: repo name matches the project, not confirmed; "
        "worked out from the release notes")


def test_an_attachment_without_a_web_address_is_dropped_with_a_warning(deployment):
    body = """
activities:
  - name: Open App Builder v0.23.0 release
    attachments: [{name: Release notes}]
    initiatives: [R-Instat]
    people: [Gabe Bolton]
    source_ref: "github:oab#v0.23.0"
"""
    proposal = _check(_file(body, deployment), deployment)
    record = proposal.stageable[0]
    assert "description" not in record.values
    assert any("no http(s)" in f.message for f in record.findings)


def test_a_proposed_summary_keeps_the_attachments_already_recorded(deployment):
    """
    The form lays a proposal over the stored record. A proposal that names only
    the summary used to replace the whole subform, so the attachments beside it
    disappeared from the form and were lost on save.
    """
    from pantograph import subforms

    stored = json.dumps({"1": {"description": "old", "attachments": [
        {"name": "Release notes", "url": "https://example.org/r"},
        {"name": None, "url": None}]}})
    merged = subforms.overlay(stored, {"1": {"description": "new"}})
    assert merged["1"]["description"] == "new"
    assert merged["1"]["attachments"][0] == {
        "name": "Release notes", "url": "https://example.org/r"}

    # Proposed attachments are added, and one already there is not repeated.
    merged = subforms.overlay(stored, {"1": {"attachments": [
        {"name": "Release notes again", "url": "https://example.org/r"},
        {"name": "Docs", "url": "https://example.org/d"}]}})
    assert merged["1"]["description"] == "old"
    assert [r["url"] for r in merged["1"]["attachments"]] == [
        "https://example.org/r", "https://example.org/d"]


def test_an_update_form_still_shows_the_recorded_attachment(deployment):
    from pantograph.form_gen import generate_form_layout

    now = datetime.datetime.now().isoformat()
    conn = db_connect()
    conn.execute(
        "INSERT INTO activities (id,version,name,description,status,timestamp,created_by)"
        " VALUES (1,1,'Release',?, 'active',?,1)",
        (json.dumps({"1": {"description": "", "attachments": [
            {"name": "Release Notes", "url": "https://example.org/notes"}]}}), now))
    conn.commit()
    conn.close()

    layout = generate_form_layout(
        deployment["default_forms"]["activities"], forms_config=deployment["forms"],
        object_id=1,
        initial_values={"description": {"1": {"description": "Cut the release."}}},
        provenances={"description": {"source": "suggested", "confirmed": False}})
    # Dash components keep values in props, which `repr` shows and the helper
    # that reads children does not. Take it from the form's own subform store.
    text = repr(layout)
    assert "Cut the release." in text
    # Once in the "Currently recorded" line, and once more in the form itself.
    assert text.count("https://example.org/notes") >= 2
