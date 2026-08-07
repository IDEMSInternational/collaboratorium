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
