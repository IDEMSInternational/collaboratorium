# main.py
import os
from datetime import datetime

from auth import server, login_required, register_auth_callbacks
from admin_routes import register_admin_routes

from dash import Dash, html, dcc, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from form_gen import register_form_callbacks
from db import init_db, db_connect
from analytics import init_db as analytics_init_db
from config_parser import load_config

from views.view_layout import generate_main_layout, register_layout_callbacks
from views.data_pipeline import register_pipeline_callbacks
from views.tab_graph import register_graph_callbacks
from views.tab_spreadsheet import register_spreadsheet_callbacks
from views.tab_report import register_report_callbacks
from views.tab_dashboard import generate_dashboard_layout, register_dashboard_callbacks
from tools.analysis_report import init_analytics_app

# ---------------------------------------------------------
# Config Load
# ---------------------------------------------------------
config = load_config("config.yaml")
forms_config = config.get("forms", {})

# ---------------------------------------------------------
# Database initialization
# ---------------------------------------------------------
init_db(config)
analytics_init_db()

# ---------------------------------------------------------
# Dash app setup
# ---------------------------------------------------------

cyto.load_extra_layouts()

# Initialize the Analytics App on the same Flask Server (Mounts securely to /analytics/)
init_analytics_app(server)

# Core Graph application initialized at the root domain
app = Dash(
    config["title"],
    title=config["title"],
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    server=server,
    suppress_callback_exceptions=True,
    assets_folder='assets',
    assets_url_path='assets',
)

app._favicon = ("cropped-IDEMS_logomark_with_border_circle-32x32.png") 

# Create the centralized overlay editor panel contents
editor_contents = html.Div([
    html.Div([
        html.Label("Add: "),
        dcc.Dropdown(
            id="table-selector",
            options=[{"label": t, "value": t} for t in config["tables"].keys()],
            placeholder="Add new element...", style={"width": "100%", "marginBottom": "15px"}
        ),
    ], id="add-dropdown-container"),
    html.Div(id="form-container"),
    html.Div(id="out_msg", children=[], className="mt-3"),
])

editor_layout_type = config.get("editor_layout", "modal")

# Choose container presentation strictly matching deployment configuration profiles
if editor_layout_type == "modal":
    editor_container = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Editor")),
        dbc.ModalBody(editor_contents),
    ], id="editor-popup", is_open=False, size="xl")
    main_content_row = dbc.Row([
        dbc.Col([generate_main_layout(config)], width=12)
    ])
elif editor_layout_type == "sidebar":
    editor_container = dbc.Offcanvas([
        editor_contents
    ], id="editor-popup", title="Editor", is_open=False, placement="end")
    main_content_row = dbc.Row([
        dbc.Col([generate_main_layout(config)], width=12)
    ])
else:
    # Fallback to the traditional 8/4 grid if explicitly designated as inline
    editor_container = html.Div(id="editor-popup", style={"display": "none"})
    main_content_row = dbc.Row([
        dbc.Col([generate_main_layout(config)], width=8),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H4("Editor", className="m-0")),
                dbc.CardBody(editor_contents)
            ])
        ], width=4)
    ])

# Hydrate the complete page application wrapper template
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='selected-action', data=None),
    dcc.Store(id='selected-node', data=None),
    dcc.Store(id='intermediary-loaded', data=False),
    dcc.Store(id="current-person-id", data=None),
    dcc.Store(id="form-refresh", data=False),
    dcc.Store(id="current-view-state", data="view-degree"),
    # The Dashboard is the landing page: it answers "what have I put in" before
    # Explore asks you to describe a query.
    dcc.Store(id="page-store", data="dashboard"),
    # Lets a page request an add-form with fields already filled in, e.g. a new
    # activity that arrives already linked to the initiative you started from.
    dcc.Store(id="form-prefill", data=None),

    dbc.Container([
        dbc.Row([
            dbc.Col(html.H2(config["title"], className="mb-4"), width=3),
            dbc.Col([
                dbc.Button("Dashboard", id="nav-dashboard", n_clicks=0, className="nav-page-btn active me-1"),
                dbc.Button("Explore", id="nav-explore", n_clicks=0, className="nav-page-btn"),
            ], width=3, className="text-center"),
            # Wide enough for three buttons and the user block to share one line.
            dbc.Col([
                # The two most common things to add lead as solid buttons; the
                # catch-all "Add Element" (any of the other tables) recedes to a
                # quiet link so three green buttons don't compete. The plus is
                # text, not an icon: the Bootstrap Icons font isn't loaded here.
                dbc.Button("+ Activity", id="btn-add-activity", color="success", className="me-2 fw-bold"),
                dbc.Button("+ Initiative", id="btn-add-initiative", color="success", className="me-2 fw-bold"),
                dbc.Button("Add other…", id="btn-add-element", color="link", size="sm", className="me-3 text-secondary"),
                html.Div(id="login-area", style={"display": "inline-block"})
            ], width=6, className="text-end")
        ]),

        html.Div(generate_dashboard_layout(config), id="dashboard-container"),
        html.Div(main_content_row, id="explore-container", style={"display": "none"}),
        editor_container
    ], fluid=True, className="p-4")
], style={'minHeight': '100vh', 'backgroundColor': 'var(--idems-bg)'})


