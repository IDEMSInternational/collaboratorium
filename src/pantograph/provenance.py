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
"""
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
