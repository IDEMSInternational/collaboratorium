"""
view_layout.py
Orchestrates the main UI components for the Graph/Spreadsheet/Report views.
Registers callbacks for switching tabs and toggling the filter sidebar.
"""
import yaml
from dash import html, dcc, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from db import get_dropdown_options

def component_for_filter(config, f_id, f_cfg):
    """Generates standard Dash components for the filter registry."""
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

def generate_main_layout(config):
    """Generates the main container including the dcc.Store intermediary cache."""
    registry = config.get("filter_registry", {})
    views = config.get("views", {})
    
    view_buttons = []
    for v_id, v_cfg in views.items():
        icon_class = v_cfg.get("icon", "bi-circle")
        btn_class = "btn btn-primary btn-sm me-2" if v_id != list(views.keys())[0] else "btn btn-light btn-sm me-2 border text-dark fw-bold"
        view_buttons.append(
            dbc.Button([html.I(className=f"bi {icon_class} me-2"), v_cfg.get("name", v_id)], id=v_id, n_clicks=0, className=btn_class)
        )
    
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

    settings_accordion = dbc.Accordion([
        dbc.AccordionItem([html.Div(filter_rows)], title="View and Filter Settings")
    ], start_collapsed=True)

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

    default_layout = config.get("network_vis", {}).get("layout", {}).get("name", "cose-bilkent")

    return dbc.Card([
        dcc.Store(id='intermediate-graph-data'), 

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
                dbc.Card(dbc.CardBody([settings_accordion, yaml_editor]), className="border-0 bg-white shadow-sm"),
                id="collapse-filters", is_open=False
            ),
            dbc.Tabs(id="output-tabs", active_tab="tab-spreadsheet", children=[
                dbc.Tab(label="Spreadsheet", tab_id="tab-spreadsheet"),
                dbc.Tab(label="Report", tab_id="tab-report"),
                dbc.Tab(label="Network Graph", tab_id="tab-graph"),
            ], className="mb-3"),
            html.Div([
                html.Div(
                    cyto.Cytoscape(id='cyto', elements=[], style={'width': '100%', 'height': '600px', 'backgroundColor': '#f8f9fa'}, stylesheet=config["network_vis"]["stylesheet"]),
                    id='graph-container'
                ),
                html.Div([
                    dbc.Tabs(id="spreadsheet-tabs", className="mt-3"),       # Navigation Only
                    html.Div(id="spreadsheet-grid-container", className="mt-3") # Grid Content Only
                ], id='spreadsheet-container', style={'display': 'none'}),
                html.Div(id='report-container', style={'display': 'none'})
            ])
        ])
    ])

def register_layout_callbacks(app, config):
    registry = config.get("filter_registry", {})
    views = config.get("views", {})
    first_view_id = list(views.keys())[0] if views else None

    @app.callback(
        [Output("collapse-filters", "is_open"), 
         Output("current-view-state", "data"),
         Output("layout-selector", "value"),
         Output("pipeline-yaml-editor", "value")] + 
        [Output(f"container-{f_id}", "style") for f_id in registry.keys()] +
        [Output(f"filter-target-entity", "options")] +
        [Output(v_id, "className") for v_id in views.keys()],
        [Input(v_id, "n_clicks") for v_id in views.keys()],
        [State("collapse-filters", "is_open"), State("current-view-state", "data"), State("layout-selector", "value")]
    )
    def manage_view_logic(*args):
        current_layout, current_view, is_open = args[-1], args[-2], args[-3]
        trigger = ctx.triggered_id or current_view
        
        active_view_id = current_view if trigger == first_view_id and current_view else trigger
        view_cfg = views.get(active_view_id, {})
        
        active_filters = view_cfg.get("active_filters", {}) if trigger != first_view_id else {}
        styles = [None if f_id in active_filters or trigger == first_view_id else {'display': 'none'} for f_id in registry.keys()]
        
        new_layout = view_cfg.get("layout", current_layout)
        new_is_open = not is_open if trigger == current_view and ctx.triggered_id else True
        pipeline_data = view_cfg.get("pipeline", [])
        yaml_string = yaml.dump(pipeline_data, sort_keys=False) if pipeline_data else "[]"
        
        target_entity_cfg = active_filters.get("target-entity") or registry.get("target-entity", {})
        source_tables = target_entity_cfg.get("parameters", {}).get("source_tables", registry.get("target-entity", {}).get("parameters", {}).get("source_tables", []))
        
        all_options = []
        for table_name in source_tables:
            if table_name in config.get("tables", {}):
                options = get_dropdown_options(table_name, "id", "name")
                if options:
                    for opt in options:
                        opt['label'] = f"{table_name.title()}: {opt['label']}"
                        opt['value'] = f"{table_name}-{opt['value']}"
                        all_options.append(opt)
        
        button_classes = []
        for v_id in views.keys():
            if v_id == active_view_id:
                button_classes.append("btn btn-warning btn-sm me-2 fw-bold text-dark shadow-sm")
            elif v_id == first_view_id:
                button_classes.append("btn btn-light btn-sm me-2 border text-dark fw-bold")
            else:
                button_classes.append("btn btn-primary btn-sm me-2")
        
        return [new_is_open, active_view_id, new_layout, yaml_string] + styles + [sorted(all_options, key=lambda x: x['label'])] + button_classes

    @app.callback(
        Output('graph-container', 'style'), Output('spreadsheet-container', 'style'), Output('report-container', 'style'),
        Input('output-tabs', 'active_tab')
    )
    def switch_tabs(active_tab):
        """Preserves DOM state by toggling CSS display instead of unmounting."""
        return (
            {'display': 'block'} if active_tab == "tab-graph" else {'display': 'none'},
            {'display': 'block'} if active_tab == "tab-spreadsheet" else {'display': 'none'},
            {'display': 'block'} if active_tab == "tab-report" else {'display': 'none'}
        )

    @app.callback(
        Output('filter-target-entity', 'value'),
        Input('current-person-id', 'data')
    )
    def set_default_target_entity(person_id):
        if person_id: return [f"people-{person_id}"]
        return no_update