@app.callback(
    Output("dashboard-container", "style"),
    Output("explore-container", "style"),
    Output("nav-dashboard", "className"),
    Output("nav-explore", "className"),
    Output("page-store", "data", allow_duplicate=True),
    Input("nav-dashboard", "n_clicks"),
    Input("nav-explore", "n_clicks"),
    Input("page-store", "data"),
    prevent_initial_call='initial_duplicate'
)
def switch_page(_dash_clicks, _explore_clicks, page):
    """Toggles CSS display so neither page loses its state on navigation."""
    trigger = ctx.triggered_id
    if trigger == "nav-dashboard":
        page = "dashboard"
    elif trigger == "nav-explore":
        page = "explore"
    page = page or "dashboard"

    # The store is both an input and an output here, so that other pages (the
    # dashboard's hand-off) can drive navigation. Echoing it back when it was
    # the trigger would just re-enter this callback.
    store = no_update if trigger == "page-store" else page

    on, off = "nav-page-btn active me-1", "nav-page-btn me-1"
    show, hide = {"display": "block"}, {"display": "none"}
    if page == "explore":
        return hide, show, off, "nav-page-btn active", store
    return show, hide, on, "nav-page-btn", store


# Add state persistence listener to automatically trigger modal visibilities on input events
@app.callback(
    Output("editor-popup", "is_open", allow_duplicate=True),
    [Input("table-selector", "value"),
     Input("cyto", "tapNodeData"),
     Input("cyto", "tapEdgeData"),
     Input("url", "hash"),
     Input("editor-popup", "is_open")],
    prevent_initial_call=True
)
def handle_editor_visibility(table_val, node_data, edge_data, url_hash, is_open_state):
    trigger = ctx.triggered_id
    if trigger == "editor-popup":
        return is_open_state
    if trigger in ["table-selector", "cyto", "url"]:
        if trigger == "table-selector" and not table_val:
            return is_open_state
        if trigger == "url" and (not url_hash or "edit" not in url_hash):
            return is_open_state
        return True
    return is_open_state

# ---------------------------------------------------------
# Dash callbacks
# ---------------------------------------------------------
register_auth_callbacks(app)
register_form_callbacks(app, config)
register_layout_callbacks(app, config)
register_dashboard_callbacks(app, config)
register_pipeline_callbacks(app, config)
register_graph_callbacks(app, config)
register_spreadsheet_callbacks(app, config)
register_report_callbacks(app, config)
register_admin_routes(server)

# ---------------------------------------------------------
# Server startup
# ---------------------------------------------------------
if __name__ == "__main__":
    in_docker = os.getcwd() == "/app"
    default_host = "0.0.0.0" if in_docker else "127.0.0.1"

    host = os.environ.get("HOST", default_host)
    port = int(os.environ.get("PORT", "8050"))
    debug_env = os.environ.get("DEBUG", None)
    if debug_env is None:
        debug = not in_docker
    else:
        debug = debug_env.lower() in ("1", "true", "yes", "on")

    print(f"Starting server on {host}:{port} (in_docker={in_docker}, debug={debug})")
    app.run(host=host, port=port, debug=debug, use_reloader=False)