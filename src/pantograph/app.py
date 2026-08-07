"""
app.py
Assembles the Dash application from a config file and the plugins it names.

Core's job here is deliberately small: mount the shared stores, build the nav
and the page containers from the plugin list, host the editor, and let each
plugin register its own callbacks. Nothing in this module names a table, a page
or a plugin.
"""
from dash import Dash, html, dcc, Input, Output, ctx, no_update
import dash_bootstrap_components as dbc

from pantograph.admin_routes import register_admin_routes
from pantograph.analytics import init_db as analytics_init_db
from pantograph.auth import server, register_auth_callbacks
from pantograph.config import load_config
from pantograph.db import init_db
from pantograph.editor import STORE_ID as EDITOR_REQUEST_STORE
from pantograph.form_gen import register_form_callbacks
from pantograph.plugins import load_plugins
from pantograph.settings import get_settings
from pantograph.tools.analysis_report import init_analytics_app

# Stores that are core contract: plugins may read and write these by name, and
# core guarantees they exist. Everything else a plugin needs is private to it
# and comes from its own Plugin.stores().
#
#   current-person-id    the signed-in user's person record
#   form-refresh         bumped after a successful submit
#   form-prefill         a page asking for an add-form with fields filled in
#   editor-request       a page asking core to open the editor (see editor.py)
#   intermediary-loaded  bumped when the underlying data changed
#   page-store           the active plugin id; writable, so a page can navigate
CORE_STORES = [
    dcc.Store(id="current-person-id", data=None),
    dcc.Store(id="form-refresh", data=False),
    dcc.Store(id="form-prefill", data=None),
    dcc.Store(id=EDITOR_REQUEST_STORE, data=None),
    dcc.Store(id="intermediary-loaded", data=False),
]


def _editor_contents(config):
    return html.Div([
        html.Div([
            html.Label("Add: "),
            dcc.Dropdown(
                id="table-selector",
                options=[{"label": t, "value": t} for t in config["tables"].keys()],
                placeholder="Add new element...",
                style={"width": "100%", "marginBottom": "15px"},
            ),
        ], id="add-dropdown-container"),
        html.Div(id="form-container"),
        html.Div(id="out_msg", children=[], className="mt-3"),
    ])


def _header(config, plugins):
    """Title, plugin nav, and the plugins' own header items."""
    nav_buttons = [
        dbc.Button(
            p.label,
            id=f"nav-{p.id}",
            n_clicks=0,
            className="nav-page-btn me-1",
        )
        for p in plugins
    ]

    # A plugin may contribute header controls — the quick-add buttons, for
    # instance, belong to whichever page wires them up, not to core.
    plugin_items = []
    for p in plugins:
        plugin_items.extend(p.header_items(config))

    return dbc.Row([
        dbc.Col(html.H2(config["title"], className="mb-4"), width=3),
        dbc.Col(nav_buttons, width=3, className="text-center"),
        dbc.Col(
            plugin_items + [
                # The catch-all "add anything" entry point is core: it is the
                # only one that works for an arbitrary schema.
                dbc.Button("Add other…", id="btn-add-element", color="link", size="sm",
                           className="me-3 text-secondary"),
                html.Div(id="login-area", style={"display": "inline-block"}),
            ],
            width=6, className="text-end",
        ),
    ])


