"""
The Import page's layout and callbacks.

Three regions and three jobs: a box to paste into, the report on what was
pasted, and the queue of what has been staged. The report is the product of the
first step — a file's errors, its warnings and, above all, the records that
probably name something that already exists — so it is built to be read, and
staging is a separate click that comes after it.
"""
import base64

from dash import html, dcc, Input, Output, State, ctx, ALL, no_update
import dash_bootstrap_components as dbc
from flask import session

from pantograph import contract, staging, suggestions
from pantograph.db import get_person_id_for_user

_SEVERITY = {"error": "danger", "warning": "warning", "advisory": "info"}


def generate_layout(config, page_id):
    p = page_id
    return html.Div([
        dcc.Store(id=f"{p}-text"),
        dcc.Store(id=f"{p}-tick", data=0),

        html.H4("Import suggestions"),
        html.P([
            "Paste the YAML your agent produced, or upload the file. Nothing is "
            "saved until you have seen what it would do — and even then a staged "
            "suggestion only becomes a record when you confirm its fields in the "
            "editor. Format ",
            html.Code(suggestions.FORMAT), ". ",
            html.A("Get a handoff bundle", href="/handoff"), "."],
            className="text-muted"),
        dcc.Upload(
            id=f"{p}-upload", multiple=False,
            children=html.Div(["Drop a .yaml file here, or ", html.A("choose one")]),
            style={"border": "1px dashed #adb5bd", "borderRadius": "6px",
                   "padding": "10px", "textAlign": "center", "marginBottom": "10px"}),
        dbc.Textarea(
            id=f"{p}-textarea",
            style={"minHeight": "220px",
                   "fontFamily": "ui-monospace, Consolas, monospace",
                   "fontSize": "0.85em"},
            placeholder=f"format: {suggestions.FORMAT}\nactivities:\n  - name: ..."),
        dbc.Button("Check it", id=f"{p}-check", color="primary", className="mt-2"),

        html.Div(id=f"{p}-report", className="mt-3"),
        html.Div(dbc.Button("Stage for review", id=f"{p}-stage", color="success"),
                 id=f"{p}-stage-wrap", style={"display": "none"}, className="mb-3"),

        html.Hr(),
        html.H4("Review queue"),
        html.Div(id=f"{p}-queue"),
    ], style={"padding": "20px", "maxWidth": "1000px"})


def _findings(items, title):
    if not items:
        return []
    return [html.H6(title, className="mt-3")] + [
        dbc.Alert([html.Code(f.where, className="d-block small"), f.message],
                  color=_SEVERITY[f.severity], className="py-2 mb-2")
        for f in items]


def _plural(n, word):
    return f"{n} {word}{'s' if n != 1 else ''}"


def _report(proposal):
    errors, warnings, advisories = (proposal.errors, proposal.warnings,
                                    proposal.advisories)
    blocked = [r for r in proposal.records if r.blocked]
    counts = []
    if errors:
        counts.append(dbc.Badge(_plural(len(errors), "error"), color="danger",
                                className="me-2"))
    if warnings:
        counts.append(dbc.Badge(_plural(len(warnings), "warning"), color="warning",
                                className="me-2"))
    if advisories:
        counts.append(dbc.Badge(f"{len(advisories)} to look at", color="info",
                                className="me-2"))
    counts.append(dbc.Badge(f"{len(proposal.stageable)} ready", color="success"))

    rows = [html.Tr([
        html.Td(r.table), html.Td(r.action), html.Td(r.name),
        html.Td(", ".join(f"{e.lstrip('@')}: {len(ids)}" for e, ids in r.links.items()),
                className="text-muted"),
        html.Td(", ".join(r.inferred.keys()), className="text-muted"),
    ]) for r in proposal.stageable]

    return html.Div([
        html.H5("Report"), html.P(counts),
        html.P(f"{_plural(len(blocked), 'record')} cannot be staged until the "
               "file is fixed. The rest can be staged now; fixing and "
               "re-uploading will not duplicate them while they carry a "
               "source_ref.") if blocked else None,
        *_findings(errors, "Errors"),
        *_findings(advisories, "Worth a look before you stage"),
        *_findings(warnings, "Warnings"),
        html.H6("What would be staged", className="mt-3"),
        dbc.Table([html.Thead(html.Tr([html.Th(h) for h in
                   ("Table", "Action", "Name", "Links", "Inferred")])),
                   html.Tbody(rows)], size="sm"),
    ])


def _staged(report):
    badges = [dbc.Badge(f"{len(report['staged'])} staged", color="success",
                        className="me-2")]
    for key, word, colour in (("already", "already here", "warning"),
                              ("declined", "previously declined", "warning"),
                              ("grouped", "grouped with a colleague's", "info")):
        if report.get(key):
            badges.append(dbc.Badge(f"{len(report[key])} {word}", color=colour,
                                    className="me-2"))
    return html.Div([html.H5("Staged"), html.P(badges), html.P(
        "Records already staged from an earlier upload were left alone, which is "
        "what makes importing the same file twice harmless.",
        className="text-muted")])


