"""
The Explore page: graph, spreadsheet and report views.

General by construction — every view is driven by the deployment's
`filter_registry`, `views` and pipeline config, and no table is named here. It
declares no `requires_tables` for that reason: it works against whatever schema
the deployment defines.
"""
from dash import dcc
import dash_cytoscape as cyto

from pantograph.plugins import Plugin as BasePlugin

from pantograph_explore.data_pipeline import register_pipeline_callbacks
from pantograph_explore.tab_graph import register_graph_callbacks
from pantograph_explore.tab_report import register_report_callbacks
from pantograph_explore.tab_spreadsheet import register_spreadsheet_callbacks
from pantograph_explore.view_layout import generate_main_layout, register_layout_callbacks

# Registers the extra Cytoscape layouts (cose-bilkent, dagre, klay) that
# deployments select in network_vis.layout. Cytoscape is this plugin's
# dependency, not core's.
cyto.load_extra_layouts()


class Plugin(BasePlugin):
    id = "explore"
    label = "Explore"

    def layout(self, config):
        return generate_main_layout(config)

    def stores(self):
        # Which view (degree, traversal, …) is active. Read and written only by
        # this plugin's callbacks.
        return [dcc.Store(id="current-view-state", data="view-degree")]

    def register(self, app, config):
        register_layout_callbacks(app, config)
        register_pipeline_callbacks(app, config)
        register_graph_callbacks(app, config)
        register_spreadsheet_callbacks(app, config)
        register_report_callbacks(app, config)