def create_app(settings=None):
    """
    Build the Dash app. Reads paths from :mod:`pantograph.settings`, so a caller
    (a test, a CLI) configures those first and this stays free of import-time
    side effects.
    """
    settings = settings or get_settings()
    config = load_config(settings.config_path)

    init_db(config)
    analytics_init_db()
    init_analytics_app(server)

    plugins, landing_id = load_plugins(config)

    app = Dash(
        config["title"],
        title=config["title"],
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        server=server,
        suppress_callback_exceptions=True,
        assets_folder=str(settings.assets_path.resolve()),
        assets_url_path="assets",
    )
    app._favicon = "cropped-IDEMS_logomark_with_border_circle-32x32.png"

    editor_contents = _editor_contents(config)
    editor_layout_type = config.get("editor_layout", "modal")

    page_containers = [
        html.Div(
            p.layout(config),
            id=f"{p.id}-container",
            style={"display": "block"} if p.id == landing_id else {"display": "none"},
        )
        for p in plugins
    ]

    if editor_layout_type == "modal":
        editor_container = dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Editor")),
            dbc.ModalBody(editor_contents),
        ], id="editor-popup", is_open=False, size="xl")
        body = page_containers + [editor_container]
    elif editor_layout_type == "sidebar":
        editor_container = dbc.Offcanvas(
            [editor_contents], id="editor-popup", title="Editor",
            is_open=False, placement="end",
        )
        body = page_containers + [editor_container]
    else:
        # Legacy inline layout: the editor sits permanently beside the pages.
        # Previously this 8/4 split wrapped the Explore page only, so on any
        # other page the editor column vanished; it now applies to every page,
        # which is the behaviour the setting describes.
        body = [
            html.Div(id="editor-popup", style={"display": "none"}),
            dbc.Row([
                dbc.Col(page_containers, width=8),
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H4("Editor", className="m-0")),
                    dbc.CardBody(editor_contents),
                ]), width=4),
            ]),
        ]

    plugin_stores = [s for p in plugins for s in p.stores()]

    app.layout = html.Div([
        dcc.Location(id="url", refresh=False),
        *CORE_STORES,
        dcc.Store(id="page-store", data=landing_id),
        *plugin_stores,
        dbc.Container([_header(config, plugins)] + body, fluid=True, className="p-4"),
    ], style={"minHeight": "100vh", "backgroundColor": "var(--idems-bg)"})

    _register_navigation(app, plugins, landing_id)
    _register_editor_visibility(app)

    register_auth_callbacks(app)
    register_form_callbacks(app, config)
    register_admin_routes(server)
    for plugin in plugins:
        plugin.register(app, config)

    return app


def _register_navigation(app, plugins, landing_id):
    nav_to_page = {f"nav-{p.id}": p.id for p in plugins}
    page_ids = [p.id for p in plugins]

    @app.callback(
        [Output(f"{pid}-container", "style") for pid in page_ids]
        + [Output(f"nav-{pid}", "className") for pid in page_ids]
        + [Output("page-store", "data", allow_duplicate=True)],
        [Input(f"nav-{pid}", "n_clicks") for pid in page_ids]
        + [Input("page-store", "data")],
        prevent_initial_call="initial_duplicate",
    )
    def switch_page(*_args):
        """Toggles CSS display so no page loses its state on navigation."""
        trigger = ctx.triggered_id
        page = _args[-1]
        if trigger in nav_to_page:
            page = nav_to_page[trigger]
        if page not in page_ids:
            page = landing_id

        # page-store is both an input and an output, so that a page can drive
        # navigation itself. Echoing it back when it was the trigger would just
        # re-enter this callback.
        store = no_update if trigger == "page-store" else page

        show, hide = {"display": "block"}, {"display": "none"}
        styles = [show if pid == page else hide for pid in page_ids]
        classes = [
            "nav-page-btn active me-1" if pid == page else "nav-page-btn me-1"
            for pid in page_ids
        ]
        return styles + classes + [store]


def _register_editor_visibility(app):
    @app.callback(
        Output("editor-popup", "is_open", allow_duplicate=True),
        [Input("table-selector", "value"),
         Input(EDITOR_REQUEST_STORE, "data"),
         Input("url", "hash"),
         Input("editor-popup", "is_open")],
        prevent_initial_call=True,
    )
    def handle_editor_visibility(table_val, request, url_hash, is_open_state):
        trigger = ctx.triggered_id
        if trigger == "editor-popup":
            return is_open_state
        if trigger in ["table-selector", EDITOR_REQUEST_STORE, "url"]:
            if trigger == "table-selector" and not table_val:
                return is_open_state
            if trigger == EDITOR_REQUEST_STORE and not request:
                return is_open_state
            if trigger == "url" and (not url_hash or "edit" not in url_hash):
                return is_open_state
            return True
        return is_open_state
