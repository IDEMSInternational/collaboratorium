"""
tab_report.py
Renders formatted hierarchical Markdown reports based on the stable data cache.
"""
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc
from report_generator import generate_markdown_report

def register_report_callbacks(app, config):
    @app.callback(
        Output('report-container', 'children'),
        Input('intermediate-graph-data', 'data'),
    )
    def render_report(elements):
        if not elements:
            return html.Div("No data to display.", className="text-muted p-4 text-center")
            
        try:
            reports_cfg = config.get("reports", {})
            if not reports_cfg:
                return html.Div("No reports configured in config.yaml under 'reports:'.", className="text-muted p-4 text-center")
                
            report_id = list(reports_cfg.keys())[0]
            report_cfg = reports_cfg[report_id]
            full_md = generate_markdown_report(report_cfg, elements)

            return html.Div([
                dbc.Row([
                    dbc.Col(html.H5(report_cfg.get('name', 'Report'), className="text-primary m-0"), width=8),
                    dbc.Col(
                        dcc.Clipboard(
                            content=full_md, 
                            className="btn btn-outline-secondary btn-sm float-end", 
                            style={"fontSize": "16px"},
                            title="Copy Markdown"
                        ), 
                        width=4, className="text-end"
                    )
                ], className="mb-3 align-items-center"),
                html.Div(
                    dcc.Markdown(full_md, dangerously_allow_html=True), 
                    style={'backgroundColor': 'white', 'padding': '30px', 'borderRadius': '8px', 'border': '1px solid var(--border-color)', 'minHeight': '400px'}
                )
            ], className="p-3")
            
        except Exception as e:
            return html.Div(f"Error generating report: {e}", className="text-danger p-4")