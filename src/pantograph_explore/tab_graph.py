"""
tab_graph.py
Controls the interactive Cytoscape network component and rendering.
"""
from dash import Input, Output

def register_graph_callbacks(app, config):
    @app.callback(
        Output('cyto', 'elements'),
        Input('intermediate-graph-data', 'data')
    )
    def update_graph_elements(elements):
        return elements if elements else []

    @app.callback(
        Output('cyto', 'layout'),
        Input('layout-selector', 'value')
    )
    def update_layout(layout_name):
        layout = config.get("network_vis", {}).get("layout", {}).copy()
        if layout_name:
            layout["name"] = layout_name
        return layout