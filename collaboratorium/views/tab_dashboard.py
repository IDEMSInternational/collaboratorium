"""
tab_dashboard.py
The Dashboard page: what you've put in, so you notice what you haven't.

Deliberately rigid. Unlike the Explore page this is not driven by the filter
registry or the YAML pipeline — it is a fixed read-only projection, so the
layout is hand-built and the queries live in dashboard_data.py. It never
writes: every action hands off to the existing generic editor or to Explore.
"""
import itertools
from datetime import datetime

from dash import html, dcc, Input, Output, State, ctx, ALL, no_update
import dash_bootstrap_components as dbc

from flask import session

import admin_routes
from auth import login_required
from db import get_dropdown_options
from dashboard_data import (
    activity_detail,
    format_tags,
    initiative_detail,
    initiative_name,
    my_totals,
    new_without_activity,
    person_name,
    quiet_initiatives,
    recently_updated,
    tag_group_definitions,
    near_your_work,
    unlinked_activities,
)
from report_generator import format_subform_data

WINDOW_OPTIONS = [30, 90]
DEFAULT_WINDOW = 90

# The same record legitimately appears more than once on the page: an activity
# linked to three initiatives shows under each, and an initiative can be both in
# the feed and in "Touching your work". Dash silently stops dispatching a
# pattern-matching callback when two components share an id, so every generated
# id carries a unique slot. The counter only has to be unique within a render.
_slot = itertools.count()


def _dash_cfg(config):
    return config.get("dashboard", {}) or {}


def _is_admin():
    """True if the current session belongs to an admin (reuses ADMIN_EMAILS).

    Reads the list off the module at call time so it reflects env/config and can
    be monkeypatched in tests.
    """
    user = session.get("user")
    return bool(user and user.get("email") in admin_routes.ADMIN_EMAILS)


def _view_as_banner(view_as_id):
    name = person_name(view_as_id) or f"person {view_as_id}"
    return html.Div(
        [
            html.Span(f"Viewing as {name}", className="dash-viewas-name"),
            html.Span("read-only", className="dash-viewas-tag"),
        ],
        className="dash-viewas-banner",
    )


