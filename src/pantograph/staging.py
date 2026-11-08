"""
staging.py
Holding proposed records between the upload and the person who confirms them.

Two properties justify a table rather than a session store, and nothing else
could provide either:

**Importing the same file twice produces the same state.** Deduplicated on
`source_ref`, which is why the format insists a producer anchor it on the
evidence and never on the run.

**A decline is remembered.** A proposal somebody rejected comes back in the
next bundle's `rejections.yaml` and is dropped rather than re-queued if it is
sent again. Without this, the third run of any producer is unusable.

It also holds the answer to overlapping work. Two people who worked on the same
activity propose it from different evidence, so their `source_ref`s differ and
deduplication cannot see that it is one thing. Those proposals are **grouped**
instead, and a reviewer resolves the group to one record with everyone linked —
which is what `activity_people_links` is for.
"""
import json
import uuid
from datetime import datetime, timezone

from pantograph.db import SUGGESTIONS_TABLE, db_connect, get_current_records

PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_names(config):
    """
    `{table: [(id, name)]}` for every table a proposal may target, read now.

    Deliberately read at import time rather than taken from the bundle's
    snapshot: a colleague may have imported something an hour ago, and matching
    against a stale snapshot is exactly how two records for one thing get made.
    """
    names = {}
    for table in ("initiatives", "activities", "contracts", "people",
                  "organisations"):
        try:
            rows = get_current_records(table)
        except Exception:
            continue
        names[table] = [(row["id"], row.get("name"))
                        for row in rows if row.get("name")]
    return names


def tag_vocabulary(config):
    """
    The tag groups as they exist right now: `{group_id: key_values}`.

    Read at import time rather than from the bundle's snapshot, for the same
    reason names are: a term added this morning should be proposable this
    afternoon. Empty when a deployment has no tag groups, which is how a
    proposal that sets tags is told there is nothing to set them to.

    The element whose groups these are is found from config rather than named
    here, so a deployment that calls its tag element something else still
    works.
    """
    table = None
    for form in (config.get("forms") or {}).values():
        for element in (form.get("elements") or {}).values():
            parameters = (element or {}).get("parameters") or {}
            if (element or {}).get("type") == "subform" and {
                    "source_table", "value_column", "label_column"
            }.issubset(parameters):
                table = parameters["source_table"]
                break
        if table:
            break
    if not table:
        return {}

    found = {}
    try:
        rows = get_current_records(table)
    except Exception:
        return {}
    for row in rows:
        raw = row.get("key_values")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            found[str(row["id"])] = parsed
    return found


def pending_rows():
    """
    `[(source_ref, table, name, subject)]` for everything awaiting review.

    Fed to the checker so a new upload collides with a colleague's unreviewed
    proposal instead of quietly becoming a second record.
    """
    conn = db_connect()
    rows = conn.execute(
        f'SELECT source_ref, record_table, name, subject FROM "{SUGGESTIONS_TABLE}"'
        f' WHERE state = ?', (PENDING,)).fetchall()
    conn.close()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def declined_refs():
    """The `source_ref`s a person has turned down."""
    conn = db_connect()
    rows = conn.execute(
        f'SELECT source_ref FROM "{SUGGESTIONS_TABLE}" WHERE state = ?'
        f' AND source_ref IS NOT NULL', (DECLINED,)).fetchall()
    conn.close()
    return {r[0] for r in rows}


def existing_states():
    """`{source_ref: state}` for everything already staged."""
    conn = db_connect()
    rows = conn.execute(
        f'SELECT source_ref, state FROM "{SUGGESTIONS_TABLE}"'
        f' WHERE source_ref IS NOT NULL').fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def _payload(record):
    return json.dumps({
        "values": record.values,
        "links": record.links,
        "inferred": record.inferred,
        "cites": record.cites,
        "target": record.target,
        "key": record.key,
        "findings": [
            {"severity": f.severity, "message": f.message,
             "element": f.element, "match": f.match}
            for f in record.findings
        ],
    }, default=str)


def stage(proposal, person_id=None):
    """
    Persist a checked proposal's stageable records.

    Returns a report: what was staged, what was skipped because it was already
    here, what was dropped because it had been declined, and which records were
    grouped with an existing proposal.
    """
    states = existing_states()
    pending_by_ref = {ref: (table, name, subject)
                      for ref, table, name, subject in pending_rows()}

    report = {"staged": [], "already": [], "declined": [], "grouped": [],
              "blocked": [r for r in proposal.records if r.blocked]}

    conn = db_connect()
    cur = conn.cursor()
    run_id = proposal.run_id
    subject = proposal.subject

    for record in proposal.stageable:
        ref = record.source_ref

        if ref and states.get(ref) == DECLINED:
            # Sticky: a proposal somebody turned down does not come back.
            report["declined"].append(record)
            continue
        if ref and ref in states:
            report["already"].append(record)
            continue

        # A collision with somebody else's unreviewed proposal shares its
        # group, so the two are resolved together rather than separately.
        group_id = None
        for finding in record.findings:
            if finding.match and finding.match[0] == "pending":
                other_ref = finding.match[1]
                group_id = _group_for(cur, other_ref) or f"grp-{uuid.uuid4().hex[:10]}"
                _assign_group(cur, other_ref, group_id)
                report["grouped"].append((record, pending_by_ref.get(other_ref)))
                break

        cur.execute(
            f'INSERT INTO "{SUGGESTIONS_TABLE}" (source_ref, run_id, subject,'
            f' record_table, action, target_id, name, payload, group_id, state,'
            f' created_at, created_by)'
            f' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (ref, run_id, subject, record.table, record.action,
             (record.target or {}).get("id"), record.name, _payload(record),
             group_id, PENDING, _now(), person_id))
        report["staged"].append(record)
        if ref:
            states[ref] = PENDING

    conn.commit()
    conn.close()
    return report


