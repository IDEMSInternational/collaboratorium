"""
provenance.py
Where a value came from, and whether anyone here stood behind it.

The same shape arrived from three directions — a field inherited from the
product versus set on this deployment, a shared assessment cited versus a
justification written for this record, and a model suggestion versus a human
answer. Each is *a value, where it came from, and whether someone here stood
behind it*, so it is one mechanism in core rather than three in a plugin.

A value may carry a provenance record alongside it:

    {"source": "suggested", "from": "run-2026-03-04", "confidence": 0.82,
     "confirmed_by": None, "confirmed_at": None}

`source` is one of `entered`, `inherited`, `cited` or `suggested`, and `from`
means whatever that source needs it to mean — a scope id, an `[assessment_id,
version]` pair, an analysis run id. Core does not interpret it; it is carried,
shown, and stored.

**Absent provenance means "entered".** Every record and form written before this
existed keeps working unchanged, and a deployment that never supplies a
provenance sees no difference at all. That invariant is why `is_confirmed(None)`
is True and why nothing is wrapped, stored or watched for an element that has no
provenance to speak of.

A value counts as confirmed when it was entered here, or when someone confirmed
it. Anything else is *unconfirmed*: it renders visibly distinct, it does not
satisfy a `required:` element, and it carries a control to confirm it. For a
compliance record that is not a nicety — a register that cannot distinguish "a
model inferred this purpose" from "the controller asserted this purpose" is not
a defensible record.

It is stored in a table of its own, keyed by the record row it describes — see
"Persistence" below.
"""
import json
from datetime import datetime

from dash import MATCH, Input, Output, State, no_update

ENTERED = "entered"
INHERITED = "inherited"
CITED = "cited"
SUGGESTED = "suggested"

SOURCES = (ENTERED, INHERITED, CITED, SUGGESTED)


class ProvenanceError(Exception):
    """Raised when a provenance record is constructed with a source core cannot honour."""


def record(source, origin=None, confidence=None, confirmed_by=None, confirmed_at=None):
    """
    Build a provenance record.

    `origin` is the `from` key, spelled out here because `from` is a Python
    keyword. Callers that already hold the wire shape should pass it through
    `normalise` instead.
    """
    if source not in SOURCES:
        raise ProvenanceError(
            f"{source!r} is not a provenance source; expected one of "
            f"{', '.join(SOURCES)}."
        )
    return {
        "source": source,
        "from": origin,
        "confidence": _confidence(confidence),
        "confirmed_by": confirmed_by,
        "confirmed_at": confirmed_at,
    }


def _confidence(raw):
    """
    A confidence outside 0..1, or one that is not a number at all, is dropped
    rather than shown: a badge reading "140% confidence" is worse than no badge.
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def normalise(raw):
    """
    A provenance record as it arrives from a store, a prefill or an ingest, or
    None when there is none.

    Absence and emptiness both mean "entered", which is what keeps existing
    forms untouched. Something present but unintelligible is *not* treated as
    absent — it is kept as an unconfirmed record of an unknown source, because
    silently promoting data we cannot read into "a human typed this" is the one
    failure this module exists to prevent.
    """
    if not raw:
        return None
    if not isinstance(raw, dict):
        return record_of_unknown_source(raw)
    source = raw.get("source")
    if source == ENTERED:
        return None
    if source not in SOURCES:
        return record_of_unknown_source(source)
    return {
        "source": source,
        "from": raw.get("from"),
        "confidence": _confidence(raw.get("confidence")),
        "confirmed_by": raw.get("confirmed_by") or None,
        "confirmed_at": raw.get("confirmed_at") or None,
    }


def record_of_unknown_source(source):
    """Whatever we could not read, kept verbatim and treated as unconfirmed."""
    return {"source": None, "from": source, "confidence": None,
            "confirmed_by": None, "confirmed_at": None}


def is_confirmed(raw):
    """
    True when a human here stands behind this value.

    Entering it is standing behind it, so `entered` — including the absent
    provenance that means the same thing — needs no separate confirmation.
    """
    provenance = normalise(raw)
    if provenance is None:
        return True
    return bool(provenance.get("confirmed_by"))


def confirm(raw, person_id, at=None):
    """
    The same record, with this person's name against it.

    Confirming is not the same as retyping: the value still says it was
    suggested or inherited, which is the fact a regulator asks about. Only the
    signature is added.
    """
    provenance = normalise(raw)
    if provenance is None:
        return None
    return {**provenance,
            "confirmed_by": person_id,
            "confirmed_at": at or datetime.now().isoformat()}


def describe(raw):
    """
    The short line shown beside the value. Empty when there is nothing to say.
    """
    provenance = normalise(raw)
    if provenance is None:
        return ""
    source = provenance.get("source")
    origin = provenance.get("from")
    if source == INHERITED:
        text = f"Inherited from {_origin(origin)}" if origin else "Inherited"
    elif source == CITED:
        text = f"Cited from {_origin(origin)}" if origin else "Cited"
    elif source == SUGGESTED:
        text = f"Suggested by {_origin(origin)}" if origin else "Suggested"
        confidence = provenance.get("confidence")
        if confidence is not None:
            text += f" ({round(confidence * 100)}% confidence)"
    else:
        text = "Of unrecorded origin"
    if provenance.get("confirmed_by"):
        text += f", confirmed by {provenance['confirmed_by']}"
    return text


def _origin(origin):
    """A citation's `from` is an [id, version] pair; everything else is a scalar."""
    if isinstance(origin, (list, tuple)) and len(origin) == 2:
        return f"{origin[0]} v{origin[1]}"
    return str(origin)