def _row(item, p):
    description = (item["payload"].get("values") or {}).get("description") or ""
    inferred = (item["payload"].get("inferred") or {}).items()
    waiting = item.get("waiting")
    return html.Tr([
        html.Td([html.Strong(item["name"]),
                 html.Div(description[:220] + ("…" if len(description) > 220 else ""),
                          className="text-muted small") if description else None]),
        html.Td([item["table"], html.Br(),
                 html.Span(item["action"], className="text-muted small")]),
        html.Td([item.get("subject") or "—", html.Br(),
                 html.Span(item.get("run_id") or "", className="text-muted small")]),
        html.Td([html.Div([html.Code(e), " ", why], className="small text-muted")
                 for e, why in inferred]),
        html.Td([
            html.Div(["waiting on ", *[html.Code(", ".join(k))
                                       for k in waiting.values()]],
                     className="text-muted small") if waiting else None,
            dbc.Button("Open", id={"type": f"{p}-open", "id": item["id"]},
                       size="sm", color="primary", className="me-1"),
            dbc.Button("Decline", id={"type": f"{p}-decline", "id": item["id"]},
                       size="sm", color="secondary", outline=True),
        ], style={"whiteSpace": "nowrap"}),
    ])


def _queue(p):
    groups, total = staging.review_order()
    if not groups:
        return html.P("Nothing awaiting review.", className="text-muted")
    blocks = [html.P(f"{total} awaiting review. Opening one puts its values in "
                     "the ordinary form, marked as not yet stood behind. Confirm "
                     "the fields you accept and save; that save is what creates "
                     "the record.", className="text-muted")]
    for items in groups.values():
        shared = len(items) > 1
        blocks.append(html.Div([
            html.Div([html.Strong(f"{len(items)} people proposed the same thing"),
                      html.P("These arrived from different evidence, so they could "
                             "not be deduplicated. Keep whichever reads best and "
                             "decline the others. Link lists are added to and never "
                             "replaced, so nobody's contribution is lost.",
                             className="small mb-2")]) if shared else None,
            dbc.Table([html.Thead(html.Tr([html.Th(h) for h in
                       ("Name", "Table", "From", "Inferred", "")])),
                       html.Tbody([_row(i, p) for i in items])], size="sm"),
        ], className="border border-info rounded p-2 mb-3" if shared else ""))
    return blocks


def _checked(config, text):
    return suggestions.check(
        text, contract.build(config), staging.current_names(config),
        staging.pending_rows(), vocabulary=staging.tag_vocabulary(config))


def register_callbacks(app, config, page_id):
    p = page_id

    @app.callback(
        Output(f"{p}-textarea", "value"),
        Input(f"{p}-upload", "contents"),
        prevent_initial_call=True,
    )
    def read_upload(contents):
        if not contents:
            return no_update
        _, _, encoded = contents.partition(",")
        # Always UTF-8, as config.py is: a file written on Windows holding an em
        # dash is undecodable as cp1252 elsewhere.
        return base64.b64decode(encoded).decode("utf-8", errors="replace")

    @app.callback(
        Output(f"{p}-report", "children"),
        Output(f"{p}-stage-wrap", "style"),
        Output(f"{p}-text", "data"),
        Input(f"{p}-check", "n_clicks"),
        State(f"{p}-textarea", "value"),
        prevent_initial_call=True,
    )
    def check(_clicks, text):
        if not text or not text.strip():
            return (dbc.Alert("Nothing to check yet.", color="secondary"),
                    {"display": "none"}, None)
        proposal = _checked(config, text)
        return (_report(proposal),
                {"display": "block" if proposal.stageable else "none"}, text)

    @app.callback(
        Output(f"{p}-report", "children", allow_duplicate=True),
        Output(f"{p}-stage-wrap", "style", allow_duplicate=True),
        Output(f"{p}-text", "data", allow_duplicate=True),
        Output(f"{p}-tick", "data", allow_duplicate=True),
        Input(f"{p}-stage", "n_clicks"),
        State(f"{p}-text", "data"),
        State(f"{p}-tick", "data"),
        prevent_initial_call=True,
    )
    def stage(_clicks, text, tick):
        if not text:
            return no_update, no_update, no_update, no_update
        # Re-checked rather than trusting what the report showed: the queue may
        # have changed between the two clicks, and a colleague's file may now
        # collide with this one.
        report = staging.stage(_checked(config, text),
                               get_person_id_for_user(session.get("user")))
        return _staged(report), {"display": "none"}, None, (tick or 0) + 1

    @app.callback(
        Output(f"{p}-queue", "children"),
        Input("page-store", "data"),
        Input(f"{p}-tick", "data"),
    )
    def render_queue(page, _tick):
        # Not rebuilt while another page is showing: the queue is a query, and
        # a page nobody is looking at does not need to run it.
        if page != p:
            return no_update
        return _queue(p)

    @app.callback(
        Output("url", "hash", allow_duplicate=True),
        Output(f"{p}-tick", "data", allow_duplicate=True),
        Input({"type": f"{p}-open", "id": ALL}, "n_clicks"),
        Input({"type": f"{p}-decline", "id": ALL}, "n_clicks"),
        State(f"{p}-tick", "data"),
        prevent_initial_call=True,
    )
    def act_on_row(_open, _decline, tick):
        trigger = ctx.triggered_id
        # A queue that was just re-rendered fires with n_clicks None.
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            return no_update, no_update
        suggestion_id = trigger["id"]

        if trigger["type"] == f"{p}-decline":
            staging.resolve(suggestion_id, staging.DECLINED,
                            get_person_id_for_user(session.get("user")))
            return no_update, (tick or 0) + 1

        item = staging.get(suggestion_id)
        if not item or item["state"] != staging.PENDING:
            return no_update, (tick or 0) + 1
        # The remembering that lets a successful save mark this suggestion
        # answered; see staging.note_saved.
        session["reviewing_suggestion"] = (suggestion_id, item["table"])
        return f"#suggest/{suggestion_id}", no_update