# ---------------------------------------------------------
# Small presentational helpers
# ---------------------------------------------------------
def _fmt_date(ts):
    """'2026-06-02T13:46:25' -> '2 Jun'. Falls back to raw text."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts).replace(" ", "T").split(".")[0])
    except (ValueError, TypeError):
        return str(ts)[:10]
    # Built by hand rather than strftime("%-d"), which is not portable to Windows.
    if dt.year != datetime.now().year:
        return f"{dt.day} {dt.strftime('%b')} {dt.year}"
    return f"{dt.day} {dt.strftime('%b')}"


def _initials(name):
    if not name:
        return "?"
    parts = [p for p in str(name).replace("_", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar(name):
    """A face is provenance, never a score. Unattributed rows stay graceful."""
    if not name:
        return html.Span("—", className="dash-avatar dash-avatar-none", title="Unattributed")
    return html.Span(_initials(name), className="dash-avatar", title=str(name))


def _chip(kind):
    return html.Span(kind.title(), className=f"dash-chip dash-chip-{kind}")


def _entity_link(kind, entity_id, name, className="dash-entity-link"):
    """Opens the detail card. Used for feed rows and for links inside a card."""
    return html.A(
        name or f"{kind[:-1].title()} {entity_id}",
        id={
            "type": "dash-open",
            "kind": kind,
            "index": int(entity_id),
            "slot": next(_slot),
        },
        className=className,
        n_clicks=0,
        href="#",
    )


def _initiative_link(initiative_id, name):
    return _entity_link("initiatives", initiative_id, name)


def _activity_link(activity_id, name):
    return _entity_link("activities", activity_id, name, className="dash-entity-link dash-ev-name")


def _panel(title, count=None, children=None, subtitle=None, header_extra=None):
    header = [html.Span(title)]
    if header_extra is not None:
        header.append(html.Span(className="dash-spacer"))
        header.append(header_extra)
    if count is not None:
        header.append(html.Span(str(count), className="dash-count"))
    body = []
    if subtitle:
        body.append(html.P(subtitle, className="dash-panel-sub"))
    body.extend(children or [])
    return html.Div(
        [html.Div(header, className="dash-panel-h"), html.Div(body)],
        className="dash-panel",
    )


def _empty(message):
    return html.P(message, className="dash-empty")


# ---------------------------------------------------------
# Section renderers
# ---------------------------------------------------------
def _render_recent(initiatives, scope, person_id=None, read_only=False):
    if not initiatives:
        if scope == "mine":
            actions = []
            if not read_only:
                actions.append(
                    dbc.Button(
                        "Add an activity",
                        id={"type": "dash-empty-add-activity", "slot": next(_slot)},
                        className="dash-mini dash-mini-go",
                        n_clicks=0,
                    )
                )
            actions.append(
                dbc.Button(
                    "See the whole organisation",
                    id={"type": "dash-empty-everyone", "slot": next(_slot)},
                    className="dash-mini",
                    n_clicks=0,
                )
            )
            body = [
                _empty(
                    "Nothing of yours was recorded in this window. Record what "
                    "you've been working on, or look at the whole organisation."
                ),
                html.Div(actions, className="dash-empty-actions"),
            ]
        else:
            body = [
                _empty(
                    "Nothing was recorded across the organisation in this window. "
                    "Try a longer one."
                )
            ]
        return _panel("Recently updated", children=body)

    rows = []
    for i in initiatives:
        events = []
        for e in i["events"]:
            events.append(
                html.Div(
                    [
                        _chip("activity"),
                        _activity_link(e["activity_id"], e["activity_name"]),
                        html.Span(className="dash-spacer"),
                        _avatar(e.get("actor_name")),
                        html.Span(e["verb"], className="dash-verb"),
                        html.Span(_fmt_date(e["timestamp"]), className="dash-ts"),
                    ],
                    className="dash-ev",
                )
            )

        count = i["activity_count"]
        activities = f"{count} {'activity' if count == 1 else 'activities'}"
        # "You're responsible" only when you actually are — an initiative can be
        # in Mine because you're on one of its activities, not because you own it.
        if person_id is not None and i["responsible_person"] == person_id:
            sub = f"You're responsible · {activities}"
        elif i["responsible_name"]:
            sub = f"{i['responsible_name']} responsible · {activities}"
        else:
            sub = f"No one responsible yet · {activities}"

        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            _chip("initiative"),
                            _initiative_link(i["id"], i["name"]),
                            html.Span(className="dash-spacer"),
                            html.Span(_fmt_date(i["last_touched"]), className="dash-ts"),
                        ],
                        className="dash-repo-h",
                    ),
                    html.P(sub, className="dash-repo-sub"),
                    html.Div(events, className="dash-ev-list") if events else None,
                ],
                className="dash-repo",
            )
        )

    label = f"{len(initiatives)} initiatives" if len(initiatives) != 1 else "1 initiative"
    return _panel("Recently updated", count=label, children=rows)


def _near_row(t, read_only):
    why = [html.Span(["on ", _initiative_link(t["initiative_id"], t["initiative_name"])])]
    if not read_only:
        why.append(html.Span(className="dash-spacer"))
        why.append(
            dbc.Button(
                # Ellipsis: this opens the activity's form to add yourself,
                # rather than adding you in one click.
                "Add yourself…",
                id={"type": "dash-add-self", "index": int(t["activity_id"]), "slot": next(_slot)},
                className="dash-mini",
                n_clicks=0,
            )
        )
    return html.Div(
        [
            html.Div(
                [
                    _chip("activity"),
                    _activity_link(t["activity_id"], t["activity_name"]),
                    html.Span(className="dash-spacer"),
                    _avatar(t.get("actor_name")),
                    html.Span("linked", className="dash-verb"),
                    html.Span(_fmt_date(t["timestamp"]), className="dash-ts"),
                ],
                className="dash-touch-h",
            ),
            html.Div(why, className="dash-touch-why"),
        ],
        className="dash-touch",
    )


def _render_near_your_work(owned, involved, expanded, read_only=False):
    """
    Owned rows (initiatives you're responsible for) show by default. The
    involved-in rows — work near activities you've contributed to but don't own —
    sit behind a per-person toggle so one incidental link can't flood the section
    with a busy initiative's whole history.
    """
    if not owned and not involved:
        return None

    subtitle = (
        "Someone else recorded something on an initiative you own or have "
        "worked on, that you're not linked to. You may have been part of it."
    )

    # Nothing on your own initiatives, but there's activity near work you've
    # contributed to: a compact prompt rather than an empty-looking section.
    if not owned and not expanded:
        return html.Div(
            [
                html.Span(f"{len(involved)} updates near work you've contributed to"),
                html.Span(className="dash-spacer"),
                dbc.Button(
                    "Show",
                    id={"type": "dash-near-toggle", "action": "expand"},
                    className="dash-mini",
                    n_clicks=0,
                ),
            ],
            className="dash-hidden-chip",
        )

    rows = [_near_row(t, read_only) for t in owned]
    if expanded:
        rows.extend(_near_row(t, read_only) for t in involved)
        if involved:
            rows.append(
                html.Div(
                    dbc.Button(
                        "Show less",
                        id={"type": "dash-near-toggle", "action": "collapse"},
                        className="dash-mini",
                        n_clicks=0,
                    ),
                    className="dash-near-more",
                )
            )
    elif involved:
        rows.append(
            html.Div(
                dbc.Button(
                    f"Show {len(involved)} more from initiatives you've contributed to",
                    id={"type": "dash-near-toggle", "action": "expand"},
                    className="dash-mini",
                    n_clicks=0,
                ),
                className="dash-near-more",
            )
        )

    shown = len(owned) + (len(involved) if expanded else 0)
    return _panel("Near Your Work", count=shown, subtitle=subtitle, children=rows)


def _render_new(items, scope, read_only=False):
    if not items:
        return None
    rows = []
    for r in items:
        if scope == "mine":
            meta = [html.Span(f"created {_fmt_date(r['created_at'])}", className="dash-ts")]
        elif r["responsible_name"]:
            meta = [
                _avatar(r["responsible_name"]),
                html.Span(r["responsible_name"]),
                html.Span(_fmt_date(r["created_at"]), className="dash-ts"),
            ]
        else:
            meta = [html.Span("no one responsible yet", className="dash-ts")]
        if not read_only:
            meta.append(html.Span(className="dash-spacer"))
            meta.append(
                dbc.Button(
                    "Add activity",
                    id={"type": "dash-add-activity", "index": int(r["id"]), "slot": next(_slot)},
                    className="dash-mini dash-mini-go",
                    n_clicks=0,
                )
            )
        rows.append(
            html.Div(
                [
                    html.P(_initiative_link(r["id"], r["name"]), className="dash-item-n"),
                    html.Div(meta, className="dash-item-m"),
                ],
                className="dash-item dash-invite",
            )
        )
    return _panel("New — no activity yet", count=len(items), children=rows)


def _render_quiet(items, hidden, read_only=False):
    """Mine only, and switchable — hiding it is never a one-way door."""
    if hidden:
        return html.Div(
            [
                html.Span("Nothing recorded in a while · hidden"),
                html.Span(className="dash-spacer"),
                dbc.Button(
                    "Show",
                    id={"type": "dash-quiet-toggle", "action": "show"},
                    className="dash-mini",
                    n_clicks=0,
                ),
            ],
            className="dash-hidden-chip",
        )
    if not items:
        return None

    rows = []
    for r in items:
        meta = [
            html.Span(f"nothing since {_fmt_date(r['created_at'])}", className="dash-ts"),
        ]
        if not read_only:
            meta.append(html.Span(className="dash-spacer"))
            meta.append(
                dbc.Button(
                    "Add activity",
                    id={"type": "dash-add-activity", "index": int(r["id"]), "slot": next(_slot)},
                    className="dash-mini",
                    n_clicks=0,
                )
            )
        rows.append(
            html.Div(
                [
                    html.P(_initiative_link(r["id"], r["name"]), className="dash-item-n"),
                    html.Div(meta, className="dash-item-m"),
                ],
                className="dash-item",
            )
        )
    # The hide toggle is a personal preference, so it only makes sense on your own
    # page — not while viewing someone else's read-only.
    hide_btn = None if read_only else dbc.Button(
        "✕",
        id={"type": "dash-quiet-toggle", "action": "hide"},
        className="dash-hide-x",
        title="Hide this section",
        n_clicks=0,
    )
    return _panel(
        "Nothing recorded in a while",
        count=len(items),
        subtitle="Only ever your own. Never shown on Everyone.",
        children=rows,
        header_extra=hide_btn,
    )


def _render_unlinked(items, read_only=False):
    if not items:
        return None
    rows = []
    for a in items:
        meta = [_chip("activity")]
        if not read_only:
            meta.append(html.Span(className="dash-spacer"))
            meta.append(
                dbc.Button(
                    "Link an initiative",
                    id={"type": "dash-link-initiative", "index": int(a["id"]), "slot": next(_slot)},
                    className="dash-mini",
                    n_clicks=0,
                )
            )
        rows.append(
            html.Div(
                [
                    html.P(_activity_link(a["id"], a["name"]), className="dash-item-n"),
                    html.Div(meta, className="dash-item-m"),
                ],
                className="dash-item",
            )
        )
    return _panel("Not linked to an initiative", count=len(items), children=rows)


# ---------------------------------------------------------
# Detail card
# ---------------------------------------------------------
def _facts(pairs):
    """A definition list of the fields that have a value; blanks stay off the card."""
    rows = []
    for label, value in pairs:
        if value in (None, "", "None"):
            continue
        rows.append(
            html.Div(
                [
                    html.Span(label, className="dash-fact-k"),
                    html.Span(value, className="dash-fact-v"),
                ],
                className="dash-fact",
            )
        )
    return html.Div(rows, className="dash-facts") if rows else None


def _prose(raw):
    """Descriptions may hold subform JSON, so reuse the report's formatter."""
    if raw in (None, ""):
        return None
    text = format_subform_data(raw)
    if not str(text).strip():
        return None
    return dcc.Markdown(str(text), className="dash-prose", link_target="_blank")


def _tag_chips(raw, defs):
    tags = format_tags(raw, defs)
    if not tags:
        return None
    chips = []
    for label, text in tags:
        chips.append(
            html.Span(
                [html.Span(f"{label}: ", className="dash-tag-k") if label else None, text],
                className="dash-tag",
            )
        )
    return html.Div(chips, className="dash-tags")


def _linked_list(title, items, kind):
    if not items:
        return None
    return html.Div(
        [
            html.P(title, className="dash-card-sec"),
            html.Div(
                [
                    html.Div(_entity_link(kind, r["id"], r["name"]), className="dash-linked-row")
                    for r in items
                ],
                className="dash-linked",
            ),
        ]
    )


def _people_list(title, items):
    if not items:
        return None
    return html.Div(
        [
            html.P(title, className="dash-card-sec"),
            html.Div(
                [
                    html.Span(
                        [_avatar(r["name"]), html.Span(r["name"], className="dash-person-n")],
                        className="dash-person",
                    )
                    for r in items
                ],
                className="dash-people",
            ),
        ]
    )


def _card_footer(kind, entity_id, read_only=False):
    # Open in Explore is read-only navigation, so it stays even while impersonating;
    # the write affordances (Add activity, Edit) drop out.
    buttons = []
    if not read_only:
        if kind == "initiatives":
            # Reading an initiative is exactly when you notice work you never entered.
            buttons.append(
                dbc.Button(
                    "Add activity",
                    id={"type": "dash-add-activity", "index": int(entity_id), "slot": next(_slot)},
                    className="dash-mini dash-mini-go me-2",
                    n_clicks=0,
                )
            )
        buttons.append(
            dbc.Button(
                "Edit",
                id={"type": "dash-card-edit", "kind": kind, "index": int(entity_id)},
                className="dash-mini",
                n_clicks=0,
            )
        )
    return buttons + [
        dbc.Button(
            "Open in Explore →",
            id={"type": "dash-card-explore", "kind": kind, "index": int(entity_id)},
            className="dash-mini dash-mini-go ms-2",
            n_clicks=0,
        ),
    ]


def _render_initiative_card(detail, defs):
    body = [
        _facts(
            [
                ("Responsible", detail["responsible_name"] or "No one yet"),
                ("Status", (detail["status"] or "").title()),
                ("Activities", str(len(detail["activities"]))),
                ("Created", _fmt_date(detail["created_at"])),
                ("Last updated", _fmt_date(detail["last_updated"])),
                ("Entered by", detail["creator_name"]),
            ]
        ),
        _tag_chips(detail["tag_groups"], defs),
        _prose(detail["description"]),
        _linked_list("Activities", detail["activities"], "activities"),
        _linked_list(
            "Related initiatives",
            [r for r in detail["related"]],
            "initiatives",
        ),
        _people_list("People involved", detail["people"]),
    ]
    return [c for c in body if c is not None]


def _render_activity_card(detail, defs):
    dates = None
    if detail["start_date"] and detail["end_date"]:
        dates = f"{_fmt_date(detail['start_date'])} – {_fmt_date(detail['end_date'])}"
    elif detail["start_date"] or detail["end_date"]:
        dates = _fmt_date(detail["start_date"] or detail["end_date"])

    body = [
        _facts(
            [
                ("When", dates),
                ("Location", detail["location"]),
                ("Status", (detail["status"] or "").title()),
                ("Created", _fmt_date(detail["created_at"])),
                ("Last updated", _fmt_date(detail["last_updated"])),
                ("Entered by", detail["creator_name"]),
            ]
        ),
        _tag_chips(detail["tag_groups"], defs),
        _prose(detail["description"]),
        _linked_list("Part of", detail["initiatives"], "initiatives"),
        _people_list("People involved", detail["people"]),
    ]
    return [c for c in body if c is not None]


def _render_card(kind, entity_id, read_only=False):
    defs = tag_group_definitions()
    if kind == "initiatives":
        detail = initiative_detail(entity_id)
        if not detail:
            return "Not found", [_empty("That initiative no longer exists.")], []
        return (
            html.Div([_chip("initiative"), html.Span(detail["name"], className="dash-card-t")],
                     className="dash-card-h"),
            _render_initiative_card(detail, defs),
            _card_footer(kind, entity_id, read_only),
        )

    detail = activity_detail(entity_id)
    if not detail:
        return "Not found", [_empty("That activity no longer exists.")], []
    return (
        html.Div([_chip("activity"), html.Span(detail["name"], className="dash-card-t")],
                 className="dash-card-h"),
        _render_activity_card(detail, defs),
        _card_footer(kind, entity_id, read_only),
    )


# ---------------------------------------------------------
# Layout
# ---------------------------------------------------------
def generate_dashboard_layout(config):
    cfg = _dash_cfg(config)
    default_window = cfg.get("default_window_days", DEFAULT_WINDOW)
    windows = cfg.get("window_options_days", WINDOW_OPTIONS)

    return html.Div(
        [
            dcc.Store(id="dashboard-scope", data="mine"),
            dcc.Store(id="dashboard-window", data=default_window),
            # Per-person override for the quiet box. localStorage keeps it out of
            # the schema entirely — there is no preferences table to add to.
            dcc.Store(id="dashboard-hide-quiet", storage_type="local"),
            # Whether "Near Your Work" is expanded to include initiatives you're
            # involved in but don't own. Per-person, remembered in the browser.
            dcc.Store(id="dashboard-near-expanded", storage_type="local"),
            # Admin "view as": whose dashboard is being shown. None = yourself.
            dcc.Store(id="view-as-person", data=None),
            # Admin-only control. Hidden by default; a callback reveals and fills
            # it only for an admin session (ADMIN_EMAILS), mirroring show_login_area.
            html.Div(
                dcc.Dropdown(
                    id="view-as-pick",
                    options=[],
                    value=None,
                    placeholder="View as… (admin)",
                    className="dash-view-as-pick",
                ),
                id="view-as-container",
                style={"display": "none"},
            ),
            html.Div(id="view-as-banner"),
            html.Div(
                [
                    html.Div(
                        [
                            dbc.Button(
                                "Mine",
                                id="dash-scope-mine",
                                n_clicks=0,
                                className="dash-toggle-btn active",
                            ),
                            dbc.Button(
                                "Everyone",
                                id="dash-scope-everyone",
                                n_clicks=0,
                                className="dash-toggle-btn",
                            ),
                        ],
                        className="dash-toggle",
                    ),
                    dcc.Dropdown(
                        id="dash-window-pick",
                        options=[{"label": f"Last {d} days", "value": d} for d in windows],
                        value=default_window,
                        clearable=False,
                        className="dash-window-pick",
                    ),
                    html.Span(className="dash-spacer"),
                    html.Span(id="dash-header-note", className="dash-ts"),
                ],
                className="dash-ctrl-row",
            ),
            dcc.Loading(html.Div(id="dashboard-body"), type="default"),
            # Read-only inspector. Writing stays with the generic editor, which
            # the Edit button opens.
            dcc.Store(id="dashboard-detail", data=None),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle(html.Div(id="dash-card-header"))),
                    dbc.ModalBody(html.Div(id="dash-card-body")),
                    dbc.ModalFooter(
                        [
                            html.Div(id="dash-card-footer", className="dash-card-footer"),
                            # Static, not part of the rendered footer: a plain-id
                            # Input must exist in the layout tree or its callback
                            # never fires.
                            dbc.Button(
                                "Close", id="dash-card-close", className="dash-mini", n_clicks=0
                            ),
                        ]
                    ),
                ],
                id="dashboard-detail-modal",
                is_open=False,
                size="lg",
                scrollable=True,
            ),
        ],
        id="dashboard-page",
    )