def by_element(ids, data):
    """
    {element_id: provenance} from the two halves a pattern-matching callback
    hands back — the matched component ids and their store contents.

    Elements with nothing to record are left out entirely, so a form with no
    provenance produces `{}` and every caller downstream behaves as it did
    before this module existed.
    """
    provenances = {}
    for component_id, raw in zip(ids or [], data or []):
        parsed = normalise(raw)
        if parsed is not None and isinstance(component_id, dict):
            provenances[component_id.get("element")] = parsed
    return provenances


def unconfirmed(provenances, element_ids=None):
    """Which of these elements carry a value nobody here has stood behind."""
    candidates = (provenances or {}) if element_ids is None else element_ids
    return {element_id for element_id in candidates
            if not is_confirmed((provenances or {}).get(element_id))}


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
#
# Provenance is stored in a table of its own, one row per
# (record table, record id, record version, element). The record tables have a
# column per element and no home for a record *about* a value, and the two
# alternatives cost more than they save. A `<element>_provenance` column per
# element multiplies the schema and needs a migration every time an element is
# added. A JSON column per record is invisible to SQL and visible to everything
# that does `SELECT *` — the graph's node properties and the spreadsheet grid
# would both start showing a column of raw JSON to deployments that have never
# supplied a provenance, which is exactly the difference they are promised not
# to see.
#
# Keying on the *version* is what makes the usual objection to a side table —
# that it can come to disagree with the row it annotates — not apply. The schema
# is append-only, so a saved row never changes; provenance written against
# (id, version) in the same transaction as that row can never come to describe a
# value that has since moved on. It needs no id or version discipline of its own
# because it borrows the record's.
#
# The columns are the record's five fields rather than a blob, so the question
# this whole mechanism exists to answer stays a query: every value in the
# register nobody has stood behind is `WHERE confirmed_by IS NULL`.

FIELDS = ("source", "origin", "confidence", "confirmed_by", "confirmed_at")


def to_fields(raw):
    """
    A provenance record as the columns it is stored in, or None when there is
    nothing to store.

    None means "entered", and an absent row already says that, so nothing is
    written for a value a human typed. That is what keeps the table empty — and
    every existing deployment untouched — until something supplies a provenance.
    """
    provenance = normalise(raw)
    if provenance is None:
        return None
    return (provenance["source"], _dump(provenance["from"]),
            provenance["confidence"], provenance["confirmed_by"],
            provenance["confirmed_at"])


def from_fields(source, origin, confidence, confirmed_by, confirmed_at):
    """The record those columns came from."""
    origin = _load(origin)
    if source is None:
        # What could not be read when it was stored is still unreadable, and
        # still unconfirmed. Round-tripping it into "a human typed this" is the
        # one outcome this module refuses.
        return record_of_unknown_source(origin)
    return normalise({"source": source, "from": origin, "confidence": confidence,
                      "confirmed_by": confirmed_by, "confirmed_at": confirmed_at})