def _group_for(cur, source_ref):
    if not source_ref:
        return None
    row = cur.execute(
        f'SELECT group_id FROM "{SUGGESTIONS_TABLE}" WHERE source_ref = ?',
        (source_ref,)).fetchone()
    return row[0] if row else None


def _assign_group(cur, source_ref, group_id):
    if source_ref:
        cur.execute(
            f'UPDATE "{SUGGESTIONS_TABLE}" SET group_id = ? WHERE source_ref = ?'
            f' AND group_id IS NULL', (group_id, source_ref))


def preview_text(value):
    """
    The first readable text in a proposed `description`, for a queue row.

    A summary is a leaf of a static subform, so it arrives as nested mappings
    (`{"1": {"description": "..."}}`), and an older row may still hold a bare
    string. Both queue pages used to slice it as text, which raised on the
    nested form and left the queue empty.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for inner in value.values():
            found = preview_text(inner)
            if found:
                return found
    return ""


def queue(state=PENDING, table=None):
    """Staged suggestions, newest group first, as dicts with payload parsed."""
    conn = db_connect()
    sql = (f'SELECT id, source_ref, run_id, subject, record_table, action,'
           f' target_id, name, payload, group_id, state, created_at, record_id'
           f' FROM "{SUGGESTIONS_TABLE}" WHERE state = ?')
    params = [state]
    if table:
        sql += " AND record_table = ?"
        params.append(table)
    sql += " ORDER BY group_id IS NULL, group_id, id"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    columns = ("id", "source_ref", "run_id", "subject", "table", "action",
               "target_id", "name", "payload", "group_id", "state",
               "created_at", "record_id")
    out = []
    for row in rows:
        item = dict(zip(columns, row))
        item["payload"] = json.loads(item["payload"])
        out.append(item)
    return out


def groups(state=PENDING):
    """
    Pending suggestions gathered into the sets that have to be resolved
    together. A suggestion with no collision is a group of one.
    """
    gathered = {}
    for item in queue(state):
        key = item["group_id"] or f"single-{item['id']}"
        gathered.setdefault(key, []).append(item)
    return gathered


def review_order():
    """
    The queue as `(groups, total)`, in the order a reviewer should take it.

    Initiatives first, then whatever is ready, then whatever is waiting on
    something else. An activity cannot be saved without an initiative to link it
    to, so a queue that offers them in file order sends the reviewer to a form
    whose submit button will not enable. Each item gains a `waiting` entry
    naming what it is waiting on.
    """
    grouped = groups()
    keys = resolved_keys()
    for items in grouped.values():
        for item in items:
            item["waiting"] = unresolved_links(item, keys)
    order = {"initiatives": 0, "contracts": 1, "activities": 2}
    ordered = dict(sorted(
        grouped.items(),
        key=lambda entry: (
            any(item["waiting"] for item in entry[1]),
            min(order.get(item["table"], 9) for item in entry[1]),
            -len(entry[1]),
        )))
    return ordered, sum(len(items) for items in ordered.values())


def get(suggestion_id):
    for item in queue(PENDING) + queue(ACCEPTED) + queue(DECLINED):
        if item["id"] == suggestion_id:
            return item
    return None


def resolved_keys():
    """
    `{key: record_id}` for suggestions that have been accepted.

    A proposal links its own records to each other by `key`, because ids are
    allocated on save. Once one of them is accepted it has an id, and the
    records that referred to it can finally be linked — so this is what turns a
    file's internal references into real links, one acceptance at a time.
    """
    conn = db_connect()
    rows = conn.execute(
        f'SELECT payload, record_id FROM "{SUGGESTIONS_TABLE}"'
        f' WHERE state = ? AND record_id IS NOT NULL', (ACCEPTED,)).fetchall()
    conn.close()
    found = {}
    for payload, record_id in rows:
        key = (json.loads(payload) or {}).get("key")
        if key:
            found[key] = record_id
    return found


def unresolved_links(item, keys=None):
    """
    `{element: [key, ...]}` for links still waiting on another suggestion.

    Shown on the queue so a reviewer is told *why* a record is not ready,
    rather than opening it and meeting a submit button that will not enable.
    """
    keys = resolved_keys() if keys is None else keys
    waiting = {}
    for element, ids in ((item["payload"].get("links")) or {}).items():
        pending_keys = [ref[1] for ref in ids
                        if isinstance(ref, (list, tuple)) and len(ref) == 2
                        and ref[0] == "key" and ref[1] not in keys]
        if pending_keys:
            waiting[element.lstrip("@")] = pending_keys
    return waiting


def note_saved(table, record_id):
    """
    Mark the suggestion a person was reviewing as accepted, if they just saved
    the record it proposed.

    The link between the two is a session key set when the queue hands them the
    form, which is available here because a Dash callback runs inside the Flask
    request that triggered it — the same reason `login_required` works on one.

    Guarded on the table matching, so opening a suggestion and then adding
    something else entirely does not silently accept the suggestion. Anything
    unexpected leaves the suggestion pending: a queue that still shows a done
    item is a small annoyance, and one that hides an undone item is a lost
    record.
    """
    try:
        from flask import session, has_request_context
        if not has_request_context():
            return None
        reviewing = session.get("reviewing_suggestion")
        if not reviewing:
            return None
        suggestion_id, suggestion_table = reviewing
        if suggestion_table != table:
            return None
        session.pop("reviewing_suggestion", None)
        resolve(suggestion_id, ACCEPTED, record_id=record_id)
        return suggestion_id
    except Exception:
        return None


def form_inputs(item):
    """
    A staged suggestion as `(initial_values, provenances)` for the form engine.

    Every element the proposal speaks about gets a provenance, because every one
    of them came from somewhere other than a person typing it here — which is
    the only claim provenance exists to prevent making by accident.

    The source is `cited` when the producer named what it read and `suggested`
    otherwise. That distinction came out of the annual-report reading: a record
    drawn from a document is a citation of a secondary source, reliable about
    what happened and unreliable about when, which is a different thing from a
    model's inference and reads differently to whoever confirms it.

    Confidence is coarse on purpose — an element the producer listed under
    `inferred:` is a stated guess, anything else it claims to have read. There
    is no evidence yet for finer gradations, and a number invented here would
    be read as one that was measured.
    """
    from pantograph import provenance

    payload = item["payload"]
    values = dict(payload.get("values") or {})
    inferred = payload.get("inferred") or {}
    cites = payload.get("cites") or []
    origin = item.get("run_id") or "import"

    keys = resolved_keys()
    for element, ids in (payload.get("links") or {}).items():
        resolved = []
        for ref in ids:
            if isinstance(ref, int):
                resolved.append(ref)
            elif (isinstance(ref, (list, tuple)) and len(ref) == 2
                  and ref[0] == "key" and ref[1] in keys):
                # Another record in the same file, accepted since, so it finally
                # has an id to link to.
                resolved.append(keys[ref[1]])
        if not resolved:
            # Still waiting on a record this file has not had accepted yet.
            # Left out rather than guessed at; the queue says which.
            continue
        values[element.lstrip("@")] = resolved

    source = "cited" if cites else "suggested"
    provenances = {}
    for element in values:
        note = inferred.get(element)
        provenances[element] = provenance.record(
            source,
            origin=f"{origin}: {', '.join(str(c) for c in cites)}" if cites else origin,
            confidence=0.5 if note else 0.9,
            note=note,
        )
    return values, provenances


def resolve(suggestion_id, state, person_id=None, record_id=None):
    """Mark a suggestion accepted or declined."""
    if state not in (ACCEPTED, DECLINED):
        raise ValueError(f"not a resolution: {state!r}")
    conn = db_connect()
    conn.execute(
        f'UPDATE "{SUGGESTIONS_TABLE}" SET state = ?, resolved_at = ?,'
        f' resolved_by = ?, record_id = ? WHERE id = ?',
        (state, _now(), person_id, record_id, suggestion_id))
    conn.commit()
    conn.close()


def rejections():
    """
    What goes in the next bundle's `rejections.yaml`.

    Name and table as well as the ref, because a producer that can see *what*
    was declined can avoid proposing the same thing under a new ref — which is
    the hole a bare list of refs leaves open.
    """
    conn = db_connect()
    rows = conn.execute(
        f'SELECT source_ref, record_table, name, resolved_at FROM'
        f' "{SUGGESTIONS_TABLE}" WHERE state = ? AND source_ref IS NOT NULL'
        f' ORDER BY resolved_at', (DECLINED,)).fetchall()
    conn.close()
    return [{"source_ref": r[0], "table": r[1], "name": r[2], "declined_at": r[3]}
            for r in rows]


def counts():
    """How many suggestions are in each state, for the page header."""
    conn = db_connect()
    rows = conn.execute(
        f'SELECT state, COUNT(*) FROM "{SUGGESTIONS_TABLE}" GROUP BY state'
    ).fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}
