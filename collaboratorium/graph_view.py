import yaml
from dash import html, dcc, Input, Output, State, ctx, ALL
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from auth import login_required
from db import build_elements_from_db, get_dropdown_options

# ==============================================================
# LAYOUT GENERATION
# ==============================================================

def generate_graph_layout(config):
    registry = config.get("filter_registry", {})
    views = config.get("views", {})
    
    # 1. Dynamically generate View Buttons from YAML
    view_buttons = []
    for v_id, v_cfg in views.items():
        icon_class = v_cfg.get("icon", "bi-circle")
        # Give the first button (usually "All Filters") a distinct light style
        btn_class = "btn btn-primary btn-sm me-2" if v_id != list(views.keys())[0] else "btn btn-light btn-sm me-2 border text-dark fw-bold"
        
        view_buttons.append(
            dbc.Button(
                [html.I(className=f"bi {icon_class} me-2"), v_cfg.get("name", v_id)], 
                id=v_id, n_clicks=0, className=btn_class
            )
        )
    
    # 2. Pre-render ALL filters from the registry
    filter_rows = []
    for f_id, f_cfg in registry.items():
        component = component_for_filter(config, f_id, f_cfg)
        filter_rows.append(
            dbc.Row(
                id=f"container-{f_id}",
                children=[
                    dbc.Col(html.Label(f_cfg.get("label", f_id)), width=3),
                    dbc.Col(component, width=9)
                ],
                className="mb-2 align-items-center",
                style={'display': 'none'}
            )
        )

    yaml_editor = dbc.Accordion([
        dbc.AccordionItem([
            dcc.Textarea(
                id="pipeline-yaml-editor",
                style={'width': '100%', 'height': '200px', 'fontFamily': 'monospace', 'fontSize': '12px'},
                placeholder="- filter: TraversalFilter\n  direction: both..."
            ),
            html.Div([
                dbc.Button("Apply Custom Pipeline", id="btn-apply-pipeline", color="success", size="sm", className="mt-2"),
                html.Span(id="pipeline-error-msg", className="text-danger ms-3", style={'fontSize': '12px'})
            ])
        ], title="Advanced Pipeline Editor (YAML)")
    ], start_collapsed=True, className="mt-3")

    # Set a safe default layout from config
    default_layout = config.get("network_vis", {}).get("layout", {}).get("name", "cose-bilkent")

    return dbc.Card([
        dbc.CardHeader([
            html.Div(view_buttons, style={'display': 'inline-block'}),
            dcc.Dropdown(
                id='layout-selector', 
                options=[{'label': i, 'value': i} for i in ['cose-bilkent', 'dagre', 'klay', 'cose', 'circle', 'grid']], 
                placeholder='Layout...', 
                value=default_layout,
                style={'display': 'inline-block', 'width': '150px', 'verticalAlign': 'bottom', 'marginLeft': '15px'}
            )
        ]),
        dbc.CardBody([
            dbc.Collapse(
                dbc.Card(dbc.CardBody([
                    html.H6(id="active-view-title", className="mb-3 text-primary fw-bold"),
                    html.Div(filter_rows),
                    yaml_editor,
                ]), className="mb-3 border-0 bg-white shadow-sm"),
                id="collapse-filters", is_open=False
            ),
            cyto.Cytoscape(id='cyto', elements=[], style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'}, stylesheet=config["network_vis"]["stylesheet"])
        ])
    ])

def component_for_filter(config, f_id, f_cfg):
    """Simple wrapper to create standard components for the registry."""
    t = f_cfg.get('type')
    cid = f"filter-{f_id}"
    
    if t == "select_multiple" and f_cfg.get("appearance") == "dropdown":
        return dcc.Dropdown(id=cid, multi=True, options=[])
        
    if t == "select_multiple" and f_cfg.get("appearance") == "checkboxes":
        opts, vals = [], []
        if f_id in ["node-type-filter", "node-type-degree"]:
            opts = [{'label': f" {x}", 'value': x} for x in config.get("node_tables", [])]
            vals = config.get("node_tables", [])
        elif f_id == "degree-inout":
            opts_dict = f_cfg.get("parameters", {}).get("options", {})
            opts = [{'label': v, 'value': k} for k, v in opts_dict.items()]
            vals = list(opts_dict.keys())
            
        return dcc.Checklist(id=cid, inline=True, inputClassName="me-1", labelClassName="me-3", options=opts, value=vals)
        
    if t == "date_range":
        return dcc.DatePickerRange(id=cid, clearable=True)
        
    if t == "integer":
        params = f_cfg.get("parameters", {})
        return dcc.Input(id=cid, type="number", min=params.get("min"), max=params.get("max"), value=params.get("default", 1), className="form-control form-control-sm")
        
    return html.Div(f"Unsupported Type: {t}")

# ==============================================================
# CALLBACKS
# ==============================================================

def register_graph_callbacks(app, config):
    registry = config.get("filter_registry", {})
    views = config.get("views", {})
    
    # Safe fallback if views is empty
    first_view_id = list(views.keys())[0] if views else None
    # 1. THE VIEW MANAGER
    @app.callback(
        [Output("collapse-filters", "is_open"), 
         Output("active-view-title", "children"),
         Output("current-view-state", "data"),
         Output("layout-selector", "value"),
         Output("pipeline-yaml-editor", "value")] + # <-- OUTPUT TO EDITOR
        [Output(f"container-{f_id}", "style") for f_id in registry.keys()] +
        [Output(f"filter-target-entity", "options")], 
        [Input(v_id, "n_clicks") for v_id in views.keys()],
        [State("collapse-filters", "is_open"), 
         State("current-view-state", "data"),
         State("layout-selector", "value")]
    )
    def manage_view_logic(*args):
        current_layout = args[-1]
        current_view = args[-2]
        is_open = args[-3]
        trigger = ctx.triggered_id or first_view_id
        
        # Determine active view config
        if trigger == first_view_id:
            # If "All Filters" is clicked, DO NOT change the active graph pipeline
            active_view_id = current_view if current_view else first_view_id
            styles = [None for _ in registry.keys()]
            new_layout = current_layout
            new_is_open = True
            base_name = views.get(active_view_id, {}).get("name", active_view_id)
            title = f"{base_name} (Advanced Settings)"
            target_entity_cfg = registry.get("target-entity", {})
            pipeline_data = views.get(active_view_id, {}).get("pipeline", [])
        else:
            active_view_id = trigger
            view_cfg = views.get(trigger, {})
            active_filters = view_cfg.get("active_filters", {})
            styles = [None if f_id in active_filters else {'display': 'none'} for f_id in registry.keys()]
            new_layout = view_cfg.get("layout", current_layout)
            new_is_open = not is_open if trigger == current_view and ctx.triggered_id else True
            title = view_cfg.get("name", "View")
            target_entity_cfg = active_filters.get("target-entity") or registry.get("target-entity", {})
            pipeline_data = view_cfg.get("pipeline", [])
        yaml_string = yaml.dump(pipeline_data, sort_keys=False) if pipeline_data else "[]"
        # Populate the target dropdown based on allowed source_tables
        params = target_entity_cfg.get("parameters", {})
        default_params = registry.get("target-entity", {}).get("parameters", {})
        source_tables = params.get("source_tables", default_params.get("source_tables", []))
        options = get_dropdown_options_multi(config, source_tables)
        
        return [new_is_open, title, active_view_id, new_layout, yaml_string] + styles + [options]

    # 2. THE GRAPH REFRESH
    @app.callback(
        Output('cyto', 'elements'),
        Output('pipeline-error-msg', 'children'),
        Input('intermediary-loaded', 'data'),
        Input('current-view-state', 'data'),
        Input('filter-target-entity', 'value'),
        Input('filter-date-range', 'start_date'),
        Input('filter-date-range', 'end_date'),
        Input('filter-degree-val', 'value'),
        Input('filter-node-type-filter', 'value'),
        Input('filter-node-type-degree', 'value'),
        Input('filter-degree-inout', 'value'),
        Input('btn-apply-pipeline', 'n_clicks'),
        State('pipeline-yaml-editor', 'value'),
    )
    def refresh_graph(loaded, view_id, targets, start, end, degree, types, degree_types, inout, apply_clicks, yaml_text):
        custom_pipeline = None
        error_msg = ""

        if ctx.triggered_id == 'btn-apply-pipeline' and yaml_text:
            try:
                custom_pipeline = yaml.safe_load(yaml_text)
                if not isinstance(custom_pipeline, list):
                    error_msg = "Error: Pipeline must be a YAML list (array)."
                    custom_pipeline = None
            except Exception as e:
                error_msg = f"YAML Error: {str(e)}"
        
        elements = build_elements_from_db(
            config, 
            view_mode=view_id, 
            target_nodes=targets,
            start_date=start,
            end_date=end,
            degree=degree,
            node_types=types,
            degree_types=degree_types,
            degree_inout=inout,
            custom_pipeline=custom_pipeline,
        )
        
        return elements, error_msg

    # 3. THE LAYOUT SELECTOR
    @app.callback(
        Output('cyto', 'layout'),
        Input('layout-selector', 'value')
    )
    def layout_selector(layout_name):
        layout = config.get("network_vis", {}).get("layout", {}).copy()
        if layout_name:
            layout["name"] = layout_name
        return layout

# --- DB Helper ---
def get_dropdown_options_multi(config, source_tables):
    all_options = []
    for table_name in source_tables:
        if table_name not in config.get("tables", {}):
            continue
        options = get_dropdown_options(table_name, "id", "name")
        if options:
            for opt in options:
                opt['label'] = f"{table_name.title()}: {opt['label']}"
                opt['value'] = f"{table_name}-{opt['value']}"
                all_options.append(opt)
    return sorted(all_options, key=lambda x: x['label'])