def _dump(origin):
    """
    `from` is stored JSON-encoded because core does not interpret it: a scope
    id, an `[assessment_id, version]` pair and an analysis run id are not the
    same type, and only one encoding round-trips all three.
    """
    if origin is None:
        return None
    try:
        return json.dumps(origin)
    except (TypeError, ValueError):
        return json.dumps(str(origin))


def _load(origin):
    """A hand-edited row that is not JSON is read as the text it is."""
    if origin is None:
        return None
    try:
        return json.loads(origin)
    except (TypeError, ValueError):
        return origin


_MISSING = object()


def surviving_edits(provenances, previous_values, values):
    """
    The provenances still true of the values about to be saved.

    A value a human has since rewritten was *entered*, whatever the record
    travelling with it on the page still says. Confirming is not retyping, and
    retyping is not confirming: editing a value is how you disown its origin.
    Persistence is what makes this matter — before it, a stale claim died with
    the page; now it would be written into the register as a standing assertion
    that a model wrote prose a person typed.

    Doubt is resolved by *keeping* the provenance. Dropping it asserts "a human
    typed this", which is the claim nothing here may make by accident, so a
    value whose shape cannot be compared exactly keeps what it had.
    """
    previous_values = previous_values or {}
    values = values or {}
    return {element: raw for element, raw in (provenances or {}).items()
            if not _changed(previous_values.get(element, _MISSING),
                            values.get(element))}


def _changed(before, after):
    before, after = _comparable(before), _comparable(after)
    return before is not None and after is not None and before != after


def _comparable(value):
    """
    A value as text, or None when this shape cannot be compared honestly.

    A subform's dict against the JSON string it was stored as, or a checkbox's
    True against the 1 in the column, would differ on their spelling alone — and
    a false difference here quietly claims authorship of someone else's value.
    Prose is where the risk actually lives, and prose compares exactly.
    """
    if value is _MISSING:
        return None
    if value is None:
        return ""
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def annotation(raw):
    """
    Where a value came from, as it reads in an exported report, or "" when there
    is nothing to say.

    Appended to the value rather than gathered into a footnote: a reader who has
    to look elsewhere to learn that nobody stood behind a purpose will read that
    purpose as asserted, and the export is the artefact a regulator is handed.
    """
    text = describe(raw)
    if not text:
        return ""
    if not is_confirmed(raw):
        text += ", not confirmed"
    return f" _[{text}]_"


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

def store_id(form_name, element_id):
    return {"type": "provenance", "form": form_name, "element": element_id}


def confirm_id(form_name, element_id):
    return {"type": "provenance-confirm", "form": form_name, "element": element_id}


def note_id(form_name, element_id):
    return {"type": "provenance-note", "form": form_name, "element": element_id}


def container_id(form_name, element_id):
    return {"type": "provenance-block", "form": form_name, "element": element_id}


def register_provenance_callbacks(app):
    """
    One callback for every confirm control in the app.

    Confirmation is per field rather than per record. A single "confirm
    everything" button would be the fastest way to make the whole mechanism
    meaningless, since the signature it records is meant to mean someone read
    that particular value.

    Registered once with MATCH on both form and element rather than per form:
    unlike relevance, nothing here depends on the form's config, and the
    controls only exist for elements that were rendered with a provenance.
    """
    @app.callback(
        Output(store_id(MATCH, MATCH), "data"),
        Output(note_id(MATCH, MATCH), "children"),
        Output(container_id(MATCH, MATCH), "style"),
        Output(confirm_id(MATCH, MATCH), "style"),
        Input(confirm_id(MATCH, MATCH), "n_clicks"),
        State(store_id(MATCH, MATCH), "data"),
        State("current-person-id", "data"),
        prevent_initial_call=True,
    )
    def confirm_value(n_clicks, current, person_id):
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        return confirmation_for(current, person_id)


def confirmation_for(current, person_id, at=None):
    """
    The callback's whole body, as a plain function so it can be tested without a
    live app: the updated store, the new note, and the two styles that stop the
    value looking provisional.
    """
    # Imported here rather than at module scope: component_factory renders the
    # provenance block and so imports this module.
    from pantograph.component_factory import CONFIRMED_STYLE, HIDDEN_CONTROL, provenance_note

    confirmed = confirm(current, person_id, at)
    return confirmed, provenance_note(confirmed), CONFIRMED_STYLE, HIDDEN_CONTROL