# ---------------------------------------------------------
# Callbacks
# ---------------------------------------------------------
def register_dashboard_callbacks(app, config):
    cfg = _dash_cfg(config)
    # Deployment-level default; a person can still switch it on their own page
    # unless the deployment has turned the section off entirely.
    quiet_enabled = cfg.get("show_quiet_box", True)

    @app.callback(
        Output("dashboard-scope", "data"),
        Output("dash-scope-mine", "className"),
        Output("dash-scope-everyone", "className"),
        Input("dash-scope-mine", "n_clicks"),
        Input("dash-scope-everyone", "n_clicks"),
        Input({"type": "dash-empty-everyone", "slot": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_scope(_mine, _everyone, empty_everyone):
        trigger = ctx.triggered_id
        to_everyone = trigger == "dash-scope-everyone" or (
            isinstance(trigger, dict) and trigger.get("type") == "dash-empty-everyone"
        )
        # The empty-state button shares the pattern-matching quirk: ignore the
        # render-time firing where no click has actually happened.
        if isinstance(trigger, dict) and not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update
        scope = "everyone" if to_everyone else "mine"
        on, off = "dash-toggle-btn active", "dash-toggle-btn"
        return scope, (off if scope == "everyone" else on), (on if scope == "everyone" else off)

    @app.callback(
        Output("dashboard-window", "data"),
        Input("dash-window-pick", "value"),
        prevent_initial_call=True,
    )
    def set_window(value):
        return value or DEFAULT_WINDOW

    @app.callback(
        Output("dashboard-hide-quiet", "data"),
        Input({"type": "dash-quiet-toggle", "action": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_quiet(clicks):
        if not any(c for c in clicks if c):
            return no_update
        trigger = ctx.triggered_id
        if not trigger:
            return no_update
        return trigger.get("action") == "hide"

    @app.callback(
        Output("dashboard-near-expanded", "data"),
        Input({"type": "dash-near-toggle", "action": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_near_expanded(clicks):
        if not any(c for c in clicks if c):
            return no_update
        trigger = ctx.triggered_id
        if not trigger:
            return no_update
        return trigger.get("action") == "expand"

    @app.callback(
        Output("view-as-container", "style"),
        Output("view-as-pick", "options"),
        Input("current-person-id", "data"),
    )
    def reveal_view_as(_ready):
        """Show the 'View as' control and its people list only for an admin."""
        if not _is_admin():
            return {"display": "none"}, []
        return {"display": "inline-block"}, get_dropdown_options("people", "id", "name") or []

    @app.callback(
        Output("view-as-person", "data"),
        Input("view-as-pick", "value"),
        prevent_initial_call=True,
    )
    def set_view_as(value):
        # Ignored server-side for non-admins (see render_dashboard), but don't even
        # record it unless the session is an admin.
        if not _is_admin():
            return None
        return value or None

    @app.callback(
        Output("btn-add-activity", "style"),
        Output("btn-add-initiative", "style"),
        Output("btn-add-element", "style"),
        Input("view-as-person", "data"),
    )
    def hide_add_buttons_when_impersonating(view_as):
        """The global add buttons write, so remove them while viewing as someone."""
        hidden = {"display": "none"} if (view_as and _is_admin()) else None
        return hidden, hidden, hidden

    @app.callback(
        Output("dashboard-body", "children"),
        Output("dash-header-note", "children"),
        Output("view-as-banner", "children"),
        Input("dashboard-scope", "data"),
        Input("dashboard-window", "data"),
        Input("dashboard-hide-quiet", "data"),
        Input("dashboard-near-expanded", "data"),
        Input("current-person-id", "data"),
        Input("view-as-person", "data"),
        Input("form-refresh", "data"),
        Input("page-store", "data"),
    )
    @login_required
    def render_dashboard(scope, window, hide_quiet, near_expanded, person_id, view_as, _refresh, page):
        if page != "dashboard":
            return no_update, no_update, no_update

        scope = scope or "mine"
        window = window or DEFAULT_WINDOW

        # "View as" is honoured only for an admin session; otherwise it's ignored,
        # so a crafted store value can't impersonate. Impersonation is read-only.
        read_only = bool(view_as) and _is_admin()
        effective_id = view_as if read_only else person_id
        banner = _view_as_banner(view_as) if read_only else None

        if scope == "mine" and not effective_id:
            return (
                html.Div(
                    _panel(
                        "Recently updated",
                        children=[
                            _empty(
                                "We couldn't match your login to a person record yet. "
                                "Switch to Everyone to see what's happening across the organisation."
                            )
                        ],
                    )
                ),
                "",
                banner,
            )

        recent = recently_updated(effective_id, window, scope)
        new_items = new_without_activity(effective_id, window, scope)

        left = [_render_recent(recent, scope, effective_id, read_only)]
        right = [_render_new(new_items, scope, read_only)]

        if scope == "mine":
            # Sections that need a "you" only exist on Mine. Showing the quiet
            # box for everyone would make it a report on other people.
            near = near_your_work(effective_id, window)
            near_owned = [r for r in near if r["owned"]]
            near_involved = [r for r in near if not r["owned"]]
            left.append(
                _render_near_your_work(near_owned, near_involved, bool(near_expanded), read_only)
            )
            if quiet_enabled:
                right.append(
                    _render_quiet(quiet_initiatives(effective_id, window), hide_quiet, read_only)
                )
            right.append(_render_unlinked(unlinked_activities(effective_id), read_only))
            totals = my_totals(effective_id)
            note = f"{totals['initiatives']} initiatives, {totals['activities']} activities"
        else:
            note = "everything across the organisation"

        body = dbc.Row(
            [
                dbc.Col(html.Div([c for c in left if c], className="dash-stack"), lg=8, md=12),
                dbc.Col(html.Div([c for c in right if c], className="dash-stack"), lg=4, md=12),
            ],
            className="g-3",
        )
        return body, note, banner

    # -----------------------------------------------------
    # Detail card
    # -----------------------------------------------------
    @app.callback(
        Output("dashboard-detail", "data"),
        Output("dashboard-detail-modal", "is_open"),
        Input({"type": "dash-open", "kind": ALL, "index": ALL, "slot": ALL}, "n_clicks"),
        Input("dash-card-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_card(entity_clicks, _close):
        trigger = ctx.triggered_id
        if trigger == "dash-card-close":
            return no_update, False
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            return no_update, no_update
        return {"kind": trigger["kind"], "id": trigger["index"]}, True

    @app.callback(
        Output("dash-card-header", "children"),
        Output("dash-card-body", "children"),
        Output("dash-card-footer", "children"),
        Input("dashboard-detail", "data"),
        State("view-as-person", "data"),
        prevent_initial_call=True,
    )
    def render_card(detail, view_as):
        if not detail:
            return no_update, no_update, no_update
        # Same rule as the page: hide write affordances while impersonating.
        read_only = bool(view_as) and _is_admin()
        return _render_card(detail["kind"], detail["id"], read_only)

    # -----------------------------------------------------
    # Handoffs — the dashboard never edits anything itself
    # -----------------------------------------------------
    @app.callback(
        Output("filter-target-entity", "value", allow_duplicate=True),
        Output("page-store", "data", allow_duplicate=True),
        Output("output-tabs", "active_tab", allow_duplicate=True),
        Output("dashboard-detail-modal", "is_open", allow_duplicate=True),
        Input({"type": "dash-card-explore", "kind": ALL, "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def goto_explore(clicks):
        """Re-centre Explore's existing ego-graph on whatever the card is showing."""
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update
        return [f"{trigger['kind']}-{trigger['index']}"], "explore", "tab-graph", False

    @app.callback(
        Output("url", "hash", allow_duplicate=True),
        Output("dashboard-detail-modal", "is_open", allow_duplicate=True),
        Input({"type": "dash-card-edit", "kind": ALL, "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def edit_from_card(clicks):
        """Hand the record to the existing generic editor via its #edit route."""
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            return no_update, no_update
        return f"#edit/{trigger['kind']}/{trigger['index']}", False

    @app.callback(
        Output("table-selector", "value", allow_duplicate=True),
        Output("form-prefill", "data", allow_duplicate=True),
        Output("add-dropdown-container", "style", allow_duplicate=True),
        Output("dashboard-detail-modal", "is_open", allow_duplicate=True),
        Input({"type": "dash-add-activity", "index": ALL, "slot": ALL}, "n_clicks"),
        Input("btn-add-activity", "n_clicks"),
        Input("btn-add-initiative", "n_clicks"),
        Input({"type": "dash-empty-add-activity", "slot": ALL}, "n_clicks"),
        State("current-person-id", "data"),
        prevent_initial_call=True,
    )
    def add_from_dashboard(add_activity_for, _activity, _initiative, _empty_add, person_id):
        """
        Open the generic add form for a new record.

        From an initiative, the new activity arrives already linked to it, which
        is why this is "Add activity" rather than a link form: creating the work
        you just did is the common case, and the link comes free. When you're
        adding an activity we also link you to it up front — recording your own
        work is the whole purpose of the page, so you shouldn't have to find your
        own name in a dropdown every time.

        The prefill carries the editor title; set_editor_title renders it.
        """
        trigger = ctx.triggered_id
        if not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update

        hide_dropdown = {"display": "none"}

        def activity_prefill(initiative_id=None):
            values = {}
            title = "Add activity"
            if initiative_id is not None:
                values["initiatives_links"] = [initiative_id]
                name = initiative_name(initiative_id)
                if name:
                    title = f"Add activity to {name}"
            if person_id is not None:
                values["people_links"] = [person_id]
            return {"table": "activities", "values": values, "title": title}

        kind = trigger.get("type") if isinstance(trigger, dict) else trigger
        if kind in ("btn-add-activity", "dash-empty-add-activity"):
            return "activities", activity_prefill(), hide_dropdown, no_update
        if kind == "btn-add-initiative":
            return "initiatives", {"table": "initiatives", "values": {}, "title": "Add initiative"}, hide_dropdown, no_update
        if kind == "dash-add-activity":
            return "activities", activity_prefill(trigger["index"]), hide_dropdown, False
        return no_update, no_update, no_update, no_update

    @app.callback(
        Output("url", "hash", allow_duplicate=True),
        Output("dashboard-detail-modal", "is_open", allow_duplicate=True),
        Input({"type": "dash-link-initiative", "index": ALL, "slot": ALL}, "n_clicks"),
        Input({"type": "dash-add-self", "index": ALL, "slot": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def edit_activity_links(link_initiative, add_self):
        """
        Both of these amend an existing activity, so open that activity's own
        form: it already carries Linked Initiatives and Linked People.
        """
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not ctx.triggered[0]["value"]:
            return no_update, no_update
        return f"#edit/activities/{trigger['index']}", False

    @app.callback(
        Output("form-prefill", "data", allow_duplicate=True),
        Input("editor-popup", "is_open"),
        prevent_initial_call=True,
    )
    def clear_prefill_on_close(is_open):
        """A prefill request lasts exactly as long as the editor it opened."""
        if is_open:
            return no_update
        return None
