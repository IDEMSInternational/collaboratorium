"""
editor.py
The contract for asking core to open the editor.

Core hosts one editor and knows nothing about what might want to open it. A page
publishes a request to the shared ``editor-request`` store and core renders it;
that is the whole interface. Before this existed, core's form callbacks took
their inputs straight from ``cyto``, the Explore graph — so core named a plugin's
component, and no other page could open the editor without pretending to be one.

Request shapes::

    {"mode": "edit",    "table": str, "id": int,           "token": ...}
    {"mode": "add",     "table": str, "values": {...},
                        "title": str | None,               "token": ...}
    {"mode": "message", "text": str,                       "token": ...}

`token` makes each request unique to the event that raised it. Pass something
that differs per event; the source event's timestamp is ideal.

It is not load-bearing today: dash-renderer re-dispatches downstream callbacks
when a Store's `data` is reassigned, even to an equal value, so tapping the same
node twice reopens the editor with or without it (verified by breaking the token
and watching test_graph_editor still pass). It is kept because relying on that
is relying on an implementation detail of the renderer, and because a request
that is unique per event is far easier to read in devtools than a stream of
identical ones.

A page whose only affordance is a link — a markdown report, a grid cell —
cannot write to a store, so the same requests can also be spelled as a URL
hash; see `parse_hash`.

`message` is for a page that has decided the thing the user clicked is not
editable and wants to say so in its own words. Core has no better wording to
offer, so it renders the text as given.
"""

STORE_ID = "editor-request"


def _request(mode, token, **fields):
    return {"mode": mode, "token": token, **fields}


def edit_request(table, object_id, token=None):
    """Open the edit form for an existing record."""
    return _request("edit", token, table=table, id=object_id)


def add_request(table, values=None, title=None, token=None):
    """
    Open the add form for a new record.

    `values` pre-populates elements using the same shapes an edit form would
    load, so a links element takes a list of ids. `title` overrides the heading,
    e.g. "Add activity to <initiative>".
    """
    return _request("add", token, table=table, values=values or {}, title=title)


def message_request(text, token=None):
    """Open the editor showing `text` instead of a form."""
    return _request("message", token, text=text)


# --------------------------------------------------------------------------
# The same requests, spelled as a URL
# --------------------------------------------------------------------------

ROUTE_EDIT = "edit"
ROUTE_ADD = "add"
ROUTE_SUGGEST = "suggest"


def suggestion_request(suggestion_id, token=None):
    """
    Open the form for a staged suggestion.

    Deliberately a request carrying only the id: resolving it means reading the
    staging table, and a URL parser that touched the database would be a
    surprising thing to have in this module. Core's form callback resolves it,
    the same way it resolves `edit` by reading the record.
    """
    return _request("suggestion", token, id=suggestion_id)


def parse_hash(url_hash):
    """
    Read an editor request out of a URL hash, or None if the hash isn't one.

    A report is markdown and a grid cell is text, so neither can hold a Dash
    component: the only affordance either has is a link. These routes are what
    such a link means.

    ::

        #edit/<table>/<id>              open that record
        #add/<table>                    open a blank add form
        #add/<table>/<element>/<id>     open an add form already linked

    The third is what makes "add an activity to this initiative" expressible
    from a template. `element` names a links element on the *new* record's own
    form — `initiatives_links` on an activity, `parents` on an initiative — so
    the route says what to link to without naming a link table, a direction or
    a column. Forms config already answers those, and a URL that restated them
    could contradict it.

    Returning None for anything else is also how a caller distinguishes an
    editor route from the hash being cleared, which is why the two callbacks
    that used to test for the substring "edit" now ask this instead.
    """
    if not url_hash or not isinstance(url_hash, str):
        return None
    parts = [p for p in url_hash.strip("#").split("/") if p != ""]
    if not parts:
        return None

    route, rest = parts[0], parts[1:]
    if route == ROUTE_EDIT and len(rest) == 2:
        table, object_id = rest
        object_id = _as_id(object_id)
        if object_id is None:
            return None
        return edit_request(table, object_id, token=url_hash)

    if route == ROUTE_ADD and len(rest) == 1:
        return add_request(rest[0], token=url_hash)

    if route == ROUTE_SUGGEST and len(rest) == 1:
        suggestion_id = _as_id(rest[0])
        if suggestion_id is None:
            return None
        return suggestion_request(suggestion_id, token=url_hash)

    if route == ROUTE_ADD and len(rest) == 3:
        table, element, object_id = rest
        object_id = _as_id(object_id)
        if object_id is None:
            return None
        # A list because that is the shape a links element loads, and the shape
        # the dashboard's own prefills already use. Core narrows it to a scalar
        # if the element it names turns out not to be multi-valued.
        return add_request(table, {element: [object_id]}, token=url_hash)

    return None


def _as_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
