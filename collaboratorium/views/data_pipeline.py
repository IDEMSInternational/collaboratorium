"""
data_pipeline.py
Executes the I/O bound database queries and graph traversals.
Listens to frontend filter inputs and dumps raw element JSON into dcc.Store.
"""
import yaml
from dash import Input, Output, State
from auth import login_required
from db import build_elements_from_db
from analytics import log_view_event

def register_pipeline_callbacks(app, config):
    @app.callback(
        Output('intermediate-graph-data', 'data'),
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
        State('current-person-id', 'data')
    )
    @login_required
    def process_data_pipeline(loaded, view_id, targets, start, end, degree, types, degree_types, inout, apply_clicks, yaml_text, person_id):
        custom_pipeline = None
        error_msg = ""
        used_advanced = 0

        if yaml_text and apply_clicks and apply_clicks > 0:
            used_advanced = 1
            try:
                custom_pipeline = yaml.safe_load(yaml_text)
                if not isinstance(custom_pipeline, list):
                    error_msg = "Error: Pipeline must be a YAML list (array)."
                    custom_pipeline = None
            except Exception as e:
                error_msg = f"YAML Error: {str(e)}"
        
        # 1. Heavy Database and Graph Traversal Execution
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
        
        # 2. UX Analytics Logging
        node_count = sum(1 for e in elements if 'source' not in e.get('data', {}))
        log_view_event(
            person_id=person_id, view_id=view_id, target_entities=targets,
            used_advanced_pipeline=used_advanced, degree=degree, node_types=types,
            degree_types=degree_types, degree_inout=inout, start_date=start,
            end_date=end, node_count=node_count
        )

        # 3. Output to Decoupled dcc.Store Cache
        return elements, error_msg