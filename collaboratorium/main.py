# main.py
import os
from datetime import datetime

from auth import server, login_required, register_auth_callbacks
from admin_routes import register_admin_routes

from dash import Dash, html, dcc, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto

from form_gen import register_form_callbacks
from db import init_db, db_connect
from analytics import init_db as analytics_init_db
from config_parser import load_config

# --- New Imports ---
from graph_view import generate_graph_layout, register_graph_callbacks
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
        dbc.Col([generate_graph_layout(config)], width=12)
    ])
elif editor_layout_type == "sidebar":
    editor_container = dbc.Offcanvas([
        editor_contents
    ], id="editor-popup", title="Editor", is_open=False, placement="end")
    main_content_row = dbc.Row([
        dbc.Col([generate_graph_layout(config)], width=12)
    ])
else:
    # Fallback to the traditional 8/4 grid if explicitly designated as inline
    editor_container = html.Div(id="editor-popup", style={"display": "none"})
    main_content_row = dbc.Row([
        dbc.Col([generate_graph_layout(config)], width=8),
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

    dbc.Container([
        dbc.Row([
            dbc.Col(html.H2(config["title"], className="mb-4"), width=6),
            dbc.Col([
                dbc.Button([html.I(className="bi bi-plus-circle me-2"), "Add Element"], id="btn-add-element", color="success", className="me-3 fw-bold"),
                html.Div(id="login-area", style={"display": "inline-block"})
            ], width=6, className="text-end")
        ]),

        main_content_row,
        editor_container
    ], fluid=True, className="p-4")
], style={'minHeight': '100vh', 'backgroundColor': 'var(--idems-bg)'})


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
register_graph_callbacks(app, config)
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